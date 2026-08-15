"""Pure seed classification for manifests and summaries.

Authorization describes permission to run.  It is intentionally independent
from whether an evaluated seed is technical, retained/consumed, or fresh.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from library import file_sha256


HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE / "formal" / "e1_seed_registry.json"


def load_seed_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_evaluation_seeds(
    evaluation_seeds: Iterable[int],
    *,
    formal_authorized: bool,
    registry: dict[str, Any] | None = None,
    registry_path: Path = DEFAULT_REGISTRY,
    explicit_fresh_seeds: Iterable[int] = (),
    execution_started: bool = False,
    execution_completed: bool = False,
) -> dict[str, Any]:
    """Classify seeds without running them or inferring freshness from authority."""
    seeds = tuple(int(seed) for seed in evaluation_seeds)
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("evaluation seeds must be non-empty and unique")
    if execution_completed and not execution_started:
        raise ValueError("execution_completed requires execution_started")
    registry = registry or load_seed_registry(registry_path)
    classifications = registry.get("classifications") or {}
    technical_known = {
        int(seed) for seed in classifications.get("technical", registry.get("technical", {}).get("seeds", ()))
    }
    retained_known = {
        int(seed) for seed in classifications.get("retained_consumed_e1", ())
    }
    fresh_explicit = {int(seed) for seed in explicit_fresh_seeds}
    if not fresh_explicit <= set(seeds):
        raise ValueError("explicit fresh seeds must be a subset of evaluation seeds")
    overlap = fresh_explicit & (technical_known | retained_known)
    if overlap:
        raise ValueError(f"known technical/retained seeds cannot be classified fresh: {sorted(overlap)}")

    technical = sorted(seed for seed in seeds if seed in technical_known)
    retained = sorted(seed for seed in seeds if seed in retained_known)
    fresh = sorted(seed for seed in seeds if seed in fresh_explicit)
    classified = set(technical) | set(retained) | set(fresh)
    unclassified = sorted(seed for seed in seeds if seed not in classified)
    return {
        "schema_version": 1,
        "registry_run_id": registry.get("run_id"),
        "seed_registry_file_sha256": file_sha256(registry_path) if registry_path.is_file() else None,
        "evaluation_seeds": list(seeds),
        "technical_seeds": technical,
        "retained_consumed_e1_seeds": retained,
        "fresh_seeds": fresh,
        "unclassified_seeds": unclassified,
        "formal_authorized": bool(formal_authorized),
        "technical_seeds_configured": bool(technical),
        "retained_e1_seeds_configured": bool(retained),
        "fresh_seeds_configured": bool(fresh),
        "execution_started": bool(execution_started),
        "execution_completed": bool(execution_completed),
        "technical_seeds_executed": bool(technical) and bool(execution_started),
        "retained_e1_seeds_executed": bool(retained) and bool(execution_started),
        "formal_fresh_seeds_executed": bool(fresh) and bool(execution_started),
    }
