from __future__ import annotations

import unittest

from boatlee_remediation import FULL_CANDIDATE_ID, public_features, remediation_candidates


class BoatleeRemediationTests(unittest.TestCase):
    def test_atomic_candidates_are_new_and_exact(self) -> None:
        candidates = remediation_candidates()
        self.assertEqual({"step_240_only", "step_241_only"}, set(candidates))
        self.assertTrue(all(row.accepted for row in candidates.values()))
        self.assertTrue(all(row.candidate_id != FULL_CANDIDATE_ID for row in candidates.values()))
        self.assertEqual([240], [row["step"] for row in candidates["step_240_only"].patches])
        self.assertEqual([241], [row["step"] for row in candidates["step_241_only"].patches])
        self.assertEqual(9, len(candidates["step_240_only"].patches[0]["market"]))
        self.assertEqual(9, len(candidates["step_241_only"].patches[0]["market"]))

    def test_public_feature_projection_excludes_private_state(self) -> None:
        observation = {
            "step": 240,
            "player": 0,
            "private": {"shed": {"MILK": 99}},
            "farms": [
                {"money": 10, "hands": [{"x": 1}], "unlocked_quadrants": ["NW"], "tiles": [[{"kind": "PLANT", "crop": "WHEAT"}]]},
                {"money": 20, "hands": [], "unlocked_quadrants": [], "tiles": [[{"kind": "ANIMAL", "animal": "COW"}]]},
            ],
            "market": {"prices": {"WHEAT": 40}, "inventory": {"WHEAT": 100}},
            "town": {"unlocked_shops": ["SEED"]},
        }
        result = public_features(observation)
        self.assertNotIn("private", result)
        self.assertNotIn("MILK", result)
        self.assertEqual(40, result["market_price_WHEAT"])
        self.assertEqual(1, result["own_crop_WHEAT"])
        self.assertEqual(1, result["opponent_animal_COW"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
