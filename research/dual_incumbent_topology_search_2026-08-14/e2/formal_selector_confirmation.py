"""Detached fresh confirmation for the frozen Boatlee public selector."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Any

import formal_s1 as s1


HERE = s1.HERE
ROOT = s1.ROOT
RUN_ID = "e2_s2_selector_confirmation_20260820_v1"
DEFAULT_ROOT = HERE / "artifacts" / "formal" / RUN_ID
SEED_REGISTRY = HERE / "selector_confirmation_seed_registry_20260820.json"
REMEDIATION_REGISTRY = HERE / "remediation_candidate_registry.json"
REMEDIATION_VERIFICATION = HERE / "remediation_verification.json"
SOURCE_RUN = HERE / "artifacts" / "remediation" / "e2_s2_boatlee_selector_20260815_v1"
LANE = "boatlee_v16_rc2_market_relay"
OTHER_LANE = "v27_current_meta"
CANDIDATE_ID = "e2boatlee_7f591d609cf14d89e6aa1599"
SOURCE_CANDIDATE = SOURCE_RUN / "inputs" / "candidate" / CANDIDATE_ID / "main.py"
SOURCE_CONTROLS = {
    LANE: SOURCE_RUN / "inputs" / "controls" / LANE / "main.py",
    OTHER_LANE: SOURCE_RUN / "inputs" / "controls" / OTHER_LANE / "main.py",
}
SOURCE_OPPONENT_ROOT = SOURCE_RUN / "inputs" / "opponents"
OPPONENTS = s1.OPPONENTS
SEATS = s1.SEATS
WORKER_LIMIT = s1.WORKER_LIMIT
EXPECTED_CANDIDATE_SHA256 = "b4ef9bff8cbba2dfaccacc320a32f707006158fcf905c02db02ad89fe0f6099a"
EXPECTED_CONTROL_SHA256 = "69ce4f657df5a168c676acfa4f9089a373bc291fe3486950de0bca16ad042213"


def _canonical_authority(path: Path, field: str) -> tuple[dict[str, Any], str]:
    row = json.loads(path.read_text(encoding="utf-8"))
    body = dict(row)
    embedded = body.pop(field, None)
    observed = s1.payload_hash(body)
    if embedded != observed:
        raise RuntimeError(f"authority canonical hash mismatch: {path.name}")
    return row, observed


def _seed_records() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    registry = json.loads(SEED_REGISTRY.read_text(encoding="utf-8"))
    records = registry.get("seeds", [])
    values = [int(row["seed"]) for row in records]
    excluded = {int(value) for value in registry.get("excluded_consumed_seeds", [])}
    if len(values) != 2 or len(set(values)) != 2:
        raise RuntimeError("selector confirmation requires exactly two distinct fresh seeds")
    if set(values) & excluded:
        raise RuntimeError("consumed seed entered selector confirmation")
    if any(
        row.get("classification") != "formal_fresh"
        or row.get("fresh") is not True
        or int(row.get("preselection_repository_hits", -1)) != 0
        or row.get("executed") is not False
        for row in records
    ):
        raise RuntimeError("fresh seed registry is not in the pre-execution state")
    return records, registry


def _freshness_scan(registry: dict[str, Any], output_root: Path) -> dict[str, Any]:
    excluded = {SEED_REGISTRY.resolve()}
    if output_root.exists():
        excluded.update(path.resolve() for path in output_root.rglob("*") if path.is_file())
    rows = []
    for item in registry["seeds"]:
        seed = int(item["seed"])
        hits: list[str] = []
        for raw_root in registry["freshness_scan_roots"]:
            scan_root = Path(raw_root)
            if not scan_root.exists():
                continue
            completed = subprocess.run(
                ["rg", "-uu", "-l", "-F", "--", str(seed), str(scan_root)],
                capture_output=True, text=True,
            )
            if completed.returncode not in (0, 1):
                raise RuntimeError(f"freshness scan failed for {scan_root}")
            for value in completed.stdout.splitlines():
                path = Path(value).resolve()
                if path not in excluded:
                    hits.append(str(path))
        rows.append({"seed": seed, "unexpected_hits": sorted(set(hits)), "pass": not hits})
    return {"rows": rows, "pass": all(row["pass"] for row in rows)}


def _frozen_paths(root: Path) -> dict[str, Any]:
    return {
        "controls": {
            lane: root / "inputs" / "controls" / lane / "main.py"
            for lane in (LANE, OTHER_LANE)
        },
        "candidate": root / "inputs" / "candidate" / CANDIDATE_ID / "main.py",
        "opponents": {
            family: root / "inputs" / "opponents" / family / "main.py"
            for family in s1.SOURCE_PUBLIC_OPPONENTS
        },
    }


def _jobs(root: Path, records: list[dict[str, Any]], frozen: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    controls: list[dict[str, Any]] = []
    for opponent in OPPONENTS:
        for seed_record in records:
            for seat in SEATS:
                job = {
                    "kind": "control", "evaluation_mode": "e2_s1_formal_exact",
                    "context": {"lane": LANE, "opponent": opponent, "seed": int(seed_record["seed"]), "seat": seat},
                    "seed_record": seed_record,
                    "artifact": {"path": str(frozen["controls"][LANE]), "sha256": s1.file_sha256(frozen["controls"][LANE])},
                }
                job["job_id"] = s1.canonical_job_id(job)
                controls.append(job)
    control_by_context = {
        (row["context"]["opponent"], row["context"]["seed"], row["context"]["seat"]): row["job_id"]
        for row in controls
    }
    candidates: list[dict[str, Any]] = []
    for opponent in OPPONENTS:
        for seed_record in records:
            for seat in SEATS:
                context = {"lane": LANE, "opponent": opponent, "seed": int(seed_record["seed"]), "seat": seat}
                job = {
                    "kind": "candidate", "evaluation_mode": "e2_s1_formal_exact",
                    "candidate_id": CANDIDATE_ID, "context": context,
                    "seed_record": seed_record,
                    "artifact": {"path": str(frozen["candidate"]), "sha256": s1.file_sha256(frozen["candidate"])},
                    "control_job_id": control_by_context[(opponent, int(seed_record["seed"]), seat)],
                    "control_cache_path": str(root / "control_cache" / f"{LANE}.json"),
                }
                job["job_id"] = s1.canonical_job_id(job)
                candidates.append(job)
    return sorted(controls, key=lambda row: row["job_id"]), sorted(candidates, key=lambda row: row["job_id"])


def _load_frozen(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    protocol_body = {key: value for key, value in protocol.items() if key != "protocol_sha256"}
    if manifest.get("manifest_sha256") != s1.payload_hash(manifest_body):
        raise RuntimeError("confirmation manifest canonical hash mismatch")
    if protocol.get("protocol_sha256") != s1.payload_hash(protocol_body):
        raise RuntimeError("confirmation protocol canonical hash mismatch")
    if manifest.get("protocol_sha256") != protocol.get("protocol_sha256"):
        raise RuntimeError("confirmation manifest/protocol identity mismatch")
    if protocol.get("formal_authorized") is not True or protocol.get("status") != "frozen_authorized_confirmation":
        raise PermissionError("confirmation protocol is not explicitly authorized")
    expected = s1.payload_hash({"controls": manifest["control_jobs"], "candidates": manifest["candidate_jobs"]})
    if protocol.get("job_manifest_sha256") != expected:
        raise RuntimeError("confirmation job manifest hash mismatch")
    return manifest, protocol


def _authority() -> dict[str, Any]:
    registry, registry_hash = _canonical_authority(REMEDIATION_REGISTRY, "registry_sha256")
    verification, verification_hash = _canonical_authority(REMEDIATION_VERIFICATION, "remediation_verification_sha256")
    selector = registry["lanes"][LANE]["frozen_selector"]
    checks = {
        "ready": verification.get("decision") == "READY_FOR_E2_S2_FRESH_CONFIRMATION",
        "selector_ready": verification["selector_validation"].get("ready_for_fresh_confirmation") is True,
        "candidate_id": selector.get("candidate_id") == CANDIDATE_ID,
        "candidate_hash": selector.get("standalone_sha256") == EXPECTED_CANDIDATE_SHA256 == s1.file_sha256(SOURCE_CANDIDATE),
        "control_hash": verification["controls"][LANE] == EXPECTED_CONTROL_SHA256 == s1.file_sha256(SOURCE_CONTROLS[LANE]),
        "thresholds": selector.get("thresholds") == {"max_fertilizer_price": 84, "min_fertilizer_inventory": 10082},
        "no_prior_fresh_confirmation": verification.get("new_formal_fresh_seeds_executed") is False,
        "no_later_tier": verification.get("later_tier_launched") is False,
    }
    return {"pass": all(checks.values()), "checks": checks, "registry_canonical_sha256": registry_hash, "verification_canonical_sha256": verification_hash}


def preflight(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    if not 1 <= int(workers) <= WORKER_LIMIT:
        raise ValueError(f"workers must be in 1..{WORKER_LIMIT}")
    if root.exists():
        raise FileExistsError(f"new confirmation root required: {root}")
    authority = _authority()
    if not authority["pass"]:
        raise RuntimeError(f"remediation authority failed: {authority}")
    records, registry = _seed_records()
    scan = _freshness_scan(registry, root)
    if not scan["pass"]:
        raise RuntimeError(f"selected confirmation seed is not fresh: {scan}")
    engine = s1.RUNNER.assert_engine_current()
    root.mkdir(parents=True)
    frozen = _frozen_paths(root)
    copied: dict[str, Any] = {
        "controls": {lane: s1._copy_exact(SOURCE_CONTROLS[lane], frozen["controls"][lane]) for lane in (LANE, OTHER_LANE)},
        "candidate": s1._copy_exact(SOURCE_CANDIDATE, frozen["candidate"]),
        "opponents": {},
    }
    for family, filenames in s1.PUBLIC_OPPONENT_FILES.items():
        source_dir = SOURCE_OPPONENT_ROOT / family
        target_dir = frozen["opponents"][family].parent
        files = {name: s1._copy_exact(source_dir / name, target_dir / name) for name in filenames}
        copied["opponents"][family] = {"entrypoint": str(frozen["opponents"][family]), "files": files, "package_sha256": s1.payload_hash(files)}
    direct_imports = {}
    for family in s1.SOURCE_PUBLIC_OPPONENTS:
        try:
            _module, agent, _latency = s1.RUNNER.harness.load_agent(frozen["opponents"][family], f"confirmation_preflight_{family}")
            direct_imports[family] = {"callable_agent": callable(agent), "pass": callable(agent)}
        except Exception as error:
            direct_imports[family] = {"callable_agent": False, "pass": False, "error": f"{type(error).__name__}: {error}"}
    if not all(row["pass"] for row in direct_imports.values()):
        raise RuntimeError(f"opponent import smoke failed: {direct_imports}")
    spawned_imports = s1._spawn_import_smoke(frozen, int(workers))
    if not spawned_imports["pass"]:
        raise RuntimeError(f"spawned opponent import smoke failed: {spawned_imports}")
    controls, candidates = _jobs(root, records, frozen)
    expected = len(OPPONENTS) * len(records) * len(SEATS)
    if len(controls) != expected or len(candidates) != expected:
        raise RuntimeError("unexpected confirmation job count")
    protocol: dict[str, Any] = {
        "schema_version": 1, "kind": "e2_s2_selector_fresh_confirmation_protocol",
        "status": "frozen_authorized_confirmation", "formal_authorized": True,
        "authorization": "User explicitly instructed on 2026-08-20: 正式 fresh search，確定指令成功啟動後就停止監看",
        "run_id": RUN_ID, "run_root": str(root), "workers": int(workers),
        "formal_fresh_seeds_executed": False, "evaluation_seeds": [int(row["seed"]) for row in records],
        "seats": list(SEATS), "opponents": list(OPPONENTS),
        "lane": LANE, "candidate_id": CANDIDATE_ID, "pool_lanes": False,
        "seed_registry": {"path": str(SEED_REGISTRY), "sha256": s1.file_sha256(SEED_REGISTRY), "records": records},
        "freshness_scan": scan, "authority": authority, "engine_fingerprint": engine,
        "control_artifacts": copied["controls"], "candidate_artifact": copied["candidate"],
        "opponent_artifacts": copied["opponents"], "opponent_import_smoke": direct_imports,
        "spawned_opponent_import_smoke": spawned_imports,
        "job_counts": {"controls": expected, "candidates": expected, "total_games": expected * 2},
        "minimum_support_and_uncertainty_contract": {
            "minimum_matched_contexts": 16, "minimum_independent_seeds": 2,
            "minimum_opponent_families": 4, "both_seats_required": True,
            "positive_signal": "paired_margin_wdl positive count must exceed negative count",
            "tail_falsifier": "any negative Roman context or renewed seat-sensitive family tail rejects confirmation",
            "uncertainty_rule": "report two-sided 95% Wilson interval for positive sign rate among nonzero contexts; no automatic promotion",
            "technical_gate": "all 32 games DONE/DONE with no candidate exception, timeout, malformed action, overage exhaustion, or market overflow",
            "automatic_later_tier_launch": False,
        },
        "implementation_hashes": {"formal_selector_confirmation.py": s1.file_sha256(Path(__file__)), "formal_s1.py": s1.file_sha256(HERE / "formal_s1.py")},
        "later_tier_launched": False,
    }
    protocol["job_manifest_sha256"] = s1.payload_hash({"controls": controls, "candidates": candidates})
    protocol["protocol_sha256"] = s1.payload_hash({key: value for key, value in protocol.items() if key != "protocol_sha256"})
    manifest: dict[str, Any] = {
        "schema_version": 1, "kind": "e2_s2_selector_fresh_confirmation_manifest",
        "run_id": RUN_ID, "run_root": str(root), "protocol_sha256": protocol["protocol_sha256"],
        "engine_sha256": s1.payload_hash(engine), "seed_registry_sha256": s1.file_sha256(SEED_REGISTRY),
        "jobs_sha256": protocol["job_manifest_sha256"], "control_jobs": controls, "candidate_jobs": candidates,
        "formal_fresh_seeds_executed": False, "later_tier_launched": False,
    }
    manifest["manifest_sha256"] = s1.payload_hash({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    s1.atomic_json(root / "protocol.json", protocol)
    s1.atomic_json(root / "manifest.json", manifest)
    s1.atomic_json(root / "jobs" / "controls.json", {"manifest_sha256": manifest["manifest_sha256"], "jobs": controls, "job_manifest_sha256": s1.payload_hash(controls)})
    s1.atomic_json(root / "jobs" / "candidates.json", {"manifest_sha256": manifest["manifest_sha256"], "jobs": candidates, "job_manifest_sha256": s1.payload_hash(candidates)})
    dry = {"schema_version": 1, "kind": "e2_s2_selector_confirmation_dry_preflight", "run_id": RUN_ID, "pass": True, "formal_authorized": True, "formal_fresh_seeds_executed": False, "manifest_sha256": manifest["manifest_sha256"], "protocol_sha256": protocol["protocol_sha256"], "registry_sha256": s1.file_sha256(SEED_REGISTRY), "job_counts": protocol["job_counts"], "freshness_scan": scan}
    dry["dry_preflight_sha256"] = s1.payload_hash({key: value for key, value in dry.items() if key != "dry_preflight_sha256"})
    s1.atomic_json(root / "dry_preflight.json", dry)
    return dry


def validate_preflight(root: Path) -> dict[str, Any]:
    manifest, protocol = _load_frozen(root.resolve())
    jobs = manifest["control_jobs"] + manifest["candidate_jobs"]
    checks = {
        "run_id": manifest["run_id"] == RUN_ID == protocol["run_id"],
        "two_fresh_seeds": len(protocol["evaluation_seeds"]) == 2 and len(set(protocol["evaluation_seeds"])) == 2,
        "job_count": len(manifest["control_jobs"]) == 16 and len(manifest["candidate_jobs"]) == 16,
        "both_seats": {row["context"]["seat"] for row in jobs} == {0, 1},
        "four_families": {row["context"]["opponent"] for row in jobs} == set(OPPONENTS),
        "lane_isolated": all(row["context"]["lane"] == LANE for row in jobs),
        "artifacts_match": all(s1.file_sha256(Path(row["artifact"]["path"])) == row["artifact"]["sha256"] for row in jobs),
        "candidate_identity": all(row.get("candidate_id") == CANDIDATE_ID for row in manifest["candidate_jobs"]),
        "candidate_hash": protocol["candidate_artifact"]["sha256"] == EXPECTED_CANDIDATE_SHA256,
        "control_hash": protocol["control_artifacts"][LANE]["sha256"] == EXPECTED_CONTROL_SHA256,
        "seed_registry": s1.file_sha256(SEED_REGISTRY) == protocol["seed_registry"]["sha256"],
        "opponents_match": all(s1.file_sha256(Path(file_row["path"])) == file_row["sha256"] for package in protocol["opponent_artifacts"].values() for file_row in package["files"].values()),
        "imports": all(row["pass"] for row in protocol["opponent_import_smoke"].values()) and protocol["spawned_opponent_import_smoke"]["pass"] is True,
        "engine": s1.RUNNER.assert_engine_current() == protocol["engine_fingerprint"],
        "implementation": s1.file_sha256(Path(__file__)) == protocol["implementation_hashes"]["formal_selector_confirmation.py"] and s1.file_sha256(HERE / "formal_s1.py") == protocol["implementation_hashes"]["formal_s1.py"],
        "not_executed": manifest["formal_fresh_seeds_executed"] is False and protocol["formal_fresh_seeds_executed"] is False,
    }
    return {"pass": all(checks.values()), "checks": checks, "manifest_sha256": manifest["manifest_sha256"], "protocol_sha256": protocol["protocol_sha256"], "job_counts": protocol["job_counts"], "formal_fresh_seeds_executed": False}


def _summary(jobs: list[dict[str, Any]], rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    results = [rows[job["job_id"]]["result"] for job in jobs]
    margins = [float(row["paired"]["margin_delta"]) for row in results]
    positives = sum(value > 0 for value in margins)
    negatives = sum(value < 0 for value in margins)
    nonzero = positives + negatives
    if nonzero:
        z = 1.959963984540054
        phat = positives / nonzero
        center = (phat + z * z / (2 * nonzero)) / (1 + z * z / nonzero)
        radius = z * math.sqrt(phat * (1 - phat) / nonzero + z * z / (4 * nonzero * nonzero)) / (1 + z * z / nonzero)
        wilson = [center - radius, center + radius]
    else:
        wilson = [0.0, 1.0]
    roman_negative = [job["context"] for job in jobs if job["context"]["opponent"] == "roman_lb950" and float(rows[job["job_id"]]["result"]["paired"]["margin_delta"]) < 0]
    return {"contexts": len(results), "paired_margin_wdl": [positives, len(margins) - nonzero, negatives], "mean_paired_margin": sum(margins) / len(margins), "worst_paired_margin": min(margins), "positive_sign_wilson_95": wilson, "roman_negative_contexts": roman_negative, "tail_falsifier_triggered": bool(roman_negative), "automatic_promotion": False}


def run(root: Path, workers: int, execute_confirmation: bool) -> dict[str, Any]:
    root = root.resolve()
    if not execute_confirmation:
        raise PermissionError("formal selector confirmation requires --execute-confirmation")
    manifest, protocol = _load_frozen(root)
    validation = validate_preflight(root)
    if not validation["pass"]:
        raise RuntimeError(f"frozen confirmation preflight failed: {validation}")
    if int(protocol["workers"]) != int(workers):
        raise RuntimeError("worker count differs from frozen confirmation protocol")
    execution = {"schema_version": 1, "kind": "e2_s2_selector_confirmation_execution", "run_id": RUN_ID, "manifest_sha256": manifest["manifest_sha256"], "protocol_sha256": protocol["protocol_sha256"], "formal_fresh_seeds_executed": True, "executed_formal_seeds": protocol["evaluation_seeds"], "candidate_id": CANDIDATE_ID, "later_tier_launched": False}
    execution["execution_sha256"] = s1.payload_hash({key: value for key, value in execution.items() if key != "execution_sha256"})
    s1.atomic_json(root / "execution.json", execution)
    control_rows = s1._run_jobs(root / "formal" / "controls", manifest["control_jobs"], workers)
    if not all(row.get("status") == "complete" and row.get("result", {}).get("technical_status") == "complete" for row in control_rows):
        raise RuntimeError("confirmation control phase incomplete; candidate phase not launched")
    control_by_id = {row["job_id"]: row["result"] for row in control_rows}
    s1.atomic_json(root / "control_cache" / f"{LANE}.json", {job["job_id"]: control_by_id[job["job_id"]] for job in manifest["control_jobs"]})
    candidate_rows = s1._run_jobs(root / "formal" / "candidates", manifest["candidate_jobs"], workers)
    by_id = {row["job_id"]: row for row in candidate_rows}
    complete = all(by_id.get(job["job_id"], {}).get("status") == "complete" for job in manifest["candidate_jobs"])
    result = _summary(manifest["candidate_jobs"], by_id) if complete else None
    summary = {"schema_version": 1, "kind": "e2_s2_selector_fresh_confirmation_summary", "run_id": RUN_ID, "manifest_sha256": manifest["manifest_sha256"], "protocol_sha256": protocol["protocol_sha256"], "formal_fresh_seeds_executed": True, "executed_formal_seeds": protocol["evaluation_seeds"], "control_contexts": len(control_rows), "candidate_contexts": len(candidate_rows), "complete": complete, "result": result, "decision_written": False, "later_tier_launched": False}
    summary["summary_sha256"] = s1.payload_hash({key: value for key, value in summary.items() if key != "summary_sha256"})
    s1.atomic_json(root / "summary.json", summary)
    return summary


def launch(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    validation = validate_preflight(root)
    if not validation["pass"]:
        raise RuntimeError(f"confirmation dry preflight failed: {validation}")
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    if int(workers) != int(protocol["workers"]):
        raise RuntimeError("launch worker count differs from frozen confirmation protocol")
    stdout_path = root / "logs" / "stdout.log"
    stderr_path = root / "logs" / "stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), "run", "--output-root", str(root), "--workers", str(workers), "--execute-confirmation"]
    creationflags = 0
    for name in ("CREATE_NO_WINDOW", "CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS"):
        creationflags |= int(getattr(subprocess, name, 0))
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, close_fds=True, creationflags=creationflags)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    record = {"schema_version": 1, "kind": "e2_s2_selector_confirmation_launch", "run_id": RUN_ID, "pid": int(process.pid), "command": command, "workers": int(workers), "manifest_sha256": manifest["manifest_sha256"], "protocol_sha256": protocol["protocol_sha256"], "registry_sha256": protocol["seed_registry"]["sha256"], "stdout": str(stdout_path), "stderr": str(stderr_path), "control_shards": str(root / "formal" / "controls" / "shards"), "candidate_shards": str(root / "formal" / "candidates" / "shards"), "execution_launched": True, "completion_audited": False, "formal_fresh_seeds_executed": False, "later_tier_launched": False}
    record["launch_sha256"] = s1.payload_hash({key: value for key, value in record.items() if key != "launch_sha256"})
    s1.atomic_json(root / "launch.json", record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "validate", "launch", "run"):
        command = commands.add_parser(name)
        command.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
        if name in {"preflight", "launch", "run"}:
            command.add_argument("--workers", type=int, required=True)
        if name == "run":
            command.add_argument("--execute-confirmation", action="store_true")
    args = parser.parse_args()
    if args.command == "preflight":
        result = preflight(args.output_root, args.workers)
    elif args.command == "validate":
        result = validate_preflight(args.output_root)
    elif args.command == "launch":
        result = launch(args.output_root, args.workers)
    else:
        result = run(args.output_root, args.workers, args.execute_confirmation)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))


if __name__ == "__main__":
    main()
