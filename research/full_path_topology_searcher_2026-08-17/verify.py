"""Development acceptance verification without formal efficacy games."""

from __future__ import annotations

from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any

try:
    from .atlas import build_atlas, mutation_frontier
    from .authority import ROOT, validate_registry
    from .compiler import compile_candidate
    from .evaluator import classify_summary_fixture
    from .model import BranchSpec
except ImportError:
    from atlas import build_atlas, mutation_frontier
    from authority import ROOT, validate_registry
    from compiler import compile_candidate
    from evaluator import classify_summary_fixture
    from model import BranchSpec


LANE = Path(__file__).resolve().parent


def calibration() -> dict[str, Any]:
    fixtures = json.loads((LANE / "calibration_fixtures.json").read_text(encoding="utf-8"))["fixtures"]
    classified = [classify_summary_fixture(value) for value in fixtures]
    e2 = json.loads((ROOT / "research/dual_incumbent_topology_search_2026-08-14/e2/remediation_verification.json").read_text(encoding="utf-8"))
    selector = e2["selector_validation"]
    e2_result = {
        "id": "boatlee_e2_frozen_selector", "evidence_level": "consumed_paired",
        "paired_margin_wdl": selector["paired_margin_wdl"], "actual_win_delta": selector["actual_win_delta"],
        "proposal_rank_signal": True, "efficacy_eligible": False,
        "rejection_reason": "zero_actual_win_delta_and_consumed_contexts",
    }
    passed = all(not row["efficacy_eligible"] for row in classified) and not e2_result["efficacy_eligible"]
    return {"passed": passed, "summary_fixtures": classified, "e2": e2_result,
            "provenance_gap": "No local raw c27 13-7 rows or fixed-horizon-25 rows; summary fixtures test classification only."}


def sample_branch() -> BranchSpec:
    return BranchSpec.from_dict({
        "lane": "v27_current_meta", "decision_step": 240,
        "trigger": {"all": [{"path": "market.prices.FERTILIZER", "op": "ge", "value": 1}]},
        "motif": {"kind": "market_edit", "patches": [{"step": 240, "market_mode": "append", "market": [["SELL", "FERTILIZER", 1]]}]},
        "displaced_actions": [],
        "continuation": {"mode": "immediate", "min_end_step": 240, "max_end_step": 240, "rejoin": {}},
        "fallback": "incumbent", "parent_node_id": "v27_current_meta:spine:240",
        "evidence_ids": ["full_action_trie_summary"], "max_horizon": 1,
    })


def compiler_smoke() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="full-path-technical-") as temporary:
        output = Path(temporary) / "main.py"
        result = compile_candidate(sample_branch(), output)
        spec = importlib.util.spec_from_file_location("full_path_candidate_smoke", output)
        if spec is None or spec.loader is None:
            raise ImportError(output)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result["path"] = "<temporary>/main.py"
        return {**result, "isolated_import": True, "callable_agent": callable(module.agent),
                "callable_server_entrypoint": callable(module._kaggle_submission_entrypoint)}


def run(include_entropy: bool = False) -> dict[str, Any]:
    authority = validate_registry()
    atlas = build_atlas(include_channel_entropy=include_entropy)
    expected_boundary = any(
        int(row.get("turn", -1)) == 78 and int(row.get("children", -1)) == 2 and int(row.get("aggregate_child_support", -1)) == 97
        for row in atlas["reported_branch_boundaries"]
    )
    atlas_checks = {
        "source_representative_tapes_227": atlas["source_representative_tapes"] == 227,
        "deduplicated_representative_tapes_225": atlas["representative_tapes"] == 225,
        "unique_full_action_digests_225": atlas["unique_full_action_digests"] == 225,
        "exact_duplicate_tapes_removed_2": atlas["exact_duplicate_tapes_removed"] == 2,
        "nodes_102803": atlas["nodes"] == 102803,
        "depth_719": atlas["max_depth"] == 719,
        "turn_78_deduplicated_boundary": expected_boundary,
        "legacy_support_statistics_not_used": atlas["legacy_support_statistics_used"] is False,
    }
    motifs = json.loads((LANE / "frontier_motifs.json").read_text(encoding="utf-8"))["motifs"]
    ranked = mutation_frontier(motifs)
    calibrations = calibration()
    compiler = compiler_smoke()
    passed = (authority["passed"] and all(atlas_checks.values()) and calibrations["passed"]
              and compiler["passed"] and compiler["static_audit"]["passed"] and compiler["isolated_import"])
    return {
        "schema_version": 1, "decision": "READY_FOR_PROPOSAL_ONLY" if passed else "DEVELOPMENT_REMEDIATION_REQUIRED",
        "formal_fresh_confirmation_authorized": False, "new_formal_seeds_selected": [], "new_formal_seeds_executed": False,
        "authority": authority, "atlas": {key: value for key, value in atlas.items() if key != "channel_entropy_by_step"},
        "atlas_checks": atlas_checks, "calibration": calibrations, "compiler": compiler,
        "proposal_frontier": ranked, "pool_lanes": False, "passed": passed,
    }


def write_report(path: Path, include_entropy: bool = False) -> dict[str, Any]:
    report = run(include_entropy=include_entropy)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
