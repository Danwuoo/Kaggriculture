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
    for step, action in enumerate(actions):
        hands = action.get("hands", []) or []
        hand_counts.append(len(hands))
        unit_actions = [action.get("farmer", ["PASS"]), *hands]
        if any(order and order[0] in ("BUILD_PASTURE", "PLANT") for order in unit_actions):
            weed_steps.append(step)
        sells = sum(
            bool(len(order) >= 3 and order[0] == "SELL")
            for order in (action.get("market", []) or [])
        )
        if sells >= 2:
            multi_sell_steps.append(step)
    return tuple(hand_counts), frozenset(weed_steps), frozenset(multi_sell_steps)


_LEGACY_ACTIONS = _load_route()
_REBALANCE_ACTIONS = _LEGACY_ACTIONS
_ROUTE_HAND_COUNTS, _WEED_CANDIDATE_STEPS, _MULTI_SELL_STEPS = _route_metadata(_LEGACY_ACTIONS)
