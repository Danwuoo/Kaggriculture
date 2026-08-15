"""Render the exact fast/standalone runtime for a compiled v2 candidate."""

from __future__ import annotations

import json
from typing import Any, Callable

from model import CompiledAsyncCandidate


RUNTIME_SOURCE = r'''
_ASYNC_BASE_AGENT = agent
_ASYNC_BASE_WOOL_GATES = tuple(globals().get("_V16_WOOL_GATES", ()))
_ASYNC_BASE_RC2_NEEDS_RELAY = globals().get("_rc2_needs_relay")
_ASYNC_STATE = {0: {"last_step": -1, "active": set(), "failed": set()}, 1: {"last_step": -1, "active": set(), "failed": set()}}

def _async_get(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    return getter(key, default) if callable(getter) else getattr(value, key, default)

def _async_context(obs):
    step = max(0, min(718, int(_async_get(obs, "step", 0) or 0)))
    seat = 1 if int(_async_get(obs, "player", 0) or 0) == 1 else 0
    farms = _async_get(obs, "farms", []) or []
    farm = farms[seat] if seat < len(farms) else {}
    private = _async_get(obs, "private", None)
    positions = [_async_get(farm, "farmer", None), *list(_async_get(farm, "hands", []) or [])]
    positions = tuple(tuple(row) if isinstance(row, (list, tuple)) else None for row in positions)
    return step, seat, farm, private, positions

def _async_copy(action):
    action = action if isinstance(action, dict) else {}
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(row or ["PASS"]) for row in (action.get("hands") or [])],
        "market": [list(row or []) for row in (action.get("market") or [])],
    }

def _async_constants():
    values = dict(_ASYNC_SPEC.get("constants") or [])
    if "demand_alpha_milli" in values:
        globals()["_DEMAND_ALPHA"] = int(values["demand_alpha_milli"]) / 1000.0
    if "weed_replay_steps" in values:
        globals()["_WEED_REPLAY_STEPS"] = int(values["weed_replay_steps"])
    names = {
        "livestock_switch_step": "_V16_SWITCH_STEP",
        "wool_pressure": "_V16_WOOL_PRESSURE",
        "wool_batch": "_V16_WOOL_BATCH",
        "wool_gap": "_V16_WOOL_GAP",
        "relay_distance_max": "_RC2_ROUTE_DISTANCE_MAX",
        "relay_lead": "_RC2_RELAY_LEAD",
        "relay_first": "_RC2_RELAY_FIRST",
        "relay_last": "_RC2_RELAY_LAST",
    }
    for source, target in names.items():
        if source in values and target in globals():
            globals()[target] = int(values[source])
    if "wool_gate_scale_bps" in values and _ASYNC_BASE_WOOL_GATES:
        scale = int(values["wool_gate_scale_bps"])
        globals()["_V16_WOOL_GATES"] = tuple((int(step), max(1, int(round(int(gate) * scale / 10000.0)))) for step, gate in _ASYNC_BASE_WOOL_GATES)

def _async_window_state(step, positions, state):
    for window in _ASYNC_SPEC.get("windows") or []:
        name = window["window_id"]
        if step == int(window["start"]) and name not in state["failed"]:
            if positions == tuple(tuple(row) for row in window["entry_positions"]):
                state["active"].add(name)
            else:
                state["failed"].add(name)
        if step == int(window["rejoin_step"]):
            if name in state["active"] and positions != tuple(tuple(row) for row in window["rejoin_positions"]):
                state["failed"].add(name)
            state["active"].discard(name)

def _async_public_market(obs, market):
    shared = _async_get(obs, "market", {}) or {}
    inventory = _async_get(shared, "inventory", {}) or {}
    prices = _async_get(shared, "prices", {}) or {}
    policies = {row["product"]: row for row in (_ASYNC_SPEC.get("market_policy") or [])}
    result = []
    for order in market:
        row = list(order)
        if len(row) < 3 or row[0] != "SELL" or row[1] not in policies:
            result.append(row)
            continue
        policy = policies[row[1]]
        public_inventory = int(_async_get(inventory, row[1], 10**9) or 0)
        public_price = int(_async_get(prices, row[1], 0) or 0)
        base = int((globals().get("_MARKET_PARAMS", {}).get(row[1]) or (0,))[0] or 0)
        if public_inventory > int(policy["max_public_inventory"]):
            continue
        if int(policy["min_price_bps"]) and public_price * 10000 < base * int(policy["min_price_bps"]):
            continue
        quantity = max(0, int(row[2])) * int(policy["quantity_bps"]) // 10000
        if quantity <= 0:
            continue
        row[2] = quantity
        result.append(row)
    limit = int(dict(_ASYNC_SPEC.get("constants") or []).get("max_market_orders", 10))
    return result[:max(0, min(10, limit))]

def _async_apply(obs, base, state, positions, private):
    step = max(0, min(718, int(_async_get(obs, "step", 0) or 0)))
    patch = next((row for row in (_ASYNC_SPEC.get("patches") or []) if int(row["step"]) == step), None)
    action = _async_copy(base)
    if patch is not None:
        active = all(name in state["active"] and name not in state["failed"] for name in patch["window_ids"])
        expected = []
        for window in _ASYNC_SPEC.get("windows") or []:
            if window["window_id"] in patch["window_ids"]:
                expected.extend(window.get("expected_positions", {}).get(str(step), []))
        if expected and positions != tuple(tuple(row) for row in expected[:len(positions)]):
            active = False
            state["failed"].update(patch["window_ids"])
        if patch.get("private_required") and private is None:
            active = False
            state["failed"].update(patch["window_ids"])
        if active:
            if patch.get("unit") is not None:
                units = [list(row or ["PASS"]) for row in patch["unit"]]
                if len(units) == 1 + len(action["hands"]):
                    action["farmer"], action["hands"] = units[0], units[1:]
                else:
                    state["failed"].update(patch["window_ids"])
                    action = _async_copy(base)
            if patch.get("market") is not None and not any(name in state["failed"] for name in patch["window_ids"]):
                action["market"] = [list(row) for row in patch["market"]]
    action["market"] = _async_public_market(obs, action["market"])
    return action

_async_constants()

if callable(_ASYNC_BASE_RC2_NEEDS_RELAY):
    def _async_rc2_needs_relay(state, step):
        values = dict(_ASYNC_SPEC.get("constants") or [])
        first = int(values.get("relay_first", globals().get("_RC2_RELAY_FIRST", 278)))
        last = int(values.get("relay_last", globals().get("_RC2_RELAY_LAST", 662)))
        if int(step) < first or int(step) > last:
            return False
        return _ASYNC_BASE_RC2_NEEDS_RELAY(state, step)
    globals()["_rc2_needs_relay"] = _async_rc2_needs_relay

def agent(obs, configuration=None):
    step, seat, farm, private, positions = _async_context(obs)
    state = _ASYNC_STATE[seat]
    if step == 0 or step < int(state.get("last_step", -1)):
        state = {"last_step": step, "active": set(), "failed": set()}
        _ASYNC_STATE[seat] = state
    state["last_step"] = step
    _async_window_state(step, positions, state)
    if _ASYNC_SPEC["lane"] == "boatlee_v16_rc2_market_relay":
        base = _ASYNC_BASE_AGENT(obs)
    else:
        base = _ASYNC_BASE_AGENT(obs, configuration)
    action = _async_apply(obs, base, state, positions, private)
    action = _project_atomic_plants(obs, action)
    return _project_action(action, len(_async_get(farm, "hands", []) or []))
'''


def render_runtime(candidate: CompiledAsyncCandidate) -> str:
    encoded = json.dumps(candidate.runtime_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"\n# ---- asynchronous topology candidate {candidate.candidate_id} ----\n_ASYNC_SPEC = json.loads({encoded!r})\n{RUNTIME_SOURCE.strip()}\n"


def make_fast_policy(module: Any, base_agent: Callable[..., dict], candidate: CompiledAsyncCandidate) -> Callable[..., dict]:
    module.__dict__["agent"] = base_agent
    exec(compile(render_runtime(candidate), f"<async:{candidate.candidate_id}>", "exec"), module.__dict__)
    return module.__dict__["agent"]
