"""Exact observable resource ledgers and bounded path synthesis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


SHED_TILES = ((4, 4), (5, 4), (4, 5), (5, 5))
MOVES = {
    (1, 0): "EAST",
    (-1, 0): "WEST",
    (0, 1): "SOUTH",
    (0, -1): "NORTH",
}


@dataclass(frozen=True)
class ResourceSnapshot:
    step: int
    money: float
    shed_total: int | None
    shed_headroom: int | None
    cow_shed: int | None
    wheat_shed: int | None
    seeds: tuple[tuple[str, int], ...] | None
    actor_positions: tuple[tuple[int, int], ...]
    hand_count: int
    market_slots: int
    target_tile: Any


@dataclass(frozen=True)
class PathPlan:
    start: tuple[int, int]
    end: tuple[int, int]
    actions: tuple[tuple[Any, ...], ...]
    positions: tuple[tuple[int, int], ...]


def _own(observation: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    seat = int(observation.get("player", 0) or 0)
    farms = observation.get("farms") or []
    farm = farms[seat] if seat < len(farms) and isinstance(farms[seat], dict) else {}
    private = observation.get("private")
    return farm, private if isinstance(private, dict) else None


def resource_snapshot(observation: dict[str, Any], target: tuple[int, int]) -> ResourceSnapshot:
    farm, private = _own(observation)
    positions = [farm.get("farmer"), *(farm.get("hands") or [])]
    clean_positions = tuple(
        (int(row[0]), int(row[1]))
        for row in positions
        if isinstance(row, (list, tuple)) and len(row) >= 2
    )
    shed = private.get("shed") if private is not None else None
    seeds = private.get("seeds") if private is not None else None
    if isinstance(shed, dict):
        shed_total = sum(max(0, int(value or 0)) for value in shed.values())
        shed_headroom = max(0, 100 - shed_total)
        cow_shed = max(0, int(shed.get("COW", 0) or 0))
        wheat_shed = max(0, int(shed.get("WHEAT", 0) or 0))
    else:
        shed_total = shed_headroom = cow_shed = wheat_shed = None
    seed_rows = tuple(sorted((str(key), max(0, int(value or 0))) for key, value in seeds.items())) if isinstance(seeds, dict) else None
    x, y = target
    try:
        target_tile = farm.get("tiles", [])[y][x]
    except (IndexError, TypeError):
        target_tile = "UNREADABLE"
    return ResourceSnapshot(
        step=int(observation.get("step", 0) or 0),
        money=float(farm.get("money", 0.0) or 0.0),
        shed_total=shed_total,
        shed_headroom=shed_headroom,
        cow_shed=cow_shed,
        wheat_shed=wheat_shed,
        seeds=seed_rows,
        actor_positions=clean_positions,
        hand_count=max(0, len(clean_positions) - 1),
        market_slots=10,
        target_tile=target_tile,
    )


def snapshot_payload(snapshot: ResourceSnapshot) -> dict[str, Any]:
    return asdict(snapshot)


def manhattan_path(start: tuple[int, int], end: tuple[int, int]) -> PathPlan:
    x, y = start
    tx, ty = end
    actions: list[tuple[Any, ...]] = []
    positions: list[tuple[int, int]] = [(x, y)]
    while x != tx:
        delta = (1 if tx > x else -1, 0)
        actions.append((MOVES[delta],))
        x += delta[0]
        positions.append((x, y))
    while y != ty:
        delta = (0, 1 if ty > y else -1)
        actions.append((MOVES[delta],))
        y += delta[1]
        positions.append((x, y))
    return PathPlan(start, end, tuple(actions), tuple(positions))


def nearest_shed_path(start: tuple[int, int]) -> PathPlan:
    candidates = [manhattan_path(start, target) for target in SHED_TILES]
    return min(candidates, key=lambda row: (len(row.actions), row.end[1], row.end[0]))


def trace_observations(trace: Iterable[Any]) -> dict[int, dict[str, Any]]:
    result = {}
    for frame in trace:
        if hasattr(frame, "step"):
            result[int(frame.step)] = frame.observation
        else:
            result[int(frame["step"])] = frame.get("observation") or {}
    return result


def actor_position(observation: dict[str, Any], actor: int) -> tuple[int, int] | None:
    farm, _ = _own(observation)
    raw = farm.get("farmer") if actor == 0 else (farm.get("hands") or [None])[actor - 1] if actor - 1 < len(farm.get("hands") or []) else None
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    return int(raw[0]), int(raw[1])


def choose_structural_actor(
    observations: dict[int, dict[str, Any]],
    nominal_build_step: int,
    target: tuple[int, int],
    *,
    max_window: int = 48,
    original_structure_removed_after: int | None = None,
) -> tuple[int, int, tuple[tuple[Any, ...], ...], int, tuple[int, int], bool, Any] | None:
    """Choose a trace-present actor and synthesize shed->target->rejoin travel."""
    earliest = max(0, nominal_build_step - 30)
    for start_step in range(nominal_build_step - 2, earliest - 1, -1):
        observation = observations.get(start_step)
        if not observation:
            continue
        farm, _ = _own(observation)
        x, y = target
        try:
            observed_target = (farm.get("tiles") or [])[y][x]
        except (IndexError, TypeError):
            continue
        counterfactual_empty = original_structure_removed_after is not None and start_step > original_structure_removed_after
        target_state = None if counterfactual_empty else observed_target
        if target_state is None:
            clearance: tuple[tuple[Any, ...], ...] = ()
        elif isinstance(target_state, dict) and "animal" not in target_state:
            clearance = (("DIG",),)
        else:
            continue
        actor_count = 1 + len(farm.get("hands") or [])
        for actor in range(actor_count):
            start = actor_position(observation, actor)
            if start is None:
                continue
            to_shed = nearest_shed_path(start)
            to_target = manhattan_path(to_shed.end, target)
            prefix = (*to_shed.actions, ("PICKUP", "COW", 1), *to_target.actions, *clearance, ("BUILD_PASTURE",), ("PLACE", "COW"))
            end_step = start_step + len(prefix) - 1
            if end_step > nominal_build_step + 8:
                continue
            for rejoin_step in range(end_step + 1, min(end_step + 17, 719)):
                rejoin_observation = observations.get(rejoin_step)
                rejoin_position = actor_position(rejoin_observation or {}, actor)
                if rejoin_position is None:
                    continue
                back = manhattan_path(target, rejoin_position)
                actions = (*prefix, *back.actions)
                if clearance:
                    # One terminal buffer lets the runtime shift BUILD/PLACE/
                    # return by one turn after a bounded DIG retry.
                    actions = (*actions, ("PASS",))
                duration = len(actions)
                if duration < 8:
                    actions = (*actions, *(("PASS",),) * (8 - duration))
                    duration = len(actions)
                if duration <= max_window and start_step + duration <= rejoin_step:
                    padding = rejoin_step - (start_step + duration)
                    actions = (*actions, *(("PASS",),) * padding)
                    if 8 <= len(actions) <= max_window:
                        return actor, start_step, tuple(actions), rejoin_step, rejoin_position, bool(clearance), target_state
    return None
