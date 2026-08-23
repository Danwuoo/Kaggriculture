"""Evaluate hash-frozen compiled branches on consumed discovery contexts only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JOB_LANE = ROOT / "research/job_value_residual_2026-08-12"
if str(JOB_LANE) not in sys.path:
    sys.path.insert(0, str(JOB_LANE))

from engine_runner import GameRun, run_game  # noqa: E402
def _hash(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def _margin(run: GameRun) -> float:
    rewards = run.summary["rewards"]
    return float(rewards[run.seat]) - float(rewards[1 - run.seat])


def _outcome(value: float) -> str:
    return "W" if value > 0 else "L" if value < 0 else "D"


def _technical(run: GameRun) -> bool:
    summary = run.summary
    return (
        summary["statuses"] == ["DONE", "DONE"]
        and summary["exception"] is None
        and summary["opponent_exception"] is None
        and summary["timeout_calls"] == 0
        and not summary["overage_exhausted"]
        and summary["max_market_orders"] <= 10
        and all(value == 0 for value in summary["action_issues"].values())
    )


def _row(control: GameRun, candidate: GameRun) -> dict[str, Any]:
    left_margin, right_margin = _margin(control), _margin(candidate)
    left, right = _outcome(left_margin), _outcome(right_margin)
    rank = {"L": 0, "D": 1, "W": 2}
    delta = right_margin - left_margin
    if rank[right] != rank[left]:
        sign = "positive" if rank[right] > rank[left] else "negative"
    else:
        sign = "positive" if delta > 0 else "negative" if delta < 0 else "neutral"
    return {
        "context": {
            "opponent_family": control.opponent_family,
            "seed": control.seed,
            "seat": control.seat,
        },
        "control_margin": left_margin,
        "candidate_margin": right_margin,
        "margin_delta": delta,
        "control_outcome": left,
        "candidate_outcome": right,
        "outcome_transition": f"{left}_TO_{right}",
        "sign": sign,
        "technical_pass": _technical(candidate),
        "action_digest_changed": candidate.summary["action_digest"] != control.summary["action_digest"],
        "opponent_action_digest_changed": candidate.summary["opponent_action_digest"] != control.summary["opponent_action_digest"],
        "money_delta": float(candidate.summary["money"][candidate.seat]) - float(control.summary["money"][control.seat]),
        "terminal_inventory_units_delta": int(candidate.summary["terminal_inventory"]["units"]) - int(control.summary["terminal_inventory"]["units"]),
        "diagnostic_delta": {
            key: int(candidate.summary["diagnostics"][key]) - int(control.summary["diagnostics"][key])
            for key in ("animal_escapes", "crop_deaths", "fresh_crop_deaths", "shed_overflow_units")
        },
        "candidate_action_digest": candidate.summary["action_digest"],
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [float(row["margin_delta"]) for row in rows]
    transitions: dict[str, int] = {}
    for row in rows:
        transition = str(row["outcome_transition"])
        transitions[transition] = transitions.get(transition, 0) + 1
    family_seat = {}
    for row in rows:
        key = f"{row['context']['opponent_family']}:seat{row['context']['seat']}"
        family_seat.setdefault(key, []).append(float(row["margin_delta"]))
    return {
        "contexts": len(rows),
        "positive": sum(row["sign"] == "positive" for row in rows),
        "neutral": sum(row["sign"] == "neutral" for row in rows),
        "negative": sum(row["sign"] == "negative" for row in rows),
        "transition_matrix": dict(sorted(transitions.items())),
        "mean_margin_delta": statistics.fmean(deltas),
        "min_margin_delta": min(deltas),
        "max_margin_delta": max(deltas),
        "mean_money_delta": statistics.fmean(float(row["money_delta"]) for row in rows),
        "technical_pass": all(row["technical_pass"] for row in rows),
        "effective_change": any(row["action_digest_changed"] for row in rows),
        "changed_contexts": sum(row["action_digest_changed"] for row in rows),
        "fallback_contexts": sum(not row["action_digest_changed"] for row in rows),
        "family_seat_mean_margin_delta": {
            key: statistics.fmean(values) for key, values in sorted(family_seat.items())
        },
        "consumed_support_only": True,
        "efficacy_signal": False,
    }


def run(manifest_path: Path, output: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("formal_efficacy_authorized") is not False:
        raise ValueError("compiled screen manifest is not a proposal-only V1 contract")
    controls: dict[tuple[str, str, int, int], GameRun] = {}
    results = []
    for registered in manifest["candidates"]:
        lane = str(registered["lane"])
        spec_path = ROOT / registered["spec_path"]
        candidate_path = ROOT / registered["candidate_path"]
        control_path = ROOT / registered["control_path"]
        if _hash(spec_path) != (registered["spec_bytes"], registered["spec_sha256"]):
            raise ValueError(f"spec drift: {registered['id']}")
        if _hash(candidate_path) != (registered["candidate_bytes"], registered["candidate_sha256"]):
            raise ValueError(f"candidate drift: {registered['id']}")
        if _hash(control_path) != (registered["control_bytes"], registered["control_sha256"]):
            raise ValueError(f"control drift: {registered['id']}")
        rows = []
        for opponent in manifest["opponent_families"]:
            for seed in manifest["consumed_seeds"]:
                for seat in manifest["seats"]:
                    context = (lane, str(opponent), int(seed), int(seat))
                    if context not in controls:
                        controls[context] = run_game(
                            lane, control_path, context[1], context[2], context[3], capture_trace=False,
                        )
                    candidate = run_game(
                        lane, candidate_path, context[1], context[2], context[3], capture_trace=False,
                    )
                    rows.append(_row(controls[context], candidate))
        results.append({
            "id": registered["id"],
            "lane": lane,
            "mechanism": registered["mechanism"],
            "spec_sha256": registered["spec_sha256"],
            "candidate_sha256": registered["candidate_sha256"],
            "summary": _summary(rows),
            "rows": rows,
        })
    result = {
        "schema_version": 1,
        "kind": "consumed_compiled_counterfactual_screen_result",
        "manifest_sha256": _hash(manifest_path)[1],
        "formal_games_run": 0,
        "consumed_discovery_games_run": len(controls) + sum(len(row["rows"]) for row in results),
        "fresh_seeds_selected": [],
        "pool_lanes": False,
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.manifest, args.output)
    print(json.dumps([
        {"id": row["id"], "lane": row["lane"], "summary": row["summary"]}
        for row in result["results"]
    ], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
