"""Test-only loader for each incumbent's future job-value runtime module."""

from __future__ import annotations

import importlib.util
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
STRATEGIES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")


def runtime_path(strategy: str) -> Path:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    return ROOT / "research" / "main_approach" / strategy / "development" / "job_value.py"


def load_runtime(strategy: str) -> Any:
    path = runtime_path(strategy)
    spec = importlib.util.spec_from_file_location(f"job_value_test_{strategy}", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observation_fixture(*, strategy: str = "v27_current_meta", step: int = 0) -> dict[str, Any]:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    farm = {"money": 3000, "farmer": [0, 0], "hands": [], "tiles": [[None] * 10 for _ in range(10)]}
    return {
        "player": 0, "step": step, "day": step // 24, "hour": step % 24,
        "farms": [farm, {**farm, "tiles": [[None] * 10 for _ in range(10)]}],
        "private": {"shed": {}, "seeds": {}, "inventories": [{}]},
        "market": {"inventory": {}, "prices": {}}, "town": {"unlocked_shops": []},
    }


def official_configuration(seed: int):
    from research.main_approach.performance_optimization_2026_08_11 import harness
    return harness.configuration(seed)


def window_dict(window: Any) -> dict[str, Any]:
    return asdict(window)
