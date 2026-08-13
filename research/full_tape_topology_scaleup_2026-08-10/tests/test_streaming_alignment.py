from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("test_streaming", ROOT / "streaming_corpus.py")
assert spec and spec.loader
STREAMING = importlib.util.module_from_spec(spec)
spec.loader.exec_module(STREAMING)


class StreamingAlignmentTest(unittest.TestCase):
    def test_extract_uses_replay_rows_one_through_719(self):
        rows = [
            [{"action": {"farmer": ["PASS", index], "hands": [], "market": []}}]
            for index in range(720)
        ]
        actions = STREAMING.meaningful_actions(rows, 0)
        self.assertEqual(len(actions), 719)
        self.assertEqual(actions[0]["farmer"], ["PASS", 1])
        self.assertEqual(actions[-1]["farmer"], ["PASS", 719])


if __name__ == "__main__":
    unittest.main()
