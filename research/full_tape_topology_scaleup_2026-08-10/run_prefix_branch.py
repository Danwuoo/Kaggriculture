"""Fresh paired test for the verified 161-turn complete-tape branch."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parent
CORRECTION = ROOT / "research" / "exact_backbone_correction_2026-08-10"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(CORRECTION))
sys.path.insert(0, str(ROOT / ".vendor" / "kaggle-environments"))

from kaggle_environments import make
from run_exact_artifact_panel import CONFIG, PUBLIC, action_issues, agent_observation, percentile, safety_diagnostics
from scripts.replay_engine_versions import CURRENT_ENGINE_NORMALIZED_SHA256, CURRENT_JSON_SHA256, VERSION_COMMITS, patch_registered_engine_current, verify_pinned_source


ARMS = {
    "v25_exact": CORRECTION / "artifacts" / "v25_meta_reset" / "main.py",
    "zero_exact": CORRECTION / "artifacts" / "zero_to_top_meta" / "main.py",
    "v25_prefix_zero_branch": LANE / "branch_v25_to_zero_agent.py",
}
SEEDS = (732023, 732031)
MEGA_SIBLINGS = ("agent_frontier", "agent_hamburger", "agent_moon", "agent_v14")


def load_module(path: Path, name: str, clear_mega: bool = False):
    if clear_mega:
        for sibling in MEGA_SIBLINGS:
            sys.modules.pop(sibling, None)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    if not callable(getattr(module, "agent", None)):
        raise TypeError(f"no agent in {path}")
    return module


def invoke(policy: Callable, observation: dict[str, Any], config: dict[str, Any]) -> Any:
    return policy(observation, config) if len(inspect.signature(policy).parameters) >= 2 else policy(observation)


def compatibility_label(observation: dict[str, Any]) -> str:
    """Own private plus public state; never reads an opponent's private view."""
    public = {
        "day": observation.get("day"), "hour": observation.get("hour"),
        "farms": observation.get("farms"), "market": observation.get("market"), "town": observation.get("town"),
    }
    payload = {"public": public, "own_private": observation.get("private", {})}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def play(arm: str, opponent_name: str, seed: int, seat: int) -> dict[str, Any]:
    patch_registered_engine_current()
    config = {**CONFIG, "seed": seed}
    candidate_module = load_module(ARMS[arm], f"_prefix_{arm}_{opponent_name}_{seed}_{seat}")
    opponent_module = load_module(PUBLIC[opponent_name], f"_prefix_public_{opponent_name}_{arm}_{seed}_{seat}", clear_mega=opponent_name == "saiteja_3000")
    env = make("kaggriculture", configuration=config, debug=True)
    env.reset(2)
    timings: list[float] = []
    digest = hashlib.sha256()
    issues = {"malformed": 0, "seed_overcommit": 0, "market_overflow": 0}
    branch_label = None
    exception = None
    while not env.done:
        actions = []
        for player in (0, 1):
            observation = agent_observation(env, player)
            if player == seat:
                if int(observation["step"]) == 161:
                    branch_label = compatibility_label(observation)
                try:
                    started = time.perf_counter()
                    action = invoke(candidate_module.agent, observation, config)
                    timings.append((time.perf_counter() - started) * 1000.0)
                    for key, value in action_issues(observation, action).items():
                        issues[key] += value
                    digest.update(json.dumps(action, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                except Exception as error:
                    exception = f"{type(error).__name__}: {error}"
                    break
            else:
                action = invoke(opponent_module.agent, observation, config)
            actions.append(action)
        if exception is not None:
            break
        env.step(actions)
    if env.done:
        final = env.steps[-1]
        own, other = final[seat], final[1 - seat]
        reward, opponent_reward = own.reward, other.reward
        statuses = [state.status for state in final]
    else:
        reward = opponent_reward = None
        statuses = [state.status for state in env.state]
    stats = candidate_module.branch_stats(seat) if hasattr(candidate_module, "branch_stats") else None
    return {
        "arm": arm, "opponent": opponent_name, "seed": seed, "seat": seat,
        "statuses": statuses, "candidate_reward": reward, "opponent_reward": opponent_reward,
        "margin": None if reward is None or opponent_reward is None else reward - opponent_reward,
        "diagnostics": safety_diagnostics(env.steps, seat), "action_issues": issues,
        "timeout_calls": sum(value >= 1000.0 for value in timings), "candidate_timings_ms": timings,
        "candidate_action_digest": digest.hexdigest(), "branch_state_label_at_161": branch_label,
        "branch_stats": stats, "exception": exception,
    }


def safe(row: dict[str, Any]) -> bool:
    return row["exception"] is None and row["statuses"] == ["DONE", "DONE"] and all(value == 0 for value in row["diagnostics"].values()) and all(value == 0 for value in row["action_issues"].values()) and row["timeout_calls"] == 0


def run(output: Path) -> dict[str, Any]:
    pairs = []
    for opponent in PUBLIC:
        for seed in SEEDS:
            for seat in (0, 1):
                baseline = play("v25_exact", opponent, seed, seat)
                zero_reference = play("zero_exact", opponent, seed, seat)
                branch = play("v25_prefix_zero_branch", opponent, seed, seat)
                pairs.append({
                    "opponent": opponent, "seed": seed, "seat": seat,
                    "baseline": baseline, "zero_reference": zero_reference, "candidate": branch,
                    "paired_margin_delta": None if branch["margin"] is None or baseline["margin"] is None else branch["margin"] - baseline["margin"],
                    "branch_state_matches_zero_reference": branch["branch_state_label_at_161"] == zero_reference["branch_state_label_at_161"],
                })
    duplicate_a = play("v25_prefix_zero_branch", "kaito_v21", SEEDS[0], 0)
    duplicate_b = play("v25_prefix_zero_branch", "kaito_v21", SEEDS[0], 0)
    rows = [pair["candidate"] for pair in pairs]
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_family[pair["opponent"]].append(pair)
    family = {
        name: {"pairs": len(items), "positive_deltas": sum(item["paired_margin_delta"] is not None and item["paired_margin_delta"] > 0 for item in items), "mean_paired_margin_delta": statistics.fmean(item["paired_margin_delta"] for item in items if item["paired_margin_delta"] is not None)}
        for name, items in by_family.items()
    }
    timings = [value for row in rows for value in row["candidate_timings_ms"]]
    positive = sum(pair["paired_margin_delta"] is not None and pair["paired_margin_delta"] > 0 for pair in pairs)
    branch_runtime_valid = all(row["branch_stats"] and row["branch_stats"]["checked"] == 161 and not row["branch_stats"]["vetoed"] and row["branch_stats"]["branched"] for row in rows)
    compatible = all(pair["branch_state_matches_zero_reference"] for pair in pairs)
    safety = all(safe(row) for row in rows)
    deterministic = duplicate_a["candidate_action_digest"] == duplicate_b["candidate_action_digest"] and duplicate_a["candidate_reward"] == duplicate_b["candidate_reward"] and duplicate_a["opponent_reward"] == duplicate_b["opponent_reward"]
    efficacy = branch_runtime_valid and compatible and safety and deterministic and positive >= 8 and all(row["mean_paired_margin_delta"] > 0 for row in family.values())
    report = {
        "engine": {"commit": VERSION_COMMITS["1.32.6"], "python_normalized_sha256": CURRENT_ENGINE_NORMALIZED_SHA256, "json_sha256": CURRENT_JSON_SHA256, "configuration": CONFIG, "pinned_base_read_only": verify_pinned_source()},
        "protocol": {"candidate": "exact v25 through step 160; shadow-verified exact zero-to-top prefix; exact zero-to-top from step 161", "common_prefix_full_actions": 161, "seeds": list(SEEDS), "seats": [0, 1], "opponent_families": list(PUBLIC), "freshness_check": "732023 and 732031 had no earlier literal occurrence under research/, reports/, scripts/ before this lane.", "promotion_rule": "runtime prefix equality + state label equality + zero safety faults + deterministic + >=8/12 positive delta and positive family means"},
        "branch_runtime_valid": branch_runtime_valid, "branch_state_compatible": compatible, "safety_passed": safety, "deterministic": deterministic, "positive_paired_deltas": positive, "family_summary": family, "efficacy_passed": efficacy,
        "performance": {"calls": len(timings), "p50": percentile(timings, .50), "p95": percentile(timings, .95), "p99": percentile(timings, .99), "max": max(timings, default=0.0)},
        "pairs": pairs, "determinism": {"first": duplicate_a, "second": duplicate_b},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.output)
    print(json.dumps({key: report[key] for key in ("branch_runtime_valid", "branch_state_compatible", "safety_passed", "deterministic", "positive_paired_deltas", "family_summary", "efficacy_passed", "performance")}, indent=2))


if __name__ == "__main__":
    main()
