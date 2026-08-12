"""Exact current-engine trace runner for the job-value residual experiments."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from typing import Any, Callable

from protocol import LANE_ROOT, control_path, opponent_path


HARNESS_ROOT = LANE_ROOT.parent / "main_approach" / "performance_optimization_2026_08_11"
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

import harness  # noqa: E402


MANIFEST_PATH = LANE_ROOT / "artifacts" / "prechange_manifest.json"
PolicyFactory = Callable[[Any, Callable[..., dict], int], Callable[..., dict]]
ENGINE_IDENTITY_KEYS = (
    "commit",
    "python_blob",
    "configuration_blob",
    "python_sha256",
    "configuration_sha256",
    "python_bytes",
    "configuration_bytes",
)


@dataclass(frozen=True)
class TraceFrame:
    step: int
    observation: dict[str, Any]
    action: dict[str, Any]
    latency_ms: float
    market_receipts: tuple[tuple[int, str, float], ...] = ()
    capacity_inflight: tuple[tuple[str, int, str], ...] = ()
    capacity_certification: str | None = None
    context: tuple[str, str, int, int] | None = None


@dataclass
class GameRun:
    incumbent: str
    opponent_family: str
    seed: int
    seat: int
    summary: dict[str, Any]
    trace: list[TraceFrame]
    policy_metadata: dict[str, Any]


def assert_engine_current() -> dict[str, Any]:
    """Reject a run unless portable engine identity matches the frozen manifest."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    actual = harness.engine_fingerprint()
    expected = manifest["engine"]
    actual_identity = {key: actual.get(key) for key in ENGINE_IDENTITY_KEYS}
    expected_identity = {key: expected.get(key) for key in ENGINE_IDENTITY_KEYS}
    if actual_identity != expected_identity:
        raise RuntimeError(
            "current engine fingerprint differs from frozen protocol: "
            f"actual={actual_identity!r} expected={expected_identity!r}"
        )
    return actual


def _new_state() -> list[Any]:
    return [
        harness.structify(
            {
                "observation": {
                    "player": player,
                    "step": 0,
                    "remainingOverageTime": 60.0,
                },
                "action": {"farmer": ["PASS"], "hands": [], "market": []},
                "status": "ACTIVE",
                "reward": 0.0,
            }
        )
        for player in range(2)
    ]


def _action_issues(observation: dict[str, Any], action: Any) -> dict[str, int]:
    if not isinstance(action, dict):
        return {
            "malformed": 1,
            "hand_alignment": 1,
            "seed_overcommit": 0,
            "market_overflow": 0,
        }
    farmer = action.get("farmer")
    hands = action.get("hands")
    market = action.get("market")
    malformed = int(
        not isinstance(farmer, list)
        or not isinstance(hands, list)
        or not isinstance(market, list)
        or (isinstance(hands, list) and any(not isinstance(item, list) for item in hands))
        or (isinstance(market, list) and any(not isinstance(item, list) for item in market))
    )
    farm = observation["farms"][observation["player"]]
    requested: dict[str, int] = {}
    if isinstance(hands, list):
        for unit_action in [farmer, *hands]:
            if (
                isinstance(unit_action, list)
                and len(unit_action) >= 2
                and unit_action[0] == "PLANT"
            ):
                crop = str(unit_action[1])
                requested[crop] = requested.get(crop, 0) + 1
    seeds = (observation.get("private", {}) or {}).get("seeds", {}) or {}
    return {
        "malformed": malformed,
        "hand_alignment": int(
            not isinstance(hands, list) or len(hands) != len(farm.get("hands", []) or [])
        ),
        "seed_overcommit": sum(
            max(0, count - int(seeds.get(crop, 0) or 0))
            for crop, count in requested.items()
        ),
        "market_overflow": int(isinstance(market, list) and len(market) > 10),
    }


def _tile_events(before: list[Any], after: list[Any], day: int) -> list[tuple[str, bool]]:
    events: list[tuple[str, bool]] = []
    for y, row in enumerate(before):
        for x, old in enumerate(row):
            new = after[y][x]
            if isinstance(old, dict) and old.get("animal"):
                if not (isinstance(new, dict) and new.get("animal") == old.get("animal")):
                    events.append(("animal_escape", False))
            if (
                isinstance(old, dict)
                and old.get("kind") == "PLANT"
                and isinstance(new, dict)
                and new.get("kind") == "WEED"
            ):
                events.append(("crop_death", int(old.get("planted_day", -1000)) == day))
    return events


