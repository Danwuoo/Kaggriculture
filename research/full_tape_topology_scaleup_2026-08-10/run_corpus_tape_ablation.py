"""Fresh paired evaluation of the corpus-supported complete tape candidate."""

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


ARMS = {"v25_exact": CORRECTION / "artifacts" / "v25_meta_reset" / "main.py", "corpus_supported_tape": LANE / "corpus_supported_tape_agent.py"}
SEEDS = (732041, 732059)
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
    return module


def invoke(policy: Callable, observation: dict[str, Any], config: dict[str, Any]) -> Any:
    return policy(observation, config) if len(inspect.signature(policy).parameters) >= 2 else policy(observation)


def play(arm: str, opponent_name: str, seed: int, seat: int) -> dict[str, Any]:
    patch_registered_engine_current()
    config = {**CONFIG, "seed": seed}
    candidate = load_module(ARMS[arm], f"_corpus_{arm}_{opponent_name}_{seed}_{seat}")
    opponent = load_module(PUBLIC[opponent_name], f"_corpus_public_{opponent_name}_{arm}_{seed}_{seat}", clear_mega=opponent_name == "saiteja_3000")
    env = make("kaggriculture", configuration=config, debug=True)
    env.reset(2)
    timings: list[float] = []
    digest = hashlib.sha256()
    issues = {"malformed": 0, "seed_overcommit": 0, "market_overflow": 0}
    exception = None
    while not env.done:
        actions = []
        for player in (0, 1):
            observation = agent_observation(env, player)
            if player == seat:
                try:
                    started = time.perf_counter()
                    action = invoke(candidate.agent, observation, config)
                    timings.append((time.perf_counter() - started) * 1000.0)
                    for key, value in action_issues(observation, action).items():
                        issues[key] += value
                    digest.update(json.dumps(action, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                except Exception as error:
                    exception = f"{type(error).__name__}: {error}"
                    break
            else:
                action = invoke(opponent.agent, observation, config)
            actions.append(action)
        if exception is not None:
            break
        env.step(actions)
    if env.done:
        final = env.steps[-1]
        own, other = final[seat], final[1 - seat]
        reward, opponent_reward, statuses = own.reward, other.reward, [state.status for state in final]
    else:
        reward = opponent_reward = None
        statuses = [state.status for state in env.state]
    return {"arm": arm, "opponent": opponent_name, "seed": seed, "seat": seat, "statuses": statuses, "candidate_reward": reward, "opponent_reward": opponent_reward, "margin": None if reward is None or opponent_reward is None else reward - opponent_reward, "diagnostics": safety_diagnostics(env.steps, seat), "action_issues": issues, "timeout_calls": sum(value >= 1000.0 for value in timings), "candidate_timings_ms": timings, "candidate_action_digest": digest.hexdigest(), "tape_stats": candidate.stats(seat) if hasattr(candidate, "stats") else None, "exception": exception}


def safe(row: dict[str, Any]) -> bool:
    return row["exception"] is None and row["statuses"] == ["DONE", "DONE"] and all(value == 0 for value in row["diagnostics"].values()) and all(value == 0 for value in row["action_issues"].values()) and row["timeout_calls"] == 0


def run(output: Path) -> dict[str, Any]:
    pairs = []
    for opponent in PUBLIC:
        for seed in SEEDS:
            for seat in (0, 1):
                baseline = play("v25_exact", opponent, seed, seat)
                candidate = play("corpus_supported_tape", opponent, seed, seat)
                pairs.append({"opponent": opponent, "seed": seed, "seat": seat, "baseline": baseline, "candidate": candidate, "paired_margin_delta": None if candidate["margin"] is None or baseline["margin"] is None else candidate["margin"] - baseline["margin"]})
    first, second = play("corpus_supported_tape", "kaito_v21", SEEDS[0], 0), play("corpus_supported_tape", "kaito_v21", SEEDS[0], 0)
    rows = [pair["candidate"] for pair in pairs]
    family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        family[pair["opponent"]].append(pair)
    family_summary = {name: {"pairs": len(items), "positive_deltas": sum(item["paired_margin_delta"] is not None and item["paired_margin_delta"] > 0 for item in items), "mean_paired_margin_delta": statistics.fmean(item["paired_margin_delta"] for item in items if item["paired_margin_delta"] is not None)} for name, items in family.items()}
    timings = [value for row in rows for value in row["candidate_timings_ms"]]
    positive = sum(item["paired_margin_delta"] is not None and item["paired_margin_delta"] > 0 for item in pairs)
    deterministic = first["candidate_action_digest"] == second["candidate_action_digest"] and first["candidate_reward"] == second["candidate_reward"] and first["opponent_reward"] == second["opponent_reward"]
    safety = all(safe(row) for row in rows)
    efficacy = safety and deterministic and positive >= 8 and all(item["mean_paired_margin_delta"] > 0 for item in family_summary.values())
    report = {"engine": {"commit": VERSION_COMMITS["1.32.6"], "python_normalized_sha256": CURRENT_ENGINE_NORMALIZED_SHA256, "json_sha256": CURRENT_JSON_SHA256, "configuration": CONFIG, "pinned_base_read_only": verify_pinned_source()}, "candidate_support": {"full_tape_sha256": "36d088a964b359f64ef0f4030fe8f6d6fbb1a0544dbc8706b9c5dab9e2d15fc2", "representative_ranks": [82, 96], "distinct_team_ids": [16656316, 16655789], "distinct_submission_ids": [55390310, 55384143], "selection_boundary": "Current live leaderboard snapshot/corpus support; no notebook-team identity claim."}, "protocol": {"comparison": "exact v25 versus complete 719-turn corpus tape with hand-count-only schema projection; no generic planner", "seeds": list(SEEDS), "seats": [0, 1], "opponent_families": list(PUBLIC), "freshness_check": "732041 and 732059 had no prior literal occurrence under research/, reports/, scripts/ before this ablation source was created.", "promotion_rule": "zero safety faults + deterministic + >=8/12 positive paired deltas and positive family mean"}, "safety_passed": safety, "deterministic": deterministic, "positive_paired_deltas": positive, "family_summary": family_summary, "efficacy_passed": efficacy, "performance": {"calls": len(timings), "p50": percentile(timings, .50), "p95": percentile(timings, .95), "p99": percentile(timings, .99), "max": max(timings, default=0.0)}, "pairs": pairs, "determinism": {"first": first, "second": second}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.output)
    print(json.dumps({key: report[key] for key in ("safety_passed", "deterministic", "positive_paired_deltas", "family_summary", "efficacy_passed", "performance")}, indent=2))


if __name__ == "__main__":
    main()
