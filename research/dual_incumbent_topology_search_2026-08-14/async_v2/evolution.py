"""Deterministic multi-gene mutation, crossover, and lane Pareto selection."""

from __future__ import annotations

from dataclasses import replace
import random
from typing import Any, Iterable

from library import gene_from_motif
from model import (
    AsyncGenome,
    ConstantGene,
    MarketPolicyGene,
    PRODUCTS,
    constant_domains,
)


DEFAULTS = {
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
ISLANDS = ("route", "market", "constants", "coupled")


def genome_island(genome: AsyncGenome) -> str:
    present = sum(bool(rows) for rows in (genome.route_blocks, genome.market_policy, genome.constants))
    if present > 1:
        return "coupled"
    if genome.route_blocks:
        return "route"
    if genome.market_policy:
        return "market"
    if genome.constants:
        return "constants"
    return "coupled"


def _construct(blocks: Iterable[Any], policy: Iterable[Any], constants: Iterable[Any]) -> AsyncGenome | None:
    try:
        return AsyncGenome(tuple(blocks), tuple(policy), tuple(constants))
    except ValueError:
        return None


def _motifs(library: dict[str, Any], lane: str, channel: str | None = None) -> list[dict[str, Any]]:
    rows = library["lanes"][lane]["motifs"]
    if channel is not None:
        rows = [row for row in rows if channel in row["channels"]]
    return sorted(rows, key=lambda row: (row["source_rank"], row["start"], row["end"], row["motif_id"]))


def _set_policy(genome: AsyncGenome, gene: MarketPolicyGene) -> AsyncGenome | None:
    rows = [row for row in genome.market_policy if row.product != gene.product]
    rows.append(gene)
    return _construct(genome.route_blocks, rows, genome.constants)


def _set_constant(genome: AsyncGenome, gene: ConstantGene) -> AsyncGenome | None:
    rows = [row for row in genome.constants if row.name != gene.name]
    if DEFAULTS.get(gene.name) != gene.value:
        rows.append(gene)
    return _construct(genome.route_blocks, genome.market_policy, rows)


def mutate(
    genome: AsyncGenome,
    lane: str,
    library: dict[str, Any],
    rng: random.Random,
    *,
    island: str | None = None,
) -> AsyncGenome:
    if island is not None and island not in ISLANDS:
        raise ValueError(island)
    operations = {
        "route": ["add_block", "remove_block"],
        "market": ["market"],
        "constants": ["constant"],
        "coupled": ["add_block", "remove_block", "market", "constant"],
        None: ["add_block", "remove_block", "market", "constant"],
    }[island]
    for _ in range(64):
        operation = rng.choice(operations)
        candidate: AsyncGenome | None = None
        if operation == "add_block" and len(genome.route_blocks) < 8:
            row = rng.choice(_motifs(library, lane))
            candidate = _construct((*genome.route_blocks, gene_from_motif(row)), genome.market_policy, genome.constants)
        elif operation == "remove_block" and genome.route_blocks:
            dropped = rng.randrange(len(genome.route_blocks))
            candidate = _construct([row for index, row in enumerate(genome.route_blocks) if index != dropped], genome.market_policy, genome.constants)
        elif operation == "market":
            product = rng.choice(PRODUCTS)
            gene = MarketPolicyGene(
                product=product,
                min_price_bps=rng.choice((0, 7500, 10000, 12500, 15000)),
                max_public_inventory=rng.choice((9000, 9500, 10000, 10500, 11000, 20000)),
                quantity_bps=rng.choice((0, 5000, 7500, 10000)),
            )
            candidate = _set_policy(genome, gene)
        elif operation == "constant":
            domains = constant_domains(lane)
            name = rng.choice(sorted(domains))
            candidate = _set_constant(genome, ConstantGene(name, rng.choice(domains[name])))
        if candidate is not None and candidate.genome_id != genome.genome_id:
            if island in {"route", "market", "constants"} and genome_island(candidate) != island:
                continue
            return candidate
    return genome


def crossover(left: AsyncGenome, right: AsyncGenome, rng: random.Random) -> AsyncGenome:
    blocks = [row for row in (*left.route_blocks, *right.route_blocks) if rng.random() < 0.5]
    policy_by_product = {}
    for row in (*left.market_policy, *right.market_policy):
        if row.product not in policy_by_product or rng.random() < 0.5:
            policy_by_product[row.product] = row
    constant_by_name = {}
    for row in (*left.constants, *right.constants):
        if row.name not in constant_by_name or rng.random() < 0.5:
            constant_by_name[row.name] = row
    # Greedily retain non-conflicting blocks; canonical construction enforces
    # the same constraint after crossover.
    kept = []
    for row in sorted(set(blocks)):
        proposal = _construct((*kept, row), policy_by_product.values(), constant_by_name.values())
        if proposal is not None:
            kept.append(row)
    return _construct(kept, policy_by_product.values(), constant_by_name.values()) or left


def initial_genomes(lane: str, library: dict[str, Any], size: int, seed: int) -> list[AsyncGenome]:
    rng = random.Random((int(seed) << 8) ^ sum(map(ord, lane)))
    result: list[AsyncGenome] = []
    island_cycle = [ISLANDS[index % len(ISLANDS)] for index in range(max(2, int(size)))]
    while len(result) < max(2, int(size)):
        island = island_cycle[len(result)]
        compatible = [row for row in result if genome_island(row) == island]
        parent = rng.choice(compatible) if compatible else AsyncGenome()
        child = mutate(parent, lane, library, rng, island=island)
        if island == "coupled" and len(result) >= 2 and rng.random() < 0.7:
            child = crossover(child, rng.choice(result), rng)
            child = mutate(child, lane, library, rng, island="coupled")
        if child.genome_id not in {row.genome_id for row in result}:
            result.append(child)
    return result[: int(size)]


def next_generation(
    lane: str,
    library: dict[str, Any],
    parents: list[AsyncGenome],
    size: int,
    seed: int,
    generation: int,
) -> list[AsyncGenome]:
    rng = random.Random((int(seed) << 16) ^ (generation << 4) ^ sum(map(ord, lane)))
    result: list[AsyncGenome] = []
    island_cycle = [ISLANDS[index % len(ISLANDS)] for index in range(int(size))]
    while len(result) < int(size):
        island = island_cycle[len(result)]
        pool = [row for row in parents if genome_island(row) == island]
        left = rng.choice(pool or parents or result or [AsyncGenome()])
        child = left
        crossover_pool = pool if len(pool) >= 2 else parents
        if len(crossover_pool) >= 2 and rng.random() < 0.7:
            child = crossover(left, rng.choice(crossover_pool), rng)
        for _ in range(1 + int(rng.random() < 0.65)):
            child = mutate(child, lane, library, rng, island=island)
        if child.genome_id not in {row.genome_id for row in result}:
            result.append(child)
    return result


def ranking_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Robust near-tie order; opponent consistency precedes mean uplift."""
    paired = row.get("paired_wdl", {})
    return (
        -int(bool(row.get("technical_pass"))),
        -int(row.get("actual_win_delta", 0)),
        -(int(paired.get("win", 0)) - int(paired.get("loss", 0))),
        -int(row.get("opponent_positive_families", 0)),
        -float(row.get("opponent_worst_mean_margin", float("-inf"))),
        -float(row.get("worst_paired_margin", float("-inf"))),
        -float(row.get("mean_paired_margin", float("-inf"))),
        -float(row.get("mean_own_bank", float("-inf"))),
        int(row.get("complexity", 0)),
        str(row.get("candidate_id", "")),
    )


def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_paired = left.get("paired_wdl", {})
    right_paired = right.get("paired_wdl", {})
    maximize = (
        (int(left.get("actual_win_delta", 0)), int(right.get("actual_win_delta", 0))),
        (int(left_paired.get("win", 0)) - int(left_paired.get("loss", 0)), int(right_paired.get("win", 0)) - int(right_paired.get("loss", 0))),
        (int(left.get("opponent_positive_families", 0)), int(right.get("opponent_positive_families", 0))),
        (float(left.get("opponent_worst_mean_margin", float("-inf"))), float(right.get("opponent_worst_mean_margin", float("-inf")))),
        (float(left.get("worst_paired_margin", float("-inf"))), float(right.get("worst_paired_margin", float("-inf")))),
        (float(left.get("mean_paired_margin", float("-inf"))), float(right.get("mean_paired_margin", float("-inf")))),
        (float(left.get("mean_own_bank", float("-inf"))), float(right.get("mean_own_bank", float("-inf")))),
        (-int(left.get("complexity", 0)), -int(right.get("complexity", 0))),
    )
    return all(a >= b for a, b in maximize) and any(a > b for a, b in maximize)


def deduplicate_scores(scores: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: dict[str, dict[str, Any]] = {}
    duplicates = []
    for row in sorted(scores, key=ranking_key):
        identity = str(
            row.get("action_digest_vector_sha256")
            or row.get("phenotype_id")
            or row.get("candidate_id")
        )
        if identity in kept:
            duplicates.append({
                "identity": identity,
                "candidate_id": row.get("candidate_id"),
                "representative_candidate_id": kept[identity].get("candidate_id"),
            })
        else:
            kept[identity] = row
    return list(kept.values()), duplicates


def pareto(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique, _ = deduplicate_scores(scores)
    valid = [
        row for row in unique
        if row.get("technical_pass") and row.get("efficacy_eligible", True)
    ]
    result = [row for row in valid if not any(dominates(other, row) for other in valid if other is not row)]
    return sorted(result, key=ranking_key)