def _inventory_total(private: Any) -> int:
    view = harness.plain(private)
    shed = sum(max(0, int(value or 0)) for value in (view.get("shed", {}) or {}).values())
    carried = sum(
        max(0, int(value or 0))
        for inventory in (view.get("inventories", []) or [])
        for value in (inventory or {}).values()
    )
    return shed + carried


def _terminal_inventory(observation: Any) -> dict[str, float | int]:
    items: dict[str, int] = {}
    private = observation.private
    for source in [private.get("shed", {}), *(private.get("inventories", []) or [])]:
        for item, value in (source or {}).items():
            items[item] = items.get(item, 0) + max(0, int(value or 0))
    prices = observation.market.get("prices", {}) or {}
    return {
        "units": sum(items.values()),
        "marked_value": sum(
            quantity * float(prices.get(item, 0) or 0)
            for item, quantity in items.items()
        ),
    }


def _instrument_engine(
    engine: Any,
    candidate_private: Any,
    diagnostics: dict[str, Any],
    planted_tiles: list[tuple[int, int]], receipts: list[tuple[int, str, float]], step_ref: list[int], capacity_reasons: dict[int, str],
):
    """Return an undo callback after observing discard and successful-plant transitions."""
    original_unit = engine._apply_unit_action
    original_daily_drop = engine._drop_inventories_to_shed
    original_commit = engine._commit_unit

    def tracked_unit(*args: Any, **kwargs: Any) -> Any:
        farm = args[0]
        private = args[1]
        unit_index = args[2]
        action = args[3]
        is_shed_drop = (
            private is candidate_private
            and isinstance(action, list)
            and bool(action)
            and action[0] == "DROP"
        )
        before = _inventory_total(private) if is_shed_drop else 0
        if is_shed_drop:
            shed = private.get("shed", {}) or {}
            carried = sum(max(0, int(value or 0)) for value in (private.get("inventories", [])[unit_index] or {}).values())
            if carried and sum(max(0, int(value or 0)) for value in shed.values()) >= 100:
                # The audited engine discards a full-shed DROP, so it cannot certify
                # a still-in-flight capacity unit. Preserve that explicit reason.
                capacity_reasons[step_ref[0]] = "drop_overflow_discards"
        result = original_unit(*args, **kwargs)
        if is_shed_drop:
            discarded = max(0, before - _inventory_total(private))
            if discarded:
                diagnostics["shed_overflow_events"] += 1
                diagnostics["shed_overflow_units"] += discarded
        if (
            private is candidate_private
            and isinstance(action, list)
            and len(action) >= 2
            and action[0] == "PLANT"
        ):
            position = engine._farmer_position(farm, unit_index)
            if position is not None:
                x, y = position
                tile = farm["tiles"][y][x]
                if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                    planted_tiles.append((x, y))
        return result

    def tracked_daily_drop(private: Any, capacity: int) -> Any:
        if private is candidate_private:
            discarded = max(0, _inventory_total(private) - int(capacity))
            if discarded:
                diagnostics["shed_overflow_events"] += 1
                diagnostics["shed_overflow_units"] += discarded
        return original_daily_drop(private, capacity)

    engine._apply_unit_action = tracked_unit
    engine._drop_inventories_to_shed = tracked_daily_drop

    def tracked_commit(op: str, item: str, price: float, farm: Any, private: Any, market: Any, shed_capacity: int = 100) -> Any:
        result = original_commit(op, item, price, farm, private, market, shed_capacity)
        if result and private is candidate_private and op == "SELL":
            receipts.append((step_ref[0], str(item), float(price)))
        return result

    engine._commit_unit = tracked_commit

    def undo() -> None:
        engine._apply_unit_action = original_unit
        engine._drop_inventories_to_shed = original_daily_drop
        engine._commit_unit = original_commit

    return undo


