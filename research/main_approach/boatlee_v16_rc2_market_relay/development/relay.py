"""Guarded, debt-accounted three-turn fertilizer relay."""

from .market import _rank_sell_slots
from .route import _REBALANCE_ACTIONS
from .runtime import _copy_action, _farm, _get, _seat

# Boatlee V16-RC2: guarded, debt-accounted inter-turn FERTILIZER relay.
_RC2_ROUTE_CHECKPOINTS = (216, 240, 264)
_RC2_ROUTE_DISTANCE_MAX = 8
_RC2_RELAY_LEAD = 3
_RC2_RELAY_FIRST = 278
_RC2_RELAY_LAST = 662
_RC2_ROUTE_STATE = {
    0: {"last_step": -1, "checks": {}, "locked": False, "due_step": -1, "due": 0},
    1: {"last_step": -1, "checks": {}, "locked": False, "due_step": -1, "due": 0},
}


def _rc2_public_signature(farm):
    counts = {
        key: 0 for key in (
            "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "COW", "SHEEP", "GOOSE", "PASTURE", "COOP", "WEED",
        )
    }
    for row in (_get(farm, "tiles", []) or []):
        for tile in row if isinstance(row, list) else [row]:
            if not isinstance(tile, dict):
                continue
            for field in ("crop", "animal", "kind"):
                value = str(tile.get(field, "")).upper()
                if value in counts:
                    counts[value] += 1
                    break
    return (
        len(_get(farm, "hands", []) or []),
        len(_get(farm, "unlocked_quadrants", []) or []),
        tuple(counts[key] for key in sorted(counts)),
    )


def _rc2_route_distance(obs):
    farms = list(_get(obs, "farms", []) or [])
    if len(farms) < 2:
        return 10**9
    left = _rc2_public_signature(farms[0])
    right = _rc2_public_signature(farms[1])
    return (
        abs(left[0] - right[0])
        + 3 * abs(left[1] - right[1])
        + sum(abs(a - b) for a, b in zip(left[2], right[2]))
    )


def _rc2_state(obs, step):
    seat = _seat(obs)
    state = _RC2_ROUTE_STATE[seat]
    if step == 0 or step < int(state.get("last_step", -1)):
        state = {
            "last_step": step,
            "checks": {},
            "locked": False,
            "due_step": -1,
            "due": 0,
        }
        _RC2_ROUTE_STATE[seat] = state
    state["last_step"] = step
    if step in _RC2_ROUTE_CHECKPOINTS and step not in state["checks"]:
        state["checks"][step] = _rc2_route_distance(obs) <= _RC2_ROUTE_DISTANCE_MAX
        if all(checkpoint in state["checks"] for checkpoint in _RC2_ROUTE_CHECKPOINTS):
            state["locked"] = all(state["checks"].values())
    return state


def _rc2_future_fertilizer_quantity(step):
    future_step = step + _RC2_RELAY_LEAD
    if not (
        _RC2_RELAY_FIRST <= step <= _RC2_RELAY_LAST
        and 281 <= future_step <= 665
        and future_step % 24 == 17
        and future_step < len(_REBALANCE_ACTIONS)
    ):
        return 0
    return sum(
        max(0, int(order[2]))
        for order in (_REBALANCE_ACTIONS[future_step].get("market") or [])
        if len(order) >= 3 and order[0] == "SELL" and order[1] == "FERTILIZER"
    )


def _rc2_repay(action, state, step):
    due_step = int(state.get("due_step", -1))
    if due_step != step:
        if due_step >= 0 and due_step < step:
            state["due_step"], state["due"] = -1, 0
        return action
    remaining_due = max(0, int(state.get("due", 0)))
    market = []
    for raw in (action.get("market") or []):
        order = list(raw)
        if (
            remaining_due > 0
            and len(order) >= 3
            and order[0] == "SELL"
            and order[1] == "FERTILIZER"
        ):
            requested = max(0, int(order[2]))
            reduction = min(requested, remaining_due)
            requested -= reduction
            remaining_due -= reduction
            if requested <= 0:
                continue
            order[2] = requested
        market.append(order)
    action["market"] = market
    state["due_step"], state["due"] = -1, 0
    return action


def _rc2_market_relay(obs, action, step, configuration):
    action = _copy_action(action)
    state = _rc2_state(obs, step)
    action = _rc2_repay(action, state, step)
    if not state.get("locked") or state.get("due", 0):
        return action
    target = _rc2_future_fertilizer_quantity(step)
    if target <= 0:
        return action
    market = [list(order) for order in (action.get("market") or [])]
    if len(market) >= 10:
        return action
    private = _get(obs, "private", {}) or {}
    shed = _get(private, "shed", {}) or {}
    available = max(0, int(_get(shed, "FERTILIZER", 0) or 0))
    for order in market:
        if len(order) >= 3 and order[0] == "SELL" and order[1] == "FERTILIZER":
            available = max(0, available - max(0, int(order[2])))
    quantity = min(target, available)
    if quantity <= 0:
        return action
    market.append(["SELL", "FERTILIZER", quantity])
    action["market"] = market[:10]
    state["due_step"] = step + _RC2_RELAY_LEAD
    state["due"] = quantity
    return _rank_sell_slots(obs, action, configuration)
