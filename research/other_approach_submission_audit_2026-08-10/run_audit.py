"""Isolated current-engine audit for scripts/other appoach/main.py."""

from __future__ import annotations

import ast
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
LANE = ROOT / "research" / "other_approach_submission_audit_2026-08-10"
REPORT_DIR = ROOT / "reports" / "other_approach_submission_audit_2026-08-10"
CANDIDATE = ROOT / "scripts" / "other appoach" / "main.py"
ADAPTIVE = (
    ROOT
    / "research"
    / "exact_backbone_correction_2026-08-10"
    / "artifacts"
    / "adaptive_farming"
    / "main.py"
)
PUBLIC = {
    "kaito_v21": ROOT / "research" / "public_agents" / "kaito_v21_top30" / "extracted" / "main.py",
    "saiteja_3000": ROOT / "research" / "public_agents" / "saiteja_mega_ensemble_3000" / "extracted" / "main.py",
    "roman_lb950": ROOT / "research" / "public_agents" / "roman_lb950" / "extracted" / "main.py",
}
MEGA_SIBLINGS = ("agent_frontier", "agent_hamburger", "agent_moon", "agent_v14")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".vendor" / "kaggle-environments"))

from kaggle_environments import make  # noqa: E402
from scripts.replay_engine_versions import (  # noqa: E402
    CURRENT_ENGINE_NORMALIZED_SHA256,
    CURRENT_JSON_SHA256,
    VERSION_COMMITS,
    patch_registered_engine_current,
    verify_pinned_source,
)


CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "townCenterSellInterval": 24,
    "townShopSellInterval": 4,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}
ARENA_SEEDS = (11, 23, 37)
PUBLIC_SEED = 904291


def load_module(path: Path, name: str, *, clear_mega: bool = False) -> Any:
    if clear_mega:
        for module_name in MEGA_SIBLINGS:
            sys.modules.pop(module_name, None)
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


def load_policy(path: Path, name: str, *, clear_mega: bool = False) -> Callable:
    policy = getattr(load_module(path, name, clear_mega=clear_mega), "agent", None)
    if not callable(policy):
        raise TypeError(f"no callable agent in {path}")
    return policy


def invoke(policy: Callable, observation: dict[str, Any], config: dict[str, Any]) -> Any:
    return policy(observation, config) if len(inspect.signature(policy).parameters) >= 2 else policy(observation)


def observation(env: Any, player: int) -> dict[str, Any]:
    obs = dict(env.state[player].observation)
    obs["step"] = int(env.state[0].observation["step"])
    return obs


def action_issues(obs: dict[str, Any], action: Any) -> dict[str, int]:
    if not isinstance(action, dict):
        return {"malformed": 1, "seed_overcommit": 0, "market_overflow": 0}
    farm = obs["farms"][obs["player"]]
    malformed = int(
        not isinstance(action.get("farmer"), list)
        or not isinstance(action.get("hands"), list)
        or not isinstance(action.get("market"), list)
        or len(action.get("hands", [])) != len(farm["hands"])
    )
    plants: dict[str, int] = defaultdict(int)
    for unit in [action.get("farmer", ["PASS"]), *(action.get("hands", []) or [])]:
        if isinstance(unit, list) and len(unit) >= 2 and unit[0] == "PLANT":
            plants[str(unit[1])] += 1
    seeds = (obs.get("private", {}) or {}).get("seeds", {}) or {}
    return {
        "malformed": malformed,
        "seed_overcommit": sum(max(0, count - int(seeds.get(crop, 0) or 0)) for crop, count in plants.items()),
        "market_overflow": int(isinstance(action.get("market"), list) and len(action["market"]) > 10),
    }


def safety(states: list[Any], seat: int) -> dict[str, int]:
    escapes = fresh_deaths = overflow_states = 0
    previous_animals: set[tuple[int, int]] = set()
    planted: dict[tuple[int, int], int] = {}
    for row in states:
        obs = row[seat].observation
        farm = obs["farms"][seat]
        animals: set[tuple[int, int]] = set()
        for y, tiles in enumerate(farm["tiles"]):
            for x, tile in enumerate(tiles):
                position = (x, y)
                if isinstance(tile, dict) and tile.get("animal"):
                    animals.add(position)
                if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                    planted[position] = int(tile.get("planted_day", obs["day"]))
                elif isinstance(tile, dict) and tile.get("kind") == "WEED" and position in planted:
                    fresh_deaths += int(int(obs["day"]) - planted[position] <= 1)
                    planted.pop(position, None)
                elif tile is None:
                    planted.pop(position, None)
        escapes += len(previous_animals - animals)
        previous_animals = animals
        overflow_states += int(sum(int(value or 0) for value in obs["private"]["shed"].values()) > 100)
    return {
        "animal_escapes": escapes,
        "fresh_crop_deaths": fresh_deaths,
        "shed_overflow_states": overflow_states,
    }


