from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("test_branch", ROOT / "branch_v25_to_zero_agent.py")
assert spec and spec.loader
BRANCH = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BRANCH)


class FakePolicy:
    def __init__(self, action):
        self.action = action
        self.calls = []

    def agent(self, observation, configuration=None):
        self.calls.append(observation["step"])
        return self.action


class BranchAgentTest(unittest.TestCase):
    def setUp(self):
        self.old_v25, self.old_zero = BRANCH.V25, BRANCH.ZERO
        BRANCH._STATE = {0: {}, 1: {}}

    def tearDown(self):
        BRANCH.V25, BRANCH.ZERO = self.old_v25, self.old_zero

    def test_branches_only_after_runtime_verified_prefix(self):
        v25 = FakePolicy({"farmer": ["PASS"], "hands": [], "market": []})
        zero = FakePolicy({"farmer": ["PASS"], "hands": [], "market": []})
        BRANCH.V25, BRANCH.ZERO = v25, zero
        self.assertEqual(BRANCH.agent({"step": 0, "player": 0}), v25.action)
        self.assertEqual(BRANCH.agent({"step": 160, "player": 0}), v25.action)
        self.assertEqual(BRANCH.agent({"step": 161, "player": 0}), zero.action)
        self.assertTrue(BRANCH.branch_stats(0)["branched"])

    def test_mismatch_vetoes_branch_and_keeps_v25(self):
        v25 = FakePolicy({"farmer": ["PASS"], "hands": [], "market": []})
        zero = FakePolicy({"farmer": ["NORTH"], "hands": [], "market": []})
        BRANCH.V25, BRANCH.ZERO = v25, zero
        BRANCH.agent({"step": 0, "player": 0})
        self.assertEqual(BRANCH.agent({"step": 161, "player": 0}), v25.action)
        self.assertTrue(BRANCH.branch_stats(0)["vetoed"])


if __name__ == "__main__":
    unittest.main()
