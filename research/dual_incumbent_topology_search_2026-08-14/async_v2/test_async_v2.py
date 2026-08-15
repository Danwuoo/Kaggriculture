from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from compiler import compile_genome, phenotype_id, semantic_noop
from evaluator import TECHNICAL_SEED, engine_fingerprint, run_control
from evolution import deduplicate_scores, genome_island, initial_genomes, mutate, pareto, ranking_key
from library import file_sha256, load_library
from model import AsyncGenome, ConstantGene, MarketPolicyGene, RouteBlockGene
from runtime import RUNTIME_SOURCE
from search import MAX_WORKERS, _job, _manifest_body, status
from seed_accounting import classify_evaluation_seeds
from topology_space import observed_behavior_summary
import formal_run
import search as search_module


HERE = Path(__file__).resolve().parent
LIBRARY_PATH = HERE / "artifacts" / "motif_library.json"


class CanonicalGenomeTests(unittest.TestCase):
    def test_multi_gene_genome_is_canonical(self) -> None:
        left = MarketPolicyGene("MILK", 10000, 10000, 7500)
        right = MarketPolicyGene("FERTILIZER", 7500, 10500, 5000)
        genome = AsyncGenome(
            market_policy=(left, right),
            constants=(ConstantGene("weed_replay_steps", 4), ConstantGene("demand_alpha_milli", 500)),
        )
        reverse = AsyncGenome(
            market_policy=(right, left),
            constants=(ConstantGene("demand_alpha_milli", 500), ConstantGene("weed_replay_steps", 4)),
        )
        self.assertEqual(genome.genome_id, reverse.genome_id)
        self.assertEqual(4, len(genome.market_policy) + len(genome.constants))

    def test_overlapping_same_channel_blocks_are_rejected(self) -> None:
        first = RouteBlockGene("a" * 64, 100, 107, ("unit",), "m1")
        second = RouteBlockGene("b" * 64, 104, 111, ("unit",), "m2")
        with self.assertRaises(ValueError):
            AsyncGenome(route_blocks=(first, second))

    def test_overlap_is_allowed_on_disjoint_channels(self) -> None:
        first = RouteBlockGene("a" * 64, 100, 107, ("unit",), "m1")
        second = RouteBlockGene("b" * 64, 104, 111, ("market",), "m2")
        self.assertEqual(2, len(AsyncGenome(route_blocks=(first, second)).route_blocks))

    def test_eight_windows_are_allowed_but_nine_are_rejected(self) -> None:
        rows = tuple(
            RouteBlockGene(str(index) * 64, index * 10, index * 10 + 7, ("unit",), f"m{index}")
            for index in range(9)
        )
        self.assertEqual(8, len(AsyncGenome(route_blocks=rows[:8]).route_blocks))
        with self.assertRaises(ValueError):
            AsyncGenome(route_blocks=rows)


class LibraryAndEvolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.library = load_library(LIBRARY_PATH)

    def test_library_has_bounded_route_and_market_surface_per_lane(self) -> None:
        for lane, payload in self.library["lanes"].items():
            motifs = payload["motifs"]
            self.assertGreater(len(motifs), 100, lane)
            self.assertTrue(any("unit" in row["channels"] for row in motifs))
            self.assertTrue(any("market" in row["channels"] for row in motifs))
            self.assertTrue(all(8 <= row["end"] - row["start"] + 1 <= 48 for row in motifs))

    def test_initial_population_contains_multi_gene_combinations(self) -> None:
        for lane in self.library["lanes"]:
            rows = initial_genomes(lane, self.library, 8, 8142026)
            self.assertEqual(8, len({row.genome_id for row in rows}))
            self.assertTrue(any(len(row.route_blocks) + len(row.market_policy) + len(row.constants) >= 2 for row in rows))

    def test_initial_population_covers_four_lane_local_islands(self) -> None:
        for lane in self.library["lanes"]:
            rows = initial_genomes(lane, self.library, 16, 8142026)
            self.assertEqual({"route", "market", "constants", "coupled"}, {genome_island(row) for row in rows})

    def test_mutation_is_lane_owned(self) -> None:
        import random
        for lane in self.library["lanes"]:
            parent = AsyncGenome()
            child = mutate(parent, lane, self.library, random.Random(17))
            self.assertNotEqual(parent.genome_id, child.genome_id)


class ExactCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.library = load_library(LIBRARY_PATH)
        cls.traces = {
            lane: run_control(lane, "other_incumbent", TECHNICAL_SEED, 0, capture_trace=True).trace
            for lane in cls.library["lanes"]
        }

    def test_control_compiles_independently_per_lane(self) -> None:
        rows = [compile_genome(lane, AsyncGenome(), self.library, self.traces[lane]) for lane in self.library["lanes"]]
        self.assertTrue(all(hasattr(row, "candidate_id") for row in rows))
        self.assertNotEqual(rows[0].candidate_id, rows[1].candidate_id)

    def test_control_is_a_pre_efficacy_semantic_no_op(self) -> None:
        for lane in self.library["lanes"]:
            candidate = compile_genome(lane, AsyncGenome(), self.library, self.traces[lane])
            self.assertTrue(semantic_noop(candidate))
            self.assertTrue(phenotype_id(candidate).startswith("ph_"))

    def test_compile_smoke_contains_coupled_candidates(self) -> None:
        payload = json.loads((HERE / "artifacts" / "compile_smoke.json").read_text(encoding="utf-8"))
        for lane in self.library["lanes"]:
            self.assertEqual(8, len(payload["lanes"][lane]["compiled"]))
            self.assertGreater(payload["lanes"][lane]["multi_gene_candidates"], 0)

    def test_runtime_selector_has_no_opponent_identity(self) -> None:
        self.assertNotIn("opponent_identity", RUNTIME_SOURCE)
        self.assertNotIn("opponent_name", RUNTIME_SOURCE)

    def test_engine_identity_is_current(self) -> None:
        fingerprint = engine_fingerprint()
        self.assertEqual("4b78842d0f2d4abf6e318a8248b6306454f5c714", fingerprint["python_blob"])
        self.assertEqual("0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8", fingerprint["configuration_blob"])


class StatusTests(unittest.TestCase):
    def test_status_does_not_create_absent_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="async-status-") as temp:
            path = Path(temp) / "absent"
            self.assertFalse(path.exists())
            self.assertFalse(status(path)["exists"])
            self.assertFalse(path.exists())


