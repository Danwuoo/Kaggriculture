"""Immutable paths and experiment strata for the job-value residual lane."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LANE_ROOT = Path(__file__).resolve().parent
REPORT_ROOT = ROOT / "reports" / "job_value_residual_2026-08-12"

INCUMBENTS = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
DISCOVERY_SEEDS = (93687444, 65365230)
SCREEN_SEEDS = (76238482, 47896298, 37504575, 22465322)
CONFIRMATION_SEEDS = (
    22831087,
    27715185,
    39010211,
    44100301,
    89716831,
    79417473,
    15516570,
    28880297,
)
OPPONENT_FAMILIES = ("other_incumbent", "kaito_v21")

ENGINE_COMMIT = "bded87b0d7879078c726a93a4884d044f79c4eed"
ENGINE_BLOB = "4b78842d0f2d4abf6e318a8248b6306454f5c714"
CONFIG_BLOB = "0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8"
ENGINE_SHA256 = "fb9215c5e21a25243e2d13e75b3d70a79cf7d78fff150a90f1bb5eacf9ba2bcf"
CONFIG_SHA256 = "7f196f4aaf9b4e482fbd61ba4bf19f5cec4da0f81938ece756954035a65c0bb5"


def _require_incumbent(name: str) -> str:
    if name not in INCUMBENTS:
        raise ValueError(f"unknown incumbent: {name}")
    return name


def candidate_path(name: str) -> Path:
    """Return the mutable generated artifact for an incumbent candidate."""
    return ROOT / "research" / "main_approach" / _require_incumbent(name) / "main.py"


def control_path(name: str) -> Path:
    """Return the immutable copied generated artifact for an incumbent."""
    return LANE_ROOT / "controls" / _require_incumbent(name) / "main.py"


def opponent_path(incumbent: str, family: str) -> Path:
    """Return the frozen opponent artifact selected by public family only."""
    _require_incumbent(incumbent)
    if family == "other_incumbent":
        other = next(name for name in INCUMBENTS if name != incumbent)
        return control_path(other)
    if family == "kaito_v21":
        return ROOT / "research" / "public_agents" / "kaito_v21_top30" / "extracted" / "main.py"
    raise ValueError(f"unknown opponent family: {family}")


def readable_route(incumbent: str) -> Path:
    """Return the independently owned readable route for an incumbent."""
    return (
        ROOT
        / "research"
        / "main_approach"
        / _require_incumbent(incumbent)
        / "development"
        / "route_actions.json"
    )


def stage_contexts(stage: str) -> tuple[tuple[str, str, int, int], ...]:
    """Return the complete incumbent/family/seed/seat matrix for one stage."""
    pools = {
        "discovery": DISCOVERY_SEEDS,
        "screen": SCREEN_SEEDS,
        "confirmation": CONFIRMATION_SEEDS,
    }
    try:
        seeds = pools[stage]
    except KeyError as error:
        raise ValueError(f"unknown stage: {stage}") from error
    return tuple(
        (incumbent, family, seed, seat)
        for incumbent in INCUMBENTS
        for family in OPPONENT_FAMILIES
        for seed in seeds
        for seat in (0, 1)
    )
