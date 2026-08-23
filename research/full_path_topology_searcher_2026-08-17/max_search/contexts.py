"""Hash-frozen, stage-disjoint execution contexts for the maximum search."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contract import LANES, canonical_json


class ContextError(ValueError):
    pass


STAGES = ("t0", "t1", "holdout")
MODES = ("development", "formal")


def _signature(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _context_id(family: str, seed: int, seat: int) -> str:
    digest = _signature({"opponent_family": family, "seed": seed, "seat": seat})
    return f"ctx_{digest[:24]}"


def _sha_row(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def opponent_artifact_snapshot(
    workspace: Path,
    families: Sequence[str],
) -> dict[str, Any]:
    """Resolve the frozen local opponent artifacts used by the official runner."""
    import sys

    lane = workspace / "research" / "job_value_residual_2026-08-12"
    if str(lane) not in sys.path:
        sys.path.insert(0, str(lane))
    from protocol import opponent_path  # type: ignore

    result: dict[str, Any] = {}
    for family in sorted(set(families)):
        by_lane: dict[str, Any] = {}
        for incumbent in LANES:
            path = opponent_path(incumbent, family)
            if not path.is_file():
                raise ContextError(f"missing opponent artifact for {incumbent}/{family}: {path}")
            by_lane[incumbent] = _sha_row(path)
        result[family] = {"by_lane": by_lane}
    return result


def _strict_context(row: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(row, Mapping) or set(row) != {"opponent_family", "seed", "seat"}:
        raise ContextError(f"{label} context schema is not closed")
    family, seed, seat = row["opponent_family"], row["seed"], row["seat"]
    if not isinstance(family, str) or not family:
        raise ContextError(f"{label} opponent family must be nonempty")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ContextError(f"{label} seed must be a non-negative integer")
    if not isinstance(seat, int) or isinstance(seat, bool) or seat not in (0, 1):
        raise ContextError(f"{label} seat must be 0 or 1")
    return {
        "context_id": _context_id(family, seed, seat),
        "opponent_family": family,
        "seed": seed,
        "seat": seat,
    }


def _validate_artifacts(value: Any, families: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != families:
        raise ContextError("opponent artifact families differ from context families")
    result: dict[str, Any] = {}
    for family in sorted(families):
        family_row = value[family]
        if not isinstance(family_row, Mapping) or set(family_row) != {"by_lane"}:
            raise ContextError(f"{family} opponent artifact schema is not closed")
        by_lane = family_row["by_lane"]
        if not isinstance(by_lane, Mapping) or set(by_lane) != set(LANES):
            raise ContextError(f"{family} opponent artifacts must bind both lanes")
        normalized: dict[str, Any] = {}
        for lane in LANES:
            row = by_lane[lane]
            if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
                raise ContextError(f"{family}/{lane} artifact schema is not closed")
            path, size, digest = row["path"], row["bytes"], row["sha256"]
            if not isinstance(path, str) or not path:
                raise ContextError(f"{family}/{lane} artifact path is malformed")
            if not isinstance(size, int) or isinstance(size, bool) or size < 1:
                raise ContextError(f"{family}/{lane} artifact size is malformed")
            if (not isinstance(digest, str) or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)):
                raise ContextError(f"{family}/{lane} artifact hash is malformed")
            normalized[lane] = {"path": path, "bytes": size, "sha256": digest}
        result[family] = {"by_lane": normalized}
    return result


@dataclass(frozen=True)
class ContextRegistry:
    payload: Mapping[str, Any]
    sha256: str

    @property
    def mode(self) -> str:
        return str(self.payload["mode"])

    def contexts(self, stage: str) -> tuple[Mapping[str, Any], ...]:
        if stage not in STAGES:
            raise ContextError(f"unknown context stage: {stage}")
        return tuple(self.payload["stages"][stage])

    @classmethod
    def create(
        cls,
        draft: Mapping[str, Any],
        *,
        opponent_artifacts: Mapping[str, Any],
    ) -> "ContextRegistry":
        if not isinstance(draft, Mapping) or set(draft) != {
            "schema_version", "kind", "mode", "stages", "freshness",
        }:
            raise ContextError("context draft schema is not closed")
        if draft.get("schema_version") != 1 or draft.get("kind") != "maximum_search_context_draft":
            raise ContextError("unsupported context draft")
        mode = draft.get("mode")
        if mode not in MODES:
            raise ContextError("context mode must be development or formal")
        stages = draft.get("stages")
        if not isinstance(stages, Mapping) or set(stages) != set(STAGES):
            raise ContextError("context stages must be exactly t0, t1, and holdout")
        normalized: dict[str, list[dict[str, Any]]] = {}
        seen_ids: set[str] = set()
        stage_seeds: dict[str, set[int]] = {}
        for stage in STAGES:
            rows = stages[stage]
            if not isinstance(rows, list) or not rows:
                raise ContextError(f"{stage} contexts must be a nonempty array")
            found = [_strict_context(row, label=stage) for row in rows]
            ids = [row["context_id"] for row in found]
            if len(ids) != len(set(ids)) or seen_ids.intersection(ids):
                raise ContextError("contexts must be unique within and across stages")
            seen_ids.update(ids)
            stage_seeds[stage] = {int(row["seed"]) for row in found}
            normalized[stage] = found
        if any(stage_seeds[left].intersection(stage_seeds[right]) for left, right in (
            ("t0", "t1"), ("t0", "holdout"), ("t1", "holdout"),
        )):
            raise ContextError("T0, T1, and holdout seed sets must be disjoint")

        freshness = draft.get("freshness")
        if not isinstance(freshness, Mapping) or set(freshness) != {
            "source", "consumed_seed_overlap_allowed", "notes",
        }:
            raise ContextError("context freshness schema is not closed")
        if not isinstance(freshness["source"], str) or not freshness["source"]:
            raise ContextError("context freshness source must be nonempty")
        if type(freshness["consumed_seed_overlap_allowed"]) is not bool:
            raise ContextError("context freshness overlap flag must be boolean")
        if not isinstance(freshness["notes"], str):
            raise ContextError("context freshness notes must be text")

        if mode == "formal":
            if len(normalized["t0"]) != 6 or len(normalized["t1"]) != 24:
                raise ContextError("formal registry requires exactly six T0 and 24 additional T1 contexts")
            if freshness["consumed_seed_overlap_allowed"] is not False:
                raise ContextError("formal contexts cannot allow consumed-seed overlap")
            for stage in ("t0", "t1", "holdout"):
                if {row["seat"] for row in normalized[stage]} != {0, 1}:
                    raise ContextError(f"formal {stage} contexts must cover both seats")
            if len({row["opponent_family"] for row in normalized["t1"]}) < 2:
                raise ContextError("formal T1 contexts must cover at least two opponent families")

        families = {row["opponent_family"] for rows in normalized.values() for row in rows}
        artifacts = _validate_artifacts(opponent_artifacts, families)
        payload = {
            "schema_version": 1,
            "kind": "maximum_search_context_registry",
            "mode": mode,
            "stages": normalized,
            "opponent_artifacts": artifacts,
            "freshness": dict(freshness),
        }
        signed = dict(payload)
        signed["registry_sha256"] = _signature(payload)
        return cls(signed, signed["registry_sha256"])

    @classmethod
    def load(cls, path: Path, *, require_mode: str | None = None) -> "ContextRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or set(payload) != {
            "schema_version", "kind", "mode", "stages", "opponent_artifacts",
            "freshness", "registry_sha256",
        }:
            raise ContextError("context registry schema is not closed")
        signature = payload.get("registry_sha256")
        unsigned = {key: value for key, value in payload.items() if key != "registry_sha256"}
        if not isinstance(signature, str) or signature != _signature(unsigned):
            raise ContextError("context registry signature mismatch")
        draft = {
            "schema_version": payload["schema_version"],
            "kind": "maximum_search_context_draft",
            "mode": payload["mode"],
            "stages": {
                stage: [
                    {key: row[key] for key in ("opponent_family", "seed", "seat")}
                    for row in payload["stages"][stage]
                ]
                for stage in STAGES
            },
            "freshness": payload["freshness"],
        }
        rebuilt = cls.create(draft, opponent_artifacts=payload["opponent_artifacts"])
        if canonical_json(rebuilt.payload) != canonical_json(payload):
            raise ContextError("context registry canonical content mismatch")
        if require_mode is not None and rebuilt.mode != require_mode:
            raise ContextError(f"context registry mode must be {require_mode}")
        return rebuilt


def verify_opponent_artifacts(registry: ContextRegistry) -> None:
    for family, family_row in registry.payload["opponent_artifacts"].items():
        for lane, expected in family_row["by_lane"].items():
            path = Path(expected["path"])
            if not path.is_file() or _sha_row(path) != dict(expected):
                raise ContextError(f"opponent artifact drift for {lane}/{family}")
