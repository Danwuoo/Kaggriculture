from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


LANE = Path(__file__).resolve().parents[1]
ROOT = LANE.parents[1]
if str(LANE) not in sys.path:
    sys.path.insert(0, str(LANE))

from max_search.checkpoint import (  # noqa: E402
    CheckpointError, RunManifest, RunState, atomic_json, read_status,
)
from max_search.coordinator import (  # noqa: E402
    CandidateBirth, CandidateIndex, CoordinatorError, GenerationBudget, propose_generation, read_birth_shard,
    seed_index, write_birth_shard,
)
from max_search.contract import ContractError, LANES, load_contract  # noqa: E402
from max_search.evolution import (  # noqa: E402
    FitnessVector, MutationEngine, compatible_crossover, dominates, island_layout,
    select_survivors,
)
from max_search.genome import (  # noqa: E402
    FullTapeGenome, GenomeError, PASS_ACTION, RootRegistry, RootTape, StepPatch, candidate_lane,
)
from max_search.policy import make_policy_factory, project_action  # noqa: E402
from max_search.preflight import source_snapshot  # noqa: E402
from max_search.scoring import (  # noqa: E402
    ScoringError, ScoringIdentity, paired_row, score_candidate, select_broad_finalists,
)


CONTRACT_PATH = LANE / "max_search_contract.json"


def tape(market=None):
    action = {"farmer": ["PASS"], "hands": [], "market": market or []}
    return [copy.deepcopy(action) for _ in range(719)]


class ContractTests(unittest.TestCase):
    def test_exact_scale_and_budget_close(self):
        contract = load_contract(CONTRACT_PATH)
        summary = contract.plan_summary()
        self.assertEqual(summary["birth_quota_total"], 30_000_000)
        self.assertEqual(summary["t0_candidate_games"], 180_000_000)
        self.assertEqual(summary["t1_candidate_games"], 120_000_000)
        self.assertEqual(summary["t1_promotion_total"], 5_000_000)
        self.assertEqual(summary["birth_quota_distribution"], {"14999": 1384, "15000": 615, "16384": 1})

    def test_island_quotas_close_each_generation(self):
        contract = load_contract(CONTRACT_PATH)
        for generation in (0, 1, 615, 616, 1999):
            quotas = contract.island_birth_quotas(generation)
            self.assertEqual(len(quotas), 32)
            self.assertEqual(sum(quotas), contract.birth_quota(generation))
            self.assertLessEqual(max(quotas) - min(quotas), 1)

    def test_contract_tamper_fails_closed(self):
        payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        payload["scale"]["raw_candidates"] -= 1
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "contract.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ContractError):
                load_contract(path)

    def test_nested_contract_tampering_fails_closed(self):
        mutations = [
            lambda value: value["tiers"].update({"t0": {"candidate_count": 30_000_000, "games_per_candidate": 5, "candidate_games": 150_000_000}, "t1": {"candidate_count": 5_000_000, "additional_games_per_candidate": 30, "candidate_games": 150_000_000}}),
            lambda value: value["genome"].update({"channels": []}),
            lambda value: value["genome"].update({"root_families": []}),
            lambda value: value["selection"].update({"tail_fields": []}),
            lambda value: value["selection"].update({"tie_break_fields": []}),
            lambda value: value.update({"engine": {"commit": "arbitrary"}}),
        ]
        for mutate in mutations:
            payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
            mutate(payload)
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "contract.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ContractError):
                    load_contract(path)

    def test_layout_is_lane_balanced(self):
        layout = island_layout(load_contract(CONTRACT_PATH))
        self.assertEqual(len(layout), 32)
        for lane in LANES:
            rows = [row for row in layout if row.lane == lane]
            self.assertEqual(len(rows), 16)
            self.assertEqual({mode: sum(row.mode == mode for row in rows) for mode in {row.mode for row in rows}}, {
                "coordinate": 4, "large_neighborhood": 4, "de_novo": 4, "novelty": 4,
            })


