"""Canonical sparse full-tape genomes and content-addressed root tapes."""

from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from ..atlas import deduplicated_tapes
except ImportError:  # direct script/test execution
    from atlas import deduplicated_tapes

from .contract import LANES, canonical_json


TURN_COUNT = 719
ACTION_KEYS = {"farmer", "hands", "market"}
PASS_ACTION = {"farmer": ["PASS"], "hands": [], "market": []}
LANE_ID_TOKENS = {"v27_current_meta": "v27", "boatlee_v16_rc2_market_relay": "boatlee"}


class GenomeError(ValueError):
    pass


def candidate_lane(candidate_id: str) -> str:
    if not isinstance(candidate_id, str):
        raise GenomeError("candidate ID must be text")
    for lane, token in LANE_ID_TOKENS.items():
        prefix = f"ft_{token}_"
        suffix = candidate_id.removeprefix(prefix)
        if candidate_id.startswith(prefix) and len(suffix) == 64 and all(character in "0123456789abcdef" for character in suffix):
            return lane
    raise GenomeError("candidate ID does not encode a valid lane and full semantic digest")


def _plain_action(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != ACTION_KEYS:
        raise GenomeError("action must contain exactly farmer, hands, and market")
    farmer, hands, market = value["farmer"], value["hands"], value["market"]
    if not isinstance(farmer, list) or not farmer or not isinstance(farmer[0], str):
        raise GenomeError("farmer action is malformed")
    if not isinstance(hands, list) or any(not isinstance(row, list) or not row or not isinstance(row[0], str) for row in hands):
        raise GenomeError("hands action list is malformed")
    if not isinstance(market, list) or len(market) > 10 or any(not isinstance(row, list) or not row or not isinstance(row[0], str) for row in market):
        raise GenomeError("market action list is malformed or exceeds ten")
    # JSON round-trip supplies a stable plain deep copy and rejects non-JSON
    # candidate payloads before they enter semantic identity.
    return json.loads(canonical_json(dict(value)))


def action_digest(action: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_plain_action(action)).encode("utf-8")).hexdigest()


def tape_digest(actions: Sequence[Mapping[str, Any]]) -> str:
    normalized = normalize_tape(actions)
    return hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()


def normalize_tape(actions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(actions, Sequence) or isinstance(actions, (str, bytes)) or len(actions) != TURN_COUNT:
        raise GenomeError("a full tape must contain exactly 719 actions")
    return [_plain_action(action) for action in actions]


@dataclass(frozen=True, order=True)
class StepPatch:
    step: int
    action_json: str

    @classmethod
    def from_action(cls, step: int, action: Mapping[str, Any]) -> "StepPatch":
        if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step < TURN_COUNT:
            raise GenomeError("patch step outside 0..718")
        return cls(step=step, action_json=canonical_json(_plain_action(action)))

    def action(self) -> dict[str, Any]:
        return json.loads(self.action_json)


@dataclass(frozen=True)
class RootTape:
    root_id: str
    source_kind: str
    source_id: str
    digest: str
    actions: tuple[str, ...]

    @classmethod
    def build(cls, source_kind: str, source_id: str, actions: Sequence[Mapping[str, Any]]) -> "RootTape":
        normalized = normalize_tape(actions)
        digest = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()
        identity = hashlib.sha256(canonical_json({
            "source_kind": source_kind, "source_id": source_id, "tape_digest": digest,
        }).encode("utf-8")).hexdigest()
        root_id = f"root_{identity[:24]}"
        return cls(root_id, source_kind, source_id, digest, tuple(canonical_json(row) for row in normalized))

    def action_at(self, step: int) -> dict[str, Any]:
        if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step < TURN_COUNT:
            raise GenomeError("root action step outside 0..718")
        return json.loads(self.actions[step])

    def materialize(self) -> list[dict[str, Any]]:
        return [json.loads(row) for row in self.actions]


@dataclass(frozen=True)
class FullTapeGenome:
    lane: str
    root_id: str
    root_digest: str
    patches: tuple[StepPatch, ...] = ()

    def __post_init__(self) -> None:
        if self.lane not in LANES:
            raise GenomeError(f"unknown lane: {self.lane}")
        if not isinstance(self.root_id, str) or not self.root_id.startswith("root_"):
            raise GenomeError("invalid root ID")
        if not isinstance(self.root_digest, str) or len(self.root_digest) != 64:
            raise GenomeError("invalid root digest")
        steps = [patch.step for patch in self.patches]
        if steps != sorted(steps) or len(steps) != len(set(steps)):
            raise GenomeError("patches must be unique and sorted by step")
        for patch in self.patches:
            _plain_action(json.loads(patch.action_json))

    @property
    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "lane": self.lane,
            "root_id": self.root_id,
            "root_digest": self.root_digest,
            "patches": [{"step": patch.step, "action": json.loads(patch.action_json)} for patch in self.patches],
        }

    @property
    def semantic_json(self) -> str:
        return canonical_json(self.semantic_payload)

    @property
    def semantic_sha256(self) -> str:
        return hashlib.sha256(self.semantic_json.encode("utf-8")).hexdigest()

    @property
    def candidate_id(self) -> str:
        return f"ft_{LANE_ID_TOKENS[self.lane]}_{self.semantic_sha256}"

    def with_actions(self, replacements: Mapping[int, Mapping[str, Any]], root: RootTape) -> "FullTapeGenome":
        if root.root_id != self.root_id or root.digest != self.root_digest:
            raise GenomeError("root provenance mismatch")
        combined = {patch.step: patch for patch in self.patches}
        for step, action in replacements.items():
            patch = StepPatch.from_action(step, action)
            if patch.action_json == root.actions[step]:
                combined.pop(step, None)
            else:
                combined[step] = patch
        return FullTapeGenome(self.lane, self.root_id, self.root_digest, tuple(sorted(combined.values())))

    def action_at(self, step: int, root: RootTape) -> dict[str, Any]:
        if root.root_id != self.root_id or root.digest != self.root_digest:
            raise GenomeError("root provenance mismatch")
        for patch in self.patches:
            if patch.step == step:
                return patch.action()
            if patch.step > step:
                break
        return root.action_at(step)

    def materialize(self, root: RootTape) -> list[dict[str, Any]]:
        if root.root_id != self.root_id or root.digest != self.root_digest:
            raise GenomeError("root provenance mismatch")
        actions = root.materialize()
        for patch in self.patches:
            actions[patch.step] = patch.action()
        return actions

    def edit_distance_from_root(self) -> int:
        return len(self.patches)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "candidate_id": self.candidate_id,
            "lane": self.lane,
            "root_id": self.root_id,
            "root_digest": self.root_digest,
            "patches": [{"step": patch.step, "action": patch.action()} for patch in self.patches],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FullTapeGenome":
        if not isinstance(value, Mapping) or set(value) != {
            "schema_version", "candidate_id", "lane", "root_id", "root_digest", "patches"
        }:
            raise GenomeError("genome document schema is not closed")
        if value["schema_version"] != 1 or not isinstance(value["patches"], list):
            raise GenomeError("unsupported genome document")
        patches = tuple(StepPatch.from_action(row["step"], row["action"]) for row in value["patches"])
        result = cls(str(value["lane"]), str(value["root_id"]), str(value["root_digest"]), patches)
        if value["candidate_id"] != result.candidate_id:
            raise GenomeError("genome candidate ID mismatch")
        return result


