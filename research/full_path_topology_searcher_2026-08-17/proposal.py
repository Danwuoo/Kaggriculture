"""Evidence-derived proposal diagnostics and bounded serialization."""

from __future__ import annotations

import ast
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from .model import BranchSpec
except ImportError:
    from model import BranchSpec


ROOT = Path(__file__).resolve().parents[2]
FRONTIER_CODE_EVIDENCE = Path(__file__).resolve().parent / "frontier_code_evidence.json"


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
        "status": "derived_consumed_negative_diagnostic",
        "candidate_direction": "known_negative_only",
        "positive_branch_label": False,
        "negative_lane_rows": len(lane_negative),
        "matching_rows": len(matched), "distinct_contexts": len(contexts), "families": sorted(families),
    }


def _source_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
    return symbols


def _frontier_relevance(motif: Mapping[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """Validate frozen source hashes and audited semantic symbols, then deduplicate lineages."""
    try:
        evidence = json.loads(FRONTIER_CODE_EVIDENCE.read_text(encoding="utf-8"))
        if evidence.get("schema_version") != 1 or evidence.get("kind") != "audited_frontier_code_motif_matches":
            raise ValueError("unsupported frontier-code evidence schema")
        policy = evidence.get("policy", {})
        if (policy.get("efficacy_signal") is not False or policy.get("priority_scalars_allowed") is not False
                or policy.get("source_hash_and_symbol_match_required") is not True):
            raise ValueError("frontier-code evidence policy is not fail-closed")
        minimum = policy.get("minimum_independent_lineages")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 2:
            raise ValueError("minimum independent lineage count must be at least two")
        source_rows = evidence.get("sources", [])
        if not isinstance(source_rows, list) or not source_rows:
            raise ValueError("frontier-code evidence requires sources")
        sources: dict[str, dict[str, Any]] = {}
        all_lineages: set[str] = set()
        for row in source_rows:
            if not isinstance(row, dict) or set(row) != {"id", "lineage", "path", "sha256", "bytes"}:
                raise ValueError("frontier source schema is closed")
            source_id = row["id"]
            lineage = row["lineage"]
            if not isinstance(source_id, str) or source_id in sources or not isinstance(lineage, str) or not lineage:
                raise ValueError("frontier source IDs must be unique and every lineage must be a nonempty string")
            path = (ROOT / row["path"]).resolve()
            public_root = (ROOT / "research/public_agents").resolve()
            try:
                path.relative_to(public_root)
            except ValueError as exc:
                raise ValueError("frontier source escapes public-agent root") from exc
            raw = path.read_bytes()
            if (len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]):
                raise ValueError(f"frontier source drift: {source_id}")
            sources[source_id] = {**row, "symbols": _source_symbols(path)}
            all_lineages.add(lineage)
        motif_row = evidence.get("motifs", {}).get(motif.get("id"), {})
        matches = motif_row.get("matches", []) if isinstance(motif_row, dict) else []
        verified: list[dict[str, Any]] = []
        lineages: set[str] = set()
        seen_sources: set[str] = set()
        for match in matches:
            if not isinstance(match, dict) or set(match) != {"source_id", "required_symbols"}:
                raise ValueError("frontier motif match schema is closed")
            source_id = match["source_id"]
            required = match["required_symbols"]
            if source_id in seen_sources or source_id not in sources or not isinstance(required, list) or not required:
                raise ValueError("frontier motif matches require unique registered sources and symbols")
            if any(not isinstance(symbol, str) or not symbol for symbol in required):
                raise ValueError("frontier motif symbols must be nonempty strings")
            seen_sources.add(source_id)
            missing = sorted(set(required) - sources[source_id]["symbols"])
            if missing:
                raise ValueError(f"frontier semantic symbols missing for {source_id}: {missing}")
            lineage = sources[source_id]["lineage"]
            lineages.add(lineage)
            verified.append({"source_id": source_id, "lineage": lineage, "required_symbols": sorted(required)})
        if len(lineages) < minimum:
            return None, {
                "status": "insufficient_independent_lineages",
                "verified_independent_sources": sorted(seen_sources),
                "verified_independent_lineages": sorted(lineages),
                "minimum_required": minimum,
            }
        score = len(lineages) / len(all_lineages)
        return round(score, 8), {
            "status": "derived_hash_and_symbol_verified",
            "evidence_level": policy.get("evidence_level"),
            "efficacy_signal": False,
            "verified_matches": verified,
            "verified_independent_sources": sorted(seen_sources),
            "verified_independent_lineages": sorted(lineages),
            "minimum_required": minimum,
            "frontier_population_lineages": len(all_lineages),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError, SyntaxError) as exc:
        return None, {"status": "frontier_code_evidence_invalid", "reason": str(exc), "minimum_required": 2}


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
        frontier, frontier_evidence = _frontier_relevance(motif)
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
                "frontier_relevance": frontier_evidence,
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
        "ranking_scope": "motif_locus_only_not_action_direction",
        "status": "READY" if eligible else "BLOCKED_MISSING_EVIDENCE",
        "ranked_proposal_count": len(eligible), "proposals": proposals,
    }


def write_branch(spec: BranchSpec, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(spec), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
