"""Deterministic lane-local compiler for V3 route and ordered-market genes."""

from __future__ import annotations

from collections import Counter
import copy
import gzip
import json
from pathlib import Path
from typing import Any

from fixture import HERE as V3_HERE, _find_candidate, _source_run, load_fixture
from model import AsyncGenome, CompiledCandidate, ConstantGene, GuardGene, LANES, MarketEditGene, RouteBlockGene, stable_id
from registry import constant_values, validate_constant


ROOT = V3_HERE.parents[2]
ROUTES = {lane: ROOT / "research" / "main_approach" / lane / "development" / "route_actions.json" for lane in LANES}
TAPES = ROOT / "research" / "cache" / "highscore_route_refresh_2026-08-13" / "corpus" / "tapes"


def incumbent_actions(lane: str) -> list[dict[str, Any]]:
    if lane not in LANES:
        raise ValueError(lane)
    payload = json.loads(ROUTES[lane].read_text(encoding="utf-8"))
    if len(payload) != 719:
        raise ValueError(f"invalid incumbent route for {lane}")
    return payload


def _reject(genome: AsyncGenome, code: str, detail: str, **evidence: Any) -> CompiledCandidate:
    return CompiledCandidate(
        genome.lane, genome, (), (), (), accepted=False,
        rejection={"code": code, "detail": detail, "evidence": dict(sorted(evidence.items()))},
    )


def _entries(rows: list[list[Any]]) -> list[dict[str, Any]]:
    return [{"order": list(row), "guard": None} for row in rows]


def _order_rows(entries: list[dict[str, Any]]) -> list[list[Any]]:
    return [list(row["order"]) for row in entries]


def _compatible(current: list[Any], expected: tuple[object, ...], *, quantity: bool = False) -> bool:
    if quantity:
        return len(current) == len(expected) and current[:2] == list(expected[:2])
    return current == list(expected)


def _apply_edit(entries: list[dict[str, Any]], edit: MarketEditGene) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    target = edit.target_index
    supplied = list(edit.order or ())
    if edit.guard is not None and len(supplied) >= 2 and edit.guard.product != supplied[1]:
        return None, {"code": "public_guard_product_mismatch", "detail": "guard must name the edited public product"}
    if edit.operation == "insert":
        index = min(int(edit.queue_index), len(entries))
        entries.insert(index, {"order": supplied, "guard": edit.guard.payload() if edit.guard else None})
    elif target is None or target >= len(entries):
        return None, {"code": "market_target_missing", "detail": "target queue position does not exist", "target_index": target}
    elif edit.operation == "remove":
        if not _compatible(entries[target]["order"], edit.order or ()):
            return None, {"code": "market_target_mismatch", "detail": "remove target differs from declared full order"}
        entries.pop(target)
    elif edit.operation == "replace":
        entries[target] = {"order": supplied, "guard": edit.guard.payload() if edit.guard else None}
    elif edit.operation == "move":
        if not _compatible(entries[target]["order"], edit.order or ()):
            return None, {"code": "market_target_mismatch", "detail": "move target differs from declared full order"}
        moved = entries.pop(target)
        moved["guard"] = edit.guard.payload() if edit.guard else moved["guard"]
        entries.insert(min(int(edit.queue_index), len(entries)), moved)
    elif edit.operation == "quantity":
        if not _compatible(entries[target]["order"], edit.order or (), quantity=True):
            return None, {"code": "market_target_mismatch", "detail": "quantity target differs in opcode or product"}
        entries[target] = {"order": supplied, "guard": edit.guard.payload() if edit.guard else entries[target]["guard"]}
    if len(entries) > 10:
        return None, {"code": "market_queue_overflow", "detail": "compiled queue exceeds engine cap", "count": len(entries)}
    return entries, None


def _dispositions(step: int, base: list[list[Any]], candidate: list[list[Any]], destination: str) -> list[dict[str, Any]]:
    remaining = Counter(tuple(row) for row in candidate)
    rows: list[dict[str, Any]] = []
    for old in base:
        key = tuple(old)
        if remaining[key]:
            remaining[key] -= 1
            new, disposition = list(old), "retained"
        else:
            new, disposition = ["PASS"], "reclaimed"
        rows.append({"step": step, "channel": "market", "incumbent": list(old), "candidate": new, "disposition": disposition, "destination": destination})
    for key, count in sorted(remaining.items()):
        for _ in range(count):
            rows.append({"step": step, "channel": "market", "incumbent": ["PASS"], "candidate": list(key), "disposition": "reassigned", "destination": destination})
    return rows


def _donor(tape_sha256: str) -> list[dict[str, Any]]:
    path = TAPES / f"{tape_sha256}.json.gz"
    if not path.is_file():
        # The source checkout owns frozen corpus data when the detached worktree
        # does not have an independent copy. This is read-only provenance.
        path = _source_run().parents[5] / "cache" / "highscore_route_refresh_2026-08-13" / "corpus" / "tapes" / f"{tape_sha256}.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    actions = payload.get("actions", [])
    if len(actions) != 719:
        raise ValueError("donor tape has wrong length")
    return actions


def _route_market_overrides(genome: AsyncGenome) -> tuple[dict[int, list[list[Any]]], dict[int, str]]:
    values: dict[int, list[list[Any]]] = {}
    destinations: dict[int, str] = {}
    for block in genome.route_blocks:
        if "market" not in block.channels:
            continue
        donor = _donor(block.source_tape)
        for step in range(block.start, block.end + 1):
            values[step] = [list(row or []) for row in (donor[step].get("market") or [])]
            destinations[step] = block.motif_id
    return values, destinations


