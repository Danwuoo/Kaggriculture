"""Canonical, lane-qualified Async V3 search schema.

Lineage deliberately lives beside the semantic genome.  This makes mutation
history auditable without allowing a parent or bundle name to change cache keys
or candidate identity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any


SCHEMA_VERSION = 3
LANES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
CHANNELS = ("unit", "market")
MARKET_OPCODES = ("HIRE", "BUY_LAND", "BUY_ANIMAL", "BUY_SEED", "BUY_PRODUCT", "SELL")
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
ANIMALS = ("GOOSE", "COW", "SHEEP")
CROPS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def stable_id(prefix: str, value: Any, length: int = 24) -> str:
    return f"{prefix}_{payload_hash(value)[:length]}"


def _order_payload(order: tuple[object, ...] | None) -> list[object] | None:
    return list(order) if order is not None else None


def validate_market_order(order: tuple[object, ...] | None) -> None:
    if not order or str(order[0]) not in MARKET_OPCODES:
        raise ValueError("unsupported market opcode")
    opcode = str(order[0])
    if opcode in {"HIRE", "BUY_LAND"}:
        if len(order) != 1:
            raise ValueError(f"{opcode} has no arguments")
        return
    if len(order) != 3 or not isinstance(order[1], str):
        raise ValueError(f"{opcode} requires item and quantity")
    if int(order[2]) <= 0 or int(order[2]) > 999:
        raise ValueError("market quantity outside bounded domain")
    item = str(order[1])
    if opcode == "BUY_ANIMAL" and item not in ANIMALS:
        raise ValueError("BUY_ANIMAL item")
    if opcode == "BUY_SEED" and item not in CROPS:
        raise ValueError("BUY_SEED item")
    if opcode == "BUY_PRODUCT" and item not in {"WHEAT", "FERTILIZER"}:
        raise ValueError("BUY_PRODUCT item")
    if opcode == "SELL" and item not in PRODUCTS:
        raise ValueError("SELL item")


@dataclass(frozen=True, order=True)
class RouteBlockGene:
    source_tape: str
    start: int
    end: int
    channels: tuple[str, ...]
    motif_id: str

    def __post_init__(self) -> None:
        channels = tuple(sorted(set(self.channels)))
        if not channels or any(value not in CHANNELS for value in channels):
            raise ValueError("invalid route channels")
        if not 0 <= int(self.start) <= int(self.end) <= 717:
            raise ValueError("route block must leave a rejoin action")
        if not 8 <= int(self.end) - int(self.start) + 1 <= 48:
            raise ValueError("route block must span 8--48 turns")
        if len(self.source_tape) != 64:
            raise ValueError("route source must be SHA-256")
        object.__setattr__(self, "channels", channels)

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class GuardGene:
    """A public-only predicate attached to one market operation."""

    kind: str
    product: str
    threshold: int

    def __post_init__(self) -> None:
        if self.kind not in {"min_price", "max_price", "min_inventory", "max_inventory"}:
            raise ValueError("guard must use public price or inventory")
        if self.product not in PRODUCTS or int(self.threshold) < 0:
            raise ValueError("invalid public guard")

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class MarketEditGene:
    """An ordered edit against one lane's incumbent market list.

    ``sequence`` establishes the declared edit order.  Input tuple ordering is
    canonicalized by :class:`AsyncGenome`, while sequence remains semantic.
    """

    step: int
    sequence: int
    operation: str
    queue_index: int
    order: tuple[object, ...] | None = None
    target_index: int | None = None
    guard: GuardGene | None = None
    dependency: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not 0 <= int(self.step) <= 718 or int(self.sequence) < 0:
            raise ValueError("invalid edit anchor")
        if self.operation not in {"insert", "remove", "replace", "move", "quantity"}:
            raise ValueError("unsupported market edit")
        if not 0 <= int(self.queue_index) <= 9:
            raise ValueError("queue position must be 0..9")
        if self.operation == "insert":
            if self.target_index is not None or self.order is None:
                raise ValueError("insert requires only its full order")
        else:
            if self.target_index is None or not 0 <= int(self.target_index) <= 9:
                raise ValueError("edit requires a target queue position")
            if self.order is None:
                raise ValueError("edit requires a full order for causal accounting")
        validate_market_order(self.order)
        if self.operation == "quantity" and len(self.order or ()) != 3:
            raise ValueError("quantity operation requires a quantity-bearing order")

    def payload(self) -> dict[str, Any]:
        return {
            "step": int(self.step), "sequence": int(self.sequence), "operation": self.operation,
            "queue_index": int(self.queue_index), "target_index": self.target_index,
            "order": _order_payload(self.order),
            "guard": self.guard.payload() if self.guard else None,
        }


@dataclass(frozen=True, order=True)
class ConstantGene:
    name: str
    value: int

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AsyncGenome:
    lane: str
    route_blocks: tuple[RouteBlockGene, ...] = ()
    market_edits: tuple[MarketEditGene, ...] = ()
    constants: tuple[ConstantGene, ...] = ()
    schema_version: int = SCHEMA_VERSION
    parent_id: str | None = field(default=None, compare=False)
    mutation_id: str | None = field(default=None, compare=False)
    causal_bundle_id: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.lane not in LANES or int(self.schema_version) != SCHEMA_VERSION:
            raise ValueError("lane or schema version")
        blocks = tuple(sorted(set(self.route_blocks)))
        edits = tuple(sorted(set(self.market_edits), key=lambda item: (item.step, item.sequence, item.operation, item.queue_index, item.target_index or -1, item.payload())))
        constants = tuple(sorted(set(self.constants)))
        if len(blocks) > 8 or len(edits) > 24 or len(constants) > 8:
            raise ValueError("bounded genome complexity exceeded")
        if len({(row.step, row.sequence) for row in edits}) != len(edits):
            raise ValueError("market edit order is ambiguous")
        if len({row.name for row in constants}) != len(constants):
            raise ValueError("constant name repeated")
        for index, left in enumerate(blocks):
            for right in blocks[index + 1:]:
                if not (left.end < right.start or right.end < left.start) and set(left.channels) & set(right.channels):
                    raise ValueError("same-channel route blocks overlap")
        object.__setattr__(self, "route_blocks", blocks)
        object.__setattr__(self, "market_edits", edits)
        object.__setattr__(self, "constants", constants)

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION, "lane": self.lane,
            "route_blocks": [row.payload() for row in self.route_blocks],
            "market_edits": [row.payload() for row in self.market_edits],
            "constants": [row.payload() for row in self.constants],
        }

    @property
    def genome_id(self) -> str:
        return stable_id("ag", self.payload())

    def lineage_payload(self) -> dict[str, str | None]:
        return {"parent_id": self.parent_id, "mutation_id": self.mutation_id, "causal_bundle_id": self.causal_bundle_id}


@dataclass(frozen=True)
class CompiledCandidate:
    lane: str
    genome: AsyncGenome
    patches: tuple[dict[str, Any], ...]
    displaced_actions: tuple[dict[str, Any], ...]
    constants: tuple[tuple[str, int], ...]
    accepted: bool = True
    rejection: dict[str, Any] | None = None
    fixture_candidate_id: str | None = None
    fixture_match: bool = False
    compiler_version: str = "async-v3"

    def payload(self) -> dict[str, Any]:
        return {
            "lane": self.lane, "genome": self.genome.payload(), "patches": list(self.patches),
            "displaced_actions": list(self.displaced_actions), "constants": [list(row) for row in self.constants],
            "compiler_version": self.compiler_version,
        }

    @property
    def candidate_id(self) -> str:
        return stable_id("ac", self.payload())

    def runtime_payload(self) -> dict[str, Any]:
        return {**self.payload(), "candidate_id": self.candidate_id, "genome_id": self.genome.genome_id, "lineage": self.genome.lineage_payload()}


def genome_from_payload(payload: dict[str, Any], *, lineage: dict[str, Any] | None = None) -> AsyncGenome:
    """Restore a canonical genome from a manifest/job payload.

    Formal workers never receive an import path or a mutable Python object.  A
    canonical payload is the only candidate transport across a spawned process.
    """
    blocks = tuple(
        RouteBlockGene(
            source_tape=str(row["source_tape"]), start=int(row["start"]), end=int(row["end"]),
            channels=tuple(row["channels"]), motif_id=str(row["motif_id"]),
        )
        for row in payload.get("route_blocks", [])
    )
    edits = tuple(
        MarketEditGene(
            step=int(row["step"]), sequence=int(row["sequence"]), operation=str(row["operation"]),
            queue_index=int(row["queue_index"]), order=tuple(row["order"] or ()),
            target_index=row.get("target_index"),
            guard=GuardGene(**row["guard"]) if row.get("guard") else None,
        )
        for row in payload.get("market_edits", [])
    )
    constants = tuple(ConstantGene(str(row["name"]), int(row["value"])) for row in payload.get("constants", []))
    lineage = lineage or {}
    return AsyncGenome(
        str(payload["lane"]), blocks, edits, constants, int(payload.get("schema_version", SCHEMA_VERSION)),
        parent_id=lineage.get("parent_id"), mutation_id=lineage.get("mutation_id"),
        causal_bundle_id=lineage.get("causal_bundle_id"),
    )


def compiled_from_payload(payload: dict[str, Any]) -> CompiledCandidate:
    """Restore an already compiled canonical candidate for an evaluator worker."""
    genome = genome_from_payload(payload["genome"], lineage=payload.get("lineage"))
    candidate = CompiledCandidate(
        lane=str(payload["lane"]), genome=genome,
        patches=tuple(payload.get("patches", [])), displaced_actions=tuple(payload.get("displaced_actions", [])),
        constants=tuple((str(name), int(value)) for name, value in payload.get("constants", [])),
        compiler_version=str(payload.get("compiler_version", "async-v3")),
    )
    expected = payload.get("candidate_id")
    if expected is not None and candidate.candidate_id != expected:
        raise ValueError("candidate payload hash does not match canonical candidate id")
    return candidate
