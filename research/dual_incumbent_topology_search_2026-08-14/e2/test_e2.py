from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from authority import HERE, reconstruct_registered, verify_authority
from effective_change import BOATLEE_ID, NOOP_ID, V27_PROBE_ID, classify_result, effective_change_audit
from selector import SELECTORS, apply_selector, decision, development_hypothesis, write_selector


def evidence(action: str, receipt: str, state: str, diagnostics: dict | None = None) -> dict:
    return {"action_digest": action, "receipt_digest": receipt, "state_digest": state, "economic_diagnostics": diagnostics or {}}


class AuthorityTests(unittest.TestCase):
    def test_registry_and_committed_authority_match(self) -> None:
        report = verify_authority()
        self.assertTrue(report["pass"], report)

    def test_registered_candidates_reconstruct_exactly(self) -> None:
        rows = reconstruct_registered()
        self.assertTrue(all(row["pass"] for row in rows.values()), rows)


class EffectiveChangeTests(unittest.TestCase):
    def test_action_only_cancelled_or_truncated_edit_is_not_effective(self) -> None:
        result = {
            "evidence": evidence("candidate", "same", "same"),
            "control": {"evidence": evidence("control", "same", "same"), "own_reward": 1, "opponent_reward": 2, "own_bank": 1, "opponent_bank": 2},
            "own_reward": 1, "opponent_reward": 2, "own_bank": 1, "opponent_bank": 2,
        }
        row = classify_result("syntactic", result)
        self.assertTrue(row["action_only_noop"])
        self.assertFalse(row["effective"])
        self.assertFalse(row["efficacy_eligible"])

    def test_receipt_state_bank_or_diagnostic_change_is_effective(self) -> None:
        for field in ("receipt", "state", "bank", "diagnostic"):
            candidate = evidence("same", "r1" if field == "receipt" else "r0", "s1" if field == "state" else "s0", {"x": 1} if field == "diagnostic" else {})
            result = {"evidence": candidate, "control": {"evidence": evidence("same", "r0", "s0"), "own_reward": 1, "opponent_reward": 2, "own_bank": 1, "opponent_bank": 2}, "own_reward": 1, "opponent_reward": 2, "own_bank": 3 if field == "bank" else 1, "opponent_bank": 2}
            self.assertTrue(classify_result("candidate", result)["effective"], field)

    def test_frozen_noop_is_excluded_and_registered_findings_remain_effective(self) -> None:
        report = effective_change_audit()
        self.assertTrue(report["pass"], report)
        self.assertIn(NOOP_ID, report["frontiers"]["excluded"])
        self.assertIn(BOATLEE_ID, report["frontiers"]["robust"])
        self.assertIn(V27_PROBE_ID, report["frontiers"]["diagnostic_high_upside"])
        self.assertEqual([], report["frontiers"]["selector_labels"])


class SelectorTests(unittest.TestCase):
    def observation(self, *, step: int = 494, price: int = 48, inventory: int = 9450, player: int = 0) -> dict:
        farm = {"money": 3000, "hands": [], "unlocked_quadrants": ["NW"]}
        return {
            "player": player, "step": step, "farms": [dict(farm), dict(farm)],
            "market": {"prices": {"WHEAT": price}, "inventory": {"WHEAT": inventory}},
            "town": {"unlocked_shops": []},
        }

    def base_action(self) -> dict:
        return {"farmer": ["PASS"], "hands": [], "market": [["BUY_PRODUCT", "WHEAT", 2]]}

    def test_public_threshold_exercises_both_branches(self) -> None:
        spec = SELECTORS[0]
        self.assertEqual("suppress_buy", decision(spec, self.observation(), self.base_action())[0])
        self.assertEqual(
            "incumbent",
            decision(spec, self.observation(price=45, inventory=9583), self.base_action())[0],
        )
        selected = apply_selector(spec, self.observation(), self.base_action())
        self.assertEqual([], selected["action"]["market"])

    def test_missing_late_or_absent_precondition_falls_back(self) -> None:
        spec = SELECTORS[0]
        self.assertEqual("incumbent", decision(spec, {"player": 0, "step": 494}, self.base_action())[0])
        self.assertEqual("incumbent", decision(spec, self.observation(step=495), self.base_action())[0])
        absent = {**self.base_action(), "market": []}
        self.assertEqual("incumbent", decision(spec, self.observation(), absent)[0])

    def test_selector_contract_is_public_frozen_and_matches_registry(self) -> None:
        self.assertLessEqual(len(SELECTORS), 2)
        spec = SELECTORS[0]
        hypothesis = development_hypothesis()
        self.assertTrue(hypothesis["pass"])
        self.assertFalse(hypothesis["opponent_identity_used"])
        self.assertFalse(hypothesis["private_opponent_information_used"])
        self.assertIsNone(spec.payload()["efficacy_claim"])
        self.assertTrue(all("private" not in feature and "opponent_identity" not in feature for feature in spec.payload()["features"]))
        registry = json.loads((HERE / "development_candidate_registry.json").read_text(encoding="utf-8"))
        self.assertEqual(spec.candidate_id, registry["lanes"]["v27_current_meta"]["candidate_id"])

    def test_materialized_selector_contains_no_runtime_filesystem_dependency(self) -> None:
        spec = SELECTORS[0]
        base = (HERE.parents[1] / "main_approach" / "v27_current_meta" / "main.py").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "main.py"
            artifact = write_selector(base, spec, output)
            source = output.read_text(encoding="utf-8")
            self.assertEqual(spec.candidate_id, artifact["candidate_id"])
            self.assertNotIn("pathlib", source.lower())
            self.assertNotIn("subprocess", source.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