class GenomeTests(unittest.TestCase):
    def setUp(self):
        self.v27_root = RootTape.build("lane_incumbent", LANES[0], tape())
        self.boatlee_root = RootTape.build("lane_incumbent", LANES[1], tape())
        self.public_root = RootTape.build("deduplicated_public_tape", "episode:1", tape([["HIRE"]]))
        self.registry = RootRegistry((self.v27_root, self.boatlee_root, self.public_root))

    def test_equal_route_bytes_keep_lane_owned_roots(self):
        self.assertNotEqual(self.v27_root.root_id, self.boatlee_root.root_id)
        self.assertEqual(self.v27_root.digest, self.boatlee_root.digest)
        self.assertEqual(self.registry.incumbent(LANES[0]).source_id, LANES[0])
        self.assertEqual(self.registry.incumbent(LANES[1]).source_id, LANES[1])

    def test_sparse_patch_round_trip(self):
        genome = FullTapeGenome(LANES[0], self.v27_root.root_id, self.v27_root.digest)
        changed = genome.with_actions({17: {"farmer": ["EAST"], "hands": [], "market": []}}, self.v27_root)
        restored = FullTapeGenome.from_dict(changed.to_dict())
        self.assertEqual(restored, changed)
        self.assertEqual(restored.materialize(self.v27_root)[17]["farmer"], ["EAST"])
        self.assertEqual(restored.edit_distance_from_root(), 1)

    def test_root_equal_patch_is_canonical_noop(self):
        genome = FullTapeGenome(LANES[0], self.v27_root.root_id, self.v27_root.digest)
        unchanged = genome.with_actions({17: PASS_ACTION}, self.v27_root)
        self.assertEqual(unchanged, genome)

    def test_cross_lane_crossover_rejected(self):
        left = FullTapeGenome(LANES[0], self.v27_root.root_id, self.v27_root.digest)
        right = FullTapeGenome(LANES[1], self.boatlee_root.root_id, self.boatlee_root.digest)
        with self.assertRaises(GenomeError):
            compatible_crossover(left, self.v27_root, right, self.boatlee_root, start=0, horizon=1)

    def test_mutation_is_deterministic_and_bounded(self):
        contract = load_contract(CONTRACT_PATH)
        island = next(row for row in island_layout(contract) if row.lane == LANES[0] and row.mode == "large_neighborhood")
        parent = FullTapeGenome(LANES[0], self.v27_root.root_id, self.v27_root.digest)
        engine = MutationEngine(self.registry, proposal_seed=123)
        first, metadata_a = engine.child(parent, island, generation=9, ordinal=4)
        second, metadata_b = engine.child(parent, island, generation=9, ordinal=4)
        self.assertEqual(first, second)
        self.assertEqual(metadata_a, metadata_b)
        self.assertLessEqual(first.edit_distance_from_root(), 719)

    def test_candidate_identity_uses_full_digest_and_encodes_lane(self):
        genome = FullTapeGenome(LANES[0], self.v27_root.root_id, self.v27_root.digest)
        self.assertEqual(candidate_lane(genome.candidate_id), LANES[0])
        self.assertEqual(len(genome.candidate_id.rsplit("_", 1)[1]), 64)


