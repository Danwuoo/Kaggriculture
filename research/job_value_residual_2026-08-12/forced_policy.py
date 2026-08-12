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
    previous_observation: Mapping[str, Any] | None = None,
    previous_order: tuple[str, ...] | None = None,
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
        if _retired_requirement(
            requirement, window, observation, previous_observation, previous_order
        ):
            continue
        actual = _requirement_value(requirement, observation)
        if actual is None or not _compare(actual, requirement.operator, requirement.value):
            return False
    return True


def _retired_requirement(
    requirement: Requirement,
    window: CandidateWindow,
    observation: Mapping[str, Any],
    previous_observation: Mapping[str, Any] | None,
    previous_order: tuple[str, ...] | None,
) -> bool:
    """Retire only a requirement whose exact input was consumed last turn."""
    if previous_observation is None or previous_order is None:
        return False
    if requirement.field == "actor_inventory" and previous_order[:1] == ("DROP",):
        if len(requirement.key) != 2 or int(requirement.key[0]) != window.actor:
            return False
        before = _requirement_value(requirement, previous_observation)
        after = _requirement_value(requirement, observation)
        return isinstance(before, (int, float)) and isinstance(after, (int, float)) and after < before
    if requirement.field in {"tile_kind", "tile_product", "tile_yield"} and previous_order[:1] == ("HARVEST",):
        if len(requirement.key) != 2 or _actor_position(previous_observation, window.actor) != tuple(requirement.key):
            return False
        before_tile = _tile(previous_observation, requirement.key)
        after_tile = _tile(observation, requirement.key)
        if before_tile is None:
            return False
        before_yield = before_tile.get("yield_units")
        after_yield = after_tile.get("yield_units") if after_tile else None
        return after_tile is None or (
            isinstance(before_yield, (int, float))
            and isinstance(after_yield, (int, float))
            and after_yield < before_yield
        )
    return False


def _requirement_identity(requirement: Requirement) -> str:
    return f"{requirement.field}:{':'.join(map(str, requirement.key))}"


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
            "sell_rejected_reason": None,
            "abort_reason": None,
            "failed_precondition": None,
            "expected_rejoin_position": list(window.expected_positions[-1]),
            "observed_rejoin_position": None,
            "last_forced_step": None,
            "last_observation": None,
            "last_order": None,
            "retired_preconditions": [],
        }

        def wrapped(observation: Mapping[str, Any], configuration: Any = None) -> dict:
            base = _call_incumbent(incumbent, observation, configuration)
            step = observation.get("step")
            if not isinstance(step, int):
                return base
            if metadata["status"] == "pending" and step > window.trigger_step:
                metadata.update(status="aborted", abort_step=step, abort_reason="interior_start")
                return base
            if step < window.trigger_step or step > window.rejoin_step:
                return base
            if step == window.rejoin_step:
                if metadata["status"] in {"active", "forced"}:
                    observed = _actor_position(observation, window.actor)
                    metadata["observed_rejoin_position"] = None if observed is None else list(observed)
                    if observed == window.expected_positions[-1]:
                        metadata["status"] = "rejoined"
                    else:
                        metadata.update(status="failed_rejoin", abort_reason="failed_rejoin")
                return base
            offset = step - window.trigger_step
            if metadata["status"] not in {"pending", "active", "forced"}:
                return base
            if metadata["last_forced_step"] is not None and step != metadata["last_forced_step"] + 1:
                metadata.update(status="aborted", abort_step=step, abort_reason="step_gap")
                return base
            failed_requirement = None
            for requirement in window.requirements:
                identity = _requirement_identity(requirement)
                if identity in metadata["retired_preconditions"]:
                    continue
                single_requirement = CandidateWindow(
                    window.candidate_id, window.incumbent, window.family,
                    window.trigger_step, window.actor, window.rejoin_step,
                    window.actions, window.expected_positions, (requirement,),
                    window.sell_directives, window.displaced_actions,
                    window.touched_tiles, window.effects,
                )
                if _retired_requirement(
                    requirement, window, observation, metadata["last_observation"], metadata["last_order"],
                ):
                    metadata["retired_preconditions"].append(identity)
                    continue
                if not requirements_hold(
                    single_requirement, observation, offset=offset,
                    previous_observation=metadata["last_observation"], previous_order=metadata["last_order"],
                ):
                    failed_requirement = requirement
                    break
            if (
                offset < 0
                or offset >= len(window.actions)
                or _actor_position(observation, window.actor) != window.expected_positions[offset]
                or failed_requirement is not None
            ):
                metadata.update(
                    status="aborted", abort_step=step,
                    abort_reason="position_mismatch" if failed_requirement is None else "precondition_failed",
                    failed_precondition=None if failed_requirement is None else _requirement_identity(failed_requirement),
                )
                return base
            try:
                changed = apply_actor_action(base, window.actor, window.actions[offset])
            except ValueError:
                metadata.update(status="aborted", abort_step=step, abort_reason="actor_absent")
                return base
            directives = [item for item in window.sell_directives if item.offset == offset]
            if len(directives) > 1:
                metadata.update(status="aborted", abort_step=step, abort_reason="multiple_sell_directives")
                return base
            if directives:
                directive = directives[0]
                available = _available_for_sell(observation, base, window.actor, window.actions[offset], directive)
                if len(changed["market"]) >= 10:
                    metadata.update(sell_rejected=True, sell_rejected_reason="market_cap")
                elif available == directive.quantity:
                    changed["market"].append(["SELL", directive.product, directive.quantity])
                    metadata["applied_sell_quantity"] += directive.quantity
                else:
                    metadata.update(sell_rejected=True, sell_rejected_reason="insufficient_shed")
            metadata["status"] = "forced"
            metadata["applied_steps"].append(step)
            metadata["applied_actions"].append(list(window.actions[offset]))
            metadata["last_forced_step"] = step
            metadata["last_observation"] = deepcopy(observation)
            metadata["last_order"] = tuple(window.actions[offset])
            return changed

        wrapped.metadata = metadata  # type: ignore[attr-defined]
        return wrapped

    return factory
