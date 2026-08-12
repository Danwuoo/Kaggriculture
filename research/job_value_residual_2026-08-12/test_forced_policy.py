"""Fail-closed contracts for one-window incumbent counterfactuals."""

from __future__ import annotations

from dataclasses import replace
import unittest

from forced_policy import apply_actor_action, make_forced_factory, requirements_hold
from schema import Requirement, SellDirective
from test_support import base_policy, candidate_fixture, observation_fixture


class ForcedPolicyTests(unittest.TestCase):
    def test_only_declared_actor_changes(self):
        window = candidate_fixture()
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        obs = observation_fixture(step=10, hands=2, hand_positions=[(1, 1), (3, 3)])
        base = base_policy(obs)
        changed = wrapped(obs)
        self.assertEqual(base["farmer"], changed["farmer"])
        self.assertEqual(list(window.actions[0]), changed["hands"][0])
        self.assertEqual(base["hands"][1], changed["hands"][1])

    def test_failed_midwindow_precondition_aborts_without_extension(self):
        window = candidate_fixture()
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        wrapped(observation_fixture(step=10, hands=1, hand_positions=[(1, 1)]))
        changed = observation_fixture(step=11, hands=0)
        self.assertEqual(base_policy(changed), wrapped(changed))
        self.assertEqual("aborted", wrapped.metadata["status"])
        self.assertEqual(11, wrapped.metadata["abort_step"])

    def test_rejoin_is_checked_and_never_overrides_after_window(self):
        window = candidate_fixture()
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        for step, position in ((10, (1, 1)), (11, (2, 1)), (12, (2, 1)), (13, (1, 1))):
            wrapped(observation_fixture(step=step, hands=1, hand_positions=[position]))
        rejoin = observation_fixture(step=14, hands=1, hand_positions=[(1, 1)])
        self.assertEqual(base_policy(rejoin), wrapped(rejoin))
        self.assertEqual("rejoined", wrapped.metadata["status"])
        later = observation_fixture(step=15, hands=1, hand_positions=[(1, 1)])
        self.assertEqual(base_policy(later), wrapped(later))

    def test_sell_uses_only_pre_action_shed_and_declared_drop(self):
        window = replace(
            candidate_fixture(),
            actions=(("DROP",), ("PASS",), ("PASS",), ("PASS",)),
            expected_positions=((4, 4), (4, 4), (4, 4), (4, 4), (4, 4)),
            sell_directives=(SellDirective(0, "MILK", 3),),
        )
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        obs = observation_fixture(step=10, hands=1, hand_positions=[(4, 4)])
        obs["private"]["shed"]["MILK"] = 1
        obs["private"]["inventories"][1]["MILK"] = 2
        self.assertEqual([["SELL", "MILK", 3]], wrapped(obs)["market"])
        self.assertEqual(3, wrapped.metadata["applied_sell_quantity"])

    def test_requirement_evaluation_is_fail_closed(self):
        window = replace(
            candidate_fixture(),
            requirements=(Requirement("tile_yield", (2, 1), "ge", 1),),
        )
        self.assertFalse(requirements_hold(window, observation_fixture(step=10)))
        obs = observation_fixture(step=10)
        obs["farms"][0]["tiles"][1][2] = {"kind": "PLANT", "yield_units": 1}
        self.assertTrue(requirements_hold(window, obs))

    def test_consumed_delivery_requirement_does_not_self_abort_after_drop(self):
        window = replace(
            candidate_fixture(),
            actions=(("DROP",), ("PASS",), ("PASS",), ("PASS",)),
            expected_positions=((4, 4),) * 5,
            requirements=(Requirement("actor_inventory", (1, "MILK"), "ge", 1),),
        )
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        for step in range(10, 14):
            obs = observation_fixture(step=step, hands=1, hand_positions=[(4, 4)])
            if step == 10:
                obs["private"]["inventories"][1]["MILK"] = 1
            wrapped(obs)
        self.assertEqual([10, 11, 12, 13], wrapped.metadata["applied_steps"])

    def test_apply_actor_action_copies_all_action_lists(self):
        action = {"farmer": ["PASS"], "hands": [["PASS"]], "market": [["SELL", "MILK", 1]]}
        changed = apply_actor_action(action, 1, ("EAST",))
        changed["market"][0][2] = 99
        self.assertEqual(1, action["market"][0][2])


if __name__ == "__main__":
    unittest.main()
