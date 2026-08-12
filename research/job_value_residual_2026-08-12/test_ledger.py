"""Conservation and public-only contracts for counterfactual value labels."""

from __future__ import annotations

import unittest

from ledger import LedgerBreakdown, derive_horizon_effects, stable_median_effect, update_public_inbound, value_effect
from schema import HorizonEffect, MarketShift
from test_support import candidate_fixture, observation_fixture


class LedgerTests(unittest.TestCase):
    def test_components_do_not_double_count_product_units(self):
        effect = HorizonEffect(
            horizon=24,
            cash_coins=100.0,
            liquidatable=(("MILK", 3, "cargo-a"),),
            asset=(("WOOL", -4, "asset-b"),),
            capacity=(("STRAWBERRY", 2, "inflight-c"),),
            market=(MarketShift("MILK", 1, 4, 1, "sale-d"),),
        )
        result = value_effect(
            effect,
            {"MILK": 20, "WOOL": 10, "STRAWBERRY": 30},
            {"sale-d": 7.0},
        )
        self.assertEqual(LedgerBreakdown(100.0, 60.0, -40.0, 60.0, 7.0), result)
        self.assertEqual(187.0, result.total)

    def test_duplicate_provenance_is_rejected(self):
        effect = HorizonEffect(24, 0.0, (("MILK", 1, "same"),), (), (("MILK", 1, "same"),), ())
        self.assertIsNone(value_effect(effect, {"MILK": 20}, {}))

    def test_missing_quote_is_unknown(self):
        effect = HorizonEffect(24, 0.0, (("MILK", 1, "cargo"),), (), (), ())
        self.assertIsNone(value_effect(effect, {}, {}))

    def test_opponent_private_field_cannot_change_inbound_tracker(self):
        state_a = update_public_inbound({}, observation_fixture(step=100), 0)
        obs = observation_fixture(step=100)
        obs["opponent_private"] = {"shed": {"MILK": 999999}}
        state_b = update_public_inbound({}, obs, 0)
        self.assertEqual(state_a, state_b)

    def test_public_harvest_is_conservatively_inferred(self):
        before = observation_fixture(step=100)
        before["farms"][1]["hands"] = [[2, 1]]
        before["farms"][1]["tiles"][1][2] = {"kind": "PASTURE", "animal": "COW", "yield_units": 3}
        state = update_public_inbound({}, before, 0)
        after = observation_fixture(step=101)
        after["farms"][1]["hands"] = [[2, 1]]
        after["farms"][1]["tiles"][1][2] = {"kind": "PASTURE", "animal": "COW", "yield_units": 1}
        state = update_public_inbound(state, after, 0)
        self.assertEqual(2, state["bounds"]["1:(2, 1)"]["MILK"])

    def test_derive_rejects_unconserved_shift(self):
        from dataclasses import replace
        from schema import SellDirective

        window = replace(candidate_fixture(), sell_directives=(SellDirective(0, "MILK", 1),))
        control = [
            {"step": 10, "observation": observation_fixture(step=10), "action": {"market": []}},
            {"step": 14, "observation": observation_fixture(step=14), "action": {"market": []}},
            {"step": 34, "observation": observation_fixture(step=34), "action": {"market": []}},
            {"step": 58, "observation": observation_fixture(step=58), "action": {"market": []}},
        ]
        candidate = [dict(item) for item in control]
        candidate[0] = {**candidate[0], "action": {"market": [["SELL", "MILK", 1]]}}
        self.assertIsNone(derive_horizon_effects(control, candidate, window))

    def test_effect_aggregation_requires_same_buckets_and_signs(self):
        first = HorizonEffect(24, 2.0, (("MILK", 2, "cargo"),), (), (), ())
        second = HorizonEffect(24, 4.0, (("MILK", 4, "cargo"),), (), (), ())
        self.assertEqual((HorizonEffect(24, 3.0, (("MILK", 3, "cargo"),), (), (), ()),), stable_median_effect((first, second)))
        self.assertIsNone(stable_median_effect((first, HorizonEffect(24, -4.0, (("MILK", -4, "cargo"),), (), (), ()))))


if __name__ == "__main__":
    unittest.main()
