"""Create machine-readable and human v2 development decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compiler import CONTROLS
from evaluator import TECHNICAL_SEED, engine_fingerprint
from library import atomic_json, file_sha256, load_library
from model import LANES, payload_hash
from search import _load_hashed, status


HERE = Path(__file__).resolve().parent
SOURCES = (
    "model.py", "library.py", "compiler.py", "runtime.py", "materialize.py",
    "evaluator.py", "evolution.py", "search.py", "scheduler_audit.py", "cli.py",
    "test_async_v2.py",
)


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Async topology v2 development decision",
        "",
        f"**{payload['decision']}**",
        "",
        "The corrected searcher can evolve several route blocks, public-market",
        "policies, and lane-owned constants in one genome.  It does not pool v27",
        "and Boatlee evidence.",
        "",
        "## Verification",
        "",
        f"- Motif library: {payload['motif_counts']['v27_current_meta']} v27 and {payload['motif_counts']['boatlee_v16_rc2_market_relay']} Boatlee lane-qualified blocks.",
        f"- Compile smoke: {payload['compile_smoke']['compiled_per_lane']} candidates/lane; {payload['compile_smoke']['multi_gene_per_lane']} multi-gene candidates/lane.",
        f"- Exact technical search: {payload['technical_search']['jobs']} jobs, {payload['technical_search']['generations']} generations, seed `{TECHNICAL_SEED}` only.",
        f"- Scheduler audit: worker 1/>1 equality={str(payload['scheduler']['serial_parallel_equal']).lower()}, corrupt resume={str(payload['scheduler']['corrupt_resume']).lower()}, failure injection={str(payload['scheduler']['failure_injection']).lower()}.",
        f"- Fast/standalone both-seat parity={str(payload['parity']['pass']).lower()}.",
        "- Formal v2 fresh seeds executed=false.",
        "",
        "## Efficacy boundary",
        "",
        "The small technical search selected the unchanged control in both lanes.",
        "This verifies the search machinery and preservation of negative evidence;",
        "it is not evidence that a stronger strategy has already been found.",
        "The superseded ninth-cow S1 does not unlock S2.",
        "",
        "## Known limitations",
        "",
        "- Only one consumed technical seed and a 4x2 development population were evaluated.",
        "- Unit-block compatibility is certified against a lane control trace; a",
        "  different public entry position causes bounded incumbent fallback.",
        "- Engine market physics remain exact and immutable.  Search mutates only",
        "  policy thresholds, model weights, order quantities, and timing.",
        "- A new seed scan, protocol, and explicit authorization are required before",
        "  any async-v2 formal search.",
        "",
    ]
    return "\n".join(lines)


def verify(library_path: Path, run_root: Path, scheduler_path: Path, compile_smoke_path: Path, output: Path, decision_path: Path) -> dict[str, Any]:
    library = load_library(library_path)
    compile_smoke = _load_hashed(compile_smoke_path, "compile_smoke_sha256")
    summary = _load_hashed(run_root / "search_summary.json", "summary_sha256")
    parity = _load_hashed(run_root / "parity.json", "parity_sha256")
    scheduler = _load_hashed(scheduler_path, "scheduler_audit_sha256")
    snapshot = status(run_root)
    motif_counts = {lane: len(library["lanes"][lane]["motifs"]) for lane in LANES}
    compiled_counts = {lane: len(compile_smoke["lanes"][lane]["compiled"]) for lane in LANES}
    multi_counts = {lane: int(compile_smoke["lanes"][lane]["multi_gene_candidates"]) for lane in LANES}
    job_counts = [generation.get("counts", {}).get("complete", 0) for generation in snapshot.get("generations", [])]
    evaluated_coupled = {
        lane: sum(int(row["complexity"]) >= 2 for row in summary["scores"][lane])
        for lane in LANES
    }
    control_selected = {
        lane: next(row for row in summary["scores"][lane] if row["candidate_id"] == summary["best_candidate_ids"][lane])["complexity"] == 0
        for lane in LANES
    }
    checks = {
        "library_nontrivial": all(value >= 100 for value in motif_counts.values()),
        "compile_population_complete": all(value >= 8 for value in compiled_counts.values()),
        "compile_contains_multi_gene": all(value > 0 for value in multi_counts.values()),
        "coupled_candidates_evaluated": all(value > 0 for value in evaluated_coupled.values()),
        "technical_jobs_complete": bool(job_counts) and all(value == 32 for value in job_counts),
        "technical_only": summary["technical_seed"] == TECHNICAL_SEED and not summary["formal_fresh_seeds_executed"],
        "parity": bool(parity["pass"]),
        "scheduler": bool(scheduler["pass"]),
        "engine": engine_fingerprint()["python_blob"] == "4b78842d0f2d4abf6e318a8248b6306454f5c714" and engine_fingerprint()["configuration_blob"] == "0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8",
        "lane_controls_distinct": file_sha256(CONTROLS[LANES[0]]) != file_sha256(CONTROLS[LANES[1]]),
    }
    passed = all(checks.values())
    body = {
        "schema_version": 2,
        "decision": "READY_FOR_ASYNC_FORMAL_PREFLIGHT" if passed else "ASYNC_DEVELOPMENT_REMEDIATION_REQUIRED",
        "pass": passed,
        "checks": checks,
        "engine": engine_fingerprint(),
        "controls": {lane: file_sha256(CONTROLS[lane]) for lane in LANES},
        "sources": {name: file_sha256(HERE / name) for name in SOURCES},
        "library_sha256": library["library_sha256"],
        "motif_counts": motif_counts,
        "compile_smoke": {
            "sha256": compile_smoke["compile_smoke_sha256"],
            "compiled_per_lane": compiled_counts,
            "multi_gene_per_lane": multi_counts,
        },
        "technical_search": {
            "summary_sha256": summary["summary_sha256"],
            "manifest_sha256": snapshot["manifest_sha256"],
            "jobs": sum(job_counts),
            "generations": len(job_counts),
            "evaluated_coupled_per_lane": evaluated_coupled,
            "best_candidate_ids": summary["best_candidate_ids"],
            "control_selected": control_selected,
            "stronger_strategy_claim": False,
        },
        "scheduler": {
            "sha256": scheduler["scheduler_audit_sha256"],
            "serial_parallel_equal": scheduler["serial_parallel_equal"],
            "corrupt_resume": scheduler["corrupt_resume"]["repaired_complete"] and scheduler["corrupt_resume"]["preserved_corrupt"],
            "failure_injection": all(not row["failed_has_efficacy"] and row["resumed_status"] == "complete" for row in scheduler["failure_injection"].values()),
        },
        "parity": {"sha256": parity["parity_sha256"], "pass": parity["pass"]},
        "superseded_s1": {
            "status": "SEARCH_SURFACE_SUPERSEDED_NO_S2",
            "consumed_fresh_seeds": [20260814, 20260815, 20260816],
        },
        "formal_v2_fresh_seeds_executed": False,
    }
    result = {**body, "development_verification_sha256": payload_hash(body)}
    atomic_json(output, result)
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(_markdown(result), encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--scheduler", type=Path, required=True)
    parser.add_argument("--compile-smoke", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.library, args.run_root, args.scheduler, args.compile_smoke, args.output, args.decision)
    print(json.dumps({"decision": result["decision"], "pass": result["pass"], "development_verification_sha256": result["development_verification_sha256"]}, sort_keys=True))
