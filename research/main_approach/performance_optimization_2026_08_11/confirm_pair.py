"""Alternating paired replay benchmark for small layer effects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import harness  # noqa: E402


def _once(path: Path, observations: list[dict], seed: int, tag: str) -> float:
    _, agent, _ = harness.load_agent(path, tag)
    config = harness.configuration(seed)
    total = 0.0
    for raw in observations:
        observation = harness.structify(raw)
        started = time.perf_counter()
        harness.invoke(agent, observation, config)
        total += time.perf_counter() - started
    return total * 1000.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer", required=True)
    parser.add_argument("--before-root", type=Path, required=True)
    parser.add_argument("--after-root", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--opponent", required=True)
    parser.add_argument("--repetitions", type=int, default=31)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = {}
    for strategy in harness.STRATEGIES:
        before = args.before_root.resolve() / strategy / "main.py"
        after = (
            args.after_root.resolve() / strategy / "main.py"
            if args.after_root
            else ROOT / "research/main_approach" / strategy / "main.py"
        )
        seats = []
        for seat in (0, 1):
            trace = harness.run_game(
                before, args.opponent, args.seed, seat, capture_observations=True,
                tag=f"{args.layer}_{strategy}_{seat}_trace",
            )
            values = {"before": [], "after": []}
            for repetition in range(args.repetitions):
                order = (("before", before), ("after", after)) if repetition % 2 == 0 else (("after", after), ("before", before))
                for name, path in order:
                    values[name].append(_once(path, trace["observations"], args.seed, f"{args.layer}_{strategy}_{seat}_{repetition}_{name}"))
            before_median = statistics.median(values["before"])
            after_median = statistics.median(values["after"])
            seats.append({
                "seat": seat,
                "before_ms": values["before"],
                "after_ms": values["after"],
                "before_median_ms": before_median,
                "after_median_ms": after_median,
                "speedup": before_median / max(after_median, 1e-12),
            })
        results[strategy] = {
            "seats": seats,
            "improved_both_seats": all(row["after_median_ms"] < row["before_median_ms"] for row in seats),
            "median_speedup": statistics.median(row["speedup"] for row in seats),
        }
    payload = {
        "layer": args.layer,
        "protocol": {"seed": args.seed, "opponent": args.opponent, "seats": [0, 1], "alternating_repetitions": args.repetitions},
        "strategies": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({name: {"improved_both_seats": row["improved_both_seats"], "median_speedup": row["median_speedup"]} for name, row in results.items()}, indent=2))


if __name__ == "__main__":
    main()
