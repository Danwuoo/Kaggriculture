"""Screen seven market tapes over one exact guarded 8-cow/4-sheep unit route."""

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


INCUMBENTS = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
OPPONENTS = ("other_incumbent", "kaito_v21")
SEED = 83171301


def candidate_paths() -> dict[str, Path]:
    manifest = json.loads((LANE / "artifacts" / "candidate_manifest.json").read_text(encoding="utf-8"))
    return {
        name: Path(row["path"])
        for name, row in manifest.items()
        if name.startswith("shared_guarded_r")
    }


def technical(summary: dict[str, Any]) -> bool:
    return (
        summary["statuses"] == ["DONE", "DONE"]
        and summary["exception"] is None and summary["opponent_exception"] is None
        and summary["timeout_calls"] == 0 and not summary["overage_exhausted"]
        and summary["max_market_orders"] <= 10
        and all(value == 0 for value in summary["action_issues"].values())
    )


def compact(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: summary[key] for key in (
        "statuses", "money", "action_digest", "opponent_action_digest", "action_issues",
        "max_market_orders", "diagnostics", "terminal_inventory", "exception", "opponent_exception",
        "timeout_calls", "overage_exhausted", "latency_ms",
    )}


def run(output: Path) -> dict[str, Any]:
    engine = engine_runner.assert_engine_current()
    candidates = candidate_paths()
    if len(candidates) != 7:
        raise RuntimeError(f"expected seven shared-unit market candidates, found {len(candidates)}")
    controls = {}
    pairs = []
    for incumbent in INCUMBENTS:
        for opponent in OPPONENTS:
            for seat in (0, 1):
                control = engine_runner.run_game(incumbent, job_protocol.control_path(incumbent), opponent, SEED, seat).summary
                controls[(incumbent, opponent, seat)] = control
                control_margin = float(control["money"][seat] - control["money"][1 - seat])
                for name, path in candidates.items():
                    candidate = engine_runner.run_game(incumbent, path, opponent, SEED, seat).summary
                    candidate_margin = float(candidate["money"][seat] - candidate["money"][1 - seat])
                    pairs.append({
                        "candidate": name, "incumbent": incumbent, "opponent": opponent,
                        "seed": SEED, "seat": seat, "technical_pass": technical(candidate),
                        "paired_margin_delta": candidate_margin - control_margin,
                        "own_bank_delta": float(candidate["money"][seat] - control["money"][seat]),
                        "control": compact(control), "candidate_run": compact(candidate),
                    })
    summaries = {}
    for name in candidates:
        summaries[name] = {}
        for incumbent in INCUMBENTS:
            rows = [row for row in pairs if row["candidate"] == name and row["incumbent"] == incumbent]
            deltas = [float(row["paired_margin_delta"]) for row in rows]
            family = {}
            for opponent in OPPONENTS:
                values = [float(row["paired_margin_delta"]) for row in rows if row["opponent"] == opponent]
                family[opponent] = {"positive_zero_negative": [sum(v > 0 for v in values), sum(v == 0 for v in values), sum(v < 0 for v in values)], "mean": statistics.fmean(values)}
            summaries[name][incumbent] = {
                "positive_zero_negative": [sum(v > 0 for v in deltas), sum(v == 0 for v in deltas), sum(v < 0 for v in deltas)],
                "mean_paired_margin_delta": statistics.fmean(deltas),
                "median_paired_margin_delta": statistics.median(deltas),
                "worst_paired_margin_delta": min(deltas),
                "mean_own_bank_delta": statistics.fmean(float(row["own_bank_delta"]) for row in rows),
                "technical_pass": all(row["technical_pass"] for row in rows),
                "opponent_families": family,
            }
    gate = {
        name: all(
            summary["technical_pass"]
            and summary["positive_zero_negative"] == [4, 0, 0]
            and all(row["positive_zero_negative"] == [2, 0, 0] for row in summary["opponent_families"].values())
            for summary in strata.values()
        )
        for name, strata in summaries.items()
    }
    report = {
        "schema_version": 1, "engine": engine,
        "protocol": {
            "unit_backbone": "exact shared unit tape 7a200e... with identical weed/seed guards",
            "variable": "only the seven observed public market tapes",
            "seed": SEED, "seats": [0, 1], "opponents": list(OPPONENTS), "incumbent_strata": list(INCUMBENTS),
            "gate": "zero technical faults and positive paired margin in both seats against both opponent families, independently in both incumbent strata",
        },
        "summaries": summaries, "gate": gate, "pairs": pairs,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=LANE / "artifacts" / "shared_market_screen.json")
    args = parser.parse_args()
    report = run(args.output.resolve())
    print(json.dumps({"summaries": report["summaries"], "gate": report["gate"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
