"""Exact-engine technical-only evaluator for Async V3 finalists."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Callable, Iterator

from compiler import ROUTES
from materialize import materialize_finalist
from model import CompiledCandidate, LANES, compiled_from_payload, payload_hash
from runtime import apply_candidate_action


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TECHNICAL_SEED = 811407
FORMAL_RETAINED_SEEDS = (81426017, 81426029)
CONTROLS = {lane: ROUTES[lane].parent.parent / "main.py" for lane in LANES}
PUBLIC = {"kaito_v21": ROOT / "research" / "public_agents" / "kaito_v21_top30" / "extracted" / "main.py"}


def _load_runner() -> Any:
    path = ROOT / "research" / "job_value_residual_2026-08-12"
    old = list(sys.path)
    prior_protocol = sys.modules.pop("protocol", None)
    prior_runner = sys.modules.pop("engine_runner", None)
    try:
        sys.path.insert(0, str(path))
        return importlib.import_module("engine_runner")
    finally:
        sys.path[:] = old
        if prior_protocol is not None:
            sys.modules["protocol"] = prior_protocol
        if prior_runner is not None:
            sys.modules["engine_runner"] = prior_runner


RUNNER = _load_runner()


def engine_fingerprint() -> dict[str, Any]:
    return RUNNER.assert_engine_current()


def _technical_seed(seed: int) -> None:
    if int(seed) != TECHNICAL_SEED:
        raise PermissionError(f"Async V3 development is restricted to technical seed {TECHNICAL_SEED}")


def _formal_seed(seed: int, seed_record: dict[str, Any] | None) -> None:
    """Guard the future retained-only E1c executor at the engine boundary."""
    if int(seed) not in FORMAL_RETAINED_SEEDS:
        raise PermissionError("formal evaluator accepts only declared retained E1c seeds")
    if not seed_record or int(seed_record.get("seed", -1)) != int(seed):
        raise PermissionError("formal seed record missing")
    if seed_record.get("classification") != "retained_consumed" or bool(seed_record.get("fresh", True)):
        raise PermissionError("formal seed must be explicitly retained/consumed and non-fresh")


def opponent_path(lane: str, family: str) -> Path:
    if family == "other_incumbent":
        return CONTROLS["boatlee_v16_rc2_market_relay" if lane == "v27_current_meta" else "v27_current_meta"]
    if family in PUBLIC:
        return PUBLIC[family]
    raise ValueError(family)


@contextmanager
def _opponents() -> Iterator[None]:
    original = RUNNER.opponent_path
    RUNNER.opponent_path = opponent_path
    try:
        yield
    finally:
        RUNNER.opponent_path = original


def run_control(lane: str, opponent: str, seed: int, seat: int, *, capture_trace: bool = False) -> Any:
    _technical_seed(seed)
    with _opponents():
        return RUNNER.run_game(lane, CONTROLS[lane], opponent, int(seed), int(seat), capture_trace=capture_trace)


def _fast_policy(candidate: CompiledCandidate, base_agent: Callable[..., dict]) -> Callable[..., dict]:
    def wrapped(obs: Any, configuration: Any = None) -> dict[str, Any]:
        base = base_agent(obs) if candidate.lane == "boatlee_v16_rc2_market_relay" else base_agent(obs, configuration)
        return apply_candidate_action(candidate, obs, base)["action"]
    return wrapped


def run_fast(candidate: CompiledCandidate, opponent: str, seed: int, seat: int, *, capture_trace: bool = False) -> Any:
    _technical_seed(seed)
    with _opponents():
        return RUNNER.run_game(candidate.lane, CONTROLS[candidate.lane], opponent, int(seed), int(seat), policy_factory=lambda _module, base, _seat: _fast_policy(candidate, base), capture_trace=capture_trace)


def run_standalone(candidate: CompiledCandidate, output: Path, opponent: str, seed: int, seat: int) -> Any:
    _technical_seed(seed)
    materialize_finalist(candidate, output)
    with _opponents():
        return RUNNER.run_game(candidate.lane, output, opponent, int(seed), int(seat))


def behavior_view(run: Any) -> dict[str, Any]:
    return RUNNER.behavior_view(run)


def technical_valid(summary: dict[str, Any]) -> bool:
    return (
        summary.get("statuses") == ["DONE", "DONE"]
        and summary.get("exception") is None and summary.get("opponent_exception") is None
        and int(summary.get("timeout_calls", 0)) == 0 and not bool(summary.get("overage_exhausted"))
        and int(summary.get("max_market_orders", 0)) <= 10
        and not any(summary.get("action_issues", {}).values())
    )


def _trace_payload(run: Any) -> dict[str, Any]:
    """Canonical trace evidence kept in worker shards, without persisting a tape."""
    frames = [
        {
            "step": int(frame.step), "action": frame.action, "observation": frame.observation,
            "market_receipts": [list(item) for item in frame.market_receipts],
            "capacity_certification": frame.capacity_certification,
        }
        for frame in run.trace
    ]
    receipts = [item for frame in frames for item in frame["market_receipts"]]
    summary = run.summary
    return {
        "action_digest": summary.get("action_digest"),
        "state_digest": payload_hash([row["observation"] for row in frames]),
        "trace_digest": payload_hash(frames),
        "receipts": receipts,
        "receipt_digest": payload_hash(receipts),
        "economic_diagnostics": summary.get("diagnostics", {}),
        "latency_ms": summary.get("latency_ms", {}),
    }


def _outcome(run: Any) -> dict[str, Any]:
    summary = run.summary
    seat = int(run.seat)
    rewards = summary.get("rewards", [0.0, 0.0])
    money = summary.get("money", [0.0, 0.0])
    return {
        "technical_status": "complete" if technical_valid(summary) else "technical_invalid",
        "summary": summary,
        "evidence": _trace_payload(run),
        "own_reward": float(rewards[seat]),
        "opponent_reward": float(rewards[1 - seat]),
        "own_bank": float(money[seat]),
        "opponent_bank": float(money[1 - seat]),
    }


def _formal_control(job: dict[str, Any]) -> dict[str, Any]:
    context = job["context"]
    _formal_seed(int(context["seed"]), job.get("seed_record"))
    with _opponents():
        run = RUNNER.run_game(str(context["lane"]), CONTROLS[str(context["lane"])], str(context["opponent"]), int(context["seed"]), int(context["seat"]), capture_trace=True)
    return _outcome(run)


def _formal_candidate(job: dict[str, Any]) -> dict[str, Any]:
    context = job["context"]
    _formal_seed(int(context["seed"]), job.get("seed_record"))
    candidate = compiled_from_payload(job["candidate"])
    with _opponents():
        run = RUNNER.run_game(
            candidate.lane, CONTROLS[candidate.lane], str(context["opponent"]), int(context["seed"]), int(context["seat"]),
            policy_factory=lambda _module, base, _seat: _fast_policy(candidate, base), capture_trace=True,
        )
    outcome = _outcome(run)
    cache_path = Path(str(job["control_cache_path"]))
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    control = cache.get(str(job["control_job_id"]))
    if not isinstance(control, dict) or control.get("technical_status") != "complete":
        raise RuntimeError("lane-relative frozen control cache is absent or invalid")
    outcome["control_job_id"] = str(job["control_job_id"])
    outcome["control"] = control
    outcome["paired"] = {
        "margin_delta": (outcome["own_reward"] - outcome["opponent_reward"]) - (float(control["own_reward"]) - float(control["opponent_reward"])),
        "own_bank_delta": outcome["own_bank"] - float(control["own_bank"]),
        "win_delta": int(outcome["own_reward"] > outcome["opponent_reward"]) - int(float(control["own_reward"]) > float(control["opponent_reward"])),
    }
    return outcome


def _mock_outcome(job: dict[str, Any]) -> dict[str, Any]:
    """Deterministic no-engine stand-in used only to prove formal plumbing."""
    context = job["context"]
    basis = int(payload_hash({"kind": job["kind"], "context": context, "candidate": job.get("candidate", {}).get("candidate_id")})[:8], 16)
    own = float(100000 + basis % 1000)
    opponent = float(99900 + (basis // 7) % 1000)
    evidence = {
        "action_digest": payload_hash({"mock": True, "context": context, "candidate": job.get("candidate", {}).get("candidate_id"), "kind": job["kind"]}),
        "state_digest": payload_hash({"mock_state": context}), "trace_digest": payload_hash({"mock_trace": context}),
        "receipts": [], "receipt_digest": payload_hash([]), "economic_diagnostics": {},
        "latency_ms": {"calls": 719, "p95": 0.0, "max": 0.0},
    }
    row = {"technical_status": "complete", "summary": {"statuses": ["DONE", "DONE"], "calls": 719, "rewards": [own, opponent], "money": [own, opponent], "action_digest": evidence["action_digest"], "exception": None, "opponent_exception": None, "timeout_calls": 0, "overage_exhausted": False, "max_market_orders": 0, "action_issues": {}, "diagnostics": {}, "latency_ms": evidence["latency_ms"]}, "evidence": evidence, "own_reward": own, "opponent_reward": opponent, "own_bank": own, "opponent_bank": opponent}
    if job["kind"] == "candidate":
        cache = json.loads(Path(str(job["control_cache_path"])).read_text(encoding="utf-8"))
        control = cache[str(job["control_job_id"])]
        row["control_job_id"] = str(job["control_job_id"])
        row["control"] = control
        row["paired"] = {"margin_delta": (own - opponent) - (float(control["own_reward"]) - float(control["opponent_reward"])), "own_bank_delta": own - float(control["own_bank"]), "win_delta": int(own > opponent) - int(float(control["own_reward"]) > float(control["opponent_reward"]))}
    return row


def evaluate_job(job: dict[str, Any]) -> dict[str, Any]:
    """Exact formal worker entrypoint; dry/mock is explicit and carries no efficacy."""
    mode = str(job.get("evaluation_mode", "formal_exact"))
    if mode == "development_mock":
        outcome = _mock_outcome(job)
        return {"status": "complete", "evaluation_kind": "development_mock", "evaluator_invoked": True, "efficacy": None, "result": outcome}
    if mode != "formal_exact":
        raise ValueError("unknown evaluation mode")
    outcome = _formal_control(job) if job["kind"] == "control" else _formal_candidate(job)
    if outcome["technical_status"] != "complete":
        return {"status": "technical_invalid", "evaluation_kind": "formal_exact", "evaluator_invoked": True, "efficacy": None, "result": outcome}
    return {"status": "complete", "evaluation_kind": "formal_exact", "evaluator_invoked": True, "efficacy": {"formal": True}, "result": outcome}


def formal_finalist_parity(
    candidate: CompiledCandidate,
    output: Path,
    *,
    opponent: str,
    seed: int,
    seat: int,
    seed_record: dict[str, Any],
) -> dict[str, Any]:
    """Future exact finalizer: only the selected frontier receives ``main.py``."""
    _formal_seed(seed, seed_record)
    with _opponents():
        fast = RUNNER.run_game(
            candidate.lane, CONTROLS[candidate.lane], opponent, int(seed), int(seat),
            policy_factory=lambda _module, base, _seat: _fast_policy(candidate, base), capture_trace=True,
        )
        materialize_finalist(candidate, output)
        standalone = RUNNER.run_game(candidate.lane, output, opponent, int(seed), int(seat), capture_trace=True)
    fast_outcome = _outcome(fast)
    standalone_outcome = _outcome(standalone)
    return {
        "candidate_id": candidate.candidate_id, "opponent": opponent, "seed": int(seed), "seat": int(seat),
        "equal": behavior_view(fast) == behavior_view(standalone), "fast": fast_outcome, "standalone": standalone_outcome,
        "artifact": str(output), "finalist_only": True,
    }
