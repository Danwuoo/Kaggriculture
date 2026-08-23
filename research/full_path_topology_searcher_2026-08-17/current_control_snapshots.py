"""Capture public decision-state snapshots for current-incumbent consumed controls."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JOB_LANE = ROOT / "research/job_value_residual_2026-08-12"
if str(JOB_LANE) not in sys.path:
    sys.path.insert(0, str(JOB_LANE))

from engine_runner import run_game  # noqa: E402


def _hash(path: Path) -> tuple[int, str]:
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest()


def _tile_counts(farm: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in farm.get("tiles", []) or []:
        for tile in row or []:
            if not isinstance(tile, dict):
                continue
            label = tile.get("animal") or tile.get("crop") or tile.get("kind")
            if label:
                result[str(label)] = result.get(str(label), 0) + 1
    return dict(sorted(result.items()))


def run(manifest_path: Path, output: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []
    seen: set[tuple[str, int, str, int, int]] = set()
    for candidate in manifest["candidates"]:
        lane = str(candidate["lane"])
        control = ROOT / candidate["control_path"]
        spec = json.loads((ROOT / candidate["spec_path"]).read_text(encoding="utf-8"))
        step = int(spec["decision_step"])
        if _hash(control) != (candidate["control_bytes"], candidate["control_sha256"]):
            raise ValueError(f"control drift: {candidate['id']}")
        for opponent in manifest["opponent_families"]:
            for seed in manifest["consumed_seeds"]:
                for seat in manifest["seats"]:
                    identity = (lane, step, str(opponent), int(seed), int(seat))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    game = run_game(lane, control, identity[2], identity[3], identity[4], capture_trace=True)
                    frame = next(item for item in game.trace if item.step == step)
                    observation = frame.observation
                    player = int(observation["player"])
                    own = observation["farms"][player]
                    other = observation["farms"][1 - player]
                    rows.append({
                        "lane": lane,
                        "decision_step": step,
                        "context": {"opponent_family": identity[2], "seed": identity[3], "seat": identity[4]},
                        "public_state": {
                            "own_money": own.get("money"),
                            "own_worker_count": 1 + len(own.get("hands", []) or []),
                            "own_tile_counts": _tile_counts(own),
                            "opponent_money": other.get("money"),
                            "opponent_worker_count": 1 + len(other.get("hands", []) or []),
                            "opponent_tile_counts": _tile_counts(other),
                            "market_prices": observation.get("market", {}).get("prices", {}),
                            "market_inventory": observation.get("market", {}).get("inventory", {}),
                            "town": observation.get("town", {}),
                        },
                    })
    result = {
        "schema_version": 1,
        "kind": "current_incumbent_consumed_public_state_snapshots",
        "manifest_sha256": _hash(manifest_path)[1],
        "formal_games_run": 0,
        "consumed_control_games_run": len(rows),
        "fresh_seeds_selected": [],
        "rows": rows,
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
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
