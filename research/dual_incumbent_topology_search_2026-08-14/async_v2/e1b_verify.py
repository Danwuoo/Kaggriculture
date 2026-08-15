"""Assemble the final Async E1b preflight decision without launching E1b."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from compiler import CONTROLS
from evaluator import TECHNICAL_SEED, engine_fingerprint
from library import atomic_json, file_sha256, load_library
from model import LANES, payload_hash
from search import _load_hashed, _manifest_body, status
from topology_space import observed_behavior_summary
import formal_run


HERE = Path(__file__).resolve().parent
SOURCE_NAMES = (
    "model.py", "library.py", "compiler.py", "runtime.py", "materialize.py",
    "evaluator.py", "evolution.py", "search.py", "scheduler_audit.py",
    "topology_space.py", "e1_artifact_audit.py", "cpu_calibrate.py",
    "machine_checks.py", "e1b_verify.py", "formal_run.py", "cli.py",
    "seed_accounting.py", "test_async_v2.py",
)


def _hashed(path: Path, field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = dict(payload)
    expected = body.pop(field, None)
    actual = payload_hash(body)
    if not expected or expected != actual:
        raise ValueError(f"{path} {field} mismatch: expected={expected} actual={actual}")
    return payload


def _decision_markdown(result: dict[str, Any]) -> str:
    cpu = result["worker_calibration"]
    lines = [
        "# Async E1b technical development decision",
        "",
        f"**{result['decision']}**",
        "",
        "This is a technical-only preflight result. It does not launch E1b,",
        "re-execute retained E1 seeds, authorize E2, or claim strategy efficacy.",
        "",
        "## Evidence",
        "",
        f"- Retained E1 audit: 4096 jobs, 235 unique lane-genomes, 36 no-op, 199 behavior-changing.",
        f"- Static/technical topology capacity: {result['topology_capacity']['compile_distinct_nonempty_per_lane']} compile-distinct nonempty semantic phenotypes per lane; this is not an exact action-change claim.",
        f"- Exact technical observed action-change: {result['technical_smoke']['observed_behavior_by_lane']}.",
        f"- Windows spawn scheduler/cache/checkpoint/failure audit: pass={str(result['scheduler']['pass']).lower()}.",
        f"- Technical smoke: seed {TECHNICAL_SEED} only, {result['technical_smoke']['jobs']} complete jobs; all finalists both-seat parity={str(result['technical_smoke']['all_finalists_parity']).lower()}.",
        f"- Formal launcher plumbing: registry_run_id={result['formal_launcher']['registry_run_id']}, retained seeds={result['formal_launcher']['retained_consumed_e1_seeds']}, fresh_evaluation_seeds={result['formal_launcher']['fresh_evaluation_seeds']}; authority hashes validated={str(result['formal_launcher']['authority_hashes_validated']).lower()}, execution_started=false.",
        f"- Failed preflight negative evidence preserved: manifest_sha256={result['failed_preflight_negative_evidence']['manifest_file_sha256']}; launch/PID evidence present=false.",
        f"- 15-worker process-tree CPU: mean={cpu['mean']:.3f}%, median={cpu['median']:.3f}%, p95={cpu['p95']:.3f}%, peak={cpu['peak']:.3f}%; overall throughput={cpu['overall_throughput']:.6f} candidate-context jobs/s.",
        f"- Formal/fresh seeds executed=false; retained E1 seeds re-executed=false; E2 games executed=false.",
        "",
        "## Boundary",
        "",
        "The progressive E1b protocol remains non-executable. A new explicit",
        "authorization is required before the consumed E1 small screen or any",
        "later stage is run.",
        "",
    ]
    return "\n".join(lines)


def verify(
    *,
    library_path: Path,
    capacity_path: Path,
    e1_audit_path: Path,
    scheduler_path: Path,
    compile_smoke_path: Path,
    technical_run_root: Path,
    calibration_path: Path,
    machine_checks_path: Path,
    protocol_path: Path,
    transcript_path: Path,
    output: Path,
    decision_path: Path,
) -> dict[str, Any]:
    library = load_library(library_path)
    capacity = _hashed(capacity_path, "topology_capacity_sha256")
    e1_audit = _hashed(e1_audit_path, "e1_artifact_audit_sha256")
    scheduler = _hashed(scheduler_path, "scheduler_audit_sha256")
    compile_smoke = _load_hashed(compile_smoke_path, "compile_smoke_sha256")
    summary = _load_hashed(technical_run_root / "search_summary.json", "summary_sha256")
    parity = _load_hashed(technical_run_root / "parity.json", "parity_sha256")
    calibration = _hashed(calibration_path, "cpu_calibration_sha256")
    machine = _hashed(machine_checks_path, "machine_checks_sha256")
    snapshot = status(technical_run_root)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    current_engine = engine_fingerprint()
    engine_keys = ("commit", "python_blob", "configuration_blob", "python_sha256", "configuration_sha256")
    engine_equal = all(
        artifact.get("engine", {}).get(key) == current_engine.get(key)
        for artifact in (capacity, machine)
        for key in engine_keys
    )
    compile_islands = {
        lane: compile_smoke["lanes"][lane].get("island_counts", {})
        for lane in LANES
    }
    score_islands = {
        lane: sorted({row["island"] for row in summary["scores"][lane]})
        for lane in LANES
    }
    finalists = {
        lane: set(summary["finalist_candidate_ids"][lane]) for lane in LANES
    }
    no_op_finalists = {
        lane: sorted(
            row["candidate_id"] for row in summary["scores"][lane]
            if row["candidate_id"] in finalists[lane] and not row.get("behavior_changing", False)
        )
        for lane in LANES
    }
    parity_counts = {lane: int(parity["lanes"][lane]["count"]) for lane in LANES}
    all_finalists_parity = bool(parity["pass"]) and all(
        parity_counts[lane] == len(finalists[lane])
        and all(
            row["pass"] and len(row["seats"]) == 2 and all(seat["equal"] for seat in row["seats"])
            for row in parity["lanes"][lane]["finalists"]
        )
        for lane in LANES
    )
    job_counts = [int(row.get("counts", {}).get("complete", 0)) for row in snapshot.get("generations", [])]
    cpu_pool = calibration["program_tree_cpu_percent_parallel_pool"]
    throughput = calibration["throughput_completed_jobs_per_second"]
    observed_behavior = {
        lane: observed_behavior_summary(summary["scores"][lane]) for lane in LANES
    }
    seed_accounting = summary["seed_accounting"]
    formal_protocol_path = HERE / "formal" / "e1b_protocol_authorized_20260815.json"
    formal_protocol, formal_validated = formal_run._protocol(formal_protocol_path)
    formal_registry_path = HERE / "formal" / "e1b_seed_registry_20260815.json"
    formal_authority_valid = (
        formal_protocol["schema_version"] == 2
        and formal_validated["authority"]["protocol_file_sha256"] == file_sha256(formal_protocol_path)
        and formal_validated["authority"]["seed_registry_file_sha256"] == file_sha256(formal_registry_path)
    )
    formal_manifest_preview = _manifest_body(
        formal_validated["library_path"], formal_validated["library"],
        int(formal_protocol["population_per_lane"]), int(formal_protocol["generations"]),
        formal_validated["opponents"], int(formal_protocol["proposal_seed"]),
        formal_validated["seeds"], True, formal_validated["authority"],
        formal_validated["fresh_evaluation_seeds"], formal_validated["registry_path"],
        formal_validated["registry"],
    )
    failed_preflight_root = HERE / "artifacts" / "formal" / "async_e1b_20260815_consumed_small_screen"
    failed_manifest_path = failed_preflight_root / "run" / "search_manifest.json"
    failed_manifest = _load_hashed(failed_manifest_path, "manifest_sha256")
    failed_launch_evidence = sorted(
        str(path) for path in failed_preflight_root.rglob("*")
        if path.is_file() and ("launch" in path.name.lower() or "pid" in path.name.lower())
    )
    checks = {
        "retained_e1_local_audit": bool(e1_audit["pass"]),
        "retained_e1_counts": e1_audit["counts"]["candidate_context_jobs"] == 4096 and e1_audit["counts"]["unique_lane_genomes"] == 235 and e1_audit["counts"]["semantic_no_op"] == 36 and e1_audit["counts"]["behavior_changing"] == 199,
        "compile_distinct_nonempty_capacity_per_lane": bool(capacity["pass"]) and all(
            capacity["lanes"][lane]["compile_distinct_nonempty_semantic_phenotypes"] == 1500
            for lane in LANES
        ),
        "semantic_nonempty_not_observed_behavior": (
            observed_behavior["v27_current_meta"]["observed_action_no_op_phenotypes"] > 0
            and "ac_bf69712345be6ebcf0a80f89"
            in observed_behavior["v27_current_meta"]["observed_action_no_op_candidate_ids"]
            and all(row["behavior_flag_consistent"] for row in observed_behavior.values())
        ),
        "eight_window_bound": all(capacity["lanes"][lane]["maximum_event_linked_windows"] <= 8 for lane in LANES),
        "four_islands_capacity": all(all(capacity["lanes"][lane]["island_counts"].get(island, 0) > 0 for island in ("route", "market", "constants", "coupled")) for lane in LANES),
        "four_islands_compile_smoke": all(all(compile_islands[lane].get(island, 0) > 0 for island in ("route", "market", "constants", "coupled")) for lane in LANES),
        "four_islands_evaluated": all(score_islands[lane] == ["constants", "coupled", "market", "route"] for lane in LANES),
        "scheduler": bool(scheduler["pass"]),
        "spawn": scheduler.get("spawn_start_method") == "spawn",
        "cache": all(scheduler["candidate_context_cache"].values()) and summary["cache"]["shard_cache_hits"] > 0,
        "checkpoint_resume_corrupt": scheduler["checkpoint"]["loaded"] and scheduler["checkpoint"]["corrupt_returns_none"] and scheduler["checkpoint"]["preserved_corrupt"] and snapshot["checkpoint"]["valid"],
        "status_read_only": all(scheduler["status_read_only"].values()),
        "technical_jobs": job_counts == [32, 32],
        "technical_seed_only": (
            summary["evaluation_seeds"] == [TECHNICAL_SEED]
            and seed_accounting["technical_seeds"] == [TECHNICAL_SEED]
            and seed_accounting["retained_consumed_e1_seeds"] == []
            and seed_accounting["fresh_seeds"] == []
            and seed_accounting["unclassified_seeds"] == []
            and not summary["formal_authorized"]
            and not summary["formal_fresh_seeds_executed"]
            and not summary["retained_e1_seeds_executed"]
        ),
        "formal_retained_launcher_plumbing": (
            tuple(formal_validated["seeds"]) == (81426017, 81426029)
            and tuple(formal_validated["fresh_evaluation_seeds"]) == ()
            and formal_validated["seed_accounting"]["registry_run_id"]
            == "async-e1b-20260815-consumed-small-screen"
            and formal_validated["seed_accounting"]["retained_consumed_e1_seeds"]
            == [81426017, 81426029]
            and formal_validated["seed_accounting"]["retained_e1_seeds_configured"] is True
            and formal_validated["seed_accounting"]["retained_e1_seeds_executed"] is False
            and formal_validated["seed_accounting"]["execution_started"] is False
            and formal_validated["seed_accounting"]["execution_completed"] is False
            and formal_validated["seed_accounting"]["formal_fresh_seeds_executed"] is False
            and formal_authority_valid
        ),
        "formal_nondefault_registry_manifest": (
            formal_manifest_preview["seed_registry_run_id"]
            == "async-e1b-20260815-consumed-small-screen"
            and formal_manifest_preview["seed_registry_file_sha256"]
            == formal_validated["authority"]["seed_registry_file_sha256"]
            and formal_manifest_preview["seed_accounting"] == formal_validated["seed_accounting"]
            and formal_manifest_preview["execution_started"] is False
            and formal_manifest_preview["execution_completed"] is False
            and formal_manifest_preview["retained_e1_seeds_executed"] is False
        ),
        "failed_preflight_negative_evidence_preserved": (
            failed_manifest["seed_accounting"]["registry_run_id"] == "async-e1-20260814"
            and not failed_launch_evidence
        ),
        "no_noop_finalists": all(not values for values in no_op_finalists.values()),
        "all_finalists_parity": all_finalists_parity,
        "action_digest_dedup": any(summary["action_digest_duplicates"][lane] for lane in LANES),
        "worker_default_cap": calibration["workers"] == 15 and protocol["workers"]["default"] == 15 and protocol["workers"]["maximum"] == 15,
        "process_tree_metrics": all(key in cpu_pool for key in ("mean", "median", "p95", "maximum")) and all(key in throughput for key in ("mean", "median", "p95", "maximum")),
        "machine_checks": bool(machine["pass"]),
        "engine_config": engine_equal and current_engine["python_blob"] == "4b78842d0f2d4abf6e318a8248b6306454f5c714" and current_engine["configuration_blob"] == "0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8",
        "protocol_non_executable": (
            protocol["stage"] == "E1b"
            and protocol["executable"] is False
            and protocol["formal_authorized"] is False
            and "compile_distinct_nonempty_semantic_per_lane_minimum" in protocol["topology_contract"]
            and "behavior_changing_unique_per_lane_minimum" not in protocol["topology_contract"]
            and all(not row["execute_in_this_development"] for row in protocol["progressive_stages"])
        ),
        "no_forbidden_seeds": not any((
            summary["formal_fresh_seeds_executed"],
            summary["retained_e1_seeds_executed"],
            capacity["formal_fresh_seeds_executed"], capacity["e1_seeds_reexecuted"],
            e1_audit["formal_fresh_seeds_executed"], e1_audit["e1_seeds_reexecuted"],
            calibration["formal_fresh_seeds_executed"], machine["formal_fresh_seeds_executed"],
            machine["e1_seeds_reexecuted"], machine["e2_games_executed"],
        )),
    }
    passed = all(checks.values())
    body = {
        "schema_version": 1,
        "decision": "READY_FOR_E1B_PREFLIGHT" if passed else "DEVELOPMENT_REMEDIATION_REQUIRED",
        "pass": passed,
        "checks": checks,
        "engine": current_engine,
        "controls": {lane: file_sha256(CONTROLS[lane]) for lane in LANES},
        "sources": {name: file_sha256(HERE / name) for name in SOURCE_NAMES},
        "protocol": {"path": str(protocol_path), "sha256": file_sha256(protocol_path), "executable": False},
        "library_sha256": library["library_sha256"],
        "retained_e1": {"sha256": e1_audit["e1_artifact_audit_sha256"], "counts": e1_audit["counts"], "requested_action_digests": e1_audit["requested_action_digests"]},
        "topology_capacity": {
            "sha256": capacity["topology_capacity_sha256"],
            "claim": "compile-distinct nonempty semantic phenotypes; not exact behavior-changing",
            "compile_distinct_nonempty_per_lane": {
                lane: capacity["lanes"][lane]["compile_distinct_nonempty_semantic_phenotypes"]
                for lane in LANES
            },
        },
        "scheduler": {"sha256": scheduler["scheduler_audit_sha256"], "pass": scheduler["pass"]},
        "technical_smoke": {
            "summary_sha256": summary["summary_sha256"], "jobs": sum(job_counts),
            "evaluation_seeds": summary["evaluation_seeds"], "seed_accounting": seed_accounting,
            "observed_behavior_by_lane": observed_behavior,
            "finalists": summary["finalist_candidate_ids"],
            "all_finalists_parity": all_finalists_parity,
            "no_op_finalists": no_op_finalists, "cache": summary["cache"],
        },
        "formal_launcher": {
            "protocol_schema_version": formal_protocol["schema_version"],
            "registry_run_id": formal_validated["seed_accounting"]["registry_run_id"],
            "retained_consumed_e1_seeds": list(formal_validated["seeds"]),
            "fresh_evaluation_seeds": list(formal_validated["fresh_evaluation_seeds"]),
            "retained_e1_seeds_configured": formal_validated["seed_accounting"]["retained_e1_seeds_configured"],
            "execution_started": formal_validated["seed_accounting"]["execution_started"],
            "execution_completed": formal_validated["seed_accounting"]["execution_completed"],
            "retained_e1_seeds_executed": formal_validated["seed_accounting"]["retained_e1_seeds_executed"],
            "formal_fresh_seeds_executed": formal_validated["seed_accounting"]["formal_fresh_seeds_executed"],
            "authority_hashes_validated": formal_authority_valid,
            "protocol_sha256": file_sha256(formal_protocol_path),
            "seed_registry_sha256": file_sha256(formal_registry_path),
            "manifest_preview_registry_run_id": formal_manifest_preview["seed_registry_run_id"],
            "manifest_preview_registry_sha256": formal_manifest_preview["seed_registry_file_sha256"],
            "manifest_preview_execution_started": formal_manifest_preview["execution_started"],
            "manifest_preview_execution_completed": formal_manifest_preview["execution_completed"],
        },
        "failed_preflight_negative_evidence": {
            "path": str(failed_preflight_root),
            "manifest_file_sha256": file_sha256(failed_manifest_path),
            "wrong_registry_run_id": failed_manifest["seed_accounting"]["registry_run_id"],
            "wrong_registry_sha256": failed_manifest["seed_accounting"]["seed_registry_file_sha256"],
            "launch_or_pid_evidence": failed_launch_evidence,
        },
        "worker_calibration": {"sha256": calibration["cpu_calibration_sha256"], "workers": 15, "mean": cpu_pool["mean"], "median": cpu_pool["median"], "p95": cpu_pool["p95"], "peak": cpu_pool["maximum"], "overall_throughput": calibration["throughput_candidate_context_jobs_per_second"], "throughput_distribution": throughput},
        "machine_checks": {"sha256": machine["machine_checks_sha256"], "transcript": str(transcript_path), "transcript_sha256": file_sha256(transcript_path)},
        "formal_authorized": bool(summary["formal_authorized"]),
        "formal_fresh_seeds_executed": bool(summary["formal_fresh_seeds_executed"]),
        "e1_seeds_reexecuted": bool(summary["retained_e1_seeds_executed"]),
        "e2_games_executed": False,
        "stronger_strategy_claim": False,
    }
    result = {**body, "e1b_verification_sha256": payload_hash(body)}
    atomic_json(output, result)
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(_decision_markdown(result), encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--capacity", type=Path, required=True)
    parser.add_argument("--e1-audit", type=Path, required=True)
    parser.add_argument("--scheduler", type=Path, required=True)
    parser.add_argument("--compile-smoke", type=Path, required=True)
    parser.add_argument("--technical-run-root", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--machine-checks", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    args = parser.parse_args()
    result = verify(
        library_path=args.library, capacity_path=args.capacity,
        e1_audit_path=args.e1_audit, scheduler_path=args.scheduler,
        compile_smoke_path=args.compile_smoke, technical_run_root=args.technical_run_root,
        calibration_path=args.calibration, machine_checks_path=args.machine_checks,
        protocol_path=args.protocol, transcript_path=args.transcript,
        output=args.output, decision_path=args.decision,
    )
    print(json.dumps({"decision": result["decision"], "pass": result["pass"], "sha256": result["e1b_verification_sha256"], "output": str(args.output)}, sort_keys=True))