def fresh_death_events(states: list[Any], seat: int) -> list[dict[str, Any]]:
    planted: dict[tuple[int, int], dict[str, int]] = {}
    events: list[dict[str, Any]] = []
    for row in states:
        obs = row[seat].observation
        step = int(row[0].observation["step"])
        farm = obs["farms"][seat]
        for y, tiles in enumerate(farm["tiles"]):
            for x, tile in enumerate(tiles):
                position = (x, y)
                if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                    planted[position] = {
                        "planted_day": int(tile.get("planted_day", obs["day"])),
                        "last_seen_step": step,
                    }
                elif isinstance(tile, dict) and tile.get("kind") == "WEED" and position in planted:
                    prior = planted.pop(position)
                    if int(obs["day"]) - prior["planted_day"] <= 1:
                        events.append({
                            "step": step,
                            "day": int(obs["day"]),
                            "position": [x, y],
                            **prior,
                        })
                elif tile is None:
                    planted.pop(position, None)
    return events


def total_items(private: dict[str, Any]) -> int:
    return sum(int(value or 0) for value in private.get("shed", {}).values()) + sum(
        int(value or 0) for inventory in private.get("inventories", []) for value in inventory.values()
    )


def install_overflow_probe(engine: Any):
    counts = {"drop_overflow_units": 0, "eod_overflow_units": 0}
    context = {"target_private_id": None}
    original_apply = engine._apply_unit_action
    original_eod = engine._drop_inventories_to_shed

    def apply_probe(farm, private, idx, action, *args, **kwargs):
        before = total_items(private)
        result = original_apply(farm, private, idx, action, *args, **kwargs)
        if id(private) == context["target_private_id"] and isinstance(action, list) and action and action[0] == "DROP":
            counts["drop_overflow_units"] += max(0, before - total_items(private))
        return result

    def eod_probe(private, capacity):
        before = total_items(private)
        result = original_eod(private, capacity)
        if id(private) == context["target_private_id"]:
            counts["eod_overflow_units"] += max(0, before - total_items(private))
        return result

    engine._apply_unit_action = apply_probe
    engine._drop_inventories_to_shed = eod_probe

    def restore() -> None:
        engine._apply_unit_action = original_apply
        engine._drop_inventories_to_shed = original_eod

    def set_target(private: Any) -> None:
        context["target_private_id"] = id(private)

    return counts, restore, set_target


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    low, high = int(index), min(len(ordered) - 1, int(index) + 1)
    return ordered[low] * (high - index) + ordered[high] * (index - low)


def opponent_policy(env: Any, name: str, serial: str) -> Callable:
    if name in ("starter", "random"):
        return env.agents[name]
    if name == "candidate_self":
        return load_policy(CANDIDATE, f"_other_self_{serial}")
    return load_policy(PUBLIC[name], f"_public_{name}_{serial}", clear_mega=name == "saiteja_3000")