class RankingAndCachePropertyTests(unittest.TestCase):
    def _score(self, candidate_id: str, digest: str, *, mean: float, worst: float, opponent_worst: float, positive: int, wins: int, losses: int, complexity: int) -> dict:
        return {
            "candidate_id": candidate_id,
            "action_digest_vector_sha256": digest,
            "phenotype_id": f"ph_{candidate_id}",
            "technical_pass": True,
            "actual_win_delta": 0,
            "paired_wdl": {"win": wins, "draw": 0, "loss": losses},
            "opponent_positive_families": positive,
            "opponent_worst_mean_margin": opponent_worst,
            "worst_paired_margin": worst,
            "mean_paired_margin": mean,
            "mean_own_bank": mean,
            "complexity": complexity,
        }

    def test_near_tie_ranking_penalizes_opponent_overfit(self) -> None:
        overfit = self._score("overfit", "d1", mean=100.0, worst=-500.0, opponent_worst=-200.0, positive=1, wins=2, losses=2, complexity=1)
        consistent = self._score("consistent", "d2", mean=20.0, worst=-5.0, opponent_worst=5.0, positive=2, wins=3, losses=1, complexity=2)
        self.assertEqual("consistent", sorted([overfit, consistent], key=ranking_key)[0]["candidate_id"])

    def test_action_digest_and_pareto_dedup_keep_one_representative(self) -> None:
        simple = self._score("simple", "same", mean=10.0, worst=0.0, opponent_worst=1.0, positive=2, wins=2, losses=0, complexity=1)
        complex_row = self._score("complex", "same", mean=10.0, worst=0.0, opponent_worst=1.0, positive=2, wins=2, losses=0, complexity=3)
        unique, duplicates = deduplicate_scores([complex_row, simple])
        self.assertEqual(["simple"], [row["candidate_id"] for row in unique])
        self.assertEqual(1, len(duplicates))
        self.assertEqual(["simple"], [row["candidate_id"] for row in pareto([complex_row, simple])])

    def test_candidate_context_cache_identity_ignores_generation(self) -> None:
        library = load_library(LIBRARY_PATH)
        lane = "v27_current_meta"
        trace = run_control(lane, "other_incumbent", TECHNICAL_SEED, 0, capture_trace=True).trace
        genome = initial_genomes(lane, library, 4, 8142026)[0]
        candidate = compile_genome(lane, genome, library, trace)
        first = _job(candidate, 0, "other_incumbent", 0)
        second = _job(candidate, 7, "other_incumbent", 0)
        self.assertNotEqual(first["job_id"], second["job_id"])
        self.assertEqual(first["context_cache_id"], second["context_cache_id"])

    def test_worker_cap_is_fifteen(self) -> None:
        self.assertEqual(15, MAX_WORKERS)

    def test_semantic_nonempty_is_not_observed_behavior_changing(self) -> None:
        report = observed_behavior_summary([{
            "candidate_id": "ac_bf69712345be6ebcf0a80f89",
            "phenotype_id": "ph_6bea70fd4b52299125c27030",
            "action_changed_contexts": 0,
            "behavior_changing": False,
        }])
        self.assertEqual(1, report["evaluated_compile_nonempty_semantic_phenotypes"])
        self.assertEqual(0, report["observed_behavior_changing_phenotypes"])
        self.assertEqual(1, report["observed_action_no_op_phenotypes"])
        self.assertEqual(
            ["ac_bf69712345be6ebcf0a80f89"],
            report["observed_action_no_op_candidate_ids"],
        )
        self.assertTrue(report["behavior_flag_consistent"])


class SeedAccountingTests(unittest.TestCase):
    def test_formal_authorized_consumed_seed_is_not_fresh(self) -> None:
        accounting = classify_evaluation_seeds(
            (81426017, 81426029), formal_authorized=True,
        )
        self.assertTrue(accounting["formal_authorized"])
        self.assertEqual([81426017, 81426029], accounting["retained_consumed_e1_seeds"])
        self.assertEqual([], accounting["fresh_seeds"])
        self.assertTrue(accounting["retained_e1_seeds_configured"])
        self.assertFalse(accounting["retained_e1_seeds_executed"])
        self.assertFalse(accounting["formal_fresh_seeds_executed"])

    def test_only_explicit_fresh_seed_sets_fresh_execution(self) -> None:
        accounting = classify_evaluation_seeds(
            (91234567,), formal_authorized=True, explicit_fresh_seeds=(91234567,),
        )
        self.assertEqual([91234567], accounting["fresh_seeds"])
        self.assertTrue(accounting["fresh_seeds_configured"])
        self.assertFalse(accounting["retained_e1_seeds_executed"])
        self.assertFalse(accounting["formal_fresh_seeds_executed"])

    def test_manifest_keeps_authorization_and_freshness_independent(self) -> None:
        library = load_library(LIBRARY_PATH)
        body = _manifest_body(
            LIBRARY_PATH, library, 2, 1, ("other_incumbent",), 811407,
            (81426017, 81426029), True, {"test": "pure-manifest"},
        )
        self.assertTrue(body["formal_authorized"])
        self.assertFalse(body["formal_fresh_seeds_executed"])
        self.assertTrue(body["seed_accounting"]["retained_e1_seeds_configured"])
        self.assertFalse(body["retained_e1_seeds_executed"])
        self.assertFalse(body["execution_started"])

    def test_completed_accounting_sets_executed_flags(self) -> None:
        accounting = classify_evaluation_seeds(
            (81426017, 81426029), formal_authorized=True,
            execution_started=True, execution_completed=True,
        )
        self.assertTrue(accounting["retained_e1_seeds_executed"])
        self.assertTrue(accounting["execution_started"])
        self.assertTrue(accounting["execution_completed"])


