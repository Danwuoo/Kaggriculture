"""Exact consumed-context validation for the Boatlee S2 remediation selector."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import statistics
from typing import Any

import boatlee_remediation as remediation
from boatlee_selector import CONTROL_STEP_240, SELECTORS, decision, make_policy, write_selector
import formal_s1 as s1
from materialize import isolated_import, static_audit


HERE = s1.HERE
ROOT = s1.ROOT
RUN_ID = "e2_s2_boatlee_selector_20260815_v1"
DEFAULT_ROOT = HERE / "artifacts" / "remediation" / RUN_ID
SOURCE_ROOT = remediation.DEFAULT_ROOT
LANE = remediation.LANE
OTHER_LANE = remediation.OTHER_LANE
SPEC = SELECTORS[0]
WORKERS = 4


def _frozen_paths(root: Path) -> dict[str, Any]:
    return {
        "controls": {
            lane: root / "inputs" / "controls" / lane / "main.py"
            for lane in (LANE, OTHER_LANE)
        },
        "candidate": root / "inputs" / "candidate" / SPEC.candidate_id / "main.py",
        "opponents": {
            family: root / "inputs" / "opponents" / family / "main.py"
            for family in s1.SOURCE_PUBLIC_OPPONENTS
        },
    }


def _source_diagnostics() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = json.loads((SOURCE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    body = dict(manifest)
    embedded = body.pop("manifest_sha256", None)
    if embedded != s1.payload_hash(body):
        raise RuntimeError("source remediation manifest hash mismatch")
    summary = json.loads((SOURCE_ROOT / "summary.json").read_text(encoding="utf-8"))
    summary_body = dict(summary)
    summary_embedded = summary_body.pop("summary_sha256", None)
    if summary_embedded != s1.payload_hash(summary_body) or summary.get("complete") is not True:
        raise RuntimeError("source remediation summary is incomplete")
    evidence = json.loads((SOURCE_ROOT / "formal_evidence.json").read_text(encoding="utf-8"))["evidence"]
    return manifest, summary, evidence


def _step_241_diagnostics(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    jobs = json.loads((SOURCE_ROOT / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    result: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if job["variant"] != "step_241_only":
            continue
        path = SOURCE_ROOT / "diagnostics" / "shards" / f"{job['job_id']}.json"
        shard = remediation._valid_shard(path, job["job_id"])
        if shard is None or shard.get("status") != "complete":
            raise RuntimeError(f"invalid step-241 diagnostic shard: {path}")
        key = remediation._context_key(job["context"])
        paired = remediation._paired(shard["result"], evidence[key]["control"])
        base = {"farmer": ["PASS"], "hands": [], "market": CONTROL_STEP_240}
        feature_observation = {
            "step": 240,
            "player": int(job["context"]["seat"]),
            "market": {
                "prices": {"FERTILIZER": shard["public_features"]["market_price_FERTILIZER"]},
                "inventory": {"FERTILIZER": shard["public_features"]["market_inventory_FERTILIZER"]},
            },
        }
        branch, reason = decision(SPEC, feature_observation, base)
        result[key] = {
            "context": job["context"],
            "public_features": shard["public_features"],
            "step_241_result": shard["result"],
            "step_241_paired": paired["paired"],
            "predicted_branch": branch,
            "predicted_reason": reason,
        }
    if len(result) != 48:
        raise RuntimeError("selector requires exactly 48 diagnostic labels")
    return result


def _jobs(root: Path, artifact: dict[str, Any], labels: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for row in labels.values():
        job = {
            "kind": "consumed_seed_diagnostic",
            "evaluation_mode": "e2_s2_boatlee_atomic_ablation",
            "variant": "public_selector",
            "candidate_id": SPEC.candidate_id,
            "context": row["context"],
            "artifact": {"path": artifact["path"], "sha256": artifact["sha256"]},
            "run_root": str(root),
            "formal_fresh": False,
            "efficacy_claim": None,
        }
        job["job_id"] = "sel_" + s1.payload_hash(job)[:24]
        jobs.append(job)
    return sorted(jobs, key=lambda row: row["job_id"])


def prepare(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if root.exists():
        raise FileExistsError(f"new selector validation root required: {root}")
    source_manifest, source_summary, evidence = _source_diagnostics()
    labels = _step_241_diagnostics(evidence)
    engine = s1.RUNNER.assert_engine_current()
    if engine != source_manifest["engine_fingerprint"]:
        raise RuntimeError("selector engine differs from remediation diagnostics")
    root.mkdir(parents=True)
    frozen = _frozen_paths(root)
    controls = {
        lane: s1._copy_exact(
            SOURCE_ROOT / "inputs" / "controls" / lane / "main.py",
            frozen["controls"][lane],
        )
        for lane in (LANE, OTHER_LANE)
    }
    opponents: dict[str, Any] = {}
    for family, filenames in s1.PUBLIC_OPPONENT_FILES.items():
        source_dir = SOURCE_ROOT / "inputs" / "opponents" / family
        target_dir = frozen["opponents"][family].parent
        files = {name: s1._copy_exact(source_dir / name, target_dir / name) for name in filenames}
        opponents[family] = {"entrypoint": str(frozen["opponents"][family]), "files": files}
    base_source = frozen["controls"][LANE].read_text(encoding="utf-8")
    artifact = write_selector(base_source, SPEC, frozen["candidate"])
    audits = {"static": static_audit(frozen["candidate"]), "isolated_import": isolated_import(frozen["candidate"])}
    if not audits["static"]["pass"] or not audits["isolated_import"]["callable_agent"]:
        raise RuntimeError(f"selector standalone audit failed: {audits}")
    jobs = _jobs(root, artifact, labels)
    predicted = [row for row in labels.values() if row["predicted_branch"] == "intervene"]
    predicted_margins = [float(row["step_241_paired"]["margin_delta"]) for row in predicted]
    diagnostic_prediction = {
        "contexts": len(labels),
        "intervene": len(predicted),
        "abstain": len(labels) - len(predicted),
        "selected_margin_wdl": [
            sum(value > 0 for value in predicted_margins),
            sum(value == 0 for value in predicted_margins),
            sum(value < 0 for value in predicted_margins),
        ],
        "predicted_all_context_mean_margin": sum(predicted_margins) / len(labels),
        "predicted_worst_margin": min([0.0, *predicted_margins]),
        "efficacy_claim": None,
    }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "e2_s2_boatlee_selector_validation_manifest",
        "run_id": RUN_ID,
        "run_root": str(root),
        "selector": SPEC.payload() | {"candidate_id": SPEC.candidate_id},
        "artifact": artifact,
        "audits": audits,
        "controls": controls,
        "opponents": opponents,
        "engine_fingerprint": engine,
        "source_remediation_manifest_sha256": source_manifest["manifest_sha256"],
        "source_remediation_summary_sha256": source_summary["summary_sha256"],
        "formal_evidence_sha256": source_manifest["formal_evidence_sha256"],
        "labels_sha256": s1.payload_hash(labels),
        "jobs_sha256": s1.payload_hash(jobs),
        "job_count": len(jobs),
        "diagnostic_prediction": diagnostic_prediction,
        "implementation_hashes": {
            "boatlee_selector.py": s1.file_sha256(HERE / "boatlee_selector.py"),
            "boatlee_selector_validation.py": s1.file_sha256(Path(__file__)),
            "boatlee_remediation.py": s1.file_sha256(HERE / "boatlee_remediation.py"),
        },
        "new_formal_fresh_seeds_executed": False,
        "efficacy_claim": None,
        "later_tier_launched": False,
    }
    manifest["manifest_sha256"] = s1.payload_hash({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    s1.atomic_json(root / "manifest.json", manifest)
    s1.atomic_json(root / "labels.json", {"labels": labels, "labels_sha256": manifest["labels_sha256"]})
    s1.atomic_json(root / "formal_evidence.json", {"evidence": evidence, "formal_evidence_sha256": manifest["formal_evidence_sha256"]})
    s1.atomic_json(root / "jobs.json", {"jobs": jobs, "jobs_sha256": manifest["jobs_sha256"]})
    return {
        "pass": True, "run_id": RUN_ID,
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_id": SPEC.candidate_id,
        "artifact_sha256": artifact["sha256"],
        "diagnostic_prediction": diagnostic_prediction,
        "new_formal_fresh_seeds_executed": False,
    }


def _technical_parity(root: Path) -> dict[str, Any]:
    frozen = _frozen_paths(root)
    original = s1.RUNNER.opponent_path
    s1.RUNNER.opponent_path = lambda _lane, family: remediation._opponent_path(root, family)
    rows: list[dict[str, Any]] = []
    try:
        for seat in (0, 1):
            standalone = s1.RUNNER.run_game(
                LANE, frozen["candidate"], "other_incumbent", 811407, seat,
            )
            fast = s1.RUNNER.run_game(
                LANE, frozen["controls"][LANE], "other_incumbent", 811407, seat,
                policy_factory=lambda _module, base, _seat: make_policy(SPEC, base),
            )
            standalone_view = s1.RUNNER.behavior_view(standalone)
            fast_view = s1.RUNNER.behavior_view(fast)
            rows.append({
                "seat": seat,
                "equal": standalone_view == fast_view,
                "standalone": standalone_view,
                "fast": fast_view,
            })
    finally:
        s1.RUNNER.opponent_path = original
    return {"seed": 811407, "correctness_only": True, "rows": rows, "pass": all(row["equal"] for row in rows)}


def _failure_injection(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    bad_hash = copy.deepcopy(jobs[0])
    bad_hash["artifact"]["sha256"] = "0" * 64
    unknown_seed = copy.deepcopy(jobs[0])
    unknown_seed["context"] = {**unknown_seed["context"], "seed": 12345678}
    rows = [remediation._evaluate_job(bad_hash), remediation._evaluate_job(unknown_seed)]
    return {
        "rows": rows,
        "pass": all(row.get("status") == "infrastructure_failed" and row.get("efficacy") is None for row in rows),
    }


def run(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    if int(workers) != WORKERS:
        raise ValueError(f"selector validation requires exactly {WORKERS} workers")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    body = dict(manifest)
    embedded = body.pop("manifest_sha256", None)
    if embedded != s1.payload_hash(body):
        raise RuntimeError("selector validation manifest hash mismatch")
    implementation_paths = {
        "boatlee_selector.py": HERE / "boatlee_selector.py",
        "boatlee_selector_validation.py": Path(__file__),
        "boatlee_remediation.py": HERE / "boatlee_remediation.py",
    }
    if any(s1.file_sha256(implementation_paths[name]) != value for name, value in manifest["implementation_hashes"].items()):
        raise RuntimeError("selector implementation changed after prepare")
    jobs_payload = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
    jobs = jobs_payload["jobs"]
    labels = json.loads((root / "labels.json").read_text(encoding="utf-8"))["labels"]
    evidence = json.loads((root / "formal_evidence.json").read_text(encoding="utf-8"))["evidence"]
    if s1.payload_hash(jobs) != manifest["jobs_sha256"] or s1.payload_hash(labels) != manifest["labels_sha256"]:
        raise RuntimeError("selector jobs or labels changed after prepare")
    execution = {
        "schema_version": 1, "kind": "e2_s2_boatlee_selector_validation_execution",
        "run_id": RUN_ID, "workers": int(workers),
        "consumed_seed_diagnostics_executed": True,
        "new_formal_fresh_seeds_executed": False,
        "efficacy_claim": None, "later_tier_launched": False,
    }
    execution["execution_sha256"] = s1.payload_hash({key: value for key, value in execution.items() if key != "execution_sha256"})
    s1.atomic_json(root / "execution.json", execution)
    rows = remediation._run_jobs(root / "diagnostics", jobs, workers)
    if not all(row.get("status") == "complete" and row.get("result", {}).get("technical_status") == "complete" for row in rows):
        raise RuntimeError("selector validation jobs incomplete")
    by_id = {row["job_id"]: row for row in rows}
    margins: list[float] = []
    banks: list[float] = []
    branch_counts = {"intervene": 0, "incumbent": 0}
    prediction_rows: list[dict[str, Any]] = []
    for job in jobs:
        row = by_id[job["job_id"]]
        key = remediation._context_key(job["context"])
        control = evidence[key]["control"]
        label = labels[key]
        paired = remediation._paired(row["result"], control)
        margins.append(float(paired["paired"]["margin_delta"]))
        banks.append(float(paired["paired"]["own_bank_delta"]))
        branch = label["predicted_branch"]
        branch_counts[branch] += 1
        expected = label["step_241_result"] if branch == "intervene" else control
        prediction_rows.append({
            "context": job["context"], "branch": branch,
            "behavior_equal": remediation._behavior_identity(row["result"], expected),
            "features_equal": row["public_features"] == label["public_features"],
            "paired": paired["paired"],
        })
    audit_jobs = [
        job for job in jobs
        if int(job["context"]["seed"]) == 42284410
    ]
    worker1_rows = remediation._run_jobs(root / "worker1_audit", audit_jobs, 1)
    worker4_by_id = by_id
    worker_equality = all(
        remediation._behavior_identity(row["result"], worker4_by_id[row["job_id"]]["result"])
        and row["public_features"] == worker4_by_id[row["job_id"]]["public_features"]
        for row in worker1_rows
    )
    technical_parity = _technical_parity(root)
    failure_injection = _failure_injection(jobs)
    summary = {
        "schema_version": 1,
        "kind": "e2_s2_boatlee_selector_validation",
        "run_id": RUN_ID,
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_id": SPEC.candidate_id,
        "artifact_sha256": manifest["artifact"]["sha256"],
        "contexts": len(rows),
        "branch_counts": branch_counts,
        "paired_margin_wdl": [sum(value > 0 for value in margins), sum(value == 0 for value in margins), sum(value < 0 for value in margins)],
        "mean_paired_margin": sum(margins) / len(margins),
        "median_paired_margin": statistics.median(margins),
        "mean_own_bank_delta": sum(banks) / len(banks),
        "worst_paired_margin": min(margins),
        "actual_win_delta": sum(int(row["paired"]["win_delta"]) for row in prediction_rows),
        "prediction_parity": {
            "contexts": len(prediction_rows),
            "behavior_equal": sum(row["behavior_equal"] for row in prediction_rows),
            "features_equal": sum(row["features_equal"] for row in prediction_rows),
            "pass": all(row["behavior_equal"] and row["features_equal"] for row in prediction_rows),
        },
        "worker_1_vs_4": {"contexts": len(worker1_rows), "pass": worker_equality},
        "technical_seed_parity": technical_parity,
        "failure_injection": failure_injection,
        "maximum_run_p95_ms": max(row["result"]["summary"]["latency_ms"]["p95"] for row in rows),
        "maximum_call_ms": max(row["result"]["summary"]["latency_ms"]["max"] for row in rows),
        "max_market_orders": max(row["result"]["summary"]["max_market_orders"] for row in rows),
        "all_contexts_technical_valid": True,
        "public_state_only": True,
        "opponent_identity_used": False,
        "efficacy_claim": None,
        "consumed_seed_diagnostics_executed": True,
        "new_formal_fresh_seeds_executed": False,
        "ready_for_fresh_confirmation": (
            all(row["behavior_equal"] and row["features_equal"] for row in prediction_rows)
            and worker_equality and technical_parity["pass"] and failure_injection["pass"]
            and min(margins) >= 0
        ),
        "later_tier_launched": False,
    }
    summary["validation_sha256"] = s1.payload_hash({key: value for key, value in summary.items() if key != "validation_sha256"})
    s1.atomic_json(root / "selector_validation.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    run_parser.add_argument("--workers", type=int, required=True)
    args = parser.parse_args()
    result = prepare(args.output_root) if args.command == "prepare" else run(args.output_root, args.workers)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))


if __name__ == "__main__":
    main()
