"""Official-engine technical smoke and paired result extraction."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from .contract import LANES
from .genome import FullTapeGenome, RootRegistry
from .policy import make_policy_factory


ROOT = Path(__file__).resolve().parents[3]
JOB_LANE = ROOT / "research" / "job_value_residual_2026-08-12"
if str(JOB_LANE) not in sys.path:
    sys.path.insert(0, str(JOB_LANE))

from engine_runner import behavior_view, run_game  # noqa: E402


def official_noop_smoke(registry: RootRegistry, *, technical_seed: int = 811407) -> dict[str, Any]:
    rows = []
    for lane in LANES:
        root = registry.incumbent(lane)
        genome = FullTapeGenome(lane, root.root_id, root.digest)
        control_path = ROOT / "research" / "main_approach" / lane / "main.py"
        for seat in (0, 1):
            control = run_game(lane, control_path, "other_incumbent", technical_seed, seat, capture_trace=False)
            wrapped = run_game(
                lane, control_path, "other_incumbent", technical_seed, seat,
                policy_factory=make_policy_factory(genome, root), capture_trace=False,
            )
            control_view = behavior_view(control)
            wrapped_view = behavior_view(wrapped)
            rows.append({
                "lane": lane,
                "seat": seat,
                "technical_seed": technical_seed,
                "exact_behavior_equal": control_view == wrapped_view,
                "statuses": wrapped.summary["statuses"],
                "action_digest": wrapped.summary["action_digest"],
                "max_market_orders": wrapped.summary["max_market_orders"],
                "action_issues": wrapped.summary["action_issues"],
                "exception": wrapped.summary["exception"],
                "opponent_exception": wrapped.summary["opponent_exception"],
                "latency_ms": wrapped.summary["latency_ms"],
                "policy_metadata": wrapped.policy_metadata,
            })
    return {
        "schema_version": 1,
        "kind": "maximum_search_official_engine_noop_smoke",
        "technical_seed": technical_seed,
        "efficacy_signal": False,
        "formal_games_run": 0,
        "technical_games_run": len(rows) * 2,
        "passed": all(
            row["exact_behavior_equal"] and row["statuses"] == ["DONE", "DONE"]
            and row["max_market_orders"] <= 10 and all(value == 0 for value in row["action_issues"].values())
            for row in rows
        ),
        "rows": rows,
    }


def official_mutation_smoke(registry: RootRegistry, *, technical_seed: int = 811407) -> dict[str, Any]:
    """Execute one real lane-local point mutation in both seats."""
    rows = []
    for lane in LANES:
        root = registry.incumbent(lane)
        action = root.action_at(0)
        if not action["market"]:
            raise RuntimeError(f"{lane} step zero has no market order for mutation smoke")
        action["market"] = action["market"][:-1]
        genome = FullTapeGenome(lane, root.root_id, root.digest).with_actions({0: action}, root)
        control_path = ROOT / "research" / "main_approach" / lane / "main.py"
        for seat in (0, 1):
            control = run_game(lane, control_path, "other_incumbent", technical_seed, seat, capture_trace=False)
            candidate = run_game(
                lane, control_path, "other_incumbent", technical_seed, seat,
                policy_factory=make_policy_factory(genome, root), capture_trace=False,
            )
            rows.append({
                "lane": lane,
                "seat": seat,
                "technical_seed": technical_seed,
                "candidate_id": genome.candidate_id,
                "edit_distance": genome.edit_distance_from_root(),
                "action_digest_changed": candidate.summary["action_digest"] != control.summary["action_digest"],
                "statuses": candidate.summary["statuses"],
                "exception": candidate.summary["exception"],
                "opponent_exception": candidate.summary["opponent_exception"],
                "action_issues": candidate.summary["action_issues"],
                "max_market_orders": candidate.summary["max_market_orders"],
                "latency_ms": candidate.summary["latency_ms"],
            })
    return {
        "schema_version": 1,
        "kind": "maximum_search_official_engine_mutation_smoke",
        "technical_seed": technical_seed,
        "efficacy_signal": False,
        "formal_games_run": 0,
        "technical_games_run": len(rows) * 2,
        "passed": all(
            row["action_digest_changed"] and row["edit_distance"] == 1
            and row["statuses"] == ["DONE", "DONE"]
            and row["exception"] is None and row["opponent_exception"] is None
            and row["max_market_orders"] <= 10 and all(value == 0 for value in row["action_issues"].values())
            for row in rows
        ),
        "rows": rows,
    }
