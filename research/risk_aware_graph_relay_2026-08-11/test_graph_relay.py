from __future__ import annotations

import copy
import unittest

import numpy as np

from graph_model import ADJACENCY, FlatMLPRegressor, GraphRegressor, graph_features, parameter_count
from relay_policy import _remove_fertilizer_sale


class GraphRelayTests(unittest.TestCase):
    def test_adjacency_is_symmetric_and_finite(self):
        self.assertTrue(np.isfinite(ADJACENCY).all())
        self.assertTrue(np.allclose(ADJACENCY, ADJACENCY.T))

    def test_models_have_comparable_parameter_count(self):
        graph = parameter_count(GraphRegressor(hidden=32))
        flat = parameter_count(FlatMLPRegressor(hidden=4))
        self.assertLess(abs(graph - flat), 0.15 * max(graph, flat))

    def test_sale_removal_preserves_unrelated_orders(self):
        action = {
            "farmer": ["PASS"],
            "market": [["SELL", "WHEAT", 4], ["SELL", "FERTILIZER", 9]],
        }
        changed = _remove_fertilizer_sale(action, 6)
        self.assertEqual(changed["market"], [["SELL", "WHEAT", 4], ["SELL", "FERTILIZER", 3]])
        self.assertEqual(action["market"][1][2], 9)

    def test_graph_ignores_unavailable_opponent_private_field(self):
        products = (
            "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER",
        )
        farm = {
            "money": 3000,
            "hands": [],
            "unlocked_quadrants": ["NW"],
            "tiles": [[None for _ in range(10)] for _ in range(10)],
        }
        obs = {
            "player": 0,
            "step": 278,
            "farms": [copy.deepcopy(farm), copy.deepcopy(farm)],
            "private": {"shed": {}, "inventories": [{}], "seeds": {}},
            "market": {
                "inventory": {item: 10000 for item in products},
                "prices": {item: 1 for item in products},
            },
            "town": {"unlocked_shops": []},
        }
        expected = graph_features(obs)
        obs["opponent_private"] = {"shed": {"FERTILIZER": 999999}}
        self.assertTrue(np.array_equal(expected, graph_features(obs)))


if __name__ == "__main__":
    unittest.main()