class FormalRunSeedPlumbingTests(unittest.TestCase):
    RETAINED = (81426017, 81426029)
    FRESH = (91234567,)

    def _protocol(self, *, retained: tuple[int, ...] = (), fresh: tuple[int, ...] = ()) -> dict:
        seeds = retained + fresh
        return {
            "schema_version": 2,
            "formal_authorized": True,
            "evaluation_seeds": list(seeds),
            "seed_classification": {
                "technical": [],
                "retained_consumed_e1": list(retained),
                "fresh": list(fresh),
            },
            "population_per_lane": 2,
            "generations": 1,
            "workers": 1,
            "proposal_seed": 1,
            "candidate_context_jobs": 0,
        }

    def _registry(self, *, retained: tuple[int, ...] = (), fresh: tuple[int, ...] = ()) -> dict:
        return {
            "run_id": "unit",
            "classifications": {
                "technical": [811407],
                "retained_consumed_e1": list(retained),
                "fresh": list(fresh),
            },
        }

    def test_retained_execute_passes_empty_fresh_set(self) -> None:
        protocol = self._protocol(retained=self.RETAINED)
        plumbing = formal_run._validated_seed_plumbing(
            protocol, self._registry(retained=self.RETAINED),
            registry_path=HERE / "formal" / "e1_seed_registry.json",
        )
        validated = {
            "library_path": LIBRARY_PATH,
            "run_root": HERE / "never-executed-retained",
            "opponents": ("other_incumbent",),
            "seeds": plumbing["evaluation_seeds"],
            "fresh_evaluation_seeds": plumbing["fresh_evaluation_seeds"],
            "registry_path": HERE / "formal" / "e1_seed_registry.json",
            "authority": {"unit": "retained"},
        }
        with patch.object(formal_run, "_validated_preflight", return_value=(protocol, validated)), patch.object(
            formal_run, "run_search", return_value={"pass": True},
        ) as mocked:
            formal_run.execute(Path("protocol.json"), Path("preflight.json"))
        kwargs = mocked.call_args.kwargs
        self.assertEqual(self.RETAINED, kwargs["evaluation_seeds"])
        self.assertEqual((), kwargs["fresh_evaluation_seeds"])
        self.assertTrue(kwargs["formal_authorized"])

    def test_explicit_registry_fresh_execute_passes_only_fresh_set(self) -> None:
        protocol = self._protocol(fresh=self.FRESH)
        plumbing = formal_run._validated_seed_plumbing(
            protocol, self._registry(fresh=self.FRESH),
            registry_path=HERE / "formal" / "e1_seed_registry.json",
        )
        validated = {
            "library_path": LIBRARY_PATH,
            "run_root": HERE / "never-executed-fresh",
            "opponents": ("other_incumbent",),
            "seeds": plumbing["evaluation_seeds"],
            "fresh_evaluation_seeds": plumbing["fresh_evaluation_seeds"],
            "registry_path": HERE / "formal" / "e1_seed_registry.json",
            "authority": {"unit": "fresh"},
        }
        with patch.object(formal_run, "_validated_preflight", return_value=(protocol, validated)), patch.object(
            formal_run, "run_search", return_value={"pass": True},
        ) as mocked:
            formal_run.execute(Path("protocol.json"), Path("preflight.json"))
        self.assertEqual(self.FRESH, mocked.call_args.kwargs["fresh_evaluation_seeds"])

    def test_unknown_seed_cannot_be_inferred_fresh(self) -> None:
        protocol = self._protocol(fresh=self.FRESH)
        with self.assertRaisesRegex(ValueError, "protocol/registry fresh classification mismatch"):
            formal_run._validated_seed_plumbing(
                protocol, self._registry(),
                registry_path=HERE / "formal" / "e1_seed_registry.json",
            )

    def test_real_protocol_registry_authority_hashes_are_validated(self) -> None:
        protocol_path = HERE / "formal" / "e1_protocol.json"
        protocol, validated = formal_run._protocol(protocol_path)
        self.assertEqual(2, protocol["schema_version"])
        self.assertEqual((), validated["fresh_evaluation_seeds"])
        self.assertEqual(self.RETAINED, validated["seeds"])
        self.assertEqual(
            formal_run.file_sha256(HERE / "formal" / "e1_seed_registry.json"),
            validated["authority"]["seed_registry_file_sha256"],
        )
        self.assertEqual(
            formal_run.file_sha256(protocol_path),
            validated["authority"]["protocol_file_sha256"],
        )

    def test_nondefault_registry_flows_into_preflight_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="async-registry-preflight-") as temp:
            root = Path(temp)
            registry_path = root / "nondefault_registry.json"
            registry = self._registry(retained=self.RETAINED)
            registry["run_id"] = "nondefault-registry-unit"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            protocol = self._protocol(retained=self.RETAINED)
            protocol.update({"run_id": registry["run_id"], "opponents": ["other_incumbent"]})
            plumbing = formal_run._validated_seed_plumbing(
                protocol, registry, registry_path=registry_path,
            )
            authority = {
                "seed_registry_file_sha256": file_sha256(registry_path),
                "seed_accounting": plumbing["accounting"],
            }
            validated = {
                "run_root": root / "run",
                "library_path": LIBRARY_PATH,
                "library": load_library(LIBRARY_PATH),
                "opponents": ("other_incumbent",),
                "seeds": plumbing["evaluation_seeds"],
                "fresh_evaluation_seeds": plumbing["fresh_evaluation_seeds"],
                "registry_path": registry_path,
                "registry": registry,
                "seed_accounting": plumbing["accounting"],
                "authority": authority,
                "program_tree_parallel_pool_mean_percent": 35.0,
            }
            output = root / "preflight.json"
            with patch.object(formal_run, "_protocol", return_value=(protocol, validated)), patch.object(
                formal_run, "_freeze_generation_zero",
                return_value={"generation_sha256": "unit", "job_manifest_sha256": "unit", "candidate_count": 0, "job_count": 0},
            ):
                formal_run.preflight(root / "protocol.json", output)
            manifest = formal_run._load_hashed(validated["run_root"] / "search_manifest.json", "manifest_sha256")
            self.assertEqual("nondefault-registry-unit", manifest["seed_accounting"]["registry_run_id"])
            self.assertEqual(file_sha256(registry_path), manifest["seed_registry_file_sha256"])
            self.assertNotEqual(
                file_sha256(HERE / "formal" / "e1_seed_registry.json"),
                manifest["seed_registry_file_sha256"],
            )
            self.assertTrue(manifest["seed_accounting"]["retained_e1_seeds_configured"])
            self.assertFalse(manifest["retained_e1_seeds_executed"])
            self.assertFalse(manifest["execution_started"])
            self.assertFalse(manifest["execution_completed"])

    def test_tampered_registry_is_rejected_before_evaluation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="async-registry-tamper-") as temp:
            root = Path(temp)
            registry_path = root / "registry.json"
            registry = self._registry(retained=self.RETAINED)
            registry["run_id"] = "frozen-before-tamper"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            accounting = classify_evaluation_seeds(
                self.RETAINED, formal_authorized=True,
                registry=registry, registry_path=registry_path,
            )
            authority = {
                "seed_registry_file_sha256": file_sha256(registry_path),
                "seed_accounting": accounting,
            }
            registry["run_id"] = "tampered-after-freeze"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            with patch.object(search_module, "run_control") as evaluator:
                with self.assertRaisesRegex(ValueError, "registry hash differs"):
                    search_module.run_search(
                        LIBRARY_PATH, root / "run", population=2, generations=1, workers=1,
                        opponents=("other_incumbent",), proposal_seed=1,
                        evaluation_seeds=self.RETAINED, formal_authorized=True,
                        authority=authority, fresh_evaluation_seeds=(),
                        seed_registry_path=registry_path,
                    )
            evaluator.assert_not_called()

    def test_registry_identity_change_rejects_resume_before_evaluation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="async-registry-resume-") as temp:
            root = Path(temp)
            run_root = root / "run"
            run_root.mkdir()
            registry_path = root / "registry.json"
            registry_a = self._registry(retained=self.RETAINED)
            registry_a["run_id"] = "registry-a"
            registry_path.write_text(json.dumps(registry_a), encoding="utf-8")
            library = load_library(LIBRARY_PATH)
            accounting_a = classify_evaluation_seeds(
                self.RETAINED, formal_authorized=True,
                registry=registry_a, registry_path=registry_path,
            )
            authority_a = {
                "seed_registry_file_sha256": file_sha256(registry_path),
                "seed_accounting": accounting_a,
            }
            manifest_a = search_module._manifest_body(
                LIBRARY_PATH, library, 2, 1, ("other_incumbent",), 1,
                self.RETAINED, True, authority_a, (), registry_path, registry_a,
            )
            search_module._write_hashed(run_root / "search_manifest.json", manifest_a, "manifest_sha256")
            registry_b = self._registry(retained=self.RETAINED)
            registry_b["run_id"] = "registry-b"
            registry_path.write_text(json.dumps(registry_b), encoding="utf-8")
            accounting_b = classify_evaluation_seeds(
                self.RETAINED, formal_authorized=True,
                registry=registry_b, registry_path=registry_path,
            )
            authority_b = {
                "seed_registry_file_sha256": file_sha256(registry_path),
                "seed_accounting": accounting_b,
            }
            with patch.object(search_module, "run_control") as evaluator:
                with self.assertRaisesRegex(ValueError, "resume manifest/config/hash mismatch"):
                    search_module.run_search(
                        LIBRARY_PATH, run_root, population=2, generations=1, workers=1,
                        opponents=("other_incumbent",), proposal_seed=1,
                        evaluation_seeds=self.RETAINED, formal_authorized=True,
                        authority=authority_b, fresh_evaluation_seeds=(),
                        seed_registry_path=registry_path,
                    )
            evaluator.assert_not_called()


class ProtocolDesignTests(unittest.TestCase):
    def test_e1b_protocol_is_non_executable_and_progressive(self) -> None:
        payload = json.loads((HERE / "formal" / "e1b_progressive_protocol.json").read_text(encoding="utf-8"))
        self.assertFalse(payload["executable"])
        self.assertFalse(payload["formal_authorized"])
        self.assertEqual(15, payload["workers"]["default"])
        self.assertEqual(15, payload["workers"]["maximum"])
        self.assertIn(
            "compile_distinct_nonempty_semantic_per_lane_minimum",
            payload["topology_contract"],
        )
        self.assertNotIn(
            "behavior_changing_unique_per_lane_minimum",
            payload["topology_contract"],
        )
        self.assertEqual(
            ["static_proposals", "technical_legality_no_op", "consumed_e1_small_screen", "consumed_e1_full_contexts"],
            [row["name"] for row in payload["progressive_stages"]],
        )
        self.assertTrue(all(not row["execute_in_this_development"] for row in payload["progressive_stages"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
