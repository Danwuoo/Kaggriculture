"""Run one frozen-control optimization-layer validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness import (  # noqa: E402
    STRATEGIES,
    behavior_view,
    cold_import_benchmark,
    compact_game,
    engine_fingerprint,
    file_fingerprint,
    replay_benchmark,
    run_game,
)


def _median_season(rows: list[dict]) -> float:
    return statistics.median(
        float(benchmark["season_total_ms"]["median"])
        for benchmark in rows
    )


def validate_layer(
    layer: str,
    before_root: Path,
    seed: int,
    opponent: str,
    repetitions: int,
) -> dict:
    strategies = {}
    for strategy in STRATEGIES:
        base = ROOT / "research/main_approach" / strategy
        paths = {
            "before": before_root / strategy / "main.py",
            "generated": base / "main.py",
            "development": base / "development_main.py",
        }
        games = []
        replays = {"before": [], "generated": []}
        for seat in (0, 1):
            control = run_game(paths["before"], opponent, seed, seat, capture_observations=True, tag=f"{layer}_{strategy}_{seat}_before")
            generated = run_game(paths["generated"], opponent, seed, seat, tag=f"{layer}_{strategy}_{seat}_generated")
            development = run_game(paths["development"], opponent, seed, seat, tag=f"{layer}_{strategy}_{seat}_development")
            equal = behavior_view(control) == behavior_view(generated) == behavior_view(development)
            games.append(
                {
                    "seat": seat,
                    "equal": equal,
                    "before": compact_game(control),
                    "generated": compact_game(generated),
                    "development": compact_game(development),
                }
            )
            observations = control["observations"]
            replays["before"].append(replay_benchmark(paths["before"], observations, seed, repetitions=repetitions, tag=f"{layer}_{strategy}_{seat}_before"))
            replays["generated"].append(replay_benchmark(paths["generated"], observations, seed, repetitions=repetitions, tag=f"{layer}_{strategy}_{seat}_generated"))
        before_ms = _median_season(replays["before"])
        after_ms = _median_season(replays["generated"])
        cold = {
            "before": cold_import_benchmark(paths["before"], repetitions),
            "generated": cold_import_benchmark(paths["generated"], repetitions),
        }
        strategies[strategy] = {
            "behavior_equal": all(row["equal"] for row in games),
            "games": games,
            "performance": {
                "before": replays["before"],
                "generated": replays["generated"],
                "season_median_ms_before": before_ms,
                "season_median_ms_after": after_ms,
                "speedup": before_ms / max(after_ms, 1e-12),
                "improvement_fraction": (before_ms - after_ms) / max(before_ms, 1e-12),
                "cold_import": cold,
            },
            "artifacts": {name: file_fingerprint(path) for name, path in paths.items()},
        }
    passed = all(row["behavior_equal"] for row in strategies.values())
    return {
        "layer": layer,
        "status": "PASS" if passed else "FAIL",
        "engine": engine_fingerprint(),
        "protocol": {
            "seed": seed,
            "opponent": opponent,
            "seats": [0, 1],
            "performance_repetitions": repetitions,
            "representations": ["frozen_before", "generated", "development"],
        },
        "strategies": strategies,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer", required=True)
    parser.add_argument("--before-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--opponent", required=True)
    parser.add_argument("--repetitions", type=int, default=11)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = validate_layer(args.layer, args.before_root.resolve(), args.seed, args.opponent, args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "output": str(args.output),
        "strategies": {
            name: {
                "behavior_equal": row["behavior_equal"],
                "season_median_ms_before": row["performance"]["season_median_ms_before"],
                "season_median_ms_after": row["performance"]["season_median_ms_after"],
                "speedup": row["performance"]["speedup"],
                "cold_import_before": row["performance"]["cold_import"]["before"]["median_ms"],
                "cold_import_after": row["performance"]["cold_import"]["generated"]["median_ms"],
            }
            for name, row in payload["strategies"].items()
        },
    }, indent=2))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
