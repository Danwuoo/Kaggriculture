from __future__ import annotations

import unittest

from boatlee_selector import (
    BoatleeSelectorSpec,
    CONTROL_STEP_240,
    CONTROL_STEP_241,
    INTERVENTION_STEP_241,
    apply_selector,
    decision,
)


def observation(step: int, *, price: int = 84, inventory: int = 10082, player: int = 0) -> dict:
    return {
        "step": step, "player": player,
        "farms": [{"hands": []}, {"hands": []}],
        "market": {"prices": {"FERTILIZER": price}, "inventory": {"FERTILIZER": inventory}},
    }


class BoatleeSelectorTests(unittest.TestCase):
    def test_public_surplus_rule_and_boundaries(self) -> None:
        spec = BoatleeSelectorSpec()
        base = {"farmer": ["PASS"], "hands": [], "market": CONTROL_STEP_240}
        self.assertEqual("intervene", decision(spec, observation(240), base)[0])
        self.assertEqual("incumbent", decision(spec, observation(240, price=85), base)[0])
        self.assertEqual("incumbent", decision(spec, observation(240, inventory=10081), base)[0])
        self.assertEqual("incumbent", decision(spec, observation(239), base)[0])

    def test_branch_is_delayed_and_rejoins(self) -> None:
        spec = BoatleeSelectorSpec()
        state = {"last_step": -1, "branch": "incumbent"}
        base_240 = {"farmer": ["PASS"], "hands": [], "market": CONTROL_STEP_240}
        first = apply_selector(spec, observation(240), base_240, state)
        self.assertEqual(CONTROL_STEP_240, first["action"]["market"])
        self.assertEqual("intervene", first["branch"])
        base_241 = {"farmer": ["PASS"], "hands": [], "market": CONTROL_STEP_241}
        second = apply_selector(spec, observation(241), base_241, state)
        self.assertEqual(INTERVENTION_STEP_241, second["action"]["market"])
        base_242 = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertEqual([], apply_selector(spec, observation(242), base_242, state)["action"]["market"])

    def test_missing_or_changed_precondition_falls_back_and_rewind_resets(self) -> None:
        spec = BoatleeSelectorSpec()
        state = {"last_step": -1, "branch": "incumbent"}
        changed = {"farmer": ["PASS"], "hands": [], "market": []}
        self.assertEqual("incumbent", apply_selector(spec, observation(240), changed, state)["branch"])
        state.update({"last_step": 241, "branch": "intervene"})
        result = apply_selector(spec, observation(100), changed, state)
        self.assertEqual("incumbent", result["branch"])
        self.assertEqual(100, state["last_step"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
