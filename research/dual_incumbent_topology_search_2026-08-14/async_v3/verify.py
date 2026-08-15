"""Machine verification for the Async V3 development-only deliverable."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import tempfile
from typing import Any

from compiler import compile_fixture_anchors
from evaluator import (
    CONTROLS,
    TECHNICAL_SEED,
    behavior_view,
    engine_fingerprint,
    run_control,
    run_fast,
    run_standalone,
    technical_valid,
)
from fixture import HERE, file_sha256, verify_frozen_evidence
from materialize import isolated_import, static_audit
from model import payload_hash
from ranking import rank_frontiers
from scheduler import atomic_json, development_audit
from formal_run import dry_mock_proof


ARTIFACTS = HERE / "artifacts" / "development"


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, prefix=f".{path.name}.") as stream:
        stream.write(text)
        temporary = Path(stream.name)
    temporary.replace(path)


def _source_hashes() -> dict[str, str]:
    return {path.name: file_sha256(path) for path in sorted(HERE.glob("*.py"))}


def _control_checks() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: dict[str, Any] = {}
    summaries: list[dict[str, Any]] = []
    for lane in CONTROLS:
        seats = []
        for seat in (0, 1):
            first = run_control(lane, "other_incumbent", TECHNICAL_SEED, seat)
            second = run_control(lane, "other_incumbent", TECHNICAL_SEED, seat)
            equal = behavior_view(first) == behavior_view(second)
            seats.append({"seat": seat, "equal": equal, "summary": first.summary})
            summaries.append(first.summary)
        checks[lane] = {"seats": seats, "pass": all(row["equal"] and technical_valid(row["summary"]) for row in seats)}
    return checks, summaries


def _finalist_checks(candidates: list[Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected = {
        "boatlee_v16_rc2_market_relay": "ac_5f4a369973330bf53370f3f8",
        "v27_current_meta": "ac_b59943fc80ea1fa0ff69ce89",
    }
    by_source = {row.fixture_candidate_id: row for row in candidates}
    result: dict[str, Any] = {}
    summaries: list[dict[str, Any]] = []
    for lane, source_id in selected.items():
        candidate = by_source[source_id]
        output = ARTIFACTS / "finalists" / lane / candidate.candidate_id / "main.py"
        seats = []
        for seat in (0, 1):
            fast = run_fast(candidate, "other_incumbent", TECHNICAL_SEED, seat)
            standalone = run_standalone(candidate, output, "other_incumbent", TECHNICAL_SEED, seat)
            equal = behavior_view(fast) == behavior_view(standalone)
            seats.append({
                "seat": seat, "equal": equal, "fast": fast.summary, "standalone": standalone.summary,
                "fast_action_digest": fast.summary["action_digest"], "standalone_action_digest": standalone.summary["action_digest"],
            })
            summaries.extend((fast.summary, standalone.summary))
        static = static_audit(output)
        isolated = isolated_import(output)
        result[lane] = {"fixture_candidate_id": source_id, "candidate_id": candidate.candidate_id, "artifact": str(output), "seats": seats, "static": static, "isolated": isolated, "pass": candidate.fixture_match and all(row["equal"] and technical_valid(row["fast"]) and technical_valid(row["standalone"]) for row in seats) and static["pass"] and isolated["callable_agent"]}
    return result, summaries


def _latency(summaries: list[dict[str, Any]]) -> dict[str, float | bool]:
    p95 = max(float(row["latency_ms"]["p95"]) for row in summaries)
    maximum = max(float(row["latency_ms"]["max"]) for row in summaries)
    return {"p95_ms": p95, "max_ms": maximum, "p95_under_150": p95 < 150.0, "max_under_750": maximum < 750.0}


def verify(*, technical_seed: int, workers: int, compare_workers: int | None = None) -> dict[str, Any]:
    if int(technical_seed) != TECHNICAL_SEED:
        raise PermissionError(f"only technical seed {TECHNICAL_SEED} is allowed")
    if not 1 <= int(workers) <= 15 or (compare_workers is not None and not 1 <= int(compare_workers) <= 15):
        raise ValueError("workers must be in 1..15")
    commands = [
        f"verify --technical-seed {TECHNICAL_SEED} --workers {workers}" + (f" --compare-workers {compare_workers}" if compare_workers else ""),
        "fixture validation (read-only)", "control reproducibility both lanes/seats", "finalist fast/standalone parity both lanes/seats", "spawn scheduler 1-vs-4 and failure audit",
        "frozen formal preflight/status/dry-mock pipeline (no E1c engine game)",
    ]
    errors: list[str] = []
    fixture = verify_frozen_evidence(HERE / "fixtures" / "e1b_regression_fixtures.json")
    candidates = compile_fixture_anchors(HERE / "fixtures" / "e1b_regression_fixtures.json")
    controls: dict[str, Any] = {}
    finalists: dict[str, Any] = {}
    all_summaries: list[dict[str, Any]] = []
    engine: dict[str, Any] | None = None
    scheduler: dict[str, Any] = {}
    formal_pipeline: dict[str, Any] = {}
    try:
        engine = engine_fingerprint()
        controls, control_summaries = _control_checks()
        finalists, finalist_summaries = _finalist_checks(candidates)
        all_summaries = control_summaries + finalist_summaries
        scheduler = development_audit(ARTIFACTS / "scheduler_audit")
        formal_pipeline = dry_mock_proof(ARTIFACTS / "formal_pipeline_dry_mock_4", workers=4, compare_workers=1, population=6, generations=2)
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
    latency = _latency(all_summaries) if all_summaries else {"p95_ms": None, "max_ms": None, "p95_under_150": False, "max_under_750": False}
    frontier = rank_frontiers(json.loads((HERE / "fixtures" / "e1b_regression_fixtures.json").read_text(encoding="utf-8")))
    checks = {
        "frozen_evidence": fixture["pass"], "anchors": len(candidates) == 4 and all(row.accepted and row.fixture_match for row in candidates),
        "engine": bool(engine and engine.get("python_blob") == "4b78842d0f2d4abf6e318a8248b6306454f5c714" and engine.get("configuration_blob") == "0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8"),
        "controls": bool(controls) and all(row["pass"] for row in controls.values()),
        "parity": bool(finalists) and all(row["pass"] for row in finalists.values()),
        "latency": bool(latency["p95_under_150"] and latency["max_under_750"]),
        "scheduler": bool(scheduler.get("pass")),
        "formal_pipeline": bool(formal_pipeline.get("pass")),
        "formal_fresh_seeds_executed": False,
    }
    passed = all(value for key, value in checks.items() if key != "formal_fresh_seeds_executed") and not errors
    body = {
        "schema_version": 3, "decision": "READY_FOR_E1C_CONSUMED_SEED_RUN" if passed else "E1C_DEVELOPMENT_REMEDIATION_REQUIRED", "pass": passed,
        "commands": commands, "technical_seed": TECHNICAL_SEED, "evaluation_seeds": [TECHNICAL_SEED], "formal_fresh_seeds_executed": False,
        "requested_workers": workers, "compare_workers": compare_workers, "checks": checks, "errors": errors,
        "engine": engine, "fixture": fixture, "controls": {lane: file_sha256(path) for lane, path in CONTROLS.items()}, "sources": _source_hashes(),
        "anchor_candidates": [{"lane": row.lane, "fixture_candidate_id": row.fixture_candidate_id, "candidate_id": row.candidate_id, "fixture_match": row.fixture_match} for row in candidates],
        "frontiers": frontier, "control_reproducibility": controls, "finalist_parity": finalists, "latency": latency, "scheduler": scheduler,
        "formal_pipeline_dry_mock": formal_pipeline,
    }
    body["development_verification_sha256"] = payload_hash({key: value for key, value in body.items() if key != "development_verification_sha256"})
    atomic_json(ARTIFACTS / "development_verification.json", body)
    _atomic_text(ARTIFACTS / "command_transcript.txt", "Kaggriculture Async V3 development command transcript\n" + "\n".join(commands) + "\npass=" + str(passed).lower() + "\n")
    decision = "# Async V3 / E1c development decision\n\n**" + body["decision"] + "**\n\nTechnical verification used only seed `811407`. The formal pipeline was exercised only in deterministic dry/mock mode; no E1c, E2, or fresh seed was executed. `formal_fresh_seeds_executed=false`.\n"
    _atomic_text(HERE / "development_decision.md", decision)
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--technical-seed", type=int, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--compare-workers", type=int)
    args = parser.parse_args()
    result = verify(technical_seed=args.technical_seed, workers=args.workers, compare_workers=args.compare_workers)
    print(json.dumps({"decision": result["decision"], "pass": result["pass"], "development_verification_sha256": result["development_verification_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
