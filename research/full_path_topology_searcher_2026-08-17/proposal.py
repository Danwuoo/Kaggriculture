"""Proposal ranking and bounded candidate serialization."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from .atlas import mutation_frontier
    from .model import BranchSpec
except ImportError:
    from atlas import mutation_frontier
    from model import BranchSpec


def rank_proposals(motifs: Iterable[dict[str, Any]], lane: str) -> list[dict[str, Any]]:
    return mutation_frontier(row for row in motifs if lane in row.get("lanes", []))


def write_branch(spec: BranchSpec, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(spec), indent=2, sort_keys=True) + "\n", encoding="utf-8")
