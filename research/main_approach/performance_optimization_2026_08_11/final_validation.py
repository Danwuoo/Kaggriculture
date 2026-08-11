"""Fresh official-engine games and standalone artifact verification."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import harness  # noqa: E402


BASELINE = HERE / "controls/layer_00_baseline"
FRESH_BLOCK = (
    (873001, "kaito_v21"),
    (873019, "saiteja_3000"),
    (873037, "other_incumbent"),
)
DETERMINISM_SEED = 873059
ISOLATED_SEED = 873077


def _valid(row: dict) -> bool:
    return (
        row["statuses"] == ["DONE", "DONE"]
        and row["calls"] == 719
        and row["exception"] is None
        and row["opponent_exception"] is None
        and all(value == 0 for value in row["action_issues"].values())
        and row["max_market_orders"] <= 10
        and row["timeout_calls"] == 0
        and not row["overage_exhausted"]
        and row["latency_ms"]["p95"] < 150.0
        and row["latency_ms"]["max"] < 750.0
    )


def _artifact(strategy: str) -> dict:
    base = ROOT / "research/main_approach" / strategy
    main = base / "main.py"
    source = main.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden_calls = {
        name: [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name]
        for name in ("open", "exec", "eval", "compile", "__import__")
    }
    with tempfile.TemporaryDirectory(prefix=f"{strategy}-builder-") as temp:
        temp_root = Path(temp)
        outputs = [temp_root / "first.py", temp_root / "second.py"]
        builder = base / "development/build_standalone.py"
        for output in outputs:
            subprocess.run([sys.executable, str(builder), "--output", str(output)], cwd=ROOT, check=True)
        deterministic = outputs[0].read_bytes() == outputs[1].read_bytes() == main.read_bytes()
    raw = main.read_bytes()
    return {
        "path": str(main),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "under_5_mib": len(raw) < 5 * 1024 * 1024,
        "imports": sorted(set(imports)),
        "standard_library_only": set(imports) <= {"base64", "json", "zlib", "math"},
        "forbidden_calls": forbidden_calls,
        "deterministic_builder": deterministic,
        "base64_route_codec": "base64.b64decode" in source and "base64.b85decode" not in source,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    harness.PUBLIC["baseline_v27"] = BASELINE / "v27_current_meta/main.py"
    harness.PUBLIC["baseline_boatlee"] = BASELINE / "boatlee_v16_rc2_market_relay/main.py"
    strategies = {}
    for strategy in harness.STRATEGIES:
        base = ROOT / "research/main_approach" / strategy
        paths = {
            "baseline": BASELINE / strategy / "main.py",
            "generated": base / "main.py",
            "development": base / "development_main.py",
        }
        games = []
        for seed, opponent_name in FRESH_BLOCK:
            opponent = opponent_name
            if opponent_name == "other_incumbent":
                opponent = "baseline_boatlee" if strategy == "v27_current_meta" else "baseline_v27"
            for seat in (0, 1):
                rows = {
                    name: harness.run_game(path, opponent, seed, seat, tag=f"final_{strategy}_{seed}_{seat}_{name}")
                    for name, path in paths.items()
                }
                equal = len({json.dumps(harness.behavior_view(row), sort_keys=True) for row in rows.values()}) == 1
                games.append({
                    "seed": seed,
                    "opponent": opponent,
                    "seat": seat,
                    "equal": equal,
                    "valid": all(_valid(row) for row in rows.values()),
                    "representations": {name: harness.compact_game(row) for name, row in rows.items()},
                })
        determinism = []
        for seat in (0, 1):
            first = harness.run_game(paths["generated"], "kaito_v21", DETERMINISM_SEED, seat, tag=f"det_{strategy}_{seat}_a")
            second = harness.run_game(paths["generated"], "kaito_v21", DETERMINISM_SEED, seat, tag=f"det_{strategy}_{seat}_b")
            determinism.append({
                "seat": seat,
                "equal": harness.behavior_view(first) == harness.behavior_view(second),
                "first": harness.compact_game(first),
                "second": harness.compact_game(second),
            })
        with tempfile.TemporaryDirectory(prefix=f"{strategy}-isolated-") as temp:
            isolated = Path(temp) / "main.py"
            isolated.write_bytes(paths["generated"].read_bytes())
            module, policy, import_ms = harness.load_agent(isolated, f"isolated_import_{strategy}")
            isolated_game = harness.run_game(isolated, "kaito_v21", ISOLATED_SEED, 0, tag=f"isolated_game_{strategy}")
            isolated_result = {
                "callable_agent": callable(policy),
                "route_steps": len(module._LEGACY_ACTIONS),
                "import_ms": import_ms,
                "game": harness.compact_game(isolated_game),
                "valid_game": _valid(isolated_game),
            }
        generated_games = [row["representations"]["generated"] for row in games]
        wins = sum(row["candidate_reward"] > row["opponent_reward"] for row in generated_games)
        draws = sum(row["candidate_reward"] == row["opponent_reward"] for row in generated_games)
        losses = sum(row["candidate_reward"] < row["opponent_reward"] for row in generated_games)
        artifact = _artifact(strategy)
        passed = (
            all(row["equal"] and row["valid"] for row in games)
            and all(row["equal"] for row in determinism)
            and isolated_result["callable_agent"]
            and isolated_result["route_steps"] == 719
            and isolated_result["valid_game"]
            and artifact["under_5_mib"]
            and artifact["standard_library_only"]
            and all(not rows for rows in artifact["forbidden_calls"].values())
            and artifact["deterministic_builder"]
            and artifact["base64_route_codec"]
        )
        strategies[strategy] = {
            "status": "PASS" if passed else "FAIL",
            "fresh_games": games,
            "fresh_wins_draws_losses": [wins, draws, losses],
            "determinism": determinism,
            "isolated_artifact": isolated_result,
            "artifact": artifact,
        }
    payload = {
        "status": "PASS" if all(row["status"] == "PASS" for row in strategies.values()) else "FAIL",
        "engine": harness.engine_fingerprint(),
        "protocol": {
            "fresh_block": [{"seed": seed, "opponent": opponent} for seed, opponent in FRESH_BLOCK],
            "seats": [0, 1],
            "determinism_seed": DETERMINISM_SEED,
            "isolated_seed": ISOLATED_SEED,
        },
        "strategies": strategies,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "strategies": {
            name: {"status": row["status"], "fresh_wdl": row["fresh_wins_draws_losses"], "artifact": row["artifact"]}
            for name, row in strategies.items()
        },
    }, indent=2))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
