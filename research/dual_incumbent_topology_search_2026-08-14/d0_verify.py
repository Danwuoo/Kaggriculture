"""Freeze manifest and exact behavior-preservation check for D0 repairs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from exact_evaluator import CONTROL_PATHS, ROUTE_PATHS, TECHNICAL_SEED, _RUNNER, behavior_view, engine_fingerprint, run_control
from scheduler import atomic_json


LANE_ROOT = Path(__file__).resolve().parent
ROOT = LANE_ROOT.parents[1]
PRE_ROOT = LANE_ROOT / "artifacts" / "controls" / "pre_d0"


def hash_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def hash_head(path: Path) -> dict[str, Any]:
    relative = path.relative_to(ROOT).as_posix()
    raw = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=ROOT)
    return {"git_object": f"HEAD:{relative}", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def source_manifest(lane: str) -> dict[str, Any]:
    development = CONTROL_PATHS[lane].parent / "development"
    paths = sorted([*development.glob("*.py"), ROUTE_PATHS[lane]])
    return {
        str(path.relative_to(ROOT)): {
            "prechange_head": hash_head(path),
            "current": hash_file(path),
        }
        for path in paths
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lanes = tuple(CONTROL_PATHS)
    old = {lane: PRE_ROOT / lane / "main.py" for lane in lanes}
    for path in old.values():
        if not path.exists():
            raise FileNotFoundError(path)

    comparisons = []
    original_lookup = _RUNNER.opponent_path

    def old_opponent(lane: str, family: str) -> Path:
        if family != "other_incumbent":
            return original_lookup(lane, family)
        other = "boatlee_v16_rc2_market_relay" if lane == "v27_current_meta" else "v27_current_meta"
        return old[other]

    try:
        for lane in lanes:
            for seat in (0, 1):
                _RUNNER.opponent_path = old_opponent
                before = _RUNNER.run_game(lane, old[lane], "other_incumbent", TECHNICAL_SEED, seat)
                _RUNNER.opponent_path = original_lookup
                after = run_control(lane, "other_incumbent", TECHNICAL_SEED, seat)
                before_view = behavior_view(before)
                after_view = behavior_view(after)
                comparisons.append(
                    {
                        "lane": lane,
                        "seat": seat,
                        "equal": before_view == after_view,
                        "before": before_view,
                        "after": after_view,
                        "latency_after_ms": after.summary["latency_ms"],
                    }
                )
    finally:
        _RUNNER.opponent_path = original_lookup

    opponents = {
        "kaito_v21": ROOT / "research" / "public_agents" / "kaito_v21_top30" / "extracted" / "main.py",
        "roman_lb950": ROOT / "research" / "public_agents" / "roman_lb950" / "extracted" / "main.py",
        "saiteja_3000": ROOT / "research" / "public_agents" / "saiteja_mega_ensemble_3000" / "extracted" / "main.py",
        "guarded_v27": ROOT / "research" / "main_approach" / "v27_current_meta_safety_guarded" / "main.py",
    }
    payload = {
        "schema_version": 1,
        "technical_seed": TECHNICAL_SEED,
        "formal_fresh_seeds_executed": False,
        "engine": engine_fingerprint(),
        "controls": {
            lane: {"pre_d0": hash_file(old[lane]), "post_d0": hash_file(CONTROL_PATHS[lane])}
            for lane in lanes
        },
        "sources": {lane: source_manifest(lane) for lane in lanes},
        "opponents": {name: hash_file(path) for name, path in opponents.items()},
        "behavior_preservation": comparisons,
        "pass": all(row["equal"] for row in comparisons),
    }
    atomic_json(args.output, payload)
    print(json.dumps({"pass": payload["pass"], "output": str(args.output)}, sort_keys=True))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