class PolicyTests(unittest.TestCase):
    def observation(self, seeds=None, hands=0):
        return {
            "player": 0,
            "step": 0,
            "farms": [{"hands": [[4, 4] for _ in range(hands)]}, {"hands": []}],
            "private": {"seeds": seeds if seeds is not None else {"WHEAT": 0}},
        }

    def test_projection_caps_market_aligns_hands_and_cancels_atomic_plant(self):
        incumbent = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
        candidate = {
            "farmer": ["PLANT", "WHEAT"],
            "hands": [["PLANT", "WHEAT"], ["EAST"]],
            "market": [["HIRE"] for _ in range(11)],
        }
        projected = project_action(self.observation({"WHEAT": 1}, hands=1), candidate, incumbent)
        self.assertEqual(projected["farmer"], ["PASS"])
        self.assertEqual(projected["hands"], [["PASS"]])
        self.assertEqual(len(projected["market"]), 10)

    def test_missing_private_state_falls_back(self):
        incumbent = {"farmer": ["WEST"], "hands": [], "market": []}
        observation = self.observation()
        del observation["private"]
        projected = project_action(observation, PASS_ACTION, incumbent)
        self.assertEqual(projected, incumbent)

    def test_unpatched_incumbent_policy_is_exact_delegate(self):
        root = RootTape.build("lane_incumbent", LANES[0], tape([["HIRE"]]))
        genome = FullTapeGenome(LANES[0], root.root_id, root.digest)
        expected = {"farmer": ["NORTH"], "hands": [], "market": [["BUY_LAND"]]}

        def incumbent(_obs, _configuration=None):
            return copy.deepcopy(expected)

        policy = make_policy_factory(genome, root)(None, incumbent, 0)
        self.assertEqual(policy(self.observation()), expected)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_contract(CONTRACT_PATH)
        self.root = RootTape.build("lane_incumbent", LANES[0], tape())
        self.registry = RootRegistry((self.root,))
        self.sources = {"engine": {"passed": True}}

    def manifest(self):
        return RunManifest.create(
            run_id="development_test", contract=self.contract,
            source_snapshot=self.sources, root_manifest=self.registry.manifest(), proposal_seed=1,
        )

    def test_formal_manifest_requires_frozen_execution_inputs(self):
        with self.assertRaises(CheckpointError):
            RunManifest.create(
                run_id="formal_test", contract=self.contract,
                source_snapshot=self.sources, root_manifest=self.registry.manifest(), proposal_seed=1,
                formal_execution_authorized=True,
            )
        with self.assertRaises(CheckpointError):
            RunManifest.create(
                run_id="formal_bypass", contract=self.contract,
                source_snapshot=self.sources, root_manifest=self.registry.manifest(), proposal_seed=1,
                seed_registry={}, context_registry={}, physical_workers=1,
                formal_execution_authorized=True,
            )

    def population_ids(self):
        from max_search.evolution import island_layout
        values = {}
        ordinal = 0
        for island in island_layout(self.contract):
            token = "v27" if island.lane == LANES[0] else "boatlee"
            rows = []
            for _ in range(island.capacity):
                rows.append(f"ft_{token}_{ordinal:064x}")
                ordinal += 1
            values[island.island_id] = rows
        return values

    def test_checkpoint_enforces_exact_islands_capacity_uniqueness_and_lane(self):
        manifest = self.manifest()
        valid = self.population_ids()
        state = RunState.initial(manifest, self.contract, valid)
        state.validate(manifest, self.contract)
        cases = []
        missing = copy.deepcopy(valid)
        missing.pop(next(iter(missing)))
        cases.append(missing)
        duplicate = copy.deepcopy(valid)
        first = next(iter(duplicate))
        duplicate[first][1] = duplicate[first][0]
        cases.append(duplicate)
        cross_lane = copy.deepcopy(valid)
        v27_island = next(key for key in cross_lane if "v27_current_meta" in key)
        cross_lane[v27_island][0] = "ft_boatlee_" + "f" * 64
        cases.append(cross_lane)
        short = copy.deepcopy(valid)
        short[first].pop()
        cases.append(short)
        for populations in cases:
            with self.assertRaises(CheckpointError):
                RunState.initial(manifest, self.contract, populations)

    def test_signed_manifest_round_trip_and_tamper_rejection(self):
        manifest = self.manifest()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            atomic_json(path, manifest.payload)
            loaded = RunManifest.load(path, expected_contract_sha256=self.contract.sha256)
            self.assertEqual(loaded.sha256, manifest.sha256)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["proposal_seed"] = 2
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CheckpointError):
                RunManifest.load(path)

    def test_status_does_not_create_missing_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            self.assertFalse(read_status(missing)["exists"])
            self.assertFalse(missing.exists())


