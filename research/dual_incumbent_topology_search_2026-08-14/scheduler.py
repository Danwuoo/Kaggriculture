"""Spawn-isolated, resumable exact-engine job scheduler.

Every job owns one canonical JSON shard.  Workers never append to a shared
file, and infrastructure failures never receive an efficacy payload.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from exact_evaluator import (
    CONTROL_PATHS,
    TECHNICAL_SEED,
    behavior_view,
    engine_fingerprint,
    run_control,
    run_fast,
)
from model import canonical_bytes, compiled_from_payload, stable_id


SCHEDULER_VERSION = "d3-v2"
ENGINE_IDENTITY_KEYS = (
    "commit",
    "python_blob",
    "configuration_blob",
    "python_sha256",
    "configuration_sha256",
    "python_bytes",
    "configuration_bytes",
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def make_jobs(
    candidates: Iterable[dict[str, Any]],
    *,
    opponents: Iterable[str],
    seeds: Iterable[int],
    seats: Iterable[int] = (0, 1),
    injection_by_candidate: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    jobs = []
    injections = injection_by_candidate or {}
    for candidate in candidates:
        lane = str(candidate["lane"])
        candidate_id = str(candidate["candidate_id"])
        for opponent in opponents:
            for seed in seeds:
                for seat in seats:
                    identity = {
                        "lane": lane,
                        "candidate_id": candidate_id,
                        "opponent": str(opponent),
                        "seed": int(seed),
                        "seat": int(seat),
                    }
                    jobs.append(
                        {
                            **identity,
                            "job_id": stable_id("job", identity, 24),
                            "candidate": candidate,
                            "failure_injection": injections.get(candidate_id),
                        }
                    )
    return sorted(jobs, key=lambda row: row["job_id"])


def create_manifest(
    path: Path,
    jobs: Iterable[dict[str, Any]],
    *,
    run_id: str,
    stage: str,
    engine: dict[str, Any],
    seed_registry_sha256: str,
    formal_authorized: bool = False,
) -> dict[str, Any]:
    rows = list(jobs)
    if not formal_authorized:
        illegal = sorted({int(row["seed"]) for row in rows if int(row["seed"]) != TECHNICAL_SEED})
        if illegal:
            raise PermissionError(f"fresh seeds are not authorized for D0-D4: {illegal}")
    controls = {lane: file_sha256(control) for lane, control in sorted(CONTROL_PATHS.items())}
    body = {
        "schema_version": 1,
        "scheduler_version": SCHEDULER_VERSION,
        "run_id": run_id,
        "stage": stage,
        "formal_authorized": bool(formal_authorized),
        "engine": engine,
        "seed_registry_sha256": seed_registry_sha256,
        "controls": controls,
        "jobs": rows,
    }
    frozen = {**body, "manifest_sha256": _payload_hash(body)}
    atomic_json(path, frozen)
    return frozen


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.pop("manifest_sha256", None)
    actual = _payload_hash(payload)
    if not expected or actual != expected:
        raise ValueError(f"manifest hash mismatch: expected={expected} actual={actual}")
    payload["manifest_sha256"] = expected
    if payload.get("scheduler_version") != SCHEDULER_VERSION:
        raise ValueError("scheduler version mismatch")
    actual_engine = engine_fingerprint()
    expected_engine = payload.get("engine") or {}
    if {key: actual_engine.get(key) for key in ENGINE_IDENTITY_KEYS} != {
        key: expected_engine.get(key) for key in ENGINE_IDENTITY_KEYS
    }:
        raise ValueError("engine/config identity changed since manifest freeze")
    registry = Path(__file__).resolve().parent / "protocol_seed_registry.json"
    if registry.is_file() and file_sha256(registry) != payload.get("seed_registry_sha256"):
        raise ValueError("seed registry changed since manifest freeze")
    for lane, expected_control in payload["controls"].items():
        actual_control = file_sha256(CONTROL_PATHS[lane])
        if actual_control != expected_control:
            raise ValueError(f"control hash changed for {lane}: {expected_control} != {actual_control}")
    if not payload.get("formal_authorized", False):
        for job in payload["jobs"]:
            if int(job["seed"]) != TECHNICAL_SEED:
                raise PermissionError("unapproved seed in development manifest")
    return payload


def _shard_path(run_root: Path, job_id: str) -> Path:
    return run_root / "shards" / f"{job_id}.json"


def _cache_path(run_root: Path, job: dict[str, Any], control_sha256: str) -> Path:
    identity = {
        "lane": job["lane"],
        "opponent": job["opponent"],
        "seed": job["seed"],
        "seat": job["seat"],
        "control_sha256": control_sha256,
    }
    return run_root / "control_cache" / f"{stable_id('control', identity, 24)}.json"


def _validated_shard(path: Path, manifest_sha256: str, job_id: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if payload.get("manifest_sha256") != manifest_sha256 or payload.get("job_id") != job_id:
        return None
    body = dict(payload)
    expected = body.pop("shard_sha256", None)
    return payload if expected and _payload_hash(body) == expected else None


def _preserve_corrupt(path: Path) -> Path | None:
    if not path.exists():
        return None
    suffix = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    destination = path.with_name(f"{path.stem}.corrupt-{suffix}{path.suffix}")
    if destination.exists():
        destination = path.with_name(f"{path.stem}.corrupt-{suffix}-{os.getpid()}{path.suffix}")
    path.replace(destination)
    return destination


def _control_cache(run_root: Path, job: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    path = _cache_path(run_root, job, manifest["controls"][job["lane"]])
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            body = dict(payload)
            expected = body.pop("cache_sha256", None)
            if expected and _payload_hash(body) == expected and payload.get("manifest_control_sha256") == manifest["controls"][job["lane"]]:
                return payload["behavior"]
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass
    run = run_control(job["lane"], job["opponent"], int(job["seed"]), int(job["seat"]), allow_formal=bool(manifest["formal_authorized"]))
    body = {
        "manifest_control_sha256": manifest["controls"][job["lane"]],
        "behavior": behavior_view(run),
        "summary": run.summary,
    }
    atomic_json(path, {**body, "cache_sha256": _payload_hash(body)})
    return body["behavior"]


def _execute_job(job: dict[str, Any], manifest: dict[str, Any], run_root_text: str) -> dict[str, Any]:
    injection = job.get("failure_injection")
    if injection == "worker_exception":
        raise RuntimeError("injected worker exception")
    if injection == "engine_import":
        raise ImportError("injected engine import failure")
    run_root = Path(run_root_text)
    control_behavior = _control_cache(run_root, job, manifest)
    candidate = compiled_from_payload(job["candidate"])
    if candidate.candidate_id != job["candidate_id"]:
        raise ValueError(f"candidate payload hash mismatch for {job['job_id']}")
    run = run_fast(
        candidate,
        job["opponent"],
        int(job["seed"]),
        int(job["seat"]),
        allow_formal=bool(manifest["formal_authorized"]),
    )
    candidate_behavior = behavior_view(run)
    # paired_result requires the full control run object; compute the same
    # lane-relative fields from the frozen behavior views without pooling.
    seat = int(job["seat"])
    control_rewards = control_behavior["rewards"]
    candidate_rewards = candidate_behavior["rewards"]
    control_margin = float(control_rewards[seat]) - float(control_rewards[1 - seat])
    candidate_margin = float(candidate_rewards[seat]) - float(candidate_rewards[1 - seat])
    summary = run.summary
    technical_failure = any(
        (
            summary["statuses"] != ["DONE", "DONE"],
            summary["exception"] is not None,
            summary["opponent_exception"] is not None,
            summary["timeout_calls"] > 0,
            summary["overage_exhausted"],
            summary["max_market_orders"] > 10,
            any(summary["action_issues"].values()),
        )
    )
    efficacy = {
        "paired_margin_delta": candidate_margin - control_margin,
        "own_bank_delta": float(candidate_rewards[seat]) - float(control_rewards[seat]),
        "control_rewards": control_rewards,
        "candidate_rewards": candidate_rewards,
    }
    body = {
        "manifest_sha256": manifest["manifest_sha256"],
        "job_id": job["job_id"],
        "lane": job["lane"],
        "candidate_id": job["candidate_id"],
        "opponent": job["opponent"],
        "seed": job["seed"],
        "seat": job["seat"],
        "status": "technical_failed" if technical_failure else "complete",
        "technical_failure": technical_failure,
        "efficacy": efficacy,
        "candidate_behavior": candidate_behavior,
    }
    return {**body, "shard_sha256": _payload_hash(body)}


def run_manifest(manifest_path: Path, run_root: Path, *, workers: int, resume: bool = False) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "shards").mkdir(parents=True, exist_ok=True)
    (run_root / "control_cache").mkdir(parents=True, exist_ok=True)
    pending = []
    preserved = []
    for job in manifest["jobs"]:
        path = _shard_path(run_root, job["job_id"])
        valid = _validated_shard(path, manifest["manifest_sha256"], job["job_id"])
        if valid is not None and resume:
            continue
        if path.exists() and valid is None:
            preserved_path = _preserve_corrupt(path)
            if preserved_path:
                preserved.append(str(preserved_path))
        pending.append(job)
    failures = []
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=max(1, int(workers)), mp_context=context) as pool:
        futures = {pool.submit(_execute_job, job, manifest, str(run_root)): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            path = _shard_path(run_root, job["job_id"])
            try:
                shard = future.result()
            except BaseException as error:
                body = {
                    "manifest_sha256": manifest["manifest_sha256"],
                    "job_id": job["job_id"],
                    "lane": job["lane"],
                    "candidate_id": job["candidate_id"],
                    "opponent": job["opponent"],
                    "seed": job["seed"],
                    "seat": job["seat"],
                    "status": "infrastructure_failed",
                    "infrastructure_failure": {"type": type(error).__name__, "message": str(error)},
                }
                shard = {**body, "shard_sha256": _payload_hash(body)}
                failures.append(job["job_id"])
            atomic_json(path, shard)
    return {
        "manifest_sha256": manifest["manifest_sha256"],
        "scheduled": len(pending),
        "infrastructure_failures": sorted(failures),
        "preserved_corrupt": sorted(preserved),
        "status": status(manifest_path, run_root),
    }


def status(manifest_path: Path, run_root: Path) -> dict[str, Any]:
    """Read-only status: this function never creates or modifies a path."""
    manifest = load_manifest(manifest_path)
    counts = {"complete": 0, "technical_failed": 0, "infrastructure_failed": 0, "missing": 0, "corrupt": 0}
    for job in manifest["jobs"]:
        path = _shard_path(run_root, job["job_id"])
        shard = _validated_shard(path, manifest["manifest_sha256"], job["job_id"])
        if shard is None:
            counts["corrupt" if path.exists() else "missing"] += 1
        else:
            counts[shard["status"]] = counts.get(shard["status"], 0) + 1
    return {
        "manifest_sha256": manifest["manifest_sha256"],
        "run_id": manifest["run_id"],
        "stage": manifest["stage"],
        "jobs": len(manifest["jobs"]),
        "counts": counts,
        "ready_to_merge": counts["missing"] == 0 and counts["corrupt"] == 0 and counts["infrastructure_failed"] == 0,
    }


def merge(manifest_path: Path, run_root: Path, output: Path) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    rows = []
    for job in manifest["jobs"]:
        path = _shard_path(run_root, job["job_id"])
        shard = _validated_shard(path, manifest["manifest_sha256"], job["job_id"])
        if shard is None:
            raise RuntimeError(f"missing or corrupt shard: {job['job_id']}")
        if shard["status"] == "infrastructure_failed":
            raise RuntimeError(f"infrastructure failure has no efficacy score: {job['job_id']}")
        rows.append(shard)
    rows.sort(key=lambda row: row["job_id"])
    body = {
        "manifest_sha256": manifest["manifest_sha256"],
        "run_id": manifest["run_id"],
        "stage": manifest["stage"],
        "rows": rows,
    }
    result = {**body, "merge_sha256": _payload_hash(body)}
    atomic_json(output, result)
    return result


def canonical_merge_view(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_sha256": payload["manifest_sha256"],
        "run_id": payload["run_id"],
        "stage": payload["stage"],
        "rows": payload["rows"],
    }
