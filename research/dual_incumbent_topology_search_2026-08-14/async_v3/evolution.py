"""Deterministic, lane-local population construction and bounded evolution."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from model import AsyncGenome, ConstantGene, GuardGene, MarketEditGene, RouteBlockGene
from registry import lane_registry


ISLANDS = ("route", "market", "constants", "guard", "coupled")
OPERATIONS = ("insert", "remove", "replace", "move", "quantity")
OPCODES = ("HIRE", "BUY_LAND", "BUY_ANIMAL", "BUY_SEED", "BUY_PRODUCT", "SELL")


def island(genome: AsyncGenome) -> str:
    count = sum(bool(value) for value in (genome.route_blocks, genome.market_edits, genome.constants))
    if count > 1:
        return "coupled"
    return "route" if genome.route_blocks else "market" if genome.market_edits else "constants"


def _with(
    genome: AsyncGenome,
    *,
    blocks: tuple[RouteBlockGene, ...] | None = None,
    edits: tuple[MarketEditGene, ...] | None = None,
    constants: tuple[ConstantGene, ...] | None = None,
    mutation: str,
    bundle: str | None = None,
) -> AsyncGenome:
    return AsyncGenome(
        genome.lane, genome.route_blocks if blocks is None else blocks,
        genome.market_edits if edits is None else edits,
        genome.constants if constants is None else constants,
        parent_id=genome.genome_id, mutation_id=mutation,
        causal_bundle_id=bundle if bundle is not None else genome.causal_bundle_id,
    )


def _order(opcode: str, quantity: int = 1) -> tuple[object, ...]:
    return {
        "HIRE": ("HIRE",), "BUY_LAND": ("BUY_LAND",), "BUY_ANIMAL": ("BUY_ANIMAL", "COW", quantity),
        "BUY_SEED": ("BUY_SEED", "MELON", quantity), "BUY_PRODUCT": ("BUY_PRODUCT", "WHEAT", quantity),
        "SELL": ("SELL", "WOOL", quantity),
    }[opcode]


def _route_template(genome: AsyncGenome) -> RouteBlockGene | None:
    if genome.route_blocks:
        return genome.route_blocks[0]
    # A lane cannot borrow an editable route from the other lane.  Population
    # roots supply provenance; a bare control has no route mutation surface.
    return None


def _mutate_route(genome: AsyncGenome) -> tuple[AsyncGenome, str]:
    block = _route_template(genome)
    if block is None:
        return _mutate_constant(genome)
    if block.end - block.start + 1 > 8:
        changed = RouteBlockGene(block.source_tape, block.start + 1, block.end, block.channels, block.motif_id)
    elif block.end < 717:
        changed = RouteBlockGene(block.source_tape, block.start, block.end + 1, block.channels, block.motif_id)
    else:
        changed = RouteBlockGene(block.source_tape, block.start - 1, block.end, block.channels, block.motif_id)
    return _with(genome, blocks=(changed,) + genome.route_blocks[1:], mutation="route_window_shift"), "route_window_shift"


def _mutate_market(genome: AsyncGenome, operation: str, opcode: str) -> tuple[AsyncGenome, str]:
    edits = list(genome.market_edits)
    step = edits[0].step if edits else 0
    sequence = max((row.sequence for row in edits if row.step == step), default=-1) + 1
    source = edits[0] if edits else MarketEditGene(step, 0, "insert", 0, order=_order(opcode))
    target = source.target_index if source.target_index is not None else 0
    supplied = _order(opcode, 2 if opcode not in {"HIRE", "BUY_LAND"} else 1)
    if operation == "insert":
        fresh = MarketEditGene(step, sequence, "insert", min(len(edits), 9), order=supplied)
        edits.append(fresh)
    else:
        # All operation kinds retain an explicit full order.  The compiler
        # later rejects a state-incompatible edit; it is never silently fixed.
        expected = source.order or supplied
        if operation == "replace":
            expected = supplied
        elif operation == "quantity":
            if len(expected) != 3:
                expected = ("SELL", "WOOL", 1)
            else:
                expected = (expected[0], expected[1], max(1, min(999, int(expected[2]) + 1)))
        fresh = MarketEditGene(step, sequence, operation, min(target + 1, 9), order=expected, target_index=target)
        edits.append(fresh)
    return _with(genome, edits=tuple(edits), mutation=f"market_{operation}_{opcode.lower()}"), f"market_{operation}_{opcode.lower()}"


def _mutate_guard(genome: AsyncGenome) -> tuple[AsyncGenome, str]:
    edits = list(genome.market_edits)
    if edits:
        old = edits[0]
        order = old.order or ("SELL", "WOOL", 1)
        if len(order) < 2 or order[0] != "SELL":
            order = ("SELL", "WOOL", 1)
            operation, target = "insert", None
        else:
            operation, target = old.operation, old.target_index
        edits[0] = MarketEditGene(old.step, old.sequence, operation, old.queue_index, order=order, target_index=target, guard=GuardGene("min_price", "WOOL", 1), dependency=old.dependency)
    else:
        edits.append(MarketEditGene(0, 0, "insert", 0, order=("SELL", "WOOL", 1), guard=GuardGene("min_price", "WOOL", 1)))
    return _with(genome, edits=tuple(edits), mutation="public_guard_min_price"), "public_guard_min_price"


def declared_market_surface(genome: AsyncGenome) -> list[AsyncGenome]:
    """One representative for every formal market operation/opcode plus guard."""
    rows = [_mutate_market(genome, operation, opcode)[0] for operation in OPERATIONS for opcode in OPCODES]
    rows.append(_mutate_guard(genome)[0])
    return list(dict.fromkeys(rows))


def _mutate_constant(genome: AsyncGenome) -> tuple[AsyncGenome, str]:
    constants = lane_registry(genome.lane)
    name = sorted(constants)[0]
    domain = tuple(constants[name]["domain"])
    current = next((row.value for row in genome.constants if row.name == name), constants[name]["default"])
    value = next(item for item in domain if item != current)
    rows = tuple(row for row in genome.constants if row.name != name) + (ConstantGene(name, int(value)),)
    return _with(genome, constants=rows, mutation="live_constant_step"), "live_constant_step"


def mutate_one(genome: AsyncGenome, *, seed: int) -> tuple[AsyncGenome, dict[str, Any]]:
    """Change one declared causal atom, choosing across the complete surface."""
    rng = random.Random(seed)
    surface = ("route", "market", "guard", "constant", "coupled")
    choice = surface[rng.randrange(len(surface))]
    if choice == "route":
        child, mutation = _mutate_route(genome)
    elif choice == "market":
        child, mutation = _mutate_market(genome, OPERATIONS[rng.randrange(len(OPERATIONS))], OPCODES[rng.randrange(len(OPCODES))])
    elif choice == "guard":
        child, mutation = _mutate_guard(genome)
    elif choice == "constant":
        child, mutation = _mutate_constant(genome)
    else:
        route, _ = _mutate_route(genome)
        child, market = _mutate_market(route, "insert", "SELL")
        child = AsyncGenome(child.lane, child.route_blocks, child.market_edits, child.constants, parent_id=genome.genome_id, mutation_id="coupled_route_market", causal_bundle_id=route.route_blocks[0].motif_id if route.route_blocks else None)
        mutation = "coupled_route_market"
    return child, {"parent_id": genome.genome_id, "child_id": child.genome_id, "changed_atoms": 1, "mutation_id": mutation, "surface": choice}


def crossover(left: AsyncGenome, right: AsyncGenome, *, seed: int) -> AsyncGenome:
    if left.lane != right.lane:
        raise ValueError("cross-lane crossover is forbidden")
    rng = random.Random(seed)
    blocks = left.route_blocks if rng.randrange(2) == 0 else right.route_blocks
    edits = left.market_edits if rng.randrange(2) == 0 else right.market_edits
    constants = left.constants if rng.randrange(2) == 0 else right.constants
    dependencies = {block.motif_id for block in blocks}
    edits = tuple(row for row in edits if row.dependency is None or row.dependency in dependencies)
    return AsyncGenome(left.lane, blocks, edits, constants, parent_id=left.genome_id, mutation_id="dependency_preserving_crossover", causal_bundle_id=left.causal_bundle_id or right.causal_bundle_id)


def remove_one_ablations(genome: AsyncGenome) -> list[AsyncGenome]:
    rows: list[AsyncGenome] = []
    for index in range(len(genome.route_blocks)):
        blocks = genome.route_blocks[:index] + genome.route_blocks[index + 1:]
        rows.append(_with(genome, blocks=blocks, mutation="remove_one_route_ablation"))
    for index in range(len(genome.market_edits)):
        edits = genome.market_edits[:index] + genome.market_edits[index + 1:]
        rows.append(_with(genome, edits=edits, mutation="remove_one_market_ablation"))
    for index in range(len(genome.constants)):
        constants = genome.constants[:index] + genome.constants[index + 1:]
        rows.append(_with(genome, constants=constants, mutation="remove_one_constant_ablation"))
    return rows


def initial_lane_roots(fixture_path: Path) -> dict[str, list[AsyncGenome]]:
    from compiler import compile_fixture_anchors

    rows: dict[str, list[AsyncGenome]] = {"v27_current_meta": [AsyncGenome("v27_current_meta")], "boatlee_v16_rc2_market_relay": [AsyncGenome("boatlee_v16_rc2_market_relay")]}
    for candidate in compile_fixture_anchors(fixture_path):
        rows[candidate.lane].append(candidate.genome)
        rows[candidate.lane].extend(remove_one_ablations(candidate.genome))
    return {lane: list(dict.fromkeys(values)) for lane, values in rows.items()}


def refill_population(parents: tuple[AsyncGenome, ...], *, target: int, seed: int, max_attempts: int) -> tuple[list[AsyncGenome], dict[str, Any]]:
    rows = list(dict.fromkeys(parents))
    attempts = 0
    while len(rows) < target and attempts < max_attempts:
        parent = rows[attempts % len(rows)] if rows else None
        if parent is None:
            break
        child, _ = mutate_one(parent, seed=seed + attempts)
        if child not in rows:
            rows.append(child)
        attempts += 1
    return rows, {"target": target, "produced": len(rows), "attempts": attempts, "saturated": len(rows) < target}


def next_generation(parents: list[AsyncGenome], *, target: int, proposal_seed: int, generation: int, max_attempts: int) -> tuple[list[AsyncGenome], dict[str, Any]]:
    """Deterministic lane-local proposal generation; scores are never pooled."""
    if not parents:
        return [], {"target": target, "produced": 0, "attempts": 0, "saturated": True}
    children: list[AsyncGenome] = list(dict.fromkeys(parents[: min(len(parents), max(1, target // 3))]))
    for index in range(min(len(parents), max(1, target // 3))):
        left = parents[index]
        right = parents[(index + 1) % len(parents)]
        children.append(crossover(left, right, seed=proposal_seed + generation * 1009 + index))
    return refill_population(tuple(children), target=target, seed=proposal_seed + generation * 7919, max_attempts=max_attempts)
