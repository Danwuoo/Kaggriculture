"""Regression and property gates for the Async V3 contract.

These tests deliberately use only the technical seed.  Fixture ranking data is
read as frozen evidence; it is never treated as a runnable efficacy screen.
"""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from compiler import compile_genome, compile_fixture_anchors, incumbent_actions, phenotype_report
from evolution import crossover, declared_market_surface, initial_lane_roots, mutate_one, refill_population
from fixture import load_fixture, verify_frozen_evidence
from model import (
    AsyncGenome,
    ConstantGene,
    GuardGene,
    MarketEditGene,
    RouteBlockGene,
    LANES,
)
from ranking import rank_frontiers
from runtime import apply_candidate_action, atomic_plant_projection
from scheduler import MAX_WORKERS, SchedulerFailure, atomic_json, development_audit, load_resume, read_status
from materialize import isolated_import, materialize_finalist, static_audit
from cli import build_parser
from formal_run import _score_rows, formal_status, preflight, run_formal


HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "e1b_regression_fixtures.json"


def order(opcode: str) -> tuple[object, ...]:
    return {
        "HIRE": ("HIRE",),
        "BUY_LAND": ("BUY_LAND",),
        "BUY_ANIMAL": ("BUY_ANIMAL", "COW", 1),
        "BUY_SEED": ("BUY_SEED", "MELON", 2),
        "BUY_PRODUCT": ("BUY_PRODUCT", "WHEAT", 3),
        "SELL": ("SELL", "WOOL", 4),
    }[opcode]


class FixtureGateTests(unittest.TestCase):
    def test_fixture_schema_and_frozen_evidence_are_valid(self) -> None:
        report = verify_frozen_evidence(FIXTURE)
        self.assertTrue(report["pass"], report)
        self.assertEqual([], report["errors"])
        self.assertFalse(load_fixture(FIXTURE)["authority"]["formal_fresh_seeds_executed"])


class CanonicalGenomeTests(unittest.TestCase):
    def test_ordering_and_lineage_do_not_change_identity(self) -> None:
        first = MarketEditGene(3, 0, "insert", 0, order=("HIRE",))
        second = MarketEditGene(3, 1, "insert", 1, order=("BUY_LAND",))
        left = AsyncGenome("v27_current_meta", market_edits=(second, first), parent_id="parent-a")
        right = AsyncGenome("v27_current_meta", market_edits=(first, second), parent_id="parent-b", mutation_id="different")
        self.assertEqual(left.genome_id, right.genome_id)
        self.assertNotEqual(left.lineage_payload(), right.lineage_payload())

    def test_lane_is_part_of_the_identity(self) -> None:
        edit = MarketEditGene(3, 0, "insert", 0, order=("HIRE",))
        self.assertNotEqual(
            AsyncGenome("v27_current_meta", market_edits=(edit,)).genome_id,
            AsyncGenome("boatlee_v16_rc2_market_relay", market_edits=(edit,)).genome_id,
        )

    def test_all_market_opcodes_and_operations_are_representable(self) -> None:
        for opcode in ("HIRE", "BUY_LAND", "BUY_ANIMAL", "BUY_SEED", "BUY_PRODUCT", "SELL"):
            MarketEditGene(1, 0, "insert", 0, order=order(opcode))
        for operation in ("remove", "replace", "move", "quantity"):
            MarketEditGene(1, 0, operation, 0, order=("SELL", "WOOL", 2), target_index=0)

    def test_invalid_route_range_and_private_guard_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RouteBlockGene("a" * 64, 0, 3, ("market",), "too-short")
        with self.assertRaises(ValueError):
            GuardGene("opponent_identity", "WOOL", 1)


