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


if __name__ == "__main__":
    unittest.main()
