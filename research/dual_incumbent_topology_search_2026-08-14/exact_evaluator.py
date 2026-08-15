"""Exact-engine fast/standalone evaluator with lane-relative pairing."""

from __future__ import annotations

from contextlib import contextmanager
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Iterator

from materialize import materialize
from model import CompiledCandidate
from runtime_patch import make_fast_policy


LANE_ROOT = Path(__file__).resolve().parent
ROOT = LANE_ROOT.parents[1]
TECHNICAL_SEED = 811407
APPROACH_ROOT = ROOT / "research" / "main_approach"
CONTROL_PATHS = {
    "v27_current_meta": APPROACH_ROOT / "v27_current_meta" / "main.py",
    "boatlee_v16_rc2_market_relay": APPROACH_ROOT / "boatlee_v16_rc2_market_relay" / "main.py",
}
ROUTE_PATHS = {
    lane: APPROACH_ROOT / lane / "development" / "route_actions.json"
    for lane in CONTROL_PATHS
}
PUBLIC_PATHS = {
    "kaito_v21": ROOT / "research" / "public_agents" / "kaito_v21_top30" / "extracted" / "main.py",
    "roman_lb950": ROOT / "research" / "public_agents" / "roman_lb950" / "extracted" / "main.py",
    "saiteja_3000": ROOT / "research" / "public_agents" / "saiteja_mega_ensemble_3000" / "extracted" / "main.py",
}


def _load_legacy_runner() -> Any:
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


_RUNNER = _load_legacy_runner()


def engine_fingerprint() -> dict[str, Any]:
    return _RUNNER.assert_engine_current()


def opponent_path(lane: str, family: str) -> Path:
    if family == "other_incumbent":
        other = "boatlee_v16_rc2_market_relay" if lane == "v27_current_meta" else "v27_current_meta"
        return CONTROL_PATHS[other]
    if family in PUBLIC_PATHS:
        return PUBLIC_PATHS[family]
    raise KeyError(family)


@contextmanager
def _patched_opponent_lookup() -> Iterator[None]:
    original = _RUNNER.opponent_path
    _RUNNER.opponent_path = opponent_path
    try:
        yield
    finally:
        _RUNNER.opponent_path = original


def _validate_technical_seed(seed: int, *, allow_formal: bool = False) -> None:
    if int(seed) != TECHNICAL_SEED and not allow_formal:
        raise PermissionError(f"D0-D4 evaluator is restricted to technical seed {TECHNICAL_SEED}; got {seed}")


def run_control(
    lane: str,
    opponent: str,
    seed: int,
    seat: int,
    *,
    capture_trace: bool = False,
    allow_formal: bool = False,
) -> Any:
    _validate_technical_seed(seed, allow_formal=allow_formal)
    with _patched_opponent_lookup():
        return _RUNNER.run_game(
            lane,
            CONTROL_PATHS[lane],
            opponent,
            int(seed),
            int(seat),
            capture_trace=capture_trace,
        )


def run_fast(
    candidate: CompiledCandidate,
    opponent: str,
    seed: int,
    seat: int,
    *,
    capture_trace: bool = False,
    allow_formal: bool = False,
) -> Any:
    _validate_technical_seed(seed, allow_formal=allow_formal)

    def factory(module: Any, base_agent: Any, _seat: int) -> Any:
        return make_fast_policy(module, base_agent, candidate)

    with _patched_opponent_lookup():
        return _RUNNER.run_game(
            candidate.lane,
            CONTROL_PATHS[candidate.lane],
            opponent,
            int(seed),
            int(seat),
            policy_factory=factory,
            capture_trace=capture_trace,
        )


def run_standalone(
    candidate: CompiledCandidate,
    standalone: Path,
    opponent: str,
    seed: int,
    seat: int,
    *,
    capture_trace: bool = False,
    allow_formal: bool = False,
) -> Any:
    _validate_technical_seed(seed, allow_formal=allow_formal)
    with _patched_opponent_lookup():
        return _RUNNER.run_game(
            candidate.lane,
            standalone,
            opponent,
            int(seed),
            int(seat),
            capture_trace=capture_trace,
        )


def behavior_view(run: Any) -> dict[str, Any]:
    return _RUNNER.behavior_view(run)


def parity_audit(
    candidate: CompiledCandidate,
    output: Path,
    *,
    opponent: str = "other_incumbent",
    seed: int = TECHNICAL_SEED,
) -> dict[str, Any]:
    artifact = materialize(CONTROL_PATHS[candidate.lane], candidate, output)
    seats = []
    for seat in (0, 1):
        fast = run_fast(candidate, opponent, seed, seat)
        standalone = run_standalone(candidate, output, opponent, seed, seat)
        fast_view = behavior_view(fast)
        standalone_view = behavior_view(standalone)
        seats.append(
            {
                "seat": seat,
                "equal": fast_view == standalone_view,
                "fast": fast_view,
                "standalone": standalone_view,
                "fast_latency_ms": fast.summary["latency_ms"],
                "standalone_latency_ms": standalone.summary["latency_ms"],
            }
        )
    return {
        "lane": candidate.lane,
        "candidate_id": candidate.candidate_id,
        "genome_id": candidate.genome.genome_id,
        "artifact": artifact,
        "engine": engine_fingerprint(),
        "seed": seed,
        "opponent": opponent,
        "seats": seats,
        "pass": all(row["equal"] for row in seats),
    }


def paired_result(control: Any, candidate: Any) -> dict[str, Any]:
    seat = int(candidate.seat)
    control_margin = float(control.summary["rewards"][seat]) - float(control.summary["rewards"][1 - seat])
    candidate_margin = float(candidate.summary["rewards"][seat]) - float(candidate.summary["rewards"][1 - seat])
    return {
        "lane": candidate.incumbent,
        "opponent": candidate.opponent_family,
        "seed": candidate.seed,
        "seat": seat,
        "control_rewards": control.summary["rewards"],
        "candidate_rewards": candidate.summary["rewards"],
        "paired_margin_delta": candidate_margin - control_margin,
        "own_bank_delta": float(candidate.summary["rewards"][seat]) - float(control.summary["rewards"][seat]),
        "technical_failure": any(
            [
                candidate.summary["statuses"] != ["DONE", "DONE"],
                candidate.summary["exception"] is not None,
                candidate.summary["opponent_exception"] is not None,
                candidate.summary["timeout_calls"] > 0,
                candidate.summary["overage_exhausted"],
                candidate.summary["max_market_orders"] > 10,
                any(candidate.summary["action_issues"].values()),
            ]
        ),
        "diagnostics": candidate.summary["diagnostics"],
        "terminal_inventory": candidate.summary["terminal_inventory"],
        "latency_ms": candidate.summary["latency_ms"],
        "action_digest": candidate.summary["action_digest"],
    }


def load_route(lane: str) -> list[dict[str, Any]]:
    return json.loads(ROUTE_PATHS[lane].read_text(encoding="utf-8"))
