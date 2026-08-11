"""Readable route data loader used only by the development tree."""

import json
from pathlib import Path


ROUTE_PATH = Path(__file__).with_name("route_actions.json")


def _load_route():
    actions = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
    if len(actions) != 719:
        raise ValueError(f"expected 719 route actions, got {len(actions)}")
    return actions


_LEGACY_ACTIONS = _load_route()
_REBALANCE_ACTIONS = _LEGACY_ACTIONS
