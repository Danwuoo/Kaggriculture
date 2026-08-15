"""Bounded structural-root enumeration, mutation, deduplication, and diversity."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from model import FACTOR_NAMES, FactorMutation, SemanticGenome, SHIFT_VALUES


DEFAULT_MUTATIONS = {
    "maintenance": FactorMutation("maintenance", "first_care", (("operation", "CARE"),)),
    "reclaimed_labor": FactorMutation("reclaimed_labor", "incumbent_followup", (("destination", "incumbent_followup"),)),
    "capacity": FactorMutation("capacity", "headroom_guard", (("min_headroom", 8),)),
    "shipping": FactorMutation("shipping", "advance_first_milk_sale", (("sale_shift", -3),)),
    "market_exposure": FactorMutation("market_exposure", "public_glut_guard", (("max_inventory", 10024), ("min_price", 2))),
    "abandonment": FactorMutation("abandonment", "skip_first_feed", ()),
}


def structural_roots() -> tuple[SemanticGenome, ...]:
    roots = [
        SemanticGenome(structural_root="control"),
        SemanticGenome(structural_root="removal"),
    ]
    roots.extend(SemanticGenome(structural_root="shift", purchase_shift=shift) for shift in SHIFT_VALUES)
    return deduplicate(roots)


def one_factor_frontier(roots: Iterable[SemanticGenome] | None = None) -> tuple[SemanticGenome, ...]:
    """Add one causal mutation per root; never build a factor Cartesian product."""
    result = list(roots or structural_roots())
    for root in tuple(result):
        for factor in FACTOR_NAMES:
            if factor == "reclaimed_labor" and root.structural_root != "removal":
                continue
            result.append(
                SemanticGenome(
                    structural_root=root.structural_root,
                    purchase_shift=root.purchase_shift,
                    mutations=(DEFAULT_MUTATIONS[factor],),
                )
            )
    return deduplicate(result)


def deduplicate(genomes: Iterable[SemanticGenome]) -> tuple[SemanticGenome, ...]:
    rows = {genome.genome_id: genome for genome in genomes}
    return tuple(rows[key] for key in sorted(rows))


def independent_populations() -> dict[str, tuple[SemanticGenome, ...]]:
    population = one_factor_frontier()
    return {
        # Equal semantic genomes are intentional; the lane populations are
        # nevertheless separately owned containers and compile to different IDs.
        "v27_current_meta": tuple(list(population)),
        "boatlee_v16_rc2_market_relay": tuple(list(population)),
    }


def pareto_diversity(
    rows: Iterable[dict[str, Any]],
    *,
    limit: int,
    objectives: tuple[str, ...] = ("paired_margin", "own_bank", "downside"),
) -> tuple[dict[str, Any], ...]:
    """Retain non-dominated rows, then round-robin across semantic niches."""
    values = list(rows)

    def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_values = [float(left.get(key, 0.0)) for key in objectives]
        right_values = [float(right.get(key, 0.0)) for key in objectives]
        # downside is stored as a non-positive value, so larger remains better.
        return all(a >= b for a, b in zip(left_values, right_values)) and any(a > b for a, b in zip(left_values, right_values))

    frontier = [row for row in values if not any(other is not row and dominates(other, row) for other in values)]
    niches: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in frontier:
        niche = (
            row.get("structural_root"),
            row.get("purchase_shift"),
            tuple(row.get("factors") or ()),
        )
        niches[niche].append(row)
    for bucket in niches.values():
        bucket.sort(key=lambda row: tuple(-float(row.get(key, 0.0)) for key in objectives) + (str(row.get("candidate_id", "")),))
    selected: list[dict[str, Any]] = []
    keys = sorted(niches, key=repr)
    while keys and len(selected) < limit:
        remaining = []
        for key in keys:
            bucket = niches[key]
            if bucket and len(selected) < limit:
                selected.append(bucket.pop(0))
            if bucket:
                remaining.append(key)
        keys = remaining
    return tuple(selected)
