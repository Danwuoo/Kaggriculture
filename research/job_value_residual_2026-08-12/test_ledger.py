"""Conservation and public-only contracts for counterfactual value labels."""

from __future__ import annotations

from dataclasses import replace
import json
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
        context_a = ("v27_current_meta", "kaito_v21", 1, 0)
        context_b = ("v27_current_meta", "kaito_v21", 2, 0)
        first = HorizonEffect(24, 2.0, (("MILK", 2, "cargo"),), (), (), (), context_a)
        second = HorizonEffect(24, 4.0, (("MILK", 4, "cargo"),), (), (), (), context_b)
        self.assertEqual((HorizonEffect(24, 3.0, (("MILK", 3, "cargo"),), (), (), ()),), stable_median_effect((first, second)))
        self.assertIsNone(stable_median_effect((first, replace(second, context=context_a))))
        self.assertIsNone(stable_median_effect((first, replace(second, cash_coins=-4.0, liquidatable=(("MILK", -4, "cargo"),)))))

    def test_capacity_bucket_requires_runner_recorded_unambiguous_inflight(self):
        window = candidate_fixture()
        context = ("v27_current_meta", "kaito_v21", 1, 0)
        control = [{"step": step, "context": context, "observation": observation_fixture(step=step), "action": {"market": []}, "market_receipts": (), "capacity_certification": "no_certified_capacity_inflight"} for step in (10, 34, 58)]
        candidate = [dict(row) for row in control]
        candidate[1] = {**candidate[1], "capacity_inflight": (("MILK", 2, "capacity:hand:1"),), "capacity_certification": "certified_capacity_inflight"}
        effects = derive_horizon_effects(control, candidate, window)
        self.assertEqual((("MILK", 2, "capacity:hand:1"),), effects[0].capacity)
        candidate[1] = {**candidate[1], "capacity_inflight": (("MILK", 2, "same"), ("MILK", 1, "same"))}
        self.assertIsNone(derive_horizon_effects(control, candidate, window))

    def test_shift_uses_realized_per_unit_receipts_not_pre_action_quote(self):
        from schema import SellDirective

        window = replace(candidate_fixture(), sell_directives=(SellDirective(0, "MILK", 2),))
        context = ("v27_current_meta", "kaito_v21", 6, 0)
        def frame(step, *, action=None, receipts=(), money=3000):
            obs = observation_fixture(step=step)
            obs["farms"][0]["money"] = money
            return {"step": step, "context": context, "observation": obs, "action": action or {"market": []}, "market_receipts": receipts, "capacity_certification": "no_certified_capacity_inflight"}
        control = [
            frame(10, action={"market": [["SELL", "MILK", 2]]}, receipts=((10, "MILK", 20.0), (10, "MILK", 19.0))),
            frame(34), frame(58),
        ]
        candidate = [
            frame(10),
            frame(11, action={"market": [["SELL", "MILK", 2]]}, receipts=((11, "MILK", 25.0), (11, "MILK", 24.0))),
            frame(34, money=3010), frame(58, money=3010),
        ]
        effects = derive_horizon_effects(control, candidate, window)
        self.assertEqual(2, len(effects[0].market))
        self.assertEqual(39.0, sum(item.control_receipt for item in effects[0].market))
        self.assertEqual(49.0, sum(item.candidate_receipt for item in effects[0].market))
        self.assertEqual(0.0, effects[0].cash_coins)

    def test_same_step_retained_unit_is_not_prorated_into_shift(self):
        from schema import SellDirective

        window = replace(candidate_fixture(), sell_directives=(SellDirective(0, "MILK", 2),))
        context = ("v27_current_meta", "kaito_v21", 7, 0)
        def frame(step, action, receipts, money):
            obs = observation_fixture(step=step)
            obs["farms"][0]["money"] = money
            return {"step": step, "context": context, "observation": obs, "action": action, "market_receipts": receipts, "capacity_certification": "no_certified_capacity_inflight"}
        control = [frame(10, {"market": [["SELL", "MILK", 2]]}, ((10, "MILK", 20.0), (10, "MILK", 19.0)), 3000), frame(34, {"market": []}, (), 3000), frame(58, {"market": []}, (), 3000)]
        candidate = [frame(10, {"market": [["SELL", "MILK", 1]]}, ((10, "MILK", 25.0),), 3000), frame(11, {"market": [["SELL", "MILK", 1]]}, ((11, "MILK", 24.0),), 3000), frame(34, {"market": []}, (), 3010), frame(58, {"market": []}, (), 3010)]
        effects = derive_horizon_effects(control, candidate, window)
        self.assertEqual(1, len(effects[0].market))
        self.assertEqual((19.0, 24.0), (effects[0].market[0].control_receipt, effects[0].market[0].candidate_receipt))
        self.assertEqual(5.0, effects[0].market[0].candidate_receipt - effects[0].market[0].control_receipt)
        self.assertEqual(5.0, effects[0].cash_coins)

    def test_effect_refuses_missing_or_mismatched_paired_context(self):
        window = candidate_fixture()
        context = ("v27_current_meta", "kaito_v21", 7, 0)
        def frame(step, identity):
            return {"step": step, "context": identity, "observation": observation_fixture(step=step), "action": {"market": []}, "market_receipts": (), "capacity_certification": "no_certified_capacity_inflight"}
        control = [frame(step, context) for step in (10, 34, 58)]
        self.assertIsNone(derive_horizon_effects(control, [frame(step, None) for step in (10, 34, 58)], window))
        boatlee = ("boatlee_v16_rc2_market_relay", "kaito_v21", 7, 0)
        self.assertIsNone(derive_horizon_effects(control, [frame(step, boatlee) for step in (10, 34, 58)], window))

    def test_json_string_round_trip_normalizes_tuple_requirement_values(self):
        from schema import Requirement, from_json, to_json
        from forced_policy import requirements_hold

        window = replace(candidate_fixture(), requirements=(
            Requirement("actor_position", (1,), "eq", (1, 1)),
            Requirement("tile_yield", (2, 1), "ge", 1),
        ))
        restored = from_json(json.loads(json.dumps(to_json(window))))
        self.assertEqual(window, restored)
        obs = observation_fixture(step=10, hands=1, hand_positions=[(1, 1)])
        obs["farms"][0]["tiles"][1][2] = {"kind": "PLANT", "yield_units": 1}
        self.assertTrue(requirements_hold(restored, obs))

    def test_public_inbound_rekeys_when_identified_actor_moves(self):
        before = observation_fixture(step=100)
        before["farms"][1]["hands"] = [[2, 1]]
        before["farms"][1]["tiles"][1][2] = {"kind": "PASTURE", "animal": "COW", "yield_units": 3}
        state = update_public_inbound({}, before, 0)
        harvest = observation_fixture(step=101)
        harvest["farms"][1]["hands"] = [[2, 1]]
        harvest["farms"][1]["tiles"][1][2] = {"kind": "PASTURE", "animal": "COW", "yield_units": 2}
        state = update_public_inbound(state, harvest, 0)
        moved = observation_fixture(step=102)
        moved["farms"][1]["hands"] = [[3, 1]]
        moved["farms"][1]["tiles"][1][2] = {"kind": "PASTURE", "animal": "COW", "yield_units": 2}
        state = update_public_inbound(state, moved, 0)
        self.assertNotIn("1:(2, 1)", state["bounds"])
        self.assertEqual(1, state["bounds"]["1:(3, 1)"]["MILK"])


if __name__ == "__main__":
    unittest.main()
