from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


LANE_ROOT = Path(__file__).resolve().parent
ROOT = LANE_ROOT.parents[1]

from compiler import BoatleeCompilerAdapter, V27CompilerAdapter, compile_genome
from exact_evaluator import CONTROL_PATHS, ROUTE_PATHS, engine_fingerprint
from lineage import extract_ninth_cow_lineage
from materialize import isolated_import, materialize, static_runtime_audit
from model import CompiledCandidate, SemanticGenome, StaticRejection, compiled_from_payload
from runtime_patch import candidate_runtime_payload
from scheduler import create_manifest, file_sha256, load_manifest, status
from search_space import independent_populations, one_factor_frontier, structural_roots


def load_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SeedGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.modules = []
        for lane in ("v27_current_meta", "boatlee_v16_rc2_market_relay"):
            path = ROOT / "research" / "main_approach" / lane / "development" / "runtime.py"
            cls.modules.append(load_file(f"seed_guard_{lane}", path))

    def test_atomic_same_crop_cancellation(self) -> None:
        action = {
            "farmer": ["PLANT", "CORN"],
            "hands": [["PLANT", "CORN"], ["PLANT", "POTATO"]],
            "market": [["SELL", "MILK", 1]],
        }
        obs = {"private": {"seeds": {"CORN": 1, "POTATO": 1}}}
        for module in self.modules:
            result = module._project_atomic_plants(obs, action)
            self.assertEqual(result["farmer"], ["PASS"])
            self.assertEqual(result["hands"][0], ["PASS"])
            self.assertEqual(result["hands"][1], ["PLANT", "POTATO"])
            self.assertEqual(result["market"], action["market"])
            self.assertEqual(action["farmer"], ["PLANT", "CORN"])

    def test_readable_sufficient_is_identity(self) -> None:
        action = {"farmer": ["PLANT", "CORN"], "hands": [], "market": []}
        for module in self.modules:
            self.assertIs(module._project_atomic_plants({"private": {"seeds": {"CORN": 1}}}, action), action)

    def test_missing_or_unreadable_ledger_preserves_incumbent(self) -> None:
        action = {"farmer": ["PLANT", "CORN"], "hands": [["PLANT", "CORN"]], "market": []}
        observations = ({}, {"private": {}}, {"private": {"seeds": {}}}, {"private": {"seeds": {"CORN": "?"}}})
        for module in self.modules:
            for obs in observations:
                self.assertIs(module._project_atomic_plants(obs, action), action)


class GenomeCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.route = json.loads(ROUTE_PATHS["v27_current_meta"].read_text(encoding="utf-8"))

    def test_local_lineage_reconstructs_ninth_cow_anchor(self) -> None:
        lineage = extract_ninth_cow_lineage(self.route, source="unit-route")
        self.assertEqual((lineage.purchase_step, lineage.build_step, lineage.place_step), (361, 517, 518))
        self.assertEqual(lineage.tile, (7, 3))
        self.assertEqual(lineage.cow_ordinal, 9)

    def test_same_genome_has_independent_lane_candidate_ids(self) -> None:
        genome = SemanticGenome(structural_root="control")
        adapters = (
            V27CompilerAdapter("v27_current_meta", ROUTE_PATHS["v27_current_meta"], CONTROL_PATHS["v27_current_meta"]),
            BoatleeCompilerAdapter("boatlee_v16_rc2_market_relay", ROUTE_PATHS["boatlee_v16_rc2_market_relay"], CONTROL_PATHS["boatlee_v16_rc2_market_relay"]),
        )
        compiled = [compile_genome(adapter, genome, self.route, ()) for adapter in adapters]
        self.assertTrue(all(isinstance(row, CompiledCandidate) for row in compiled))
        self.assertNotEqual(compiled[0].candidate_id, compiled[1].candidate_id)
        self.assertEqual(compiled[0].genome.genome_id, compiled[1].genome.genome_id)

    def test_payload_round_trip(self) -> None:
        adapter = V27CompilerAdapter("v27_current_meta", ROUTE_PATHS["v27_current_meta"], CONTROL_PATHS["v27_current_meta"])
        result = compile_genome(adapter, SemanticGenome(structural_root="control"), self.route, ())
        self.assertIsInstance(result, CompiledCandidate)
        payload = candidate_runtime_payload(result)
        restored = compiled_from_payload(payload)
        self.assertEqual(restored.candidate_id, result.candidate_id)
        self.assertEqual(restored.payload(), result.payload())

    def test_windows_and_dispositions_are_bounded_and_explicit(self) -> None:
        adapter = V27CompilerAdapter("v27_current_meta", ROUTE_PATHS["v27_current_meta"], CONTROL_PATHS["v27_current_meta"])
        result = compile_genome(adapter, SemanticGenome(structural_root="control"), self.route, ())
        self.assertIsInstance(result, CompiledCandidate)
        self.assertTrue(all(8 <= window.end - window.start + 1 <= 48 for window in result.windows))
        self.assertTrue(all(row.disposition in {"retained", "reassigned", "reclaimed"} for row in result.displaced_actions))

    def test_search_space_is_one_factor_not_cartesian(self) -> None:
        roots = structural_roots()
        frontier = one_factor_frontier(roots)
        self.assertTrue(all(len(row.mutations) <= 1 for row in frontier))
        populations = independent_populations()
        self.assertEqual(set(populations), {"v27_current_meta", "boatlee_v16_rc2_market_relay"})
        self.assertIsNot(populations["v27_current_meta"], populations["boatlee_v16_rc2_market_relay"])

    def test_public_selector_declares_no_identity(self) -> None:
        adapter = V27CompilerAdapter("v27_current_meta", ROUTE_PATHS["v27_current_meta"], CONTROL_PATHS["v27_current_meta"])
        result = compile_genome(adapter, SemanticGenome(structural_root="control"), self.route, ())
        self.assertIsInstance(result, CompiledCandidate)
        self.assertFalse(result.public_selector["opponent_identity"])
        self.assertNotIn("private", " ".join(result.public_selector["opponent_inputs"]))