class CompilerRuntimeTests(unittest.TestCase):
    def test_ordered_edits_have_complete_dispositions_and_cap(self) -> None:
        lane = "v27_current_meta"
        genome = AsyncGenome(
            lane,
            market_edits=(
                MarketEditGene(0, 0, "insert", 0, order=("BUY_PRODUCT", "WHEAT", 11)),
                MarketEditGene(0, 1, "quantity", 0, order=("BUY_PRODUCT", "WHEAT", 9), target_index=0),
                MarketEditGene(0, 2, "move", 9, order=("BUY_PRODUCT", "WHEAT", 9), target_index=0),
                MarketEditGene(0, 3, "replace", 0, order=("HIRE",), target_index=0),
                MarketEditGene(0, 4, "remove", 0, order=("HIRE",), target_index=0),
            ),
        )
        candidate = compile_genome(lane, genome)
        self.assertTrue(candidate.accepted, candidate.rejection)
        self.assertTrue(all(len(row["market"]) <= 10 for row in candidate.patches))
        self.assertTrue(candidate.displaced_actions)
        self.assertTrue(all(row["disposition"] in {"retained", "reassigned", "reclaimed"} for row in candidate.displaced_actions))

    def test_fixture_anchors_reconstruct_effective_market_patches(self) -> None:
        rows = compile_fixture_anchors(FIXTURE)
        self.assertEqual(4, len(rows))
        for row in rows:
            self.assertTrue(row.accepted, row.rejection)
            self.assertTrue(row.fixture_match)

    def test_live_constant_phenotypes_are_distinct_or_explicitly_inactive(self) -> None:
        anchors = compile_fixture_anchors(FIXTURE)
        for lane in LANES:
            anchor = next(row for row in anchors if row.lane == lane)
            prefix = "v27" if lane == "v27_current_meta" else "boatlee"
            active = compile_genome(lane, AsyncGenome(lane, route_blocks=anchor.genome.route_blocks, constants=(ConstantGene(f"{prefix}_market_order_cap", 4),)))
            inactive = compile_genome(lane, AsyncGenome(lane, constants=(ConstantGene(f"{prefix}_market_order_cap", 10),)))
            report = phenotype_report((anchor, active, inactive))
            self.assertIn(active.candidate_id, report["active_constants"])
            self.assertIn(inactive.candidate_id, report["inactive_constants"])

    def test_public_guard_and_missing_private_state_fall_back(self) -> None:
        lane = "v27_current_meta"
        genome = AsyncGenome(
            lane,
            market_edits=(MarketEditGene(0, 0, "insert", 0, order=("SELL", "WOOL", 2), guard=GuardGene("min_price", "WOOL", 100)),),
        )
        candidate = compile_genome(lane, genome)
        base = {"farmer": ["PASS"], "hands": [], "market": []}
        rejected = apply_candidate_action(candidate, {"step": 0, "player": 0, "farms": [{"hands": []}], "market": {"prices": {"WOOL": 1}, "inventory": {"WOOL": 1}}}, base)
        self.assertEqual(base, rejected["action"])
        fallback = apply_candidate_action(candidate, {"step": 0, "player": 0, "farms": [{"hands": []}]}, base)
        self.assertEqual(base, fallback["action"])

    def test_atomic_seed_projection_is_local_and_preserves_missing_private(self) -> None:
        action = {"farmer": ["PLANT", "MELON"], "hands": [["PLANT", "MELON"]], "market": []}
        self.assertEqual(action, atomic_plant_projection({}, action))
        guarded = atomic_plant_projection({"private": {"seeds": {"MELON": 1}}}, action)
        self.assertEqual(["PASS"], guarded["farmer"])
        self.assertEqual(["PASS"], guarded["hands"][0])

    def test_live_public_constant_abstains_when_public_price_is_missing(self) -> None:
        lane = "v27_current_meta"
        candidate = compile_genome(lane, AsyncGenome(lane, constants=(ConstantGene("v27_guard_min_price", 25),)))
        base = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WOOL", 1]]}
        result = apply_candidate_action(candidate, {"step": 1, "player": 0, "farms": [{"hands": []}], "private": {}}, base)
        self.assertEqual(base, result["action"])
        self.assertEqual("missing_public_state_for_live_constant", result["fallback"])


