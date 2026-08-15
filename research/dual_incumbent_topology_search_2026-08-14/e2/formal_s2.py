"""Boatlee-only E2 S2 tail-characterization preflight, launcher, and worker."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import formal_s1 as s1


HERE = s1.HERE
ROOT = s1.ROOT
RUN_ID = "e2_s2_20260815_boatlee_tail_v1"
DEFAULT_ROOT = HERE / "artifacts" / "formal" / RUN_ID
SEED_REGISTRY = HERE / "s2_seed_registry_20260815.json"
S1_DECISION = HERE / "s1_decision.json"
S1_ROOT = HERE / "artifacts" / "formal" / s1.RUN_ID
S1_SUMMARY = S1_ROOT / "s1_summary.json"
S1_CHECKPOINT = S1_ROOT / "checkpoint.json"
S1_PROTOCOL = S1_ROOT / "protocol.json"
DEVELOPMENT_VERIFICATION = s1.DEVELOPMENT_VERIFICATION
LANE = "boatlee_v16_rc2_market_relay"
OTHER_LANE = "v27_current_meta"
CANDIDATE_ID = "ac_3aa759d7d7fc4a409c409326"
OPPONENTS = s1.OPPONENTS
SEATS = s1.SEATS
WORKER_LIMIT = s1.WORKER_LIMIT
SOURCE_CONTROLS = s1.SOURCE_CONTROLS
SOURCE_ROUTES = s1.SOURCE_ROUTES
SOURCE_CANDIDATE = s1.SOURCE_CANDIDATES[LANE]
SOURCE_PUBLIC_OPPONENTS = s1.SOURCE_PUBLIC_OPPONENTS
PUBLIC_OPPONENT_FILES = s1.PUBLIC_OPPONENT_FILES


def _seed_records() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    registry = json.loads(SEED_REGISTRY.read_text(encoding="utf-8"))
    records = registry.get("seeds", [])
    values = [int(row["seed"]) for row in records]
    if len(values) != 4 or len(set(values)) != 4:
        raise RuntimeError("E2 S2 requires exactly four distinct fresh seeds")
    if any(
        row.get("classification") != "formal_fresh"
        or row.get("fresh") is not True
        or int(row.get("preselection_repository_hits", -1)) != 0
        or row.get("executed") is not False
        for row in records
    ):
        raise RuntimeError("S2 seed registry is not in the pre-execution state")
    if set(values) & {811407, 81426017, 81426029, 42284410, 73912654}:
        raise RuntimeError("technical, E1c, or S1 seed entered E2 S2")
    return records, registry


def _freshness_scan(registry: dict[str, Any], output_root: Path) -> dict[str, Any]:
    excluded = {SEED_REGISTRY.resolve()}
    if output_root.exists():
        excluded.update(path.resolve() for path in output_root.rglob("*") if path.is_file())
    rows: list[dict[str, Any]] = []
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
                raise RuntimeError(f"freshness rg failed for {scan_root}: {completed.returncode}")
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
        "candidates": {
            LANE: root / "inputs" / "candidates" / LANE / CANDIDATE_ID / "main.py",
        },
        "opponents": {
            family: root / "inputs" / "opponents" / family / "main.py"
            for family in SOURCE_PUBLIC_OPPONENTS
        },
    }


def _jobs(
    root: Path,
    records: list[dict[str, Any]],
    frozen: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    controls: list[dict[str, Any]] = []
    for opponent in OPPONENTS:
        for seed_record in records:
            for seat in SEATS:
                job = {
                    "kind": "control",
                    "evaluation_mode": "e2_s2_formal_exact",
                    "context": {
                        "lane": LANE, "opponent": opponent,
                        "seed": int(seed_record["seed"]), "seat": seat,
                    },
                    "seed_record": seed_record,
                    "artifact": {
                        "path": str(frozen["controls"][LANE]),
                        "sha256": s1.file_sha256(frozen["controls"][LANE]),
                    },
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
                context = {
                    "lane": LANE, "opponent": opponent,
                    "seed": int(seed_record["seed"]), "seat": seat,
                }
                job = {
                    "kind": "candidate",
                    "evaluation_mode": "e2_s2_formal_exact",
                    "candidate_id": CANDIDATE_ID,
                    "context": context,
                    "seed_record": seed_record,
                    "artifact": {
                        "path": str(frozen["candidates"][LANE]),
                        "sha256": s1.file_sha256(frozen["candidates"][LANE]),
                    },
                    "control_job_id": control_by_context[(opponent, int(seed_record["seed"]), seat)],
                    "control_cache_path": str(root / "control_cache" / f"{LANE}.json"),
                }
                job["job_id"] = s1.canonical_job_id(job)
                candidates.append(job)
    return (
        sorted(controls, key=lambda row: row["job_id"]),
        sorted(candidates, key=lambda row: row["job_id"]),
    )


def _s1_authority() -> dict[str, Any]:
    decision = json.loads(S1_DECISION.read_text(encoding="utf-8"))
    decision_canonical, decision_ok = s1._canonical_file(S1_DECISION, "s1_decision_sha256")
    summary = json.loads(S1_SUMMARY.read_text(encoding="utf-8"))
    summary_canonical, summary_ok = s1._canonical_file(S1_SUMMARY, "s1_summary_sha256")
    checkpoint = json.loads(S1_CHECKPOINT.read_text(encoding="utf-8"))
    checkpoint_canonical, checkpoint_ok = s1._canonical_file(S1_CHECKPOINT, "checkpoint_sha256")
    protocol = json.loads(S1_PROTOCOL.read_text(encoding="utf-8"))
    checks = {
        "decision_canonical": decision_ok,
        "decision_hash": decision_canonical == decision.get("s1_decision_sha256"),
        "decision_scope": (
            decision.get("overall_decision") == "ADVANCE_BOATLEE_ONLY_TO_E2_S2"
            and decision["lanes"][LANE]["decision"] == "ADVANCE_TO_E2_S2_TAIL_CHARACTERIZATION"
            and decision["lanes"][OTHER_LANE]["decision"] == "CURRENT_SELECTOR_NO_EFFICACY_STOP"
            and decision["lanes"][LANE].get("s2_candidate_mutation") is None
            and decision["lanes"][OTHER_LANE].get("s2_candidate") is None
        ),
        "summary_canonical": summary_ok,
        "summary_complete": summary.get("complete") is True,
        "checkpoint_canonical": checkpoint_ok,
        "checkpoint_complete": checkpoint.get("complete") is True,
        "source_hashes": (
            decision.get("source_summary_file_sha256") == s1.file_sha256(S1_SUMMARY)
            and decision.get("source_summary_canonical_sha256") == summary_canonical
            and decision.get("source_checkpoint_file_sha256") == s1.file_sha256(S1_CHECKPOINT)
            and decision.get("source_checkpoint_canonical_sha256") == checkpoint_canonical
        ),
        "candidate_identity": (
            decision["lanes"][LANE]["candidate_id"] == CANDIDATE_ID
            and protocol["candidate_artifacts"][LANE]["sha256"] == s1.file_sha256(SOURCE_CANDIDATE)
        ),
        "no_later_tier_already_launched": (
            decision.get("later_tier_launched") is False
            and summary.get("later_tier_launched") is False
            and checkpoint.get("later_tier_launched") is False
        ),
    }
    return {
        "pass": all(checks.values()), "checks": checks,
        "decision_file_sha256": s1.file_sha256(S1_DECISION),
        "decision_canonical_sha256": decision_canonical,
        "summary_file_sha256": s1.file_sha256(S1_SUMMARY),
        "summary_canonical_sha256": summary_canonical,
        "checkpoint_file_sha256": s1.file_sha256(S1_CHECKPOINT),
        "checkpoint_canonical_sha256": checkpoint_canonical,
        "protocol_file_sha256": s1.file_sha256(S1_PROTOCOL),
    }


def preflight(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    if not 1 <= int(workers) <= WORKER_LIMIT:
        raise ValueError(f"workers must be in 1..{WORKER_LIMIT}")
    if root.exists():
        raise FileExistsError(f"new E2 S2 root required: {root}")
    authority = s1.verify_authority()
    if not authority["pass"]:
        raise RuntimeError("E1c authority verification failed")
    s1_authority = _s1_authority()
    if not s1_authority["pass"]:
        raise RuntimeError(f"S1 decision authority failed: {s1_authority}")
    records, registry = _seed_records()
    scan = _freshness_scan(registry, root)
    if not scan["pass"]:
        raise RuntimeError(f"selected S2 seed is not fresh: {scan}")
    engine = s1.RUNNER.assert_engine_current()
    development = json.loads(DEVELOPMENT_VERIFICATION.read_text(encoding="utf-8"))
    development_canonical, development_ok = s1._canonical_file(
        DEVELOPMENT_VERIFICATION, "development_verification_sha256",
    )
    if development.get("decision") != "READY_FOR_E2_S1" or not development_ok:
        raise RuntimeError("development verification authority failed")

    root.mkdir(parents=True)
    frozen = _frozen_paths(root)
    copied: dict[str, Any] = {
        "controls": {
            lane: s1._copy_exact(SOURCE_CONTROLS[lane], frozen["controls"][lane])
            for lane in (LANE, OTHER_LANE)
        },
        "candidates": {LANE: s1._copy_exact(SOURCE_CANDIDATE, frozen["candidates"][LANE])},
        "opponents": {},
    }
    for family, filenames in PUBLIC_OPPONENT_FILES.items():
        source_dir = SOURCE_PUBLIC_OPPONENTS[family].parent
        target_dir = frozen["opponents"][family].parent
        files = {
            name: s1._copy_exact(source_dir / name, target_dir / name)
            for name in filenames
        }
        copied["opponents"][family] = {
            "entrypoint": str(frozen["opponents"][family]),
            "files": files,
            "package_sha256": s1.payload_hash(files),
        }

    opponent_import_smoke: dict[str, Any] = {}
    for family in SOURCE_PUBLIC_OPPONENTS:
        try:
            _module, agent, _latency = s1.RUNNER.harness.load_agent(
                frozen["opponents"][family], f"e2_s2_preflight_{family}",
            )
            opponent_import_smoke[family] = {
                "callable_agent": callable(agent), "pass": callable(agent),
            }
        except Exception as error:
            opponent_import_smoke[family] = {
                "callable_agent": False, "pass": False,
                "error": f"{type(error).__name__}: {error}",
            }
    if not all(row["pass"] for row in opponent_import_smoke.values()):
        raise RuntimeError(f"frozen opponent import smoke failed: {opponent_import_smoke}")
    spawned_import_smoke = s1._spawn_import_smoke(frozen, int(workers))
    if not spawned_import_smoke["pass"]:
        raise RuntimeError(f"spawned frozen opponent import smoke failed: {spawned_import_smoke}")

    expected_candidate_hash = development["registered_candidate_parity"][LANE]["artifact"]["sha256"]
    s1_protocol = json.loads(S1_PROTOCOL.read_text(encoding="utf-8"))
    if copied["candidates"][LANE]["sha256"] != expected_candidate_hash:
        raise RuntimeError("Boatlee candidate differs from development verification")
    if copied["candidates"][LANE]["sha256"] != s1_protocol["candidate_artifacts"][LANE]["sha256"]:
        raise RuntimeError("Boatlee candidate differs from S1")
    if any(
        copied["controls"][lane]["sha256"] != s1_protocol["control_hashes"][lane]
        for lane in (LANE, OTHER_LANE)
    ):
        raise RuntimeError("S2 control differs from S1")

    controls, candidates = _jobs(root, records, frozen)
    expected_contexts = len(OPPONENTS) * len(records) * len(SEATS)
    if len(controls) != expected_contexts or len(candidates) != expected_contexts:
        raise RuntimeError("unexpected S2 job count")
    protocol: dict[str, Any] = {
        "schema_version": 1,
        "kind": "e2_s2_boatlee_tail_protocol",
        "status": "frozen_authorized_s2",
        "formal_authorized": True,
        "authorization": "User explicitly instructed: complete and enter S2",
        "run_id": RUN_ID,
        "run_root": str(root),
        "workers": int(workers),
        "formal_fresh_seeds_executed": False,
        "evaluation_seeds": [int(row["seed"]) for row in records],
        "technical_seed": 811407,
        "seats": list(SEATS),
        "opponents": list(OPPONENTS),
        "lanes": {
            LANE: {
                "control": "lane_incumbent", "candidates": [CANDIDATE_ID],
                "candidate_mutation": None, "purpose": "public_market_tail_characterization",
                "pool_with_other_lane": False,
            },
            OTHER_LANE: {
                "status": "stopped_at_s1_no_efficacy", "candidates": [],
                "games": 0, "pool_with_other_lane": False,
            },
        },
        "seed_registry": {
            "path": str(SEED_REGISTRY), "sha256": s1.file_sha256(SEED_REGISTRY),
            "records": records,
        },
        "freshness_scan": scan,
        "s1_authority": s1_authority,
        "engine_fingerprint": engine,
        "control_hashes": {
            lane: copied["controls"][lane]["sha256"] for lane in (LANE, OTHER_LANE)
        },
        "route_hashes": {
            lane: s1.file_sha256(SOURCE_ROUTES[lane]) for lane in (LANE, OTHER_LANE)
        },
        "candidate_registry_sha256": s1.file_sha256(HERE / "candidate_registry.json"),
        "development_candidate_registry_sha256": s1.file_sha256(s1.DEVELOPMENT_REGISTRY),
        "development_verification": {
            "canonical_sha256": development_canonical,
            "file_sha256": s1.file_sha256(DEVELOPMENT_VERIFICATION),
        },
        "candidate_artifacts": copied["candidates"],
        "opponent_artifacts": copied["opponents"],
        "opponent_import_smoke": opponent_import_smoke,
        "spawned_opponent_import_smoke": spawned_import_smoke,
        "job_counts": {
            "boatlee_controls": expected_contexts,
            "boatlee_candidates": expected_contexts,
            "v27_controls": 0,
            "v27_candidates": 0,
            "total_games": len(controls) + len(candidates),
        },
        "decision_rule": {
            "technical_gate": "all 64 games complete with valid actions, no timeout or exception",
            "tail_outputs": [
                "paired_margin_wdl", "mean_paired_margin", "worst_paired_margin",
                "lower_quartile_mean", "per_opponent_mean", "negative_contexts",
            ],
            "candidate_failure_scores": False,
            "lane_pooling": False,
            "automatic_later_tier_launch": False,
            "post_run_action": "write an attributed S2 decision before any later tier",
        },
        "implementation_hashes": {
            "formal_s2.py": s1.file_sha256(Path(__file__)),
            "formal_s1.py": s1.file_sha256(HERE / "formal_s1.py"),
        },
        "later_tier_launched": False,
    }
    protocol["job_manifest_sha256"] = s1.payload_hash({
        "controls": controls, "candidates": candidates,
    })
    protocol["protocol_sha256"] = s1.payload_hash({
        key: value for key, value in protocol.items() if key != "protocol_sha256"
    })
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "e2_s2_boatlee_tail_manifest",
        "run_id": RUN_ID,
        "run_root": str(root),
        "protocol_sha256": protocol["protocol_sha256"],
        "engine_sha256": s1.payload_hash(engine),
        "controls_sha256": s1.payload_hash(copied["controls"]),
        "candidates_sha256": s1.payload_hash(copied["candidates"]),
        "opponents_sha256": s1.payload_hash(copied["opponents"]),
        "seed_registry_sha256": s1.file_sha256(SEED_REGISTRY),
        "jobs_sha256": protocol["job_manifest_sha256"],
        "control_jobs": controls,
        "candidate_jobs": candidates,
        "formal_fresh_seeds_executed": False,
        "later_tier_launched": False,
    }
    manifest["manifest_sha256"] = s1.payload_hash({
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    })
    s1.atomic_json(root / "protocol.json", protocol)
    s1.atomic_json(root / "manifest.json", manifest)
    s1.atomic_json(root / "jobs" / "controls.json", {
        "manifest_sha256": manifest["manifest_sha256"],
        "jobs": controls, "job_manifest_sha256": s1.payload_hash(controls),
    })
    s1.atomic_json(root / "jobs" / "candidates.json", {
        "manifest_sha256": manifest["manifest_sha256"],
        "jobs": candidates, "job_manifest_sha256": s1.payload_hash(candidates),
    })
    dry = {
        "schema_version": 1,
        "kind": "e2_s2_dry_preflight",
        "run_id": RUN_ID,
        "pass": True,
        "formal_authorized": True,
        "formal_fresh_seeds_executed": False,
        "later_tier_launched": False,
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "registry_sha256": s1.file_sha256(SEED_REGISTRY),
        "s1_decision_canonical_sha256": s1_authority["decision_canonical_sha256"],
    }
    dry["dry_preflight_sha256"] = s1.payload_hash({
        key: value for key, value in dry.items() if key != "dry_preflight_sha256"
    })
    s1.atomic_json(root / "dry_preflight.json", dry)
    return dry


def _load_frozen(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    protocol_body = {key: value for key, value in protocol.items() if key != "protocol_sha256"}
    if manifest.get("manifest_sha256") != s1.payload_hash(manifest_body):
        raise RuntimeError("S2 manifest canonical hash mismatch")
    if protocol.get("protocol_sha256") != s1.payload_hash(protocol_body):
        raise RuntimeError("S2 protocol canonical hash mismatch")
    if manifest.get("protocol_sha256") != protocol.get("protocol_sha256"):
        raise RuntimeError("S2 manifest/protocol identity mismatch")
    if protocol.get("formal_authorized") is not True or protocol.get("status") != "frozen_authorized_s2":
        raise PermissionError("S2 protocol is not explicitly authorized")
    expected_jobs = s1.payload_hash({
        "controls": manifest["control_jobs"], "candidates": manifest["candidate_jobs"],
    })
    if protocol.get("job_manifest_sha256") != expected_jobs:
        raise RuntimeError("S2 job manifest hash mismatch")
    return manifest, protocol


def validate_preflight(root: Path) -> dict[str, Any]:
    manifest, protocol = _load_frozen(root.resolve())
    controls = manifest["control_jobs"]
    candidates = manifest["candidate_jobs"]
    all_jobs = controls + candidates
    current_s1 = _s1_authority()
    checks = {
        "run_id": manifest["run_id"] == RUN_ID == protocol["run_id"],
        "four_fresh_seeds": (
            len(protocol["evaluation_seeds"]) == 4
            and len(set(protocol["evaluation_seeds"])) == 4
            and not set(protocol["evaluation_seeds"]) & {811407, 81426017, 81426029, 42284410, 73912654}
        ),
        "boatlee_only_candidate": (
            protocol["lanes"][LANE]["candidates"] == [CANDIDATE_ID]
            and protocol["lanes"][LANE]["candidate_mutation"] is None
            and protocol["lanes"][OTHER_LANE]["candidates"] == []
            and protocol["lanes"][OTHER_LANE]["games"] == 0
            and all(row["context"]["lane"] == LANE for row in all_jobs)
        ),
        "job_count": len(controls) == 32 and len(candidates) == 32,
        "both_seats": set(row["context"]["seat"] for row in all_jobs) == {0, 1},
        "opponents": set(row["context"]["opponent"] for row in all_jobs) == set(OPPONENTS),
        "lane_control_isolated": (
            all("control_cache_path" not in row for row in controls)
            and all(Path(row["control_cache_path"]).stem == LANE for row in candidates)
        ),
        "inputs_match": all(
            s1.file_sha256(Path(row["artifact"]["path"])) == row["artifact"]["sha256"]
            for row in all_jobs
        ),
        "candidate_identity": all(
            row.get("candidate_id") == CANDIDATE_ID
            and row["artifact"]["sha256"] == protocol["candidate_artifacts"][LANE]["sha256"]
            for row in candidates
        ),
        "opponents_match": all(
            s1.file_sha256(Path(file_row["path"])) == file_row["sha256"]
            for package in protocol["opponent_artifacts"].values()
            for file_row in package["files"].values()
        ),
        "opponents_imported": all(
            row["pass"] and row["callable_agent"]
            for row in protocol["opponent_import_smoke"].values()
        ),
        "opponents_imported_in_spawn_workers": protocol["spawned_opponent_import_smoke"]["pass"] is True,
        "registries_match": (
            s1.file_sha256(SEED_REGISTRY) == protocol["seed_registry"]["sha256"]
            and s1.file_sha256(HERE / "candidate_registry.json") == protocol["candidate_registry_sha256"]
            and s1.file_sha256(s1.DEVELOPMENT_REGISTRY) == protocol["development_candidate_registry_sha256"]
        ),
        "implementation_match": (
            s1.file_sha256(Path(__file__)) == protocol["implementation_hashes"]["formal_s2.py"]
            and s1.file_sha256(HERE / "formal_s1.py") == protocol["implementation_hashes"]["formal_s1.py"]
        ),
        "s1_authority": current_s1["pass"] and current_s1 == protocol["s1_authority"],
        "engine": s1.RUNNER.assert_engine_current() == protocol["engine_fingerprint"],
        "not_executed": (
            manifest["formal_fresh_seeds_executed"] is False
            and protocol["formal_fresh_seeds_executed"] is False
            and manifest["later_tier_launched"] is False
            and protocol["later_tier_launched"] is False
        ),
    }
    return {
        "pass": all(checks.values()), "checks": checks,
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "seed_registry_sha256": protocol["seed_registry"]["sha256"],
        "job_counts": protocol["job_counts"],
        "formal_fresh_seeds_executed": False,
        "later_tier_launched": False,
    }


def _evaluate_job(job: dict[str, Any]) -> dict[str, Any]:
    if job.get("evaluation_mode") != "e2_s2_formal_exact":
        return {
            "job_id": job.get("job_id"), "status": "infrastructure_failed",
            "efficacy": None,
            "infrastructure_failure": {"type": "ValueError", "detail": "unknown S2 evaluation mode"},
        }
    delegated = dict(job)
    delegated["evaluation_mode"] = "e2_s1_formal_exact"
    return s1._evaluate_job(delegated)


def _run_jobs(root: Path, jobs: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    shards = root / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    retained: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for original in jobs:
        job = {**original, "run_root": str(root.parents[1].resolve())}
        path = shards / f"{job['job_id']}.json"
        if path.exists():
            valid = s1._valid_shard(path, job["job_id"])
            if valid is not None:
                retained.append(valid)
                continue
            preserved = path.with_name(f"{path.stem}.corrupt-{s1.file_sha256(path)[:12]}.json")
            path.replace(preserved)
        pending.append(job)
    context = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        futures = {pool.submit(_evaluate_job, job): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = {
                    "job_id": job["job_id"], "status": "infrastructure_failed",
                    "efficacy": None,
                    "infrastructure_failure": {"type": "worker", "detail": str(error)},
                }
            body = dict(row)
            body["shard_sha256"] = s1.payload_hash(body)
            s1.atomic_json(shards / f"{row['job_id']}.json", body)
            retained.append(body)
    return sorted(retained, key=lambda row: row["job_id"])


def _tail_summary(jobs: list[dict[str, Any]], rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    contexts: list[dict[str, Any]] = []
    for job in jobs:
        row = rows[job["job_id"]]
        result = row["result"]
        contexts.append({
            "context": job["context"],
            "paired": result["paired"],
            "effective_change": result["effective_change"],
            "mechanism": result["mechanism"],
        })
    margins = sorted(float(row["paired"]["margin_delta"]) for row in contexts)
    lower_count = max(1, math.ceil(len(margins) * 0.25))
    negative = sorted(
        (row for row in contexts if float(row["paired"]["margin_delta"]) < 0),
        key=lambda row: float(row["paired"]["margin_delta"]),
    )
    return {
        "contexts": len(contexts),
        "paired_margin_wdl": [
            sum(value > 0 for value in margins),
            sum(value == 0 for value in margins),
            sum(value < 0 for value in margins),
        ],
        "lower_quartile_count": lower_count,
        "lower_quartile_mean": sum(margins[:lower_count]) / lower_count,
        "negative_context_count": len(negative),
        "negative_contexts": negative,
    }


def run(root: Path, workers: int, execute_s2: bool) -> dict[str, Any]:
    root = root.resolve()
    if not execute_s2:
        raise PermissionError("formal exact E2 S2 requires --execute-s2")
    manifest, protocol = _load_frozen(root)
    validation = validate_preflight(root)
    if not validation["pass"]:
        raise RuntimeError(f"frozen S2 preflight no longer validates: {validation}")
    if int(protocol["workers"]) != int(workers):
        raise RuntimeError("worker count differs from frozen S2 protocol")
    execution = {
        "schema_version": 1,
        "kind": "e2_s2_execution",
        "run_id": RUN_ID,
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "formal_fresh_seeds_executed": True,
        "executed_formal_seeds": protocol["evaluation_seeds"],
        "boatlee_candidate_executed": CANDIDATE_ID,
        "v27_executed": False,
        "later_tier_launched": False,
    }
    execution["execution_sha256"] = s1.payload_hash({
        key: value for key, value in execution.items() if key != "execution_sha256"
    })
    s1.atomic_json(root / "execution.json", execution)

    control_rows = _run_jobs(root / "formal" / "controls", manifest["control_jobs"], workers)
    if not all(
        row.get("status") == "complete"
        and row.get("result", {}).get("technical_status") == "complete"
        for row in control_rows
    ):
        raise RuntimeError("S2 control phase incomplete; candidate phase not launched")
    control_results = {row["job_id"]: row["result"] for row in control_rows}
    cache = {
        job["job_id"]: control_results[job["job_id"]]
        for job in manifest["control_jobs"]
    }
    s1.atomic_json(root / "control_cache" / f"{LANE}.json", cache)

    candidate_rows = _run_jobs(root / "formal" / "candidates", manifest["candidate_jobs"], workers)
    by_id = {row["job_id"]: row for row in candidate_rows}
    lane_summary = s1._lane_summary(LANE, manifest["candidate_jobs"], by_id)
    complete = bool(lane_summary["complete"])
    tail = _tail_summary(manifest["candidate_jobs"], by_id) if complete else None
    summary = {
        "schema_version": 1,
        "kind": "e2_s2_boatlee_tail_summary",
        "run_id": RUN_ID,
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "formal_fresh_seeds_executed": True,
        "executed_formal_seeds": protocol["evaluation_seeds"],
        "control_contexts": len(control_rows),
        "candidate_contexts": len(candidate_rows),
        "lanes": {
            LANE: lane_summary,
            OTHER_LANE: {"status": "stopped_at_s1_no_efficacy", "contexts": 0},
        },
        "tail_characterization": tail,
        "complete": complete,
        "decision_written": False,
        "later_tier_launched": False,
    }
    summary["s2_summary_sha256"] = s1.payload_hash({
        key: value for key, value in summary.items() if key != "s2_summary_sha256"
    })
    s1.atomic_json(root / "s2_summary.json", summary)
    checkpoint = {
        "schema_version": 1,
        "manifest_sha256": manifest["manifest_sha256"],
        "control_shards": [row["job_id"] for row in control_rows],
        "candidate_shards": [row["job_id"] for row in candidate_rows],
        "complete": complete,
        "s2_summary_sha256": summary["s2_summary_sha256"],
        "formal_fresh_seeds_executed": True,
        "decision_written": False,
        "later_tier_launched": False,
    }
    checkpoint["checkpoint_sha256"] = s1.payload_hash({
        key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"
    })
    s1.atomic_json(root / "checkpoint.json", checkpoint)
    return summary


def launch(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    validation = validate_preflight(root)
    if not validation["pass"]:
        raise RuntimeError(f"S2 dry preflight failed: {validation}")
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    if int(workers) != int(protocol["workers"]):
        raise RuntimeError("launch worker count differs from frozen S2 protocol")
    stdout_path = root / "logs" / "stdout.log"
    stderr_path = root / "logs" / "stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, str(Path(__file__).resolve()), "run",
        "--output-root", str(root), "--workers", str(workers), "--execute-s2",
    ]
    creationflags = 0
    for name in ("CREATE_NO_WINDOW", "CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS"):
        creationflags |= int(getattr(subprocess, name, 0))
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command, cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, close_fds=True,
            creationflags=creationflags,
        )
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    record = {
        "schema_version": 1,
        "kind": "e2_s2_launch",
        "run_id": RUN_ID,
        "pid": int(process.pid),
        "command": command,
        "workers": int(workers),
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "registry_sha256": protocol["seed_registry"]["sha256"],
        "s1_decision_canonical_sha256": protocol["s1_authority"]["decision_canonical_sha256"],
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "control_shards": str(root / "formal" / "controls" / "shards"),
        "candidate_shards": str(root / "formal" / "candidates" / "shards"),
        "execution_launched": True,
        "completion_audited": False,
        "formal_fresh_seeds_executed": False,
        "v27_executed": False,
        "later_tier_launched": False,
    }
    record["launch_sha256"] = s1.payload_hash({
        key: value for key, value in record.items() if key != "launch_sha256"
    })
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
            command.add_argument("--execute-s2", action="store_true")
    args = parser.parse_args()
    if args.command == "preflight":
        result = preflight(args.output_root, args.workers)
    elif args.command == "validate":
        result = validate_preflight(args.output_root)
    elif args.command == "launch":
        result = launch(args.output_root, args.workers)
    else:
        result = run(args.output_root, args.workers, args.execute_s2)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))


if __name__ == "__main__":
    main()
