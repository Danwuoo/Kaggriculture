from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


LANE = Path(__file__).resolve().parents[1]
ROOT = LANE.parents[1]
if str(LANE) not in sys.path:
    sys.path.insert(0, str(LANE))

from max_search.checkpoint import RunManifest, atomic_json  # noqa: E402
from max_search.coordinator import CandidateIndex  # noqa: E402
from max_search.contexts import ContextError, ContextRegistry  # noqa: E402
from max_search.contract import LANES, canonical_json, load_contract  # noqa: E402
from max_search.execution import ExecutionError, ExecutionManifest, ExecutionState  # noqa: E402
from max_search.evolution import FitnessVector, select_survivors_scalable  # noqa: E402
from max_search.genome import FullTapeGenome, RootRegistry  # noqa: E402
from max_search.runner import (  # noqa: E402
    SearchStore, _bounded_parallel, _expected_progress, _signed_artifact,
    _ensure_generation_pruned, _prepare_receipt_retention, _technical_pass,
    _verify_completion_storage, resource_estimate,
)


CONTRACT_PATH = LANE / "max_search_contract.json"


def artifacts(families=("other_incumbent", "kaito_v21")):
    return {
        family: {
            "by_lane": {
                lane: {"path": f"C:/frozen/{lane}/{family}.py", "bytes": 10, "sha256": "a" * 64}
                for lane in LANES
            }
        }
        for family in families
    }


def development_draft():
    return {
        "schema_version": 1,
        "kind": "maximum_search_context_draft",
        "mode": "development",
        "stages": {
            "t0": [{"opponent_family": "other_incumbent", "seed": 1, "seat": 0}],
            "t1": [{"opponent_family": "kaito_v21", "seed": 2, "seat": 1}],
            "holdout": [{"opponent_family": "other_incumbent", "seed": 3, "seat": 1}],
        },
        "freshness": {
            "source": "unit-test technical contexts",
            "consumed_seed_overlap_allowed": True,
            "notes": "not efficacy evidence",
        },
    }


