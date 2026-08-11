"""Yarn-shop-conditioned livestock conversion."""

from .runtime import _copy_action, _get, _seat

# Boatlee V16-R5B: weed-replay-safe livestock-mix controller.
_V16_NAME = 'Boatlee V16-RC2-MarketRelay'
_V16_SWITCH_STEP = 161
_V16_PURCHASE_STEPS = frozenset([192])
_V16_ACTOR_WINDOWS = [(4, 193, 212)]
_V16_ROUTE_STATE = {0: {"last_step": -1, "yarn": None}, 1: {"last_step": -1, "yarn": None}}


def _v16_yarn_route(obs, step):
    seat = _seat(obs)
    state = _V16_ROUTE_STATE[seat]
    if step == 0 or step < int(state.get("last_step", -1)):
        state = {"last_step": step, "yarn": None}
        _V16_ROUTE_STATE[seat] = state
    state["last_step"] = step
    if step < _V16_SWITCH_STEP:
        return False
    if state.get("yarn") is None:
        town = _get(obs, "town", {}) or {}
        shops = tuple(_get(town, "unlocked_shops", []) or [])
        blocked = {"SMOOTHIE_SHOP", "PIZZA_SHOP"}
        state["yarn"] = (
            "YARN_STORE" in shops
            and not any(shop in blocked for shop in shops)
        )
    return bool(state["yarn"])


def _v16_swap_cow(order):
    order = list(order or ["PASS"])
    if len(order) >= 2 and order[1] == "COW":
        order[1] = "SHEEP"
    return order


def _v16_convert_livestock(action, obs, step):
    action = _copy_action(action)
    if not _v16_yarn_route(obs, step):
        return action
    if step in _V16_PURCHASE_STEPS:
        action["market"] = [_v16_swap_cow(order) for order in (action.get("market") or [])]
    hands = [list(order or ["PASS"]) for order in (action.get("hands") or [])]
    for actor, start, end in _V16_ACTOR_WINDOWS:
        if int(start) <= step <= int(end) and int(actor) < len(hands):
            hands[int(actor)] = _v16_swap_cow(hands[int(actor)])
    action["hands"] = hands
    return action
