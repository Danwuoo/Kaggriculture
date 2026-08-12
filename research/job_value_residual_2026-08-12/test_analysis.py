"""Behavioural contracts for discovery labels, gates, and frozen-window output."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from analysis import discovery_gate, label_pair, summarize_discovery
from freeze_windows import render_policy
from test_support import passing_discovery_summary


class AnalysisTests(unittest.TestCase):
    def test_outcome_transition_precedes_margin(self):
        """Catch labels that call an L-to-D improvement neutral on zero margin."""
        label = label_pair({"margin": -1.0}, {"margin": 0.0})
        self.assertEqual("positive", label.sign)
        self.assertEqual("L_TO_D", label.outcome_transition)

    def test_unchanged_outcome_uses_terminal_margin_delta(self):
        """Catch labels that ignore terminal margin when the outcome is unchanged."""
        label = label_pair({"margin": 10.0}, {"margin": 15.0})
        self.assertEqual("positive", label.sign)
        self.assertEqual("W_TO_W", label.outcome_transition)
        self.assertEqual(5.0, label.margin_delta)

    def test_gate_requires_both_signs_and_two_families_per_incumbent(self):
        """Catch a dual-incumbent pass that lacks diverse counterfactual labels."""
        summary = passing_discovery_summary()
        self.assertTrue(discovery_gate(summary)["pass"])
        summary["v27_current_meta"]["negative"] = 3
        self.assertFalse(discovery_gate(summary)["pass"])

    def test_summary_selects_larger_threshold_after_accuracy_and_coverage_tie(self):
        """Catch threshold selection that is not deterministic at an exact score tie."""
        rows = [
            {
                "incumbent": "v27_current_meta", "candidate": {"family": "maintenance_trade"},
                "label": {"sign": "positive"}, "delta_value_24": 250.0, "delta_value_48": 250.0,
                "technical_failure": False, "metadata": {"status": "rejoined"},
                "logistics_delivery_valid": True,
            },
            {
                "incumbent": "v27_current_meta", "candidate": {"family": "productive_detour"},
                "label": {"sign": "negative"}, "delta_value_24": -250.0, "delta_value_48": -250.0,
                "technical_failure": False, "metadata": {"status": "rejoined"},
                "logistics_delivery_valid": True,
            },
        ]
        summary = summarize_discovery(rows)
        self.assertEqual(200.0, summary["v27_current_meta"]["threshold"])

    def test_frozen_window_renderer_is_byte_stable(self):
        """Catch output whose runtime table changes across equivalent renders."""
        payload = {
            "threshold": 50.0,
            "windows": [{"trigger_step": 12, "candidate_id": "b"}, {"trigger_step": 10, "candidate_id": "a"}],
        }
        self.assertEqual(render_policy(payload), render_policy(payload))
        self.assertLess(render_policy(payload).find("candidate_id': 'a"), render_policy(payload).find("candidate_id': 'b"))


if __name__ == "__main__":
    unittest.main()
