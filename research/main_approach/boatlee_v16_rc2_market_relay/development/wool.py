"""Inventory- and price-aware wool release."""

from .route import _WOOL_SELL_STEPS
from .runtime import _get

# Boatlee V16-R6: inventory- and price-aware WOOL release for YARN_STORE.
_V16_WOOL_GATES = ((480, 170), (600, 120), (672, 80), (719, 1))
_V16_WOOL_PRESSURE = 78
_V16_WOOL_BATCH = 16
_V16_WOOL_GAP = 6
_V16_WOOL_STATE = {0: {"last_sale": -1000}, 1: {"last_sale": -1000}}


def _v16_wool_reset(seat):
    state = {"last_sale": -1000}
    _V16_WOOL_STATE[seat] = state
    return state


def _v16_wool_gate(step):
    for end_step, gate in _V16_WOOL_GATES:
        if step < int(end_step):
            return int(gate)
    return 1


def _v16_wool_controller(action, obs, step, seat, yarn):
    if not yarn:
        return action
    state = _V16_WOOL_STATE[seat]
    if step in _WOOL_SELL_STEPS:
        return action
    market_orders = [list(order) for order in (action.get("market") or [])]
    private = _get(obs, "private", {}) or {}
    shed = _get(private, "shed", {}) or {}
    wool = max(0, int(_get(shed, "WOOL", 0) or 0))
    if wool <= 0 or len(market_orders) >= 10:
        return action
    total = sum(max(0, int(value or 0)) for value in shed.values())
    market = _get(obs, "market", {}) or {}
    prices = _get(market, "prices", {}) or {}
    price = max(0, int(_get(prices, "WOOL", 0) or 0))
    terminal = step >= 713
    pressure = total >= _V16_WOOL_PRESSURE
    price_ok = price >= _v16_wool_gate(step)
    gap_ok = step - int(state.get("last_sale", -1000)) >= _V16_WOOL_GAP
    if not terminal and not pressure and (not price_ok or not gap_ok):
        return action
    quantity = wool if terminal else min(wool, _V16_WOOL_BATCH)
    if pressure:
        quantity = min(wool, max(quantity, total - (_V16_WOOL_PRESSURE - 12)))
    market_orders.append(["SELL", "WOOL", max(1, int(quantity))])
    action["market"] = market_orders[:10]
    state["last_sale"] = step
    return action
