"""Exact current-engine evaluator for asynchronous topology candidates."""

from __future__ import annotations

from contextlib import contextmanager
import importlib
from pathlib import Path
import sys
from typing import Any, Iterator

from compiler import CONTROLS
from model import CompiledAsyncCandidate, LANES
from runtime import make_fast_policy


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TECHNICAL_SEED = 811407
PUBLIC = {
    "kaito_v21": ROOT / "research" / "public_agents" / "kaito_v21_top30" / "extracted" / "main.py",
    "roman_lb950": ROOT / "research" / "public_agents" / "roman_lb950" / "extracted" / "main.py",
    "saiteja_3000": ROOT / "research" / "public_agents" / "saiteja_mega_ensemble_3000" / "extracted" / "main.py",
}


def _load_runner() -> Any:
    path = ROOT / "research" / "job_value_residual_2026-08-12"
    old_path = list(sys.path)
    previous_protocol = sys.modules.pop("protocol", None)
    previous_runner = sys.modules.pop("engine_runner", None)
    try:
        sys.path.insert(0, str(path))
        return importlib.import_module("engine_runner")
    finally:
        sys.path[:] = old_path
        if previous_protocol is not None:
            sys.modules["protocol"] = previous_protocol
        if previous_runner is not None:
            sys.modules["engine_runner"] = previous_runner


RUNNER = _load_runner()


def engine_fingerprint() -> dict[str, Any]:
    return RUNNER.assert_engine_current()


def opponent_path(lane: str, family: str) -> Path:
    if family == "other_incumbent":
        other = "boatlee_v16_rc2_market_relay" if lane == "v27_current_meta" else "v27_current_meta"
        return CONTROLS[other]
    if family in PUBLIC:
        return PUBLIC[family]
    raise KeyError(family)


@contextmanager
def _opponents() -> Iterator[None]:
    original = RUNNER.opponent_path
    RUNNER.opponent_path = opponent_path
    try:
        yield
    finally:
        RUNNER.opponent_path = original


def _seed(seed: int, formal_seeds: frozenset[int] | None = None) -> None:
    value = int(seed)
    if value == TECHNICAL_SEED:
        return
    if formal_seeds and value in formal_seeds:
        return
    raise PermissionError(
        f"async-v2 seed {value} is neither technical seed {TECHNICAL_SEED} "
        "nor present in the validated formal seed set"
    )


def run_control(
    lane: str,
    opponent: str,
    seed: int,
    seat: int,
    *,
    capture_trace: bool = False,
    formal_seeds: frozenset[int] | None = None,
) -> Any:
    if lane not in LANES:
        raise ValueError(lane)
    _seed(seed, formal_seeds)
    with _opponents():
        return RUNNER.run_game(lane, CONTROLS[lane], opponent, int(seed), int(seat), capture_trace=capture_trace)


def run_fast(
    candidate: CompiledAsyncCandidate,
    opponent: str,
    seed: int,
    seat: int,
    *,
    capture_trace: bool = False,
    formal_seeds: frozenset[int] | None = None,
) -> Any:
    _seed(seed, formal_seeds)

    def factory(module: Any, base_agent: Any, _seat: int) -> Any:
        return make_fast_policy(module, base_agent, candidate)

    with _opponents():
        return RUNNER.run_game(
            candidate.lane, CONTROLS[candidate.lane], opponent, int(seed), int(seat),
            policy_factory=factory, capture_trace=capture_trace,
        )


def run_standalone(
    candidate: CompiledAsyncCandidate,
    path: Path,
    opponent: str,
    seed: int,
    seat: int,
    *,
    formal_seeds: frozenset[int] | None = None,
) -> Any:
    _seed(seed, formal_seeds)
    with _opponents():
        return RUNNER.run_game(candidate.lane, path, opponent, int(seed), int(seat))


def behavior_view(run: Any) -> dict[str, Any]:
    return RUNNER.behavior_view(run)


def technical_valid(summary: dict[str, Any]) -> bool:
    return not any((
        summary["statuses"] != ["DONE", "DONE"],
        summary["exception"] is not None,
        summary["opponent_exception"] is not None,
        int(summary["timeout_calls"]) > 0,
        bool(summary["overage_exhausted"]),
        int(summary["max_market_orders"]) > 10,
        any(summary["action_issues"].values()),
    ))


def paired_view(control: dict[str, Any], candidate: dict[str, Any], seat: int) -> dict[str, Any]:
    control_rewards = control["rewards"]
    candidate_rewards = candidate["rewards"]
    control_margin = float(control_rewards[seat]) - float(control_rewards[1 - seat])
    candidate_margin = float(candidate_rewards[seat]) - float(candidate_rewards[1 - seat])
    return {
        "control_rewards": control_rewards,
        "candidate_rewards": candidate_rewards,
        "paired_margin_delta": candidate_margin - control_margin,
        "own_bank_delta": float(candidate_rewards[seat]) - float(control_rewards[seat]),
    }
