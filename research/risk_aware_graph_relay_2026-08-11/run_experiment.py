"""Run the counterfactual training and held-out paired evaluation."""

from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from engine_runner import GameResult, ROOT, run_game
from graph_model import (
    FlatMLPRegressor,
    GraphRegressor,
    parameter_count,
    save_model,
)
from relay_policy import intervention_factory


LANE = Path(__file__).resolve().parent
ARTIFACTS = LANE / "artifacts"
CANDIDATE = ROOT / "research/main_approach/boatlee_v16_rc2_market_relay/main.py"
OPPONENTS = {
    "v27_current_meta": ROOT / "research/main_approach/v27_current_meta/main.py",
    "v27_current_meta_safety_guarded": ROOT / "research/main_approach/v27_current_meta_safety_guarded/main.py",
    "kaito_v21_top30": ROOT / "research/public_agents/kaito_v21_top30/extracted/main.py",
    "roman_lb950": ROOT / "research/public_agents/roman_lb950/extracted/main.py",
    "saiteja_mega_ensemble_3000": ROOT / "research/public_agents/saiteja_mega_ensemble_3000/extracted/main.py",
}
TRAIN_PLAN = {
    "train": {
        "seeds": (101, 202),
        "opponents": ("v27_current_meta", "kaito_v21_top30"),
    },
    "validation": {
        "seeds": (303,),
        "opponents": ("v27_current_meta_safety_guarded", "roman_lb950"),
    },
}
TARGET_STEPS = (278, 350, 422, 494, 566, 638)
TEST_SEEDS = (404, 505)


def _risk(row: GameResult) -> dict[str, Any]:
    return {
        "animal_escapes": row.animal_escapes,
        "crop_deaths": row.crop_deaths,
        "fresh_crop_deaths": row.fresh_crop_deaths,
        "seed_overcommit_events": row.seed_overcommit_events,
        "seed_overcommit_units": row.seed_overcommit_units,
        "overflow_units": row.overflow_units,
        "terminal_inventory_units": row.terminal_inventory_units,
        "terminal_inventory_mark": row.terminal_inventory_mark,
    }


def generate_counterfactuals() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total = sum(
        len(plan["seeds"]) * len(plan["opponents"]) * 2 * len(TARGET_STEPS)
        for plan in TRAIN_PLAN.values()
    )
    index = 0
    for split, plan in TRAIN_PLAN.items():
        for seed in plan["seeds"]:
            for opponent_name in plan["opponents"]:
                for seat in (0, 1):
                    for step in TARGET_STEPS:
                        index += 1
                        force = run_game(
                            CANDIDATE,
                            OPPONENTS[opponent_name],
                            seed,
                            seat,
                            intervention_factory("force", step),
                        )
                        block = run_game(
                            CANDIDATE,
                            OPPONENTS[opponent_name],
                            seed,
                            seat,
                            intervention_factory("block", step),
                        )
                        snapshot = force.policy_metadata.get("snapshot") or block.policy_metadata.get("snapshot")
                        row = {
                            "split": split,
                            "seed": seed,
                            "opponent": opponent_name,
                            "seat": seat,
                            "step": step,
                            "force_margin": force.margin,
                            "block_margin": block.margin,
                            "delta_force_minus_block": force.margin - block.margin,
                            "force_quantity": force.policy_metadata.get("intervention_quantity", 0),
                            "block_quantity": block.policy_metadata.get("intervention_quantity", 0),
                            "force_risk": _risk(force),
                            "block_risk": _risk(block),
                            "force_technical_failures": force.exceptions + force.malformed_actions + force.timeout_calls + int(force.overage_exhausted),
                            "block_technical_failures": block.exceptions + block.malformed_actions + block.timeout_calls + int(block.overage_exhausted),
                            "snapshot": snapshot,
                        }
                        rows.append(row)
                        delta = row["delta_force_minus_block"]
                        print(
                            f"counterfactual {index:03d}/{total}: {split} {opponent_name} "
                            f"seed={seed} seat={seat} step={step} delta={delta:+.0f}",
                            flush=True,
                        )
    return rows


def _save_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _dataset(rows: list[dict[str, Any]], split: str) -> tuple[np.ndarray, np.ndarray]:
    selected = [row for row in rows if row["split"] == split and row.get("snapshot") is not None]
    return (
        np.asarray([row["snapshot"] for row in selected], dtype=np.float64),
        np.asarray([row["delta_force_minus_block"] for row in selected], dtype=np.float64),
    )


