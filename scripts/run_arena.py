"""Official-engine regression arena and 720-turn latency report."""

import hashlib
import importlib
import json
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submission"))
VENDOR = ROOT / ".vendor" / "kaggle-environments"
sys.path.insert(1, str(VENDOR))
import main
from rules import is_action_schema
from kaggle_environments import make


PINNED_ENGINE_COMMIT = "a4dce5ae6e2ffe3c1afea8ec4b24b562df74cc07"
ENGINE_DIR = VENDOR / "kaggle_environments" / "envs" / "kaggriculture"
ENGINE_FILES_SHA256 = {
    name: hashlib.sha256((ENGINE_DIR / name).read_bytes()).hexdigest().upper()
    for name in ("kaggriculture.py", "kaggriculture.json")
}


def percentile(values, pct):
    values = sorted(values)
    if not values:
        return 0.0
    index = (len(values) - 1) * pct
    low, high = int(index), min(len(values) - 1, int(index) + 1)
    fraction = index - low
    return values[low] * (1 - fraction) + values[high] * fraction


def inspect_episode(env, our_seat):
    escapes = 0
    fresh_crop_deaths = 0
    overflow = 0
    prior_animals = set()
    tracked_plants = {}
    for row in env.steps:
        obs = row[our_seat].observation
        farm = obs.farms[our_seat]
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
            overflow += 1
    return {"escapes": escapes, "fresh_crop_deaths": fresh_crop_deaths, "overflow_states": overflow}


def action_violations(obs, action):
    """Check emitted actions against the engine's aggregate seed/order limits."""
    market_overflow = int(not isinstance(action, dict) or len(action.get("market", [])) > 10)
    if not isinstance(action, dict):
        return {"seed_overcommit": 0, "market_overflow": market_overflow}
    private = obs.get("private", {}) if isinstance(obs, dict) else {}
    seeds = private.get("seeds", {}) if isinstance(private, dict) else {}
    plants = {}
    units = [action.get("farmer", ["PASS"])] + list(action.get("hands", []))
    for unit in units:
        if isinstance(unit, list) and len(unit) >= 2 and unit[0] == "PLANT":
            plants[unit[1]] = plants.get(unit[1], 0) + 1
    overcommitted = sum(
        count - int(seeds.get(crop, 0))
        for crop, count in plants.items()
        if count > int(seeds.get(crop, 0))
    )
    return {"seed_overcommit": overcommitted, "market_overflow": market_overflow}


def play(opponent, seed, seat, capture_actions=False):
    main._controllers.clear()
    timings = []
    actions = []
    malformed = []
    seed_overcommit = []
    market_overflow = []
    timeout_calls = []

    def ours(obs):
        started = time.perf_counter()
        action = main.agent(obs)
        elapsed = (time.perf_counter() - started) * 1000.0
        timings.append(elapsed)
        if not is_action_schema(action, len(obs["farms"][obs["player"]]["hands"])):
            malformed.append(obs["step"])
        violations = action_violations(obs, action)
        if violations["seed_overcommit"]:
            seed_overcommit.append({"step": int(obs["step"]), "count": violations["seed_overcommit"]})
        if violations["market_overflow"]:
            market_overflow.append(int(obs["step"]))
        if elapsed >= 1000.0:
            timeout_calls.append(int(obs["step"]))
        if capture_actions:
            actions.append(action)
        return action

    agents = [ours, opponent] if seat == 0 else [opponent, ours]
    env = make("kaggriculture", configuration={"episodeSteps": 720, "seed": seed}, debug=True)
    env.run(agents)
    final = env.steps[-1]
    status = [s.status for s in final]
    rewards = [s.reward for s in final]
    diagnostics = inspect_episode(env, seat)
    digest = hashlib.sha256(json.dumps(actions, sort_keys=True, separators=(",", ":")).encode()).hexdigest() if capture_actions else None
    return {
        "opponent": opponent if isinstance(opponent, str) else "self",
        "seed": seed,
        "seat": seat,
        "status": status,
        "rewards": rewards,
        "our_reward": rewards[seat],
        "opponent_reward": rewards[1 - seat],
        "win": rewards[seat] > rewards[1 - seat],
        "malformed": malformed,
        "seed_overcommit": seed_overcommit,
        "market_overflow": market_overflow,
        "timeout_calls": timeout_calls,
        "diagnostics": diagnostics,
        "timings_ms": timings,
        "action_digest": digest,
    }


def compact(game):
    out = dict(game)
    out.pop("timings_ms", None)
    return out


def main_run():
    games = []
    # Required full self-play validation.
    games.append(play(main.agent, 101, 0, capture_actions=True))
    performance_720 = list(games[0]["timings_ms"])
    for opponent in ("starter", "random"):
        for seed in (11, 23, 37):
            for seat in (0, 1):
                games.append(play(opponent, seed, seat))

    deterministic_a = play(main.agent, 777, 0, capture_actions=True)
    deterministic_b = play(main.agent, 777, 0, capture_actions=True)
    deterministic = (
        deterministic_a["rewards"] == deterministic_b["rewards"]
        and deterministic_a["action_digest"] == deterministic_b["action_digest"]
    )
    all_times = [value for game in games for value in game["timings_ms"]]
    perf = {
        "calls": len(all_times),
        "p50_ms": percentile(all_times, .50),
        "p95_ms": percentile(all_times, .95),
        "p99_ms": percentile(all_times, .99),
        "max_ms": max(all_times),
    }
    perf720 = {
        "calls": len(performance_720),
        "p50_ms": percentile(performance_720, .50),
        "p95_ms": percentile(performance_720, .95),
        "p99_ms": percentile(performance_720, .99),
        "max_ms": max(performance_720),
    }
    checked_games = games + [deterministic_a, deterministic_b]
    report = {
        "official_engine_commit": PINNED_ENGINE_COMMIT,
        "engine_files_sha256": ENGINE_FILES_SHA256,
        "all_done": all(game["status"] == ["DONE", "DONE"] for game in checked_games),
        "malformed_actions": sum(len(game["malformed"]) for game in checked_games),
        "timeout_calls": sum(len(game["timeout_calls"]) for game in checked_games),
        "timeouts": sum(
            state != "DONE" for game in checked_games for state in game["status"]
        ),
        "escapes": sum(game["diagnostics"]["escapes"] for game in checked_games),
        "fresh_crop_deaths": sum(game["diagnostics"]["fresh_crop_deaths"] for game in checked_games),
        "shed_overflow_states": sum(game["diagnostics"]["overflow_states"] for game in checked_games),
        "seed_overcommit": sum(len(game["seed_overcommit"]) for game in checked_games),
        "market_orders_over_10": sum(len(game["market_overflow"]) for game in checked_games),
        "deterministic": deterministic,
        "performance_all": perf,
        "performance_720": perf720,
        "games": [compact(game) for game in games],
        "determinism_runs": [compact(deterministic_a), compact(deterministic_b)],
    }
    destination = ROOT / "reports" / "arena_results.json"
    destination.parent.mkdir(exist_ok=True)
    acceptance = (
        report["all_done"] and report["deterministic"]
        and not report["malformed_actions"] and not report["timeouts"]
        and not report["timeout_calls"] and not report["escapes"]
        and not report["fresh_crop_deaths"] and not report["shed_overflow_states"]
        and not report["seed_overcommit"] and not report["market_orders_over_10"]
        and report["performance_720"]["p95_ms"] < 150.0
        and report["performance_720"]["max_ms"] < 750.0
    )
    report["acceptance_passed"] = acceptance
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not acceptance:
        raise SystemExit(1)


if __name__ == "__main__":
    main_run()
