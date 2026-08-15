"""Runtime application and standalone source rendering for compiled patches."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any, Callable

from model import CompiledCandidate


def candidate_runtime_payload(candidate: CompiledCandidate) -> dict[str, Any]:
    payload = candidate.payload()
    payload["candidate_id"] = candidate.candidate_id
    payload["genome_id"] = candidate.genome.genome_id
    return payload


RUNTIME_SOURCE = r'''
_TOPOLOGY_BASE_AGENT = agent
_TOPOLOGY_STATE = {0: {"last_step": -1, "failed": set(), "active": set(), "delays": {}, "retries": {}}, 1: {"last_step": -1, "failed": set(), "active": set(), "delays": {}, "retries": {}}}

def _topology_plain(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(value, key, default)

def _topology_copy(action):
    action = action if isinstance(action, dict) else {}
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(row or ["PASS"]) for row in (action.get("hands") or [])],
        "market": [list(row) for row in (action.get("market") or [])],
    }

def _topology_context(obs):
    step = max(0, min(718, int(_topology_plain(obs, "step", 0) or 0)))
    seat = 1 if int(_topology_plain(obs, "player", 0) or 0) == 1 else 0
    farms = _topology_plain(obs, "farms", []) or []
    farm = farms[seat] if seat < len(farms) else {}
    private = _topology_plain(obs, "private", None)
    return step, seat, farm, private

def _topology_positions(farm):
    return [_topology_plain(farm, "farmer", None), *list(_topology_plain(farm, "hands", []) or [])]

def _topology_tile(farm, position):
    try:
        x, y = int(position[0]), int(position[1])
        return (_topology_plain(farm, "tiles", []) or [])[y][x]
    except (IndexError, TypeError, ValueError):
        return "UNREADABLE"

def _topology_value(field, obs, action, farm, private, value):
    if field == "step":
        return int(_topology_plain(obs, "step", 0) or 0)
    if field == "money":
        return float(_topology_plain(farm, "money", 0.0) or 0.0)
    if field == "hand_count":
        return len(_topology_plain(farm, "hands", []) or [])
    if field == "market_slots":
        return max(0, 10 - len(action.get("market") or []))
    if field == "actor_position":
        positions = _topology_positions(farm)
        if not isinstance(value, dict):
            return None
        actor = int(value.get("actor", -1))
        expected = value.get("position")
        if actor < 0 or actor >= len(positions) or not isinstance(expected, (list, tuple)):
            return None
        position = positions[actor]
        return tuple(position) if isinstance(position, (list, tuple)) else None
    if field == "target_tile":
        return _topology_tile(farm, value)
    if private is None:
        return None
    shed = _topology_plain(private, "shed", None)
    if not isinstance(shed, dict):
        return None
    if field == "shed_headroom":
        return max(0, 100 - sum(max(0, int(item or 0)) for item in shed.values()))
    if field == "cow_total":
        inventories = _topology_plain(private, "inventories", None)
        if not isinstance(inventories, list):
            return None
        return max(0, int(shed.get("COW", 0) or 0)) + sum(max(0, int((row or {}).get("COW", 0) or 0)) for row in inventories if isinstance(row, dict))
    return None

def _topology_condition(condition, obs, action, farm, private):
    field = condition["field"]
    expected = condition.get("value")
    actual = _topology_value(field, obs, action, farm, private, expected)
    operator = condition["operator"]
    if operator == "empty":
        return actual is None
    if operator == "clearable":
        return actual is None or (isinstance(actual, dict) and "animal" not in actual)
    if actual is None:
        return False
    if operator == "eq":
        if field == "actor_position" and isinstance(expected, dict):
            expected = expected.get("position")
        return actual == (tuple(expected) if isinstance(expected, list) and isinstance(actual, tuple) else expected)
    if operator == "ge":
        return actual >= expected
    return False

def _topology_window_activation(step, patches, window):
    patch_steps = [row["step"] for row in patches if window["start"] <= row["step"] <= window["end"]]
    return min(patch_steps) if patch_steps else window["start"]

def _topology_apply(obs, base_action, spec, state):
    step, seat, farm, private = _topology_context(obs)
    patches = spec["patches"]
    action = _topology_copy(base_action)
    capacity = (spec.get("public_selector") or {}).get("capacity")
    if capacity:
        headroom = _topology_value("shed_headroom", obs, action, farm, private, None)
        if headroom is None or headroom < int(capacity["min_shed_headroom"]):
            return action
    for window in spec["windows"]:
        name = window["name"]
        activation = _topology_window_activation(step, patches, window)
        if step == activation and name not in state["active"] and name not in state["failed"]:
            if all(_topology_condition(row, obs, action, farm, private) for row in window["entry_conditions"]):
                state["active"].add(name)
            else:
                state["failed"].add(name)
        if step >= window["rejoin_step"]:
            state["active"].discard(name)
    effective_step = step
    retry = (spec.get("public_selector") or {}).get("dig_retry")
    if retry and int(retry["build_step"]) <= step <= int(retry["end_step"]):
        effective_step = step - int(state["delays"].get(retry["window"], 0))
    patch = next((row for row in patches if int(row["step"]) == effective_step), None)
    if patch is None:
        return action
    covering = [window for window in spec["windows"] if window["start"] <= step <= window["end"]]
    if covering and any(window["name"] in state["failed"] for window in covering):
        return action
    if covering and any(window["name"] not in state["active"] for window in covering if step >= _topology_window_activation(step, patches, window)):
        return action
    if retry and int(retry["build_step"]) <= effective_step <= int(retry["end_step"]):
        building = any(int(actor) == int(retry["actor"]) and order and order[0] == "BUILD_PASTURE" for actor, order in patch["actor_actions"])
        if building:
            target_state = _topology_tile(farm, retry["target"])
            if target_state is not None:
                used = int(state["retries"].get(retry["window"], 0))
                clearable = isinstance(target_state, dict) and "animal" not in target_state
                if not clearable or used >= int(retry["max_retries"]):
                    state["failed"].add(retry["window"])
                    return _topology_copy(base_action)
                state["retries"][retry["window"]] = used + 1
                state["delays"][retry["window"]] = int(state["delays"].get(retry["window"], 0)) + 1
                patch = {"actor_actions": [[int(retry["actor"]), ["DIG"]]], "remove_market": [], "append_market": []}
    units = [action["farmer"], *action["hands"]]
    for actor, order in patch["actor_actions"]:
        actor = int(actor)
        if actor >= len(units):
            return _topology_copy(base_action)
        units[actor] = list(order)
    action["farmer"], action["hands"] = units[0], units[1:]
    market = [list(row) for row in action["market"]]
    for remove in patch["remove_market"]:
        target = list(remove)
        for index, row in enumerate(market):
            if row == target:
                market.pop(index)
                break
    exposure = (spec.get("public_selector") or {}).get("market_exposure")
    append_allowed = True
    if exposure:
        shared = _topology_plain(obs, "market", {}) or {}
        inventory = _topology_plain(shared, "inventory", {}) or {}
        prices = _topology_plain(shared, "prices", {}) or {}
        product = exposure["product"]
        append_allowed = int(_topology_plain(inventory, product, 10**9) or 0) <= int(exposure["max_public_inventory"]) and int(_topology_plain(prices, product, 0) or 0) >= int(exposure["min_public_price"])
    if append_allowed:
        market.extend([list(row) for row in patch["append_market"]])
    if len(market) > 10:
        return _topology_copy(base_action)
    action["market"] = market
    return action

def _topology_project(obs, action, fallback):
    step, seat, farm, private = _topology_context(obs)
    expected_hands = len(_topology_plain(farm, "hands", []) or [])
    if not isinstance(action, dict):
        action = _topology_copy(fallback)
    else:
        action = _topology_copy(action)
    if len(action["hands"]) < expected_hands:
        action["hands"].extend([["PASS"] for _ in range(expected_hands - len(action["hands"]))])
    action["hands"] = action["hands"][:expected_hands]
    if len(action["market"]) > 10:
        return _topology_copy(fallback)
    seeds = _topology_plain(private, "seeds", None) if private is not None else None
    if seeds is not None:
        units = [action["farmer"], *action["hands"]]
        demand = {}
        readable = True
        for order in units:
            if isinstance(order, list) and len(order) >= 2 and order[0] == "PLANT":
                crop = str(order[1])
                demand[crop] = demand.get(crop, 0) + 1
        available = {}
        for crop in demand:
            raw = _topology_plain(seeds, crop, None)
            if raw is None:
                readable = False
                break
            try:
                available[crop] = max(0, int(raw))
            except (TypeError, ValueError):
                readable = False
                break
        if readable:
            blocked = {crop for crop, count in demand.items() if count > available[crop]}
            if blocked:
                units = [["PASS"] if isinstance(order, list) and len(order) >= 2 and order[0] == "PLANT" and str(order[1]) in blocked else order for order in units]
                action["farmer"], action["hands"] = units[0], units[1:]
    return action

def agent(obs, configuration=None):
    if _TOPOLOGY_SPEC["lane"] == "boatlee_v16_rc2_market_relay":
        base = _TOPOLOGY_BASE_AGENT(obs)
    else:
        base = _TOPOLOGY_BASE_AGENT(obs, configuration)
    step, seat, farm, private = _topology_context(obs)
    state = _TOPOLOGY_STATE[seat]
    if step == 0 or step < state["last_step"]:
        state = {"last_step": step, "failed": set(), "active": set(), "delays": {}, "retries": {}}
        _TOPOLOGY_STATE[seat] = state
    state["last_step"] = step
    candidate = _topology_apply(obs, base, _TOPOLOGY_SPEC, state)
    return _topology_project(obs, candidate, base)
'''


def render_runtime(candidate: CompiledCandidate) -> str:
    encoded = json.dumps(candidate_runtime_payload(candidate), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"\n# ---- dual-incumbent topology patch {candidate.candidate_id} ----\n_TOPOLOGY_SPEC = json.loads({encoded!r})\n{RUNTIME_SOURCE.strip()}\n"


def make_fast_policy(module: Any, base_agent: Callable[..., dict], candidate: CompiledCandidate) -> Callable[..., dict]:
    """Install the exact standalone runtime source into an already-loaded control module."""
    module.__dict__["agent"] = base_agent
    exec(compile(render_runtime(candidate), f"<fast:{candidate.candidate_id}>", "exec"), module.__dict__)
    return module.__dict__["agent"]
