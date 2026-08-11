"""Full current-engine equivalence check for generated and development agents."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
APPROACH_ROOT = Path(__file__).resolve().parent
AUDIT_RUNNER = (
    ROOT / "research" / "other_approach_submission_audit_2026-08-10" / "run_audit.py"
)
OUTPUT = APPROACH_ROOT / "development_validation.json"
SEED = 811407
STRATEGIES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
WORKTREE_CONTROLS = (
    APPROACH_ROOT / "performance_optimization_2026_08_11" / "controls" / "layer_00_baseline"
)
WORKTREE_CONTROL_SHA256 = {
    "v27_current_meta": "917fda167d98bbdea95307d61ff3954f56493404baa64ef8467407ad21571fb9",
    "boatlee_v16_rc2_market_relay": "02d9e7442a5efc425b767aae942d35a1acd41327b53a8038c694f7065b9e1379",
}


def _load_audit_runner():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.replay_engine_versions import VENDOR_ROOT

    if str(VENDOR_ROOT) not in sys.path:
        sys.path.insert(0, str(VENDOR_ROOT))
    spec = importlib.util.spec_from_file_location("main_approach_development_audit", AUDIT_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(AUDIT_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _head_source(strategy: str) -> bytes:
    relative = f"research/main_approach/{strategy}/main.py"
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    manifest = json.loads(
        (APPROACH_ROOT / strategy / "development" / "source_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    logical_digest = hashlib.sha256(result.stdout).hexdigest()
    checkout_digest = hashlib.sha256(result.stdout.replace(b"\n", b"\r\n")).hexdigest()
    if checkout_digest == manifest["standalone_before_split_sha256"]:
        return result.stdout
    frozen = WORKTREE_CONTROLS / strategy / "main.py"
    if frozen.is_file():
        frozen_bytes = frozen.read_bytes()
        frozen_digest = hashlib.sha256(frozen_bytes).hexdigest()
        if frozen_digest == WORKTREE_CONTROL_SHA256[strategy]:
            return frozen_bytes
    raise RuntimeError(
        f"neither HEAD nor frozen working-tree control matches for {strategy}; "
        f"HEAD logical digest was {logical_digest}"
    )


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "statuses": row["statuses"],
        "states": row["states"],
        "calls": row["calls"],
        "candidate_reward": row["candidate_reward"],
        "opponent_reward": row["opponent_reward"],
        "action_digest": row["action_digest"],
        "action_issues": row["action_issues"],
        "diagnostics": row["diagnostics"],
        "timeout_calls": row["timeout_calls"],
        "latency_ms": row["latency_ms"],
        "exception": row["exception"],
        "opponent_exception": row["opponent_exception"],
    }


def main() -> None:
    runner = _load_audit_runner()
    comparisons = []
    original_sha256 = {}
    with tempfile.TemporaryDirectory(prefix="kaggriculture-main-approach-") as temp:
        temp_root = Path(temp)
        for strategy in STRATEGIES:
            base = APPROACH_ROOT / strategy
            original_path = temp_root / f"{strategy}_original.py"
            original_bytes = _head_source(strategy)
            original_path.write_bytes(original_bytes)
            original_sha256[strategy] = hashlib.sha256(original_bytes).hexdigest()
            for seat in (0, 1):
                original = runner.play(
                    original_path,
                    f"{strategy}_original",
                    "kaito_v21",
                    SEED,
                    seat,
                    f"{strategy}_original_{seat}",
                )
                generated = runner.play(
                    base / "main.py",
                    f"{strategy}_generated",
                    "kaito_v21",
                    SEED,
                    seat,
                    f"{strategy}_generated_{seat}",
                )
                development = runner.play(
                    base / "development_main.py",
                    f"{strategy}_development",
                    "kaito_v21",
                    SEED,
                    seat,
                    f"{strategy}_development_{seat}",
                )
                rows = (original, generated, development)
                equal = (
                    all(row["statuses"] == ["DONE", "DONE"] for row in rows)
                    and len({row["candidate_reward"] for row in rows}) == 1
                    and len({row["opponent_reward"] for row in rows}) == 1
                    and len({row["action_digest"] for row in rows}) == 1
                    and original["action_issues"] == generated["action_issues"] == development["action_issues"]
                    and original["diagnostics"] == generated["diagnostics"] == development["diagnostics"]
                    and all(row["exception"] is None for row in rows)
                )
                comparisons.append(
                    {
                        "strategy": strategy,
                        "seed": SEED,
                        "seat": seat,
                        "equal": equal,
                        "original": _summary(original),
                        "generated": _summary(generated),
                        "development": _summary(development),
                    }
                )
    payload = {
        "status": "PASS" if all(row["equal"] for row in comparisons) else "FAIL",
        "current_engine_patch": "bded87b0d7879078c726a93a4884d044f79c4eed",
        "opponent": "kaito_v21",
        "comparisons": comparisons,
        "original_sha256": original_sha256,
        "original_checkout_sha256": {
            strategy: json.loads(
                (APPROACH_ROOT / strategy / "development" / "source_manifest.json").read_text(
                    encoding="utf-8"
                )
            )["standalone_before_split_sha256"]
            for strategy in STRATEGIES
        },
        "standalone_sha256": {
            strategy: _sha256(APPROACH_ROOT / strategy / "main.py")
            for strategy in STRATEGIES
        },
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if payload["status"] != "PASS":
        raise SystemExit("development/standalone equivalence failed")


if __name__ == "__main__":
    main()