def play(
    policy_path: Path,
    policy_label: str,
    opponent_name: str,
    seed: int,
    seat: int,
    serial: str,
    *,
    capture_trace: bool = False,
) -> dict[str, Any]:
    engine = patch_registered_engine_current()
    overflow, restore, set_target = install_overflow_probe(engine)
    config = {**CONFIG, "seed": seed}
    candidate = load_policy(policy_path, f"_{policy_label}_{serial}")
    env = make("kaggriculture", configuration=config, debug=True)
    env.reset(2)
    opponent = opponent_policy(env, opponent_name, serial)
    set_target(env.state[seat].observation.private)
    timings: list[float] = []
    digest = hashlib.sha256()
    issues = {"malformed": 0, "seed_overcommit": 0, "market_overflow": 0}
    issue_events: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    exception = opponent_exception = None
    calls = 0
    try:
        while not env.done:
            actions = []
            for player in (0, 1):
                obs = observation(env, player)
                try:
                    if player == seat:
                        started = time.perf_counter()
                        action = invoke(candidate, obs, config)
                        timings.append((time.perf_counter() - started) * 1000.0)
                        calls += 1
                        found = action_issues(obs, action)
                        for key, value in found.items():
                            issues[key] += value
                        if any(found.values()):
                            issue_events.append({
                                "step": int(obs["step"]),
                                "found": found,
                                "seeds": dict((obs.get("private", {}) or {}).get("seeds", {}) or {}),
                                "farmer": action.get("farmer") if isinstance(action, dict) else None,
                                "hands": action.get("hands") if isinstance(action, dict) else None,
                                "market": action.get("market") if isinstance(action, dict) else None,
                            })
                        digest.update(json.dumps(action, sort_keys=True, separators=(",", ":")).encode())
                        if capture_trace:
                            own_farm = obs["farms"][seat]
                            trace.append({
                                "step": int(obs["step"]),
                                "day": int(obs["day"]),
                                "positions": [own_farm["farmer"], *list(own_farm.get("hands", []) or [])],
                                "action": action,
                                "seeds": dict((obs.get("private", {}) or {}).get("seeds", {}) or {}),
                                "tile_0_9": own_farm["tiles"][9][0],
                            })
                    else:
                        action = invoke(opponent, obs, config)
                except Exception as error:
                    message = f"{type(error).__name__}: {error}"
                    if player == seat:
                        exception = message
                    else:
                        opponent_exception = message
                    break
                actions.append(action)
            if exception or opponent_exception:
                break
            env.step(actions)
    finally:
        restore()
    if env.done:
        final = env.steps[-1]
        statuses = [state.status for state in final]
        reward, other_reward = final[seat].reward, final[1 - seat].reward
    else:
        statuses = [state.status for state in env.state]
        reward = other_reward = None
    return {
        "policy": policy_label,
        "opponent": opponent_name,
        "seed": seed,
        "seat": seat,
        "statuses": statuses,
        "states": len(env.steps),
        "calls": calls,
        "candidate_reward": reward,
        "opponent_reward": other_reward,
        "margin": None if reward is None or other_reward is None else reward - other_reward,
        "diagnostics": {**safety(env.steps, seat), **overflow},
        "fresh_death_events": fresh_death_events(env.steps, seat),
        "action_issues": issues,
        "action_issue_events": issue_events,
        "timeout_calls": sum(value >= 1000.0 for value in timings),
        "latency_ms": {
            "calls": len(timings),
            "p50": percentile(timings, 0.50),
            "p95": percentile(timings, 0.95),
            "p99": percentile(timings, 0.99),
            "max": max(timings, default=0.0),
        },
        "timings_ms": timings,
        "action_digest": digest.hexdigest(),
        "trace": trace if capture_trace else None,
        "exception": exception,
        "opponent_exception": opponent_exception,
    }


def valid(row: dict[str, Any]) -> bool:
    return (
        row["statuses"] == ["DONE", "DONE"]
        and row["states"] == 720
        and row["calls"] == 719
        and row["exception"] is None
        and row["opponent_exception"] is None
        and all(value == 0 for value in row["diagnostics"].values())
        and all(value == 0 for value in row["action_issues"].values())
        and row["timeout_calls"] == 0
    )


def static_audit() -> dict[str, Any]:
    source = CANDIDATE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    module = load_module(CANDIDATE, "_other_static")
    tape = module._LEGACY_ACTIONS
    encoded = json.dumps(tape, sort_keys=True, separators=(",", ":")).encode()
    forbidden_calls = {
        name: [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
        ]
        for name in ("open", "exec", "eval", "compile", "__import__")
    }
    return {
        "path": str(CANDIDATE),
        "bytes": CANDIDATE.stat().st_size,
        "sha256": hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(),
        "imports": sorted(set(imports)),
        "forbidden_calls": forbidden_calls,
        "agent_parameters": list(inspect.signature(module.agent).parameters),
        "tape_steps": len(tape),
        "tape_sha256": hashlib.sha256(encoded).hexdigest(),
        "rebalance_is_legacy_object": module._REBALANCE_ACTIONS is module._LEGACY_ACTIONS,
        "first_action": tape[0],
        "last_action": tape[-1],
    }


