from __future__ import annotations

import unittest

from formal_s1 import EXPECTED_CANDIDATES, LANES, OPPONENTS, SEATS, _classify, _seed_records


class FormalS1ContractTests(unittest.TestCase):
    def test_s1_surface_is_exactly_two_lane_local_candidates(self) -> None:
        self.assertEqual(set(LANES), set(EXPECTED_CANDIDATES))
        self.assertEqual(2, len(EXPECTED_CANDIDATES))
        self.assertEqual(4, len(OPPONENTS))
        self.assertEqual((0, 1), SEATS)

    def test_seed_registry_is_two_fresh_seeds_and_excludes_prior_seeds(self) -> None:
        records, _registry = _seed_records()
        values = {int(row["seed"]) for row in records}
        self.assertEqual(2, len(values))
        self.assertFalse(values & {811407, 81426017, 81426029})
        self.assertTrue(all(row["fresh"] and row["classification"] == "formal_fresh" for row in records))

    def test_action_only_difference_is_not_effective(self) -> None:
        evidence = {
            "receipt_digest": "r", "public_state_digest": "s",
            "economic_diagnostics": {},
        }
        control = {
            "evidence": {**evidence, "action_digest": "control"},
            "own_reward": 1, "opponent_reward": 2, "own_bank": 1, "opponent_bank": 2,
        }
        candidate = {
            "evidence": {**evidence, "action_digest": "candidate"},
            "own_reward": 1, "opponent_reward": 2, "own_bank": 1, "opponent_bank": 2,
        }
        result = _classify(candidate, control)
        self.assertTrue(result["action_only_noop"])
        self.assertFalse(result["effective"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
