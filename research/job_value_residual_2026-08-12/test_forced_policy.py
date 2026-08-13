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

    def test_full_market_queue_rejects_extra_sell_without_mutating_base_orders(self):
        window = replace(
            candidate_fixture(),
            actions=(("DROP",), ("PASS",), ("PASS",), ("PASS",)),
            expected_positions=((4, 4),) * 5,
            sell_directives=(SellDirective(0, "MILK", 1),),
        )

        def full_market(obs, configuration=None):
            result = base_policy(obs)
            result["market"] = [["SELL", "WHEAT", 1] for _ in range(10)]
            return result

        obs = observation_fixture(step=10, hands=1, hand_positions=[(4, 4)])
        obs["private"]["shed"]["MILK"] = 1
        wrapped = make_forced_factory(window)(object(), full_market, 0)
        changed = wrapped(obs)
        self.assertEqual(10, len(changed["market"]))
        self.assertTrue(wrapped.metadata["sell_rejected"])
        self.assertEqual("market_cap", wrapped.metadata["sell_rejected_reason"])

    def test_interior_first_call_and_step_gap_abort_fail_closed(self):
        window = candidate_fixture()
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        interior = observation_fixture(step=11, hands=1, hand_positions=[(2, 1)])
        self.assertEqual(base_policy(interior), wrapped(interior))
        self.assertEqual("interior_start", wrapped.metadata["abort_reason"])
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        wrapped(observation_fixture(step=10, hands=1, hand_positions=[(1, 1)]))
        gap = observation_fixture(step=12, hands=1, hand_positions=[(2, 1)])
        self.assertEqual(base_policy(gap), wrapped(gap))
        self.assertEqual("step_gap", wrapped.metadata["abort_reason"])

    def test_rejoin_rejects_missing_forced_offsets(self):
        window = candidate_fixture()
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        wrapped(observation_fixture(step=10, hands=1, hand_positions=[(1, 1)]))
        rejoin = observation_fixture(step=14, hands=1, hand_positions=[(1, 1)])
        self.assertEqual(base_policy(rejoin), wrapped(rejoin))
        self.assertEqual("aborted", wrapped.metadata["status"])
        self.assertEqual("step_gap", wrapped.metadata["abort_reason"])
        self.assertEqual(14, wrapped.metadata["abort_step"])

    def test_retirement_needs_same_actor_product_and_same_mutated_tile(self):
        inventory = replace(
            candidate_fixture(),
            actions=(("DROP",), ("PASS",), ("PASS",), ("PASS",)),
            expected_positions=((4, 4),) * 5,
            requirements=(
                Requirement("actor_inventory", (1, "MILK"), "ge", 1),
                Requirement("actor_inventory", (0, "WOOL"), "ge", 1),
            ),
        )
        wrapped = make_forced_factory(inventory)(object(), base_policy, 0)
        start = observation_fixture(step=10, hands=1, hand_positions=[(4, 4)])
        start["private"]["inventories"][1]["MILK"] = 1
        start["private"]["inventories"][0]["WOOL"] = 1
        wrapped(start)
        later = observation_fixture(step=11, hands=1, hand_positions=[(4, 4)])
        later["private"]["inventories"][0]["WOOL"] = 0
        self.assertEqual(base_policy(later), wrapped(later))
        self.assertEqual("actor_inventory:0:WOOL", wrapped.metadata["failed_precondition"])

    def test_apply_actor_action_copies_all_action_lists(self):
        action = {"farmer": ["PASS"], "hands": [["PASS"]], "market": [["SELL", "MILK", 1]]}
        changed = apply_actor_action(action, 1, ("EAST",))
        changed["market"][0][2] = 99
        self.assertEqual(1, action["market"][0][2])


if __name__ == "__main__":
    unittest.main()
