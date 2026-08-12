"""Contracts for deterministic bounded job-window discovery."""

from __future__ import annotations

from dataclasses import replace
import unittest

from engine_runner import TraceFrame
from schema import CandidateWindow, SellDirective, from_json, to_json
from test_support import candidate_fixture, observation_fixture
from window_search import mine_candidates, shortest_actions, validate_window


class WindowSearchTests(unittest.TestCase):
    def test_shortest_path_is_deterministic(self):
        self.assertEqual(("EAST", "EAST", "SOUTH"), shortest_actions((0, 0), (2, 1)))

    def test_shortest_path_clamps_out_of_bounds_endpoints(self):
        self.assertEqual(("EAST", "SOUTH"), shortest_actions((-1, -1), (1, 1)))

    def test_window_is_one_actor_four_to_eight_turns_and_rejoins(self):
        window = candidate_fixture()
        errors = validate_window(window)
        self.assertEqual([], errors)
        self.assertGreaterEqual(len(window.actions), 4)
        self.assertLessEqual(len(window.actions), 8)
        self.assertEqual(window.rejoin_step, window.trigger_step + len(window.actions))
        self.assertEqual(len(window.expected_positions), len(window.actions) + 1)

    def test_market_only_shift_is_rejected(self):
        window = replace(candidate_fixture(), family="logistics_market", actions=(("PASS",),) * 4, sell_directives=(SellDirective(0, "MILK", 6),))
        self.assertIn("market_without_delivery", validate_window(window))

    def test_schema_round_trip_preserves_tuple_order_and_id(self):
        window = candidate_fixture()
        self.assertEqual(window, from_json(to_json(window)))

    def test_static_contract_rejects_forbidden_action_and_second_actor(self):
        window = replace(candidate_fixture(), actions=(("HIRE",), ("PASS",), ("PASS",), ("PASS",)))
        self.assertIn("forbidden_opcode", validate_window(window))
        window = replace(candidate_fixture(), actions=(("EAST", "SOUTH"),) * 4)
        self.assertIn("multiple_actors", validate_window(window))

    def test_static_contract_rejects_all_named_error_paths_and_unknown_requirements(self):
        cases = (
            (replace(candidate_fixture(), incumbent="wrong"), "wrong_incumbent"),
            (replace(candidate_fixture(), family="wrong"), "unknown_family"),
            (replace(candidate_fixture(), actions=(("PASS",),) * 3), "window_length"),
            (replace(candidate_fixture(), rejoin_step=99), "rejoin_step"),
            (replace(candidate_fixture(), expected_positions=((1, 1),)), "position_count"),
            (replace(candidate_fixture(), sell_directives=(SellDirective(0, "MILK", 0),)), "sell_quantity"),
            (replace(candidate_fixture(), sell_directives=(SellDirective(0, "MILK", 1), SellDirective(1, "MILK", 1))), "more_than_one_sell"),
            (replace(candidate_fixture(), requirements=(__import__("schema").Requirement("unknown", (), "eq", 1),)), "invalid_requirement"),
            (replace(candidate_fixture(), requirements=(__import__("schema").Requirement("actor_position", (1,), "eq", (1, 1)),)), None),
        )
        for window, expected in cases:
            errors = validate_window(window)
            if expected is None:
                self.assertEqual([], errors)
            else:
                self.assertIn(expected, errors)

    def test_static_contract_accepts_only_each_named_variable_requirement_shape(self):
        Requirement = __import__("schema").Requirement
        window = replace(candidate_fixture(), requirements=(
            Requirement("hands", (), "ge", 1), Requirement("money", (), "ge", 1),
            Requirement("actor_position", (1,), "eq", (1, 1)), Requirement("tile_kind", (2, 1), "eq", "PLANT"),
            Requirement("tile_product", (2, 1), "eq", "WHEAT"), Requirement("tile_yield", (2, 1), "ge", 1),
            Requirement("actor_inventory", (1, "WHEAT"), "ge", 1), Requirement("shed", ("WHEAT",), "ge", 1),
        ))
        self.assertEqual([], validate_window(window))

    def test_miner_is_deterministic_and_never_creates_market_only_candidate(self):
        observations = []
        actions = []
        for step in range(8):
            obs = observation_fixture(step=step, hand_positions=[(1, 1)])
            obs["farms"][0]["tiles"][1][2] = {"kind": "PLANT", "yield_units": 2, "watered_today": True}
            observations.append(obs)
            actions.append({"farmer": ["PASS"], "hands": [["PASS"]], "market": []})
        trace = [TraceFrame(step, observations[step], actions[step], 0.1) for step in range(8)]
        route = tuple(actions)
        first = mine_candidates("v27_current_meta", trace, route, opponent_family="kaito_v21", seed=1, seat=0)
        second = mine_candidates("v27_current_meta", trace, route, opponent_family="kaito_v21", seed=1, seat=0)
        self.assertEqual(first, second)
        self.assertTrue(first)
        self.assertTrue(all(validate_window(window) == [] for window in first))
        self.assertTrue(all(window.family != "logistics_market" or window.touched_tiles for window in first))

    def test_miner_rejects_a_window_touched_by_an_active_incumbent_overlay(self):
        """Catch discovery treating the readable tape as control while an overlay changed it."""
        observations = []
        actions = []
        for step in range(5):
            obs = observation_fixture(step=step, hand_positions=[(1, 1)])
            obs["farms"][0]["tiles"][1][2] = {"kind": "PLANT", "yield_units": 2, "watered_today": True}
            observations.append(obs)
            actions.append({"farmer": ["PASS"], "hands": [["PASS"]], "market": []})
        actions[1] = {"farmer": ["PASS"], "hands": [["EAST"]], "market": []}
        trace = [TraceFrame(step, observations[step], actions[step], 0.1) for step in range(5)]
        route = tuple({"farmer": ["PASS"], "hands": [["PASS"]], "market": []} for _ in range(5))
        self.assertEqual((), mine_candidates("v27_current_meta", trace, route, opponent_family="kaito_v21", seed=1, seat=0))

    def test_miner_rejects_farmer_or_market_overlay_across_full_interval(self):
        trace = []
        route = []
        for step in range(5):
            obs = observation_fixture(step=step, hand_positions=[(1, 1)])
            obs["farms"][0]["tiles"][1][2] = {"kind": "PLANT", "yield_units": 2, "watered_today": True}
            action = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
            trace.append(TraceFrame(step, obs, action, 0.1))
            route.append(action)
        for overlay in (
            {"farmer": ["EAST"], "hands": [["PASS"]], "market": []},
            {"farmer": ["PASS"], "hands": [["PASS"]], "market": [["SELL", "MILK", 1]]},
        ):
            changed = list(trace)
            changed[1] = TraceFrame(1, changed[1].observation, overlay, 0.1)
            self.assertEqual((), mine_candidates("v27_current_meta", changed, tuple(route), opponent_family="kaito_v21", seed=1, seat=0))

    def test_anchor_window_does_not_read_offset_six_for_length_four(self):
        trace, route = self._pass_trace(8)
        trace[0].observation["farms"][0]["tiles"][1][2] = {"kind": "PLANT", "yield_units": 2, "watered_today": True}
        route[6] = {"farmer": ["PASS"], "hands": [["WATER"]], "market": []}
        found = mine_candidates("v27_current_meta", trace, tuple(route), opponent_family="kaito_v21", seed=1, seat=0)
        self.assertFalse([window for window in found if window.family == "maintenance_trade"])

    def test_drop_capacity_and_terminal_logistics_anchors_are_discovered_without_bare_sell(self):
        trace, route = self._pass_trace(5, step_base=671)
        route = [{"farmer": ["PASS"], "hands": [["PASS"]], "market": []} for _ in range(671)] + route
        obs = trace[0].observation
        obs["private"]["inventories"][1]["MILK"] = 3
        obs["private"]["shed"]["WHEAT"] = 85
        found = mine_candidates("v27_current_meta", trace, tuple(route), opponent_family="kaito_v21", seed=1, seat=0)
        logistics = [window for window in found if window.family == "logistics_market"]
        self.assertTrue(logistics)
        self.assertTrue(any(action[0] == "DROP" for action in logistics[0].actions))
        self.assertEqual((48,), tuple(effect.horizon for effect in logistics[0].effects))
        for frame in trace:
            frame.observation["private"]["inventories"][1]["MILK"] = 0
        bare = [replace(frame, action={"farmer": ["PASS"], "hands": [["PASS"]], "market": [["SELL", "MILK", 3]]}) for frame in trace]
        self.assertFalse([window for window in mine_candidates("v27_current_meta", bare, tuple(route), opponent_family="kaito_v21", seed=1, seat=0) if window.family == "logistics_market"])

    def test_harvest_inside_window_can_anchor_logistics_delivery(self):
        trace, route = self._pass_trace(5)
        for index, frame in enumerate(trace):
            frame.observation["farms"][0]["tiles"][4][4] = {"kind": "PLANT", "crop": "WHEAT", "yield_units": 2, "watered_today": True}
        harvest = {"farmer": ["PASS"], "hands": [["HARVEST"]], "market": []}
        trace[0] = replace(trace[0], action=harvest)
        route[0] = harvest
        found = mine_candidates("v27_current_meta", trace, tuple(route), opponent_family="kaito_v21", seed=1, seat=0)
        logistics = [window for window in found if window.family == "logistics_market"]
        self.assertTrue(logistics)
        self.assertIn(("HARVEST",), logistics[0].actions)
        self.assertIn(("DROP",), logistics[0].actions)

    def _pass_trace(self, count, step_base=0):
        trace, route = [], []
        for offset in range(count):
            obs = observation_fixture(step=step_base + offset, hand_positions=[(4, 4)])
            action = {"farmer": ["PASS"], "hands": [["PASS"]], "market": []}
            trace.append(TraceFrame(step_base + offset, obs, action, 0.1))
            route.append(action)
        return trace, route


if __name__ == "__main__":
    unittest.main()
