"""Observation and action normalization helpers."""

_LAST_STEP = [-1, -1]

def _get(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(value, key, default)


def _regime(configuration):
    interval = int(_get(configuration, "townCenterSellInterval", 12) or 12)
    return "rebalance" if interval >= 24 else "legacy"


def _copy_action(action):
    action = action if isinstance(action, dict) else {}
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(order or ["PASS"]) for order in (action.get("hands") or [])],
        "market": [list(order) for order in (action.get("market") or [])],
    }


def _runtime_context(obs, last_route_step):
    if isinstance(obs, dict):
        step = min(max(0, int(obs.get("step", 0) or 0)), last_route_step)
        seat = 1 if int(obs.get("player", 0) or 0) == 1 else 0
        farms = obs.get("farms", []) or []
    else:
        step = min(max(0, int(_get(obs, "step", 0) or 0)), last_route_step)
        seat = _seat(obs)
        farms = _get(obs, "farms", []) or []
    farm = farms[seat] if seat < len(farms) else {}
    hands = farm.get("hands", []) if isinstance(farm, dict) else (_get(farm, "hands", []) or [])
    reset = step == 0 or step < _LAST_STEP[seat]
    _LAST_STEP[seat] = step
    return step, seat, farm, len(hands or []), reset


def _project_action(action, expected_hands):
    """Final schema/alignment boundary; valid materialized actions pass through."""
    if isinstance(action, dict):
        farmer = action.get("farmer")
        hands = action.get("hands")
        market = action.get("market")
        if (
            isinstance(farmer, list)
            and isinstance(hands, list)
            and len(hands) == expected_hands
            and all(isinstance(order, list) and order for order in hands)
            and isinstance(market, list)
            and all(isinstance(order, list) for order in market)
        ):
            return action
    action = _copy_action(action)
    hands = action["hands"]
    if len(hands) < expected_hands:
        hands.extend([["PASS"] for _ in range(expected_hands - len(hands))])
    action["hands"] = hands[:expected_hands]
    return action


def _project_atomic_plants(obs, action):
    """Mirror the engine's same-crop atomic PLANT cancellation when observable."""
    private = _get(obs, "private", None)
    if private is None:
        return action
    seeds = _get(private, "seeds", None)
    if seeds is None:
        return action
    farmer = action.get("farmer") if isinstance(action, dict) else None
    hands = action.get("hands") if isinstance(action, dict) else None
    if not isinstance(farmer, list) or not isinstance(hands, list):
        return action
    units = [farmer, *hands]
    demand = {}
    for order in units:
        if isinstance(order, list) and len(order) >= 2 and order[0] == "PLANT":
            crop = str(order[1])
            demand[crop] = demand.get(crop, 0) + 1
    if not demand:
        return action
    available = {}
    for crop in demand:
        raw = _get(seeds, crop, None)
        if raw is None:
            return action
        try:
            available[crop] = max(0, int(raw))
        except (TypeError, ValueError):
            return action
    blocked = {crop for crop, count in demand.items() if count > available[crop]}
    if not blocked:
        return action
    projected = _copy_action(action)
    projected_units = [projected["farmer"], *projected["hands"]]
    projected_units = [
        ["PASS"]
        if isinstance(order, list)
        and len(order) >= 2
        and order[0] == "PLANT"
        and str(order[1]) in blocked
        else order
        for order in projected_units
    ]
    projected["farmer"] = projected_units[0]
    projected["hands"] = projected_units[1:]
    return projected


def _seat(obs):
    return 1 if int(_get(obs, "player", 0) or 0) == 1 else 0


def _farm(obs, seat):
    farms = list(_get(obs, "farms", []) or [])
    return farms[seat] if seat < len(farms) else {}


def _align_hands(action, obs):
    expected = len(_get(_farm(obs, _seat(obs)), "hands", []) or [])
    return _project_action(action, expected)


def _tile_at(farm, position):
    try:
        x, y = int(position[0]), int(position[1])
        return (_get(farm, "tiles", []) or [])[y][x]
    except (IndexError, TypeError, ValueError):
        return "LOCKED"


def _trace_actor_action(actions, step, actor):
    trace = actions[min(max(int(step), 0), len(actions) - 1)] or {}
    if actor == "farmer":
        return list(trace.get("farmer") or ["PASS"])
    hands = trace.get("hands", []) or []
    return list(hands[actor] if actor < len(hands) else ["PASS"])
