"""Separate robust and high-upside frontiers; never pool incumbent strata."""

from __future__ import annotations

from typing import Any


def _robust(row: dict[str, Any]) -> bool:
    metrics = row["metrics"]
    return (
        bool(metrics.get("technical_pass"))
        and bool(metrics.get("all_contexts_complete", True))
        and int(metrics.get("action_changed_contexts", 0)) > 0
        and int(metrics.get("opponent_nonnegative_families", 0)) >= 2
        and float(metrics.get("worst_paired_margin", -1)) >= 0
    )


def _upside(row: dict[str, Any]) -> bool:
    metrics = row["metrics"]
    return int(metrics.get("actual_win_delta", 0)) > 0 or row.get("expected_frontier") == "high_upside"


def _lane_rows(source: dict[str, Any]) -> tuple[float, dict[str, list[dict[str, Any]]]]:
    """Accept frozen fixture anchors or freshly evaluated formal score rows."""
    epsilon = float(source.get("near_tie_mean_margin_epsilon", source.get("epsilon", 1.0)))
    lanes: dict[str, list[dict[str, Any]]] = {}
    for lane, rows in source["lanes"].items():
        lanes[lane] = list(rows.values()) if isinstance(rows, dict) else list(rows)
    return epsilon, lanes


def rank_frontiers(source: dict[str, Any]) -> dict[str, Any]:
    epsilon, source_lanes = _lane_rows(source)
    output: dict[str, Any] = {"epsilon": epsilon, "lanes": {}}
    for lane, rows in source_lanes.items():
        # A worker failure cannot be promoted by an attractive partial result.
        rows = [row for row in rows if row.get("score") is not None or "metrics" in row]
        robust = [row for row in rows if _robust(row)]
        high = [row for row in rows if _upside(row)]
        robust.sort(key=lambda row: (-float(row["metrics"]["mean_paired_margin"]), int(row["metrics"]["complexity"]), row["candidate_id"]))
        if robust:
            best_mean = float(robust[0]["metrics"]["mean_paired_margin"])
            representative = min((row for row in robust if best_mean - float(row["metrics"]["mean_paired_margin"]) <= epsilon), key=lambda row: (int(row["metrics"]["complexity"]), row["candidate_id"]))["candidate_id"]
        else:
            representative = None
        output["lanes"][lane] = {
            "robust": [row["candidate_id"] for row in robust],
            "high_upside": [row["candidate_id"] for row in high],
            "causal_representative": representative,
            "pooled": False,
        }
    return output
