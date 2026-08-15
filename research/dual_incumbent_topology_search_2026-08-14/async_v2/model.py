"""Canonical v2 genomes and compiled candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any


LANES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
CHANNELS = ("unit", "market")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def stable_id(prefix: str, value: Any, length: int = 24) -> str:
    return f"{prefix}_{payload_hash(value)[:length]}"


@dataclass(frozen=True, order=True)
class RouteBlockGene:
    source_tape: str
    start: int
    end: int
    channels: tuple[str, ...]
    motif_id: str

    def __post_init__(self) -> None:
        channels = tuple(sorted(set(self.channels)))
        if not channels or any(channel not in CHANNELS for channel in channels):
            raise ValueError(f"invalid channels: {channels}")
        if not 0 <= int(self.start) <= int(self.end) <= 717:
            raise ValueError("route block must leave a recorded rejoin step")
        if not 8 <= int(self.end) - int(self.start) + 1 <= 48:
            raise ValueError("route block must span 8--48 turns")
        object.__setattr__(self, "channels", channels)

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class MarketPolicyGene:
    product: str
    min_price_bps: int = 0
    max_public_inventory: int = 20000
    quantity_bps: int = 10000

    def __post_init__(self) -> None:
        if self.product not in PRODUCTS:
            raise ValueError(self.product)
        if self.min_price_bps not in {0, 5000, 7500, 10000, 12500, 15000}:
            raise ValueError("unsupported public price threshold")
        if self.max_public_inventory not in {9000, 9500, 10000, 10500, 11000, 20000}:
            raise ValueError("unsupported public inventory threshold")
        if self.quantity_bps not in {0, 5000, 7500, 10000}:
            raise ValueError("quantity may only suppress or scale down a route sale")

    def payload(self) -> dict[str, Any]:
        return asdict(self)


COMMON_CONSTANT_DOMAINS: dict[str, tuple[int, ...]] = {
    "demand_alpha_milli": (0, 125, 250, 500, 1000),
    "weed_replay_steps": (2, 4, 8, 12),
    "max_market_orders": (1, 2, 4, 10),
}
BOATLEE_CONSTANT_DOMAINS: dict[str, tuple[int, ...]] = {
    "livestock_switch_step": (137, 149, 161, 173, 185),
    "wool_gate_scale_bps": (5000, 7500, 10000, 12500, 15000),
    "wool_pressure": (66, 72, 78, 84, 90),
    "wool_batch": (8, 12, 16, 24, 32),
    "wool_gap": (3, 6, 9, 12, 24),
    "relay_distance_max": (4, 6, 8, 10, 12),
    "relay_lead": (0, 1, 3, 6),
    "relay_first": (254, 266, 278, 290, 302),
    "relay_last": (614, 638, 662, 686),
}


def constant_domains(lane: str) -> dict[str, tuple[int, ...]]:
    if lane not in LANES:
        raise ValueError(lane)
    result = dict(COMMON_CONSTANT_DOMAINS)
    if lane == "boatlee_v16_rc2_market_relay":
        result.update(BOATLEE_CONSTANT_DOMAINS)
    return result


@dataclass(frozen=True, order=True)
class ConstantGene:
    name: str
    value: int

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AsyncGenome:
    route_blocks: tuple[RouteBlockGene, ...] = ()
    market_policy: tuple[MarketPolicyGene, ...] = ()
    constants: tuple[ConstantGene, ...] = ()
    schema_version: int = 2

    def __post_init__(self) -> None:
        blocks = tuple(sorted(set(self.route_blocks)))
        policy = tuple(sorted(set(self.market_policy)))
        constants = tuple(sorted(set(self.constants)))
        if len(blocks) > 8 or len(policy) > 5 or len(constants) > 12:
            raise ValueError("genome complexity bound exceeded")
        if len({row.product for row in policy}) != len(policy):
            raise ValueError("one market policy gene per product")
        if len({row.name for row in constants}) != len(constants):
            raise ValueError("one constant gene per name")
        for left_index, left in enumerate(blocks):
            for right in blocks[left_index + 1:]:
                if left.end < right.start or right.end < left.start:
                    continue
                if set(left.channels) & set(right.channels):
                    raise ValueError("route blocks may overlap only on disjoint channels")
        object.__setattr__(self, "route_blocks", blocks)
        object.__setattr__(self, "market_policy", policy)
        object.__setattr__(self, "constants", constants)

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "route_blocks": [row.payload() for row in self.route_blocks],
            "market_policy": [row.payload() for row in self.market_policy],
            "constants": [row.payload() for row in self.constants],
        }

    @property
    def genome_id(self) -> str:
        return stable_id("ag", self.payload())


@dataclass(frozen=True)
class CompiledAsyncCandidate:
    lane: str
    genome: AsyncGenome
    control_sha256: str
    library_sha256: str
    windows: tuple[dict[str, Any], ...]
    patches: tuple[dict[str, Any], ...]
    constants: tuple[tuple[str, int], ...]
    market_policy: tuple[dict[str, Any], ...]
    displaced_actions: tuple[dict[str, Any], ...]
    compiler_version: str = "async-v2"

    def payload(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "genome": self.genome.payload(),
            "control_sha256": self.control_sha256,
            "library_sha256": self.library_sha256,
            "windows": list(self.windows),
            "patches": list(self.patches),
            "constants": [[key, value] for key, value in self.constants],
            "market_policy": list(self.market_policy),
            "displaced_actions": list(self.displaced_actions),
            "compiler_version": self.compiler_version,
        }

    @property
    def candidate_id(self) -> str:
        return stable_id("ac", self.payload())

    def runtime_payload(self) -> dict[str, Any]:
        return {**self.payload(), "candidate_id": self.candidate_id, "genome_id": self.genome.genome_id}


@dataclass(frozen=True)
class StaticRejection:
    lane: str
    genome_id: str
    code: str
    detail: str
    evidence: tuple[tuple[str, Any], ...] = ()

    def payload(self) -> dict[str, Any]:
        return {
            "status": "rejected", "lane": self.lane, "genome_id": self.genome_id,
            "code": self.code, "detail": self.detail, "evidence": dict(self.evidence),
        }


def genome_from_payload(payload: dict[str, Any]) -> AsyncGenome:
    return AsyncGenome(
        route_blocks=tuple(RouteBlockGene(**row) for row in payload.get("route_blocks", ())),
        market_policy=tuple(MarketPolicyGene(**row) for row in payload.get("market_policy", ())),
        constants=tuple(ConstantGene(**row) for row in payload.get("constants", ())),
        schema_version=int(payload.get("schema_version", 2)),
    )


def candidate_from_payload(payload: dict[str, Any]) -> CompiledAsyncCandidate:
    candidate = CompiledAsyncCandidate(
        lane=payload["lane"], genome=genome_from_payload(payload["genome"]),
        control_sha256=payload["control_sha256"], library_sha256=payload["library_sha256"],
        windows=tuple(payload.get("windows", ())), patches=tuple(payload.get("patches", ())),
        constants=tuple((str(key), int(value)) for key, value in payload.get("constants", ())),
        market_policy=tuple(payload.get("market_policy", ())),
        displaced_actions=tuple(payload.get("displaced_actions", ())),
        compiler_version=payload.get("compiler_version", "async-v2"),
    )
    expected = payload.get("candidate_id")
    if expected is not None and expected != candidate.candidate_id:
        raise ValueError("candidate payload hash mismatch")
    return candidate
