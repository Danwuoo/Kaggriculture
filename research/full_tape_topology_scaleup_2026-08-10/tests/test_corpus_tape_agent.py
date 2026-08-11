from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("test_corpus_tape", ROOT / "corpus_supported_tape_agent.py")
assert spec and spec.loader
AGENT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AGENT)


class CorpusTapeAgentTest(unittest.TestCase):
    def test_exact_tape_and_hand_projection_only(self):
        observation = {"step": 0, "player": 0, "farms": [{"hands": [[5, 4]]}]}
        action = AGENT.agent(observation)
        self.assertEqual(action["farmer"], AGENT._ACTIONS[0]["farmer"])
        self.assertEqual(action["market"], AGENT._ACTIONS[0]["market"])
        self.assertEqual(len(action["hands"]), 1)
        self.assertEqual(AGENT.stats(0)["alignment_changes"], 1)


if __name__ == "__main__":
    unittest.main()