class SelectionTests(unittest.TestCase):
    CONTROL = "0" * 64

    def setUp(self):
        self.contract = load_contract(CONTRACT_PATH)
        self.manifest = RunManifest.create(
            run_id="scoring_test", contract=self.contract,
            source_snapshot={
                "pool_lanes": False,
                "controls": {lane: {"sha256": self.CONTROL} for lane in LANES},
            },
            root_manifest={"manifest_sha256": "1" * 64}, proposal_seed=1,
        )
        self.identity_root = RootTape.build("lane_incumbent", LANES[0], tape())
        self.identity = ScoringIdentity.from_manifest(
            self.manifest,
            FullTapeGenome(LANES[0], self.identity_root.root_id, self.identity_root.digest),
        )

    @staticmethod
    def candidate_id(name, lane=LANES[0]):
        token = "v27" if lane == LANES[0] else "boatlee"
        return f"ft_{token}_{hashlib.sha256(name.encode()).hexdigest()}"

    def row(self, candidate_id, **overrides):
        values = dict(
            candidate_id=self.candidate_id(candidate_id), lane=LANES[0], control_sha256=self.CONTROL,
            manifest_sha256=self.manifest.sha256,
            technical_pass=True, net_wdl_transition=1,
            effective_change=True,
            w_to_l=0, repeatable_family_seat_negative_tails=0, cvar_01=0,
            cvar_05=0, worst_margin=0, mean_margin=1, mean_own_bank=1,
            complexity=1, novelty=0,
        )
        values.update(overrides)
        return FitnessVector(**values)

    def test_pareto_selection_preserves_non_dominated_tradeoff(self):
        safe = self.row("safe", net_wdl_transition=2, worst_margin=0)
        upside = self.row("upside", net_wdl_transition=3, worst_margin=-10)
        dominated = self.row("dominated", net_wdl_transition=1, worst_margin=-20)
        self.assertFalse(dominates(safe, upside))
        self.assertFalse(dominates(upside, safe))
        selected = select_survivors([safe, upside, dominated], 2)
        self.assertEqual({row.candidate_id for row in selected}, {safe.candidate_id, upside.candidate_id})

    def test_scoring_retains_repeated_family_seat_tail(self):
        rows = [
            paired_row(
                identity=self.identity,
                opponent_family="family", seed=seed, seat=0,
                control_margin=-1, candidate_margin=(-2 if seed < 3 else 2),
                control_own_bank=10, candidate_own_bank=11,
                technical_pass=True, effective_change=True,
            )
            for seed in (1, 2, 3)
        ]
        vector, diagnostics = score_candidate(
            self.identity, rows,
            complexity=1, novelty=0.5,
        )
        self.assertEqual(vector.repeatable_family_seat_negative_tails, 1)
        self.assertEqual(len(diagnostics["repeatable_family_seat_negative_tails"][0]["negative_seeds"]), 2)

    def test_action_only_noop_is_ineligible(self):
        row = paired_row(
            identity=self.identity,
            opponent_family="family", seed=1, seat=0,
            control_margin=1, candidate_margin=1,
            control_own_bank=10, candidate_own_bank=10,
            technical_pass=True, effective_change=False,
        )
        vector, _ = score_candidate(
            self.identity, [row],
            complexity=1, novelty=1,
        )
        self.assertFalse(vector.effective_change)
        self.assertEqual(vector.objectives()[0], float("-inf"))

    def test_invalid_rows_never_fill_survivor_capacity(self):
        eligible = self.row("eligible")
        invalid = self.row("invalid", technical_pass=False)
        with self.assertRaises(GenomeError):
            select_survivors([eligible, invalid], 2)

    def test_fixed_tie_break_prefers_margin_then_bank_then_complexity_then_novelty(self):
        high_margin = self.row("high_margin", mean_margin=2, mean_own_bank=0, complexity=10, novelty=0)
        high_bank = self.row("high_bank", mean_margin=1, mean_own_bank=100, complexity=1, novelty=100)
        selected = select_survivors([high_margin, high_bank], 1)
        self.assertEqual(selected[0].candidate_id, high_margin.candidate_id)

    def test_nonfinite_scores_fail_closed(self):
        with self.assertRaises(ScoringError):
            paired_row(
                identity=self.identity,
                opponent_family="family", seed=1, seat=0,
                control_margin=0, candidate_margin=float("nan"),
                control_own_bank=0, candidate_own_bank=0,
                technical_pass=True, effective_change=True,
            )
        with self.assertRaises(GenomeError):
            self.row("nan", novelty=float("inf"))

    def test_broad_selection_rejects_cross_lane_bucket(self):
        rows = {
            LANES[0]: [self.row(f"v27_{index}") for index in range(50)],
            LANES[1]: [self.row(f"wrong_{index}") for index in range(50)],
        }
        with self.assertRaises(ScoringError):
            select_broad_finalists(rows, manifest=self.manifest)
        with self.assertRaises(TypeError):
            select_broad_finalists(rows, manifest=self.manifest, per_lane=1)

    def test_score_rejects_row_provenance_relabeling(self):
        with self.assertRaises(TypeError):
            ScoringIdentity(self.manifest.sha256, self.identity.candidate_id, LANES[0], self.CONTROL)
        row = paired_row(
            identity=self.identity, opponent_family="family", seed=1, seat=0,
            control_margin=0, candidate_margin=1, control_own_bank=0, candidate_own_bank=1,
            technical_pass=True, effective_change=True,
        )
        tampered = copy.deepcopy(row)
        tampered["provenance"]["lane"] = LANES[1]
        with self.assertRaises(ScoringError):
            score_candidate(self.identity, [tampered], complexity=1, novelty=0)
        tampered = copy.deepcopy(row)
        tampered["margin_delta"] = 999
        tampered["outcome_rank_delta"] = 2
        tampered["own_bank_delta"] = 888
        with self.assertRaises(ScoringError):
            score_candidate(self.identity, [tampered], complexity=1, novelty=0)
        tampered = copy.deepcopy(row)
        tampered["context"]["opponent_family"] = ""
        with self.assertRaises(ScoringError):
            score_candidate(self.identity, [tampered], complexity=1, novelty=0)


