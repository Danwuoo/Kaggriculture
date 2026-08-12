"""Behavioural contracts for discovery labels, gates, and frozen-window output."""

from __future__ import annotations

import gzip
import hashlib
import json
import tempfile
from pathlib import Path
import unittest

from analysis import discovery_gate, label_pair, summarize_discovery
from engine_runner import TraceFrame
from freeze_windows import render_policy
from run_discovery import audit_existing, candidate_market_receipts
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

    def test_candidate_record_keeps_every_committed_receipt_when_an_earlier_sell_fails(self):
        """Catch receipt encoding that loses later units after a failed earlier SELL order."""
        trace = [
            TraceFrame(
                step=12, observation={}, action={"market": [["SELL", "MILK", 2], ["SELL", "WOOL", 1]]}, latency_ms=0.1,
                market_receipts=((12, "WOOL", 30.0),),
            ),
        ]
        self.assertEqual(
            [
                {"step": 12, "receipt_index": 0, "product": "WOOL", "receipt": 30.0},
            ],
            candidate_market_receipts(trace),
        )

    def _candidate_evidence(self, directory, *, summary=None, metadata=None):
        trace_path = Path(directory) / "candidate.json.gz"
        payload = {
            "summary": {"reward": 12} if summary is None else summary,
            "policy_metadata": {"status": "rejoined"} if metadata is None else metadata,
            "trace": [{"step": 0, "market_receipts": []}],
        }
        with gzip.open(trace_path, "wt", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
        row = {
            "kind": "candidate", "candidate_trace": "candidate.json.gz",
            "candidate_trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
            "candidate_run": {"reward": 12}, "metadata": {"status": "rejoined"},
            "candidate_market_receipts": [],
        }
        records = Path(directory) / "records.jsonl"
        records.write_text(json.dumps(row) + "\n", encoding="utf-8")
        return records, trace_path, row

    def test_offline_audit_rejects_candidate_trace_hash_mutation(self):
        """Catch a swapped or mutated candidate trace that still has plausible rows."""
        with tempfile.TemporaryDirectory() as directory:
            records, trace_path, _row = self._candidate_evidence(directory)
            trace_path.write_bytes(trace_path.read_bytes() + b"mutation")
            with self.assertRaisesRegex(RuntimeError, "candidate trace hash mismatch"):
                audit_existing(records)

    def test_offline_audit_rejects_same_receipts_with_mutated_summary(self):
        """Catch trace-content mutation hidden by recomputing its row hash."""
        with tempfile.TemporaryDirectory() as directory:
            records, trace_path, row = self._candidate_evidence(directory, summary={"reward": 13})
            row["candidate_trace_sha256"] = hashlib.sha256(trace_path.read_bytes()).hexdigest()
            records.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "candidate trace summary mismatch"):
                audit_existing(records)

    def test_offline_audit_rejects_same_receipts_with_mutated_metadata(self):
        """Catch trace policy drift that leaves all unit receipt values unchanged."""
        with tempfile.TemporaryDirectory() as directory:
            records, trace_path, row = self._candidate_evidence(directory, metadata={"status": "aborted"})
            row["candidate_trace_sha256"] = hashlib.sha256(trace_path.read_bytes()).hexdigest()
            records.write_text(json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "candidate trace metadata mismatch"):
                audit_existing(records)


if __name__ == "__main__":
    unittest.main()
