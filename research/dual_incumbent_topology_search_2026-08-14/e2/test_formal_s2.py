from __future__ import annotations

import unittest

from formal_s2 import (
    CANDIDATE_ID,
    LANE,
    OPPONENTS,
    OTHER_LANE,
    SEATS,
    _s1_authority,
    _seed_records,
)


class FormalS2ContractTests(unittest.TestCase):
    def test_s2_is_boatlee_only_with_unchanged_finalist(self) -> None:
        self.assertEqual("boatlee_v16_rc2_market_relay", LANE)
        self.assertEqual("v27_current_meta", OTHER_LANE)
        self.assertEqual("ac_3aa759d7d7fc4a409c409326", CANDIDATE_ID)
        self.assertEqual(4, len(OPPONENTS))
        self.assertEqual((0, 1), SEATS)

    def test_seed_registry_is_four_new_fresh_seeds(self) -> None:
        records, _registry = _seed_records()
        values = {int(row["seed"]) for row in records}
        self.assertEqual(4, len(values))
        self.assertFalse(values & {811407, 81426017, 81426029, 42284410, 73912654})
        self.assertTrue(all(row["fresh"] and row["classification"] == "formal_fresh" for row in records))

    def test_s1_authority_advances_only_boatlee(self) -> None:
        authority = _s1_authority()
        self.assertTrue(authority["pass"], authority)
        self.assertTrue(authority["checks"]["decision_scope"])
        self.assertTrue(authority["checks"]["candidate_identity"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