class EvolutionRankingTests(unittest.TestCase):
    def test_mutation_changes_one_causal_atom_and_crossover_keeps_dependencies(self) -> None:
        parent = AsyncGenome("v27_current_meta", market_edits=(MarketEditGene(0, 0, "insert", 0, order=("HIRE",)),))
        child, atom = mutate_one(parent, seed=7)
        self.assertEqual(1, atom["changed_atoms"])
        dependent = AsyncGenome("v27_current_meta", route_blocks=(RouteBlockGene("a" * 64, 0, 7, ("market",), "bundle"),), market_edits=(MarketEditGene(0, 0, "insert", 0, order=("HIRE",), dependency="bundle"),))
        crossed = crossover(dependent, parent, seed=2)
        self.assertTrue(all(edit.dependency in {None, "bundle"} for edit in crossed.market_edits))

    def test_refill_saturates_instead_of_looping(self) -> None:
        parent = AsyncGenome("v27_current_meta")
        rows, saturation = refill_population((parent,), target=99, seed=1, max_attempts=3)
        self.assertLessEqual(len(rows), 99)
        self.assertTrue(saturation["saturated"])

    def test_two_frontiers_are_lane_isolated_and_fixture_semantics_hold(self) -> None:
        fixture = load_fixture(FIXTURE)
        result = rank_frontiers(fixture)
        boatlee = result["lanes"]["boatlee_v16_rc2_market_relay"]
        v27 = result["lanes"]["v27_current_meta"]
        self.assertIn("ac_5f4a369973330bf53370f3f8", boatlee["robust"])
        self.assertEqual("ac_5f4a369973330bf53370f3f8", boatlee["causal_representative"])
        self.assertNotIn("ac_b59943fc80ea1fa0ff69ce89", v27["robust"])
        self.assertIn("ac_b59943fc80ea1fa0ff69ce89", v27["high_upside"])

    def test_declared_market_surface_reaches_every_operation_opcode_and_guard(self) -> None:
        rows = declared_market_surface(AsyncGenome("v27_current_meta"))
        operations = {edit.operation for genome in rows for edit in genome.market_edits}
        opcodes = {str(edit.order[0]) for genome in rows for edit in genome.market_edits if edit.order}
        self.assertEqual({"insert", "remove", "replace", "move", "quantity"}, operations)
        self.assertEqual({"HIRE", "BUY_LAND", "BUY_ANIMAL", "BUY_SEED", "BUY_PRODUCT", "SELL"}, opcodes)
        self.assertTrue(any(edit.guard is not None for genome in rows for edit in genome.market_edits))


class SchedulerTests(unittest.TestCase):
    def test_worker_cap_resume_hash_and_read_only_status(self) -> None:
        self.assertEqual(15, MAX_WORKERS)
        with tempfile.TemporaryDirectory(prefix="async-v3-") as temp:
            root = Path(temp) / "run"
            self.assertFalse(root.exists())
            self.assertFalse(read_status(root)["exists"])
            self.assertFalse(root.exists())
            root.mkdir()
            atomic_json(root / "manifest.json", {"manifest": "a", "engine": "e", "control": "c", "fixture": "f", "registry": "r", "jobs": "j"})
            self.assertIsNotNone(load_resume(root, {"manifest": "a", "engine": "e", "control": "c", "fixture": "f", "registry": "r", "jobs": "j"}))
            with self.assertRaises(SchedulerFailure):
                load_resume(root, {"manifest": "b", "engine": "e", "control": "c", "fixture": "f", "registry": "r", "jobs": "j"})

    def test_spawn_audit_covers_parallel_and_failure_modes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="async-v3-scheduler-") as temp:
            result = development_audit(Path(temp) / "audit")
        self.assertTrue(result["pass"], result)
        self.assertTrue(result["canonical_equal"])
        self.assertTrue(result["maximum_enforced"])
        self.assertTrue(result["failures"]["corrupt"]["preserved"])


class MaterializationTests(unittest.TestCase):
    def test_only_finalist_materialization_is_self_contained_and_importable(self) -> None:
        candidate = compile_fixture_anchors(FIXTURE)[0]
        with tempfile.TemporaryDirectory(prefix="async-v3-materialize-") as temp:
            output = Path(temp) / "main.py"
            artifact = materialize_finalist(candidate, output)
            audit = static_audit(output)
            imported = isolated_import(output)
        self.assertTrue(artifact["finalist_only"])
        self.assertTrue(audit["pass"], audit)
        self.assertTrue(imported["callable_agent"])


