"""Small current-engine runner used by the graph-relay research lane.

The research script imports the official Kaggriculture interpreter.  This file
only supplies the tiny amount of framework state that the interpreter expects;
it does not reimplement game rules.
"""

from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".research_runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from kaggle_environments.envs.kaggriculture import kaggriculture as engine  # noqa: E402


class Struct(dict):
    """Dict with Kaggle-style attribute access."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def structify(value: Any) -> Any:
    if isinstance(value, dict):
        return Struct({key: structify(item) for key, item in value.items()})
    if isinstance(value, list):
        return [structify(item) for item in value]
    return value


def plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


def _configuration(seed: int) -> Struct:
    spec_path = RUNTIME / "kaggle_environments/envs/kaggriculture/kaggriculture.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))["configuration"]
    values = {}
    for key, item in spec.items():
        values[key] = item.get("default") if isinstance(item, dict) else item
    values["seed"] = int(seed)
    return structify(values)


def _new_state() -> list[Struct]:
    states = []
    for player in range(2):
        states.append(
            structify(
                {
                    "observation": {
                        "player": player,
                        "step": 0,
                        "remainingOverageTime": 60.0,
                    },
                    "action": {"farmer": ["PASS"], "hands": [], "market": []},
                    "status": "ACTIVE",
                    "reward": 0.0,
                }
            )
        )
    return states


def load_agent(path: Path, tag: str) -> tuple[Any, Callable[..., dict]]:
    """Load a source agent under a fresh module name for each game."""

    module_name = f"research_agent_{tag}_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load agent: {path}")
    module = importlib.util.module_from_spec(spec)
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(path.parent))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = old_path
    return module, module.agent


def _call_agent(agent: Callable[..., dict], observation: Struct, configuration: Struct) -> dict:
    params = inspect.signature(agent).parameters
    if len(params) >= 2:
        return agent(observation, copy.deepcopy(configuration))
    return agent(observation)


def _action_shape_errors(action: Any) -> int:
    if not isinstance(action, dict):
        return 1
    errors = 0
    if not isinstance(action.get("farmer", ["PASS"]), list):
        errors += 1
    if not isinstance(action.get("hands", []), list):
        errors += 1
    market = action.get("market", [])
    if not isinstance(market, list):
        errors += 1
    elif len(market) > 10:
        errors += 1
    return errors


def _tile_events(before: list, after: list, day: int) -> tuple[int, int, int]:
    escapes = crop_deaths = fresh_crop_deaths = 0
    for y, row in enumerate(before):
        for x, old in enumerate(row):
            new = after[y][x]
            if isinstance(old, dict) and "animal" in old:
                if not (isinstance(new, dict) and new.get("animal") == old.get("animal")):
                    escapes += 1
            if isinstance(old, dict) and old.get("kind") == "PLANT":
                if isinstance(new, dict) and new.get("kind") == "WEED":
                    crop_deaths += 1
                    if int(old.get("planted_day", -1000)) == day:
                        fresh_crop_deaths += 1
    return escapes, crop_deaths, fresh_crop_deaths


def _seed_overcommit(action: dict, private: dict) -> tuple[int, int]:
    unit_actions = [action.get("farmer", ["PASS"]), *(action.get("hands", []) or [])]
    demand: dict[str, int] = {}
    for order in unit_actions:
        if isinstance(order, list) and len(order) >= 2 and order[0] == "PLANT":
            demand[str(order[1])] = demand.get(str(order[1]), 0) + 1
    events = units = 0
    seeds = private.get("seeds", {}) or {}
    for crop, requested in demand.items():
        excess = max(0, requested - int(seeds.get(crop, 0) or 0))
        if excess:
            events += 1
            units += excess
    return events, units


def _pending_overflow(private: dict, capacity: int) -> int:
    shed = sum(max(0, int(value or 0)) for value in (private.get("shed", {}) or {}).values())
    carried = 0
    for inventory in private.get("inventories", []) or []:
        carried += sum(max(0, int(value or 0)) for value in (inventory or {}).values())
    return max(0, shed + carried - capacity)


def _inventory_value(observation: Struct) -> tuple[int, float]:
    private = observation.private
    items: dict[str, int] = {}
    for source in [private.get("shed", {}), *(private.get("inventories", []) or [])]:
        for key, value in (source or {}).items():
            items[key] = items.get(key, 0) + max(0, int(value or 0))
    count = sum(items.values())
    prices = observation.market.get("prices", {}) or {}
    marked = sum(quantity * float(prices.get(item, 0) or 0) for item, quantity in items.items())
    return count, marked


@dataclass
class GameResult:
    seed: int
    seat: int
    own_score: float
    opponent_score: float
    margin: float
    status: str
    exceptions: int
    malformed_actions: int
    timeout_calls: int
    overage_exhausted: bool
    latency_p95_ms: float
    latency_max_ms: float
    animal_escapes: int
    crop_deaths: int
    fresh_crop_deaths: int
    seed_overcommit_events: int
    seed_overcommit_units: int
    overflow_events: int
    overflow_units: int
    terminal_inventory_units: int
    terminal_inventory_mark: float
    policy_metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        row = dict(self.__dict__)
        row["policy_metadata"] = json.dumps(row["policy_metadata"], sort_keys=True)
        return row


PolicyFactory = Callable[[Any, Callable[..., dict], int], Callable[..., dict]]


def run_game(
    candidate_path: Path,
    opponent_path: Path,
    seed: int,
    seat: int,
    candidate_factory: PolicyFactory | None = None,
    snapshot_hook: Callable[[Struct, int], None] | None = None,
) -> GameResult:
    """Run one deterministic full season on the official interpreter."""

    configuration = _configuration(seed)
    env = SimpleNamespace(configuration=configuration, info={}, done=False, steps=[])
    state = _new_state()
    engine.interpreter(state, env)

    candidate_module, candidate = load_agent(candidate_path, "candidate")
    _, opponent = load_agent(opponent_path, "opponent")
    metadata: dict[str, Any] = {}
    if candidate_factory is not None:
        candidate = candidate_factory(candidate_module, candidate, seat)
        metadata = getattr(candidate, "metadata", metadata)
    agents = [opponent, opponent]
    agents[seat] = candidate

    exceptions = malformed = timeout_calls = 0
    overage = [60.0, 60.0]
    latencies: list[float] = []
    metrics = {
        "animal_escapes": 0,
        "crop_deaths": 0,
        "fresh_crop_deaths": 0,
        "seed_overcommit_events": 0,
        "seed_overcommit_units": 0,
        "overflow_events": 0,
        "overflow_units": 0,
    }

    episode_steps = int(configuration.episodeSteps)
    turns_per_day = int(configuration.turnsPerDay)
    capacity = int(configuration.shedCapacity)
    for step in range(episode_steps - 1):
        for index in range(2):
            state[index].observation.step = step
            state[index].observation.remainingOverageTime = overage[index]
        if snapshot_hook is not None:
            snapshot_hook(copy.deepcopy(state[seat].observation), step)

        eod = (step + 1) % turns_per_day == 0
        before_tiles = (
            copy.deepcopy(state[seat].observation.farms[seat]["tiles"])
            if eod
            else None
        )
        for index, agent in enumerate(agents):
            observation = structify(copy.deepcopy(plain(state[index].observation)))
            started = time.perf_counter()
            try:
                action = _call_agent(agent, observation, configuration)
            except Exception:
                exceptions += int(index == seat)
                action = {"farmer": ["PASS"], "hands": [], "market": []}
            duration = time.perf_counter() - started
            if index == seat:
                latencies.append(duration * 1000.0)
                malformed += _action_shape_errors(action)
                seed_events, seed_units = _seed_overcommit(
                    action if isinstance(action, dict) else {},
                    plain(state[index].observation.private),
                )
                metrics["seed_overcommit_events"] += seed_events
                metrics["seed_overcommit_units"] += seed_units
            if duration > float(configuration.actTimeout):
                overage[index] -= duration - float(configuration.actTimeout)
                if index == seat:
                    timeout_calls += 1
            state[index].action = structify(action if isinstance(action, dict) else {})

        if eod:
            overflow = _pending_overflow(plain(state[seat].observation.private), capacity)
            if overflow:
                metrics["overflow_events"] += 1
                metrics["overflow_units"] += overflow
        engine.interpreter(state, env)
        if eod:
            day = step // turns_per_day
            events = _tile_events(before_tiles, state[seat].observation.farms[seat]["tiles"], day)
            metrics["animal_escapes"] += events[0]
            metrics["crop_deaths"] += events[1]
            metrics["fresh_crop_deaths"] += events[2]
        if all(item.status == "DONE" for item in state):
            break

    scores = [float(state[i].observation.farms[i]["money"]) for i in range(2)]
    inventory_units, inventory_mark = _inventory_value(state[seat].observation)
    ordered = sorted(latencies)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1) if ordered else 0
    return GameResult(
        seed=int(seed),
        seat=int(seat),
        own_score=scores[seat],
        opponent_score=scores[1 - seat],
        margin=scores[seat] - scores[1 - seat],
        status=str(state[seat].status),
        exceptions=exceptions,
        malformed_actions=malformed,
        timeout_calls=timeout_calls,
        overage_exhausted=overage[seat] < 0,
        latency_p95_ms=ordered[p95_index] if ordered else 0.0,
        latency_max_ms=max(ordered, default=0.0),
        terminal_inventory_units=inventory_units,
        terminal_inventory_mark=inventory_mark,
        policy_metadata=metadata,
        **metrics,
    )


def summarize(rows: list[GameResult]) -> dict[str, float]:
    margins = [row.margin for row in rows]
    sorted_margins = sorted(margins)
    tail_n = max(1, math.ceil(0.20 * len(sorted_margins))) if sorted_margins else 1
    return {
        "games": len(rows),
        "wins": sum(value > 0 for value in margins),
        "ties": sum(value == 0 for value in margins),
        "mean_margin": statistics.fmean(margins) if margins else 0.0,
        "median_margin": statistics.median(margins) if margins else 0.0,
        "worst_margin": min(margins, default=0.0),
        "cvar20_margin": statistics.fmean(sorted_margins[:tail_n]) if margins else 0.0,
        "technical_failures": sum(
            row.exceptions + row.malformed_actions + row.timeout_calls + int(row.overage_exhausted)
            for row in rows
        ),
        "animal_escapes": sum(row.animal_escapes for row in rows),
        "crop_deaths": sum(row.crop_deaths for row in rows),
        "fresh_crop_deaths": sum(row.fresh_crop_deaths for row in rows),
        "seed_overcommit_events": sum(row.seed_overcommit_events for row in rows),
        "overflow_units": sum(row.overflow_units for row in rows),
        "latency_p95_ms_max": max((row.latency_p95_ms for row in rows), default=0.0),
        "latency_max_ms": max((row.latency_max_ms for row in rows), default=0.0),
    }
