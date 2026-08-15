"""Lane-qualified static compiler for event-linked ninth-cow patches."""

from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
from pathlib import Path
from typing import Any, Iterable

from ledgers import (
    actor_position,
    choose_structural_actor,
    resource_snapshot,
    snapshot_payload,
    trace_observations,
)
from lineage import NinthCowLineage, extract_ninth_cow_lineage
from model import (
    CompiledCandidate,
    DisplacedAction,
    FactorMutation,
    PatchWindow,
    Precondition,
    SemanticGenome,
    StaticRejection,
    StepPatch,
)


COMPILER_VERSION = "d1-v4"
COW_COST = 400


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _units(action: dict[str, Any]) -> list[list[Any]]:
    return [
        list(action.get("farmer") or ["PASS"]),
        *[list(row or ["PASS"]) for row in (action.get("hands") or [])],
    ]


def _market(action: dict[str, Any]) -> list[list[Any]]:
    return [list(row) for row in (action.get("market") or [])]


def _window(
    name: str,
    active_start: int,
    active_end: int,
    entry: tuple[Precondition, ...],
    rejoin_step: int,
    actor: int | None,
    rejoin_position: tuple[int, int] | None,
) -> PatchWindow:
    start = max(0, active_start)
    end = min(718, active_end)
    if end - start + 1 < 8:
        missing = 8 - (end - start + 1)
        start = max(0, start - (missing // 2))
        end = min(718, start + 7)
        start = max(0, end - 7)
    return PatchWindow(name, start, end, entry, max(end + 1, rejoin_step), actor, rejoin_position)


class CompilerAdapter:
    """Independent lane ownership with a shared compiler implementation."""

    def __init__(self, lane: str, route_path: Path, control_path: Path):
        self.lane = lane
        self.route_path = route_path
        self.control_path = control_path

    @property
    def route_sha256(self) -> str:
        return file_sha256(self.route_path)

    @property
    def control_sha256(self) -> str:
        return file_sha256(self.control_path)

    def lane_constraints(self) -> dict[str, Any]:
        if self.lane == "boatlee_v16_rc2_market_relay":
            return {
                "existing_overlays": ("weed", "livestock", "wool", "fertilizer_relay"),
                "relay_steps": tuple(range(278, 663, 24)),
            }
        return {
            "existing_overlays": ("weed", "market_rank"),
            "relay_steps": (),
        }


class V27CompilerAdapter(CompilerAdapter):
    pass


class BoatleeCompilerAdapter(CompilerAdapter):
    pass


def _reject(adapter: CompilerAdapter, genome: SemanticGenome, code: str, stage: str, detail: str, **evidence: Any) -> StaticRejection:
    return StaticRejection(adapter.lane, genome.genome_id, code, stage, detail, evidence)


def _add_patch(
    patches: dict[int, dict[str, Any]],
    step: int,
    *,
    actor: int | None = None,
    action: tuple[Any, ...] | None = None,
    remove_market: tuple[Any, ...] | None = None,
    append_market: tuple[Any, ...] | None = None,
) -> None:
    row = patches.setdefault(step, {"actors": {}, "remove": [], "append": []})
    if actor is not None and action is not None:
        row["actors"][int(actor)] = tuple(action)
    if remove_market is not None:
        row["remove"].append(tuple(remove_market))
    if append_market is not None:
        row["append"].append(tuple(append_market))


def _compiled_patches(rows: dict[int, dict[str, Any]]) -> tuple[StepPatch, ...]:
    return tuple(
        StepPatch(
            step=step,
            actor_actions=tuple(sorted(row["actors"].items())),
            remove_market=tuple(row["remove"]),
            append_market=tuple(row["append"]),
        )
        for step, row in sorted(rows.items())
    )


def _disposition(incumbent: list[Any], candidate: tuple[Any, ...], *, cow_specific: bool = False) -> str:
    if tuple(incumbent) == candidate:
        return "retained"
    if cow_specific or not incumbent or incumbent[0] == "PASS":
        return "reclaimed"
    return "reassigned"


def _entry_for_purchase(observation: dict[str, Any], route_market_count: int) -> tuple[Precondition, ...] | StaticRejection:
    if route_market_count >= 10:
        return StaticRejection("", "", "market_slot_unavailable", "purchase", "target purchase turn already has ten market orders", {"market_orders": route_market_count})
    return (
        Precondition("own_public", "money", "ge", COW_COST, True),
        Precondition("own_private", "shed_headroom", "ge", 1, False),
        Precondition("action", "market_slots", "ge", 1, True),
    )


def _apply_mutation(
    mutation: FactorMutation,
    genome: SemanticGenome,
    lineage: NinthCowLineage,
    route: list[dict[str, Any]],
    observations: dict[int, dict[str, Any]],
    patches: dict[int, dict[str, Any]],
    displaced: list[DisplacedAction],
    selector: dict[str, Any],
) -> tuple[str, str, dict[str, Any]] | None:
    shift = genome.purchase_shift if genome.structural_root == "shift" else 0
    if mutation.factor == "market_exposure":
        selector["market_exposure"] = {
            "product": "MILK",
            "max_public_inventory": int(dict(mutation.parameters).get("max_inventory", 10000)),
            "min_public_price": int(dict(mutation.parameters).get("min_price", 2)),
            "source": "public market only",
        }
        return None
    if mutation.factor == "capacity":
        selector["capacity"] = {
            "min_shed_headroom": int(dict(mutation.parameters).get("min_headroom", 8)),
            "degradation": "incumbent",
        }
        return None
    if mutation.factor == "reclaimed_labor":
        if genome.structural_root != "removal":
            return "reclaimed_labor_requires_removal", "mutation", {"root": genome.structural_root}
        destination = str(dict(mutation.parameters).get("destination", "incumbent_followup"))
        for source_step in (lineage.build_step, lineage.place_step):
            target_step = min(718, source_step + 1)
            replacement = tuple(_units(route[target_step])[lineage.actor])
            _add_patch(patches, source_step, actor=lineage.actor, action=replacement)
            displaced.append(
                DisplacedAction(
                    source_step,
                    "unit",
                    lineage.actor,
                    _units(route[source_step])[lineage.actor],
                    replacement,
                    "reclaimed",
                    destination,
                )
            )
        return None
    relative_events = [
        event
        for event in lineage.events
        if event.kind in {"FEED", "CARE", "COLLECT_FERTILIZER", "HARVEST", "SELL"}
    ]
    if mutation.factor in {"maintenance", "abandonment"}:
        desired = "FEED" if mutation.factor == "abandonment" else str(dict(mutation.parameters).get("operation", "CARE"))
        matching = [event for event in relative_events if event.kind == desired]
        if not matching:
            return "lifecycle_event_absent", "mutation", {"operation": desired}
        event = matching[0]
        target_step = event.step + shift
        if target_step not in observations:
            return "lifecycle_trace_missing", "mutation", {"target_step": target_step}
        actor = next(
            (
                index
                for index in range(1 + len((observations[target_step].get("farms") or [])[int(observations[target_step].get("player", 0) or 0)].get("hands", []) or []))
                if actor_position(observations[target_step], index) == lineage.tile
            ),
            None,
        )
        if actor is None:
            return "lifecycle_actor_path_unavailable", "mutation", {"target_step": target_step, "tile": lineage.tile}
        candidate = ("PASS",) if mutation.factor == "abandonment" else tuple(event.order)
        incumbent = _units(route[target_step])[actor]
        if event.step != target_step and event.actor is not None:
            original_incumbent = _units(route[event.step])[event.actor]
            _add_patch(patches, event.step, actor=event.actor, action=("PASS",))
            displaced.append(DisplacedAction(event.step, "unit", event.actor, original_incumbent, ("PASS",), "reassigned", f"time_shifted_{mutation.factor}"))
        _add_patch(patches, target_step, actor=actor, action=candidate)
        displaced.append(DisplacedAction(target_step, "unit", actor, incumbent, candidate, _disposition(incumbent, candidate), mutation.factor))
        return None
    if mutation.factor == "shipping":
        sales = [event for event in relative_events if event.kind == "SELL" and event.product == "MILK"]
        if not sales:
            return "shipping_sale_absent", "mutation", {}
        event = sales[0]
        sale_shift = int(dict(mutation.parameters).get("sale_shift", -3))
        target = event.step + shift + sale_shift
        if not 0 <= target <= 718:
            return "shipping_target_out_of_range", "mutation", {"target": target}
        if len(_market(route[target])) >= 10:
            return "shipping_market_slot_unavailable", "mutation", {"target": target}
        original_step = event.step
        _add_patch(patches, original_step, remove_market=event.order)
        _add_patch(patches, target, append_market=event.order)
        displaced.append(DisplacedAction(original_step, "market", None, list(event.order), ["PASS"], "reassigned", "shifted_milk_sale"))
        return None
    return "mutation_not_implemented", "mutation", {"factor": mutation.factor}


def compile_genome(
    adapter: CompilerAdapter,
    genome: SemanticGenome,
    route: list[dict[str, Any]],
    trace: Iterable[Any],
) -> CompiledCandidate | StaticRejection:
    observations = trace_observations(trace)
    try:
        lineage = extract_ninth_cow_lineage(route, trace, source=f"{adapter.lane}:technical-trace")
    except Exception as error:
        return _reject(adapter, genome, "lineage_incomplete", "lineage", str(error))
    if lineage.cow_ordinal != 9:
        return _reject(adapter, genome, "cow_ordinal_mismatch", "lineage", "last attributable cow purchase is not the ninth cow", ordinal=lineage.cow_ordinal)
    patches: dict[int, dict[str, Any]] = {}
    windows: list[PatchWindow] = []
    displaced: list[DisplacedAction] = []
    selector: dict[str, Any] = {
        "opponent_identity": False,
        "opponent_inputs": ("public_farm", "public_market", "public_town"),
        "fallback": "incumbent",
    }
    ledger: dict[str, Any] = {
        "lane_constraints": adapter.lane_constraints(),
        "lineage": asdict(lineage),
    }

    if genome.structural_root == "control" or (genome.structural_root == "shift" and genome.purchase_shift == 0):
        anchor_obs = observations.get(lineage.purchase_step)
        if anchor_obs:
            ledger["control_anchor"] = snapshot_payload(resource_snapshot(anchor_obs, lineage.tile))
        windows.append(
            _window(
                "control_anchor",
                lineage.purchase_step - 3,
                lineage.purchase_step + 4,
                (Precondition("own_public", "step", "eq", lineage.purchase_step, True),),
                lineage.purchase_step + 5,
                None,
                None,
            )
        )
    else:
        original_buy = ("BUY_ANIMAL", "COW", 1)
        _add_patch(patches, lineage.purchase_step, remove_market=original_buy)
        displaced.append(DisplacedAction(lineage.purchase_step, "market", None, list(original_buy), ["PASS"], "reclaimed", "ninth_cow_capital"))
        purchase_window_entry = (Precondition("own_public", "step", "eq", lineage.purchase_step, True),)
        windows.append(_window("remove_original_purchase", lineage.purchase_step - 3, lineage.purchase_step + 4, purchase_window_entry, lineage.purchase_step + 5, None, None))

        chain_actions = {
            lineage.pickup_step: ("PICKUP", "COW", 1),
            lineage.build_step: ("BUILD_PASTURE",),
            lineage.place_step: ("PLACE", "COW"),
        }
        for step, expected in chain_actions.items():
            incumbent = _units(route[step])[lineage.actor]
            _add_patch(patches, step, actor=lineage.actor, action=("PASS",))
            displaced.append(DisplacedAction(step, "unit", lineage.actor, incumbent, ("PASS",), "reclaimed", "ninth_cow_chain_removed"))
        cleanup_rejoin = lineage.place_step + 5
        cleanup_obs = observations.get(cleanup_rejoin)
        cleanup_pos = actor_position(cleanup_obs or {}, lineage.actor)
        windows.append(
            _window(
                "remove_original_structure",
                lineage.pickup_step - 3,
                lineage.place_step + 4,
                (Precondition("own_public", "hand_count", "ge", lineage.actor, True),),
                cleanup_rejoin,
                lineage.actor,
                cleanup_pos,
            )
        )

        if genome.structural_root == "shift":
            shift = genome.purchase_shift
            purchase_step = lineage.purchase_step + shift
            build_step = lineage.build_step + shift
            if not (0 <= purchase_step <= 718 and 0 <= build_step <= 717):
                return _reject(adapter, genome, "shift_out_of_range", "structural", "shifted structural event leaves the episode", purchase_step=purchase_step, build_step=build_step)
            purchase_obs = observations.get(purchase_step)
            if purchase_obs is None:
                return _reject(adapter, genome, "purchase_trace_missing", "purchase", "technical trace has no shifted purchase observation", step=purchase_step)
            entry = _entry_for_purchase(purchase_obs, len(_market(route[purchase_step])))
            if isinstance(entry, StaticRejection):
                return _reject(adapter, genome, entry.code, entry.stage, entry.detail, **entry.evidence)
            _add_patch(patches, purchase_step, append_market=original_buy)
            windows.append(_window("shifted_purchase", purchase_step - 3, purchase_step + 4, entry, purchase_step + 5, None, None))
            ledger["purchase"] = snapshot_payload(resource_snapshot(purchase_obs, lineage.tile))

            plan = choose_structural_actor(
                observations,
                build_step,
                lineage.tile,
                original_structure_removed_after=lineage.place_step,
            )
            if plan is None:
                return _reject(
                    adapter,
                    genome,
                    "actor_path_rejoin_unavailable",
                    "route_synthesis",
                    "no trace-present actor can travel through shed, pick up cow, build, place, and rejoin within 48 turns",
                    nominal_build_step=build_step,
                    target=lineage.tile,
                )
            actor, start_step, actions, rejoin_step, rejoin_position, clears_target, displaced_target = plan
            if start_step <= purchase_step:
                return _reject(adapter, genome, "purchase_before_pickup_gap_invalid", "resource", "structural staging begins before shifted purchase settles", purchase_step=purchase_step, staging_start=start_step)
            for offset, candidate in enumerate(actions):
                step = start_step + offset
                if step > 718:
                    return _reject(adapter, genome, "synthesized_path_out_of_range", "route_synthesis", "synthesized actor path leaves the episode", step=step)
                incumbent_units = _units(route[step])
                incumbent = incumbent_units[actor] if actor < len(incumbent_units) else ["PASS"]
                _add_patch(patches, step, actor=actor, action=candidate)
                displaced.append(
                    DisplacedAction(
                        step,
                        "unit",
                        actor,
                        incumbent,
                        candidate,
                        _disposition(incumbent, candidate),
                        "shifted_ninth_cow_structure",
                    )
                )
            start_obs = observations.get(start_step)
            if start_obs is None:
                return _reject(adapter, genome, "entry_trace_missing", "route_synthesis", "structural entry observation is absent", step=start_step)
            start_pos = actor_position(start_obs, actor)
            entry_conditions = (
                Precondition("own_public", "actor_position", "eq", {"actor": actor, "position": start_pos}, True),
                Precondition("own_public", "hand_count", "ge", actor, True),
                Precondition("own_private", "cow_total", "ge", 1, False),
                Precondition("own_public", "target_tile", "clearable" if clears_target else "empty", lineage.tile, True),
            )
            windows.append(_window("shifted_structure", start_step, start_step + len(actions) - 1, entry_conditions, rejoin_step, actor, rejoin_position))
            ledger["structure_entry"] = snapshot_payload(resource_snapshot(start_obs, lineage.tile))
            ledger["structure_plan"] = {
                "actor": actor,
                "start_step": start_step,
                "actions": actions,
                "rejoin_step": rejoin_step,
                "rejoin_position": rejoin_position,
                "nominal_build_step": build_step,
                "clears_target": clears_target,
            }
            if clears_target:
                build_action_step = start_step + actions.index(("BUILD_PASTURE",))
                selector["dig_retry"] = {
                    "window": "shifted_structure",
                    "actor": actor,
                    "target": lineage.tile,
                    "build_step": build_action_step,
                    "end_step": start_step + len(actions) - 1,
                    "max_retries": 1,
                    "source": "own public tile only",
                }
                ledger["target_clearance"] = {
                    "step": start_step + actions.index(("DIG",)),
                    "tile": lineage.tile,
                    "displaced_asset": displaced_target,
                    "economic_attribution": "deliberate_asset_abandonment_for_shifted_pasture",
                    "retry_contract": "DIG, revalidate next-turn BUILD, one bounded DIG retry, then incumbent fallback",
                }

    for mutation in genome.mutations:
        before = {step: repr(row) for step, row in patches.items()}
        failure = _apply_mutation(mutation, genome, lineage, route, observations, patches, displaced, selector)
        if failure:
            code, stage, evidence = failure
            return _reject(adapter, genome, code, stage, f"factor mutation {mutation.factor} cannot compile", **evidence)
        changed_steps = sorted(step for step, row in patches.items() if before.get(step) != repr(row))
        uncovered = [step for step in changed_steps if not any(window.start <= step <= window.end for window in windows)]
        if not changed_steps and mutation.factor in {"capacity", "market_exposure"} and not patches:
            return _reject(adapter, genome, "selector_has_no_active_patch", "mutation", f"{mutation.factor} cannot affect a control root with no patch")
        if uncovered:
            if uncovered[-1] - uncovered[0] + 1 > 40:
                return _reject(adapter, genome, "factor_window_exceeds_bound", "mutation", "factor-linked patch span cannot fit a 48-turn local window", steps=uncovered)
            active_actors = sorted({actor for step in uncovered for actor in (patches[step]["actors"] or {})})
            rejoin_actor = active_actors[0] if len(active_actors) == 1 else None
            factor_end = min(718, max(uncovered[-1], uncovered[0] + 7))
            rejoin_step = min(719, factor_end + 1)
            rejoin_position = actor_position(observations.get(rejoin_step, {}), rejoin_actor) if rejoin_actor is not None else None
            if rejoin_actor is not None and rejoin_position is None:
                return _reject(adapter, genome, "factor_rejoin_position_unverified", "rejoin", "factor patch actor lacks a trace-verified incumbent rejoin", actor=rejoin_actor, step=rejoin_step)
            windows.append(
                _window(
                    f"factor_{mutation.factor}",
                    uncovered[0],
                    factor_end,
                    (Precondition("own_public", "step", "eq", uncovered[0], True),),
                    rejoin_step,
                    rejoin_actor,
                    rejoin_position,
                )
            )

    if not windows:
        return _reject(adapter, genome, "no_bounded_window", "rejoin", "compiler produced no bounded active window")
    if any(window.rejoin_actor is not None and window.rejoin_position is None for window in windows):
        return _reject(adapter, genome, "rejoin_position_unverified", "rejoin", "trace does not verify the incumbent rejoin position")
    return CompiledCandidate(
        lane=adapter.lane,
        genome=genome,
        compiler_version=COMPILER_VERSION,
        control_sha256=adapter.control_sha256,
        route_sha256=adapter.route_sha256,
        patches=_compiled_patches(patches),
        windows=tuple(sorted(windows, key=lambda row: (row.start, row.name))),
        displaced_actions=tuple(sorted(displaced, key=lambda row: (row.step, row.channel, row.actor if row.actor is not None else -1, row.destination))),
        lineage_digest=lineage.digest,
        resource_ledger=ledger,
        public_selector=selector,
    )
