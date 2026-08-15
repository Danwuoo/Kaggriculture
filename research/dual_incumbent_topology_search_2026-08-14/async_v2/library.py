"""Mine bounded route-block genes from the corrected local high-score corpus."""

from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
from functools import lru_cache
from typing import Any, Iterable

from model import LANES, RouteBlockGene, canonical_bytes, payload_hash, stable_id


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CORPUS = ROOT / "research" / "cache" / "highscore_route_refresh_2026-08-13" / "corpus"
MANIFEST = CORPUS / "manifest.jsonl"
TAPES = CORPUS / "tapes"
ROUTES = {
    lane: ROOT / "research" / "main_approach" / lane / "development" / "route_actions.json"
    for lane in LANES
}
MOVE = {"EAST": (1, 0), "SOUTH": (0, 1), "WEST": (-1, 0), "NORTH": (0, -1)}
STRUCTURAL = frozenset({"HIRE", "BUY_LAND", "BUY_ANIMAL", "BUY_SEED", "BUY_PRODUCT", "BUILD_PASTURE", "BUILD_COOP", "PLANT", "PLACE", "DIG"})


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@lru_cache(maxsize=64)
def load_tape(tape_sha256: str) -> list[dict[str, Any]]:
    path = TAPES / f"{tape_sha256}.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    actions = payload.get("actions") or []
    if len(actions) != 719 or payload_hash(actions) != tape_sha256:
        raise ValueError(f"invalid corrected donor tape: {tape_sha256}")
    return actions


def _units(action: dict[str, Any]) -> list[list[Any]]:
    return [list(action.get("farmer") or ["PASS"]), *[list(row or ["PASS"]) for row in (action.get("hands") or [])]]


def _market(action: dict[str, Any]) -> list[list[Any]]:
    return [list(row or []) for row in (action.get("market") or [])]


def _channel_view(action: dict[str, Any], channel: str) -> Any:
    return _units(action) if channel == "unit" else _market(action)


def _hire_count(actions: list[dict[str, Any]], start: int, end: int) -> int:
    return sum(
        max(1, int(order[1]) if len(order) >= 2 and isinstance(order[1], int) else 1)
        for step in range(start, end + 1)
        for order in _market(actions[step])
        if order and order[0] == "HIRE"
    )


def _movement_signature(actions: list[dict[str, Any]], start: int, end: int) -> tuple[tuple[int, int], ...]:
    maximum = max(len(_units(actions[step])) for step in range(start, end + 1))
    result = []
    for actor in range(maximum):
        dx = dy = 0
        for step in range(start, end + 1):
            units = _units(actions[step])
            order = units[actor] if actor < len(units) else ["PASS"]
            if order and order[0] in MOVE:
                mx, my = MOVE[order[0]]
                dx += mx
                dy += my
        result.append((dx, dy))
    return tuple(result)


def _unit_compatible(base: list[dict[str, Any]], donor: list[dict[str, Any]], start: int, end: int) -> bool:
    if any(len(_units(base[step])) != len(_units(donor[step])) for step in range(start, end + 1)):
        return False
    return _movement_signature(base, start, end) == _movement_signature(donor, start, end)


