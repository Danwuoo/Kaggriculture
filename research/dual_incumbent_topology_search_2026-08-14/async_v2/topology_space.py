"""Static E1b topology capacity and action-operation coverage evidence."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import random
from typing import Any

from compiler import compile_genome, phenotype_id, semantic_noop
from evaluator import TECHNICAL_SEED, engine_fingerprint, run_control
from evolution import ISLANDS, crossover, genome_island, mutate
from library import ROUTES, atomic_json, load_library, load_tape
from model import AsyncGenome, LANES, StaticRejection, payload_hash


OPERATION_FAMILIES = (
    "insertion", "removal", "swap", "time_shift", "quantity", "order_priority",
)
EVENT_FAMILIES = (
    "capital", "market_batching", "buyback", "animal", "build_place",
    "maintenance", "shipping", "production", "terminal_liquidation",
)


def observed_behavior_summary(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Report exact evaluated action changes separately from semantic shape."""
    semantic_nonempty = [row for row in scores if row.get("phenotype_id")]
    changed = [row for row in semantic_nonempty if int(row.get("action_changed_contexts", 0)) > 0]
    unchanged = [row for row in semantic_nonempty if int(row.get("action_changed_contexts", 0)) == 0]
    return {
        "evaluated_compile_nonempty_semantic_phenotypes": len(semantic_nonempty),
        "observed_behavior_changing_phenotypes": len(changed),
        "observed_action_no_op_phenotypes": len(unchanged),
        "observed_behavior_changing_rate": (
            len(changed) / len(semantic_nonempty) if semantic_nonempty else 0.0
        ),
        "observed_action_no_op_candidate_ids": sorted(str(row["candidate_id"]) for row in unchanged),
        "behavior_flag_consistent": all(
            bool(row.get("behavior_changing")) == (int(row.get("action_changed_contexts", 0)) > 0)
            for row in semantic_nonempty
        ),
    }


def _units(action: dict[str, Any]) -> list[list[Any]]:
    return [list(action.get("farmer") or ["PASS"]), *[list(row or ["PASS"]) for row in (action.get("hands") or [])]]


def _market(action: dict[str, Any]) -> list[list[Any]]:
    return [list(row or []) for row in (action.get("market") or [])]


def _signature(order: list[Any]) -> tuple[Any, ...]:
    if len(order) >= 3 and isinstance(order[2], (int, float)):
        return tuple(order[:2])
    return tuple(order)


