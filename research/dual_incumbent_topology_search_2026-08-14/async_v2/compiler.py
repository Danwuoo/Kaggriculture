"""Compile multi-gene route and policy genomes against one incumbent trace."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable

from library import ROUTES, file_sha256, load_tape
from model import (
    AsyncGenome,
    CompiledAsyncCandidate,
    LANES,
    StaticRejection,
    constant_domains,
)


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTROLS = {lane: ROOT / "research" / "main_approach" / lane / "main.py" for lane in LANES}
MOVE = {"EAST": (1, 0), "SOUTH": (0, 1), "WEST": (-1, 0), "NORTH": (0, -1)}
PRIVATE_REQUIRED = frozenset({"PLANT", "PLACE"})
SEMANTIC_VERSION = "async-e1b-phenotype-v1"
RUNTIME_DEFAULTS = {
    "demand_alpha_milli": 250,
    "weed_replay_steps": 8,
    "max_market_orders": 10,
    "livestock_switch_step": 161,
    "wool_gate_scale_bps": 10000,
    "wool_pressure": 78,
    "wool_batch": 16,
    "wool_gap": 6,
    "relay_distance_max": 8,
    "relay_lead": 3,
    "relay_first": 278,
    "relay_last": 662,
}


def _positions(observation: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    seat = 1 if int(observation.get("player", 0) or 0) == 1 else 0
    farms = observation.get("farms", []) or []
    farm = farms[seat] if seat < len(farms) else {}
    rows = [farm.get("farmer"), *(farm.get("hands", []) or [])]
    return tuple(tuple(map(int, row)) for row in rows)


def _units(action: dict[str, Any]) -> list[list[Any]]:
    return [list(action.get("farmer") or ["PASS"]), *[list(row or ["PASS"]) for row in (action.get("hands") or [])]]


def _market(action: dict[str, Any]) -> list[list[Any]]:
    return [list(row or []) for row in (action.get("market") or [])]


def _move(position: tuple[int, int], order: list[Any]) -> tuple[int, int]:
    if not order or order[0] not in MOVE:
        return position
    dx, dy = MOVE[order[0]]
    return max(0, min(9, position[0] + dx)), max(0, min(9, position[1] + dy))


def _reject(lane: str, genome: AsyncGenome, code: str, detail: str, **evidence: Any) -> StaticRejection:
    return StaticRejection(lane, genome.genome_id, code, detail, tuple(sorted(evidence.items())))


def _trace_map(trace: Iterable[Any]) -> dict[int, Any]:
    return {int(frame.step): frame for frame in trace}


def _window_contract(
    lane: str,
    genome: AsyncGenome,
    gene: Any,
    donor: list[dict[str, Any]],
    trace: dict[int, Any],
) -> tuple[dict[str, Any] | None, StaticRejection | None]:
    start, end = int(gene.start), int(gene.end)
    if start not in trace or end + 1 not in trace:
        return None, _reject(lane, genome, "reference_trace_gap", "route block lacks entry or rejoin trace", start=start, end=end)
    entry_positions = _positions(trace[start].observation)
    rejoin_positions = _positions(trace[end + 1].observation)
    expected: dict[str, list[list[int]]] = {}
    positions = entry_positions
    if "unit" in gene.channels:
        for step in range(start, end + 1):
            units = _units(donor[step])
            if len(units) != len(positions):
                return None, _reject(
                    lane, genome, "actor_count_incompatible", "donor unit block changes the active actor count",
                    step=step, expected=len(positions), donor=len(units), motif_id=gene.motif_id,
                )
            expected[str(step)] = [list(row) for row in positions]
            positions = tuple(_move(position, order) for position, order in zip(positions, units))
        if positions != rejoin_positions:
            return None, _reject(
                lane, genome, "actor_rejoin_mismatch", "donor unit path does not rejoin the incumbent actor positions",
                motif_id=gene.motif_id, start=start, end=end,
                candidate=[list(row) for row in positions], incumbent=[list(row) for row in rejoin_positions],
            )
    return {
        "window_id": gene.motif_id,
        "start": start,
        "end": end,
        "rejoin_step": end + 1,
        "channels": list(gene.channels),
        "entry_positions": [list(row) for row in entry_positions],
        "expected_positions": expected,
        "rejoin_positions": [list(row) for row in rejoin_positions],
        "fallback": "incumbent",
    }, None


def _displaced_units(step: int, base: list[list[Any]], candidate: list[list[Any]], motif_id: str) -> list[dict[str, Any]]:
    result = []
    for actor, (old, new) in enumerate(zip(base, candidate)):
        if old == new:
            continue
        disposition = "reclaimed" if new[:1] == ["PASS"] and old[:1] != ["PASS"] else "reassigned"
        result.append({
            "step": step, "channel": "unit", "actor": actor, "incumbent": old,
            "candidate": new, "disposition": disposition, "destination": motif_id,
        })
    return result


def _displaced_market(step: int, base: list[list[Any]], candidate: list[list[Any]], motif_id: str) -> list[dict[str, Any]]:
    remaining = Counter(tuple(row) for row in candidate)
    result = []
    for old in base:
        key = tuple(old)
        if remaining[key] > 0:
            remaining[key] -= 1
            result.append({
                "step": step, "channel": "market", "actor": None, "incumbent": old,
                "candidate": old, "disposition": "retained", "destination": motif_id,
            })
        else:
            result.append({
                "step": step, "channel": "market", "actor": None, "incumbent": old,
                "candidate": ["PASS"], "disposition": "reclaimed", "destination": motif_id,
            })
    for order, count in sorted(remaining.items()):
        for _ in range(count):
            result.append({
                "step": step, "channel": "market", "actor": None, "incumbent": ["PASS"],
                "candidate": list(order), "disposition": "reassigned", "destination": motif_id,
            })
    return result


def compile_genome(
    lane: str,
    genome: AsyncGenome,
    library: dict[str, Any],
    reference_trace: Iterable[Any],
) -> CompiledAsyncCandidate | StaticRejection:
    if lane not in LANES:
        raise ValueError(lane)
    if library["lanes"][lane]["route_sha256"] != __import__("model").payload_hash(
        json.loads(ROUTES[lane].read_text(encoding="utf-8"))
    ):
        return _reject(lane, genome, "incumbent_route_changed", "library route hash no longer matches the lane")
    domains = constant_domains(lane)
    for gene in genome.constants:
        if gene.name not in domains or int(gene.value) not in domains[gene.name]:
            return _reject(lane, genome, "constant_out_of_domain", "lane does not own this constant value", name=gene.name, value=gene.value)
    motif_rows = {row["motif_id"]: row for row in library["lanes"][lane]["motifs"]}
    base = json.loads(ROUTES[lane].read_text(encoding="utf-8"))
    trace = _trace_map(reference_trace)
    donors: dict[str, list[dict[str, Any]]] = {}
    windows = []
    patches: dict[int, dict[str, Any]] = {}
    displaced: list[dict[str, Any]] = []
    for gene in genome.route_blocks:
        row = motif_rows.get(gene.motif_id)
        if row is None:
            return _reject(lane, genome, "unknown_motif", "motif is not present in the frozen lane library", motif_id=gene.motif_id)
        if (
            row["source_tape"] != gene.source_tape or int(row["start"]) != gene.start
            or int(row["end"]) != gene.end or tuple(sorted(row["channels"])) != gene.channels
        ):
            return _reject(lane, genome, "motif_payload_mismatch", "gene metadata differs from the frozen motif")
        donor = donors.setdefault(gene.source_tape, load_tape(gene.source_tape))
        window, rejection = _window_contract(lane, genome, gene, donor, trace)
        if rejection is not None:
            return rejection
        windows.append(window)
        for step in range(gene.start, gene.end + 1):
            patch = patches.setdefault(step, {"step": step, "unit": None, "market": None, "window_ids": []})
            patch["window_ids"].append(gene.motif_id)
            if "unit" in gene.channels:
                old_units, new_units = _units(base[step]), _units(donor[step])
                patch["unit"] = new_units
                displaced.extend(_displaced_units(step, old_units, new_units, gene.motif_id))
                patch["private_required"] = any(order and order[0] in PRIVATE_REQUIRED for order in new_units)
            if "market" in gene.channels:
                old_market, new_market = _market(base[step]), _market(donor[step])
                if len(new_market) > 10:
                    return _reject(lane, genome, "donor_market_overflow", "donor motif has more than ten market orders", step=step)
                patch["market"] = new_market
                displaced.extend(_displaced_market(step, old_market, new_market, gene.motif_id))
    for patch in patches.values():
        patch["window_ids"] = sorted(set(patch["window_ids"]))
        patch.setdefault("private_required", False)
    policy = tuple(gene.payload() for gene in genome.market_policy)
    return CompiledAsyncCandidate(
        lane=lane,
        genome=genome,
        control_sha256=file_sha256(CONTROLS[lane]),
        library_sha256=library["library_sha256"],
        windows=tuple(sorted(windows, key=lambda row: (row["start"], row["end"], row["window_id"]))),
        patches=tuple(patches[step] for step in sorted(patches)),
        constants=tuple((row.name, int(row.value)) for row in genome.constants),
        market_policy=policy,
        displaced_actions=tuple(displaced),
    )


def semantic_payload(candidate: CompiledAsyncCandidate) -> dict[str, Any]:
    """Canonical behavior surface used before any efficacy game is scheduled.

    Candidate IDs preserve exact genome provenance.  This payload deliberately
    removes provenance-only windows and genes that cannot change a route or a
    lane-owned runtime decision, so distinct genomes with one executable
    phenotype share one semantic identity.
    """
    base = json.loads(ROUTES[candidate.lane].read_text(encoding="utf-8"))
    effective_patches = []
    effective_window_ids: set[str] = set()
    sell_products = {
        str(order[1])
        for action in base
        for order in _market(action)
        if len(order) >= 3 and order[0] == "SELL"
    }
    for raw in candidate.patches:
        patch = dict(raw)
        step = int(patch["step"])
        effective: dict[str, Any] = {"step": step}
        if patch.get("unit") is not None and list(patch["unit"]) != _units(base[step]):
            effective["unit"] = patch["unit"]
        if patch.get("market") is not None and list(patch["market"]) != _market(base[step]):
            effective["market"] = patch["market"]
            sell_products.update(
                str(order[1])
                for order in patch["market"]
                if len(order) >= 3 and order[0] == "SELL"
            )
        if len(effective) > 1:
            effective_window_ids.update(str(value) for value in (patch.get("window_ids") or []))
            effective["private_required"] = bool(patch.get("private_required"))
            effective_patches.append(effective)

    # Boatlee may create WOOL sales dynamically even when the fixed tape does
    # not contain a sale at the same step.
    if candidate.lane == "boatlee_v16_rc2_market_relay":
        sell_products.add("WOOL")
        sell_products.add("FERTILIZER")
    effective_policy = []
    for row in candidate.market_policy:
        policy = dict(row)
        is_identity = (
            int(policy["min_price_bps"]) == 0
            and int(policy["max_public_inventory"]) == 20000
            and int(policy["quantity_bps"]) == 10000
        )
        if not is_identity and policy["product"] in sell_products:
            effective_policy.append(policy)
    return {
        "semantic_version": SEMANTIC_VERSION,
        "lane": candidate.lane,
        "control_sha256": candidate.control_sha256,
        "windows": sorted(
            [
                {key: value for key, value in dict(window).items() if key != "window_id"}
                for window in candidate.windows
                if str(window.get("window_id")) in effective_window_ids
            ],
            key=lambda row: (int(row["start"]), int(row["end"]), tuple(row["channels"])),
        ),
        "patches": effective_patches,
        "market_policy": sorted(effective_policy, key=lambda row: row["product"]),
        "constants": [
            [name, int(value)]
            for name, value in candidate.constants
            if RUNTIME_DEFAULTS.get(name) != int(value)
        ],
    }


def phenotype_id(candidate: CompiledAsyncCandidate) -> str:
    return __import__("model").stable_id("ph", semantic_payload(candidate))


def semantic_noop(candidate: CompiledAsyncCandidate) -> bool:
    payload = semantic_payload(candidate)
    return not any((payload["patches"], payload["market_policy"], payload["constants"]))
