"""Development acceptance verification without formal efficacy games."""

from __future__ import annotations

from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import tempfile
import hashlib
import subprocess
import re
from typing import Any

try:
    from .atlas import build_atlas
    from .authority import ROOT, canonical_utf8_lf, validate_registry
    from .compiler import compile_candidate
    from .evaluator import classify_summary_fixture
    from .model import BranchSpec
    from .proposal import proposal_oracle
except ImportError:
    from atlas import build_atlas
    from authority import ROOT, canonical_utf8_lf, validate_registry
    from compiler import compile_candidate
    from evaluator import classify_summary_fixture
    from model import BranchSpec
    from proposal import proposal_oracle


LANE = Path(__file__).resolve().parent


def calibration() -> dict[str, Any]:
    fixtures = json.loads((LANE / "calibration_fixtures.json").read_text(encoding="utf-8"))["fixtures"]
    classified = [classify_summary_fixture(value) for value in fixtures]
    e2 = json.loads((ROOT / "research/dual_incumbent_topology_search_2026-08-14/e2/remediation_verification.json").read_text(encoding="utf-8"))
    selector = e2["selector_validation"]
    e2_result = {
        "id": "boatlee_e2_frozen_selector", "evidence_level": "consumed_paired",
        "anchor_role": "margin_only_false_positive_control",
        "paired_margin_wdl": selector["paired_margin_wdl"], "actual_win_delta": selector["actual_win_delta"],
        "calibration_status": "rejected_as_required", "efficacy_eligible": False,
        "rejection_reason": "zero_actual_win_delta_and_consumed_contexts",
    }
    safety_passed = all(not row["efficacy_eligible"] for row in classified) and not e2_result["efficacy_eligible"]
    return {"status": "PARTIAL_BLOCKED_RAW_ANCHORS", "safety_passed": safety_passed,
            "three_anchor_calibration_passed": False, "summary_fixtures": classified, "e2": e2_result,
            "provenance_gap": "No local raw c27 13-7 rows or fixed-horizon-25 rows; those anchors remain uncalibrated."}


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
    loss_rows = json.loads((ROOT / "research/job_value_residual_2026-08-12/artifacts/discovery_windows.json").read_text(encoding="utf-8"))["rows"]
    proposal_atlas = atlas if include_entropy else build_atlas(include_channel_entropy=True)
    proposal_oracles = {
        lane: proposal_oracle(motifs, lane, proposal_atlas, loss_rows)
        for lane in ("v27_current_meta", "boatlee_v16_rc2_market_relay")
    }
    proposal_ready = all(value["status"] == "READY" and value["ranked_proposal_count"] > 0
                         for value in proposal_oracles.values())
    calibrations = calibration()
    compiler = compiler_smoke()
    passed = (authority["passed"] and all(atlas_checks.values()) and calibrations["safety_passed"]
              and compiler["passed"] and compiler["static_audit"]["passed"] and compiler["isolated_import"])
    return {
        "schema_version": 2,
        "decision": "REPRODUCIBLE_BRANCH_EXPERIMENTATION_SUBSTRATE_ONLY" if passed else "DEVELOPMENT_REMEDIATION_REQUIRED",
        "status_matrix": {
            "v1_design_safety": "PASS_WITH_CAVEATS" if passed else "FAIL",
            "reproducible_development_verification": "PASS" if passed else "FAIL",
            "expected_full_path_architecture": "PARTIAL_IMPLEMENTATION",
            "proposal_oracle": "READY_LOCUS_ONLY" if proposal_ready else "BLOCKED_MISSING_EVIDENCE",
            "three_anchor_calibration": "BLOCKED_RAW_ROWS",
            "formal_efficacy": "NOT_AUTHORIZED",
        },
        "architecture_capabilities": {
            "incumbent_linear_spines": True, "single_bounded_branch_compilation": True,
            "multi_branch_conditional_routing": False, "best_policy_topology_materialized": False,
        },
        "formal_fresh_confirmation_authorized": False, "new_formal_seeds_selected": [], "new_formal_seeds_executed": False,
        "authority": authority, "atlas": {key: value for key, value in atlas.items() if key != "channel_entropy_by_step"},
        "atlas_checks": atlas_checks, "calibration": calibrations, "compiler": compiler,
        "proposal_oracles": proposal_oracles, "pool_lanes": False, "passed": passed,
    }