class WorkspacePreflightTests(unittest.TestCase):
    def test_audited_engine_and_lane_sources_fingerprint(self):
        contract = load_contract(CONTRACT_PATH)
        registry = RootRegistry.load_workspace(ROOT, include_public=False)
        snapshot = source_snapshot(ROOT, contract, registry)
        self.assertEqual(snapshot["engine"]["python_sha256"], contract.payload["engine"]["python_sha256"])
        self.assertEqual(snapshot["engine"]["configuration_sha256"], contract.payload["engine"]["configuration_sha256"])
        self.assertEqual(set(snapshot["controls"]), set(LANES))
        self.assertFalse(snapshot["pool_lanes"])
        self.assertGreaterEqual(snapshot["implementation"]["file_count"], 10)
        self.assertEqual(len(snapshot["implementation"]["manifest_sha256"]), 64)


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_contract(CONTRACT_PATH)
        roots = [
            RootTape.build("lane_incumbent", LANES[0], tape()),
            RootTape.build("lane_incumbent", LANES[1], tape()),
            RootTape.build("deduplicated_public_tape", "episode:1", tape([["HIRE"]])),
            RootTape.build("deduplicated_public_tape", "episode:2", tape([["BUY_LAND"]])),
        ]
        self.registry = RootRegistry(roots)
        self.layout = island_layout(self.contract)
        self.catalog = {}
        self.populations = {}
        for island in self.layout:
            root = self.registry.incumbent(island.lane)
            genome = FullTapeGenome(island.lane, root.root_id, root.digest)
            # Catalog semantics may be shared across same-lane islands, but the
            # population mapping remains explicit.
            self.catalog[genome.candidate_id] = genome.to_dict()
            self.populations[island.island_id] = [genome.candidate_id]

    def test_generation_budget_closes(self):
        budget = GenerationBudget.from_contract(self.contract, 1)
        self.assertEqual(sum(budget.births_by_island), budget.births)
        self.assertEqual(budget.t0_games, budget.births * 6)
        self.assertEqual(budget.t1_games, budget.t1_promotions * 24)

    def test_streaming_generation_and_shard_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            index = CandidateIndex(Path(temporary) / "candidates.sqlite", manifest_sha256="1" * 64)
            # seed_index requires a unique ownership row per semantic ID; use
            # two representatives and let island residents share them.
            for candidate_id, value in self.catalog.items():
                lane = value["lane"]
                index.add(FullTapeGenome.from_dict(value), 0, f"seed_{lane}", expected_lane=lane)
            index.commit()
            births, summary = propose_generation(
                contract=self.contract, registry=self.registry, proposal_seed=7,
                generation=1, populations=self.populations, catalog=self.catalog,
                index=index, development_limit_per_island=1,
            )
            self.assertEqual(len(births), 32)
            self.assertFalse(summary["saturated_islands"])
            path = Path(temporary) / "births.jsonl.gz"
            artifact = write_birth_shard(path, births)
            restored = list(read_birth_shard(path))
            self.assertEqual([row.genome for row in restored], [row.genome for row in births])
            self.assertEqual(artifact["rows"], 32)
            index.close()

    def test_index_provenance_collision_and_crash_reconciliation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidates.sqlite"
            manifest = "2" * 64
            genome = FullTapeGenome.from_dict(next(iter(self.catalog.values())))
            with CandidateIndex(path, manifest_sha256=manifest) as index:
                self.assertTrue(index.add(genome, 1, "island", expected_lane=genome.lane))
                index.rollback()
                self.assertEqual(index.generation_count(1), 0)
                birth = CandidateBirth(
                    1, "island", 0, genome.candidate_id, None, genome, {"operation": "test"},
                )
                island_lanes = {"island": genome.lane}
                index.reconcile_generation(1, [birth], island_lanes=island_lanes)
                self.assertTrue(index.validate_generation(1, [birth], island_lanes=island_lanes))
                index.connection.execute(
                    "UPDATE candidates SET semantic_json='different' WHERE candidate_id=?", (genome.candidate_id,),
                )
                with self.assertRaises(CoordinatorError):
                    index.add(genome, 1, "island", expected_lane=genome.lane)
                with self.assertRaises(CoordinatorError):
                    index.reconcile_generation(1, [birth], island_lanes={"island": LANES[1]})
            with self.assertRaises(CoordinatorError):
                CandidateIndex(path, manifest_sha256="3" * 64)


if __name__ == "__main__":
    unittest.main()
