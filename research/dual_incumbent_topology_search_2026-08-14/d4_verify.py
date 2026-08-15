"""Run D4 commands and consolidate machine-readable development evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from exact_evaluator import CONTROL_PATHS, ROUTE_PATHS, engine_fingerprint
from materialize import isolated_import, static_runtime_audit
from scheduler import atomic_json


LANE_ROOT = Path(__file__).resolve().parent
ROOT = LANE_ROOT.parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "pass": completed.returncode == 0,
    }


def transcript(rows: list[dict[str, Any]]) -> str:
    blocks = []
    for row in rows:
        blocks.append(
            "$ " + subprocess.list2cmdline(row["command"]) + "\n"
            + f"exit_code={row['exit_code']}\n"
            + "stdout:\n" + (row["stdout"] or "")
            + "stderr:\n" + (row["stderr"] or "")
        )
    return "\n".join(blocks)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latency_gate(audit: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for lane_name, lane in audit["lanes"].items():
        for candidate in lane["candidates"]:
            for seat in candidate.get("parity", {}).get("seats", []):
                for representation in ("fast", "standalone"):
                    latency = seat[f"{representation}_latency_ms"]
                    rows.append(
                        {
                            "lane": lane_name,
                            "candidate_id": candidate["compile"]["candidate_id"],
                            "seat": seat["seat"],
                            "representation": representation,
                            "p95": latency["p95"],
                            "max": latency["max"],
                            "pass": latency["p95"] < 150.0 and latency["max"] < 750.0,
                        }
                    )
    return {
        "rows": rows,
        "max_p95_ms": max(row["p95"] for row in rows),
        "max_call_ms": max(row["max"] for row in rows),
        "pass": all(row["pass"] for row in rows),
    }


def candidate_isolation(audit: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for lane_name, lane in audit["lanes"].items():
        for candidate in lane["candidates"]:
            path = Path(candidate["parity"]["artifact"]["path"])
            static = static_runtime_audit(path)
            isolated = isolated_import(path)
            size = path.stat().st_size
            rows.append(
                {
                    "lane": lane_name,
                    "candidate_id": candidate["compile"]["candidate_id"],
                    "path": str(path),
                    "sha256": sha256(path),
                    "bytes": size,
                    "static": static,
                    "isolated": isolated,
                    "pass": static["pass"] and isolated["callable_agent"] and size < 5 * 1024 * 1024,
                }
            )
    return {"rows": rows, "pass": all(row["pass"] for row in rows)}


def source_hashes() -> dict[str, Any]:
    result = {}
    for lane, control in CONTROL_PATHS.items():
        development = control.parent / "development"
        result[lane] = {
            "control": {"path": str(control), "sha256": sha256(control)},
            "route": {"path": str(ROUTE_PATHS[lane]), "sha256": sha256(ROUTE_PATHS[lane])},
            "development": {
                str(path.relative_to(ROOT)): sha256(path)
                for path in sorted(development.glob("*.py"))
            },
        }
    result["searcher"] = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in sorted(LANE_ROOT.glob("*.py"))
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    args = parser.parse_args()
    python = sys.executable
    commands = [
        [python, str(ROOT / "research/main_approach/v27_current_meta/development/build_standalone.py")],
        [python, str(ROOT / "research/main_approach/v27_current_meta/development/build_standalone.py"), "--check"],
        [python, str(ROOT / "research/main_approach/boatlee_v16_rc2_market_relay/development/build_standalone.py")],
        [python, str(ROOT / "research/main_approach/boatlee_v16_rc2_market_relay/development/build_standalone.py"), "--check"],
        [python, "-m", "unittest", "research.main_approach.test_development_sources", "-v"],
        [python, str(LANE_ROOT / "test_topology_search.py"), "-v"],
        [python, str(LANE_ROOT / "cli.py"), "launch-formal", "--help"],
        # The system-default 3.14 install intentionally has no third-party
        # packages; the repository's legacy audit runner needs requests and
        # the compatible installed 3.12 environment.
        ["py", "-3.12", str(ROOT / "research/main_approach/validate_development.py")],
        [python, "-m", "compileall", "-q", str(LANE_ROOT)],
        ["git", "diff", "--check"],
    ]
    command_rows = [run_command(command) for command in commands]
    args.transcript.parent.mkdir(parents=True, exist_ok=True)
    args.transcript.write_text(transcript(command_rows), encoding="utf-8", newline="\n")

    d0_path = LANE_ROOT / "artifacts/d0_verification.json"
    audit_path = LANE_ROOT / "artifacts/technical_audit.json"
    population_path = LANE_ROOT / "artifacts/development_population.json"
    failure_path = LANE_ROOT / "artifacts/d3_failure_audit.json"
    serial_path = LANE_ROOT / "artifacts/d3_serial_merge.json"
    parallel_path = LANE_ROOT / "artifacts/d3_parallel_merge.json"
    registry_path = LANE_ROOT / "protocol_seed_registry.json"
    main_validation_path = ROOT / "research/main_approach/development_validation.json"
    d0 = load(d0_path)
    audit = load(audit_path)
    population = load(population_path)
    failure = load(failure_path)
    serial = load(serial_path)
    parallel = load(parallel_path)
    registry = load(registry_path)
    main_validation = load(main_validation_path)
    latency = latency_gate(audit)
    isolation = candidate_isolation(audit)
    population_summary = {
        lane: {
            "compiled": sum(row["status"] == "compiled" for row in data["results"]),
            "rejected": sum(row["status"] == "rejected" for row in data["results"]),
            "candidate_ids": sorted(row["candidate_id"] for row in data["results"] if row["status"] == "compiled"),
        }
        for lane, data in population["lanes"].items()
    }
    cross_lane_collisions = sorted(
        set(population_summary["v27_current_meta"]["candidate_ids"])
        & set(population_summary["boatlee_v16_rc2_market_relay"]["candidate_ids"])
    )
    shipping_lineage_complete = all(
        any(event["kind"] == "DROP" and event.get("product") in {"MILK", "FERTILIZER"} for event in candidate["compile"]["resource_ledger"]["lineage"]["events"])
        and any(edge[2] == "actor_inventory_carry_to_shed" for edge in candidate["compile"]["resource_ledger"]["lineage"]["edges"])
        and any(edge[2] == "shipping_market" for edge in candidate["compile"]["resource_ledger"]["lineage"]["edges"])
        for lane in audit["lanes"].values()
        for candidate in lane["candidates"]
    )
    true_time_shift_execution = all(
        candidate.get("time_shift_execution", {}).get("pass", False)
        for lane in audit["lanes"].values()
        for candidate in lane["candidates"]
        if candidate["genome"]["structural_root"] == "shift" and candidate["genome"]["purchase_shift"] in {-24, 24}
    )
    technical_game_safety = all(
        behavior["statuses"] == ["DONE", "DONE"]
        and behavior["exception"] is None
        and behavior["opponent_exception"] is None
        and behavior["timeout_calls"] == 0
        and not behavior["overage_exhausted"]
        and behavior["max_market_orders"] <= 10
        and not any(behavior["action_issues"].values())
        for lane in audit["lanes"].values()
        for candidate in lane["candidates"]
        for seat in candidate["parity"]["seats"]
        for behavior in (seat["fast"], seat["standalone"])
    )
    checks = {
        "commands": all(row["pass"] for row in command_rows),
        "d0_behavior_preserving": d0["pass"],
        "technical_compile_and_parity": audit["pass"],
        "technical_games_done_and_valid": technical_game_safety,
        "main_development_validation": main_validation["status"] == "PASS",
        "serial_parallel_canonical_equality": serial == parallel and serial["merge_sha256"] == parallel["merge_sha256"],
        "failure_injection": failure["pass"],
        "candidate_isolation": isolation["pass"],
        "latency": latency["pass"],
        "lane_candidate_ids_independent": not cross_lane_collisions,
        "production_drop_shed_sale_lineage": shipping_lineage_complete,
        "true_minus24_plus24_execution": true_time_shift_execution,
        "formal_seeds_not_executed": registry["formal_fresh_seeds_executed"] is False and audit["formal_fresh_seeds_executed"] is False and d0["formal_fresh_seeds_executed"] is False,
        "technical_seed_only": audit["seed"] == 811407 and d0["technical_seed"] == 811407,
    }
    passed = all(checks.values())
    payload = {
        "schema_version": 1,
        "decision": "READY_FOR_FORMAL_S1" if passed else "DEVELOPMENT_REMEDIATION_REQUIRED",
        "pass": passed,
        "formal_fresh_seeds_executed": False,
        "engine": engine_fingerprint(),
        "checks": checks,
        "commands": command_rows,
        "command_transcript": {"path": str(args.transcript), "sha256": sha256(args.transcript)},
        "source_hashes": source_hashes(),
        "population_summary": population_summary,
        "cross_lane_candidate_id_collisions": cross_lane_collisions,
        "technical_audit": {"path": str(audit_path), "sha256": sha256(audit_path)},
        "d0_verification": {"path": str(d0_path), "sha256": sha256(d0_path)},
        "d3": {
            "manifest": str(LANE_ROOT / "artifacts/d3_job_manifest.json"),
            "serial_merge": {"path": str(serial_path), "sha256": sha256(serial_path), "merge_sha256": serial["merge_sha256"]},
            "parallel_merge": {"path": str(parallel_path), "sha256": sha256(parallel_path), "merge_sha256": parallel["merge_sha256"]},
            "failure_audit": {"path": str(failure_path), "sha256": sha256(failure_path)},
        },
        "latency": latency,
        "candidate_isolation": isolation,
        "known_limitations": [
            "D0-D4 used only technical seed 811407; no formal fresh-seed efficacy evidence exists.",
            "Missing Phase 1, Phase 2A, fixed8 selector-v2, and prior plus/minus-24 artifacts remain prompt memory rather than repository authority.",
            "The D1 compiler uses deterministic Manhattan travel over the exact trace and rejects rather than improvises when resource/path/rejoin evidence is absent.",
            "The 811407 score deltas are retained diagnostics only and cannot promote a candidate.",
        ],
    }
    atomic_json(args.output, payload)
    print(json.dumps({"decision": payload["decision"], "pass": passed, "output": str(args.output)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