def _operation_coverage(base: list[dict[str, Any]], donor: list[dict[str, Any]], row: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    temporal_old: dict[tuple[Any, ...], set[int]] = {}
    temporal_new: dict[tuple[Any, ...], set[int]] = {}
    for step in range(int(row["start"]), int(row["end"]) + 1):
        if "unit" in row["channels"]:
            for old, new in zip(_units(base[step]), _units(donor[step])):
                temporal_old.setdefault(_signature(old), set()).add(step)
                temporal_new.setdefault(_signature(new), set()).add(step)
                if old == new:
                    continue
                if old[:1] == ["PASS"] and new[:1] != ["PASS"]:
                    found.add("insertion")
                elif new[:1] == ["PASS"] and old[:1] != ["PASS"]:
                    found.add("removal")
                else:
                    found.add("swap")
                    if len(old) >= 3 and len(new) >= 3 and old[:2] == new[:2] and old[2] != new[2]:
                        found.add("quantity")
        if "market" in row["channels"]:
            old_market, new_market = _market(base[step]), _market(donor[step])
            for order in old_market:
                temporal_old.setdefault(_signature(order), set()).add(step)
            for order in new_market:
                temporal_new.setdefault(_signature(order), set()).add(step)
            if Counter(map(tuple, old_market)) == Counter(map(tuple, new_market)) and old_market != new_market:
                found.add("order_priority")
            old_counts, new_counts = Counter(map(tuple, old_market)), Counter(map(tuple, new_market))
            if any(new_counts[key] > old_counts[key] for key in new_counts):
                found.add("insertion")
            if any(old_counts[key] > new_counts[key] for key in old_counts):
                found.add("removal")
            if old_market != new_market and old_market and new_market:
                found.add("swap")
            old_quantities = {(o[0], o[1]): o[2] for o in old_market if len(o) >= 3}
            new_quantities = {(o[0], o[1]): o[2] for o in new_market if len(o) >= 3}
            if any(key in new_quantities and new_quantities[key] != value for key, value in old_quantities.items()):
                found.add("quantity")
    if any(
        signature in temporal_new and temporal_old[signature] != temporal_new[signature]
        for signature in temporal_old
        if signature and signature != ("PASS",)
    ):
        found.add("time_shift")
    return found


def _event_coverage(donor: list[dict[str, Any]], row: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for step in range(int(row["start"]), int(row["end"]) + 1):
        orders = []
        if "unit" in row["channels"]:
            orders.extend(_units(donor[step]))
        if "market" in row["channels"]:
            orders.extend(_market(donor[step]))
        opcodes = [str(order[0]) for order in orders if order]
        if any(op in {"HIRE", "BUY_LAND", "BUY_SEED", "BUY_ANIMAL"} for op in opcodes):
            found.add("capital")
        if sum(op in {"BUY_PRODUCT", "SELL"} for op in opcodes) >= 2:
            found.add("market_batching")
        if "BUY_PRODUCT" in opcodes:
            found.add("buyback")
        if any(op in {"BUY_ANIMAL", "FEED", "CARE", "COLLECT_FERTILIZER"} for op in opcodes):
            found.add("animal")
        if any(op in {"BUILD_COOP", "BUILD_PASTURE", "PLACE"} for op in opcodes):
            found.add("build_place")
        if any(op in {"WATER", "FEED", "CARE", "DIG"} for op in opcodes):
            found.add("maintenance")
        if any(op in {"PICKUP", "DROP", "PLACE", "SELL"} for op in opcodes):
            found.add("shipping")
        if any(op in {"PLANT", "FERTILIZE", "HARVEST", "COLLECT_FERTILIZER"} for op in opcodes):
            found.add("production")
        if int(row["end"]) >= 672 and "SELL" in opcodes:
            found.add("terminal_liquidation")
    return found


def _coverage(library: dict[str, Any], lane: str) -> dict[str, Any]:
    base = json.loads(ROUTES[lane].read_text(encoding="utf-8"))
    operations: Counter[str] = Counter()
    events: Counter[str] = Counter()
    opcode_counts: Counter[str] = Counter()
    for row in library["lanes"][lane]["motifs"]:
        donor = load_tape(row["source_tape"])
        operations.update(_operation_coverage(base, donor, row))
        events.update(_event_coverage(donor, row))
        opcode_counts.update(row.get("structural_opcodes") or [])
    return {
        "operation_motif_counts": {key: operations[key] for key in OPERATION_FAMILIES},
        "event_motif_counts": {key: events[key] for key in EVENT_FAMILIES},
        "structural_opcode_counts": dict(sorted(opcode_counts.items())),
    }


def _compile_capacity(
    lane: str,
    library: dict[str, Any],
    trace: list[Any],
    target: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random((int(seed) << 12) ^ sum(map(ord, lane)))
    parents: dict[str, list[AsyncGenome]] = {island: [AsyncGenome()] for island in ISLANDS}
    genomes: set[str] = set()
    compile_nonempty_phenotypes: set[str] = set()
    candidate_ids: list[str] = []
    island_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    maximum_windows = 0
    attempts = 0
    island_index = 0
    while len(compile_nonempty_phenotypes) < int(target) and attempts < int(target) * 800:
        attempts += 1
        island = ISLANDS[island_index % len(ISLANDS)]
        island_index += 1
        pool = parents[island]
        parent = rng.choice(pool[-256:])
        child = mutate(parent, lane, library, rng, island=island)
        if island == "coupled" and rng.random() < 0.72:
            other = rng.choice([row for values in parents.values() for row in values[-64:]])
            child = crossover(child, other, rng)
            child = mutate(child, lane, library, rng, island="coupled")
        if child.genome_id in genomes:
            continue
        genomes.add(child.genome_id)
        result = compile_genome(lane, child, library, trace)
        if isinstance(result, StaticRejection):
            rejection_counts[result.code] += 1
            continue
        if semantic_noop(result):
            rejection_counts["semantic_no_op"] += 1
            continue
        phenotype = phenotype_id(result)
        if phenotype in compile_nonempty_phenotypes:
            rejection_counts["duplicate_phenotype"] += 1
            continue
        compile_nonempty_phenotypes.add(phenotype)
        resolved_island = genome_island(child)
        island_counts[resolved_island] += 1
        parents[island].append(child)
        candidate_ids.append(result.candidate_id)
        maximum_windows = max(maximum_windows, len(result.windows))
    if len(compile_nonempty_phenotypes) < int(target):
        raise RuntimeError(
            f"{lane} produced only {len(compile_nonempty_phenotypes)}/{target} "
            "compile-distinct nonempty semantic phenotypes"
        )
    return {
        "target": int(target),
        "attempts": attempts,
        "unique_genomes": len(genomes),
        "compile_distinct_nonempty_semantic_phenotypes": len(compile_nonempty_phenotypes),
        "candidate_id_digest": payload_hash(sorted(candidate_ids)),
        "phenotype_id_digest": payload_hash(sorted(compile_nonempty_phenotypes)),
        "island_counts": dict(sorted(island_counts.items())),
        "maximum_event_linked_windows": maximum_windows,
        "rejection_counts": dict(sorted(rejection_counts.items())),
    }


def build_capacity_evidence(
    library_path: Path,
    output: Path,
    *,
    target_per_lane: int = 1500,
    proposal_seed: int = 811407,
) -> dict[str, Any]:
    if proposal_seed != TECHNICAL_SEED:
        raise PermissionError("E1b topology capacity proof is restricted to technical seed 811407")
    if not 1000 <= int(target_per_lane) <= 2000:
        raise ValueError("target_per_lane must be in 1000..2000")
    library = load_library(library_path)
    traces = {
        lane: run_control(lane, "other_incumbent", TECHNICAL_SEED, 0, capture_trace=True).trace
        for lane in LANES
    }
    lanes = {}
    for lane in LANES:
        lanes[lane] = {
            **_compile_capacity(lane, library, traces[lane], int(target_per_lane), proposal_seed),
            **_coverage(library, lane),
        }
    checks = {
        "compile_distinct_nonempty_capacity": all(
            1000 <= row["compile_distinct_nonempty_semantic_phenotypes"] <= 2000
            for row in lanes.values()
        ),
        "four_lane_local_islands": all(all(row["island_counts"].get(island, 0) > 0 for island in ISLANDS) for row in lanes.values()),
        "window_bound": all(row["maximum_event_linked_windows"] <= 8 for row in lanes.values()),
        "operation_coverage": all(all(row["operation_motif_counts"].get(name, 0) > 0 for name in OPERATION_FAMILIES) for row in lanes.values()),
        "event_coverage": all(all(row["event_motif_counts"].get(name, 0) > 0 for name in EVENT_FAMILIES) for row in lanes.values()),
    }
    body = {
        "schema_version": 2,
        "purpose": (
            "static plus technical-seed compile-distinct nonempty semantic capacity; "
            "not an observed behavior-change or efficacy claim"
        ),
        "technical_seed": TECHNICAL_SEED,
        "formal_fresh_seeds_executed": False,
        "e1_seeds_reexecuted": False,
        "engine": engine_fingerprint(),
        "library_sha256": library["library_sha256"],
        "lanes": lanes,
        "checks": checks,
        "pass": all(checks.values()),
    }
    result = {**body, "topology_capacity_sha256": payload_hash(body)}
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-per-lane", type=int, default=1500)
    args = parser.parse_args()
    evidence = build_capacity_evidence(args.library, args.output, target_per_lane=args.target_per_lane)
    print(json.dumps({"pass": evidence["pass"], "sha256": evidence["topology_capacity_sha256"], "output": str(args.output)}, sort_keys=True))
