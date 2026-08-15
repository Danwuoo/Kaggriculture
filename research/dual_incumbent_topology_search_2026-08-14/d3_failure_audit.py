"""Deterministic D3 corruption, restart, and failure-injection audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from exact_evaluator import engine_fingerprint
from scheduler import create_manifest, load_manifest, merge, run_manifest, status


LANE_ROOT = Path(__file__).resolve().parent
REGISTRY = LANE_ROOT / "protocol_seed_registry.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_view(root: Path) -> list[tuple[str, int, str]]:
    if not root.exists():
        return []
    return [
        (str(path.relative_to(root)), path.stat().st_size, sha256(path))
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def injected_manifest(base: dict[str, Any], output: Path, mode: str) -> dict[str, Any]:
    job = dict(base["jobs"][0])
    job["failure_injection"] = mode
    identity = {key: job[key] for key in ("lane", "candidate_id", "opponent", "seed", "seat")}
    identity["injection"] = mode
    job["job_id"] = f"job_inject_{hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]}"
    return create_manifest(
        output,
        [job],
        run_id=f"d3-{mode}",
        stage="D3-failure-injection",
        engine=engine_fingerprint(),
        seed_registry_sha256=sha256(REGISTRY),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = load_manifest(args.manifest)
    if args.work_root.exists():
        raise FileExistsError(f"failure-audit work root already exists: {args.work_root}")
    args.work_root.mkdir(parents=True)
    results: dict[str, Any] = {"schema_version": 1, "manifest_sha256": base["manifest_sha256"]}

    # A status query on an absent run directory must not create it.
    absent = args.work_root / "read_only_absent"
    before = tree_view(args.work_root)
    absent_status = status(args.manifest, absent)
    after = tree_view(args.work_root)
    results["read_only_status"] = {"pass": before == after and not absent.exists(), "status": absent_status}

    # Work on a copy so the retained canonical serial evidence remains immutable.
    restart_root = args.work_root / "restart_copy"
    shutil.copytree(args.source_run, restart_root)
    first, second = base["jobs"][:2]

    corrupt_path = restart_root / "shards" / f"{first['job_id']}.json"
    corrupt_path.write_text("injected-corrupt-shard\n", encoding="utf-8")
    corrupt_status = status(args.manifest, restart_root)
    corrupt_resume = run_manifest(args.manifest, restart_root, workers=2, resume=True)
    preserved_corrupt = sorted(str(path) for path in (restart_root / "shards").glob(f"{first['job_id']}.corrupt-*.json"))
    results["corrupt_shard"] = {
        "detected": corrupt_status["counts"]["corrupt"] == 1,
        "resume": corrupt_resume,
        "preserved": preserved_corrupt,
        "pass": corrupt_status["counts"]["corrupt"] == 1 and corrupt_resume["scheduled"] == 1 and bool(preserved_corrupt),
    }

    interrupted_path = restart_root / "shards" / f"{second['job_id']}.json"
    interrupted_evidence = interrupted_path.with_suffix(".interrupted.json")
    interrupted_path.replace(interrupted_evidence)
    interrupted_status = status(args.manifest, restart_root)
    interrupted_resume = run_manifest(args.manifest, restart_root, workers=2, resume=True)
    results["kill_restart"] = {
        "detected_missing": interrupted_status["counts"]["missing"] == 1,
        "resume": interrupted_resume,
        "preserved": str(interrupted_evidence),
        "pass": interrupted_status["counts"]["missing"] == 1 and interrupted_resume["scheduled"] == 1 and interrupted_evidence.exists(),
    }

    for mode in ("worker_exception", "engine_import"):
        manifest_path = args.work_root / f"{mode}_manifest.json"
        manifest = injected_manifest(base, manifest_path, mode)
        run_root = args.work_root / mode
        run = run_manifest(manifest_path, run_root, workers=2)
        shard_path = run_root / "shards" / f"{manifest['jobs'][0]['job_id']}.json"
        shard = json.loads(shard_path.read_text(encoding="utf-8"))
        merge_refused = False
        try:
            merge(manifest_path, run_root, args.work_root / f"{mode}_merge_should_not_exist.json")
        except RuntimeError:
            merge_refused = True
        results[mode] = {
            "run": run,
            "shard": shard,
            "no_efficacy": "efficacy" not in shard,
            "merge_refused": merge_refused,
            "pass": shard["status"] == "infrastructure_failed" and "efficacy" not in shard and merge_refused,
        }

    results["pass"] = all(
        results[key]["pass"]
        for key in ("read_only_status", "corrupt_shard", "kill_restart", "worker_exception", "engine_import")
    )
    from scheduler import atomic_json

    atomic_json(args.output, results)
    print(json.dumps({"pass": results["pass"], "output": str(args.output)}, sort_keys=True))
    return 0 if results["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