class RootRegistry:
    """Read-only, deduplicated tape roots with immutable semantic identities."""

    def __init__(self, roots: Iterable[RootTape]):
        by_id: dict[str, RootTape] = {}
        for root in roots:
            existing = by_id.get(root.root_id)
            if existing is not None and existing.digest != root.digest:
                raise GenomeError("root ID collision")
            by_id[root.root_id] = existing or root
        if not by_id:
            raise GenomeError("root registry cannot be empty")
        self._roots = dict(sorted(by_id.items()))

    def __len__(self) -> int:
        return len(self._roots)

    def get(self, root_id: str) -> RootTape:
        try:
            return self._roots[root_id]
        except KeyError as exc:
            raise GenomeError(f"unknown root: {root_id}") from exc

    def roots(self, *, source_kind: str | None = None) -> tuple[RootTape, ...]:
        return tuple(root for root in self._roots.values() if source_kind is None or root.source_kind == source_kind)

    def incumbent(self, lane: str) -> RootTape:
        matches = [root for root in self._roots.values() if root.source_kind == "lane_incumbent" and root.source_id == lane]
        if len(matches) != 1:
            raise GenomeError(f"expected exactly one incumbent root for {lane}")
        return matches[0]

    def manifest(self) -> dict[str, Any]:
        rows = [
            {"root_id": root.root_id, "source_kind": root.source_kind, "source_id": root.source_id, "digest": root.digest}
            for root in self._roots.values()
        ]
        return {
            "schema_version": 1,
            "root_count": len(rows),
            "roots": rows,
            "manifest_sha256": hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest(),
        }

    @classmethod
    def load_workspace(cls, root: Path, *, include_public: bool = True) -> "RootRegistry":
        roots: list[RootTape] = []
        for lane in LANES:
            path = root / "research" / "main_approach" / lane / "development" / "route_actions.json"
            actions = json.loads(path.read_text(encoding="utf-8"))
            roots.append(RootTape.build("lane_incumbent", lane, actions))
        roots.append(RootTape.build("pass_tape", "all_pass", [copy.deepcopy(PASS_ACTION) for _ in range(TURN_COUNT)]))
        if include_public:
            retained, _duplicates = deduplicated_tapes()
            for record, actions, digest in retained:
                roots.append(RootTape.build("deduplicated_public_tape", f"episode:{int(record['episode_id'])}:{digest}", actions))
        return cls(roots)
