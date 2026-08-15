"""Spawn-only technical scheduler with immutable manifests and atomic shards."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
from typing import Any

from model import canonical_bytes, payload_hash


MAX_WORKERS = 15


class SchedulerFailure(RuntimeError):
    pass


def atomic_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return payload


def canonical_job_id(job: dict[str, Any]) -> str:
    return f"job_{payload_hash(job)[:24]}"


def load_resume(root: Path, expected: dict[str, Any]) -> dict[str, Any] | None:
    path = root / "manifest.json"
    if not path.is_file():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    required = ("manifest", "engine", "control", "fixture", "registry", "jobs")
    if any(loaded.get(key) != expected.get(key) for key in required):
        raise SchedulerFailure("resume manifest/engine/control/fixture/registry/job hash mismatch")
    return loaded


def read_status(root: Path) -> dict[str, Any]:
    """Read-only status; absence is not a reason to create a run root."""
    manifest = root / "manifest.json"
    if not manifest.is_file():
        return {"exists": False, "run_root": str(root)}
    try:
        return {"exists": True, "manifest_valid": True, "manifest": json.loads(manifest.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError) as error:
        return {"exists": True, "manifest_valid": False, "error": f"{type(error).__name__}: {error}"}


def _valid_shard(path: Path, job_id: str) -> dict[str, Any] | None:
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
        body = dict(row)
        expected = body.pop("shard_sha256", None)
        if row.get("job_id") != job_id or expected != payload_hash(body):
            return None
        return row
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _preserve_corrupt(path: Path) -> Path | None:
    if not path.exists():
        return None
    suffix = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    target = path.with_name(f"{path.stem}.corrupt-{suffix}{path.suffix}")
    if not target.exists():
        path.replace(target)
    return target


def _worker(job: dict[str, Any]) -> dict[str, Any]:
    """Spawned worker: infrastructure handling stays here; game work is evaluator-owned."""
    failure = job.get("failure_injection")
    if failure in {"kill", "worker"}:
        raise RuntimeError(f"injected {failure} failure")
    if failure in {"import", "engine"}:
        return {"status": "infrastructure_failed", "infrastructure_failure": {"type": failure}, "job_id": job["job_id"], "efficacy": None}
    try:
        # Import in the child proves that real formal work crosses the Windows
        # spawn boundary; no evaluator callable is smuggled through a closure.
        from evaluator import evaluate_job

        result = evaluate_job(job)
        return {"job_id": job["job_id"], "job_payload_sha256": payload_hash({key: value for key, value in job.items() if key != "job_id"}), **result}
    except Exception as error:
        return {
            "status": "infrastructure_failed", "job_id": job["job_id"], "efficacy": None,
            "infrastructure_failure": {"type": "evaluator", "detail": f"{type(error).__name__}: {error}"},
        }


def evaluate_jobs(root: Path, jobs: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    if not 1 <= int(workers) <= MAX_WORKERS:
        raise ValueError(f"workers must be in 1..{MAX_WORKERS}")
    root.mkdir(parents=True, exist_ok=True)
    shards = root / "shards"
    shards.mkdir(exist_ok=True)
    normalized = [{**job, "job_id": job.get("job_id") or canonical_job_id(job)} for job in jobs]
    retained: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for job in normalized:
        existing = shards / f"{job['job_id']}.json"
        if existing.exists():
            valid = _valid_shard(existing, job["job_id"])
            if valid is not None:
                retained.append(valid)
                continue
            _preserve_corrupt(existing)
        pending.append(job)
    if workers == 1:
        iterable = []
        for job in pending:
            try:
                iterable.append(_worker(job))
            except Exception as error:
                iterable.append({"status": "infrastructure_failed", "job_id": job["job_id"], "efficacy": None, "infrastructure_failure": {"type": "worker", "detail": str(error)}})
    else:
        context = mp.get_context("spawn")
        iterable = []
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            futures = [(job, pool.submit(_worker, job)) for job in pending]
            for job, future in futures:
                try:
                    iterable.append(future.result())
                except Exception as error:
                    iterable.append({"status": "infrastructure_failed", "job_id": job["job_id"], "efficacy": None, "infrastructure_failure": {"type": "worker", "detail": str(error)}})
    result = []
    for row in sorted(iterable, key=lambda value: value["job_id"]):
        body = dict(row)
        body["shard_sha256"] = payload_hash(body)
        atomic_json(shards / f"{row['job_id']}.json", body)
        result.append(body)
    return sorted(retained + result, key=lambda value: value["job_id"])


def development_audit(root: Path) -> dict[str, Any]:
    """Bounded, no-engine failure exercise used by the verification command."""
    jobs = [
        {
            "kind": "control", "evaluation_mode": "development_mock",
            "context": {"lane": lane, "opponent": "mock", "seed": 811407, "seat": index},
            "payload": {"lane": lane, "ordinal": index},
        }
        for index, lane in enumerate(("v27_current_meta", "boatlee_v16_rc2_market_relay"))
    ]
    serial = evaluate_jobs(root / "workers-1", jobs, 1)
    parallel = evaluate_jobs(root / "workers-4", jobs, 4)
    serial_view = [{key: value for key, value in row.items() if key != "shard_sha256"} for row in serial]
    parallel_view = [{key: value for key, value in row.items() if key != "shard_sha256"} for row in parallel]
    failures: dict[str, Any] = {}
    for kind in ("kill", "corrupt", "import", "engine", "worker"):
        job = {"kind": "control", "evaluation_mode": "development_mock", "context": {"lane": "v27_current_meta", "opponent": "mock", "seed": 811407, "seat": 0}, "payload": {"failure": kind}, "failure_injection": kind}
        if kind == "corrupt":
            job = {"kind": "control", "evaluation_mode": "development_mock", "context": {"lane": "v27_current_meta", "opponent": "mock", "seed": 811407, "seat": 0}, "payload": {"failure": kind}}
            first = evaluate_jobs(root / "failure-corrupt", [job], 1)[0]
            shard = root / "failure-corrupt" / "shards" / f"{first['job_id']}.json"
            shard.write_text("{corrupt", encoding="utf-8")
            resumed = evaluate_jobs(root / "failure-corrupt", [job], 1)[0]
            failures[kind] = {"status": resumed["status"], "preserved": bool(list(shard.parent.glob("*.corrupt-*.json"))), "has_efficacy": "efficacy" in resumed and resumed.get("efficacy") is not None}
            continue
        failed = evaluate_jobs(root / f"failure-{kind}", [job], 1)[0]
        restarted = evaluate_jobs(root / f"restart-{kind}", [{"kind": "control", "evaluation_mode": "development_mock", "context": {"lane": "v27_current_meta", "opponent": "mock", "seed": 811407, "seat": 0}, "payload": {"failure": kind}}], 1)[0]
        failures[kind] = {"status": failed["status"], "restart": restarted["status"], "has_efficacy": "efficacy" in failed and failed.get("efficacy") is not None}
    absent = root / "status-absent"
    before = absent.exists()
    status = read_status(absent)
    cap_enforced = False
    try:
        evaluate_jobs(root / "too-many-workers", jobs, MAX_WORKERS + 1)
    except ValueError:
        cap_enforced = True
    return {
        "spawn_start_method": "spawn", "workers": [1, 4], "canonical_equal": serial_view == parallel_view,
        "maximum_workers": MAX_WORKERS, "maximum_enforced": cap_enforced, "failures": failures,
        "status_read_only": not before and not absent.exists() and not status["exists"],
        "pass": serial_view == parallel_view and cap_enforced and all(
            (row.get("status") == "complete" and row.get("preserved")) if kind == "corrupt" else (row.get("status") == "infrastructure_failed" and row.get("restart") == "complete" and not row.get("has_efficacy"))
            for kind, row in failures.items()
        ) and not before and not absent.exists() and not status["exists"],
    }