class MaterializationAndSchedulerTests(unittest.TestCase):
    def _candidate(self) -> CompiledCandidate:
        route = json.loads(ROUTE_PATHS["v27_current_meta"].read_text(encoding="utf-8"))
        adapter = V27CompilerAdapter("v27_current_meta", ROUTE_PATHS["v27_current_meta"], CONTROL_PATHS["v27_current_meta"])
        result = compile_genome(adapter, SemanticGenome(structural_root="control"), route, ())
        if isinstance(result, StaticRejection):
            self.fail(result)
        return result

    def test_materialized_control_wrapper_is_isolated_and_standard_library(self) -> None:
        with tempfile.TemporaryDirectory(prefix="topology-test-") as temp:
            output = Path(temp) / "main.py"
            materialize(CONTROL_PATHS["v27_current_meta"], self._candidate(), output)
            self.assertTrue(static_runtime_audit(output)["pass"])
            self.assertTrue(isolated_import(output)["callable_agent"])

    def test_manifest_hash_and_read_only_status(self) -> None:
        candidate = candidate_runtime_payload(self._candidate())
        job = {
            "job_id": "job_unit",
            "lane": candidate["lane"],
            "candidate_id": candidate["candidate_id"],
            "opponent": "other_incumbent",
            "seed": 811407,
            "seat": 0,
            "candidate": candidate,
            "failure_injection": None,
        }
        with tempfile.TemporaryDirectory(prefix="topology-manifest-") as temp:
            root = Path(temp)
            manifest_path = root / "manifest.json"
            manifest = create_manifest(
                manifest_path,
                [job],
                run_id="unit",
                stage="D3",
                engine=engine_fingerprint(),
                seed_registry_sha256=file_sha256(LANE_ROOT / "protocol_seed_registry.json"),
            )
            self.assertEqual(load_manifest(manifest_path)["manifest_sha256"], manifest["manifest_sha256"])
            absent = root / "absent-run"
            snapshot = status(manifest_path, absent)
            self.assertFalse(absent.exists())
            self.assertEqual(snapshot["counts"]["missing"], 1)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["stage"] = "tampered"
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_manifest(manifest_path)

    def test_development_manifest_rejects_fresh_seed(self) -> None:
        candidate = candidate_runtime_payload(self._candidate())
        job = {
            "job_id": "job_bad_seed",
            "lane": candidate["lane"],
            "candidate_id": candidate["candidate_id"],
            "opponent": "other_incumbent",
            "seed": 999998,
            "seat": 0,
            "candidate": candidate,
            "failure_injection": None,
        }
        with tempfile.TemporaryDirectory(prefix="topology-seed-") as temp:
            with self.assertRaises(PermissionError):
                create_manifest(Path(temp) / "manifest.json", [job], run_id="bad", stage="D3", engine={}, seed_registry_sha256="unit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
