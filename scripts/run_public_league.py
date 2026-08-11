"""Run the current submission against extracted public agents at scale."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import importlib.util
import inspect
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBMISSION = ROOT / "submission"
PUBLIC_ROOT = ROOT / "research" / "public_agents"
sys.path.insert(0, str(SUBMISSION))
VENDOR = ROOT / ".vendor" / "kaggle-environments"
sys.path.insert(1, str(VENDOR))

import main as candidate
from rules import is_action_schema
from kaggle_environments import make


PINNED_ENGINE_COMMIT = "a4dce5ae6e2ffe3c1afea8ec4b24b562df74cc07"
ENGINE_DIR = VENDOR / "kaggle_environments" / "envs" / "kaggriculture"
ENGINE_FILES_SHA256 = {
    name: hashlib.sha256((ENGINE_DIR / name).read_bytes()).hexdigest().upper()
    for name in ("kaggriculture.py", "kaggriculture.json")
}


PUBLIC_AGENTS = {
    "kaito_v20": PUBLIC_ROOT / "kaito_v20_weed_recovery" / "extracted" / "main.py",
    "kaito_v21": PUBLIC_ROOT / "kaito_v21_top30" / "extracted" / "main.py",
    "roman_lb950": PUBLIC_ROOT / "roman_lb950" / "extracted" / "main.py",
    "saiteja_3000": PUBLIC_ROOT / "saiteja_mega_ensemble_3000" / "extracted" / "main.py",
    "saiteja_2600": PUBLIC_ROOT / "saiteja_pure_architecture_2600" / "extracted" / "main.py",
}
MEGA_SIBLINGS = ("agent_frontier", "agent_hamburger", "agent_moon", "agent_v14")
DEFAULT_SEEDS = (0, 1, 7, 11, 23, 37, 101, 777)


def percentile(values, pct):
    values = sorted(values)
    if not values:
        return 0.0
    index = (len(values) - 1) * pct
    low, high = int(index), min(len(values) - 1, int(index) + 1)
    fraction = index - low
    return values[low] * (1 - fraction) + values[high] * fraction


def timing_summary(values):
    return {
        "calls": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values, default=0.0),
    }


def inspect_episode(env, seat):
    escapes = 0
    fresh_crop_deaths = 0
    overflow_states = 0
    prior_animals = set()
    tracked_plants = {}
    for row in env.steps:
        obs = row[seat].observation
        farm = obs.farms[seat]
        current_animals = set()
        for y, tiles in enumerate(farm.tiles):
            for x, tile in enumerate(tiles):
                pos = (x, y)
                if isinstance(tile, dict) and tile.get("animal"):
                    current_animals.add(pos)
                if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                    tracked_plants[pos] = tile.get("planted_day", obs.day)
                elif isinstance(tile, dict) and tile.get("kind") == "WEED" and pos in tracked_plants:
                    if obs.day - tracked_plants[pos] <= 1:
                        fresh_crop_deaths += 1
                    tracked_plants.pop(pos, None)
                elif tile is None:
                    tracked_plants.pop(pos, None)
        escapes += len(prior_animals - current_animals)
        prior_animals = current_animals
        if sum(obs.private.shed.values()) > 100:
            overflow_states += 1
    return {
        "escapes": escapes,
        "fresh_crop_deaths": fresh_crop_deaths,
        "overflow_states": overflow_states,
    }


def load_public_agent(name, serial):
    path = PUBLIC_AGENTS[name]
    if not path.exists():
        raise FileNotFoundError(f"missing extracted public agent: {path}")
    if name == "saiteja_3000":
        for module_name in MEGA_SIBLINGS:
            sys.modules.pop(module_name, None)
    module_name = f"_kaggriculture_public_{name}_{serial}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load public agent: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    if not callable(getattr(module, "agent", None)):
        raise TypeError(f"public module does not expose agent(obs): {path}")
    return module.agent


def play(name, seed, candidate_seat, serial):
    candidate._controllers.clear()
    public_agent = load_public_agent(name, serial)
    signature = inspect.signature(public_agent)
    accepts_config = len(signature.parameters) >= 2 or any(
        parameter.kind == inspect.Parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    candidate_times = []
    opponent_times = []
    candidate_malformed = []
    opponent_malformed = []

    def ours(obs):
        started = time.perf_counter()
        action = candidate.agent(obs)
        candidate_times.append((time.perf_counter() - started) * 1000.0)
        hands = len(obs["farms"][obs["player"]]["hands"])
        if not is_action_schema(action, hands):
            candidate_malformed.append(int(obs["step"]))
        return action

    def theirs(obs, config=None):
        started = time.perf_counter()
        action = public_agent(obs, config) if accepts_config else public_agent(obs)
        opponent_times.append((time.perf_counter() - started) * 1000.0)
        hands = len(obs["farms"][obs["player"]]["hands"])
        if not is_action_schema(action, hands):
            opponent_malformed.append(int(obs["step"]))
        return action

    agents = [ours, theirs] if candidate_seat == 0 else [theirs, ours]
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed}, debug=True)
    env.run(agents)
    final = env.steps[-1]
    rewards = [state.reward for state in final]
    statuses = [state.status for state in final]
    opponent_seat = 1 - candidate_seat
    return {
        "opponent": name,
        "seed": seed,
        "candidate_seat": candidate_seat,
        "status": statuses,
        "candidate_reward": rewards[candidate_seat],
        "opponent_reward": rewards[opponent_seat],
        "difference": rewards[candidate_seat] - rewards[opponent_seat],
        "candidate_malformed": candidate_malformed,
        "opponent_malformed": opponent_malformed,
        "candidate_diagnostics": inspect_episode(env, candidate_seat),
        "opponent_diagnostics": inspect_episode(env, opponent_seat),
        "candidate_timing": timing_summary(candidate_times),
        "opponent_timing": timing_summary(opponent_times),
    }


def _play_task(task):
    serial, name, seed, seat = task
    return serial, play(name, seed, seat, serial)


def summarize(games):
    groups = defaultdict(list)
    for game in games:
        groups[game["opponent"]].append(game)
    result = {}
    for name, rows in sorted(groups.items()):
        differences = [row["difference"] for row in rows]
        result[name] = {
            "games": len(rows),
            "wins": sum(value > 0 for value in differences),
            "ties": sum(value == 0 for value in differences),
            "losses": sum(value < 0 for value in differences),
            "mean_difference": statistics.fmean(differences),
            "median_difference": statistics.median(differences),
            "worst_difference": min(differences),
            "all_done": all(row["status"] == ["DONE", "DONE"] for row in rows),
            "candidate_malformed": sum(len(row["candidate_malformed"]) for row in rows),
            "opponent_malformed": sum(len(row["opponent_malformed"]) for row in rows),
            "candidate_escapes": sum(row["candidate_diagnostics"]["escapes"] for row in rows),
            "candidate_fresh_crop_deaths": sum(
                row["candidate_diagnostics"]["fresh_crop_deaths"] for row in rows
            ),
        }
    return result


def source_digest():
    digest = hashlib.sha256()
    for path in sorted(SUBMISSION.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main_run(names, seeds, output, workers=1):
    tasks = []
    for name in names:
        for seed in seeds:
            for seat in (0, 1):
                tasks.append((len(tasks) + 1, name, seed, seat))
    total = len(tasks)
    indexed = {}

    def record(serial, game):
        indexed[serial] = game
        print(
            f"[{len(indexed):03d}/{total:03d}] {game['opponent']} seed={game['seed']} "
            f"seat={game['candidate_seat']} diff={game['difference']:+.0f} status={game['status']}",
            flush=True,
        )

    if workers <= 1:
        for task in tasks:
            record(*_play_task(task))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_play_task, task) for task in tasks]
            for future in as_completed(futures):
                record(*future.result())

    games = [indexed[serial] for serial in sorted(indexed)]
    report = {
        "candidate_source_sha256": source_digest(),
        "official_engine_commit": PINNED_ENGINE_COMMIT,
        "engine_files_sha256": ENGINE_FILES_SHA256,
        "agents": names,
        "seeds": seeds,
        "summary": summarize(games),
        "games": games,
    }
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return report


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", nargs="+", choices=sorted(PUBLIC_AGENTS), default=sorted(PUBLIC_AGENTS))
    parser.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS))
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "public_league_results.json")
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    report = main_run(args.agents, args.seeds, args.output, max(1, args.workers))
    if not all(row["all_done"] for row in report["summary"].values()):
        raise SystemExit(1)
