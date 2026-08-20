from __future__ import annotations

from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


LANE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LANE))

from atlas import build_atlas, build_incumbent_graph, deduplicated_tapes, first_irreversible_divergence
from authority import canonical_utf8_lf, fingerprint, load_registry, validate_registry
import compiler as compiler_module
from compiler import MAX_CANDIDATE_BYTES, RUNTIME_SOURCE, compile_candidate, static_audit, technical_evaluate
import evaluator as evaluator_module
from evaluator import classify_summary_fixture, evaluate_pairs
from model import BranchSpec, ContinuationSpec, RejoinContract, StateSignature
from proposal import proposal_oracle
from verify import calibration, sample_branch, source_inventory

LANE_NAME = "v27_current_meta"
REGISTRY = load_registry()
PROTOCOL = {
    "protocol_id": "unit-fresh-paired-v1", "paired": True, "matched_contexts": True,
    "control_lane": LANE_NAME, "candidate_lane": LANE_NAME, "seats": [0, 1], "seeds": [990001],
    "contexts": [{"seed": 990001, "family": "Kaito", "context_id": "c1"}],
    "engine": REGISTRY["engine"], "control_sha256": "063128bf765f6a6bb29ecaccc3a7dae8943e35e46c26a6364a1b3169313b9fb4",
    "candidate_sha256": "b" * 64,
}


def wdl_row(seat, control_rewards, candidate_rewards, *, seed=990001, family="Kaito", context_id="c1", **changes):
    row = {
        "lane": LANE_NAME, "seed": seed, "seat": seat, "family": family, "context_id": context_id,
        "engine": REGISTRY["engine"], "control_sha256": PROTOCOL["control_sha256"],
        "candidate_sha256": PROTOCOL["candidate_sha256"], "control_rewards": control_rewards,
        "candidate_rewards": candidate_rewards, "technical_valid": True,
    }
    row.update(changes)
    return row


def branch(**changes):
    value = asdict(sample_branch())
    value.update(changes)
    return BranchSpec.from_dict(value)


def runtime(spec):
    namespace = {"_FP_SPEC": asdict(spec), "agent": lambda obs, configuration=None: {
        "farmer": ["PASS"], "hands": [["PASS"] for _ in obs.get("farms", [{}])[obs.get("player", 0)].get("hands", [])], "market": []
    }}
    exec(RUNTIME_SOURCE, namespace)
    return namespace


def obs(step, price=10, seeds=None):
    return {"step": step, "player": 0, "farms": [{"hands": [{}]}, {"hands": []}],
            "market": {"prices": {"FERTILIZER": price}, "inventory": {"FERTILIZER": 10}},
            "private": {"seeds": seeds or {}}}