def source_inventory() -> dict[str, Any]:
    lane_relative = LANE.relative_to(ROOT).as_posix()
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", ".gitattributes", "full_path_topology_searching_report_2026-08-17.md",
         "topology_path.md", lane_relative], cwd=ROOT, text=True).splitlines()
    paths = [ROOT / value for value in sorted(set(tracked))
             if not value.endswith("development_verification_summary.json")]
    entries = []
    for path in paths:
        raw = canonical_utf8_lf(path.read_bytes())
        entries.append({"path": path.relative_to(ROOT).as_posix(), "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest()})
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"file_count": len(entries), "sha256": hashlib.sha256(encoded).hexdigest(), "files": entries}


def run_verification_commands() -> list[dict[str, Any]]:
    commands = [
        (["python", "-m", "unittest", "discover", "-s", "tests", "-v"], LANE, 60, "unittest"),
        (["python", "-m", "unittest", "test_async_v3", "-v"], ROOT / "research/dual_incumbent_topology_search_2026-08-14/async_v3", 23, "unittest"),
        (["python", "-m", "unittest", "research.main_approach.test_development_sources", "-v"], ROOT, 3, "unittest"),
        (["python", "cli.py", "validate"], LANE, 1, "validation"),
    ]
    runs = []
    for command, cwd, minimum_count, kind in commands:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        output = completed.stdout + completed.stderr
        matches = re.findall(r"Ran (\d+) tests?", output)
        if kind == "unittest":
            count = int(matches[-1]) if matches else 0
            semantic_pass = count >= minimum_count
        else:
            try:
                validation = json.loads(completed.stdout)
                semantic_pass = validation["authority"]["passed"] is True and validation["calibration"]["safety_passed"] is True
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                semantic_pass = False
            count = 1 if semantic_pass else 0
        passed = completed.returncode == 0 and semantic_pass
        run = {
            "command": subprocess.list2cmdline(command), "working_directory": cwd.relative_to(ROOT).as_posix() or ".",
            "exit_code": completed.returncode, "minimum_required": minimum_count,
            "passed": count if passed else 0, "failed": 0 if passed else max(1, count),
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        }
        runs.append(run)
        if not passed:
            raise RuntimeError(f"verification command failed: {run}")
    return runs


def tracked_summary(report: dict[str, Any], verification_runs: list[dict[str, Any]]) -> dict[str, Any]:
    inventory = source_inventory()
    compiler = report["compiler"]
    atlas = report["atlas"]
    base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                 text=True, check=True).stdout.strip()
    return {
        "schema_version": 1, "verified_date": "2026-08-20", "base_commit_at_verification": base_commit,
        "source_inventory_policy": "git_tracked_sources_only",
        "source_inventory_sha256": inventory["sha256"], "source_file_count": inventory["file_count"],
        "decision": report["decision"], "status_matrix": report["status_matrix"],
        "formal_efficacy_authorized": False,
        "atlas": {"source_representatives": atlas["source_representative_tapes"],
                  "unique_full_action_tapes": atlas["representative_tapes"], "nodes": atlas["nodes"],
                  "max_depth": atlas["max_depth"], "structure_digest": atlas["deduplicated_structure_digest"],
                  "input_inventory_sha256": report["authority"]["collections"]["atlas_inputs"]["inventory_sha256"]},
        "candidate_smoke": {"bytes": compiler["bytes"], "sha256": compiler["sha256"],
                            "isolated_import": compiler["isolated_import"], "both_entrypoints": compiler["callable_agent"] and compiler["callable_server_entrypoint"]},
        "calibration": {"status": report["calibration"]["status"],
                        "three_anchor_calibration_passed": False},
        "proposal_oracles": {lane: {"status": value["status"], "ranked_proposal_count": value["ranked_proposal_count"]}
                             for lane, value in report["proposal_oracles"].items()},
        "verification_runs": verification_runs,
    }


def write_report(path: Path, include_entropy: bool = False) -> dict[str, Any]:
    report = run(include_entropy=include_entropy)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return report
