"""Consumed-context search for lane-local, time-shifted four-turn counterfactuals."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from itertools import permutations
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
JOB_LANE = ROOT / "research/job_value_residual_2026-08-12"
if str(JOB_LANE) not in sys.path:
    sys.path.insert(0, str(JOB_LANE))

from engine_runner import GameRun, run_game  # noqa: E402
from forced_policy import make_forced_factory  # noqa: E402
from schema import CandidateWindow, Requirement  # noqa: E402


MOVES = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "EAST": (1, 0),
    "WEST": (-1, 0),
}

LANES = {
    "v27_current_meta": {
        "trigger_step": 610,
        "actor": 8,
        "start": (1, 2),
        "baseline": ("WEST", "WATER", "EAST", "NORTH"),
        "known_negative": ("EAST", "HARVEST", "WEST", "NORTH"),
    },
    "boatlee_v16_rc2_market_relay": {
        "trigger_step": 499,
        "actor": 8,
        "start": (0, 0),
        "baseline": ("WATER", "EAST", "WATER", "HARVEST"),
        "known_negative": ("EAST", "SOUTH", "HARVEST", "NORTH"),
    },
}

OPPONENTS = ("other_incumbent", "kaito_v21")
CONSUMED_SEEDS = (93687444, 65365230)


def current_control_path(lane: str) -> Path:
    return ROOT / "research/main_approach" / lane / "main.py"


def _positions(start: tuple[int, int], actions: Iterable[str]) -> tuple[tuple[int, int], ...] | None:
    positions = [start]
    x, y = start
    for action in actions:
        dx, dy = MOVES.get(action, (0, 0))
        x, y = x + dx, y + dy
        if not (0 <= x < 10 and 0 <= y < 10):
            return None
        positions.append((x, y))
    return tuple(positions)


def _candidate_id(lane: str, actions: tuple[str, ...]) -> str:
    raw = json.dumps({"lane": lane, "actions": actions}, sort_keys=True, separators=(",", ":")).encode()
    return "cf_" + hashlib.sha256(raw).hexdigest()[:20]


def candidates(lane: str) -> tuple[CandidateWindow, ...]:
    definition = LANES[lane]
    baseline = tuple(definition["baseline"])
    start = tuple(definition["start"])
    baseline_positions = _positions(start, baseline)
    assert baseline_positions is not None
    endpoint = baseline_positions[-1]
    unique = sorted(set(permutations(baseline)))
    result = []
    for actions in unique:
        if actions == baseline:
            continue
        expected = _positions(start, actions)
        if expected is None or expected[-1] != endpoint:
            continue
        touched = tuple(sorted({expected[index] for index, action in enumerate(actions)
                                if action in {"WATER", "HARVEST"}}))
        result.append(CandidateWindow(
            candidate_id=_candidate_id(lane, actions),
            incumbent=lane,
            family="productive_detour",
            trigger_step=int(definition["trigger_step"]),
            actor=int(definition["actor"]),
            rejoin_step=int(definition["trigger_step"]) + len(actions),
            actions=tuple((action,) for action in actions),
            expected_positions=expected,
            requirements=(Requirement("actor_position", (int(definition["actor"]),), "eq", start),),
            sell_directives=(),
            displaced_actions=tuple((action,) for action in baseline),
            touched_tiles=touched,
            effects=(),
        ))
    return tuple(result)


def _margin(run: GameRun) -> float:
    rewards = run.summary["rewards"]
    return float(rewards[run.seat]) - float(rewards[1 - run.seat])


def _outcome(margin: float) -> str:
    return "W" if margin > 0 else "L" if margin < 0 else "D"


def _technical(run: GameRun) -> bool:
    summary = run.summary
    return (
        summary["statuses"] == ["DONE", "DONE"]
        and summary["exception"] is None
        and summary["opponent_exception"] is None
        and not summary["overage_exhausted"]
        and summary["timeout_calls"] == 0
        and summary["max_market_orders"] <= 10
        and all(value == 0 for value in summary["action_issues"].values())
    )


def _public_tile(observation: dict[str, Any], seat: int, position: tuple[int, int]) -> Any:
    x, y = position
    return observation["farms"][seat]["tiles"][y][x]


def _trigger_snapshot(run: GameRun) -> dict[str, Any]:
    definition = LANES[run.incumbent]
    frame = next(item for item in run.trace if item.step == definition["trigger_step"])
    observation = frame.observation
    seat = int(observation["player"])
    positions = _positions(tuple(definition["start"]), tuple(definition["baseline"]))
    assert positions is not None
    relevant = sorted(set(positions))
    return {
        "actor_position": observation["farms"][seat]["hands"][int(definition["actor"]) - 1],
        "tiles": [
            {"position": list(position), "state": _public_tile(observation, seat, position)}
            for position in relevant
        ],
    }


def _row(control: GameRun, candidate: GameRun, window: CandidateWindow) -> dict[str, Any]:
    control_margin = _margin(control)
    candidate_margin = _margin(candidate)
    left, right = _outcome(control_margin), _outcome(candidate_margin)
    delta = candidate_margin - control_margin
    # Outcome rank, rather than lexical W/D/L ordering, is authoritative.
    rank = {"L": 0, "D": 1, "W": 2}
    if rank[right] != rank[left]:
        sign = "positive" if rank[right] > rank[left] else "negative"
    else:
        sign = "positive" if delta > 0 else "negative" if delta < 0 else "neutral"
    return {
        "context": {"opponent_family": control.opponent_family, "seed": control.seed, "seat": control.seat},
        "candidate_id": window.candidate_id,
        "actions": [list(action) for action in window.actions],
        "control_margin": control_margin,
        "candidate_margin": candidate_margin,
        "margin_delta": delta,
        "control_outcome": left,
        "candidate_outcome": right,
        "outcome_transition": f"{left}_TO_{right}",
        "sign": sign,
        "technical_pass": _technical(candidate),
        "rejoin_status": candidate.policy_metadata.get("status"),
        "action_digest_changed": candidate.summary["action_digest"] != control.summary["action_digest"],
        "money_delta": float(candidate.summary["money"][candidate.seat]) - float(control.summary["money"][control.seat]),
        "diagnostic_delta": {
            key: int(candidate.summary["diagnostics"][key]) - int(control.summary["diagnostics"][key])
            for key in ("animal_escapes", "crop_deaths", "fresh_crop_deaths", "shed_overflow_units")
        },
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [float(row["margin_delta"]) for row in rows]
    return {
        "contexts": len(rows),
        "positive": sum(row["sign"] == "positive" for row in rows),
        "neutral": sum(row["sign"] == "neutral" for row in rows),
        "negative": sum(row["sign"] == "negative" for row in rows),
        "positive_outcome_transitions": sum(
            row["outcome_transition"] in {"L_TO_D", "L_TO_W", "D_TO_W"} for row in rows
        ),
        "negative_outcome_transitions": sum(
            row["outcome_transition"] in {"W_TO_D", "W_TO_L", "D_TO_L"} for row in rows
        ),
        "mean_margin_delta": statistics.fmean(deltas),
        "min_margin_delta": min(deltas),
        "max_margin_delta": max(deltas),
        "technical_pass": all(row["technical_pass"] and row["rejoin_status"] == "rejoined" for row in rows),
    }


def _rank(summary: dict[str, Any]) -> tuple[Any, ...]:
    return (
        summary["positive_outcome_transitions"] - summary["negative_outcome_transitions"],
        summary["positive"] - summary["negative"],
        summary["min_margin_delta"],
        summary["mean_margin_delta"],
    )


def run(output: Path, expand_count: int = 4) -> dict[str, Any]:
    controls: dict[tuple[str, str, int, int], GameRun] = {}
    snapshots: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}

    def control(context: tuple[str, str, int, int]) -> GameRun:
        if context not in controls:
            lane, opponent, seed, seat = context
            value = run_game(lane, current_control_path(lane), opponent, seed, seat, capture_trace=True)
            snapshots[lane].append({
                "context": {"opponent_family": opponent, "seed": seed, "seat": seat},
                "snapshot": _trigger_snapshot(value),
            })
            value.trace.clear()
            controls[context] = value
        return controls[context]

    candidate_cache: dict[tuple[str, str, int, int, str], dict[str, Any]] = {}

    def evaluate(window: CandidateWindow, context: tuple[str, str, int, int]) -> dict[str, Any]:
        key = (*context, window.candidate_id)
        if key not in candidate_cache:
            base = control(context)
            lane, opponent, seed, seat = context
            forced = run_game(
                lane, current_control_path(lane), opponent, seed, seat,
                policy_factory=make_forced_factory(window), capture_trace=False,
            )
            candidate_cache[key] = _row(base, forced, window)
        return candidate_cache[key]

    screen_contexts = {
        lane: tuple((lane, opponent, CONSUMED_SEEDS[0], 0) for opponent in OPPONENTS)
        for lane in LANES
    }
    full_contexts = {
        lane: tuple((lane, opponent, seed, seat)
                    for opponent in OPPONENTS for seed in CONSUMED_SEEDS for seat in (0, 1))
        for lane in LANES
    }
    result_lanes: dict[str, Any] = {}
    for lane in LANES:
        windows = candidates(lane)
        screen_rows: dict[str, list[dict[str, Any]]] = {
            window.candidate_id: [evaluate(window, context) for context in screen_contexts[lane]]
            for window in windows
        }
        screen_summaries = {
            candidate_id: _summarize(rows) for candidate_id, rows in screen_rows.items()
        }
        selected_ids = [
            candidate_id for candidate_id, _ in
            sorted(screen_summaries.items(), key=lambda item: (_rank(item[1]), item[0]), reverse=True)[:expand_count]
        ]
        by_id = {window.candidate_id: window for window in windows}
        expanded_rows = {
            candidate_id: [evaluate(by_id[candidate_id], context) for context in full_contexts[lane]]
            for candidate_id in selected_ids
        }
        expanded_summaries = {
            candidate_id: _summarize(rows) for candidate_id, rows in expanded_rows.items()
        }
        ranked = sorted(selected_ids, key=lambda candidate_id: (_rank(expanded_summaries[candidate_id]), candidate_id), reverse=True)
        result_lanes[lane] = {
            "candidate_count": len(windows),
            "screen_contexts": [list(context[1:]) for context in screen_contexts[lane]],
            "screen": [
                {"candidate": asdict(window), "summary": screen_summaries[window.candidate_id]}
                for window in windows
            ],
            "expanded_contexts": [list(context[1:]) for context in full_contexts[lane]],
            "expanded": [
                {
                    "rank": index + 1,
                    "candidate": asdict(by_id[candidate_id]),
                    "summary": expanded_summaries[candidate_id],
                    "rows": expanded_rows[candidate_id],
                    "consumed_discovery_support_only": True,
                    "efficacy_signal": False,
                }
                for index, candidate_id in enumerate(ranked)
            ],
        }
    result = {
        "schema_version": 1,
        "kind": "lane_local_time_shifted_counterfactual_search",
        "evidence_level": "consumed_discovery_support_only",
        "formal_games_run": 0,
        "fresh_seeds_selected": [],
        "pool_lanes": False,
        "search_contract": {
            "preserve_lane_baseline_action_multiset": True,
            "preserve_four_turn_horizon": True,
            "preserve_rejoin_endpoint": True,
            "screen_seed": CONSUMED_SEEDS[0],
            "expanded_consumed_seeds": list(CONSUMED_SEEDS),
            "screen_seat": 0,
            "opponent_families": list(OPPONENTS),
            "expand_count_per_lane": expand_count,
        },
        "trigger_snapshots": snapshots,
        "lanes": result_lanes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expand-count", type=int, default=4)
    args = parser.parse_args()
    result = run(args.output, args.expand_count)
    compact = {
        lane: [
            {"rank": row["rank"], "candidate_id": row["candidate"]["candidate_id"],
             "actions": row["candidate"]["actions"], "summary": row["summary"]}
            for row in value["expanded"]
        ]
        for lane, value in result["lanes"].items()
    }
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