def compact(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop("timings_ms", None)
    return result


def main() -> None:
    static = static_audit()
    rows: list[dict[str, Any]] = []
    rows.append(play(CANDIDATE, "candidate", "candidate_self", 101, 0, "self_101_0"))
    for opponent in ("starter", "random"):
        for seed in ARENA_SEEDS:
            for seat in (0, 1):
                rows.append(play(CANDIDATE, "candidate", opponent, seed, seat, f"arena_{opponent}_{seed}_{seat}"))

    public_rows: list[dict[str, Any]] = []
    adaptive_rows: list[dict[str, Any]] = []
    for opponent in PUBLIC:
        for seat in (0, 1):
            public_rows.append(play(CANDIDATE, "candidate", opponent, PUBLIC_SEED, seat, f"public_{opponent}_{seat}"))
            adaptive_rows.append(play(ADAPTIVE, "adaptive", opponent, PUBLIC_SEED, seat, f"adaptive_{opponent}_{seat}"))

    det_a = play(CANDIDATE, "candidate", "kaito_v21", 777, 0, "det_a")
    det_b = play(CANDIDATE, "candidate", "kaito_v21", 777, 0, "det_b")
    deterministic = (
        det_a["action_digest"] == det_b["action_digest"]
        and det_a["candidate_reward"] == det_b["candidate_reward"]
        and det_a["opponent_reward"] == det_b["opponent_reward"]
        and det_a["statuses"] == det_b["statuses"]
    )

    candidate_rows = rows + public_rows + [det_a, det_b]
    all_timings = [value for row in candidate_rows for value in row["timings_ms"]]
    performance_game = rows[0]["timings_ms"]
    family = {}
    for opponent in PUBLIC:
        candidate_family = [row for row in public_rows if row["opponent"] == opponent]
        adaptive_family = [row for row in adaptive_rows if row["opponent"] == opponent]
        deltas = [
            candidate_family[seat]["margin"] - adaptive_family[seat]["margin"]
            for seat in range(2)
        ]
        family[opponent] = {
            "candidate_wins": sum(row["margin"] is not None and row["margin"] > 0 for row in candidate_family),
            "adaptive_wins": sum(row["margin"] is not None and row["margin"] > 0 for row in adaptive_family),
            "candidate_margins": [row["margin"] for row in candidate_family],
            "adaptive_margins": [row["margin"] for row in adaptive_family],
            "candidate_minus_adaptive_margin": deltas,
            "paired_mean_delta": statistics.fmean(deltas),
        }

    acceptance = (
        all(valid(row) for row in candidate_rows)
        and deterministic
        and percentile(performance_game, 0.95) < 150.0
        and max(performance_game, default=0.0) < 750.0
        and static["tape_steps"] == 719
        and static["agent_parameters"] == ["obs", "configuration"]
        and all(not lines for lines in static["forbidden_calls"].values())
    )
    report = {
        "decision": {
            "submission_gate_passed": acceptance,
            "reason": "All current-engine completion, schema, safety, overflow, determinism, and latency gates passed."
            if acceptance
            else "At least one current-engine completion, schema, safety, overflow, determinism, or latency gate failed.",
        },
        "static_audit": static,
        "engine": {
            "commit": VERSION_COMMITS["1.32.6"],
            "python_normalized_sha256": CURRENT_ENGINE_NORMALIZED_SHA256,
            "json_sha256": CURRENT_JSON_SHA256,
            "configuration": CONFIG,
            "pinned_base_read_only": verify_pinned_source(),
        },
        "protocol": {
            "candidate_games": len(candidate_rows),
            "adaptive_reference_games": len(adaptive_rows),
            "arena": {"opponents": ["starter", "random"], "seeds": list(ARENA_SEEDS), "seats": [0, 1]},
            "public": {"opponents": list(PUBLIC), "fresh_seed": PUBLIC_SEED, "seats": [0, 1]},
            "determinism": {"opponent": "kaito_v21", "seed": 777, "seat": 0, "repetitions": 2},
        },
        "acceptance": {
            "all_candidate_games_valid": all(valid(row) for row in candidate_rows),
            "deterministic": deterministic,
            "latency_all_ms": {
                "calls": len(all_timings),
                "p50": percentile(all_timings, 0.50),
                "p95": percentile(all_timings, 0.95),
                "p99": percentile(all_timings, 0.99),
                "max": max(all_timings, default=0.0),
            },
            "latency_full_episode_ms": {
                "calls": len(performance_game),
                "p50": percentile(performance_game, 0.50),
                "p95": percentile(performance_game, 0.95),
                "p99": percentile(performance_game, 0.99),
                "max": max(performance_game, default=0.0),
            },
            "diagnostic_totals": {
                key: sum(row["diagnostics"][key] for row in candidate_rows)
                for key in candidate_rows[0]["diagnostics"]
            },
            "action_issue_totals": {
                key: sum(row["action_issues"][key] for row in candidate_rows)
                for key in candidate_rows[0]["action_issues"]
            },
            "timeout_calls": sum(row["timeout_calls"] for row in candidate_rows),
        },
        "public_comparison": {
            "candidate_wins_draws_losses": [
                sum(row["margin"] is not None and row["margin"] > 0 for row in public_rows),
                sum(row["margin"] == 0 for row in public_rows),
                sum(row["margin"] is not None and row["margin"] < 0 for row in public_rows),
            ],
            "adaptive_wins_draws_losses": [
                sum(row["margin"] is not None and row["margin"] > 0 for row in adaptive_rows),
                sum(row["margin"] == 0 for row in adaptive_rows),
                sum(row["margin"] is not None and row["margin"] < 0 for row in adaptive_rows),
            ],
            "family": family,
        },
        "games": [compact(row) for row in rows],
        "public_games": [compact(row) for row in public_rows],
        "adaptive_reference_games": [compact(row) for row in adaptive_rows],
        "determinism_runs": [compact(det_a), compact(det_b)],
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = REPORT_DIR / "results.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "submission_gate_passed": acceptance,
        "acceptance": report["acceptance"],
        "public_comparison": report["public_comparison"],
        "results": str(output),
    }, indent=2))
    if not acceptance:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