class FormalOrchestrationTests(unittest.TestCase):
    def test_cli_exposes_preflight_status_search_and_resume_surface(self) -> None:
        parser = build_parser()
        for command in ("preflight", "status", "run", "search"):
            self.assertIn(command, parser._subparsers._group_actions[0].choices)
        args = parser.parse_args(["run", "--output-root", "C:/tmp/async-v3", "--workers", "1", "--dry-run", "--resume"])
        self.assertTrue(args.dry_run)
        self.assertTrue(args.resume)

    def test_formal_dry_pipeline_invokes_evaluator_and_scores_only_complete_contexts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="async-v3-formal-") as temp:
            root = Path(temp) / "run"
            manifest = preflight(root, proposal_seed=17, population=6, generations=1, workers=1)
            self.assertTrue(all(manifest["population_report"]["fixture_root_presence"].values()))
            missing = _score_rows(manifest, [])
            self.assertTrue(all(row["score"] is None for row in missing))
            result = run_formal(root, workers=1, dry_run=True)
            self.assertTrue(result["summary"]["complete"], result["summary"])
            self.assertTrue(all(row["score"] is not None for row in result["summary"]["scores"]))
            self.assertEqual(len(result["summary"]["scores"]) * 8, result["summary"]["candidate_contexts"])
            self.assertEqual([], result["summary"]["seed_accounting"]["executed_formal_seeds"])
            shard = next((root / "dry_mock" / "candidates" / "shards").glob("*.json"))
            payload = json.loads(shard.read_text(encoding="utf-8"))
            self.assertTrue(payload["evaluator_invoked"])
            self.assertEqual("development_mock", payload["evaluation_kind"])

    def test_dry_serial_parallel_scores_match_and_resume_is_hash_validated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="async-v3-formal-parallel-") as temp:
            base = Path(temp)
            serial_root, parallel_root = base / "serial", base / "parallel"
            preflight(serial_root, proposal_seed=23, population=6, generations=1, workers=1)
            serial = run_formal(serial_root, workers=1, dry_run=True)
            preflight(parallel_root, proposal_seed=23, population=6, generations=1, workers=4)
            parallel = run_formal(parallel_root, workers=4, dry_run=True)
            serial_scores = [{key: value for key, value in row.items() if key not in {"candidate_id"}} for row in serial["summary"]["scores"]]
            parallel_scores = [{key: value for key, value in row.items() if key not in {"candidate_id"}} for row in parallel["summary"]["scores"]]
            self.assertEqual(serial_scores, parallel_scores)
            resumed = preflight(serial_root, proposal_seed=23, population=6, generations=1, workers=1, resume=True)
            self.assertEqual(serial["manifest"]["manifest"], resumed["manifest"])
            with self.assertRaises(SchedulerFailure):
                preflight(serial_root, proposal_seed=23, population=7, generations=1, workers=1, resume=True)

    def test_status_is_read_only_and_exact_execution_is_explicitly_blocked_in_development(self) -> None:
        with tempfile.TemporaryDirectory(prefix="async-v3-formal-status-") as temp:
            root = Path(temp) / "absent"
            self.assertFalse(formal_status(root)["exists"])
            self.assertFalse(root.exists())
            preflight(root, proposal_seed=31, population=6, generations=1, workers=1)
            with self.assertRaises(PermissionError):
                run_formal(root, workers=1, dry_run=False, execute_retained_e1c=False)

    def test_scored_frontier_never_promotes_negative_downside_from_win_delta(self) -> None:
        rows = {
            "epsilon": 1.0,
            "lanes": {
                "v27_current_meta": [{"candidate_id": "negative", "score": 10.0, "metrics": {"technical_pass": True, "all_contexts_complete": True, "action_changed_contexts": 2, "opponent_nonnegative_families": 2, "worst_paired_margin": -1.0, "mean_paired_margin": 10.0, "actual_win_delta": 4, "complexity": 1}}],
                "boatlee_v16_rc2_market_relay": [],
            },
        }
        self.assertNotIn("negative", rank_frontiers(rows)["lanes"]["v27_current_meta"]["robust"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