def run_game(
    incumbent: str,
    candidate_path: Path,
    opponent_family: str,
    seed: int,
    seat: int,
    *,
    policy_factory: PolicyFactory | None = None,
    opponent_policy_factory: PolicyFactory | None = None,
    capture_trace: bool = False,
    clock: Callable[[], float] = time.perf_counter,
) -> GameRun:
    """Play one full, deterministic current-engine game from either seat."""
    fingerprint = assert_engine_current()
    engine, _ = harness.load_engine()
    config = harness.configuration(seed)
    env = SimpleNamespace(configuration=config, info={}, done=False, steps=[])
    state = _new_state()
    engine.interpreter(state, env)

    module, candidate, import_ms = harness.load_agent(
        candidate_path, f"job_{incumbent}_{seed}_{seat}"
    )
    metadata: dict[str, Any] = {}
    if policy_factory is not None:
        candidate = policy_factory(module, candidate, seat)
        metadata = getattr(candidate, "metadata", metadata)
    opponent_module, opponent, opponent_import_ms = harness.load_agent(
        opponent_path(incumbent, opponent_family),
        f"job_opponent_{incumbent}_{opponent_family}_{seed}_{seat}",
    )
    if opponent_policy_factory is not None:
        opponent = opponent_policy_factory(opponent_module, opponent, 1 - seat)
    policies = [opponent, opponent]
    policies[seat] = candidate

    digests = [hashlib.sha256(), hashlib.sha256()]
    latencies_ms: list[list[float]] = [[], []]
    trace: list[TraceFrame] = []
    calls = [0, 0]
    overage = [60.0, 60.0]
    exceptions: list[str | None] = [None, None]
    issues = [
        {
            "malformed": 0,
            "hand_alignment": 0,
            "seed_overcommit": 0,
            "market_overflow": 0,
        }
        for _ in range(2)
    ]
    diagnostics = {
        "animal_escapes": 0,
        "crop_deaths": 0,
        "fresh_crop_deaths": 0,
        "animal_escape_steps": [],
        "crop_death_steps": [],
        "fresh_crop_death_steps": [],
        "shed_overflow_events": 0,
        "shed_overflow_units": 0,
    }
    max_market_orders = [0, 0]
    planted_tiles: list[tuple[int, int]] = []
    receipts: list[tuple[int, str, float]] = []
    step_ref = [-1]
    capacity_reasons: dict[int, str] = {}
    undo_instrumentation = _instrument_engine(
        engine, state[seat].observation.private, diagnostics, planted_tiles, receipts, step_ref, capacity_reasons
    )
    try:
        for step in range(int(config.episodeSteps) - 1):
            step_ref[0] = step
            for index in range(2):
                state[index].observation.step = step
                state[index].observation.remainingOverageTime = overage[index]
            before_tiles = copy.deepcopy(state[seat].observation.farms[seat]["tiles"])
            planted_tiles.clear()
            for index, policy in enumerate(policies):
                observation = harness.structify(
                    copy.deepcopy(harness.plain(state[index].observation))
                )
                started = clock()
                try:
                    returned = harness.invoke(policy, observation, config)
                except Exception as error:
                    returned = {"farmer": ["PASS"], "hands": [], "market": []}
                    exceptions[index] = f"{type(error).__name__}: {error}"
                elapsed_ms = (clock() - started) * 1000.0
                calls[index] += 1
                if elapsed_ms > float(config.actTimeout) * 1000.0:
                    overage[index] -= elapsed_ms / 1000.0 - float(config.actTimeout)
                action = harness.plain(returned) if isinstance(returned, dict) else {}
                digests[index].update(
                    json.dumps(action, sort_keys=True, separators=(",", ":")).encode("utf-8")
                )
                latencies_ms[index].append(elapsed_ms)
                found = _action_issues(harness.plain(observation), returned)
                for key, value in found.items():
                    issues[index][key] += value
                market = action.get("market", [])
                if isinstance(market, list):
                    max_market_orders[index] = max(max_market_orders[index], len(market))
                if index == seat:
                    if capture_trace:
                        trace.append(
                            TraceFrame(
                                step=step,
                                observation=harness.plain(copy.deepcopy(observation)),
                                action=copy.deepcopy(action),
                                latency_ms=elapsed_ms,
                                context=(incumbent, opponent_family, int(seed), int(seat)),
                            )
                        )
                state[index].action = harness.structify(action)
            if any(exceptions):
                break
            engine.interpreter(state, env)
            if capture_trace:
                frame = trace[-1]
                trace[-1] = replace(
                    frame,
                    market_receipts=tuple(item for item in receipts if item[0] == step),
                    capacity_certification=capacity_reasons.get(step, "no_certified_capacity_inflight"),
                )
            for event, fresh in _tile_events(
                before_tiles,
                state[seat].observation.farms[seat]["tiles"],
                step // int(config.turnsPerDay),
            ):
                if event == "animal_escape":
                    diagnostics["animal_escapes"] += 1
                    diagnostics["animal_escape_steps"].append(step)
                else:
                    diagnostics["crop_deaths"] += 1
                    diagnostics["crop_death_steps"].append(step)
                    if fresh:
                        diagnostics["fresh_crop_deaths"] += 1
                        diagnostics["fresh_crop_death_steps"].append(step)
            for x, y in planted_tiles:
                tile = state[seat].observation.farms[seat]["tiles"][y][x]
                if isinstance(tile, dict) and tile.get("kind") == "WEED":
                    diagnostics["crop_deaths"] += 1
                    diagnostics["fresh_crop_deaths"] += 1
                    diagnostics["crop_death_steps"].append(step)
                    diagnostics["fresh_crop_death_steps"].append(step)
            if all(item.status == "DONE" for item in state):
                break
    finally:
        undo_instrumentation()

    rewards = [float(item.reward) for item in state]
    money = [float(state[index].observation.farms[index]["money"]) for index in range(2)]
    summary = {
        "statuses": [str(item.status) for item in state],
        "calls": calls[seat],
        "rewards": rewards,
        "money": money,
        "action_digest": digests[seat].hexdigest(),
        "opponent_action_digest": digests[1 - seat].hexdigest(),
        "action_issues": issues[seat],
        "max_market_orders": max_market_orders[seat],
        "diagnostics": diagnostics,
        "terminal_inventory": _terminal_inventory(state[seat].observation),
        "exception": exceptions[seat],
        "opponent_exception": exceptions[1 - seat],
        "timeout_calls": sum(
            value > float(config.actTimeout) * 1000.0 for value in latencies_ms[seat]
        ),
        "overage_exhausted": overage[seat] < 0.0,
        "latency_ms": harness.latency_summary(latencies_ms[seat]),
        "opponent_calls": calls[1 - seat],
        "opponent_action_issues": issues[1 - seat],
        "opponent_max_market_orders": max_market_orders[1 - seat],
        "opponent_timeout_calls": sum(
            value > float(config.actTimeout) * 1000.0 for value in latencies_ms[1 - seat]
        ),
        "opponent_overage_exhausted": overage[1 - seat] < 0.0,
        "opponent_latency_ms": harness.latency_summary(latencies_ms[1 - seat]),
        "engine_fingerprint": fingerprint,
        "import_ms": import_ms,
        "opponent_import_ms": opponent_import_ms,
        "remaining_overage": overage,
    }
    return GameRun(
        incumbent=incumbent,
        opponent_family=opponent_family,
        seed=int(seed),
        seat=int(seat),
        summary=summary,
        trace=trace,
        policy_metadata=metadata,
    )


def behavior_view(run: GameRun) -> dict[str, Any]:
    """Return only deterministic game behavior for paired-run comparison."""
    return {
        key: run.summary[key]
        for key in (
            "statuses",
            "calls",
            "rewards",
            "money",
            "action_digest",
            "opponent_action_digest",
            "action_issues",
            "max_market_orders",
            "diagnostics",
            "terminal_inventory",
            "exception",
            "opponent_exception",
            "timeout_calls",
            "overage_exhausted",
        )
    }


def write_trace_gzip(path: Path, run: GameRun) -> None:
    """Persist a trace as a compact, canonical JSON document inside gzip."""
    payload = {
        "summary": run.summary,
        "trace": [asdict(frame) for frame in run.trace],
        "policy_metadata": run.policy_metadata,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
