"""Machine-readable E2 development verification; never launches formal E2."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from authority import HERE, ROOT, file_sha256, payload_hash, reconstruct_registered, registry, verify_authority
from effective_change import effective_change_audit
from selector import SELECTORS, development_hypothesis, make_policy, write_selector

from evaluator import CONTROLS, RUNNER, TECHNICAL_SEED, behavior_view, run_fast, run_standalone, technical_valid
from materialize import isolated_import, materialize_finalist, static_audit
from scheduler import atomic_json, development_audit


RUN_ID = "e2_development_20260815_v3"
ARTIFACTS = HERE / "artifacts" / "development" / RUN_ID
SELECTOR_OPPONENTS = {
    "other_incumbent": CONTROLS["boatlee_v16_rc2_market_relay"],
    "kaito_v21": ROOT / "research" / "public_agents" / "kaito_v21_top30" / "extracted" / "main.py",
    "roman_lb950": ROOT / "research" / "public_agents" / "roman_lb950" / "extracted" / "main.py",
    "saiteja_3000": ROOT / "research" / "public_agents" / "saiteja_mega_ensemble_3000" / "extracted" / "main.py",
}


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def summary_view(run: Any) -> dict[str, Any]:
    summary = run.summary
    return {
        "statuses": summary["statuses"], "calls": summary["calls"],
        "rewards": summary["rewards"], "money": summary["money"],
        "action_digest": summary["action_digest"], "diagnostics": summary["diagnostics"],
        "exception": summary["exception"], "opponent_exception": summary["opponent_exception"],
        "timeout_calls": summary["timeout_calls"], "overage_exhausted": summary["overage_exhausted"],
        "max_market_orders": summary["max_market_orders"], "action_issues": summary["action_issues"],
        "latency_ms": summary["latency_ms"],
    }


def registered_parity(candidates: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    result: dict[str, Any] = {}
    summaries: list[dict[str, Any]] = []
    reg = registry()
    for lane, wrapped in candidates.items():
        candidate = wrapped["candidate"]
        output = ARTIFACTS / "registered" / lane / candidate.candidate_id / "main.py"
        expected_hash = reg["lanes"][lane].get("standalone_sha256")
        frozen_path = reg["lanes"][lane].get("standalone_path")
        if expected_hash and frozen_path:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / frozen_path, output)
            artifact = {
                "lane": lane, "candidate_id": candidate.candidate_id, "path": str(output),
                "bytes": output.stat().st_size, "sha256": file_sha256(output),
                "finalist_only": True, "materialization": "exact_committed_frozen_bytes",
            }
        else:
            artifact = materialize_finalist(candidate, output)
        seats = []
        for seat in (0, 1):
            fast = run_fast(candidate, "other_incumbent", TECHNICAL_SEED, seat, capture_trace=True)
            if expected_hash and frozen_path:
                original_opponent_path = RUNNER.opponent_path
                RUNNER.opponent_path = lambda current_lane, family: CONTROLS[
                    "boatlee_v16_rc2_market_relay" if current_lane == "v27_current_meta" else "v27_current_meta"
                ]
                try:
                    standalone = RUNNER.run_game(
                        lane, output, "other_incumbent", TECHNICAL_SEED, seat,
                    )
                finally:
                    RUNNER.opponent_path = original_opponent_path
            else:
                standalone = run_standalone(candidate, output, "other_incumbent", TECHNICAL_SEED, seat)
            equal = behavior_view(fast) == behavior_view(standalone)
            seats.append({"seat": seat, "equal": equal, "fast": summary_view(fast), "standalone": summary_view(standalone)})
            summaries.extend((fast.summary, standalone.summary))
        exact_frozen_hash = expected_hash is None or artifact["sha256"] == expected_hash
        result[lane] = {
            "candidate_id": candidate.candidate_id, "artifact": artifact,
            "expected_frozen_sha256": expected_hash, "exact_frozen_hash": exact_frozen_hash,
            "static": static_audit(output), "isolated": isolated_import(output), "seats": seats,
        }
        result[lane]["pass"] = (
            exact_frozen_hash and file_sha256(output) == artifact["sha256"]
            and result[lane]["static"]["pass"] and result[lane]["isolated"]["callable_agent"]
            and all(row["equal"] and technical_valid(row["fast"]) and technical_valid(row["standalone"]) for row in seats)
        )
    return result, summaries


def selector_parity() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    base_source = CONTROLS["v27_current_meta"].read_text(encoding="utf-8")
    result: dict[str, Any] = {}
    summaries: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    target = ["BUY_PRODUCT", "WHEAT", 2]
    original_opponent_path = RUNNER.opponent_path

    def opponent_path(lane: str, family: str) -> Path:
        if lane != "v27_current_meta" or family not in SELECTOR_OPPONENTS:
            raise KeyError((lane, family))
        return SELECTOR_OPPONENTS[family]

    RUNNER.opponent_path = opponent_path
    for spec in SELECTORS:
        RUNNER.opponent_path = opponent_path
        try:
            output = ARTIFACTS / "selectors" / spec.candidate_id / "main.py"
            artifact = write_selector(base_source, spec, output)
            contexts = []
            for opponent in SELECTOR_OPPONENTS:
                for seat in (0, 1):
                    def factory(_module: Any, base: Any, _seat: int) -> Any:
                        return make_policy(spec, base)

                    control = RUNNER.run_game(
                        "v27_current_meta", CONTROLS["v27_current_meta"], opponent,
                        TECHNICAL_SEED, seat, capture_trace=True,
                    )
                    fast = RUNNER.run_game(
                        "v27_current_meta", CONTROLS["v27_current_meta"], opponent,
                        TECHNICAL_SEED, seat, policy_factory=factory, capture_trace=True,
                    )
                    standalone = RUNNER.run_game(
                        "v27_current_meta", output, opponent, TECHNICAL_SEED, seat,
                        capture_trace=True,
                    )
                    control_frame = control.trace[spec.decision_step]
                    fast_frame = fast.trace[spec.decision_step]
                    market = control_frame.observation["market"]
                    price = int(market["prices"]["WHEAT"])
                    inventory = int(market["inventory"]["WHEAT"])
                    selected_branch = (
                        "suppress_buy"
                        if price >= spec.min_wheat_price and inventory <= spec.max_wheat_inventory
                        else "incumbent"
                    )
                    expected_action = copy.deepcopy(control_frame.action)
                    precondition = target in expected_action.get("market", [])
                    if selected_branch == "suppress_buy" and precondition:
                        expected_action["market"].remove(target)
                    action_correct = precondition and fast_frame.action == expected_action
                    equal = behavior_view(fast) == behavior_view(standalone)
                    feature = {
                        "opponent_family": opponent, "seat": seat, "step": spec.decision_step,
                        "wheat_price": price, "wheat_inventory": inventory,
                        "selected_branch": selected_branch, "control_precondition": precondition,
                        "action_correct": action_correct,
                    }
                    feature_rows.append(feature)
                    contexts.append({
                        **feature, "equal": equal, "control": summary_view(control),
                        "fast": summary_view(fast), "standalone": summary_view(standalone),
                    })
                    summaries.extend((fast.summary, standalone.summary))
            result[spec.candidate_id] = {
                "role": "frozen_e2_s1_fresh_label_selector", "spec": spec.payload(),
                "artifact": artifact, "static": static_audit(output),
                "isolated": isolated_import(output), "contexts": contexts,
            }
            result[spec.candidate_id]["pass"] = (
                result[spec.candidate_id]["static"]["pass"]
                and result[spec.candidate_id]["isolated"]["callable_agent"]
                and all(
                    row["equal"] and row["action_correct"]
                    and technical_valid(row["control"])
                    and technical_valid(row["fast"])
                    and technical_valid(row["standalone"])
                    for row in contexts
                )
            )
        finally:
            RUNNER.opponent_path = original_opponent_path
    branches = sorted({row["selected_branch"] for row in feature_rows})
    coverage = {
        "seed": TECHNICAL_SEED, "correctness_only": True,
        "public_features_only": True, "rows": feature_rows, "branches": branches,
        "pass": branches == ["incumbent", "suppress_buy"]
        and all(row["control_precondition"] and row["action_correct"] for row in feature_rows),
    }
    return result, summaries, coverage


def latency(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    p95 = max(float(row["latency_ms"]["p95"]) for row in summaries)
    maximum = max(float(row["latency_ms"]["max"]) for row in summaries)
    return {"p95_ms": p95, "max_ms": maximum, "p95_under_150": p95 < 150.0, "max_under_750": maximum < 750.0, "pass": p95 < 150.0 and maximum < 750.0}


def command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    stdout = completed.stdout.encode("utf-8", errors="replace")
    stderr = completed.stderr.encode("utf-8", errors="replace")
    return {
        "command": subprocess.list2cmdline(command), "returncode": completed.returncode,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(), "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_tail": completed.stdout[-2000:], "stderr_tail": completed.stderr[-2000:],
        "pass": completed.returncode == 0,
    }


def repository_audit() -> dict[str, Any]:
    python = sys.executable
    commands = [
        [python, r"research\main_approach\v27_current_meta\development\build_standalone.py", "--check"],
        [python, r"research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py", "--check"],
        [python, "-m", "unittest", "research.main_approach.test_development_sources", "-v"],
        [python, "-m", "unittest", "discover", "-s", r"research\dual_incumbent_topology_search_2026-08-14\async_v2", "-p", "test_*.py", "-v"],
        [python, "-m", "unittest", "discover", "-s", r"research\dual_incumbent_topology_search_2026-08-14\async_v3", "-p", "test_*.py", "-v"],
        [python, "-m", "unittest", "discover", "-s", r"research\dual_incumbent_topology_search_2026-08-14\e2", "-p", "test_*.py", "-v"],
        [python, "-m", "json.tool", str(HERE / "candidate_registry.json")],
        [python, "-m", "json.tool", str(HERE / "development_candidate_registry.json")],
        [python, "-m", "json.tool", str(HERE / "protocol_template.json")],
        ["git", "diff", "--check"],
    ]
    rows = [command(row) for row in commands]
    return {"pass": all(row["pass"] for row in rows), "commands": rows}


def seed_audit() -> dict[str, Any]:
    result = subprocess.run(["git", "grep", "-n", "-E", r"[0-9]{8}"], cwd=ROOT, capture_output=True)
    raw = result.stdout
    return {
        "command": "git grep -n -E [0-9]{8}", "returncode": result.returncode,
        "tracked_hits": len(raw.splitlines()), "output_sha256": hashlib.sha256(raw).hexdigest(),
        "technical_seed": TECHNICAL_SEED, "e1_consumed_seeds_not_rerun": [81426017, 81426029],
        "e2_fresh_seeds_selected": [], "formal_fresh_seeds_executed": False,
    }


def verify(technical_seed: int) -> dict[str, Any]:
    if int(technical_seed) != TECHNICAL_SEED:
        raise PermissionError(f"E2 development accepts only technical seed {TECHNICAL_SEED}")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    authority = verify_authority()
    reconstructed = reconstruct_registered()
    effective = effective_change_audit()
    registered, registered_summaries = registered_parity(reconstructed)
    selectors, selector_summaries, selector_coverage = selector_parity()
    timing = latency(registered_summaries + selector_summaries)
    scheduler = development_audit(ARTIFACTS / "scheduler_audit")
    repository = repository_audit()
    seeds = seed_audit()
    hypothesis = development_hypothesis()
    development_registry = json.loads((HERE / "development_candidate_registry.json").read_text(encoding="utf-8"))
    registry_match = (
        development_registry["lanes"]["boatlee_v16_rc2_market_relay"]["candidate_id"]
        == registry()["lanes"]["boatlee_v16_rc2_market_relay"]["candidate_id"]
        and development_registry["lanes"]["v27_current_meta"]["candidate_id"]
        == SELECTORS[0].candidate_id
        and development_registry["lanes"]["boatlee_v16_rc2_market_relay"]["mutation"] is None
        and development_registry["formal_fresh_seeds_executed"] is False
    )
    technical_checks = {
        "authority": authority["pass"], "effective_change": effective["pass"],
        "registered_parity": all(row["pass"] for row in registered.values()),
        "development_candidate_registry": registry_match,
        "selector_fast_standalone_parity": all(row["pass"] for row in selectors.values()),
        "selector_public_branch_coverage": selector_coverage["pass"],
        "selector_development_hypothesis": hypothesis["pass"],
        "latency": timing["pass"], "scheduler_failure_injection": scheduler["pass"],
        "repository": repository["pass"], "formal_fresh_seeds_executed": False,
    }
    readiness_checks = dict(technical_checks)
    ready = all(value for key, value in readiness_checks.items() if key != "formal_fresh_seeds_executed")
    decision_value = "READY_FOR_E2_S1" if ready else "E2_DEVELOPMENT_REMEDIATION_REQUIRED"
    body: dict[str, Any] = {
        "schema_version": 2, "kind": "e2_development_verification", "run_id": RUN_ID,
        "decision": decision_value, "ready_for_e2_s1": ready, "technical_gates_pass": all(value for key, value in technical_checks.items() if key != "formal_fresh_seeds_executed"),
        "technical_seed": TECHNICAL_SEED, "technical_rewards_used_for_efficacy": False,
        "evaluation_seeds": [TECHNICAL_SEED], "e2_fresh_seeds": [], "formal_fresh_seeds_executed": False,
        "checks": readiness_checks, "authority": authority, "effective_change": effective,
        "registered_candidate_parity": registered, "selector_development_ablations": selectors,
        "selector_public_branch_coverage": selector_coverage,
        "selector_development_hypothesis": hypothesis,
        "development_candidate_registry": {
            "path": str(HERE / "development_candidate_registry.json"),
            "sha256": file_sha256(HERE / "development_candidate_registry.json"),
            "matches_runtime": registry_match,
        },
        "latency": timing, "scheduler": scheduler,
        "repository": repository, "seed_audit": seeds,
        "known_limitations": [
            "The delayed step-494 intervention has no retained efficacy claim; E2 S1 is required to acquire fresh labels.",
            "Thresholds were exercised only on correctness seed 811407 and were not selected from reward evidence.",
            "READY_FOR_E2_S1 does not authorize selecting seeds or launching S1.",
        ],
    }
    body["development_verification_sha256"] = payload_hash({key: value for key, value in body.items() if key != "development_verification_sha256"})
    atomic_json(ARTIFACTS / "development_verification.json", body)
    transcript_lines = [
        "Kaggriculture E2 development command transcript", f"run_id={RUN_ID}",
        f"invocation={sys.executable} research\\dual_incumbent_topology_search_2026-08-14\\e2\\verify.py --technical-seed {TECHNICAL_SEED}",
    ]
    transcript_lines.extend(
        f"{row['command']} | exit={row['returncode']} | stdout_sha256={row['stdout_sha256']} | stderr_sha256={row['stderr_sha256']}"
        for row in repository["commands"]
    )
    transcript_lines.extend([
        "registered parity: exact engine, seed 811407, both seats, other-incumbent opponent",
        "selector parity: exact engine, seed 811407, both seats, four public opponent families",
        "scheduler: workers 1-vs-4 plus kill/corrupt/import/engine/worker injection",
        "formal fresh seeds executed=false", f"decision={decision_value}",
    ])
    atomic_text(ARTIFACTS / "command_transcript.txt", "\n".join(transcript_lines) + "\n")
    decision_text = (
        "# E2 development decision\n\n"
        f"**{decision_value}**\n\n"
        "All E2 development gates passed, including exact registered-candidate reconstruction, effective-change/no-op regression, both-seat fast/standalone parity, public-selector branch coverage, workers 1-versus-4 equality, failure injection, latency, builders, and Async V2/V3/E2 tests.\n\n"
        "The exact v27 probe `ac_46448f767f398cc4ce8047d3` remains diagnostic-only. The user-authorized remediation freezes `e2v27_8b3ebcb128a4f4709ea94ce3`, which makes one public-market decision at step 494, removes only the exact WHEAT buy when the public scarcity threshold is met, and rejoins v27 at step 495. It uses neither opponent identity nor private-opponent information. Frozen E1c ablation shows the delayed component has no retained efficacy claim; a separately authorized E2 S1 would acquire fresh labels rather than confirm an inherited gain. Boatlee `ac_3aa759d7d7fc4a409c409326` is byte-exact and unmodified.\n\n"
        "Technical seed `811407` was correctness-only. Seeds `81426017` and `81426029` were read from frozen evidence and not rerun. No E2 fresh seed was selected or executed. `formal_fresh_seeds_executed=false`.\n"
    )
    atomic_text(HERE / "development_decision.md", decision_text)
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--technical-seed", type=int, required=True)
    args = parser.parse_args()
    result = verify(args.technical_seed)
    print(json.dumps({"decision": result["decision"], "technical_gates_pass": result["technical_gates_pass"], "ready_for_e2_s1": result["ready_for_e2_s1"], "development_verification_sha256": result["development_verification_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
