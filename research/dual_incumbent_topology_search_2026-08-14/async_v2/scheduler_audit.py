"""Development audit for canonical parallelism, resume, corruption, and failures."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from compiler import compile_genome
from evaluator import TECHNICAL_SEED, run_control
from evolution import initial_genomes
from library import atomic_json, load_library
from model import CompiledAsyncCandidate, StaticRejection, payload_hash
from search import (
    _context_cache_path,
    _evaluate_jobs,
    _job,
    _load_checkpoint,
    _shard_path,
    _write_hashed,
    status,
)


def _canonical(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        result.append({
            "job_id": row["job_id"], "lane": row["lane"], "candidate_id": row["candidate_id"],
            "opponent": row["opponent"], "seed": row["seed"], "seat": row["seat"],
            "status": row.get("status", "complete"),
            "technical_pass": row.get("technical_pass"),
            "candidate_behavior": row.get("candidate_behavior"),
            "infrastructure_failure": row.get("infrastructure_failure"),
        })
    return sorted(result, key=lambda row: row["job_id"])


def run_audit(library_path: Path, output: Path) -> dict[str, Any]:
    library = load_library(library_path)
    candidates = []
    rejections = []
    for lane in library["lanes"]:
        trace = run_control(lane, "other_incumbent", TECHNICAL_SEED, 0, capture_trace=True).trace
        for genome in initial_genomes(lane, library, 4, 8142026):
            result = compile_genome(lane, genome, library, trace)
            if isinstance(result, StaticRejection):
                rejections.append(result.payload())
                continue
            if result.genome.route_blocks or result.genome.market_policy or result.genome.constants:
                candidates.append(result)
                break
        else:
            raise RuntimeError(f"no behavioral candidate compiled for {lane}")
    jobs = [_job(candidate, 0, "other_incumbent", seat) for candidate in candidates for seat in (0, 1)]
    with tempfile.TemporaryDirectory(prefix="async-scheduler-audit-") as temp:
        root = Path(temp)
        serial = _evaluate_jobs(root / "serial", jobs, 1)
        parallel = _evaluate_jobs(root / "parallel", jobs, 2)
        canonical_equal = _canonical(serial) == _canonical(parallel)

        # A repeated candidate/context in a later generation must be served by
        # the generation-independent candidate/context cache.
        cache_root = root / "cache"
        cache_first = _evaluate_jobs(cache_root, [jobs[0]], 1)[0]
        cache_job = _job(candidates[0], 1, jobs[0]["opponent"], jobs[0]["seat"])
        cache_second = _evaluate_jobs(cache_root, [cache_job], 1)[0]
        cache_path = _context_cache_path(cache_root, cache_job["context_cache_id"])
        cache_path.write_text("{broken", encoding="utf-8")
        cache_job_2 = _job(candidates[0], 2, jobs[0]["opponent"], jobs[0]["seat"])
        cache_repaired = _evaluate_jobs(cache_root, [cache_job_2], 1)[0]
        preserved_cache = list(cache_path.parent.glob(f"{cache_path.stem}.corrupt-*.json"))

        # Corrupt one canonical shard.  Resume must preserve it and recreate
        # exactly one valid shard without changing the remaining jobs.
        corrupt_root = root / "corrupt"
        first_pass = _evaluate_jobs(corrupt_root, jobs[:1], 1)
        corrupt_path = _shard_path(corrupt_root, jobs[0]["job_id"])
        corrupt_path.write_text("{broken", encoding="utf-8")
        repaired = _evaluate_jobs(corrupt_root, jobs[:1], 1)
        preserved_corrupt = list(corrupt_path.parent.glob(f"{corrupt_path.stem}.corrupt-*.json"))

        failures = {}
        for kind in ("worker_exception", "engine_import"):
            failure_root = root / kind
            injected = dict(jobs[0], failure_injection=kind)
            failed = _evaluate_jobs(failure_root, [injected], 1)[0]
            failure_path = _shard_path(failure_root, injected["job_id"])
            resumed = _evaluate_jobs(failure_root, [jobs[0]], 1)[0]
            failures[kind] = {
                "failed_status": failed["status"],
                "failed_has_efficacy": "candidate_behavior" in failed,
                "failure_type": failed.get("infrastructure_failure", {}).get("type"),
                "resumed_status": resumed.get("status", "complete"),
                "preserved_failure": bool(list(failure_path.parent.glob(f"{failure_path.stem}.corrupt-*.json"))),
            }

        checkpoint_root = root / "checkpoint"
        checkpoint_root.mkdir()
        manifest_sha256 = "f" * 64
        checkpoint = _write_hashed(
            checkpoint_root / "checkpoint.json",
            {"manifest_sha256": manifest_sha256, "completed_generation": 0, "parents": {}},
            "checkpoint_sha256",
        )
        loaded_checkpoint = _load_checkpoint(checkpoint_root, manifest_sha256, preserve_corrupt=False)
        checkpoint_root.joinpath("checkpoint.json").write_text("{broken", encoding="utf-8")
        repaired_checkpoint = _load_checkpoint(checkpoint_root, manifest_sha256, preserve_corrupt=True)
        preserved_checkpoint = list(checkpoint_root.glob("checkpoint.corrupt-*.json"))

        absent_status_root = root / "status_absent"
        before_status = list(root.rglob("*"))
        absent_status = status(absent_status_root)
        after_status = list(root.rglob("*"))

    body = {
        "technical_seed": TECHNICAL_SEED,
        "formal_fresh_seeds_executed": False,
        "candidate_ids": [row.candidate_id for row in candidates],
        "compile_rejections": rejections,
        "jobs": len(jobs),
        "serial_parallel_equal": canonical_equal,
        "spawn_start_method": "spawn",
        "candidate_context_cache": {
            "initial_complete": cache_first.get("status") == "complete",
            "cross_generation_hit": bool(cache_second.get("cache_hit")),
            "repaired_complete": cache_repaired.get("status") == "complete",
            "preserved_corrupt": bool(preserved_cache),
        },
        "corrupt_resume": {
            "initial_complete": first_pass[0].get("status", "complete") == "complete",
            "repaired_complete": repaired[0].get("status", "complete") == "complete",
            "preserved_corrupt": bool(preserved_corrupt),
        },
        "failure_injection": failures,
        "checkpoint": {
            "initial_sha256": checkpoint["checkpoint_sha256"],
            "loaded": loaded_checkpoint is not None,
            "corrupt_returns_none": repaired_checkpoint is None,
            "preserved_corrupt": bool(preserved_checkpoint),
        },
        "status_read_only": {
            "absent": absent_status.get("exists") is False,
            "filesystem_unchanged": [str(path) for path in before_status] == [str(path) for path in after_status],
        },
    }
    body["pass"] = bool(
        canonical_equal
        and body["corrupt_resume"]["initial_complete"]
        and body["corrupt_resume"]["repaired_complete"]
        and body["corrupt_resume"]["preserved_corrupt"]
        and all(body["candidate_context_cache"].values())
        and body["checkpoint"]["loaded"]
        and body["checkpoint"]["corrupt_returns_none"]
        and body["checkpoint"]["preserved_corrupt"]
        and all(body["status_read_only"].values())
        and all(
            row["failed_status"] == "infrastructure_failed"
            and not row["failed_has_efficacy"]
            and row["resumed_status"] == "complete"
            and row["preserved_failure"]
            for row in failures.values()
        )
    )
    result = {**body, "scheduler_audit_sha256": payload_hash(body)}
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_audit(args.library, args.output)
    print(json.dumps({"pass": result["pass"], "scheduler_audit_sha256": result["scheduler_audit_sha256"], "output": str(args.output)}, sort_keys=True))
