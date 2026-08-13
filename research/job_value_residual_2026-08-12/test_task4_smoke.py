"""Replay the retained Task-4 counterfactual evidence through shipped schema code."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from engine_runner import run_game
from forced_policy import make_forced_factory
from protocol import control_path
from schema import from_json


class Task4SmokeReplayTests(unittest.TestCase):
    def test_artifact_windows_deserialize_and_replay_recorded_forced_behavior(self):
        path = Path(__file__).resolve().parent / "artifacts" / "task4_smoke.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            context = row["context"]
            window_json = dict(row["forced_window"])
            window_json.update({
                "candidate_id": row["candidate"]["id"],
                "incumbent": context["incumbent"],
                "family": row["candidate"]["family"],
                "trigger_step": row["candidate"]["trigger_step"],
                "actor": row["candidate"]["actor"],
                "rejoin_step": row["candidate"]["rejoin_step"],
                "effects": [],
            })
            window = from_json(json.dumps(window_json))
            control = run_game(
                context["incumbent"], control_path(context["incumbent"]),
                context["opponent_family"], context["seed"], context["seat"],
            )
            forced = run_game(
                context["incumbent"], control_path(context["incumbent"]),
                context["opponent_family"], context["seed"], context["seat"],
                policy_factory=make_forced_factory(window),
            )
            self.assertEqual(row["control"]["action_digest"], control.summary["action_digest"])
            self.assertEqual(row["forced"]["action_digest"], forced.summary["action_digest"])
            self.assertEqual(row["metadata"]["status"], forced.policy_metadata["status"])


if __name__ == "__main__":
    unittest.main()
