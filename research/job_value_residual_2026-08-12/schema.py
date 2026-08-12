"""Stable, JSON-friendly records for bounded offline residual windows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping


@dataclass(frozen=True)
class Requirement:
    field: str
    key: tuple[Any, ...]
    operator: str
    value: Any


@dataclass(frozen=True)
class SellDirective:
    offset: int
    product: str
    quantity: int


@dataclass(frozen=True)
class MarketShift:
    product: str
    quantity: int
    control_offset: int
    candidate_offset: int
    provenance: str
    control_receipt: float | None = None
    candidate_receipt: float | None = None


@dataclass(frozen=True)
class HorizonEffect:
    horizon: int
    cash_coins: float
    liquidatable: tuple[tuple[str, int, str], ...]
    asset: tuple[tuple[str, int, str], ...]
    capacity: tuple[tuple[str, int, str], ...]
    market: tuple[MarketShift, ...]
    context: tuple[str, str, int, int] | None = None


@dataclass(frozen=True)
class CandidateWindow:
    candidate_id: str
    incumbent: str
    family: str
    trigger_step: int
    actor: int
    rejoin_step: int
    actions: tuple[tuple[str, ...], ...]
    expected_positions: tuple[tuple[int, int], ...]
    requirements: tuple[Requirement, ...]
    sell_directives: tuple[SellDirective, ...]
    displaced_actions: tuple[tuple[str, ...], ...]
    touched_tiles: tuple[tuple[int, int], ...]
    effects: tuple[HorizonEffect, ...] = ()


def to_json(window: CandidateWindow) -> dict[str, Any]:
    """Return a plain ordered structure suitable for canonical JSON encoding."""
    return asdict(window)


def _requirement(value: Mapping[str, Any]) -> Requirement:
    field = str(value["field"])
    expected = value["value"]
    # ``actor_position`` is the schema's exact-coordinate requirement. JSON
    # decodes its tuple as a list, which must not silently break equality or a
    # forced window's fail-closed position precondition on artifact replay.
    if field == "actor_position" and isinstance(expected, list):
        expected = tuple(expected)
    return Requirement(field, tuple(value["key"]), str(value["operator"]), expected)


def _directive(value: Mapping[str, Any]) -> SellDirective:
    return SellDirective(int(value["offset"]), str(value["product"]), int(value["quantity"]))


def _market_shift(value: Mapping[str, Any]) -> MarketShift:
    return MarketShift(
        str(value["product"]), int(value["quantity"]), int(value["control_offset"]),
        int(value["candidate_offset"]), str(value["provenance"]),
        None if value.get("control_receipt") is None else float(value["control_receipt"]),
        None if value.get("candidate_receipt") is None else float(value["candidate_receipt"]),
    )


def _effect(value: Mapping[str, Any]) -> HorizonEffect:
    return HorizonEffect(
        int(value["horizon"]), float(value["cash_coins"]),
        tuple(tuple(item) for item in value["liquidatable"]),
        tuple(tuple(item) for item in value["asset"]),
        tuple(tuple(item) for item in value["capacity"]),
        tuple(_market_shift(item) for item in value["market"]),
        None if value.get("context") is None else (
            str(value["context"][0]), str(value["context"][1]),
            int(value["context"][2]), int(value["context"][3]),
        ),
    )


def from_json(value: str | Mapping[str, Any]) -> CandidateWindow:
    """Restore the exact immutable tuple structure emitted by :func:`to_json`."""
    data = json.loads(value) if isinstance(value, str) else value
    return CandidateWindow(
        candidate_id=str(data["candidate_id"]),
        incumbent=str(data["incumbent"]),
        family=str(data["family"]),
        trigger_step=int(data["trigger_step"]),
        actor=int(data["actor"]),
        rejoin_step=int(data["rejoin_step"]),
        actions=tuple(tuple(item) for item in data["actions"]),
        expected_positions=tuple(tuple(item) for item in data["expected_positions"]),
        requirements=tuple(_requirement(item) for item in data["requirements"]),
        sell_directives=tuple(_directive(item) for item in data["sell_directives"]),
        displaced_actions=tuple(tuple(item) for item in data["displaced_actions"]),
        touched_tiles=tuple(tuple(item) for item in data["touched_tiles"]),
        effects=tuple(_effect(item) for item in data.get("effects", ())),
    )
