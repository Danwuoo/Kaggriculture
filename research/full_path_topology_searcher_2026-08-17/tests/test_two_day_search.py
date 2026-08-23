from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


LANE = Path(__file__).resolve().parents[1]
ROOT = LANE.parents[1]
if str(LANE) not in sys.path:
    sys.path.insert(0, str(LANE))

from max_search.contexts import ContextRegistry  # noqa: E402
from max_search.genome import FullTapeGenome, RootRegistry  # noqa: E402
from max_search.runner import SearchStore, _evaluate_candidates  # noqa: E402
from max_search.two_day import (  # noqa: E402
    CALIBRATION_CONTEXTS,
    CALIBRATION_CONTEXT_PROVENANCE,
    CALIBRATION_CONTEXTS_SHA256,
    DEFAULT_OLD_RUN,
    DEFAULT_STOP,
    RESIDENTS_PER_ISLAND,
    _build_contract,
    _choose_quotas,
    _completed_ledger_rows,
    _critical_compatibility,
    _identity,
    _old_authority,
    _prototype_payload,
    _recover,
    _runtime_dependency_snapshot,
    _select_seed_population,
    _signed,
    _validate_calibration,
    _verify_runtime_dependencies,
    calibrate,
    copied_old_databases,
    load_two_day_contract,
    ManifestView,
    prepare,
    TwoDayContract,
)


