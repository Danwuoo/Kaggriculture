"""Fail-closed, single-actor wrappers for offline counterfactual windows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

from schema import CandidateWindow, Requirement, SellDirective


SHED_TILES = frozenset(((4, 4), (5, 4), (4, 5), (5, 5)))


def _nonnegative(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _own_farm(observation: Mapping[str, Any]) -> Mapping[str, Any] | None:
    farms = observation.get("farms")
    player = observation.get("player")
    if not isinstance(farms, list) or not isinstance(player, int) or not (0 <= player < len(farms)):
        return None
    farm = farms[player]
    return farm if isinstance(farm, Mapping) else None


def _actor_position(observation: Mapping[str, Any], actor: int) -> tuple[int, int] | None:
    farm = _own_farm(observation)
    if farm is None:
        return None
    raw = farm.get("farmer") if actor == 0 else (farm.get("hands") or [])[actor - 1] if actor - 1 < len(farm.get("hands") or []) else None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        return int(raw[0]), int(raw[1])
    except (TypeError, ValueError):
        return None


def _tile(observation: Mapping[str, Any], key: tuple[Any, ...]) -> Mapping[str, Any] | None:
    if len(key) != 2:
        return None
    try:
        x, y = int(key[0]), int(key[1])
    except (TypeError, ValueError):
        return None
    farm = _own_farm(observation)
    tiles = farm.get("tiles") if farm else None
    if not isinstance(tiles, list) or y < 0 or y >= len(tiles) or not isinstance(tiles[y], list) or x < 0 or x >= len(tiles[y]):
        return None
    item = tiles[y][x]
    return item if isinstance(item, Mapping) else None


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    try:
        if operator == "eq":
            return actual == expected
        if operator == "ge":
            return actual >= expected
        if operator == "le":
            return actual <= expected
    except TypeError:
        pass
    return False


def _requirement_value(requirement: Requirement, observation: Mapping[str, Any]) -> Any:
    farm = _own_farm(observation)
    private = observation.get("private") if isinstance(observation.get("private"), Mapping) else {}
    if requirement.field == "hands":
        return len(farm.get("hands") or []) if farm else None
    if requirement.field == "money":
        return farm.get("money") if farm else None
    if requirement.field == "actor_position" and len(requirement.key) == 1:
        try:
            return _actor_position(observation, int(requirement.key[0]))
        except (TypeError, ValueError):
            return None
    if requirement.field.startswith("tile_"):
        tile = _tile(observation, requirement.key)
        if tile is None:
            return None
        return {
            "tile_kind": tile.get("kind"),
            "tile_product": tile.get("crop") or ({"COW": "MILK", "SHEEP": "WOOL"}.get(tile.get("animal"))),
            "tile_yield": tile.get("yield_units"),
        }.get(requirement.field)
    if requirement.field == "actor_inventory" and len(requirement.key) == 2:
        try:
            actor = int(requirement.key[0])
        except (TypeError, ValueError):
            return None
        product = str(requirement.key[1])
        inventories = private.get("inventories") or []
        if actor < 0 or actor >= len(inventories) or not isinstance(inventories[actor], Mapping):
            return None
        return inventories[actor].get(product)
    if requirement.field == "shed" and len(requirement.key) == 1:
        shed = private.get("shed") or {}
        return shed.get(str(requirement.key[0])) if isinstance(shed, Mapping) else None
    return None


def requirements_hold(
    window: CandidateWindow,
    observation: Mapping[str, Any],
    *,
    offset: int = 0,
) -> bool:
    """Return false for missing/malformed data rather than improvising a window."""
    for requirement in window.requirements:
        # The wrapper independently checks the offset-specific declared position.
        # A mined ``actor_position`` requirement describes its trigger anchor,
        # so evaluating it again after an intentional MOVE would self-abort.
        if requirement.field == "actor_position" and offset:
            continue
        # A delivery consumes its declared carried input.  Requiring that same
        # input on the turn after a successful DROP would turn a legal local
        # route into a false failed-precondition extension.
        if requirement.field == "actor_inventory" and any(
            action[:1] == ("DROP",) for action in window.actions[:offset]
        ):
            continue
        # Likewise, a harvested tile is no longer required to retain the yield
        # that was explicitly consumed by the prior forced action.
        if requirement.field in {"tile_kind", "tile_product", "tile_yield"} and any(
            action[:1] == ("HARVEST",) for action in window.actions[:offset]
        ):
            continue
        actual = _requirement_value(requirement, observation)
        if actual is None or not _compare(actual, requirement.operator, requirement.value):
            return False
    return True


def apply_actor_action(action: Mapping[str, Any], actor: int, order: tuple[str, ...]) -> dict[str, list[Any]]:
    """Copy a complete incumbent action and replace exactly one unit directive."""
    changed: dict[str, list[Any]] = {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(item or ["PASS"]) for item in action.get("hands", []) or []],
        "market": [list(item) for item in action.get("market", []) or []],
    }
    if actor == 0:
        changed["farmer"] = list(order)
    elif 0 < actor <= len(changed["hands"]):
        changed["hands"][actor - 1] = list(order)
    else:
        raise ValueError("actor is absent from incumbent action")
    return changed


def _available_for_sell(
    observation: Mapping[str, Any], action: Mapping[str, Any], actor: int, override: tuple[str, ...], directive: SellDirective,
) -> int:
    private = observation.get("private") if isinstance(observation.get("private"), Mapping) else {}
    shed = private.get("shed") if isinstance(private.get("shed"), Mapping) else {}
    available = _nonnegative(shed.get(directive.product, 0))
    if override[:1] == ("DROP",) and _actor_position(observation, actor) in SHED_TILES:
        inventories = private.get("inventories") if isinstance(private.get("inventories"), list) else []
        if 0 <= actor < len(inventories) and isinstance(inventories[actor], Mapping):
            available += _nonnegative(inventories[actor].get(directive.product, 0))
    for order in action.get("market", []) or []:
        if isinstance(order, (list, tuple)) and len(order) >= 3 and order[0] == "SELL" and order[1] == directive.product:
            available -= _nonnegative(order[2])
    return max(0, available)


def _call_incumbent(policy: Callable[..., dict], observation: Mapping[str, Any], configuration: Any) -> dict:
    try:
        action = policy(observation, configuration)
    except TypeError:
        action = policy(observation)
    return deepcopy(action) if isinstance(action, dict) else {"farmer": ["PASS"], "hands": [], "market": []}


def make_forced_factory(window: CandidateWindow) -> Callable[[Any, Callable[..., dict], int], Callable[..., dict]]:
    """Build a policy factory that can modify only ``window.actor`` in its interval."""
    def factory(module: Any, incumbent: Callable[..., dict], seat: int) -> Callable[..., dict]:
        del module, seat
        metadata: dict[str, Any] = {
            "candidate_id": window.candidate_id,
            "status": "pending",
            "applied_steps": [],
            "applied_actions": [],
            "abort_step": None,
            "rejoin_step": window.rejoin_step,
            "applied_sell_quantity": 0,
            "sell_rejected": False,
        }

        def wrapped(observation: Mapping[str, Any], configuration: Any = None) -> dict:
            base = _call_incumbent(incumbent, observation, configuration)
            step = observation.get("step")
            if not isinstance(step, int):
                return base
            if step < window.trigger_step or step > window.rejoin_step:
                return base
            if step == window.rejoin_step:
                if metadata["status"] in {"active", "forced"}:
                    if _actor_position(observation, window.actor) == window.expected_positions[-1]:
                        metadata["status"] = "rejoined"
                    else:
                        metadata["status"] = "failed_rejoin"
                return base
            offset = step - window.trigger_step
            if metadata["status"] not in {"pending", "active", "forced"}:
                return base
            if (
                offset < 0
                or offset >= len(window.actions)
                or _actor_position(observation, window.actor) != window.expected_positions[offset]
                or not requirements_hold(window, observation, offset=offset)
            ):
                metadata["status"] = "aborted"
                metadata["abort_step"] = step
                return base
            try:
                changed = apply_actor_action(base, window.actor, window.actions[offset])
            except ValueError:
                metadata["status"] = "aborted"
                metadata["abort_step"] = step
                return base
            directives = [item for item in window.sell_directives if item.offset == offset]
            if len(directives) > 1:
                metadata["status"] = "aborted"
                metadata["abort_step"] = step
                return base
            if directives:
                directive = directives[0]
                available = _available_for_sell(observation, base, window.actor, window.actions[offset], directive)
                if available == directive.quantity:
                    changed["market"].append(["SELL", directive.product, directive.quantity])
                    metadata["applied_sell_quantity"] += directive.quantity
                else:
                    metadata["sell_rejected"] = True
            metadata["status"] = "forced"
            metadata["applied_steps"].append(step)
            metadata["applied_actions"].append(list(window.actions[offset]))
            return changed

        wrapped.metadata = metadata  # type: ignore[attr-defined]
        return wrapped

    return factory