def _bounded_clusters(steps: Iterable[int]) -> list[tuple[int, int]]:
    values = sorted(set(int(step) for step in steps if 0 <= int(step) <= 717))
    if not values:
        return []
    raw: list[list[int]] = [[values[0]]]
    for step in values[1:]:
        current = raw[-1]
        if step - current[-1] <= 4 and step - current[0] < 48:
            current.append(step)
        else:
            raw.append([step])
    result = []
    for group in raw:
        start, end = group[0], group[-1]
        missing = max(0, 8 - (end - start + 1))
        left = min(start, missing // 2)
        start -= left
        end = min(717, end + (missing - left))
        if end - start + 1 < 8:
            start = max(0, end - 7)
        result.append((start, end))
    return result


def _structural_opcodes(actions: list[dict[str, Any]], start: int, end: int, channels: tuple[str, ...]) -> list[str]:
    opcodes = []
    for step in range(start, end + 1):
        orders = []
        if "unit" in channels:
            orders.extend(_units(actions[step]))
        if "market" in channels:
            orders.extend(_market(actions[step]))
        opcodes.extend(str(order[0]) for order in orders if order and str(order[0]) in STRUCTURAL)
    return sorted(Counter(opcodes).elements())


def _mine_for_lane(
    lane: str,
    base: list[dict[str, Any]],
    donors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    motifs: dict[str, dict[str, Any]] = {}
    for source in donors:
        donor = load_tape(source["full_tape"])
        channel_clusters: dict[str, list[tuple[int, int]]] = {}
        for channel in ("unit", "market"):
            differences = [
                step for step in range(718)
                if _channel_view(base[step], channel) != _channel_view(donor[step], channel)
            ]
            channel_clusters[channel] = _bounded_clusters(differences)
        proposals: set[tuple[int, int, tuple[str, ...]]] = set()
        proposals.update((start, end, ("unit",)) for start, end in channel_clusters["unit"])
        proposals.update((start, end, ("market",)) for start, end in channel_clusters["market"])
        # A coupled proposal exists where unit and market difference clusters
        # overlap.  It lets crossover retain a route/market dependency as one
        # atomic gene instead of rediscovering a Cartesian pair.
        for u_start, u_end in channel_clusters["unit"]:
            for m_start, m_end in channel_clusters["market"]:
                start, end = min(u_start, m_start), max(u_end, m_end)
                if start <= min(u_end, m_end) and end - start + 1 <= 48:
                    proposals.add((start, end, ("unit", "market")))
        for start, end, channels in sorted(proposals):
            if "unit" in channels and not _unit_compatible(base, donor, start, end):
                continue
            if "market" in channels and _hire_count(base, start, end) != _hire_count(donor, start, end):
                continue
            changed = [
                step for step in range(start, end + 1)
                if any(_channel_view(base[step], channel) != _channel_view(donor[step], channel) for channel in channels)
            ]
            if not changed:
                continue
            content = [
                {channel: _channel_view(donor[step], channel) for channel in channels}
                for step in range(start, end + 1)
            ]
            semantic = {
                "lane": lane, "start": start, "end": end, "channels": list(channels),
                "content_sha256": payload_hash(content),
            }
            motif_id = stable_id("motif", semantic)
            row = {
                "motif_id": motif_id,
                "source_tape": source["full_tape"],
                "source_rank": int(source["rank"]),
                "source_family": source["family"],
                "start": start,
                "end": end,
                "channels": list(channels),
                "changed_steps": changed,
                "content_sha256": semantic["content_sha256"],
                "structural_opcodes": _structural_opcodes(donor, start, end, channels),
            }
            previous = motifs.get(motif_id)
            if previous is None or row["source_rank"] < previous["source_rank"]:
                motifs[motif_id] = row
    return sorted(motifs.values(), key=lambda row: (row["start"], row["end"], row["channels"], row["source_rank"], row["motif_id"]))


def build_library(output: Path, *, donor_limit: int = 40) -> dict[str, Any]:
    manifest_rows = [
        json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    donors = sorted(manifest_rows, key=lambda row: (int(row["rank"]), row["full_tape"]))[: int(donor_limit)]
    source = {
        "manifest": str(MANIFEST),
        "manifest_sha256": file_sha256(MANIFEST),
        "donor_count": len(donors),
        "donor_tapes": [row["full_tape"] for row in donors],
    }
    lanes = {}
    for lane, path in ROUTES.items():
        base = json.loads(path.read_text(encoding="utf-8"))
        if len(base) != 719:
            raise ValueError(f"invalid incumbent route: {lane}")
        lanes[lane] = {
            "route_path": str(path),
            "route_sha256": payload_hash(base),
            "motifs": _mine_for_lane(lane, base, donors),
        }
    body = {"schema_version": 2, "source": source, "lanes": lanes}
    result = {**body, "library_sha256": payload_hash(body)}
    atomic_json(output, result)
    return result


def load_library(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = dict(payload)
    expected = body.pop("library_sha256", None)
    actual = payload_hash(body)
    if not expected or expected != actual:
        raise ValueError(f"motif library hash mismatch: expected={expected} actual={actual}")
    for lane in LANES:
        if lane not in payload.get("lanes", {}):
            raise ValueError(f"missing lane: {lane}")
    return payload


def gene_from_motif(row: dict[str, Any]) -> RouteBlockGene:
    return RouteBlockGene(
        source_tape=row["source_tape"], start=int(row["start"]), end=int(row["end"]),
        channels=tuple(row["channels"]), motif_id=row["motif_id"],
    )
