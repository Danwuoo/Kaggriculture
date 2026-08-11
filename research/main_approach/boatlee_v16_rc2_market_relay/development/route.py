"""Readable route data loader used only by the development tree."""

import json
from pathlib import Path


ROUTE_PATH = Path(__file__).with_name("route_actions.json")


def _load_route():
    actions = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
    if len(actions) != 719:
        raise ValueError(f"expected 719 route actions, got {len(actions)}")
    return actions


def _route_metadata(actions):
    hand_counts = []
    weed_steps = []
    multi_sell_steps = []
    livestock_steps = []
    wool_sell_steps = []
    relay_targets = {}
    for step, action in enumerate(actions):
        hands = action.get("hands", []) or []
        market = action.get("market", []) or []
        hand_counts.append(len(hands))
        unit_actions = [action.get("farmer", ["PASS"]), *hands]
        if any(order and order[0] in ("BUILD_PASTURE", "PLANT") for order in unit_actions):
            weed_steps.append(step)
        if sum(bool(len(order) >= 3 and order[0] == "SELL") for order in market) >= 2:
            multi_sell_steps.append(step)
        if any(len(order) >= 2 and order[1] == "COW" for order in [*hands, *market]):
            livestock_steps.append(step)
        if any(len(order) >= 2 and order[0] == "SELL" and order[1] == "WOOL" for order in market):
            wool_sell_steps.append(step)
    for step in range(len(actions)):
        future_step = step + 3
        if not (278 <= step <= 662 and 281 <= future_step <= 665 and future_step % 24 == 17):
            continue
        quantity = sum(
            max(0, int(order[2]))
            for order in (actions[future_step].get("market", []) or [])
            if len(order) >= 3 and order[0] == "SELL" and order[1] == "FERTILIZER"
        )
        if quantity:
            relay_targets[step] = quantity
    return (
        tuple(hand_counts), frozenset(weed_steps), frozenset(multi_sell_steps),
        frozenset(livestock_steps), frozenset(wool_sell_steps), relay_targets,
    )


_LEGACY_ACTIONS = _load_route()
_REBALANCE_ACTIONS = _LEGACY_ACTIONS
(
    _ROUTE_HAND_COUNTS,
    _WEED_CANDIDATE_STEPS,
    _MULTI_SELL_STEPS,
    _LIVESTOCK_ROUTE_STEPS,
    _WOOL_SELL_STEPS,
    _RELAY_TARGET_QUANTITIES,
) = _route_metadata(_LEGACY_ACTIONS)
_RELAY_CHECKPOINT_STEPS = frozenset((216, 240, 264))
