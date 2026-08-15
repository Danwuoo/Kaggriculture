"""Single canonical live-domain registry shared by compiler and runtime."""

from __future__ import annotations

from typing import Any

from model import LANES


# Each value names a real runtime decision point.  No compiler-local default is
# allowed: registry/default/domain lookups all come from this table.
LIVE_CONSTANTS: dict[str, dict[str, dict[str, Any]]] = {
    "v27_current_meta": {
        "v27_market_order_cap": {"domain": (4, 6, 8, 10), "default": 10, "target": "runtime.market_order_cap"},
        "v27_guard_min_price": {"domain": (0, 25, 50, 75, 100), "default": 0, "target": "runtime.default_min_price"},
    },
    "boatlee_v16_rc2_market_relay": {
        "boatlee_market_order_cap": {"domain": (4, 6, 8, 10), "default": 10, "target": "runtime.market_order_cap"},
        "boatlee_guard_min_price": {"domain": (0, 25, 50, 75, 100), "default": 0, "target": "runtime.default_min_price"},
    },
}


def lane_registry(lane: str) -> dict[str, dict[str, Any]]:
    if lane not in LANES:
        raise ValueError(lane)
    return LIVE_CONSTANTS[lane]


def validate_constant(lane: str, name: str, value: int) -> None:
    row = lane_registry(lane).get(name)
    if row is None or int(value) not in row["domain"]:
        raise ValueError(f"constant is not live in {lane}: {name}={value}")


def constant_values(lane: str, rows: tuple[tuple[str, int], ...] | tuple[Any, ...]) -> dict[str, int]:
    result = {name: int(spec["default"]) for name, spec in lane_registry(lane).items()}
    for row in rows:
        name, value = (row.name, row.value) if hasattr(row, "name") else row
        validate_constant(lane, str(name), int(value))
        result[str(name)] = int(value)
    return result


def market_order_cap(lane: str, values: dict[str, int]) -> int:
    return int(values[f"{'v27' if lane == 'v27_current_meta' else 'boatlee'}_market_order_cap"])


def default_min_price(lane: str, values: dict[str, int]) -> int:
    return int(values[f"{'v27' if lane == 'v27_current_meta' else 'boatlee'}_guard_min_price"])
