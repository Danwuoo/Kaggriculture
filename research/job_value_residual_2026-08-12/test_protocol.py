"""Behavioral contract for the frozen job-value residual protocol."""

from __future__ import annotations

import unittest

from protocol import (
    CONFIRMATION_SEEDS,
    DISCOVERY_SEEDS,
    INCUMBENTS,
    SCREEN_SEEDS,
    opponent_path,
    stage_contexts,
)


class ProtocolTests(unittest.TestCase):
    def test_seed_pools_are_disjoint_and_have_exact_sizes(self):
        """Catch a seed being duplicated or accidentally omitted across stages."""
        pools = [DISCOVERY_SEEDS, SCREEN_SEEDS, CONFIRMATION_SEEDS]
        self.assertEqual([2, 4, 8], [len(pool) for pool in pools])
        self.assertEqual(14, len(set().union(*map(set, pools))))

    def test_stage_context_counts(self):
        """Catch a missing incumbent, opponent family, seed, or seat stratum."""
        self.assertEqual(16, len(stage_contexts("discovery")))
        self.assertEqual(32, len(stage_contexts("screen")))
        self.assertEqual(64, len(stage_contexts("confirmation")))

    def test_opponents_are_frozen_other_incumbent_or_kaito(self):
        """Catch experiments accidentally pointing at mutable candidates or no opponent."""
        for incumbent in INCUMBENTS:
            self.assertTrue(opponent_path(incumbent, "other_incumbent").is_file())
            self.assertTrue(opponent_path(incumbent, "kaito_v21").is_file())


if __name__ == "__main__":
    unittest.main()