class TwoDayQuotaTests(unittest.TestCase):
    def test_calibration_is_closed_and_rejects_cpu_or_worker_tamper(self):
        elapsed = 100.0
        games = 176
        payload = _signed({
            "schema_version": 1, "kind": "two_day_worker_calibration", "created_at": "now",
            "old_execution_manifest_sha256": "a" * 64,
            "critical_compatibility_sha256": "b" * 64,
            "source_snapshot_sha256": "c" * 64,
            "physical_workers": 14, "active_in_flight": 11,
            "throttle_mode": "bounded_active_in_flight", "logical_cpus": 32,
            "candidate_batches": 22, "candidate_games": games,
            "technical_contexts": list(CALIBRATION_CONTEXTS),
            "technical_contexts_sha256": CALIBRATION_CONTEXTS_SHA256,
            "technical_context_provenance": CALIBRATION_CONTEXT_PROVENANCE,
            "candidate_lane_counts": {
                "v27_current_meta": 11, "boatlee_v16_rc2_market_relay": 11,
            },
            "contexts_per_batch": 8,
            "elapsed_seconds": elapsed, "games_per_second": games / elapsed,
            "whole_interval_cpu_percent": 57.0,
            "worker_pids": list(range(100, 111)), "worker_processes_observed": 11,
            "technical_failures": 0, "bytes_per_receipt": 3000.0,
            "free_bytes_before": 100 * 1024**3, "free_bytes_after": 99 * 1024**3,
            "thermal_before": {"available": False}, "thermal_after": {"available": False},
            "accepted": True,
            "acceptance": {"minimum_candidate_games": 128, "cpu_percent": [50, 65],
                           "minimum_free_bytes": 50 * 1024**3, "zero_technical_failures": True},
        }, "calibration_sha256")
        _validate_calibration(payload)
        tampered = dict(payload)
        tampered["whole_interval_cpu_percent"] = 70.0
        tampered.pop("calibration_sha256")
        with self.assertRaisesRegex(Exception, "CPU"):
            _validate_calibration(_signed(tampered, "calibration_sha256"))
        tampered = dict(payload)
        tampered["candidate_lane_counts"] = {
            "v27_current_meta": 16, "boatlee_v16_rc2_market_relay": 6,
        }
        tampered.pop("calibration_sha256")
        with self.assertRaisesRegex(Exception, "small|close"):
            _validate_calibration(_signed(tampered, "calibration_sha256"))

    def test_calibration_and_prepare_reject_stopped_run_output_paths(self):
        with self.assertRaisesRegex(Exception, "immutable stopped run"):
            calibrate(
                old_run=DEFAULT_OLD_RUN, stop_path=DEFAULT_STOP,
                output=DEFAULT_OLD_RUN / "execution_manifest.json",
                physical_workers=14, active_in_flight=11,
                candidate_batches=8, require_gates=False,
            )
        with self.assertRaisesRegex(Exception, "immutable stopped run"):
            prepare(
                old_run=DEFAULT_OLD_RUN, stop_path=DEFAULT_STOP,
                calibration_path=Path("not-read.json"),
                output_root=DEFAULT_OLD_RUN / "forbidden_new_run",
                run_id="forbidden", authorization_id="test",
            )

    def test_official_runtime_dependency_closure_and_drift_rejection(self):
        dependencies = _runtime_dependency_snapshot()
        self.assertEqual(len(dependencies), 4)
        self.assertEqual({Path(row["path"]).name for row in dependencies}, {
            "engine_runner.py", "protocol.py", "harness.py", "prechange_manifest.json",
        })
        _verify_runtime_dependencies(dependencies)
        drifted = copy.deepcopy(dependencies)
        drifted[0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(Exception, "runtime dependency drift"):
            _verify_runtime_dependencies(drifted)

    def test_calibration_contexts_are_disjoint_from_formal_and_holdout(self):
        registry = ContextRegistry.load(DEFAULT_OLD_RUN / "context_registry.json", require_mode="formal")
        formal = {
            int(row["seed"])
            for stage in ("t0", "t1", "holdout")
            for row in registry.contexts(stage)
        }
        technical = {int(row["seed"]) for row in CALIBRATION_CONTEXTS}
        self.assertFalse(formal.intersection(technical))
        self.assertEqual(len(technical), 4)

    def test_calibrated_quota_is_exact_multi_generation_and_two_day_bounded(self):
        quota = _choose_quotas(1.3438633707555117, 196272)
        self.assertEqual(quota["execution_generations"], 16)
        self.assertGreater(quota["births_per_island_per_execution_generation"], 0)
        self.assertGreater(quota["promotions_per_island_per_execution_generation"], 0)
        self.assertLess(
            quota["promotions_per_island_per_execution_generation"],
            quota["births_per_island_per_execution_generation"],
        )
        self.assertGreaterEqual(quota["projected_search_hours"], 44.0)
        self.assertLessEqual(quota["projected_search_hours"], 45.5)
        self.assertGreater(quota["total_completed_t0_t1_game_keys"], 400000)
        self.assertEqual(
            quota["newly_executed_t0_t1_games"],
            quota["newly_executed_t0_games"] + quota["newly_executed_t1_games"],
        )

    def test_signed_contract_closes_reused_and_new_counters(self):
        calibration = {"games_per_second": 1.3438633707555117, "active_in_flight": 11}
        compatibility = {"compatibility_sha256": "a" * 64}
        ledger = {
            "completed_game_keys": 196272,
            "counts": {"gen0_reconstructed_t0": 98304, "gen0_reconstructed_t1": 65520, "gen1_live_t0": 32448},
        }
        payload = _build_contract(calibration=calibration, compatibility=compatibility, ledger_summary=ledger)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "contract.json"
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            contract = load_two_day_contract(path)
        self.assertEqual(contract.population, 32 * RESIDENTS_PER_ISLAND)
        self.assertEqual(contract.t1_promotion_quota(0), 0)
        self.assertEqual(sum(contract.island_birth_quotas(1)), contract.birth_quota(1))
        self.assertFalse(contract.payload["pool_lanes"])
        self.assertTrue(contract.payload["execution_boundary"]["holdout_frozen_untouched"])


@unittest.skipUnless(DEFAULT_OLD_RUN.is_dir(), "stopped formal run is not present")
class StoppedRunImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_manifest, cls.old_checkpoint, cls.development_manifest, _ = _old_authority(
            DEFAULT_OLD_RUN, DEFAULT_STOP,
        )
        cls.contexts = ContextRegistry.load(DEFAULT_OLD_RUN / "context_registry.json", require_mode="formal")
        cls.registry = RootRegistry.load_workspace(ROOT, include_public=True)
        cls.compatibility = _critical_compatibility(
            old_run=DEFAULT_OLD_RUN, raw_manifest=cls.raw_manifest,
            development_manifest=cls.development_manifest,
            context_registry=cls.contexts, registry=cls.registry,
        )

    def test_completed_game_ledger_reconstructs_exact_old_counts_without_mutation(self):
        before = [_identity(path) for path in (
            DEFAULT_OLD_RUN / "execution_store.sqlite",
            DEFAULT_OLD_RUN / "execution_candidate_index.sqlite",
            DEFAULT_OLD_RUN / "execution_candidate_index.sqlite-wal",
            DEFAULT_OLD_RUN / "execution_candidate_index.sqlite-shm",
        )]
        with copied_old_databases(DEFAULT_OLD_RUN) as (store, index, _identities):
            rows = list(_completed_ledger_rows(
                store=store, index=index, context_registry=self.contexts,
                compatibility_sha256=self.compatibility["compatibility_sha256"],
            ))
        after = [_identity(Path(row["path"])) for row in before]
        self.assertEqual(before, after)
        self.assertEqual(len(rows), 196272)
        self.assertEqual(len({row["game_key_sha256"] for row in rows}), len(rows))
        self.assertEqual(Counter(row["source"] for row in rows), {
            "gen0_reconstructed_pruned": 163824,
            "gen1_live_receipt": 32448,
        })
        self.assertEqual(Counter(row["tier"] for row in rows), {"t0": 130752, "t1": 65520})

    def test_reuse_compatibility_rejects_drifted_opponent_bytes(self):
        drifted = copy.deepcopy(self.contexts.payload)
        family = next(iter(drifted["opponent_artifacts"]))
        lane = next(iter(drifted["opponent_artifacts"][family]["by_lane"]))
        drifted["opponent_artifacts"][family]["by_lane"][lane]["sha256"] = "0" * 64
        with self.assertRaisesRegex(Exception, "opponent artifact drift"):
            _critical_compatibility(
                old_run=DEFAULT_OLD_RUN, raw_manifest=self.raw_manifest,
                development_manifest=self.development_manifest,
                context_registry=ContextRegistry(drifted, self.contexts.sha256), registry=self.registry,
            )

    def test_seed_population_uses_both_sources_in_every_lane_owned_island(self):
        with copied_old_databases(DEFAULT_OLD_RUN) as (store, index, _identities):
            populations, seeds, summary = _select_seed_population(
                store=store, index=index, old_checkpoint=self.old_checkpoint,
                development_manifest=self.development_manifest, registry=self.registry,
                context_registry=self.contexts,
            )
        self.assertEqual(len(populations), 32)
        self.assertTrue(all(len(values) == RESIDENTS_PER_ISLAND for values in populations.values()))
        self.assertEqual(len({candidate_id for values in populations.values() for candidate_id in values}), 2048)
        self.assertEqual(summary["source_counts"], {"gen0_frontier": 1856, "gen1_live_t0": 192})
        self.assertEqual(len(summary["gen1_islands_seeded"]), 12)
        for island_id, candidate_ids in populations.items():
            sources = Counter(seeds[candidate_id]["source"] for candidate_id in candidate_ids)
            expected = (
                {"gen0_frontier": 48, "gen1_live_t0": 16}
                if island_id in summary["gen1_islands_seeded"]
                else {"gen0_frontier": 64}
            )
            self.assertEqual(sources, expected)
            self.assertTrue(all(seeds[candidate_id]["island_id"] == island_id for candidate_id in candidate_ids))


class TwoDayRecoveryIntegrationTests(unittest.TestCase):
    @staticmethod
    def _candidate_id(lane: str, ordinal: int) -> str:
        token = "v27" if lane == "v27_current_meta" else "boatlee"
        return f"ft_{token}_{ordinal:064x}"

    def test_partial_receipts_resume_without_reexecuting_completed_tuple(self):
        registry = RootRegistry.load_workspace(ROOT, include_public=False)
        root = registry.incumbent("v27_current_meta")
        genome = FullTapeGenome("v27_current_meta", root.root_id, root.digest)
        contexts = [
            {"context_id": f"ctx_{ordinal}", "opponent_family": "test", "seed": ordinal, "seat": ordinal % 2}
            for ordinal in range(3)
        ]

        class Index:
            def catalog(self, candidate_ids):
                self.last_ids = list(candidate_ids)
                return {genome.candidate_id: genome.to_dict()}

        class Evaluator:
            def __init__(self):
                self.calls = []

            def run(self, tasks):
                for task in tasks:
                    self.calls.append([row["context_id"] for row in task["contexts"]])
                    yield {
                        "worker_pid": 123, "candidate_id": genome.candidate_id,
                        "lane": genome.lane, "island_id": "island",
                        "results": [{"context_id": row["context_id"]} for row in task["contexts"]],
                    }

        class Manifest:
            payload = {"backend": "official"}

        with tempfile.TemporaryDirectory() as temporary:
            with SearchStore(Path(temporary) / "store.sqlite", execution_manifest_sha256="1" * 64) as store:
                store.put_receipt({
                    "candidate_id": genome.candidate_id, "tier": "t0", "context_id": "ctx_0",
                    "lane": genome.lane, "generation": 1, "island_id": "island",
                    "payload": {"context_id": "ctx_0"},
                })
                store.commit()
                evaluator = Evaluator()
                pids = _evaluate_candidates(
                    store, evaluator=evaluator, manifest=Manifest(), index=Index(),
                    candidates_by_island={"island": [genome.candidate_id]},
                    generation=1, tier="t0", contexts=contexts,
                )
                self.assertEqual(pids, {123})
                self.assertEqual(evaluator.calls, [["ctx_1", "ctx_2"]])
                self.assertEqual(store.live_receipt_counts(), {"t0": 3, "t1": 0})
                self.assertEqual(_evaluate_candidates(
                    store, evaluator=evaluator, manifest=Manifest(), index=Index(),
                    candidates_by_island={"island": [genome.candidate_id]},
                    generation=1, tier="t0", contexts=contexts,
                ), set())
                self.assertEqual(evaluator.calls, [["ctx_1", "ctx_2"]])
                self.assertEqual(store.live_receipt_counts(), {"t0": 3, "t1": 0})

    def test_prepared_completion_recovers_once_and_closes_exact_counters(self):
        contract = TwoDayContract(_prototype_payload(), "c" * 64)
        context_path = DEFAULT_OLD_RUN / "context_registry.json"
        manifest = ManifestView({
            "context_registry": {"path": str(context_path)},
            "imported_seed_t0_fitness": 2048,
            "imported_seed_combined_fitness": 1856,
            "baseline_imported_candidates": 31384,
            "retention_policy": {},
        }, "m" * 64)
        populations = {}
        ordinal = 1
        from max_search.evolution import island_layout
        for island in island_layout(contract):
            populations[island.island_id] = [
                self._candidate_id(island.lane, ordinal + offset)
                for offset in range(RESIDENTS_PER_ISLAND)
            ]
            ordinal += RESIDENTS_PER_ISLAND
        expected = {"new_candidates": 1280, "promotions": 192, "new_t0": 7680, "new_t1": 4608}

        class Store:
            def __init__(self):
                self.summary_calls = []
                self.commits = 0

            def counts(self):
                return {"controls": 60, "t0": 7680, "t1": 4608,
                        "fitness_t0": 3328, "fitness_combined": 2048}

            def put_generation_summary(self, generation, payload):
                self.summary_calls.append((generation, payload["artifact_sha256"]))

            def commit(self):
                self.commits += 1

        class Index:
            def count(self):
                return 31384 + 1280

            def generation_count(self, generation):
                return 1280 if generation == 1 else 0

        completion = _signed({
            "schema_version": 1, "kind": "two_day_generation_complete",
            "manifest_sha256": manifest.sha256, "generation": 1,
            "candidate_count": 1280, "t1_promotions": 192,
            "expected_progress": expected, "store_counts": Store().counts(),
            "candidate_index_count": 31384 + 1280, "worker_pids": [1, 2],
            "elapsed_seconds": 10.0, "games_per_second": 1228.8,
            "birth_artifact_sha256": "b" * 64, "next_population_ids": populations,
            "receipt_retention": {"receipt_counts": {"t0": 7680, "t1": 4608}},
            "holdout_executed": False,
        }, "artifact_sha256")
        checkpoint = _signed({
            "schema_version": 1, "kind": "two_day_execution_checkpoint", "run_id": "test",
            "manifest_sha256": manifest.sha256, "status": "prepared",
            "last_completed_generation": 0, "next_generation": 1,
            "population_ids": populations, "baseline_imported_candidates": 31384,
            "new_candidates_created": 0, "reused_completed_game_keys": 196272,
            "new_t0_games_executed": 0, "new_t1_games_executed": 0,
            "newly_executed_games": 0, "total_completed_game_keys": 196272,
            "holdout_executed": False,
        }, "checkpoint_sha256")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepared = root / "two_day_generation_0001_prepared.json"
            prepared.write_text(json.dumps(completion), encoding="utf-8")
            store, index = Store(), Index()
            with patch("max_search.two_day._ensure_generation_pruned") as prune:
                recovered = _recover(
                    run_root=root, checkpoint=checkpoint, manifest=manifest,
                    contract=contract, store=store, index=index,
                )
                self.assertEqual(prune.call_count, 1)
                self.assertFalse(prepared.exists())
                self.assertTrue((root / "two_day_generation_0001_summary.json").is_file())
                self.assertEqual(recovered["next_generation"], 2)
                self.assertEqual(recovered["new_candidates_created"], 1280)
                self.assertEqual(recovered["new_t0_games_executed"], 7680)
                self.assertEqual(recovered["new_t1_games_executed"], 4608)
                self.assertEqual(recovered["newly_executed_games"], 12288)
                self.assertEqual(recovered["total_completed_game_keys"], 208560)
                self.assertEqual(store.commits, 1)
                self.assertEqual(len(store.summary_calls), 1)

                rerun = _recover(
                    run_root=root, checkpoint=recovered, manifest=manifest,
                    contract=contract, store=store, index=index,
                )
                self.assertEqual(rerun, recovered)
                self.assertEqual(prune.call_count, 1)
                self.assertEqual(store.commits, 1)
                self.assertEqual(len(store.summary_calls), 1)

        invalid = dict(completion)
        invalid.pop("artifact_sha256")
        invalid["candidate_count"] = 1279
        invalid = _signed(invalid, "artifact_sha256")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepared = root / "two_day_generation_0001_prepared.json"
            prepared.write_text(json.dumps(invalid), encoding="utf-8")
            with patch("max_search.two_day._ensure_generation_pruned") as prune:
                with self.assertRaisesRegex(Exception, "candidate count"):
                    _recover(
                        run_root=root, checkpoint=checkpoint, manifest=manifest,
                        contract=contract, store=Store(), index=Index(),
                    )
                prune.assert_not_called()
                self.assertTrue(prepared.is_file())


if __name__ == "__main__":
    unittest.main()