def formal_draft():
    t0 = [
        {"opponent_family": "other_incumbent", "seed": 100 + index // 2, "seat": index % 2}
        for index in range(6)
    ]
    t1 = [
        {
            "opponent_family": "other_incumbent" if index < 12 else "kaito_v21",
            "seed": 200 + index // 2,
            "seat": index % 2,
        }
        for index in range(24)
    ]
    holdout = [
        {"opponent_family": "other_incumbent", "seed": 400, "seat": 0},
        {"opponent_family": "kaito_v21", "seed": 401, "seat": 1},
    ]
    return {
        "schema_version": 1,
        "kind": "maximum_search_context_draft",
        "mode": "formal",
        "stages": {"t0": t0, "t1": t1, "holdout": holdout},
        "freshness": {
            "source": "separately authorized fresh registry",
            "consumed_seed_overlap_allowed": False,
            "notes": "unit-test shape only",
        },
    }


def fake_development_manifest(contract, temporary: Path) -> tuple[RunManifest, Path]:
    registry = RootRegistry.load_workspace(ROOT, include_public=False)
    source_snapshot = {
        "schema_version": 2,
        "controls": {lane: {"sha256": "b" * 64} for lane in LANES},
        "pool_lanes": False,
    }
    manifest = RunManifest.create(
        run_id="execution_test_preflight", contract=contract,
        source_snapshot=source_snapshot, root_manifest=registry.manifest(), proposal_seed=7,
    )
    initial = temporary / "initial.json"
    initial.write_text("{}", encoding="utf-8")
    return manifest, initial


class ContextRegistryTests(unittest.TestCase):
    def test_formal_registry_closes_exact_tier_counts_and_round_trips(self):
        registry = ContextRegistry.create(formal_draft(), opponent_artifacts=artifacts())
        self.assertEqual(len(registry.contexts("t0")), 6)
        self.assertEqual(len(registry.contexts("t1")), 24)
        self.assertEqual(len({row["context_id"] for stage in ("t0", "t1", "holdout") for row in registry.contexts(stage)}), 32)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "contexts.json"
            atomic_json(path, registry.payload)
            self.assertEqual(ContextRegistry.load(path, require_mode="formal"), registry)

    def test_stage_seed_overlap_and_formal_count_tamper_fail_closed(self):
        draft = development_draft()
        draft["stages"]["holdout"][0]["seed"] = 1
        with self.assertRaises(ContextError):
            ContextRegistry.create(draft, opponent_artifacts=artifacts())
        draft = formal_draft()
        draft["stages"]["t1"].pop()
        with self.assertRaises(ContextError):
            ContextRegistry.create(draft, opponent_artifacts=artifacts())

    def test_empty_family_and_artifact_mismatch_fail_closed(self):
        draft = development_draft()
        draft["stages"]["t0"][0]["opponent_family"] = ""
        with self.assertRaises(ContextError):
            ContextRegistry.create(draft, opponent_artifacts=artifacts())
        with self.assertRaises(ContextError):
            ContextRegistry.create(development_draft(), opponent_artifacts=artifacts(("other_incumbent",)))


class ExecutionManifestTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_contract(CONTRACT_PATH)

    def test_development_manifest_and_checkpoint_are_closed(self):
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            development_manifest, initial = fake_development_manifest(self.contract, temporary)
            registry = ContextRegistry.create(development_draft(), opponent_artifacts=artifacts())
            manifest = ExecutionManifest.create(
                run_id="execution_test", contract=self.contract,
                development_manifest=development_manifest, preflight_root=temporary,
                initial_population_path=initial, context_registry=registry,
                physical_workers=1, max_in_flight=2, backend="deterministic_mock",
                formal_execution_authorized=False, formal_authorization_id=None,
                development_generations=3, development_residents_per_island=1,
                development_births_per_island=1, development_t1_promotions_per_island=1,
            )
            registry_workspace = RootRegistry.load_workspace(ROOT, include_public=False)
            populations = {}
            for island in __import__("max_search.evolution", fromlist=["island_layout"]).island_layout(self.contract):
                root = registry_workspace.incumbent(island.lane)
                populations[island.island_id] = [FullTapeGenome(island.lane, root.root_id, root.digest).candidate_id]
            # Same semantic candidate in multiple same-lane islands is correctly rejected.
            with self.assertRaises(ExecutionError):
                ExecutionState.initial(manifest, self.contract, populations)

    def test_formal_mode_rejects_mock_backend_limits_and_missing_authorization(self):
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            development_manifest, initial = fake_development_manifest(self.contract, temporary)
            registry = ContextRegistry.create(formal_draft(), opponent_artifacts=artifacts())
            common = dict(
                run_id="formal_test", contract=self.contract,
                development_manifest=development_manifest, preflight_root=temporary,
                initial_population_path=initial, context_registry=registry,
                physical_workers=1, max_in_flight=2, formal_execution_authorized=True,
                development_generations=None, development_residents_per_island=None,
                development_births_per_island=None, development_t1_promotions_per_island=None,
            )
            with self.assertRaises(ExecutionError):
                ExecutionManifest.create(backend="deterministic_mock", formal_authorization_id="approved", **common)
            with self.assertRaises(ExecutionError):
                ExecutionManifest.create(backend="official", formal_authorization_id=None, **common)

    def test_formal_manifest_binds_matching_cpu_and_storage_calibration(self):
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            development_manifest, initial = fake_development_manifest(self.contract, temporary)
            registry = ContextRegistry.create(formal_draft(), opponent_artifacts=artifacts())
            source_digest = hashlib.sha256(canonical_json(
                development_manifest.payload["source_snapshot"]
            ).encode("utf-8")).hexdigest()
            calibration = _signed_artifact({
                "schema_version": 1,
                "kind": "maximum_search_worker_calibration",
                "contract_sha256": self.contract.sha256,
                "source_snapshot_sha256": source_digest,
                "execution_manifest_sha256": "c" * 64,
                "backend": "official",
                "physical_workers": 1,
                "logical_cpus": os.cpu_count() or 1,
                "candidate_games": 128,
                "elapsed_seconds": 10.0,
                "games_per_second": 6.4,
                "cpu_percent": 58.0,
                "receipt_rows": 128,
                "store_bytes": 128,
                "bytes_per_receipt": 1.0,
            }, "calibration_sha256")
            calibration_path = temporary / "calibration.json"
            atomic_json(calibration_path, calibration)
            manifest = ExecutionManifest.create(
                run_id="formal_calibrated", contract=self.contract,
                development_manifest=development_manifest, preflight_root=temporary,
                initial_population_path=initial, context_registry=registry,
                physical_workers=1, max_in_flight=2, backend="official",
                formal_execution_authorized=True, formal_authorization_id="approved_test",
                calibration_path=calibration_path,
            )
            self.assertTrue(manifest.formal)
            self.assertEqual(manifest.payload["resource_projection"]["cpu_percent"], 58.0)
            manifest_path = temporary / "execution_manifest.json"
            atomic_json(manifest_path, manifest.payload)
            loaded = ExecutionManifest.load(
                manifest_path, contract=self.contract,
                development_manifest=development_manifest, context_registry=registry,
            )
            self.assertEqual(loaded, manifest)
            tampered = copy.deepcopy(calibration)
            tampered["cpu_percent"] = 70.0
            unsigned = {key: value for key, value in tampered.items() if key != "calibration_sha256"}
            tampered["calibration_sha256"] = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
            atomic_json(calibration_path, tampered)
            with self.assertRaises(ExecutionError):
                ExecutionManifest.create(
                    run_id="formal_bad_cpu", contract=self.contract,
                    development_manifest=development_manifest, preflight_root=temporary,
                    initial_population_path=initial, context_registry=registry,
                    physical_workers=1, max_in_flight=2, backend="official",
                    formal_execution_authorized=True, formal_authorization_id="approved_test",
                    calibration_path=calibration_path,
                )


class ParallelAndStoreTests(unittest.TestCase):
    def test_candidate_gate_retains_opponent_seed_diagnostic_without_candidate_failure(self):
        summary = {
            "statuses": ["DONE", "DONE"], "calls": 719, "opponent_calls": 719,
            "exception": None, "opponent_exception": None,
            "timeout_calls": 0, "opponent_timeout_calls": 0,
            "overage_exhausted": False, "opponent_overage_exhausted": False,
            "action_issues": {"malformed": 0, "hand_alignment": 0, "seed_overcommit": 0, "market_overflow": 0},
            "opponent_action_issues": {"malformed": 0, "hand_alignment": 0, "seed_overcommit": 4, "market_overflow": 0},
            "max_market_orders": 10, "opponent_max_market_orders": 10,
        }
        self.assertTrue(_technical_pass(summary))
        summary["opponent_action_issues"]["malformed"] = 1
        self.assertFalse(_technical_pass(summary))

    def test_scalable_runner_selection_is_deterministic_and_preserves_extremes(self):
        rows = [
            FitnessVector(
                candidate_id=f"ft_v27_{index:064x}", lane=LANES[0],
                control_sha256="a" * 64, manifest_sha256="b" * 64,
                technical_pass=True, effective_change=True,
                net_wdl_transition=index % 7, w_to_l=index % 3,
                repeatable_family_seat_negative_tails=index % 5,
                cvar_01=float(-index), cvar_05=float(index % 11),
                worst_margin=float(-index % 13), mean_margin=float(index),
                mean_own_bank=float(200 - index), complexity=index % 19,
                novelty=float(index) / 200.0,
            )
            for index in range(200)
        ]
        first = select_survivors_scalable(rows, 50)
        second = select_survivors_scalable(list(reversed(rows)), 50)
        self.assertEqual([row.candidate_id for row in first], [row.candidate_id for row in second])
        self.assertEqual(len(first), 50)
        self.assertEqual(len({row.candidate_id for row in first}), 50)

    def test_runner_progress_math_closes_formal_30m_and_300m(self):
        contract = load_contract(CONTRACT_PATH)
        class Manifest:
            formal = True
            limits = {}
            payload = {"context_counts": {"t0": 6, "t1": 24, "holdout": 2}}
        progress = _expected_progress(contract, Manifest(), 1999)
        self.assertEqual(progress["raw_candidates"], 30_000_000)
        self.assertEqual(progress["t0_games"], 180_000_000)
        self.assertEqual(progress["t1_games"], 120_000_000)

    def test_spawn_pool_returns_process_receipts(self):
        registry = RootRegistry.load_workspace(ROOT, include_public=True)
        context = {
            "context_id": "ctx_test", "opponent_family": "other_incumbent", "seed": 1, "seat": 0,
        }
        tasks = [
            {
                "kind": "control", "backend": "deterministic_mock", "lane": LANES[index % 2],
                "contexts": [context for _ in range(32)], "tier": "control",
                "generation": -1, "island_id": "control",
            }
            for index in range(8)
        ]
        rows = list(_bounded_parallel(
            tasks, workspace=ROOT,
            root_manifest_sha256=registry.manifest()["manifest_sha256"],
            workers=min(2, os.cpu_count() or 1), max_in_flight=4,
        ))
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(row["worker_pid"] != os.getpid() for row in rows))
        self.assertLessEqual(len({row["worker_pid"] for row in rows}), min(2, os.cpu_count() or 1))

    def test_store_is_idempotent_and_rejects_different_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            with SearchStore(Path(temporary) / "store.sqlite", execution_manifest_sha256="d" * 64) as store:
                payload = {
                    "context_id": "ctx", "opponent_family": "family", "seed": 1, "seat": 0,
                    "margin": 1.0, "own_bank": 2.0, "technical_pass": True,
                    "behavior_sha256": "e" * 64, "action_digest": "f" * 64,
                    "failure": None, "worker_pid": 1,
                }
                row = {
                    "candidate_id": "candidate", "tier": "t0", "context_id": "ctx",
                    "lane": LANES[0], "generation": 0, "island_id": "island", "payload": payload,
                }
                store.put_receipt(row)
                store.put_receipt(row)
                tampered = copy.deepcopy(row)
                tampered["payload"]["margin"] = 99.0
                with self.assertRaises(Exception):
                    store.put_receipt(tampered)

    def test_generation_retention_preserves_adverse_rows_and_prunes_raw_receipts(self):
        class Manifest:
            sha256 = "9" * 64
            payload = {
                "retention_policy": load_contract(CONTRACT_PATH).payload["execution_boundary"]["storage_retention"]
            }

        def payload(context_id, margin, *, technical=True, crop_deaths=0):
            return {
                "context_id": context_id, "opponent_family": "family", "seed": 1, "seat": 0,
                "margin": float(margin), "own_bank": 2.0, "technical_pass": technical,
                "behavior_sha256": "e" * 64, "action_digest": "f" * 64,
                "failure": None if technical else {"worker_error": "failed"},
                "diagnostics": {
                    "animal_escapes": 0, "crop_deaths": crop_deaths,
                    "fresh_crop_deaths": 0, "shed_overflow_events": 0,
                    "shed_overflow_units": 0,
                },
                "terminal_inventory": {"marked_value": 0.0, "units": 0},
                "worker_pid": 1,
            }

        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            with SearchStore(temporary / "store.sqlite", execution_manifest_sha256=Manifest.sha256) as store:
                for context_id in ("positive", "negative", "economic", "invalid"):
                    store.put_control(LANES[0], payload(context_id, 10.0))
                candidates = (
                    ("positive", 11.0, True, 0),
                    ("negative", 9.0, True, 0),
                    ("economic", 11.0, True, 1),
                    ("invalid", 10.0, False, 0),
                )
                for context_id, margin, technical, crop_deaths in candidates:
                    store.put_receipt({
                        "candidate_id": f"candidate_{context_id}", "tier": "t0",
                        "context_id": context_id, "lane": LANES[0], "generation": 0,
                        "island_id": "island", "payload": payload(
                            context_id, margin, technical=technical, crop_deaths=crop_deaths,
                        ),
                    })
                store.commit()
                retention = _prepare_receipt_retention(
                    temporary, store=store, manifest=Manifest(), generation=0,
                )
                self.assertEqual(retention["receipt_counts"], {"t0": 4, "t1": 0})
                self.assertEqual(retention["adverse_rows"], 3)
                _ensure_generation_pruned(
                    temporary, store=store, manifest=Manifest(), generation=0,
                    retention=retention,
                )
                self.assertEqual(store.live_receipt_counts(), {"t0": 0, "t1": 0})
                self.assertEqual(store.counts()["t0"], 4)
                _ensure_generation_pruned(
                    temporary, store=store, manifest=Manifest(), generation=0,
                    retention=retention,
                )
                with self.assertRaises(Exception):
                    store.put_receipt({
                        "candidate_id": "late", "tier": "t0", "context_id": "positive",
                        "lane": LANES[0], "generation": 0, "island_id": "island",
                        "payload": payload("positive", 11.0),
                    })

    def test_completion_recovery_reconciles_store_and_candidate_index(self):
        registry = RootRegistry.load_workspace(ROOT, include_public=False)
        root = registry.incumbent(LANES[0])
        genome = FullTapeGenome(LANES[0], root.root_id, root.digest)
        with tempfile.TemporaryDirectory() as temporary:
            with CandidateIndex(Path(temporary) / "index.sqlite", manifest_sha256="1" * 64) as index, SearchStore(
                Path(temporary) / "store.sqlite", execution_manifest_sha256="2" * 64,
            ) as store:
                index.add(genome, 0, "island", expected_lane=LANES[0])
                index.commit()
                payload = {
                    "store_counts": store.counts(),
                    "raw_candidates_created": 1,
                    "next_population_ids": {"island": [genome.candidate_id]},
                }
                _verify_completion_storage(payload, store=store, index=index)
                payload["raw_candidates_created"] = 2
                with self.assertRaises(Exception):
                    _verify_completion_storage(payload, store=store, index=index)

    def test_resource_estimate_closes_full_candidate_game_budget(self):
        result = resource_estimate(
            contract=load_contract(CONTRACT_PATH), measured_games_per_second=100.0,
            measured_bytes_per_receipt=256.0, physical_workers=4,
        )
        self.assertEqual(result["projected_seconds"], 3_000_000.0)
        self.assertFalse(result["formal_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
