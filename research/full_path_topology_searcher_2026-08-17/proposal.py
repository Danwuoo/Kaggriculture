"""Evidence-derived proposal diagnostics and bounded serialization."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from .model import BranchSpec
except ImportError:
    from model import BranchSpec


def _mutability(motif: Mapping[str, Any], atlas: Mapping[str, Any]) -> tuple[float | None, dict[str, Any]]:
    channel = motif.get("channel")
    window = motif.get("step_window")
    entropy = atlas.get("channel_entropy_by_step", {}).get(channel)
    if (not isinstance(entropy, list) or len(entropy) != 719 or not isinstance(window, list)
            or len(window) != 2 or any(not isinstance(value, int) or isinstance(value, bool) for value in window)):
        return None, {"status": "missing_or_invalid_atlas_entropy"}
    start, end = window
    if start < 0 or end < start or end >= len(entropy):
        return None, {"status": "invalid_step_window"}
    maximum = max(float(value) for value in entropy)
    values = [float(value) for value in entropy[start:end + 1]]
    score = 0.0 if maximum <= 0 else sum(values) / len(values) / maximum
    return round(score, 8), {
        "status": "derived", "channel": channel, "step_window": window,
        "population": atlas.get("support_population"), "support": atlas.get("representative_tapes"),
    }


def _own_loss_match(motif: Mapping[str, Any], lane: str,
                    loss_rows: Iterable[Mapping[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    families = set(motif.get("loss_families", []))
    lane_negative = []
    matched = []
    for row in loss_rows:
        if row.get("incumbent") != lane or row.get("label", {}).get("sign") != "negative":
            continue
        lane_negative.append(row)
        if row.get("window", {}).get("family") in families:
            matched.append(row)
    if not lane_negative or not matched:
        return None, {"status": "no_matching_own_loss_windows", "negative_lane_rows": len(lane_negative),
                      "matching_rows": len(matched), "families": sorted(families)}
    contexts = {
        (row.get("context", {}).get("seed"), row.get("context", {}).get("seat"),
         row.get("context", {}).get("opponent_family")) for row in matched
    }
    return round(len(matched) / len(lane_negative), 8), {
        "status": "derived_consumed_diagnostic", "negative_lane_rows": len(lane_negative),
        "matching_rows": len(matched), "distinct_contexts": len(contexts), "families": sorted(families),
    }


def derive_proposals(motifs: Iterable[dict[str, Any]], lane: str, atlas: Mapping[str, Any],
                     loss_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Derive available signals and refuse ranking while any required signal is absent."""
    result = []
    loss_rows = list(loss_rows)
    for motif in motifs:
        if lane not in motif.get("lanes", []):
            continue
        mutability, mutability_evidence = _mutability(motif, atlas)
        own_loss, own_loss_evidence = _own_loss_match(motif, lane, loss_rows)
        # Semantic source-motif extraction has not been implemented. Do not
        # accept hand-authored "verified" flags as a substitute.
        independent: set[str] = set()
        frontier = None
        missing = []
        if mutability is None:
            missing.append("replay_mutability")
        if frontier is None:
            missing.append("frontier_relevance")
        if own_loss is None:
            missing.append("own_loss_match")
        value = {key: motif[key] for key in ("id", "lanes", "bounded_horizon", "channel", "step_window")}
        value.update({
            "signals": {"replay_mutability": mutability, "frontier_relevance": frontier, "own_loss_match": own_loss},
            "evidence": {
                "replay_mutability": mutability_evidence,
                "frontier_relevance": {"status": "semantic_source_match_extractor_not_implemented",
                                       "verified_independent_sources": sorted(independent), "minimum_required": 2},
                "own_loss_match": own_loss_evidence,
            },
            "priority": round(mutability * frontier * own_loss, 8) if not missing else None,
            "ranking_eligible": not missing,
            "status": "ranked_for_development_budget" if not missing else "blocked_missing_evidence",
            "missing_signals": missing,
        })
        result.append(value)
    return sorted(result, key=lambda value: (not value["ranking_eligible"], -(value["priority"] or 0), value["id"]))


def proposal_oracle(motifs: Iterable[dict[str, Any]], lane: str, atlas: Mapping[str, Any],
                    loss_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    proposals = derive_proposals(motifs, lane, atlas, loss_rows)
    eligible = [row for row in proposals if row["ranking_eligible"]]
    return {
        "lane": lane, "development_budget_only": True, "efficacy_signal": False,
        "status": "READY" if eligible else "BLOCKED_MISSING_EVIDENCE",
        "ranked_proposal_count": len(eligible), "proposals": proposals,
    }


def write_branch(spec: BranchSpec, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(spec), indent=2, sort_keys=True) + "\n", encoding="utf-8")
