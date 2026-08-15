"""Canonical genome, compile-result, and job schemas."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any


LANES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
SHIFT_VALUES = (-72, -48, -24, 0, 24, 48, 72)
FACTOR_NAMES = (
    "maintenance",
    "reclaimed_labor",
    "capacity",
    "shipping",
    "market_exposure",
    "abandonment",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def stable_id(prefix: str, value: Any, length: int = 20) -> str:
    return f"{prefix}_{hashlib.sha256(canonical_bytes(value)).hexdigest()[:length]}"


@dataclass(frozen=True)
class FactorMutation:
    factor: str
    mode: str
    parameters: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.factor not in FACTOR_NAMES:
            raise ValueError(f"unknown causal factor: {self.factor}")
        object.__setattr__(self, "parameters", tuple(sorted(self.parameters)))

    def payload(self) -> dict[str, Any]:
        return {
            "factor": self.factor,
            "mode": self.mode,
            "parameters": {key: value for key, value in self.parameters},
        }


@dataclass(frozen=True)
class SemanticGenome:
    family: str = "ninth_cow"
    structural_root: str = "control"
    purchase_shift: int = 0
    mutations: tuple[FactorMutation, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.family != "ninth_cow":
            raise ValueError("D1 supports only the ninth_cow family")
        if self.structural_root not in {"control", "removal", "shift"}:
            raise ValueError(self.structural_root)
        if self.structural_root == "shift" and self.purchase_shift not in SHIFT_VALUES:
            raise ValueError(f"unsupported shift: {self.purchase_shift}")
        if self.structural_root != "shift" and self.purchase_shift != 0:
            raise ValueError("non-shift roots must use purchase_shift=0")
        factors = [mutation.factor for mutation in self.mutations]
        if len(factors) != len(set(factors)):
            raise ValueError("a genome may mutate each causal factor once")
        object.__setattr__(self, "mutations", tuple(sorted(self.mutations, key=lambda row: row.factor)))

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "family": self.family,
            "structural_root": self.structural_root,
            "purchase_shift": self.purchase_shift,
            "mutations": [mutation.payload() for mutation in self.mutations],
        }

    @property
    def genome_id(self) -> str:
        return stable_id("g", self.payload())


@dataclass(frozen=True)
class Precondition:
    scope: str
    field: str
    operator: str
    value: Any
    public: bool


@dataclass(frozen=True)
class DisplacedAction:
    step: int
    channel: str
    actor: int | None
    incumbent: Any
    candidate: Any
    disposition: str
    destination: str

    def __post_init__(self) -> None:
        if self.disposition not in {"retained", "reassigned", "reclaimed"}:
            raise ValueError(self.disposition)


@dataclass(frozen=True)
class StepPatch:
    step: int
    actor_actions: tuple[tuple[int, tuple[Any, ...]], ...] = ()
    remove_market: tuple[tuple[Any, ...], ...] = ()
    append_market: tuple[tuple[Any, ...], ...] = ()


@dataclass(frozen=True)
class PatchWindow:
    name: str
    start: int
    end: int
    entry_conditions: tuple[Precondition, ...]
    rejoin_step: int
    rejoin_actor: int | None
    rejoin_position: tuple[int, int] | None
    fallback: str = "incumbent"

    def __post_init__(self) -> None:
        duration = self.end - self.start + 1
        if duration < 8 or duration > 48:
            raise ValueError(f"window {self.name} duration {duration} outside 8..48")
        if self.rejoin_step <= self.end:
            raise ValueError(f"window {self.name} must rejoin after its active end")


@dataclass(frozen=True)
class StaticRejection:
    lane: str
    genome_id: str
    code: str
    stage: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def candidate_id(self) -> str:
        return stable_id(
            "reject",
            {"lane": self.lane, "genome_id": self.genome_id, "code": self.code, "stage": self.stage},
        )


@dataclass(frozen=True)
class CompiledCandidate:
    lane: str
    genome: SemanticGenome
    compiler_version: str
    control_sha256: str
    route_sha256: str
    patches: tuple[StepPatch, ...]
    windows: tuple[PatchWindow, ...]
    displaced_actions: tuple[DisplacedAction, ...]
    lineage_digest: str
    resource_ledger: dict[str, Any]
    public_selector: dict[str, Any]

    def __post_init__(self) -> None:
        if self.lane not in LANES:
            raise ValueError(self.lane)
        if any(row.scope == "opponent_private" for window in self.windows for row in window.entry_conditions):
            raise ValueError("opponent-private preconditions are forbidden")

    def payload(self) -> dict[str, Any]:
        result = asdict(self)
        result["genome"] = self.genome.payload()
        return result

    @property
    def candidate_id(self) -> str:
        identity = {
            "lane": self.lane,
            "genome_id": self.genome.genome_id,
            "compiler_version": self.compiler_version,
            "control_sha256": self.control_sha256,
            "route_sha256": self.route_sha256,
            "lineage_digest": self.lineage_digest,
            "patches": [asdict(row) for row in self.patches],
            "windows": [asdict(row) for row in self.windows],
            "displaced_actions": [asdict(row) for row in self.displaced_actions],
            "resource_ledger": self.resource_ledger,
            "public_selector": self.public_selector,
        }
        return stable_id("c", identity, length=24)


def genome_from_payload(payload: dict[str, Any]) -> SemanticGenome:
    mutations = tuple(
        FactorMutation(
            factor=str(row["factor"]),
            mode=str(row["mode"]),
            parameters=tuple((str(key), value) for key, value in (row.get("parameters") or {}).items()),
        )
        for row in payload.get("mutations", [])
    )
    return SemanticGenome(
        family=str(payload.get("family", "ninth_cow")),
        structural_root=str(payload.get("structural_root", "control")),
        purchase_shift=int(payload.get("purchase_shift", 0)),
        mutations=mutations,
        schema_version=int(payload.get("schema_version", 1)),
    )


def compiled_from_payload(payload: dict[str, Any]) -> CompiledCandidate:
    genome = genome_from_payload(payload["genome"])
    patches = tuple(
        StepPatch(
            step=int(row["step"]),
            actor_actions=tuple((int(actor), tuple(order)) for actor, order in row.get("actor_actions", [])),
            remove_market=tuple(tuple(order) for order in row.get("remove_market", [])),
            append_market=tuple(tuple(order) for order in row.get("append_market", [])),
        )
        for row in payload.get("patches", [])
    )
    windows = tuple(
        PatchWindow(
            name=str(row["name"]),
            start=int(row["start"]),
            end=int(row["end"]),
            entry_conditions=tuple(Precondition(**condition) for condition in row.get("entry_conditions", [])),
            rejoin_step=int(row["rejoin_step"]),
            rejoin_actor=None if row.get("rejoin_actor") is None else int(row["rejoin_actor"]),
            rejoin_position=None if row.get("rejoin_position") is None else tuple(row["rejoin_position"]),
            fallback=str(row.get("fallback", "incumbent")),
        )
        for row in payload.get("windows", [])
    )
    displaced = tuple(
        DisplacedAction(
            step=int(row["step"]),
            channel=str(row["channel"]),
            actor=None if row.get("actor") is None else int(row["actor"]),
            incumbent=row.get("incumbent"),
            candidate=row.get("candidate"),
            disposition=str(row["disposition"]),
            destination=str(row["destination"]),
        )
        for row in payload.get("displaced_actions", [])
    )
    return CompiledCandidate(
        lane=str(payload["lane"]),
        genome=genome,
        compiler_version=str(payload["compiler_version"]),
        control_sha256=str(payload["control_sha256"]),
        route_sha256=str(payload["route_sha256"]),
        patches=patches,
        windows=windows,
        displaced_actions=displaced,
        lineage_digest=str(payload["lineage_digest"]),
        resource_ledger=dict(payload.get("resource_ledger") or {}),
        public_selector=dict(payload.get("public_selector") or {}),
    )