def compile_genome(lane: str, genome: AsyncGenome) -> CompiledCandidate:
    if lane != genome.lane or lane not in LANES:
        return _reject(genome, "lane_mismatch", "compiler lane must equal the canonical genome lane")
    try:
        for row in genome.constants:
            validate_constant(lane, row.name, row.value)
        defaults = constant_values(lane, genome.constants)
        base = incumbent_actions(lane)
        route_patches, destinations = _route_market_overrides(genome)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        return _reject(genome, "route_or_constant_precondition", str(error))

    edits_by_step: dict[int, list[MarketEditGene]] = {}
    for edit in genome.market_edits:
        edits_by_step.setdefault(edit.step, []).append(edit)
    patches: list[dict[str, Any]] = []
    displaced: list[dict[str, Any]] = []
    for step in sorted(set(route_patches) | set(edits_by_step)):
        base_market = [list(row or []) for row in (base[step].get("market") or [])]
        entries = _entries(copy.deepcopy(route_patches.get(step, base_market)))
        for edit in sorted(edits_by_step.get(step, []), key=lambda row: row.sequence):
            entries, error = _apply_edit(entries, edit)
            if error is not None or entries is None:
                return _reject(genome, str((error or {}).get("code", "market_edit_rejected")), str((error or {}).get("detail", "market edit rejected")), step=step)
        market = _order_rows(entries)
        if market == base_market:
            continue
        destination = destinations.get(step, f"edit:{step}")
        displaced.extend(_dispositions(step, base_market, market, destination))
        patches.append({
            "step": step, "market": market, "market_entries": entries,
            "rejoin": {"step": min(718, step + 1), "reason": "bounded_incumbent_fallback"},
            "public_only": True,
        })
    return CompiledCandidate(
        lane, genome, tuple(patches), tuple(displaced), tuple(sorted(defaults.items())),
    )


def phenotype_report(candidates: tuple[CompiledCandidate, ...] | list[CompiledCandidate]) -> dict[str, Any]:
    """Count only constant values that can reach a live runtime decision."""
    active: list[str] = []
    inactive: list[str] = []
    identities: dict[str, str] = {}
    for candidate in candidates:
        values = dict(candidate.constants)
        named = {row.name for row in candidate.genome.constants}
        cap_name = "v27_market_order_cap" if candidate.lane == "v27_current_meta" else "boatlee_market_order_cap"
        guard_name = "v27_guard_min_price" if candidate.lane == "v27_current_meta" else "boatlee_guard_min_price"
        cap_active = cap_name in named and any(len(row["market"]) > int(values[cap_name]) for row in candidate.patches)
        guard_active = guard_name in named and int(values[guard_name]) > 0 and any(
            order and order[0] == "SELL" for patch in candidate.patches for order in patch["market"]
        )
        is_active = cap_active or guard_active
        (active if is_active else inactive).append(candidate.candidate_id)
        payload = {
            "lane": candidate.lane, "patches": list(candidate.patches),
            "active_constants": {name: values[name] for name in sorted(named) if (name == cap_name and cap_active) or (name == guard_name and guard_active)},
        }
        identities[candidate.candidate_id] = stable_id("ph", payload)
    return {"phenotype_ids": identities, "active_constants": active, "inactive_constants": inactive}


def _v3_genome_from_v2(lane: str, payload: dict[str, Any]) -> AsyncGenome:
    blocks = tuple(
        RouteBlockGene(
            source_tape=row["source_tape"], start=int(row["start"]), end=int(row["end"]),
            channels=tuple(row["channels"]), motif_id=row["motif_id"],
        )
        for row in payload.get("genome", {}).get("route_blocks", [])
    )
    return AsyncGenome(lane, route_blocks=blocks)


def compile_fixture_anchors(path: Path) -> list[CompiledCandidate]:
    fixture = load_fixture(path)
    run = _source_run()
    result: list[CompiledCandidate] = []
    for lane, anchors in fixture["lanes"].items():
        for anchor in anchors.values():
            source = _find_candidate(run, lane, anchor["candidate_id"], anchor["first_generation_file"])
            if source is None:
                genome = AsyncGenome(lane)
                result.append(_reject(genome, "fixture_candidate_missing", "frozen anchor payload is absent"))
                continue
            candidate = compile_genome(lane, _v3_genome_from_v2(lane, source))
            expected = {
                int(step): rows for step, rows in anchor.get("effective_market_patches", {}).items()
            }
            observed = {int(row["step"]): row["market"] for row in candidate.patches}
            # Fixture provides a concise effective subset for three anchors. For
            # the fourth, compare every source patch so it is still reconstructed.
            base = incumbent_actions(lane)
            source_observed = {
                int(row["step"]): row.get("market")
                for row in source.get("patches", [])
                if row.get("market") is not None
                and row.get("market") != [list(value or []) for value in (base[int(row["step"])].get("market") or [])]
            }
            fixture_match = (all(observed.get(step) == rows for step, rows in expected.items()) and (bool(expected) or observed == source_observed))
            result.append(CompiledCandidate(
                **{**candidate.__dict__, "fixture_candidate_id": anchor["candidate_id"], "fixture_match": fixture_match}
            ))
    return result
