"""Command-line entrypoint for the D0-D4 topology-search development lane."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from compiler import BoatleeCompilerAdapter, V27CompilerAdapter, compile_genome
from exact_evaluator import CONTROL_PATHS, ROUTE_PATHS, TECHNICAL_SEED, engine_fingerprint, load_route, parity_audit, run_control, run_fast
from model import CompiledCandidate, SemanticGenome, StaticRejection, canonical_bytes
from runtime_patch import candidate_runtime_payload
from scheduler import canonical_merge_view, create_manifest, load_manifest, make_jobs, merge, run_manifest, status
from search_space import one_factor_frontier, structural_roots


LANE_ROOT = Path(__file__).resolve().parent
ARTIFACTS = LANE_ROOT / "artifacts"
REGISTRY = LANE_ROOT / "protocol_seed_registry.json"
ADAPTERS = {
    "v27_current_meta": V27CompilerAdapter,
    "boatlee_v16_rc2_market_relay": BoatleeCompilerAdapter,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    from scheduler import atomic_json

    atomic_json(path, payload)


def adapter(lane: str):
    return ADAPTERS[lane](lane, ROUTE_PATHS[lane], CONTROL_PATHS[lane])


def compile_with_trace(lane: str, genomes: list[SemanticGenome] | tuple[SemanticGenome, ...]):
    control = run_control(lane, "other_incumbent", TECHNICAL_SEED, 0, capture_trace=True)
    route = load_route(lane)
    return control, [compile_genome(adapter(lane), genome, route, control.trace) for genome in genomes]


def cmd_preflight(args: argparse.Namespace) -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    payload = {
        "workspace": str(LANE_ROOT.parents[1]),
        "engine": engine_fingerprint(),
        "controls": {lane: {"path": str(path), "sha256": sha256(path)} for lane, path in CONTROL_PATHS.items()},
        "routes": {lane: {"path": str(path), "sha256": sha256(path)} for lane, path in ROUTE_PATHS.items()},
        "seed_registry": {"path": str(REGISTRY), "sha256": sha256(REGISTRY), "formal_fresh_seeds_executed": registry["formal_fresh_seeds_executed"]},
    }
    if args.output:
        write_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


def _result_payload(result: CompiledCandidate | StaticRejection) -> dict[str, Any]:
    if isinstance(result, CompiledCandidate):
        return {"status": "compiled", **candidate_runtime_payload(result)}
    return {"status": "rejected", **asdict(result), "candidate_id": result.candidate_id}


def _time_shift_execution_audit(candidate: CompiledCandidate) -> dict[str, Any]:
    run = run_fast(candidate, "other_incumbent", TECHNICAL_SEED, 0, capture_trace=True)
    plan = candidate.resource_ledger["structure_plan"]
    actual = []
    equal = True
    for offset, expected in enumerate(plan["actions"]):
        step = int(plan["start_step"]) + offset
        frame = run.trace[step]
        units = [frame.action.get("farmer") or ["PASS"], *(frame.action.get("hands") or [])]
        returned = units[int(plan["actor"])] if int(plan["actor"]) < len(units) else ["MISSING"]
        row_equal = list(returned) == list(expected)
        equal = equal and row_equal
        actual.append({"step": step, "expected": list(expected), "returned": list(returned), "equal": row_equal})
    kinds = [row["returned"][0] for row in actual if row["returned"]]
    required = {"BUILD_PASTURE", "PLACE"}
    if candidate.resource_ledger.get("target_clearance"):
        required.add("DIG")
    return {
        "seat": 0,
        "action_digest": run.summary["action_digest"],
        "plan_actions": actual,
        "required_structural_actions": sorted(required),
        "required_actions_executed": required.issubset(set(kinds)),
        "pass": equal and required.issubset(set(kinds)),
    }


def cmd_enumerate(args: argparse.Namespace) -> int:
    genomes = one_factor_frontier() if args.frontier else structural_roots()
    lanes = {}
    for lane in ADAPTERS:
        control, results = compile_with_trace(lane, genomes)
        lanes[lane] = {
            "control_action_digest": control.summary["action_digest"],
            "control_rewards": control.summary["rewards"],
            "results": [_result_payload(result) for result in results],
        }
    payload = {
        "schema_version": 1,
        "seed": TECHNICAL_SEED,
        "formal_fresh_seeds_executed": False,
        "engine": engine_fingerprint(),
        "lanes": lanes,
    }
    write_json(args.output, payload)
    print(json.dumps({lane: {"compiled": sum(row["status"] == "compiled" for row in data["results"]), "rejected": sum(row["status"] == "rejected" for row in data["results"])} for lane, data in lanes.items()}, sort_keys=True))
    return 0


def cmd_audit_technical(args: argparse.Namespace) -> int:
    genomes = (
        SemanticGenome(structural_root="control"),
        SemanticGenome(structural_root="removal"),
        SemanticGenome(structural_root="shift", purchase_shift=-24),
        SemanticGenome(structural_root="shift", purchase_shift=24),
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "seed": TECHNICAL_SEED,
        "purpose": "technical correctness only; not fresh efficacy evidence",
        "formal_fresh_seeds_executed": False,
        "engine": engine_fingerprint(),
        "lanes": {},
    }
    failed = False
    for lane in ADAPTERS:
        control, results = compile_with_trace(lane, genomes)
        lane_rows = []
        for genome, result in zip(genomes, results):
            row = {"genome": genome.payload(), "genome_id": genome.genome_id, "compile": _result_payload(result)}
            if isinstance(result, StaticRejection):
                failed = True
            else:
                output = ARTIFACTS / "candidates" / lane / result.candidate_id / "main.py"
                row["parity"] = parity_audit(result, output, seed=TECHNICAL_SEED)
                failed = failed or not row["parity"]["pass"]
                if genome.structural_root == "shift" and genome.purchase_shift in {-24, 24}:
                    row["time_shift_execution"] = _time_shift_execution_audit(result)
                    failed = failed or not row["time_shift_execution"]["pass"]
            lane_rows.append(row)
        payload["lanes"][lane] = {
            "control": {
                "rewards": control.summary["rewards"],
                "action_digest": control.summary["action_digest"],
                "lineage_expected": {"cow_ordinal": 9, "purchase_step": 361, "build_step": 517, "place_step": 518, "tile": [7, 3]},
            },
            "candidates": lane_rows,
        }
    payload["pass"] = not failed
    write_json(args.output, payload)
    print(json.dumps({"pass": payload["pass"], "output": str(args.output)}, sort_keys=True))
    return 0 if payload["pass"] else 1


def _compiled_from_registry(path: Path, ids: list[str]) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    found = {}
    for lane in payload["lanes"].values():
        for row in lane.get("results", []):
            if row.get("status") == "compiled":
                found[row["candidate_id"]] = row
        for row in lane.get("candidates", []):
            compile_row = row.get("compile", {})
            if compile_row.get("status") == "compiled":
                found[compile_row["candidate_id"]] = compile_row
    missing = sorted(set(ids) - set(found))
    if missing:
        raise KeyError(f"candidate ids absent from registry: {missing}")
    return [found[candidate_id] for candidate_id in ids]


def cmd_make_manifest(args: argparse.Namespace) -> int:
    candidates = _compiled_from_registry(args.registry, args.candidate_id)
    jobs = make_jobs(candidates, opponents=args.opponent, seeds=args.seed or [TECHNICAL_SEED], seats=args.seat or [0, 1])
    payload = create_manifest(
        args.output,
        jobs,
        run_id=args.run_id,
        stage=args.stage,
        engine=engine_fingerprint(),
        seed_registry_sha256=sha256(REGISTRY),
        formal_authorized=False,
    )
    print(json.dumps({"manifest_sha256": payload["manifest_sha256"], "jobs": len(jobs), "output": str(args.output)}, sort_keys=True))
    return 0


def cmd_make_formal_manifest(args: argparse.Namespace) -> int:
    if args.authorization != "START_E1":
        raise PermissionError("formal manifest creation requires the explicit START_E1 authorization token")
    seed_registry = json.loads(args.seed_registry.read_text(encoding="utf-8"))
    tier = seed_registry["formal_tiers"][args.tier]
    if tier["status"] != "FROZEN" or not tier["seeds"]:
        raise RuntimeError(f"{args.tier} must be populated and FROZEN after a fresh seed-usage rescan")
    candidates = _compiled_from_registry(args.registry, args.candidate_id)
    jobs = make_jobs(candidates, opponents=args.opponent, seeds=tier["seeds"], seats=args.seat or [0, 1])
    payload = create_manifest(
        args.output,
        jobs,
        run_id=args.run_id,
        stage=args.tier,
        engine=engine_fingerprint(),
        seed_registry_sha256=sha256(args.seed_registry),
        formal_authorized=True,
    )
    print(json.dumps({"manifest_sha256": payload["manifest_sha256"], "jobs": len(jobs), "output": str(args.output)}, sort_keys=True))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    result = run_manifest(args.manifest, args.run_root, workers=args.workers, resume=args.resume)
    print(json.dumps(result, sort_keys=True))
    return 1 if result["infrastructure_failures"] else 0


def cmd_status(args: argparse.Namespace) -> int:
    print(json.dumps(status(args.manifest, args.run_root), sort_keys=True))
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    result = merge(args.manifest, args.run_root, args.output)
    print(json.dumps({"merge_sha256": result["merge_sha256"], "rows": len(result["rows"]), "output": str(args.output)}, sort_keys=True))
    return 0


def _validate_formal(args: argparse.Namespace) -> dict[str, Any]:
    if args.authorization != "START_E1":
        raise PermissionError("formal preflight requires the explicit START_E1 authorization token")
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    tier = registry["formal_tiers"][args.tier]
    if tier["status"] != "FROZEN" or not tier["seeds"]:
        raise RuntimeError(f"{args.tier} must be populated and FROZEN after a fresh seed-usage rescan")
    manifest = load_manifest(args.manifest)
    if manifest["seed_registry_sha256"] != sha256(args.registry):
        raise RuntimeError("formal manifest does not match the supplied seed registry")
    if not manifest["formal_authorized"] or manifest["stage"] != args.tier:
        raise RuntimeError("formal manifest is not authorized for the requested tier")
    if sorted({int(job["seed"]) for job in manifest["jobs"]}) != sorted(tier["seeds"]):
        raise RuntimeError("manifest seeds do not equal frozen registry tier")
    return manifest


def cmd_formal_preflight(args: argparse.Namespace) -> int:
    manifest = _validate_formal(args)
    print(json.dumps({"pass": True, "tier": args.tier, "manifest_sha256": manifest["manifest_sha256"], "jobs": len(manifest["jobs"])}))
    return 0


def cmd_launch_formal(args: argparse.Namespace) -> int:
    """Launch once, record evidence, and return without polling the child."""
    manifest = _validate_formal(args)
    args.stdout.parent.mkdir(parents=True, exist_ok=True)
    args.stderr.parent.mkdir(parents=True, exist_ok=True)
    args.run_root.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "run",
        "--manifest",
        str(args.manifest.resolve()),
        "--run-root",
        str(args.run_root.resolve()),
        "--workers",
        str(args.workers),
        "--resume",
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with args.stdout.open("ab") as stdout_stream, args.stderr.open("ab") as stderr_stream:
        process = subprocess.Popen(
            command,
            cwd=LANE_ROOT.parents[1],
            stdin=subprocess.DEVNULL,
            stdout=stdout_stream,
            stderr=stderr_stream,
            creationflags=creationflags,
            close_fds=True,
        )
    record = {
        "schema_version": 1,
        "authorization": args.authorization,
        "tier": args.tier,
        "launched_at_utc": datetime.now(timezone.utc).isoformat(),
        "pid": process.pid,
        "run_id": manifest["run_id"],
        "manifest": str(args.manifest.resolve()),
        "manifest_sha256": manifest["manifest_sha256"],
        "seed_registry": str(args.registry.resolve()),
        "seed_registry_sha256": sha256(args.registry),
        "run_root": str(args.run_root.resolve()),
        "shards": [str((args.run_root / "shards" / f"{job['job_id']}.json").resolve()) for job in manifest["jobs"]],
        "stdout": str(args.stdout.resolve()),
        "stderr": str(args.stderr.resolve()),
        "command": command,
        "polling_performed": False,
    }
    write_json(args.launch_record, record)
    print(json.dumps({"launched": True, "pid": process.pid, "run_id": manifest["run_id"], "manifest_sha256": manifest["manifest_sha256"], "launch_record": str(args.launch_record)}, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--output", type=Path)
    preflight.set_defaults(func=cmd_preflight)
    enum = commands.add_parser("enumerate")
    enum.add_argument("--frontier", action="store_true")
    enum.add_argument("--output", type=Path, required=True)
    enum.set_defaults(func=cmd_enumerate)
    audit = commands.add_parser("audit-technical")
    audit.add_argument("--output", type=Path, required=True)
    audit.set_defaults(func=cmd_audit_technical)
    manifest = commands.add_parser("make-dev-manifest")
    manifest.add_argument("--registry", type=Path, required=True)
    manifest.add_argument("--candidate-id", action="append", required=True)
    manifest.add_argument("--opponent", action="append", required=True)
    manifest.add_argument("--seed", action="append", type=int)
    manifest.add_argument("--seat", action="append", type=int)
    manifest.add_argument("--run-id", required=True)
    manifest.add_argument("--stage", default="D3")
    manifest.add_argument("--output", type=Path, required=True)
    manifest.set_defaults(func=cmd_make_manifest)
    formal_manifest = commands.add_parser("make-formal-manifest")
    formal_manifest.add_argument("--authorization", required=True)
    formal_manifest.add_argument("--tier", choices=("S1", "S2", "S3", "S4"), required=True)
    formal_manifest.add_argument("--seed-registry", type=Path, required=True)
    formal_manifest.add_argument("--registry", type=Path, required=True)
    formal_manifest.add_argument("--candidate-id", action="append", required=True)
    formal_manifest.add_argument("--opponent", action="append", required=True)
    formal_manifest.add_argument("--seat", action="append", type=int)
    formal_manifest.add_argument("--run-id", required=True)
    formal_manifest.add_argument("--output", type=Path, required=True)
    formal_manifest.set_defaults(func=cmd_make_formal_manifest)
    run = commands.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--run-root", type=Path, required=True)
    run.add_argument("--workers", type=int, required=True)
    run.add_argument("--resume", action="store_true")
    run.set_defaults(func=cmd_run)
    stat = commands.add_parser("status")
    stat.add_argument("--manifest", type=Path, required=True)
    stat.add_argument("--run-root", type=Path, required=True)
    stat.set_defaults(func=cmd_status)
    merger = commands.add_parser("merge")
    merger.add_argument("--manifest", type=Path, required=True)
    merger.add_argument("--run-root", type=Path, required=True)
    merger.add_argument("--output", type=Path, required=True)
    merger.set_defaults(func=cmd_merge)
    formal = commands.add_parser("formal-preflight")
    formal.add_argument("--authorization", required=True)
    formal.add_argument("--tier", choices=("S1", "S2", "S3", "S4"), required=True)
    formal.add_argument("--registry", type=Path, required=True)
    formal.add_argument("--manifest", type=Path, required=True)
    formal.set_defaults(func=cmd_formal_preflight)
    launch = commands.add_parser("launch-formal")
    launch.add_argument("--authorization", required=True)
    launch.add_argument("--tier", choices=("S1", "S2", "S3", "S4"), required=True)
    launch.add_argument("--registry", type=Path, required=True)
    launch.add_argument("--manifest", type=Path, required=True)
    launch.add_argument("--run-root", type=Path, required=True)
    launch.add_argument("--workers", type=int, required=True)
    launch.add_argument("--stdout", type=Path, required=True)
    launch.add_argument("--stderr", type=Path, required=True)
    launch.add_argument("--launch-record", type=Path, required=True)
    launch.set_defaults(func=cmd_launch_formal)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