class ContractTests(unittest.TestCase):
    def test_state_id_is_canonical_and_ignores_offline_family(self):
        common = dict(step=4, lane="v27_current_meta", seat=0, public_state={"own_farm": {"money": 1}}, own_private_state={}, resource_topology={}, exact_state_digest="a" * 64)
        self.assertEqual(StateSignature(**common, opponent_family="Roman").node_id,
                         StateSignature(**common, opponent_family="Kaito").node_id)

    def test_state_rejects_identity_selector(self):
        with self.assertRaises(ValueError):
            StateSignature(4, "v27_current_meta", 0, {"team_id": 4}, {}, {}, "a" * 64)

    def test_state_rejects_private_opponent_resource_topology(self):
        with self.assertRaises(ValueError):
            StateSignature(4, LANE_NAME, 0, {}, {}, {"opponent_private.seeds": 3}, "a" * 64)
        with self.assertRaises(ValueError):
            StateSignature(4, LANE_NAME, 0, {}, {}, {"opponent": {"private": {"seeds": 3}}}, "a" * 64)
        with self.assertRaises(ValueError):
            StateSignature(4, LANE_NAME, 0, {}, {}, {"opponent": {"inventory": 3}}, "a" * 64)

    def test_state_rejects_unknown_own_private_fields_and_boolean_integers(self):
        with self.assertRaises(ValueError):
            StateSignature(4, LANE_NAME, 0, {}, {"hidden_alias": 3}, {}, "a" * 64)
        with self.assertRaises(ValueError):
            StateSignature(4, LANE_NAME, 0, {}, {"hidden_alias": {}}, {}, "a" * 64)
        with self.assertRaises(ValueError):
            StateSignature(4, LANE_NAME, True, {}, {}, {}, "a" * 64)
        with self.assertRaises(ValueError):
            StateSignature(False, LANE_NAME, 0, {}, {}, {}, "a" * 64)
        for count in (True, "2", -1):
            with self.subTest(count=count), self.assertRaises(ValueError):
                StateSignature(4, LANE_NAME, 0, {}, {"seeds": {"WHEAT": count}}, {}, "a" * 64)
        with self.assertRaises(ValueError):
            StateSignature(4, LANE_NAME, 0, {}, {}, {"worker_positions": [[True, 2]]}, "a" * 64)
        valid = StateSignature(4, LANE_NAME, 0, {}, {"seeds": {"WHEAT": 2}}, {}, "a" * 64)
        self.assertTrue(valid.node_id.startswith(f"{LANE_NAME}:"))

    def test_branch_requires_v1_schema_and_nonboolean_integer_fields(self):
        for changes in ({"schema_version": 2}, {"schema_version": True}, {"decision_step": True}, {"max_horizon": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                branch(**changes)
        with self.assertRaises(ValueError):
            branch(continuation={"mode": "immediate", "min_end_step": True, "max_end_step": 240, "rejoin": {}})

    def test_branch_round_trip_and_stable_id(self):
        original = sample_branch()
        rebuilt = BranchSpec.from_dict(json.loads(json.dumps(asdict(original))))
        self.assertEqual(original.branch_id, rebuilt.branch_id)

    def test_cross_lane_parent_rejected(self):
        with self.assertRaises(ValueError):
            branch(parent_node_id="boatlee_v16_rc2_market_relay:wrong")

    def test_opponent_private_trigger_rejected(self):
        with self.assertRaises(ValueError):
            branch(trigger={"opponent_private": {"seeds": 3}})

    def test_empty_and_private_triggers_rejected(self):
        with self.assertRaises(ValueError):
            branch(trigger={"all": []})
        with self.assertRaises(ValueError):
            branch(trigger={"all": [{"path": "private.seeds.WHEAT", "op": "ge", "value": 1}]})
        with self.assertRaises(ValueError):
            branch(trigger={"all": [{"path": "opponent_private.seeds.WHEAT", "op": "ge", "value": 1}]})
        with self.assertRaises(ValueError):
            branch(trigger={"all": [{"path": "farms.1.inventory.hidden", "op": "ge", "value": 1}]})
        with self.assertRaises(ValueError):
            branch(trigger={"all": [{"path": "opponent_farm.inventory", "op": "ge", "value": 1}]})
        with self.assertRaises(ValueError):
            branch(trigger={"all": [{"path": "market.prices.FERTILIZER", "op": "ge", "value": 1, "ignored": True}]})
        with self.assertRaises(ValueError):
            branch(trigger={"all": [{"path": "market.prices.FERTILIZER", "op": "ge", "value": 1}], "ignored": True})

    def test_forbidden_rejoin_path_rejected(self):
        with self.assertRaises(ValueError):
            RejoinContract(("opponent_private.seeds.WHEAT",), {"opponent_private.seeds.WHEAT": 1}, {})
        with self.assertRaises(ValueError):
            RejoinContract(("farms.1.private.seeds.WHEAT",), {"farms.1.private.seeds.WHEAT": 1}, {})

    def test_state_rejoin_requires_fields(self):
        with self.assertRaises(ValueError):
            ContinuationSpec("state_rejoin", 3, 4)

    def test_horizon_is_bounded(self):
        with self.assertRaises(ValueError):
            branch(max_horizon=49)

    def test_continuation_cannot_precede_decision(self):
        with self.assertRaises(ValueError):
            branch(continuation={"mode": "fixed", "min_end_step": 239, "max_end_step": 240, "rejoin": {}})


class AtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.atlas = build_atlas(include_channel_entropy=False)

    def test_retained_atlas_cardinality(self):
        self.assertEqual((self.atlas["source_representative_tapes"], self.atlas["representative_tapes"], self.atlas["nodes"], self.atlas["max_depth"]), (227, 225, 102803, 719))

    def test_exact_full_action_tapes_are_unique(self):
        tapes, duplicates = deduplicated_tapes()
        digests = [digest for _record, _actions, digest in tapes]
        self.assertEqual((len(tapes), len(digests), len(set(digests)), len(duplicates)), (225, 225, 225, 2))
        self.assertFalse(self.atlas["legacy_support_statistics_used"])
        self.assertTrue(self.atlas["legacy_node_structure_match"])

    def test_retained_turn_78_boundary(self):
        self.assertTrue(any(row == {"children": 2, "turn": 78, "aggregate_child_support": 97} for row in self.atlas["reported_branch_boundaries"]))

    def test_incumbent_dags_are_complete_and_lane_isolated(self):
        left = build_incumbent_graph("v27_current_meta")
        right = build_incumbent_graph("boatlee_v16_rc2_market_relay")
        self.assertEqual((len(left["nodes"]), len(left["edges"])), (719, 718))
        self.assertNotEqual(left["graph_digest"], right["graph_digest"])
        self.assertTrue(all(row["source"].startswith("v27_current_meta:") for row in left["edges"]))

    def test_proposal_oracle_fails_closed_without_verified_frontier_sources(self):
        atlas = build_atlas(include_channel_entropy=True)
        motifs = json.loads((LANE / "frontier_motifs.json").read_text(encoding="utf-8"))["motifs"]
        rows = json.loads((LANE.parents[1] / "research/job_value_residual_2026-08-12/artifacts/discovery_windows.json").read_text(encoding="utf-8"))["rows"]
        result = proposal_oracle(motifs, LANE_NAME, atlas, rows)
        self.assertEqual(result["status"], "BLOCKED_MISSING_EVIDENCE")
        self.assertEqual(result["ranked_proposal_count"], 0)
        self.assertTrue(all(row["priority"] is None for row in result["proposals"]))
        self.assertTrue(any(row["signals"]["replay_mutability"] is not None for row in result["proposals"]))

    def test_first_irreversible_divergence(self):
        result = first_irreversible_divergence([{"causal_digest": "a"}, {"causal_digest": "b"}], [{"causal_digest": "a"}, {"causal_digest": "c"}])
        self.assertEqual(result["divergence_step"], 1)


class EvaluatorTests(unittest.TestCase):
    def test_wdl_improvement_is_primary(self):
        rows = [
            wdl_row(0, [0, 1], [1, 0], terminal_state_changed=True),
            wdl_row(1, [0, 0], [0, 0], terminal_state_changed=False),
        ]
        result = evaluate_pairs(rows, "fresh_paired", LANE_NAME, PROTOCOL)
        self.assertEqual((result.improve, result.worsen), (1, 0))
        self.assertFalse(result.wdl_gate_passed)
        self.assertFalse(result.efficacy_eligible)
        self.assertIn("protocol_not_registered", result.stop_reasons)
        self.assertIn("candidate_artifact_not_verified", result.stop_reasons)
        self.assertIn("formal_efficacy_not_authorized", result.stop_reasons)

    def test_registered_protocol_and_independently_hashed_candidate_can_reach_mechanical_gate(self):
        with tempfile.TemporaryDirectory(dir=LANE) as temporary:
            artifact = Path(temporary) / "candidate.py"
            artifact.write_bytes(b"registered candidate fixture\n")
            relative = artifact.relative_to(LANE.parents[1]).as_posix()
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            registered = {**PROTOCOL, "candidate_source_id": "verified_candidate", "candidate_sha256": digest}
            registry = {
                **REGISTRY,
                "paired_protocols": [registered],
                "sources": [*REGISTRY["sources"], {
                    "id": "verified_candidate", "path": relative, "sha256": digest,
                    "bytes": artifact.stat().st_size, "lane": LANE_NAME,
                    "candidate_artifact": True, "technical_verified": True, "mutable": False,
                }],
            }
            rows = [
                {**wdl_row(0, [0, 1], [1, 0], terminal_state_changed=True), "candidate_sha256": digest},
                {**wdl_row(1, [0, 0], [0, 0]), "candidate_sha256": digest},
            ]
            with mock.patch.object(evaluator_module, "_registry", return_value=registry):
                result = evaluate_pairs(rows, "fresh_paired", LANE_NAME, registered)
            self.assertTrue(result.wdl_gate_passed)
            self.assertFalse(result.efficacy_eligible)
            self.assertIn("formal_efficacy_contract_not_approved", result.stop_reasons)

    def test_authorization_flag_and_approved_contract_still_enforce_support_and_uncertainty(self):
        with tempfile.TemporaryDirectory(dir=LANE) as temporary:
            artifact = Path(temporary) / "candidate.py"
            artifact.write_bytes(b"registered candidate fixture\n")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            registered = {**PROTOCOL, "candidate_source_id": "verified_candidate", "candidate_sha256": digest}
            source = {"id": "verified_candidate", "path": artifact.relative_to(LANE.parents[1]).as_posix(),
                      "sha256": digest, "bytes": artifact.stat().st_size, "lane": LANE_NAME,
                      "candidate_artifact": True, "technical_verified": True, "mutable": False}
            registry = {**REGISTRY, "formal_efficacy_authorized": True,
                        "formal_efficacy_contract": {"status": "approved", "minimum_matched_contexts": 2,
                            "minimum_independent_seeds": 2, "minimum_opponent_families": 2,
                            "uncertainty_lower_bound_rule": "cluster_bootstrap_p025_gt_0"},
                        "paired_protocols": [registered], "sources": [*REGISTRY["sources"], source]}
            rows = [{**wdl_row(0, [0, 1], [1, 0], terminal_state_changed=True), "candidate_sha256": digest},
                    {**wdl_row(1, [0, 0], [0, 0]), "candidate_sha256": digest}]
            with mock.patch.object(evaluator_module, "_registry", return_value=registry):
                result = evaluate_pairs(rows, "fresh_paired", LANE_NAME, registered)
            self.assertTrue(result.wdl_gate_passed)
            self.assertFalse(result.efficacy_eligible)
            self.assertIn("formal_efficacy_support_or_uncertainty_gate_failed", result.stop_reasons)

    def test_registered_candidate_provenance_negative_matrix_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=LANE) as temporary:
            artifact = Path(temporary) / "candidate.py"
            artifact.write_bytes(b"registered candidate fixture\n")
            relative = artifact.relative_to(LANE.parents[1]).as_posix()
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            registered = {**PROTOCOL, "candidate_source_id": "verified_candidate", "candidate_sha256": digest}
            source = {
                "id": "verified_candidate", "path": relative, "sha256": digest,
                "bytes": artifact.stat().st_size, "lane": LANE_NAME,
                "candidate_artifact": True, "technical_verified": True, "mutable": False,
            }
            rows = [
                {**wdl_row(0, [0, 1], [1, 0], terminal_state_changed=True), "candidate_sha256": digest},
                {**wdl_row(1, [0, 0], [0, 0]), "candidate_sha256": digest},
            ]
            cases = [
                {"bytes": source["bytes"] + 1},
                {"sha256": "c" * 64},
                {"lane": "boatlee_v16_rc2_market_relay"},
                {"mutable": True},
                {"technical_verified": False},
            ]
            for changes in cases:
                altered = {**source, **changes}
                protocol = {**registered, "candidate_sha256": altered["sha256"]}
                case_rows = [{**row, "candidate_sha256": altered["sha256"]} for row in rows]
                registry = {**REGISTRY, "paired_protocols": [protocol], "sources": [*REGISTRY["sources"], altered]}
                with self.subTest(changes=changes), mock.patch.object(evaluator_module, "_registry", return_value=registry):
                    result = evaluate_pairs(case_rows, "fresh_paired", LANE_NAME, protocol)
                    self.assertFalse(result.wdl_gate_passed)
                    self.assertIn("candidate_artifact_not_verified", result.stop_reasons)

    def test_action_digest_alone_is_no_effect(self):
        result = evaluate_pairs([wdl_row(0, [0, 1], [0, 1], action_digest_changed=True),
                                 wdl_row(1, [0, 1], [0, 1], action_digest_changed=True)], "fresh_paired", LANE_NAME, PROTOCOL)
        self.assertFalse(result.effective_change)
        self.assertFalse(result.efficacy_eligible)

    def test_nonfresh_or_technically_unverified_rows_are_not_efficacy(self):
        rows = [wdl_row(0, [0, 1], [1, 0], terminal_state_changed=True), wdl_row(1, [0, 0], [0, 0])]
        rows[0]["technical_valid"] = False
        self.assertFalse(evaluate_pairs(rows, "fresh_paired", LANE_NAME, PROTOCOL).efficacy_eligible)
        rows[0]["technical_valid"] = True
        self.assertFalse(evaluate_pairs(rows, "consumed_paired", LANE_NAME, PROTOCOL).efficacy_eligible)

    def test_repeatable_family_seat_tail_stops(self):
        protocol = {**PROTOCOL, "seeds": [990001, 990002], "contexts": [
            {"seed": 990001, "family": "Roman", "context_id": "c990001"},
            {"seed": 990002, "family": "Roman", "context_id": "c990002"},
        ]}
        rows = []
        for seed in protocol["seeds"]:
            rows.extend([wdl_row(0, [0, 0], [0, 0], seed=seed, family="Roman", context_id=f"c{seed}", public_state_changed=True),
                         wdl_row(1, [0, 1], [1, 0], seed=seed, family="Roman", context_id=f"c{seed}", public_state_changed=True)])
        result = evaluate_pairs(rows, "fresh_paired", LANE_NAME, protocol)
        self.assertTrue(any(reason.startswith("repeatable_stratum_worsening") for reason in result.stop_reasons))

    def test_balanced_or_mixed_lane_evidence_is_not_efficacy(self):
        balanced = [
            wdl_row(0, [0, 1], [0, 0], family="A", public_state_changed=True),
            wdl_row(1, [0, 0], [1, 0], family="A", public_state_changed=True),
        ]
        self.assertFalse(evaluate_pairs(balanced, "fresh_paired", LANE_NAME, PROTOCOL).efficacy_eligible)
        balanced[1]["lane"] = "boatlee_v16_rc2_market_relay"
        result = evaluate_pairs(balanced, "fresh_paired", LANE_NAME, PROTOCOL)
        self.assertIn("mixed_or_unattributed_incumbent_lane", result.stop_reasons)

    def test_consumed_duplicate_mismatch_and_nonboolean_rows_fail_closed(self):
        consumed_protocol = {**PROTOCOL, "seeds": [42284410], "contexts": [{"seed": 42284410, "family": "Kaito", "context_id": "c1"}]}
        consumed_rows = [wdl_row(0, [0, 1], [1, 0], seed=42284410, terminal_state_changed=True),
                         wdl_row(1, [0, 0], [0, 0], seed=42284410)]
        self.assertIn("nonfresh_evidence", evaluate_pairs(consumed_rows, "fresh_paired", LANE_NAME, consumed_protocol).stop_reasons)
        duplicate = [wdl_row(0, [0, 1], [1, 0], terminal_state_changed=True), wdl_row(0, [0, 1], [1, 0], terminal_state_changed=True), wdl_row(1, [0, 0], [0, 0])]
        self.assertIn("duplicate_matched_context", evaluate_pairs(duplicate, "fresh_paired", LANE_NAME, PROTOCOL).stop_reasons)
        mismatch = [wdl_row(0, [0, 1], [1, 0], terminal_state_changed=True, candidate_outcome="L"), wdl_row(1, [0, 0], [0, 0])]
        self.assertIn("reward_outcome_mismatch", evaluate_pairs(mismatch, "fresh_paired", LANE_NAME, PROTOCOL).stop_reasons)
        nonboolean = [wdl_row(0, [0, 1], [1, 0], terminal_state_changed=1), wdl_row(1, [0, 0], [0, 0])]
        self.assertIn("nonboolean_validity_or_change_flag", evaluate_pairs(nonboolean, "fresh_paired", LANE_NAME, PROTOCOL).stop_reasons)

    def test_boolean_seats_fail_closed_in_protocol_and_rows(self):
        bool_protocol = {**PROTOCOL, "seats": [False, True]}
        rows = [wdl_row(0, [0, 1], [1, 0], terminal_state_changed=True), wdl_row(1, [0, 0], [0, 0])]
        self.assertIn("paired_protocol_not_declared", evaluate_pairs(rows, "fresh_paired", LANE_NAME, bool_protocol).stop_reasons)
        rows[0]["seat"] = False
        self.assertIn("invalid_raw_pair_schema", evaluate_pairs(rows, "fresh_paired", LANE_NAME, PROTOCOL).stop_reasons)

    def test_summary_fixture_never_claims_efficacy(self):
        result = classify_summary_fixture({"id": "c27", "evidence_level": "summary_only", "claimed_wdl": {"wins": 13, "losses": 7}})
        self.assertFalse(result["proposal_rank_signal"])
        self.assertEqual(result["calibration_status"], "blocked_raw_paired_rows_unavailable")
        self.assertFalse(result["efficacy_eligible"])
        mislabeled = classify_summary_fixture({"id": "aggregate", "evidence_level": "fresh_paired", "claimed_wdl": {"wins": 99}})
        self.assertFalse(mislabeled["efficacy_eligible"])

    def test_calibration_rejects_e2_and_missing_raw_rows(self):
        result = calibration()
        self.assertTrue(result["safety_passed"])
        self.assertFalse(result["three_anchor_calibration_passed"])
        self.assertFalse(result["e2"]["efficacy_eligible"])
        self.assertIn("No local raw", result["provenance_gap"])


class RuntimeTests(unittest.TestCase):
    def test_triggered_market_patch_and_market_cap(self):
        spec = sample_branch(); ns = runtime(spec)
        result = ns["agent"](obs(240))
        self.assertEqual(result["market"], [["SELL", "FERTILIZER", 1]])
        self.assertEqual(ns["_FP_STATE"][0]["status"], "complete")

    def test_boolean_or_string_runtime_player_and_step_do_not_trigger(self):
        base = {"farmer": ["PASS"], "hands": [["PASS"]], "market": [["HIRE"]]}
        for changes in ({"player": True}, {"player": "0"}, {"step": True}, {"step": "240"}):
            current = obs(240); current.update(changes)
            ns = runtime(sample_branch())
            self.assertEqual(ns["_fp_apply"](current, base)["market"], [["HIRE"]])
            self.assertTrue(all(state["status"] == "idle" for state in ns["_FP_STATE"].values()))

    def test_ordered_market_insert_is_preserved(self):
        spec = branch(motif={"kind": "market_edit", "patches": [{"step": 240, "market_mode": "insert", "market_index": 0, "market": [["SELL", "FERTILIZER", 1]]}]})
        ns = runtime(spec)
        base = {"farmer": ["PASS"], "hands": [["PASS"]], "market": [["HIRE"]]}
        self.assertEqual(ns["_fp_apply"](obs(240), base)["market"], [["SELL", "FERTILIZER", 1], ["HIRE"]])

    def test_missing_trigger_field_falls_back(self):
        ns = runtime(sample_branch()); current = obs(240); current.pop("market")
        self.assertEqual(ns["agent"](current)["market"], [])

    def test_missing_farms_preserves_incumbent_schema(self):
        ns = runtime(sample_branch()); current = obs(240); current.pop("farms")
        base = {"farmer": ["PASS"], "hands": [["WEST"]], "market": []}
        self.assertEqual(ns["_fp_apply"](current, base)["hands"], [["WEST"]])

    def test_malformed_inactive_fallback_is_projected_to_safe_pass(self):
        ns = runtime(sample_branch())
        base = {"farmer": ["BOGUS"], "hands": [["BOGUS"]], "market": [["BOGUS"]]}
        self.assertEqual(ns["_fp_apply"](obs(1), base), {"farmer": ["PASS"], "hands": [["PASS"]], "market": []})
        self.assertEqual(ns["_FP_STATE"][0]["status"], "technical_failure")

    def test_atomic_plant_projection(self):
        spec = branch(motif={"kind": "action_sequence", "patches": [{"step": 240, "farmer": ["PLANT", "WHEAT"], "actor_actions": [[0, ["PLANT", "WHEAT"]]], "market": []}]})
        result = runtime(spec)["agent"](obs(240, seeds={"WHEAT": 1}))
        self.assertEqual(result["farmer"], ["PASS"]); self.assertEqual(result["hands"], [["PASS"]])

    def test_state_rejoin_and_timeout_failure(self):
        spec = branch(
            continuation={"mode": "state_rejoin", "min_end_step": 241, "max_end_step": 242,
                          "rejoin": {"compatibility_fields": ["market.inventory.FERTILIZER"], "expected": {"market.inventory.FERTILIZER": 5}, "tolerances": {}}},
            max_horizon=3,
            motif={"kind": "market_edit", "patches": [{"step": 240, "market_mode": "preserve", "market": []}]})
        ns = runtime(spec); ns["agent"](obs(240)); ns["agent"](obs(241)); ns["agent"](obs(242)); ns["agent"](obs(243))
        self.assertEqual(ns["_FP_STATE"][0]["status"], "continuation_failure")
        ns = runtime(spec); ns["agent"](obs(240)); current = obs(241); current["market"]["inventory"]["FERTILIZER"] = 5; ns["agent"](current)
        self.assertEqual(ns["_FP_STATE"][0]["status"], "rejoined")

    def test_missing_rejoin_field_and_exception_cancel_branch(self):
        spec = branch(
            continuation={"mode": "state_rejoin", "min_end_step": 241, "max_end_step": 242,
                          "rejoin": {"compatibility_fields": ["market.inventory.FERTILIZER"], "expected": {"market.inventory.FERTILIZER": 5}, "tolerances": {}}},
            max_horizon=3,
            motif={"kind": "market_edit", "patches": [{"step": 240, "market_mode": "preserve", "market": []}]})
        ns = runtime(spec); ns["agent"](obs(240)); current = obs(241); current["market"].pop("inventory"); ns["agent"](current)
        self.assertFalse(ns["_FP_STATE"][0]["active"]); self.assertEqual(ns["_FP_STATE"][0]["status"], "technical_failure")
        bad = branch(trigger={"all": [{"path": "market.prices.FERTILIZER", "op": "in", "value": 1}]})
        ns = runtime(bad); ns["agent"](obs(240))
        self.assertFalse(ns["_FP_STATE"][0]["active"]); self.assertEqual(ns["_FP_STATE"][0]["status"], "technical_failure")

    def test_invalid_runtime_patch_falls_back_to_incumbent(self):
        spec = branch(motif={"kind": "action_sequence", "patches": [{"step": 240, "farmer": ["BOGUS"], "market": []}]})
        ns = runtime(spec)
        self.assertEqual(ns["agent"](obs(240))["farmer"], ["PASS"])

    def test_partial_motif_failure_cancels_later_patches(self):
        spec = branch(
            continuation={"mode": "fixed", "min_end_step": 240, "max_end_step": 241, "rejoin": {}}, max_horizon=2,
            motif={"kind": "action_sequence", "patches": [
                {"step": 240, "actor_actions": [[9, ["WEST"]]], "market": []},
                {"step": 241, "market_mode": "append", "market": [["SELL", "FERTILIZER", 1]]},
            ]})
        ns = runtime(spec); ns["agent"](obs(240)); later = ns["agent"](obs(241))
        self.assertEqual(ns["_FP_STATE"][0]["status"], "technical_failure"); self.assertEqual(later["market"], [])

    def test_market_overflow_and_missing_plant_ledger_cancel(self):
        append = branch(motif={"kind": "market_edit", "patches": [{"step": 240, "market_mode": "append", "market": [["HIRE"]]}]})
        ns = runtime(append); base = {"farmer": ["PASS"], "hands": [["PASS"]], "market": [["HIRE"] for _ in range(10)]}
        self.assertEqual(ns["_fp_apply"](obs(240), base)["market"], base["market"]); self.assertEqual(ns["_FP_STATE"][0]["status"], "technical_failure")
        plant = branch(motif={"kind": "action_sequence", "patches": [{"step": 240, "farmer": ["PLANT", "WHEAT"], "market": []}]})
        ns = runtime(plant); result = ns["agent"](obs(240, seeds={}))
        self.assertEqual(result["farmer"], ["PASS"]); self.assertEqual(ns["_FP_STATE"][0]["status"], "technical_failure")

    def test_incumbent_exception_is_single_call_safe_fallback(self):
        ns = runtime(sample_branch()); calls = []
        def explode(*args):
            calls.append(args); raise RuntimeError("boom")
        ns["_FP_BASE_AGENT"] = explode
        result = ns["agent"](obs(240))
        self.assertEqual(len(calls), 1); self.assertEqual(result, {"farmer": ["PASS"], "hands": [["PASS"]], "market": []})
        self.assertEqual(ns["_FP_STATE"][0]["status"], "technical_failure")

    def test_seat_relative_public_path_resolves(self):
        spec = branch(trigger={"all": [{"path": "own_farm.money", "op": "ge", "value": 5}]})
        current = obs(240); current["farms"][0]["money"] = 10
        self.assertEqual(runtime(spec)["agent"](current)["market"], [["SELL", "FERTILIZER", 1]])

    def test_rewind_resets_seat_local_state(self):
        ns = runtime(sample_branch()); ns["agent"](obs(240)); ns["agent"](obs(0))
        self.assertEqual(ns["_FP_STATE"][0]["status"], "reset")
        self.assertEqual(ns["_FP_STATE"][1]["status"], "idle")


class IntegrationTests(unittest.TestCase):
    def test_canonical_text_fingerprint_is_eol_independent(self):
        self.assertEqual(canonical_utf8_lf(b"a\r\nb\r\n"), b"a\nb\n")
        with tempfile.TemporaryDirectory() as temporary:
            left = Path(temporary) / "left.txt"; right = Path(temporary) / "right.txt"
            left.write_bytes(b"a\r\nb\r\n"); right.write_bytes(b"a\nb\n")
            self.assertEqual(fingerprint(left, "canonical_utf8_lf")["sha256"],
                             fingerprint(right, "canonical_utf8_lf")["sha256"])

    def test_registry_is_frozen(self):
        result = validate_registry()
        self.assertTrue(result["passed"])
        self.assertTrue(all(result["registry_contract"].values()))
        self.assertEqual(result["collections"]["atlas_inputs"]["file_count"], 451)
        self.assertTrue(result["collections"]["atlas_inputs"]["passed"])
        topology = next(row for row in result["sources"] if row["id"] == "user_expected_architecture")
        self.assertEqual(topology["fingerprint_mode"], "canonical_utf8_lf")
        self.assertEqual(topology["actual_bytes"], 9122)

    def test_source_inventory_is_stable_and_excludes_summary(self):
        inventory = source_inventory()
        self.assertRegex(inventory["sha256"], r"^[0-9a-f]{64}$")
        self.assertFalse(any(row["path"].endswith("development_verification_summary.json") for row in inventory["files"]))
        with tempfile.TemporaryDirectory(dir=LANE) as temporary:
            (Path(temporary) / "ignored-candidate.py").write_text("def agent(obs): return {}\n", encoding="utf-8")
            self.assertEqual(source_inventory()["sha256"], inventory["sha256"])

    def test_compiler_is_standalone_and_under_package_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "main.py"
            result = compile_candidate(sample_branch(), path)
            self.assertTrue(result["static_audit"]["passed"])
            self.assertLess(result["bytes"], 5 * 1024 * 1024)
            self.assertNotIn("pathlib", static_audit(path)["imports"])

    def test_compiled_public_entrypoint_rejects_boolean_and_string_observation_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "main.py"
            compile_candidate(sample_branch(), path)
            loaded = importlib.util.spec_from_file_location("compiled_identity_probe", path)
            self.assertIsNotNone(loaded); self.assertIsNotNone(loaded.loader)
            module = importlib.util.module_from_spec(loaded)
            loaded.loader.exec_module(module)
            base = {"farmer": ["PASS"], "hands": [["PASS"]], "market": [["HIRE"]]}
            module._FP_BASE_AGENT = lambda *args: base
            for changes in ({"player": True}, {"player": "0"}, {"step": True}, {"step": "240"}):
                current = obs(240); current.update(changes)
                self.assertEqual(module._kaggle_submission_entrypoint(current)["market"], [["HIRE"]])

    def test_compiler_rejects_malformed_actions_unreachable_patch_and_parent(self):
        cases = [
            branch(motif={"kind": "action_sequence", "patches": [{"step": 240, "farmer": ["BOGUS"], "market": []}]}),
            branch(motif={"kind": "market_edit", "patches": [{"step": 240, "market_mode": "replace", "market": [["SELL", "FERTILIZER", 0]]}]}),
            branch(motif={"kind": "market_edit", "patches": [{"step": 240, "market_mode": "replace", "market": [["BOGUS"]]}]}),
            branch(motif={"kind": "market_edit", "patches": [{"step": 241, "market_mode": "preserve", "market": []}]}),
            branch(parent_node_id=f"{LANE_NAME}:spine:999"),
            branch(evidence_ids=("boatlee_incumbent",)),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            for index, spec in enumerate(cases):
                with self.subTest(index=index), self.assertRaises(ValueError):
                    compile_candidate(spec, Path(temporary) / f"{index}.py")

    def test_compiler_rejects_unknown_fields_duplicate_steps_and_boolean_patch_integers(self):
        cases = [
            branch(motif={"kind": "market_edit", "patches": [{"step": 240, "market": []}], "ignored": True}),
            branch(motif={"kind": "market_edit", "patches": [{"step": 240, "market": [], "ignored": True}]}),
            branch(motif={"kind": "market_edit", "patches": [{"step": 240, "market": []}, {"step": 240, "market": []}]}),
            branch(motif={"kind": "action_sequence", "patches": [{"step": True, "market": []}]}),
            branch(motif={"kind": "action_sequence", "patches": [{"step": 240, "actor_actions": [[False, ["PASS"]]], "market": []}]}),
            branch(motif={"kind": "action_sequence", "patches": [{"step": 240, "market_mode": "preserve", "market": [["HIRE"]]}]}),
            branch(motif={"kind": "action_sequence", "patches": [{"step": 240, "market_mode": "append", "market_index": 0, "market": [["HIRE"]]}]}),
            branch(motif={"kind": "market_edit", "patches": [{"step": 240, "farmer": ["PASS"], "market": []}]}),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            for index, spec in enumerate(cases):
                with self.subTest(index=index), self.assertRaises(ValueError):
                    compile_candidate(spec, Path(temporary) / f"closed-{index}.py")

    def test_compiler_rejects_protected_incumbent_and_evidence_outputs(self):
        protected = [
            compiler_module.INCUMBENTS[LANE_NAME],
            compiler_module.ROOT / "research/dual_incumbent_topology_search_2026-08-14/e2/forbidden.py",
        ]
        before = hashlib.sha256(compiler_module.INCUMBENTS[LANE_NAME].read_bytes()).hexdigest()
        for output in protected:
            with self.subTest(output=output), self.assertRaises(ValueError):
                compile_candidate(sample_branch(), output)
        self.assertEqual(hashlib.sha256(compiler_module.INCUMBENTS[LANE_NAME].read_bytes()).hexdigest(), before)

    def test_compiler_and_technical_evaluator_enforce_size_limit(self):
        huge = branch(trigger={"all": [{"path": "market.prices.FERTILIZER", "op": "eq", "value": "x" * MAX_CANDIDATE_BYTES}]})
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate.py"
            with self.assertRaises(ValueError):
                compile_candidate(huge, output)
            output.write_bytes(b"#" * MAX_CANDIDATE_BYTES)
            result = technical_evaluate(output)
            self.assertFalse(result["passed"]); self.assertFalse(result["size_passed"])

    def test_compiler_revalidates_incumbent_and_does_not_publish_failed_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); drift = root / "drift.py"; drift.write_text("def agent(obs): return {}\n", encoding="utf-8")
            output = root / "candidate.py"
            with mock.patch.dict(compiler_module.INCUMBENTS, {LANE_NAME: drift}), self.assertRaises(ValueError):
                compile_candidate(sample_branch(), output)
            self.assertFalse(output.exists())
            with mock.patch.object(compiler_module, "RUNTIME_SOURCE", RUNTIME_SOURCE + "\nimport requests\n"), self.assertRaises(ValueError):
                compile_candidate(sample_branch(), output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
