"""Small matched ablation for two new public high-score replay backbones."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parent
JOB_LANE = ROOT / "research" / "job_value_residual_2026-08-12"
sys.path.insert(0, str(JOB_LANE))

import engine_runner  # noqa: E402
import protocol as job_protocol  # noqa: E402


CANDIDATES = {
    "rank1_10c4s": LANE / "candidates" / "rank1_10c4s" / "main.py",
    "dominant_8c4s": LANE / "candidates" / "dominant_8c4s" / "main.py",
}
INCUMBENTS = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
OPPONENTS = ("other_incumbent", "kaito_v21")
SEED = 83171301


def outcome(margin: float) -> str:
    return "W" if margin > 0 else "L" if margin < 0 else "D"


def technical_pass(summary: dict[str, Any]) -> bool:
    return (
        summary["statuses"] == ["DONE", "DONE"]
        and summary["exception"] is None
        and summary["opponent_exception"] is None
        and summary["timeout_calls"] == 0
        and not summary["overage_exhausted"]
        and summary["max_market_orders"] <= 10
        and all(value == 0 for value in summary["action_issues"].values())
    )


def compact(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: summary[key] for key in (
        "statuses", "calls", "rewards", "money", "action_digest", "opponent_action_digest",
        "action_issues", "max_market_orders", "diagnostics", "terminal_inventory", "exception",
        "opponent_exception", "timeout_calls", "overage_exhausted", "latency_ms", "engine_fingerprint",
    )}


def play(path: Path, incumbent: str, opponent: str, seat: int) -> dict[str, Any]:
    return engine_runner.run_game(incumbent, path, opponent, SEED, seat).summary


def summarize_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [float(row["paired_margin_delta"]) for row in pairs]
    own = [float(row["candidate"]["money"][row["seat"]] - row["control"]["money"][row["seat"]]) for row in pairs]
    return {
        "pairs": len(pairs),
        "positive_zero_negative": [sum(value > 0 for value in deltas), sum(value == 0 for value in deltas), sum(value < 0 for value in deltas)],
        "mean_paired_margin_delta": statistics.fmean(deltas),
        "median_paired_margin_delta": statistics.median(deltas),
        "worst_paired_margin_delta": min(deltas),
        "mean_own_bank_delta": statistics.fmean(own),
        "outcome_improvements": sum(row["control_outcome"] != "W" and row["candidate_outcome"] == "W" for row in pairs),
        "outcome_regressions": sum(row["control_outcome"] == "W" and row["candidate_outcome"] != "W" for row in pairs),
        "technical_pass": all(row["technical_pass"] for row in pairs),
    }


def run(output: Path) -> dict[str, Any]:
    engine = engine_runner.assert_engine_current()
    pairs = []
    control_cache: dict[tuple[str, str, int], dict[str, Any]] = {}
    for candidate_name, candidate_path in CANDIDATES.items():
        if not candidate_path.is_file():
            raise FileNotFoundError(f"run build_candidates.py first: {candidate_path}")
        for incumbent in INCUMBENTS:
            for opponent in OPPONENTS:
                for seat in (0, 1):
                    key = (incumbent, opponent, seat)
                    control = control_cache.get(key)
                    if control is None:
                        control = play(job_protocol.control_path(incumbent), incumbent, opponent, seat)
                        control_cache[key] = control
                    candidate = play(candidate_path, incumbent, opponent, seat)
                    control_margin = float(control["money"][seat] - control["money"][1 - seat])
                    candidate_margin = float(candidate["money"][seat] - candidate["money"][1 - seat])
                    pairs.append({
                        "candidate_name": candidate_name, "incumbent_stratum": incumbent,
                        "opponent_family": opponent, "seed": SEED, "seat": seat,
                        "control_outcome": outcome(control_margin), "candidate_outcome": outcome(candidate_margin),
                        "paired_margin_delta": candidate_margin - control_margin,
                        "technical_pass": technical_pass(candidate),
                        "control": compact(control), "candidate": compact(candidate),
                    })

    first = play(CANDIDATES["dominant_8c4s"], "v27_current_meta", "kaito_v21", 0)
    second = play(CANDIDATES["dominant_8c4s"], "v27_current_meta", "kaito_v21", 0)
    deterministic = engine_runner.behavior_view(engine_runner.GameRun("v27_current_meta", "kaito_v21", SEED, 0, first, [], {})) == engine_runner.behavior_view(engine_runner.GameRun("v27_current_meta", "kaito_v21", SEED, 0, second, [], {}))

    strata = {}
    for candidate_name in CANDIDATES:
        strata[candidate_name] = {}
        for incumbent in INCUMBENTS:
            selected = [row for row in pairs if row["candidate_name"] == candidate_name and row["incumbent_stratum"] == incumbent]
            strata[candidate_name][incumbent] = summarize_pairs(selected)
    expansion_pass = {
        candidate: all(
            row["technical_pass"]
            and row["positive_zero_negative"][0] > row["positive_zero_negative"][2]
            and row["outcome_improvements"] > row["outcome_regressions"]
            and row["median_paired_margin_delta"] > 0
            for row in incumbent_rows.values()
        )
        for candidate, incumbent_rows in strata.items()
    }
    report = {
        "schema_version": 1,
        "engine": engine,
        "protocol": {
            "mechanism": "complete 719-turn public replay tape transplant with hand-count-only projection",
            "controls": list(INCUMBENTS), "opponents": list(OPPONENTS), "seed": SEED, "seats": [0, 1],
            "stopping_rule": "stop unless each incumbent stratum has technical validity, positive sign majority, positive median, and more outcome improvements than regressions",
            "freshness": "83171301 had no literal occurrence outside the new lane before protocol creation",
        },
        "deterministic": deterministic,
        "strata": strata,
        "expansion_pass": expansion_pass,
        "pairs": pairs,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=LANE / "artifacts" / "route_transplant_ablation.json")
    args = parser.parse_args()
    report = run(args.output.resolve())
    print(json.dumps({"deterministic": report["deterministic"], "strata": report["strata"], "expansion_pass": report["expansion_pass"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

