"""Reversible fertilizer-relay interventions around Boatlee V16-RC2."""

from __future__ import annotations

import copy
from typing import Any, Callable

from graph_model import graph_features


TRIGGER_STEPS = tuple(range(278, 663, 24))


def _seat(obs: dict) -> int:
    return int(obs.get("player", 0) or 0)


def _relay_state(module: Any, obs: dict, step: int) -> dict:
    return module._RC2_ROUTE_STATE[_seat(obs)]


def _remove_fertilizer_sale(action: dict, quantity: int) -> dict:
    action = copy.deepcopy(action)
    remaining = max(0, int(quantity))
    market = [list(order) for order in (action.get("market", []) or [])]
    for index in range(len(market) - 1, -1, -1):
        order = market[index]
        if remaining <= 0:
            break
        if len(order) < 3 or order[0] != "SELL" or order[1] != "FERTILIZER":
            continue
        available = max(0, int(order[2]))
        reduction = min(available, remaining)
        remaining -= reduction
        available -= reduction
        if available:
            order[2] = available
        else:
            market.pop(index)
    action["market"] = market
    return action


def _block(module: Any, obs: dict, action: dict, step: int) -> tuple[dict, int]:
    state = _relay_state(module, obs, step)
    if int(state.get("due_step", -1)) != step + module._RC2_RELAY_LEAD:
        return action, 0
    quantity = max(0, int(state.get("due", 0)))
    if quantity <= 0:
        return action, 0
    action = _remove_fertilizer_sale(action, quantity)
    state["due_step"], state["due"] = -1, 0
    return action, quantity


def _force(module: Any, obs: dict, action: dict, step: int) -> tuple[dict, int]:
    state = _relay_state(module, obs, step)
    if int(state.get("due_step", -1)) == step + module._RC2_RELAY_LEAD:
        return action, max(0, int(state.get("due", 0)))
    target = max(0, int(module._rc2_future_fertilizer_quantity(step)))
    if target <= 0:
        return action, 0
    action = copy.deepcopy(action)
    market = [list(order) for order in (action.get("market", []) or [])]
    if len(market) >= 10:
        return action, 0
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    available = max(0, int(shed.get("FERTILIZER", 0) or 0))
    for order in market:
        if len(order) >= 3 and order[0] == "SELL" and order[1] == "FERTILIZER":
            available -= max(0, int(order[2]))
    quantity = min(target, max(0, available))
    if quantity <= 0:
        return action, 0
    market.append(["SELL", "FERTILIZER", quantity])
    action["market"] = market[:10]
    state["due_step"], state["due"] = step + module._RC2_RELAY_LEAD, quantity
    return module._rank_sell_slots(obs, action, module._V16_OFFICIAL_CONFIGURATION), quantity


def intervention_factory(mode: str, target_step: int | None = None, model: Any | None = None):
    """Create a runner factory for force, block, GCN, or flat-MLP policy."""

    if mode not in {"force", "block", "model"}:
        raise ValueError(mode)

    def factory(module: Any, base_agent: Callable[..., dict], seat: int):
        metadata: dict[str, Any] = {
            "mode": mode,
            "target_step": target_step,
            "decisions": [],
            "intervention_quantity": 0,
            "snapshot": None,
        }

        def policy(obs: dict, configuration: Any = None) -> dict:
            step = int(obs.get("step", 0) or 0)
            action = base_agent(obs)
            eligible = step in TRIGGER_STEPS and (target_step is None or step == target_step)
            if not eligible:
                return action
            x = graph_features(obs)
            metadata["snapshot"] = x.tolist()
            selected = mode
            prediction = None
            if mode == "model":
                prediction = float(model.predict(x)[0])
                selected = "force" if prediction > 0.0 else "block"
            if selected == "force":
                action, quantity = _force(module, obs, action, step)
            else:
                action, quantity = _block(module, obs, action, step)
            metadata["intervention_quantity"] += int(quantity)
            metadata["decisions"].append(
                {"step": step, "choice": selected, "prediction": prediction, "quantity": int(quantity)}
            )
            return action

        policy.metadata = metadata
        return policy

    return factory
