"""Verified-prefix v25 -> zero-to-top complete-tape branch.

The first 161 calls execute the exact v25 artifact.  In parallel, the exact
zero-to-top artifact is shadow-called only to initialize its original overlay
state and to verify that its actual emitted action equals v25's action at each
common-prefix step.  At step 161 it may branch only when that runtime equality
held throughout; thereafter it executes the original zero-to-top full policy.
No generic maintenance action is ever generated.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent / "exact_backbone_correction_2026-08-10"
PREFIX_END = 161


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V25 = _load("_branch_v25", ROOT / "artifacts" / "v25_meta_reset" / "main.py")
ZERO = _load("_branch_zero", ROOT / "artifacts" / "zero_to_top_meta" / "main.py")
_STATE: dict[int, dict[str, Any]] = {0: {}, 1: {}}


def _digest(action: Any) -> str:
    return hashlib.sha256(json.dumps(action, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _seat(observation: dict[str, Any]) -> int:
    return int(observation.get("player", 0) or 0)


def _fresh_state(step: int) -> dict[str, Any]:
    return {"last_step": step, "checked": 0, "mismatches": [], "branched": False, "vetoed": False}


def branch_stats(seat: int | None = None) -> dict[str, Any]:
    if seat is None:
        return copy.deepcopy(_STATE)
    return copy.deepcopy(_STATE.get(seat, {}))


def agent(observation: dict[str, Any], configuration: dict[str, Any] | None = None) -> dict[str, Any]:
    step = int(observation.get("step", 0) or 0)
    seat = _seat(observation)
    state = _STATE.get(seat, {})
    if step == 0 or step < int(state.get("last_step", -1)):
        state = _fresh_state(step)
        _STATE[seat] = state
    state["last_step"] = step
    v25_action = V25.agent(observation, configuration)
    if step < PREFIX_END:
        zero_action = ZERO.agent(observation)
        state["checked"] += 1
        if _digest(v25_action) != _digest(zero_action):
            state["vetoed"] = True
            if len(state["mismatches"]) < 8:
                state["mismatches"].append(step)
        return v25_action
    if not state.get("vetoed", False):
        state["branched"] = True
        return ZERO.agent(observation)
    return v25_action
