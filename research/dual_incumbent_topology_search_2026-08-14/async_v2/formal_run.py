"""Freeze, validate, run, and detach the authorized Async E1 search."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from evolution import initial_genomes
from library import atomic_json, file_sha256, load_library
from model import LANES, candidate_from_payload, payload_hash
from search import (
    MAX_WORKERS,
    _compile_population,
    _freeze_job_manifest,
    _generation_file,
    _job,
    _load_generation,
    _load_hashed,
    _manifest_body,
    _materialize_generation,
    _reference_traces,
    _write_hashed,
    run_search,
)
from evaluator import TECHNICAL_SEED, engine_fingerprint
from seed_accounting import classify_evaluation_seeds


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ALLOWED_OPPONENTS = {"other_incumbent", "kaito_v21", "roman_lb950", "saiteja_3000"}
FORMAL_IMPLEMENTATION = (
    "formal_run.py",
    "search.py",
    "evaluator.py",
    "compiler.py",
    "evolution.py",
    "model.py",
    "runtime.py",
    "materialize.py",
    "library.py",
    "seed_accounting.py",
)


def _repo_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if ROOT.resolve() not in path.parents and path != ROOT.resolve():
        raise ValueError(f"path escapes repository: {value}")
    return path


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validated_seed_plumbing(
    protocol: dict[str, Any],
    registry: dict[str, Any],
    *,
    registry_path: Path,
) -> dict[str, Any]:
    """Validate an explicit protocol partition against the frozen registry."""
    seeds = tuple(int(seed) for seed in protocol.get("evaluation_seeds") or ())
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("formal protocol evaluation_seeds must be non-empty and unique")
    declared = protocol.get("seed_classification") or {}
    declared_sets = {
        "technical": {int(seed) for seed in declared.get("technical") or ()},
        "retained_consumed_e1": {
            int(seed) for seed in declared.get("retained_consumed_e1") or ()
        },
        "fresh": {int(seed) for seed in declared.get("fresh") or ()},
    }
    if any(
        declared_sets[left] & declared_sets[right]
        for index, left in enumerate(declared_sets)
        for right in tuple(declared_sets)[index + 1 :]
    ):
        raise ValueError("formal protocol seed classifications overlap")
    if set().union(*declared_sets.values()) != set(seeds):
        raise ValueError("formal protocol seed classifications do not partition evaluation_seeds")

    registered = registry.get("classifications") or {}
    registered_sets = {
        "technical": {int(seed) for seed in registered.get("technical") or ()},
        "retained_consumed_e1": {
            int(seed) for seed in registered.get("retained_consumed_e1") or ()
        },
        "fresh": {int(seed) for seed in registered.get("fresh") or ()},
    }
    if any(
        registered_sets[left] & registered_sets[right]
        for index, left in enumerate(registered_sets)
        for right in tuple(registered_sets)[index + 1 :]
    ):
        raise ValueError("seed registry classifications overlap")
    for name, declared_values in declared_sets.items():
        expected = set(seeds) & registered_sets[name]
        if declared_values != expected:
            raise ValueError(
                f"protocol/registry {name} classification mismatch: "
                f"declared={sorted(declared_values)} expected={sorted(expected)}"
            )
    accounting = classify_evaluation_seeds(
        seeds,
        formal_authorized=bool(protocol.get("formal_authorized")),
        registry=registry,
        registry_path=registry_path,
        explicit_fresh_seeds=tuple(sorted(declared_sets["fresh"])),
    )
    if accounting["unclassified_seeds"]:
        raise ValueError(f"unknown formal seeds are forbidden: {accounting['unclassified_seeds']}")
    active_modes = [
        name for name in ("retained_consumed_e1", "fresh") if declared_sets[name]
    ]
    if declared_sets["technical"] or len(active_modes) != 1:
        raise ValueError("formal protocol must use exactly one retained-or-fresh seed mode")
    return {
        "evaluation_seeds": seeds,
        "fresh_evaluation_seeds": tuple(sorted(declared_sets["fresh"])),
        "mode": active_modes[0],
        "accounting": accounting,
    }


def _protocol(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    protocol = _json(path)
    if protocol.get("schema_version") != 2 or not protocol.get("formal_authorized"):
        raise PermissionError("protocol is not an authorized schema-v2 formal run")
    if protocol.get("stage") != "E1" or protocol.get("lanes") != list(LANES):
        raise ValueError("protocol stage or lane ownership mismatch")
    if protocol.get("seats") != [0, 1]:
        raise ValueError("formal E1 requires both seats")
    opponents = tuple(protocol.get("opponents") or ())
    if not opponents or len(set(opponents)) != len(opponents) or not set(opponents) <= ALLOWED_OPPONENTS:
        raise ValueError("invalid formal opponent block")
    if int(protocol.get("population_per_lane", 0)) < 2 or int(protocol.get("generations", 0)) < 1:
        raise ValueError("invalid population/generation budget")
    if not 1 <= int(protocol.get("workers", 0)) <= MAX_WORKERS:
        raise ValueError(f"formal worker count must be in 1..{MAX_WORKERS}")

    registry_path = _repo_path(protocol["seed_registry"])
    usage_path = _repo_path(protocol["seed_usage_scan"])
    library_path = _repo_path(protocol["library"])
    calibration_path = _repo_path(protocol["cpu_calibration"])
    registry = _json(registry_path)
    usage = _json(usage_path)
    calibration = _json(calibration_path)
    tier = (registry.get("formal_tiers") or {}).get("E1") or {}
    seed_plumbing = _validated_seed_plumbing(
        protocol, registry, registry_path=registry_path,
    )
    seeds = seed_plumbing["evaluation_seeds"]
    if registry.get("run_id") != protocol.get("run_id"):
        raise ValueError("protocol/registry run-id mismatch")
    if tuple(int(seed) for seed in tier.get("seeds") or ()) != seeds:
        raise ValueError("protocol/registry E1 tier seed mismatch")
    expected_status = (
        "FROZEN_FOR_AUTHORIZED_LAUNCH"
        if seed_plumbing["mode"] == "fresh"
        else "CONSUMED_RETAINED_E1"
    )
    if tier.get("status") != expected_status:
        raise PermissionError(
            f"E1 seed tier status {tier.get('status')!r} is invalid for {seed_plumbing['mode']}"
        )
    if TECHNICAL_SEED in seeds or len(set(seeds)) != len(seeds):
        raise ValueError("formal E1 seed set is invalid")
    selected = usage.get("selected") or []
    if [int(row["seed"]) for row in selected] != list(seeds):
        raise ValueError("seed rescan and registry differ")
    if seed_plumbing["mode"] == "fresh" and (
        not usage.get("fresh_at_freeze")
        or any(row.get("matching_files_before_freeze") for row in selected)
    ):
        raise PermissionError("selected fresh E1 seeds were not locally fresh at freeze")

    actual_engine = engine_fingerprint()
    for expected in (protocol.get("engine") or {}, registry.get("engine") or {}):
        if not expected or any(actual_engine.get(key) != value for key, value in expected.items()):
            raise RuntimeError("exact engine/configuration fingerprint changed")
    library = load_library(library_path)
    if int(calibration.get("technical_seed", -1)) != TECHNICAL_SEED:
        raise ValueError("CPU calibration did not use the technical seed")
    if calibration.get("formal_fresh_seeds_executed") is not False or int(calibration.get("returncode", -1)) != 0:
        raise ValueError("CPU calibration is not a clean technical-only run")
    if int(calibration.get("workers", -1)) != int(protocol["workers"]):
        raise ValueError("protocol worker count differs from calibration")
    pool_mean = float(calibration["program_tree_cpu_percent_parallel_pool"]["mean"])
    if not 30.0 <= pool_mean <= 40.0 or not calibration.get("target_mean_met"):
        raise ValueError(f"program-tree CPU calibration is outside 30-40 percent: {pool_mean}")
    if int(protocol.get("candidate_context_jobs", -1)) != (
        len(LANES)
        * int(protocol["population_per_lane"])
        * int(protocol["generations"])
        * len(seeds)
        * len(opponents)
        * 2
    ):
        raise ValueError("declared candidate-context job count is inconsistent")

    authority = {
        "run_id": protocol["run_id"],
        "stage": "E1",
        "protocol_file_sha256": file_sha256(path),
        "seed_registry_file_sha256": file_sha256(registry_path),
        "seed_usage_scan_file_sha256": file_sha256(usage_path),
        "cpu_calibration_file_sha256": file_sha256(calibration_path),
        "implementation_file_sha256": {
            name: file_sha256(HERE / name)
            for name in FORMAL_IMPLEMENTATION
        },
        "seed_mode": seed_plumbing["mode"],
        "seed_accounting": seed_plumbing["accounting"],
    }
    validated = {
        "protocol": protocol,
        "registry": registry,
        "registry_path": registry_path,
        "seeds": seeds,
        "fresh_evaluation_seeds": seed_plumbing["fresh_evaluation_seeds"],
        "seed_accounting": seed_plumbing["accounting"],
        "opponents": opponents,
        "library": library,
        "library_path": library_path,
        "run_root": _repo_path(protocol["run_root"]),
        "authority": authority,
        "program_tree_parallel_pool_mean_percent": pool_mean,
    }
    return protocol, validated


def _freeze_generation_zero(validated: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    protocol = validated["protocol"]
    run_root = validated["run_root"]
    generation_path = _generation_file(run_root, 0)
    if generation_path.exists():
        frozen = _load_generation(generation_path)
        candidates = [
            candidate_from_payload(row)
            for lane in LANES
            for row in frozen["candidates"][lane]
        ]
    else:
        traces = _reference_traces()
        candidates = []
        rejected_by_lane = {}
        for lane in LANES:
            genomes = initial_genomes(
                lane,
                validated["library"],
                int(protocol["population_per_lane"]),
                int(protocol["proposal_seed"]),
            )
            compiled, rejected = _compile_population(
                lane,
                genomes,
                validated["library"],
                traces[lane],
                int(protocol["population_per_lane"]),
                int(protocol["proposal_seed"]),
                0,
            )
            candidates.extend(compiled)
            rejected_by_lane[lane] = rejected
        body = {
            "generation": 0,
            "manifest_sha256": manifest["manifest_sha256"],
            "candidates": {
                lane: [row.runtime_payload() for row in candidates if row.lane == lane]
                for lane in LANES
            },
            "rejections": rejected_by_lane,
            "artifacts": _materialize_generation(run_root, candidates),
        }
        frozen = _write_hashed(generation_path, body, "generation_sha256")
    formal_seeds = frozenset(validated["seeds"])
    jobs = [
        _job(candidate, 0, opponent, seat, seed=seed, formal_seeds=formal_seeds)
        for candidate in candidates
        for opponent in validated["opponents"]
        for seed in validated["seeds"]
        for seat in (0, 1)
    ]
    job_manifest = _freeze_job_manifest(run_root, manifest["manifest_sha256"], 0, jobs)
    return {
        "generation_sha256": frozen["generation_sha256"],
        "job_manifest_sha256": job_manifest["job_manifest_sha256"],
        "candidate_count": len(candidates),
        "job_count": len(jobs),
    }


def preflight(protocol_path: Path, output: Path) -> dict[str, Any]:
    protocol, validated = _protocol(protocol_path)
    run_root = validated["run_root"]
    run_root.mkdir(parents=True, exist_ok=True)
    manifest_body = _manifest_body(
        validated["library_path"],
        validated["library"],
        int(protocol["population_per_lane"]),
        int(protocol["generations"]),
        validated["opponents"],
        int(protocol["proposal_seed"]),
        validated["seeds"],
        True,
        validated["authority"],
        validated["fresh_evaluation_seeds"],
        validated["registry_path"],
        validated["registry"],
    )
    manifest_path = run_root / "search_manifest.json"
    if manifest_path.exists():
        manifest = _load_hashed(manifest_path, "manifest_sha256")
        actual = dict(manifest)
        actual.pop("manifest_sha256")
        if actual != manifest_body:
            raise ValueError("existing formal search manifest differs from frozen protocol")
    else:
        manifest = _write_hashed(manifest_path, manifest_body, "manifest_sha256")
    generation_zero = _freeze_generation_zero(validated, manifest)
    body = {
        "schema_version": 1,
        "run_id": protocol["run_id"],
        "stage": "E1",
        "decision": "READY_TO_LAUNCH_ASYNC_E1",
        "execution_started": False,
        "execution_completed": False,
        "formal_fresh_seeds_executed": False,
        "retained_e1_seeds_reexecuted": False,
        "seed_accounting": validated["seed_accounting"],
        "authority": validated["authority"],
        "engine": engine_fingerprint(),
        "evaluation_seeds": list(validated["seeds"]),
        "workers": int(protocol["workers"]),
        "program_tree_parallel_pool_mean_percent": validated["program_tree_parallel_pool_mean_percent"],
        "candidate_context_jobs": int(protocol["candidate_context_jobs"]),
        "search_manifest": str(manifest_path),
        "search_manifest_sha256": manifest["manifest_sha256"],
        "generation_zero": generation_zero,
        "shard_directory": str(run_root / "shards"),
    }
    if output.exists():
        existing = _load_hashed(output, "preflight_sha256")
        actual = dict(existing)
        actual.pop("preflight_sha256")
        if actual != body:
            raise ValueError("existing E1 preflight evidence differs")
        return existing
    return _write_hashed(output, body, "preflight_sha256")


def _validated_preflight(protocol_path: Path, preflight_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    protocol, validated = _protocol(protocol_path)
    frozen = _load_hashed(preflight_path, "preflight_sha256")
    if frozen.get("authority") != validated["authority"]:
        raise ValueError("preflight authority hashes are stale")
    if frozen.get("seed_accounting") != validated["seed_accounting"]:
        raise ValueError("preflight seed registry identity/classification is stale")
    manifest = _load_hashed(validated["run_root"] / "search_manifest.json", "manifest_sha256")
    if manifest["manifest_sha256"] != frozen.get("search_manifest_sha256"):
        raise ValueError("preflight/search manifest hash mismatch")
    if manifest.get("seed_accounting") != validated["seed_accounting"]:
        raise ValueError("search manifest seed registry identity/classification is stale")
    if manifest.get("seed_registry_file_sha256") != validated["authority"]["seed_registry_file_sha256"]:
        raise ValueError("search manifest seed registry hash differs from frozen authority")
    if manifest.get("execution_started") is not False or manifest.get("execution_completed") is not False:
        raise ValueError("preflight search manifest incorrectly claims execution")
    return protocol, validated


def execute(protocol_path: Path, preflight_path: Path) -> dict[str, Any]:
    protocol, validated = _validated_preflight(protocol_path, preflight_path)
    return run_search(
        validated["library_path"],
        validated["run_root"],
        population=int(protocol["population_per_lane"]),
        generations=int(protocol["generations"]),
        workers=int(protocol["workers"]),
        opponents=validated["opponents"],
        proposal_seed=int(protocol["proposal_seed"]),
        evaluation_seeds=validated["seeds"],
        formal_authorized=True,
        authority=validated["authority"],
        fresh_evaluation_seeds=validated["fresh_evaluation_seeds"],
        seed_registry_path=validated["registry_path"],
    )


def launch(
    protocol_path: Path,
    preflight_path: Path,
    launch_path: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    protocol, validated = _validated_preflight(protocol_path, preflight_path)
    if launch_path.exists() or stdout_path.exists() or stderr_path.exists():
        raise FileExistsError("refusing to replace launch evidence or redirected logs")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "execute",
        "--protocol",
        str(protocol_path.resolve()),
        "--preflight",
        str(preflight_path.resolve()),
    ]
    creationflags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    stdout = stdout_path.open("wb")
    stderr = stderr_path.open("wb")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
            close_fds=True,
        )
    finally:
        stdout.close()
        stderr.close()
    body = {
        "schema_version": 1,
        "run_id": protocol["run_id"],
        "stage": "E1",
        "launched_at_utc": datetime.now(timezone.utc).isoformat(),
        "pid": int(process.pid),
        "command": command,
        "cwd": str(ROOT),
        "workers": int(protocol["workers"]),
        "program_tree_parallel_pool_mean_percent_calibrated": validated["program_tree_parallel_pool_mean_percent"],
        "protocol": str(protocol_path.resolve()),
        "protocol_file_sha256": validated["authority"]["protocol_file_sha256"],
        "preflight": str(preflight_path.resolve()),
        "preflight_sha256": _load_hashed(preflight_path, "preflight_sha256")["preflight_sha256"],
        "search_manifest": str(validated["run_root"] / "search_manifest.json"),
        "search_manifest_sha256": _load_hashed(validated["run_root"] / "search_manifest.json", "manifest_sha256")["manifest_sha256"],
        "shard_directory": str(validated["run_root"] / "shards"),
        "stdout": str(stdout_path.resolve()),
        "stderr": str(stderr_path.resolve()),
        "formal_seed_execution_started": True,
        "seed_registry_file_sha256": validated["authority"]["seed_registry_file_sha256"],
        "seed_registry_run_id": validated["seed_accounting"]["registry_run_id"],
        "monitoring_performed_after_launch": False,
    }
    return _write_hashed(launch_path, body, "launch_sha256")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("preflight")
    prepare.add_argument("--protocol", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("execute")
    run.add_argument("--protocol", type=Path, required=True)
    run.add_argument("--preflight", type=Path, required=True)
    detach = commands.add_parser("launch")
    detach.add_argument("--protocol", type=Path, required=True)
    detach.add_argument("--preflight", type=Path, required=True)
    detach.add_argument("--launch-evidence", type=Path, required=True)
    detach.add_argument("--stdout", type=Path, required=True)
    detach.add_argument("--stderr", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "preflight":
        result = preflight(args.protocol, args.output)
        print(json.dumps({"decision": result["decision"], "preflight_sha256": result["preflight_sha256"]}, sort_keys=True))
    elif args.command == "execute":
        result = execute(args.protocol, args.preflight)
        print(json.dumps({"pass": result["pass"], "summary_sha256": result["summary_sha256"]}, sort_keys=True))
    else:
        result = launch(args.protocol, args.preflight, args.launch_evidence, args.stdout, args.stderr)
        print(json.dumps({"pid": result["pid"], "launch_sha256": result["launch_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
