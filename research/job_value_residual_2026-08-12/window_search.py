"""Deterministic event-anchored discovery of small one-actor route repairs."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any, Iterable, Sequence

from engine_runner import TraceFrame
from protocol import INCUMBENTS
from schema import CandidateWindow, HorizonEffect, Requirement, SellDirective, to_json


DELTAS = {"EAST": (1, 0), "SOUTH": (0, 1), "WEST": (-1, 0), "NORTH": (0, -1)}
OPPOSITE = {"EAST": "WEST", "WEST": "EAST", "NORTH": "SOUTH", "SOUTH": "NORTH"}
FAMILIES = ("maintenance_trade", "productive_detour", "logistics_market")
MOVES = frozenset(DELTAS)
FORBIDDEN = frozenset({"HIRE", "BUY_LAND", "BUILD", "BUILD_COOP", "BUILD_PASTURE", "PLANT", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL"})
SELLABLE = frozenset({"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"})
SHED_TILES = ((4, 4), (5, 4), (4, 5), (5, 5))
REQUIREMENT_KEYS = {
    "hands": {()}, "money": {()}, "actor_position": None, "tile_kind": None,
    "tile_product": None, "tile_yield": None, "actor_inventory": None, "shed": None,
}


def shortest_actions(start: tuple[int, int], target: tuple[int, int]) -> tuple[str, ...]:
    x, y = (max(0, min(9, int(start[0]))), max(0, min(9, int(start[1]))))
    tx, ty = (max(0, min(9, int(target[0]))), max(0, min(9, int(target[1]))))
    result: list[str] = []
    result.extend(["EAST" if tx > x else "WEST"] * abs(tx - x))
    result.extend(["SOUTH" if ty > y else "NORTH"] * abs(ty - y))
    return tuple(result)


def _position_after(position: tuple[int, int], action: Sequence[str]) -> tuple[int, int]:
    if not action or action[0] not in DELTAS:
        return position
    dx, dy = DELTAS[action[0]]
    return (max(0, min(9, position[0] + dx)), max(0, min(9, position[1] + dy)))


def _actor_position(observation: dict[str, Any], actor: int) -> tuple[int, int] | None:
    farm = observation["farms"][int(observation.get("player", 0))]
    positions = [farm.get("farmer"), *(farm.get("hands", []) or [])]
    if actor >= len(positions) or positions[actor] is None:
        return None
    return tuple(map(int, positions[actor]))


def _actor_action(action: dict[str, Any], actor: int) -> tuple[str, ...]:
    if actor == 0:
        return tuple(action.get("farmer", ["PASS"]))
    hands = action.get("hands", []) or []
    return tuple(hands[actor - 1]) if actor - 1 < len(hands) else ("PASS",)


def _tile(observation: dict[str, Any], position: tuple[int, int]) -> Any:
    return observation["farms"][int(observation.get("player", 0))]["tiles"][position[1]][position[0]]


def _job_at(observation: dict[str, Any], position: tuple[int, int]) -> tuple[str, Requirement] | None:
    tile = _tile(observation, position)
    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        if int(tile.get("yield_units", 0) or 0) > 0:
            return "HARVEST", Requirement("tile_yield", position, "ge", 1)
        if not tile.get("watered_today", False):
            return "WATER", Requirement("tile_kind", position, "eq", "PLANT")
    if isinstance(tile, dict) and tile.get("kind") in {"COOP", "PASTURE"} and tile.get("animal"):
        if not tile.get("fed_today", False):
            return "FEED", Requirement("tile_product", position, "eq", str(tile["animal"]))
        if not tile.get("cared_today", False):
            return "CARE", Requirement("tile_product", position, "eq", str(tile["animal"]))
    if isinstance(tile, dict) and (tile.get("kind") == "WEED" or (tile.get("kind") in {"COOP", "PASTURE"} and not tile.get("animal"))):
        return "DIG", Requirement("tile_kind", position, "eq", str(tile.get("kind")))
    return None


def _route_matches(frame: TraceFrame, route: Sequence[dict[str, Any]], actor: int) -> bool:
    return 0 <= frame.step < len(route) and _actor_action(frame.action, actor) == _actor_action(route[frame.step], actor)


def _normalized_action(action: Any) -> str:
    """Compare the full readable action object, including every actor and market order."""
    return json.dumps(action, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _window_route_matches(frames: dict[int, TraceFrame], frame: TraceFrame, route: Sequence[dict[str, Any]], actor: int, length: int) -> bool:
    """Do not modify a readable-tape interval already changed by an incumbent overlay."""
    return all(
        frame.step + offset in frames
        and _normalized_action(frames[frame.step + offset].action) == _normalized_action(route[frame.step + offset])
        for offset in range(length)
    )


def _stationary(action: tuple[str, ...]) -> bool:
    return not action or action[0] not in MOVES


def _candidate_id(window: CandidateWindow) -> str:
    encoded = to_json(replace(window, effects=()))
    source = {
        "incumbent": window.incumbent, "trigger_step": window.trigger_step, "actor": window.actor,
        "family": window.family, "actions": encoded["actions"], "requirements": encoded["requirements"],
        "sell_directives": encoded["sell_directives"],
    }
    return hashlib.sha256(json.dumps(source, default=list, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


def _effects(step: int) -> tuple[HorizonEffect, ...]:
    remaining = max(1, 719 - step)
    horizons = (remaining,) if step >= 671 else tuple(sorted(set((min(24, remaining), min(48, remaining)))))
    return tuple(HorizonEffect(horizon, 0.0, (), (), (), ()) for horizon in horizons)


def _frame_positions(trace: Sequence[TraceFrame]) -> dict[int, TraceFrame]:
    return {frame.step: frame for frame in trace}


def _rejoin_position(frames: dict[int, TraceFrame], frame: TraceFrame, route: Sequence[dict[str, Any]], actor: int, length: int) -> tuple[int, int] | None:
    next_frame = frames.get(frame.step + length)
    if next_frame is not None:
        return _actor_position(next_frame.observation, actor)
    position = _actor_position(frame.observation, actor)
    if position is None:
        return None
    for offset in range(length):
        if frame.step + offset >= len(route):
            return None
        position = _position_after(position, _actor_action(route[frame.step + offset], actor))
    return position


def _inventory(observation: dict[str, Any], actor: int) -> dict[str, int]:
    inventories = (observation.get("private", {}) or {}).get("inventories", []) or []
    return inventories[actor] if actor < len(inventories) else {}


def _targets(observation: dict[str, Any]) -> list[tuple[tuple[int, int], str, Requirement]]:
    result = []
    for y in range(10):
        for x in range(10):
            job = _job_at(observation, (x, y))
            if job is not None:
                result.append(((x, y), *job))
    return result


def _drop_targets(observation: dict[str, Any], actor: int) -> list[tuple[tuple[int, int], str, Requirement]]:
    cargo = [(product, int(amount or 0)) for product, amount in _inventory(observation, actor).items()
             if product in SELLABLE and int(amount or 0) > 0]
    if not cargo:
        return []
    product, _ = sorted(cargo)[0]
    return [(tile, "DROP", Requirement("actor_inventory", (actor, product), "ge", 1)) for tile in SHED_TILES]


def _shed_occupancy(observation: dict[str, Any]) -> int:
    return sum(max(0, int(value or 0)) for value in ((observation.get("private", {}) or {}).get("shed", {}) or {}).values())


def _route_sell(route: Sequence[dict[str, Any]], step: int, length: int, product: str, delivered: int) -> SellDirective | None:
    for offset in range(length):
        for order in route[step + offset].get("market", []) or []:
            if len(order) >= 3 and order[0] == "SELL" and order[1] == product:
                return SellDirective(offset, product, min(delivered, max(0, int(order[2] or 0))))
    return None


def _with_capacity_anchor(window: CandidateWindow, observation: dict[str, Any], delivered: int) -> CandidateWindow:
    """Annotate only a delivery that would project the finite shed to the capacity region."""
    projected = _shed_occupancy(observation) + max(0, int(delivered))
    if projected < 85:
        return window
    capacity = ("shed_occupancy", projected, "ge_85")
    return replace(window, effects=tuple(replace(effect, capacity=(capacity,)) for effect in window.effects))


def validate_window(window: CandidateWindow) -> list[str]:
    errors: list[str] = []
    if window.incumbent not in INCUMBENTS:
        errors.append("wrong_incumbent")
    if window.family not in FAMILIES:
        errors.append("unknown_family")
    if not 4 <= len(window.actions) <= 8:
        errors.append("window_length")
    if window.rejoin_step != window.trigger_step + len(window.actions):
        errors.append("rejoin_step")
    if len(window.expected_positions) != len(window.actions) + 1:
        errors.append("position_count")
    if any(action and action[0] in FORBIDDEN for action in window.actions):
        errors.append("forbidden_opcode")
    if any(len(action) > 1 and action[1] in MOVES for action in window.actions):
        errors.append("multiple_actors")
    for requirement in window.requirements:
        if requirement.field not in REQUIREMENT_KEYS:
            errors.append("invalid_requirement")
            break
        allowed = REQUIREMENT_KEYS[requirement.field]
        valid_key = allowed is None or tuple(requirement.key) in allowed
        if requirement.operator not in {"eq", "ge", "le"} or not valid_key:
            errors.append("invalid_requirement")
            break
        key = tuple(requirement.key)
        if requirement.field == "actor_position" and len(key) != 1:
            errors.append("invalid_requirement")
        if requirement.field in {"tile_kind", "tile_product", "tile_yield"} and len(key) != 2:
            errors.append("invalid_requirement")
        if requirement.field == "actor_inventory" and len(key) != 2:
            errors.append("invalid_requirement")
        if requirement.field == "shed" and len(key) != 1:
            errors.append("invalid_requirement")
    if window.family == "logistics_market":
        has_delivery = any(action and action[0] == "DROP" for action in window.actions)
        if not has_delivery:
            errors.append("market_without_delivery")
    if any(directive.quantity <= 0 for directive in window.sell_directives):
        errors.append("sell_quantity")
    if len(window.sell_directives) > 1:
        errors.append("more_than_one_sell")
    return list(dict.fromkeys(errors))


def mine_candidates(
    incumbent: str, trace: Sequence[TraceFrame], route: Sequence[dict[str, Any]], *,
    opponent_family: str, seed: int, seat: int,
) -> tuple[CandidateWindow, ...]:
    """Mine at most one structural candidate per family for one public context."""
    del opponent_family, seed, seat  # Context scopes retention, never the structural candidate ID.
    if incumbent not in INCUMBENTS:
        raise ValueError(f"unknown incumbent: {incumbent}")
    frames = _frame_positions(trace)
    choices: dict[str, CandidateWindow | None] = {family: None for family in FAMILIES}

    def retain(candidate: CandidateWindow | None) -> None:
        if candidate is None:
            return
        current = choices[candidate.family]
        key = (len(candidate.actions), -_public_amount(candidate), candidate.candidate_id)
        if current is None or key < (len(current.actions), -_public_amount(current), current.candidate_id):
            choices[candidate.family] = candidate
    for frame in sorted(trace, key=lambda item: item.step):
        for actor in range(1 + len(frame.observation["farms"][int(frame.observation.get("player", 0))].get("hands", []) or [])):
            if not _route_matches(frame, route, actor):
                continue
            position = _actor_position(frame.observation, actor)
            if position is None:
                continue
            targets = _targets(frame.observation) + _drop_targets(frame.observation, actor)
            targets = sorted(
                targets,
                key=lambda item: (abs(item[0][0] - position[0]) + abs(item[0][1] - position[1]), item[0], item[1]),
            )[:4]
            inventory = _inventory(frame.observation, actor)
            for length in range(4, 9):
                if frame.step < 0 or frame.step + length > len(route):
                    continue
                if not _window_route_matches(frames, frame, route, actor, length):
                    continue
                baseline = [_actor_action(route[frame.step + offset], actor) for offset in range(length)]
                has_maintenance = any(action and action[0] in {"WATER", "FEED", "CARE"} for action in baseline)
                has_pass_or_reverse = any(action and action[0] == "PASS" for action in baseline) or any(
                    left and right and left[0] in OPPOSITE and OPPOSITE[left[0]] == right[0]
                    for left, right in zip(baseline, baseline[1:])
                )
                rejoin = _rejoin_position(frames, frame, route, actor, length)
                if rejoin is None:
                    continue
                for target, job, requirement in targets:
                    if has_maintenance and job in {"HARVEST", "DROP"}:
                        candidate = _build_window_with_rejoin(incumbent, "maintenance_trade", frame, actor, target, job, requirement, route, length, rejoin)
                        retain(candidate)
                    if has_pass_or_reverse:
                        candidate = _build_window_with_rejoin(incumbent, "productive_detour", frame, actor, target, job, requirement, route, length, rejoin)
                        retain(candidate)
                scheduled = _scheduled_jobs(frames, frame, actor, length)
                if len(scheduled) >= 2:
                    retain(_reversed_jobs_window(
                        incumbent, frame, actor, scheduled[0], scheduled[1], route, length, rejoin
                    ))
                for harvest_offset in range(length):
                    sample = frames.get(frame.step + harvest_offset)
                    if sample is None or _actor_action(sample.action, actor)[:1] != ("HARVEST",):
                        continue
                    harvest_position = _actor_position(sample.observation, actor)
                    harvest_tile = _tile(sample.observation, harvest_position) if harvest_position is not None else None
                    if not isinstance(harvest_tile, dict):
                        continue
                    product = str(harvest_tile.get("crop") or "")
                    quantity = int(harvest_tile.get("yield_units", 0) or 0)
                    if product not in SELLABLE or quantity <= 0:
                        continue
                    candidate = _harvest_logistics_window(
                        incumbent, frame, actor, harvest_position, product, quantity, route, length, rejoin
                    )
                    retain(candidate)
                cargo = [(product, int(amount or 0)) for product, amount in inventory.items() if product in SELLABLE and int(amount or 0) > 0]
                if cargo:
                    product, quantity = sorted(cargo)[0]
                    shed = min(SHED_TILES, key=lambda item: (abs(item[0] - position[0]) + abs(item[1] - position[1]), item))
                    requirement = Requirement("actor_inventory", (actor, product), "ge", 1)
                    candidate = _build_window_with_rejoin(incumbent, "logistics_market", frame, actor, shed, "DROP", requirement, route, length, rejoin)
                    if candidate is not None:
                        directive = _route_sell(route, frame.step, length, product, quantity)
                        candidate = replace(candidate, sell_directives=() if directive is None else (directive,))
                        candidate = _with_capacity_anchor(candidate, frame.observation, quantity)
                        candidate = replace(candidate, candidate_id=_candidate_id(candidate))
                        retain(candidate)
    selected = []
    for family, candidate in choices.items():
        if candidate is not None:
            selected.append(candidate)
    return tuple(sorted(selected, key=lambda item: (item.family, item.trigger_step, item.actor, len(item.actions), item.candidate_id)))


def _build_window_with_rejoin(*args: Any) -> CandidateWindow | None:
    incumbent, family, frame, actor, target, job, requirement, route, window_len, rejoin = args
    start = _actor_position(frame.observation, actor)
    if start is None:
        return None
    prefix = [(move,) for move in shortest_actions(start, target)] + [(job,)]
    actions = prefix + [(move,) for move in shortest_actions(target, rejoin)]
    if len(actions) > window_len:
        return None
    baseline = [_actor_action(route[frame.step + offset], actor) for offset in range(window_len)]
    for offset in range(len(actions), window_len):
        if not _stationary(baseline[offset]):
            return None
        actions.append(baseline[offset])
    positions = [start]
    for action in actions:
        positions.append(_position_after(positions[-1], action))
    if positions[-1] != rejoin:
        return None
    window = CandidateWindow(
        "", incumbent, family, frame.step, actor, frame.step + window_len, tuple(actions), tuple(positions),
        (Requirement("actor_position", (actor,), "eq", start), requirement), (), tuple(baseline), (target,), _effects(frame.step),
    )
    window = replace(window, candidate_id=_candidate_id(window))
    return None if validate_window(window) else window


def _reversed_jobs_window(
    incumbent: str, frame: TraceFrame, actor: int, first: tuple[tuple[int, int], str, Requirement],
    second: tuple[tuple[int, int], str, Requirement], route: Sequence[dict[str, Any]], window_len: int,
    rejoin: tuple[int, int],
) -> CandidateWindow | None:
    """Swap two already scheduled, legal single-actor jobs without widening the window."""
    start = _actor_position(frame.observation, actor)
    if start is None:
        return None
    first_target, first_job, first_requirement = first
    second_target, second_job, second_requirement = second
    actions = [(move,) for move in shortest_actions(start, second_target)] + [(second_job,)]
    actions += [(move,) for move in shortest_actions(second_target, first_target)] + [(first_job,)]
    actions += [(move,) for move in shortest_actions(first_target, rejoin)]
    if len(actions) > window_len:
        return None
    baseline = [_actor_action(route[frame.step + offset], actor) for offset in range(window_len)]
    for offset in range(len(actions), window_len):
        if not _stationary(baseline[offset]):
            return None
        actions.append(baseline[offset])
    positions = [start]
    for action in actions:
        positions.append(_position_after(positions[-1], action))
    if positions[-1] != rejoin:
        return None
    window = CandidateWindow(
        "", incumbent, "productive_detour", frame.step, actor, frame.step + window_len,
        tuple(actions), tuple(positions),
        (Requirement("actor_position", (actor,), "eq", start), second_requirement, first_requirement),
        (), tuple(baseline), (second_target, first_target), _effects(frame.step),
    )
    window = replace(window, candidate_id=_candidate_id(window))
    return None if validate_window(window) else window


def _harvest_logistics_window(
    incumbent: str, frame: TraceFrame, actor: int, harvest: tuple[int, int], product: str, quantity: int,
    route: Sequence[dict[str, Any]], window_len: int, rejoin: tuple[int, int],
) -> CandidateWindow | None:
    """Collect a trace-observed harvest and deliver it before the original rejoin point."""
    start = _actor_position(frame.observation, actor)
    if start is None:
        return None
    shed = min(SHED_TILES, key=lambda item: (abs(item[0] - harvest[0]) + abs(item[1] - harvest[1]), item))
    actions = [(move,) for move in shortest_actions(start, harvest)] + [("HARVEST",)]
    actions += [(move,) for move in shortest_actions(harvest, shed)] + [("DROP",)]
    actions += [(move,) for move in shortest_actions(shed, rejoin)]
    if len(actions) > window_len:
        return None
    baseline = [_actor_action(route[frame.step + offset], actor) for offset in range(window_len)]
    for offset in range(len(actions), window_len):
        if not _stationary(baseline[offset]):
            return None
        actions.append(baseline[offset])
    positions = [start]
    for action in actions:
        positions.append(_position_after(positions[-1], action))
    if positions[-1] != rejoin:
        return None
    directive = _route_sell(route, frame.step, window_len, product, quantity)
    window = CandidateWindow(
        "", incumbent, "logistics_market", frame.step, actor, frame.step + window_len,
        tuple(actions), tuple(positions),
        (Requirement("actor_position", (actor,), "eq", start), Requirement("tile_yield", harvest, "ge", 1)),
        () if directive is None else (directive,), tuple(baseline), (harvest, shed), _effects(frame.step),
    )
    window = replace(window, candidate_id=_candidate_id(window))
    window = _with_capacity_anchor(window, frame.observation, quantity)
    return None if validate_window(window) else window


def _scheduled_jobs(
    frames: dict[int, TraceFrame], frame: TraceFrame, actor: int, window_len: int,
) -> list[tuple[tuple[int, int], str, Requirement]]:
    jobs = []
    for offset in range(window_len):
        sample = frames.get(frame.step + offset)
        if sample is None:
            continue
        action = _actor_action(sample.action, actor)
        position = _actor_position(sample.observation, actor)
        if position is None or not action:
            continue
        legal = _job_at(sample.observation, position)
        if legal is not None and legal[0] == action[0]:
            jobs.append((position, *legal))
    return jobs


def _public_amount(window: CandidateWindow) -> int:
    for requirement in window.requirements:
        if requirement.field in {"tile_yield", "actor_inventory"} and isinstance(requirement.value, int):
            return requirement.value
    return 0