def train_models(rows: list[dict[str, Any]]):
    train_x, train_y = _dataset(rows, "train")
    validation = _dataset(rows, "validation")
    if len(train_x) == 0 or len(validation[0]) == 0:
        raise RuntimeError("counterfactual dataset is empty")
    gcn = GraphRegressor(hidden=32, seed=17)
    mlp = FlatMLPRegressor(hidden=4, seed=17)
    gcn_fit = gcn.fit(train_x, train_y, validation)
    mlp_fit = mlp.fit(train_x, train_y, validation)
    save_model(gcn, ARTIFACTS / "gcn_model.json")
    save_model(mlp, ARTIFACTS / "flat_mlp_model.json")
    fit = {
        "gcn": {**gcn_fit.__dict__, "parameters": parameter_count(gcn)},
        "flat_mlp": {**mlp_fit.__dict__, "parameters": parameter_count(mlp)},
        "train_samples": len(train_x),
        "validation_samples": len(validation[0]),
        "train_delta_summary": _values_summary(train_y.tolist()),
        "validation_delta_summary": _values_summary(validation[1].tolist()),
    }
    (ARTIFACTS / "fit_summary.json").write_text(
        json.dumps(fit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(fit, indent=2, sort_keys=True), flush=True)
    return gcn, mlp, fit


def evaluate(gcn: Any, mlp: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    policies = (
        ("control", None),
        ("always_force", intervention_factory("force")),
        ("gcn", intervention_factory("model", model=gcn)),
        ("flat_mlp", intervention_factory("model", model=mlp)),
    )
    total = len(TEST_SEEDS) * len(OPPONENTS) * 2 * len(policies)
    index = 0
    for seed in TEST_SEEDS:
        for opponent_name, opponent_path in OPPONENTS.items():
            for seat in (0, 1):
                for policy_name, factory in policies:
                    index += 1
                    result = run_game(CANDIDATE, opponent_path, seed, seat, factory)
                    row = result.as_dict()
                    row["opponent"] = opponent_name
                    row["policy"] = policy_name
                    rows.append(row)
                    print(
                        f"evaluation {index:03d}/{total}: {policy_name} {opponent_name} "
                        f"seed={seed} seat={seat} margin={result.margin:+.0f}",
                        flush=True,
                    )
    return rows


def _values_summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    tail_n = max(1, int(np.ceil(0.20 * len(ordered)))) if ordered else 1
    return {
        "count": len(values),
        "positive": sum(value > 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "negative": sum(value < 0 for value in values),
        "mean": statistics.fmean(values) if values else 0.0,
        "median": statistics.median(values) if values else 0.0,
        "worst": min(values, default=0.0),
        "cvar20": statistics.fmean(ordered[:tail_n]) if values else 0.0,
    }


def analyze(evaluation: list[dict[str, Any]], fit: dict[str, Any]) -> dict[str, Any]:
    controls = {
        (row["seed"], row["opponent"], row["seat"]): row
        for row in evaluation
        if row["policy"] == "control"
    }
    report: dict[str, Any] = {"fit": fit, "models": {}}
    for policy in ("always_force", "gcn", "flat_mlp"):
        policy_rows = [row for row in evaluation if row["policy"] == policy]
        deltas = []
        by_opponent: dict[str, list[float]] = defaultdict(list)
        soft_risk_delta: dict[str, float] = defaultdict(float)
        technical = 0
        for row in policy_rows:
            key = (row["seed"], row["opponent"], row["seat"])
            control = controls[key]
            delta = float(row["margin"]) - float(control["margin"])
            deltas.append(delta)
            by_opponent[row["opponent"]].append(delta)
            for metric in (
                "animal_escapes", "crop_deaths", "fresh_crop_deaths",
                "seed_overcommit_events", "seed_overcommit_units", "overflow_units",
                "terminal_inventory_units", "terminal_inventory_mark",
            ):
                soft_risk_delta[metric] += float(row[metric]) - float(control[metric])
            technical += int(row["exceptions"]) + int(row["malformed_actions"]) + int(row["timeout_calls"]) + int(row["overage_exhausted"])
        opponent_summary = {name: _values_summary(values) for name, values in by_opponent.items()}
        report["models"][policy] = {
            "paired_delta": _values_summary(deltas),
            "by_opponent": opponent_summary,
            "weakest_opponent_mean": min((item["mean"] for item in opponent_summary.values()), default=0.0),
            "technical_failures": technical,
            "soft_risk_delta_vs_control": dict(soft_risk_delta),
            "latency_p95_ms_max": max((float(row["latency_p95_ms"]) for row in policy_rows), default=0.0),
            "latency_max_ms": max((float(row["latency_max_ms"]) for row in policy_rows), default=0.0),
        }
    graph = report["models"]["gcn"]
    flat = report["models"]["flat_mlp"]
    static = report["models"]["always_force"]
    graph_delta = graph["paired_delta"]
    report["promotion"] = {
        "technical_gate": graph["technical_failures"] == 0,
        "held_out_mean_gate": graph_delta["mean"] > 0,
        "paired_win_gate": graph_delta["positive"] > graph_delta["negative"],
        "downside_gate": graph_delta["cvar20"] >= -100.0,
        "weakest_family_gate": graph["weakest_opponent_mean"] >= 0.0,
        "graph_ablation_gate": graph_delta["mean"] > max(
            flat["paired_delta"]["mean"], static["paired_delta"]["mean"]
        ),
    }
    report["promotion"]["promote"] = all(report["promotion"].values())
    return report


def save_evaluation(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    # Do not persist policy_metadata: it contains per-decision feature snapshots
    # derived from the candidate's private observation.  The safe audit export
    # retains outcomes, risk counts, and latency only.
    fieldnames = [
        "seed", "seat", "opponent", "policy", "own_score", "opponent_score",
        "margin", "status", "exceptions", "malformed_actions", "timeout_calls",
        "overage_exhausted", "latency_p95_ms", "latency_max_ms", "animal_escapes",
        "crop_deaths", "fresh_crop_deaths", "seed_overcommit_events",
        "seed_overcommit_units", "overflow_events", "overflow_units",
        "terminal_inventory_units", "terminal_inventory_mark",
    ]
    with (ARTIFACTS / "held_out_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fieldnames} for row in rows)


def main() -> int:
    started = time.perf_counter()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    dataset_path = ARTIFACTS / "counterfactuals.jsonl"
    if "--reuse-counterfactuals" in sys.argv and dataset_path.exists():
        counterfactuals = _load_jsonl(dataset_path)
    else:
        counterfactuals = generate_counterfactuals()
        _save_jsonl(dataset_path, counterfactuals)
    gcn, mlp, fit = train_models(counterfactuals)
    evaluation = evaluate(gcn, mlp)
    save_evaluation(evaluation)
    report = analyze(evaluation, fit)
    report["wall_time_seconds"] = time.perf_counter() - started
    (ARTIFACTS / "analysis.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
