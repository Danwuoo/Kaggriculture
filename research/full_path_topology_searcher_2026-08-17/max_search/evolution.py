"""Deterministic multi-scale mutation, crossover, islands, and Pareto survival."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import random
from typing import Any, Iterable, Mapping, Sequence

from .contract import LANES, MODES, SearchContract, canonical_json
from .genome import FullTapeGenome, GenomeError, PASS_ACTION, RootRegistry, RootTape, candidate_lane


@dataclass(frozen=True)
class IslandSpec:
    index: int
    island_id: str
    lane: str
    mode: str
    capacity: int


def island_layout(contract: SearchContract) -> tuple[IslandSpec, ...]:
    result: list[IslandSpec] = []
    for lane in LANES:
        for mode in MODES:
            count = int(contract.payload["lanes"][lane]["modes"][mode])
            for ordinal in range(count):
                index = len(result)
                result.append(IslandSpec(
                    index=index,
                    island_id=f"island_{index:02d}_{lane}_{mode}_{ordinal}",
                    lane=lane,
                    mode=mode,
                    capacity=int(contract.scale["residents_per_island"]),
                ))
    if len(result) != contract.islands or sum(row.capacity for row in result) != contract.population:
        raise GenomeError("island layout does not reproduce the scale contract")
    return tuple(result)


def _rng_seed(*parts: object) -> int:
    raw = canonical_json(list(parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _replace_channel(base: Mapping[str, Any], donor: Mapping[str, Any], channel: str) -> dict[str, Any]:
    result = json.loads(canonical_json(dict(base)))
    if channel == "full":
        return json.loads(canonical_json(dict(donor)))
    if channel not in {"farmer", "hands", "market"}:
        raise GenomeError(f"unknown action channel: {channel}")
    result[channel] = json.loads(canonical_json(donor[channel]))
    return result


def _market_mutation(action: Mapping[str, Any], operation: str, donor: Mapping[str, Any], rng: random.Random) -> dict[str, Any]:
    result = json.loads(canonical_json(dict(action)))
    market = result["market"]
    donor_market = json.loads(canonical_json(donor["market"]))
    if operation == "market_insert":
        if len(market) < 10 and donor_market:
            market.insert(rng.randrange(len(market) + 1), donor_market[rng.randrange(len(donor_market))])
    elif operation == "market_remove":
        if market:
            market.pop(rng.randrange(len(market)))
    elif operation == "market_replace":
        if market and donor_market:
            market[rng.randrange(len(market))] = donor_market[rng.randrange(len(donor_market))]
        elif donor_market and len(market) < 10:
            market.append(donor_market[rng.randrange(len(donor_market))])
    elif operation == "market_reorder":
        if len(market) >= 2:
            left, right = rng.sample(range(len(market)), 2)
            market[left], market[right] = market[right], market[left]
    elif operation == "quantity_step":
        candidates = [index for index, order in enumerate(market)
                      if len(order) >= 3 and isinstance(order[2], int) and not isinstance(order[2], bool)]
        if candidates:
            index = rng.choice(candidates)
            quantity = int(market[index][2])
            delta = rng.choice((-max(1, quantity // 4), -1, 1, max(1, quantity // 4)))
            market[index][2] = max(1, quantity + delta)
    else:
        raise GenomeError(f"unsupported market mutation: {operation}")
    return result


def donor_block(
    parent: FullTapeGenome,
    parent_root: RootTape,
    donor: RootTape | tuple[FullTapeGenome, RootTape],
    *,
    start: int,
    horizon: int,
    channel: str = "full",
) -> FullTapeGenome:
    if not 0 <= start < 719 or horizon < 1 or start + horizon > 719:
        raise GenomeError("donor block outside 719-turn tape")
    def donor_action(step: int) -> dict[str, Any]:
        if isinstance(donor, RootTape):
            return donor.action_at(step)
        return donor[0].action_at(step, donor[1])

    replacements = {
        step: _replace_channel(parent.action_at(step, parent_root), donor_action(step), channel)
        for step in range(start, start + horizon)
    }
    return parent.with_actions(replacements, parent_root)


def destroy_repair(
    parent: FullTapeGenome,
    parent_root: RootTape,
    *,
    start: int,
    horizon: int,
    channel: str,
) -> FullTapeGenome:
    replacements: dict[int, Mapping[str, Any]] = {}
    for step in range(start, start + horizon):
        if channel == "full":
            replacements[step] = PASS_ACTION
        else:
            replacements[step] = _replace_channel(parent.action_at(step, parent_root), PASS_ACTION, channel)
    return parent.with_actions(replacements, parent_root)


def time_shift(
    parent: FullTapeGenome,
    parent_root: RootTape,
    *,
    start: int,
    horizon: int,
    offset: int,
    channel: str,
) -> FullTapeGenome:
    if offset == 0:
        raise GenomeError("time shift offset cannot be zero")
    target_start = start + offset
    if start < 0 or horizon < 1 or start + horizon > 719 or target_start < 0 or target_start + horizon > 719:
        raise GenomeError("time shift outside 719-turn tape")
    replacements: dict[int, Mapping[str, Any]] = {}
    for relative in range(horizon):
        source_step = start + relative
        target_step = target_start + relative
        replacements[target_step] = _replace_channel(
            parent.action_at(target_step, parent_root), parent.action_at(source_step, parent_root), channel,
        )
    # Vacated cells are explicitly repaired to PASS in the shifted channel.
    vacated = set(range(start, start + horizon)) - set(range(target_start, target_start + horizon))
    for step in vacated:
        replacements[step] = PASS_ACTION if channel == "full" else _replace_channel(
            parent.action_at(step, parent_root), PASS_ACTION, channel,
        )
    return parent.with_actions(replacements, parent_root)


def compatible_crossover(
    left: FullTapeGenome,
    left_root: RootTape,
    right: FullTapeGenome,
    right_root: RootTape,
    *,
    start: int,
    horizon: int,
    channel: str = "full",
) -> FullTapeGenome:
    if left.lane != right.lane:
        raise GenomeError("crossover cannot cross incumbent lanes")
    return donor_block(left, left_root, (right, right_root), start=start, horizon=horizon, channel=channel)


class MutationEngine:
    def __init__(self, registry: RootRegistry, *, proposal_seed: int):
        self.registry = registry
        self.proposal_seed = int(proposal_seed)

    def initial_genome(self, island: IslandSpec, ordinal: int) -> FullTapeGenome:
        if island.mode == "de_novo":
            public = self.registry.roots(source_kind="deduplicated_public_tape")
            roots = public or self.registry.roots(source_kind="pass_tape")
            root = roots[_rng_seed(self.proposal_seed, island.island_id, "root", ordinal) % len(roots)]
        elif island.mode == "novelty" and ordinal % 8 == 0:
            root = self.registry.roots(source_kind="pass_tape")[0]
        else:
            root = self.registry.incumbent(island.lane)
        return FullTapeGenome(island.lane, root.root_id, root.digest)

    def child(
        self,
        parent: FullTapeGenome,
        island: IslandSpec,
        *,
        generation: int,
        ordinal: int,
        mate: FullTapeGenome | None = None,
    ) -> tuple[FullTapeGenome, dict[str, Any]]:
        if parent.lane != island.lane:
            raise GenomeError("parent lane differs from island lane")
        rng = random.Random(_rng_seed(self.proposal_seed, island.island_id, generation, ordinal, parent.candidate_id))
        root = self.registry.get(parent.root_id)
        public = self.registry.roots(source_kind="deduplicated_public_tape")
        donors = public or self.registry.roots()
        donor_root = donors[rng.randrange(len(donors))]

        if island.mode == "coordinate":
            operations = ("point_replace", "market_insert", "market_remove", "market_replace", "market_reorder", "quantity_step", "time_shift")
            horizons = (1, 2, 4)
        elif island.mode == "large_neighborhood":
            operations = ("donor_block", "destroy_repair", "time_shift", "compatible_crossover")
            horizons = (8, 24, 48, 96, 192)
        elif island.mode == "de_novo":
            operations = ("donor_block", "destroy_repair", "compatible_crossover")
            horizons = (24, 48, 96, 192, 719)
        else:
            operations = ("point_replace", "donor_block", "destroy_repair", "time_shift", "compatible_crossover")
            horizons = (1, 2, 4, 8, 24, 48, 96, 192, 719)

        operation = rng.choice(operations)
        horizon = rng.choice(horizons)
        start = 0 if horizon == 719 else rng.randrange(720 - horizon)
        channel = "full" if horizon >= 24 else rng.choice(("farmer", "hands", "market", "full"))
        metadata: dict[str, Any] = {
            "operation": operation,
            "start": start,
            "horizon": horizon,
            "channel": channel,
            "donor_root_id": donor_root.root_id,
        }

        if operation == "point_replace":
            child = parent.with_actions({start: _replace_channel(
                parent.action_at(start, root), donor_root.action_at(start), channel,
            )}, root)
        elif operation.startswith("market_") or operation == "quantity_step":
            child = parent.with_actions({start: _market_mutation(
                parent.action_at(start, root), operation, donor_root.action_at(start), rng,
            )}, root)
        elif operation == "donor_block":
            child = donor_block(parent, root, donor_root, start=start, horizon=horizon, channel=channel)
        elif operation == "destroy_repair":
            child = destroy_repair(parent, root, start=start, horizon=horizon, channel=channel)
        elif operation == "time_shift":
            max_abs = min(24, start, 719 - (start + horizon))
            if max_abs < 1:
                child = donor_block(parent, root, donor_root, start=start, horizon=horizon, channel=channel)
                metadata["operation"] = "donor_block_boundary_fallback"
            else:
                offset = rng.choice((-max_abs, max_abs))
                metadata["offset"] = offset
                child = time_shift(parent, root, start=start, horizon=horizon, offset=offset, channel=channel)
        elif operation == "compatible_crossover":
            if mate is None or mate.lane != parent.lane:
                child = donor_block(parent, root, donor_root, start=start, horizon=horizon, channel=channel)
                metadata["operation"] = "donor_block_no_compatible_mate"
            else:
                child = compatible_crossover(parent, root, mate, self.registry.get(mate.root_id), start=start, horizon=horizon, channel=channel)
                metadata["mate_id"] = mate.candidate_id
        else:  # pragma: no cover - closed above
            raise GenomeError(f"unhandled mutation operation: {operation}")
        metadata["changed_steps"] = child.edit_distance_from_root()
        metadata["candidate_id"] = child.candidate_id
        return child, metadata


@dataclass(frozen=True)
class FitnessVector:
    candidate_id: str
    lane: str
    control_sha256: str
    manifest_sha256: str
    technical_pass: bool
    effective_change: bool
    net_wdl_transition: int
    w_to_l: int
    repeatable_family_seat_negative_tails: int
    cvar_01: float
    cvar_05: float
    worst_margin: float
    mean_margin: float
    mean_own_bank: float
    complexity: int
    novelty: float

    def __post_init__(self) -> None:
        if candidate_lane(self.candidate_id) != self.lane or self.lane not in LANES:
            raise GenomeError("fitness lane does not match candidate identity")
        if (not isinstance(self.control_sha256, str) or len(self.control_sha256) != 64
                or any(character not in "0123456789abcdef" for character in self.control_sha256)):
            raise GenomeError("fitness control provenance must be a full SHA-256")
        if (not isinstance(self.manifest_sha256, str) or len(self.manifest_sha256) != 64
                or any(character not in "0123456789abcdef" for character in self.manifest_sha256)):
            raise GenomeError("fitness run provenance must be a full manifest SHA-256")
        if type(self.technical_pass) is not bool or type(self.effective_change) is not bool:
            raise GenomeError("fitness gates must be strict booleans")
        for field in ("net_wdl_transition", "w_to_l", "repeatable_family_seat_negative_tails", "complexity"):
            value = getattr(self, field)
            if not isinstance(value, int) or isinstance(value, bool):
                raise GenomeError(f"fitness {field} must be an integer")
        if self.w_to_l < 0 or self.repeatable_family_seat_negative_tails < 0 or self.complexity < 0:
            raise GenomeError("fitness count fields cannot be negative")
        for field in ("cvar_01", "cvar_05", "worst_margin", "mean_margin", "mean_own_bank", "novelty"):
            value = getattr(self, field)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                raise GenomeError(f"fitness {field} must be finite")
        if self.novelty < 0:
            raise GenomeError("fitness novelty cannot be negative")

    def objectives(self) -> tuple[float, ...]:
        if not self.technical_pass or not self.effective_change:
            return (-math.inf,) * 10
        return (
            float(self.net_wdl_transition),
            float(-self.w_to_l),
            float(-self.repeatable_family_seat_negative_tails),
            float(self.cvar_01),
            float(self.cvar_05),
            float(self.worst_margin),
            float(self.mean_margin),
            float(self.mean_own_bank),
            float(-self.complexity),
            float(self.novelty),
        )


def dominates(left: FitnessVector, right: FitnessVector) -> bool:
    a, b = left.objectives(), right.objectives()
    return all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b))


def pareto_fronts(rows: Iterable[FitnessVector]) -> list[list[FitnessVector]]:
    values = list(rows)
    remaining = {row.candidate_id: row for row in values}
    if len(remaining) != len(values):
        raise GenomeError("fitness candidate IDs must be unique")
    fronts: list[list[FitnessVector]] = []
    while remaining:
        values = list(remaining.values())
        front = [row for row in values if not any(dominates(other, row) for other in values if other.candidate_id != row.candidate_id)]
        front.sort(key=lambda row: (row.objectives(), row.candidate_id), reverse=True)
        fronts.append(front)
        for row in front:
            del remaining[row.candidate_id]
    return fronts


def select_survivors(rows: Sequence[FitnessVector], capacity: int) -> tuple[FitnessVector, ...]:
    if capacity < 1:
        raise GenomeError("survivor capacity must be positive")
    if len({row.candidate_id for row in rows}) != len(rows):
        raise GenomeError("fitness candidate IDs must be unique")
    eligible = [row for row in rows if row.technical_pass and row.effective_change]
    if len(eligible) < capacity:
        raise GenomeError("hard technical/effective gate leaves fewer candidates than survivor capacity")
    selected: list[FitnessVector] = []
    for front in pareto_fronts(eligible):
        if len(selected) + len(front) <= capacity:
            selected.extend(front)
            continue
        needed = capacity - len(selected)
        # A deterministic tail-aware tie break is used only within one Pareto
        # front; no hand-entered scalar weighting collapses the objectives.
        front.sort(key=lambda row: (
            row.mean_margin,
            row.mean_own_bank,
            -row.complexity,
            row.novelty,
            row.candidate_id,
        ), reverse=True)
        selected.extend(front[:needed])
        break
    return tuple(selected)


def _risk_lexicographic_key(row: FitnessVector) -> tuple[Any, ...]:
    return (
        row.net_wdl_transition,
        -row.w_to_l,
        -row.repeatable_family_seat_negative_tails,
        row.cvar_01,
        row.cvar_05,
        row.worst_margin,
        row.mean_margin,
        row.mean_own_bank,
        -row.complexity,
        row.novelty,
        row.candidate_id,
    )


def select_survivors_scalable(
    rows: Sequence[FitnessVector],
    capacity: int,
) -> tuple[FitnessVector, ...]:
    """O(objectives*n*log n) risk-first beam with objective-extreme retention.

    Exact non-dominated sorting is retained for small analysis sets, but its
    quadratic behavior is unsuitable for 63,968 island selections. The formal
    runner uses this deterministic, non-scalar beam: 75% follows the declared
    WDL/tail/tie order and 25% is filled round-robin from each objective rank.
    """
    if capacity < 1:
        raise GenomeError("survivor capacity must be positive")
    if len({row.candidate_id for row in rows}) != len(rows):
        raise GenomeError("fitness candidate IDs must be unique")
    eligible = [row for row in rows if row.technical_pass and row.effective_change]
    if len(eligible) < capacity:
        raise GenomeError("hard technical/effective gate leaves fewer candidates than survivor capacity")
    primary_slots = max(1, capacity * 3 // 4)
    risk_ranked = sorted(eligible, key=_risk_lexicographic_key, reverse=True)
    selected: dict[str, FitnessVector] = {
        row.candidate_id: row for row in risk_ranked[:primary_slots]
    }
    objective_rankings = [
        sorted(eligible, key=lambda row, index=index: (row.objectives()[index], row.candidate_id), reverse=True)
        for index in range(len(eligible[0].objectives()))
    ]
    cursors = [0] * len(objective_rankings)
    while len(selected) < capacity:
        progressed = False
        for index, ranking in enumerate(objective_rankings):
            while cursors[index] < len(ranking):
                row = ranking[cursors[index]]
                cursors[index] += 1
                if row.candidate_id not in selected:
                    selected[row.candidate_id] = row
                    progressed = True
                    break
            if len(selected) == capacity:
                break
        if not progressed:
            break
    if len(selected) != capacity:
        raise GenomeError("scalable survivor beam failed to fill capacity")
    return tuple(sorted(selected.values(), key=_risk_lexicographic_key, reverse=True))
