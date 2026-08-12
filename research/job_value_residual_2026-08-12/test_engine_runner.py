"""Integration contracts for the exact current-engine trace runner."""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
import gzip
import json

from engine_runner import GameRun, TraceFrame, control_path, run_game, write_trace_gzip


class EngineRunnerTests(unittest.TestCase):
    def test_full_game_has_719_calls_and_stable_digest(self):
        """Catch a runner that stops early or fails to reset agent state."""
        path = control_path("v27_current_meta")
        first = run_game(
            "v27_current_meta", path, "kaito_v21", 93687444, 0, capture_trace=True
        )
        second = run_game(
            "v27_current_meta", path, "kaito_v21", 93687444, 0, capture_trace=False
        )
        self.assertEqual(["DONE", "DONE"], first.summary["statuses"])
        self.assertEqual(719, len(first.trace))
        self.assertEqual(719, first.summary["calls"])
        self.assertEqual(first.summary["action_digest"], second.summary["action_digest"])
        self.assertEqual(first.summary["rewards"], second.summary["rewards"])
        self.assertEqual(["DONE", "DONE"], second.summary["statuses"])
        self.assertIsNone(first.summary["exception"])
        self.assertIsNone(first.summary["opponent_exception"])
        self.assertEqual(
            {"malformed": 0, "hand_alignment": 0, "seed_overcommit": 0, "market_overflow": 0},
            first.summary["action_issues"],
        )
        self.assertLessEqual(first.summary["max_market_orders"], 10)
        self.assertEqual(0, first.summary["timeout_calls"])
        self.assertFalse(first.summary["overage_exhausted"])

    def test_trace_contains_only_own_private_view(self):
        """Catch trace construction leaking an opponent-private field."""
        run = run_game(
            "v27_current_meta",
            control_path("v27_current_meta"),
            "kaito_v21",
            93687444,
            1,
            capture_trace=True,
        )
        self.assertIn("private", run.trace[0].observation)
        self.assertNotIn("opponent_private", run.trace[0].observation)

    def test_trace_gzip_has_canonical_json_payload(self):
        """Catch trace persistence that loses frames or emits unstable JSON formatting."""
        run = GameRun(
            incumbent="v27_current_meta",
            opponent_family="kaito_v21",
            seed=1,
            seat=0,
            summary={"calls": 1, "statuses": ["DONE", "DONE"]},
            trace=[
                TraceFrame(
                    step=0,
                    observation={"private": {"shed": {}}},
                    action={"farmer": ["PASS"], "hands": [], "market": []},
                    latency_ms=0.25,
                )
            ],
            policy_metadata={"selector": "control"},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json.gz"
            write_trace_gzip(path, run)
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                payload = stream.read()
        self.assertEqual(
            '{"policy_metadata":{"selector":"control"},"summary":{"calls":1,"statuses":["DONE","DONE"]},"trace":[{"action":{"farmer":["PASS"],"hands":[],"market":[]},"latency_ms":0.25,"observation":{"private":{"shed":{}}},"step":0}]}',
            payload,
        )
        self.assertEqual(1, json.loads(payload)["summary"]["calls"])

    def test_overflow_diagnostics_do_not_count_consumption_as_discard(self):
        """Catch FEED or other consuming actions being recorded as shed overflow."""
        run = run_game(
            "v27_current_meta",
            control_path("v27_current_meta"),
            "kaito_v21",
            93687444,
            0,
            capture_trace=True,
        )
        direct_drops = sum(
            int(
                isinstance(order, list)
                and bool(order)
                and order[0] == "DROP"
            )
            for frame in run.trace
            for order in [
                frame.action.get("farmer"),
                *(frame.action.get("hands", []) or []),
            ]
        )
        days = 719 // 24
        self.assertLessEqual(
            run.summary["diagnostics"]["shed_overflow_events"], direct_drops + days
        )

    def test_transition_sampling_counts_same_turn_fresh_crop_death(self):
        """Catch an EOD PLANT that becomes a weed before the next snapshot."""
        def plant_on_end_of_day(_module, _policy, _seat):
            def policy(observation):
                if observation.step == 0:
                    return {
                        "farmer": ["PASS"],
                        "hands": [],
                        "market": [["BUY_SEED", "WHEAT", 1]],
                    }
                if observation.step == 23:
                    return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
                return {"farmer": ["PASS"], "hands": [], "market": []}

            return policy

        run = run_game(
            "v27_current_meta",
            control_path("v27_current_meta"),
            "kaito_v21",
            93687444,
            0,
            policy_factory=plant_on_end_of_day,
        )
        self.assertEqual(1, run.summary["diagnostics"]["crop_deaths"])
        self.assertEqual(1, run.summary["diagnostics"]["fresh_crop_deaths"])
        self.assertEqual([23], run.summary["diagnostics"]["crop_death_steps"])
        self.assertEqual([23], run.summary["diagnostics"]["fresh_crop_death_steps"])

    def test_transition_sampling_counts_non_eod_lifespan_decay(self):
        """Catch lifespan decay that converts a plant to weed between daily refreshes."""
        def water_until_lifespan(_module, _policy, _seat):
            water_steps = {2, 24, 48, 72, 96}

            def policy(observation):
                if observation.step == 0:
                    return {
                        "farmer": ["PASS"],
                        "hands": [],
                        "market": [["BUY_SEED", "WHEAT", 1]],
                    }
                if observation.step == 1:
                    return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
                if observation.step in water_steps:
                    return {"farmer": ["WATER"], "hands": [], "market": []}
                return {"farmer": ["PASS"], "hands": [], "market": []}

            return policy

        run = run_game(
            "v27_current_meta",
            control_path("v27_current_meta"),
            "kaito_v21",
            93687444,
            0,
            policy_factory=water_until_lifespan,
        )
        self.assertEqual(1, run.summary["diagnostics"]["crop_deaths"])
        self.assertEqual(0, run.summary["diagnostics"]["fresh_crop_deaths"])
        self.assertEqual([126], run.summary["diagnostics"]["crop_death_steps"])
        self.assertEqual([], run.summary["diagnostics"]["fresh_crop_death_steps"])

    def test_opponent_violation_metrics_are_retained_separately(self):
        """Catch a runner that hides malformed, capped, or timed-out opponent calls."""
        class OpponentTimeoutClock:
            def __init__(self):
                self.calls = 0

            def __call__(self):
                cycle, offset = divmod(self.calls, 4)
                self.calls += 1
                return float(cycle * 2 + (2 if offset == 3 else 0))

        def candidate_pass(_module, _policy, _seat):
            return lambda _observation: {"farmer": ["PASS"], "hands": [], "market": []}

        def violating_opponent(_module, _policy, _seat):
            return lambda _observation: {
                "farmer": ["PASS"],
                "hands": [["PASS"]],
                "market": [["SELL", "WHEAT", 1]] * 11,
            }

        run = run_game(
            "v27_current_meta",
            control_path("v27_current_meta"),
            "kaito_v21",
            93687444,
            0,
            policy_factory=candidate_pass,
            opponent_policy_factory=violating_opponent,
            clock=OpponentTimeoutClock(),
        )
        self.assertEqual(719, run.summary["calls"])
        self.assertEqual(0, run.summary["timeout_calls"])
        self.assertFalse(run.summary["overage_exhausted"])
        self.assertEqual(719, run.summary["opponent_calls"])
        self.assertEqual(719, run.summary["opponent_action_issues"]["hand_alignment"])
        self.assertEqual(719, run.summary["opponent_action_issues"]["market_overflow"])
        self.assertEqual(11, run.summary["opponent_max_market_orders"])
        self.assertEqual(719, run.summary["opponent_timeout_calls"])
        self.assertTrue(run.summary["opponent_overage_exhausted"])
        self.assertEqual(719, run.summary["opponent_latency_ms"]["calls"])


if __name__ == "__main__":
    unittest.main()
