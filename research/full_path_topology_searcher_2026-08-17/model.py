"""Canonical, lane-isolated contracts for topology search."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any, Mapping


LANES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
CONTINUATION_MODES = ("immediate", "fixed", "state_rejoin", "terminal_handoff")
FORBIDDEN_RUNTIME_KEYS = {
    "account", "opponent", "opponent_family", "opponent_identity", "opponent_private", "opponent_team",
    "opponent_private_state", "submission_id", "team", "team_id",
}
PRODUCTS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"}
ANIMALS = {"GOOSE", "COW", "SHEEP"}
PUBLIC_TILE_FIELDS = {
    "kind", "crop", "animal", "planted_day", "placed_day", "watered_today", "fed_today",
    "cared_today", "consecutive_unwatered", "consecutive_unfed", "consecutive_uncared",
    "yield_units", "fertilizer_available", "fertilized_until_day", "max_lifespan_step",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()[:24]}"


def _forbidden_paths(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            segments = {part.lower() for part in str(key).replace("[", ".").replace("]", "").split(".")}
            if segments & FORBIDDEN_RUNTIME_KEYS:
                found.append(child_path)
            found.extend(_forbidden_paths(child, child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found.extend(_forbidden_paths(child, f"{path}[{index}]"))
    return found


def _private_key_paths(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            segments = {part.lower() for part in str(key).split(".")}
            if "private" in segments:
                found.append(child_path)
            found.extend(_private_key_paths(child, child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found.extend(_private_key_paths(child, f"{path}[{index}]"))
    return found


def _path_allowed(path: str, allow_own_private: bool) -> bool:
    parts = path.split(".")
    if path in {"step", "day", "hour"}:
        return True
    if len(parts) == 3 and parts[:2] in (["market", "prices"], ["market", "inventory"]):
        return parts[2] in PRODUCTS
    if len(parts) == 3 and parts[:2] == ["town", "unlocked_shops"]:
        return parts[2].isdigit()
    if parts and parts[0] in {"own_farm", "opponent_farm"}:
        rest = parts[1:]
        if rest == ["money"]:
            return True
        if len(rest) == 2 and rest[0] == "farmer" and rest[1] in {"0", "1"}:
            return True
        if len(rest) == 3 and rest[0] == "hands" and rest[1].isdigit() and rest[2] in {"0", "1"}:
            return True
        if len(rest) == 3 and rest[0] == "tiles" and rest[1].isdigit() and rest[2].isdigit():
            return True
        if len(rest) == 4 and rest[0] == "tiles" and rest[1].isdigit() and rest[2].isdigit() and rest[3] in PUBLIC_TILE_FIELDS:
            return True
        return False
    if allow_own_private and len(parts) == 3 and parts[0] == "private":
        if parts[1] == "seeds":
            return parts[2] in PRODUCTS
        if parts[1] == "shed":
            return parts[2] in PRODUCTS | ANIMALS
    if allow_own_private and len(parts) == 4 and parts[0:2] == ["private", "inventories"]:
        return parts[2].isdigit() and parts[3] in PRODUCTS | ANIMALS
    return False


def _validate_dotted_path(path: str, allow_own_private: bool) -> None:
    parts = path.split(".")
    if not parts or any(not part for part in parts) or not _path_allowed(path, allow_own_private):
        raise ValueError(f"path is outside the explicit observation schema: {path}")
    if {part.lower() for part in parts} & FORBIDDEN_RUNTIME_KEYS:
        raise ValueError(f"path crosses the identity/private-opponent boundary: {path}")
    if "private" in {part.lower() for part in parts[1:]}:
        raise ValueError(f"private may only be the root for own-private rejoin state: {path}")


def _leaf_paths(value: Any, path: str = "") -> list[str]:
    if isinstance(value, Mapping):
        paths: list[str] = []
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            paths.extend(_leaf_paths(child, child_path))
        return paths
    if isinstance(value, (list, tuple)):
        paths = []
        for index, child in enumerate(value):
            paths.extend(_leaf_paths(child, f"{path}.{index}" if path else str(index)))
        return paths
    return [path]


def _validate_resource_topology(value: Mapping[str, Any]) -> None:
    allowed = {"worker_positions", "crop_tiles", "animal_tiles", "jobs", "market_exposure", "route_step", "shed_capacity", "resource_digest"}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"resource topology contains non-schema fields: {sorted(unknown)}")
    for key in ("worker_positions", "crop_tiles", "animal_tiles"):
        rows = value.get(key, [])
        if not isinstance(rows, (list, tuple)) or any(
                not isinstance(row, (list, tuple)) or len(row) != 2
                or any(not isinstance(item, int) or isinstance(item, bool) for item in row)
                for row in rows):
            raise ValueError(f"{key} must contain coordinate pairs")
    jobs = value.get("jobs", [])
    if not isinstance(jobs, (list, tuple)) or any(not isinstance(item, str) for item in jobs):
        raise ValueError("jobs must be string identifiers")
    exposure = value.get("market_exposure", {})
    if not isinstance(exposure, Mapping) or any(key not in PRODUCTS or not isinstance(item, (int, float)) or isinstance(item, bool) for key, item in exposure.items()):
        raise ValueError("market_exposure must contain known public products and numeric values")
    for key in ("route_step", "shed_capacity"):
        if key in value and (not isinstance(value[key], int) or isinstance(value[key], bool)):
            raise ValueError(f"{key} must be an integer")
    if "resource_digest" in value and (not isinstance(value["resource_digest"], str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value["resource_digest"])):
        raise ValueError("resource_digest must be a SHA-256 hex digest")


def _validate_own_private_state(value: Mapping[str, Any]) -> None:
    unknown = set(value) - {"seeds", "shed", "inventories"}
    if unknown:
        raise ValueError(f"own-private state contains non-schema fields: {sorted(unknown)}")
    for section, allowed in (("seeds", PRODUCTS), ("shed", PRODUCTS | ANIMALS)):
        rows = value.get(section, {})
        if (not isinstance(rows, Mapping) or any(key not in allowed for key in rows)
                or any(not isinstance(count, int) or isinstance(count, bool) or count < 0 for count in rows.values())):
            raise ValueError(f"private.{section} must map known item names to nonnegative integer counts")
    inventories = value.get("inventories", {})
    if isinstance(inventories, Mapping):
        inventory_rows = inventories.items()
    elif isinstance(inventories, (list, tuple)):
        inventory_rows = enumerate(inventories)
    else:
        raise ValueError("private.inventories must be indexed mappings")
    for index, inventory in inventory_rows:
        if isinstance(index, bool) or not str(index).isdigit() or not isinstance(inventory, Mapping):
            raise ValueError("private.inventories must use non-Boolean integer indices")
        if any(item not in PRODUCTS | ANIMALS for item in inventory):
            raise ValueError("private.inventories must map known item names")
        if any(not isinstance(count, int) or isinstance(count, bool) or count < 0 for count in inventory.values()):
            raise ValueError("private.inventories must contain nonnegative integer counts")


@dataclass(frozen=True)
class StateSignature:
    step: int
    lane: str
    seat: int
    public_state: Mapping[str, Any]
    own_private_state: Mapping[str, Any]
    resource_topology: Mapping[str, Any]
    exact_state_digest: str
    opponent_family: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.lane not in LANES:
            raise ValueError(f"unknown lane: {self.lane}")
        if (not isinstance(self.seat, int) or isinstance(self.seat, bool) or self.seat not in (0, 1)
                or not isinstance(self.step, int) or isinstance(self.step, bool) or not 0 <= self.step <= 718):
            raise ValueError("seat must be 0/1 and step must be 0..718")
        if not all(isinstance(value, Mapping) for value in (self.public_state, self.own_private_state, self.resource_topology)):
            raise ValueError("state sections must be mappings")
        if len(self.exact_state_digest) != 64 or any(char not in "0123456789abcdef" for char in self.exact_state_digest.lower()):
            raise ValueError("exact_state_digest must be a SHA-256 hex digest")
        illegal = (_forbidden_paths(self.public_state) + _forbidden_paths(self.own_private_state)
                   + _forbidden_paths(self.resource_topology) + _private_key_paths(self.public_state)
                   + _private_key_paths(self.resource_topology))
        if illegal:
            raise ValueError(f"runtime state contains forbidden identity/private-opponent keys: {illegal}")
        for path in _leaf_paths(self.public_state):
            _validate_dotted_path(path, allow_own_private=False)
        for path in _leaf_paths(self.own_private_state):
            _validate_dotted_path(f"private.{path}", allow_own_private=True)
        _validate_own_private_state(self.own_private_state)
        _validate_resource_topology(self.resource_topology)

    @property
    def node_id(self) -> str:
        payload = asdict(self)
        payload.pop("opponent_family", None)  # offline stratum, never a runtime selector
        return f"{self.lane}:{stable_id('state', payload)}"


@dataclass(frozen=True)
class RejoinContract:
    compatibility_fields: tuple[str, ...] = ()
    expected: Mapping[str, Any] = field(default_factory=dict)
    tolerances: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if set(self.expected) != set(self.compatibility_fields):
            raise ValueError("expected values must exactly match compatibility_fields")
        if not set(self.tolerances).issubset(self.expected):
            raise ValueError("tolerances must name compatibility fields")
        if any(float(value) < 0 for value in self.tolerances.values()):
            raise ValueError("rejoin tolerances must be non-negative")
        illegal = _forbidden_paths(self.expected)
        if illegal:
            raise ValueError(f"rejoin values contain forbidden identity/private-opponent keys: {illegal}")
        for path in self.compatibility_fields:
            _validate_dotted_path(path, allow_own_private=True)


@dataclass(frozen=True)
class ContinuationSpec:
    mode: str
    min_end_step: int
    max_end_step: int
    rejoin: RejoinContract = field(default_factory=RejoinContract)

    def __post_init__(self) -> None:
        if self.mode not in CONTINUATION_MODES:
            raise ValueError(f"unknown continuation mode: {self.mode}")
        if (not isinstance(self.min_end_step, int) or isinstance(self.min_end_step, bool)
                or not isinstance(self.max_end_step, int) or isinstance(self.max_end_step, bool)
                or not 0 <= self.min_end_step <= self.max_end_step <= 718):
            raise ValueError("continuation bounds must be ordered within 0..718")
        if self.mode == "state_rejoin" and not self.rejoin.compatibility_fields:
            raise ValueError("state_rejoin requires explicit compatibility fields")


@dataclass(frozen=True)
class BranchSpec:
    lane: str
    decision_step: int
    trigger: Mapping[str, Any]
    motif: Mapping[str, Any]
    displaced_actions: tuple[str, ...]
    continuation: ContinuationSpec
    fallback: str
    parent_node_id: str
    evidence_ids: tuple[str, ...]
    max_horizon: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ValueError("V1 accepts schema_version == 1 only")
        if self.lane not in LANES:
            raise ValueError(f"unknown lane: {self.lane}")
        if not isinstance(self.decision_step, int) or isinstance(self.decision_step, bool) or not 0 <= self.decision_step <= 718:
            raise ValueError("decision_step must be 0..718")
        if self.fallback != "incumbent":
            raise ValueError("V1 supports incumbent fallback only")
        if not isinstance(self.max_horizon, int) or isinstance(self.max_horizon, bool) or not 1 <= self.max_horizon <= 48:
            raise ValueError("max_horizon must be bounded to 1..48 turns")
        if self.continuation.max_end_step - self.decision_step + 1 > self.max_horizon:
            raise ValueError("continuation exceeds max_horizon")
        if self.continuation.min_end_step < self.decision_step:
            raise ValueError("continuation cannot end before its decision step")
        if self.continuation.mode == "immediate" and (self.continuation.min_end_step != self.decision_step or self.continuation.max_end_step != self.decision_step):
            raise ValueError("immediate continuation must begin and end at the decision step")
        if self.continuation.mode == "terminal_handoff" and self.continuation.max_end_step != 718:
            raise ValueError("terminal_handoff must explicitly run through step 718")
        clauses = self.trigger.get("all") if isinstance(self.trigger, Mapping) else None
        if not isinstance(self.trigger, Mapping) or set(self.trigger) != {"all"}:
            raise ValueError("branch trigger schema permits the 'all' field only")
        if not isinstance(clauses, list) or not clauses:
            raise ValueError("branch requires at least one explicit public trigger clause")
        for clause in clauses:
            if (not isinstance(clause, Mapping) or not {"path", "op", "value"}.issubset(clause)
                    or set(clause) - {"path", "op", "value", "tolerance"}
                    or not isinstance(clause.get("path"), str)):
                raise ValueError("every trigger clause requires a dotted public path")
            if clause["path"].split(".", 1)[0] == "private":
                raise ValueError("branch triggers cannot select on private state")
            _validate_dotted_path(str(clause["path"]), allow_own_private=False)
            if clause.get("op", "eq") not in ("eq", "ge", "gt", "le", "lt", "in"):
                raise ValueError("unsupported trigger comparison")
        illegal = _forbidden_paths(self.trigger) + _forbidden_paths(self.motif)
        if illegal:
            raise ValueError(f"branch contains forbidden runtime selectors: {illegal}")
        if not self.parent_node_id.startswith(f"{self.lane}:"):
            raise ValueError("parent node must be explicitly lane-scoped")
        if not self.evidence_ids:
            raise ValueError("branch requires attributed evidence")

    @property
    def branch_id(self) -> str:
        return stable_id("branch", asdict(self))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BranchSpec":
        continuation = dict(value["continuation"])
        continuation["rejoin"] = RejoinContract(**continuation.get("rejoin", {}))
        payload = dict(value)
        payload["continuation"] = ContinuationSpec(**continuation)
        motif = dict(payload["motif"])
        normalized_patches = []
        for raw_patch in motif.get("patches", []):
            patch = dict(raw_patch) if isinstance(raw_patch, Mapping) else raw_patch
            if isinstance(patch, dict):
                patch.setdefault("actor_actions", [])
                patch.setdefault("market_mode", "preserve")
                patch.setdefault("market", [])
                if patch["market_mode"] == "insert":
                    patch.setdefault("market_index", 0)
            normalized_patches.append(patch)
        motif["patches"] = normalized_patches
        payload["motif"] = motif
        payload["displaced_actions"] = tuple(payload.get("displaced_actions", ()))
        payload["evidence_ids"] = tuple(payload.get("evidence_ids", ()))
        return cls(**payload)


@dataclass(frozen=True)
class ConditionalOutcomeValue:
    lane: str
    protocol: Mapping[str, Any]
    control_wdl: Mapping[str, int]
    candidate_wdl: Mapping[str, int]
    transition_matrix: Mapping[str, int]
    improve: int
    same: int
    worsen: int
    strata: Mapping[str, Any]
    uncertainty: Mapping[str, Any]
    support: int
    freshness: str
    technical_valid: bool
    effective_change: bool
    wdl_gate_passed: bool
    efficacy_eligible: bool
    economics: Mapping[str, Any] = field(default_factory=dict)
    stop_reasons: tuple[str, ...] = ()

    @property
    def value_id(self) -> str:
        return stable_id("wdl", asdict(self))


@dataclass(frozen=True)
class AtlasNode:
    lane: str
    kind: str
    payload: Mapping[str, Any]

    @property
    def node_id(self) -> str:
        return f"{self.lane}:{stable_id('atlas', {'lane': self.lane, 'kind': self.kind, 'payload': self.payload})}"


@dataclass(frozen=True)
class AtlasEdge:
    lane: str
    source: str
    target: str
    kind: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind not in ("structural", "causal", "outcome"):
            raise ValueError("atlas edge kind must keep structural/causal/outcome evidence separate")
        if not self.source.startswith(f"{self.lane}:") or not self.target.startswith(f"{self.lane}:"):
            raise ValueError("atlas edges cannot cross incumbent lanes")
