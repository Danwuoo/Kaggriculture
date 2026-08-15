"""Small self-contained candidate runtime overlay.

The renderer embeds this code with a canonical payload in a finalist only.  It
has no filesystem, network, process, or logging dependency.
"""

from __future__ import annotations

from typing import Any

from model import CompiledCandidate
from registry import default_min_price, market_order_cap


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    return getter(key, default) if callable(getter) else getattr(value, key, default)


def copy_action(action: Any, hand_count: int) -> dict[str, Any]:
    action = action if isinstance(action, dict) else {}
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(row or ["PASS"]) for row in list(action.get("hands") or [])[:hand_count]],
        "market": [list(row or []) for row in list(action.get("market") or [])[:10]],
    }


def atomic_plant_projection(obs: Any, action: dict[str, Any]) -> dict[str, Any]:
    """Apply engine-equivalent atomic same-crop planting only when readable."""
    private = _get(obs, "private", None)
    seeds = _get(private, "seeds", None)
    if not isinstance(seeds, dict):
        return action
    requested: dict[str, int] = {}
    for order in [action.get("farmer"), *(action.get("hands") or [])]:
        if isinstance(order, list) and len(order) >= 2 and order[0] == "PLANT":
            crop = str(order[1])
            requested[crop] = requested.get(crop, 0) + 1
    blocked = {crop for crop, count in requested.items() if count > int(seeds.get(crop, 0) or 0)}
    if not blocked:
        return action
    result = copy_action(action, len(action.get("hands") or []))
    if len(result["farmer"]) >= 2 and result["farmer"][0] == "PLANT" and str(result["farmer"][1]) in blocked:
        result["farmer"] = ["PASS"]
    result["hands"] = [
        ["PASS"] if len(row) >= 2 and row[0] == "PLANT" and str(row[1]) in blocked else row
        for row in result["hands"]
    ]
    return result


def final_project(obs: Any, action: Any) -> dict[str, Any]:
    seat = 1 if int(_get(obs, "player", 0) or 0) == 1 else 0
    farms = _get(obs, "farms", []) or []
    farm = farms[seat] if seat < len(farms) and isinstance(farms[seat], dict) else {}
    return copy_action(action, len(_get(farm, "hands", []) or []))


def _guard_allows(guard: dict[str, Any] | None, obs: Any) -> tuple[bool, str]:
    if guard is None:
        return True, "queued"
    market = _get(obs, "market", None)
    if not isinstance(market, dict):
        return False, "missing_public_market"
    product = str(guard["product"])
    prices = _get(market, "prices", {}) or {}
    inventory = _get(market, "inventory", {}) or {}
    if guard["kind"] in {"min_price", "max_price"}:
        if product not in prices:
            return False, "missing_public_price"
        actual = int(prices[product])
        return ((actual >= int(guard["threshold"])), "price_below_guard") if guard["kind"] == "min_price" else ((actual <= int(guard["threshold"])), "price_above_guard")
    if product not in inventory:
        return False, "missing_public_inventory"
    actual = int(inventory[product])
    return ((actual >= int(guard["threshold"])), "inventory_below_guard") if guard["kind"] == "min_inventory" else ((actual <= int(guard["threshold"])), "inventory_above_guard")


def apply_candidate_action(candidate: CompiledCandidate, obs: Any, base_action: Any) -> dict[str, Any]:
    """Return candidate action plus planned, not engine-claimed, receipts."""
    farms = _get(obs, "farms", None)
    private = _get(obs, "private", None)
    step = _get(obs, "step", None)
    if not isinstance(farms, list) or not isinstance(private, dict) or step is None:
        return {"action": final_project(obs, base_action), "receipts": [], "fallback": "missing_current_or_private_state"}
    action = final_project(obs, base_action)
    values = dict(candidate.constants)
    minimum = default_min_price(candidate.lane, values)
    public = _get(obs, "market", None)
    if minimum and (not isinstance(public, dict) or not isinstance(_get(public, "prices", None), dict)):
        return {"action": final_project(obs, base_action), "receipts": [], "fallback": "missing_public_state_for_live_constant"}
    patch = next((row for row in candidate.patches if int(row["step"]) == int(step)), None)
    receipts: list[dict[str, Any]] = []
    if patch is not None:
        chosen: list[list[Any]] = []
        for index, entry in enumerate(patch["market_entries"]):
            allowed, reason = _guard_allows(entry.get("guard"), obs)
            order = list(entry["order"])
            if allowed and entry.get("guard") is None and len(order) >= 3 and order[0] in {"SELL", "BUY_PRODUCT"}:
                if order[0] == "SELL" and minimum:
                    price = _get(_get(obs, "market", {}), "prices", {}).get(order[1]) if isinstance(_get(obs, "market", {}), dict) else None
                    if price is None or int(price) < minimum:
                        allowed, reason = False, "default_min_price_guard"
            receipts.append({
                "step": int(step), "queue_index": index, "planned_order": order,
                "executed": False, "reason": reason if not allowed else "queued",
                "money_before": _get((farms[1 if int(_get(obs, "player", 0) or 0) == 1 else 0] if farms else {}), "money", None),
                "public_inventory_before": _get(_get(_get(obs, "market", {}), "inventory", {}), order[1], None) if len(order) >= 2 else None,
                "public_price_before": _get(_get(_get(obs, "market", {}), "prices", {}), order[1], None) if len(order) >= 2 else None,
            })
            if allowed:
                chosen.append(order)
        action["market"] = chosen[: min(10, market_order_cap(candidate.lane, dict(candidate.constants)))]
    else:
        action["market"] = action["market"][: min(10, market_order_cap(candidate.lane, dict(candidate.constants)))]
    if minimum:
        prices = _get(public, "prices", {}) or {}
        action["market"] = [row for row in action["market"] if not (len(row) >= 3 and row[0] == "SELL" and int(prices.get(row[1], -1)) < minimum)]
    action = atomic_plant_projection(obs, action)
    action = final_project(obs, action)  # final legality/schema boundary before return
    return {"action": action, "receipts": receipts, "fallback": None}
