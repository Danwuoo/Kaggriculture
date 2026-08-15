"""Finalist-only standalone materialization for canonical V3 payloads."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any

from compiler import ROUTES
from model import CompiledCandidate
from scheduler import atomic_json


FORBIDDEN_IMPORTS = {"subprocess", "multiprocessing", "socket", "requests", "pandas", "sklearn", "pathlib"}


RUNTIME_SOURCE = r'''
# ---- Async V3 finalist runtime (standard-library free overlay) ----
_V3_BASE_AGENT = agent
_V3_STATE = {0: -1, 1: -1}
def _v3_get(value, key, default=None):
    if isinstance(value, dict): return value.get(key, default)
    getter = getattr(value, "get", None)
    return getter(key, default) if callable(getter) else getattr(value, key, default)
def _v3_copy(action, hands):
    action = action if isinstance(action, dict) else {}
    return {"farmer": list(action.get("farmer") or ["PASS"]), "hands": [list(row or ["PASS"]) for row in list(action.get("hands") or [])[:hands]], "market": [list(row or []) for row in list(action.get("market") or [])[:10]]}
def _v3_atomic(obs, action):
    private = _v3_get(obs, "private", None); seeds = _v3_get(private, "seeds", None)
    if not isinstance(seeds, dict): return action
    demand = {}
    for row in [action.get("farmer"), *(action.get("hands") or [])]:
        if isinstance(row, list) and len(row) >= 2 and row[0] == "PLANT": demand[row[1]] = demand.get(row[1], 0) + 1
    blocked = {crop for crop, count in demand.items() if count > int(seeds.get(crop, 0) or 0)}
    if not blocked: return action
    result = _v3_copy(action, len(action.get("hands") or []))
    if len(result["farmer"]) >= 2 and result["farmer"][0] == "PLANT" and result["farmer"][1] in blocked: result["farmer"] = ["PASS"]
    result["hands"] = [["PASS"] if len(row) >= 2 and row[0] == "PLANT" and row[1] in blocked else row for row in result["hands"]]
    return result
def _v3_guard(guard, obs):
    if guard is None: return True
    market = _v3_get(obs, "market", None)
    if not isinstance(market, dict): return False
    product = guard["product"]
    if guard["kind"] in ("min_price", "max_price"):
        values = _v3_get(market, "prices", {}) or {}
        if product not in values: return False
        return int(values[product]) >= int(guard["threshold"]) if guard["kind"] == "min_price" else int(values[product]) <= int(guard["threshold"])
    values = _v3_get(market, "inventory", {}) or {}
    if product not in values: return False
    return int(values[product]) >= int(guard["threshold"]) if guard["kind"] == "min_inventory" else int(values[product]) <= int(guard["threshold"])
def _v3_apply(obs, base):
    seat = 1 if int(_v3_get(obs, "player", 0) or 0) == 1 else 0
    farms = _v3_get(obs, "farms", []) or []
    farm = farms[seat] if seat < len(farms) and isinstance(farms[seat], dict) else {}
    action = _v3_copy(base, len(_v3_get(farm, "hands", []) or []))
    if not isinstance(_v3_get(obs, "private", None), dict) or not isinstance(farms, list): return action
    if int(dict(_V3_SPEC["constants"])[_V3_GUARD]) and (not isinstance(_v3_get(obs, "market", None), dict) or not isinstance(_v3_get(_v3_get(obs, "market", {}), "prices", None), dict)): return action
    patch = next((row for row in _V3_SPEC["patches"] if int(row["step"]) == int(_v3_get(obs, "step", -1))), None)
    if patch is not None:
        action["market"] = [list(row["order"]) for row in patch["market_entries"] if _v3_guard(row.get("guard"), obs)][:min(10, int(dict(_V3_SPEC["constants"])[_V3_CAP]))]
    else:
        action["market"] = action["market"][:min(10, int(dict(_V3_SPEC["constants"])[_V3_CAP]))]
    minimum = int(dict(_V3_SPEC["constants"])[_V3_GUARD])
    if minimum:
        prices = _v3_get(_v3_get(obs, "market", {}), "prices", {}) or {}
        action["market"] = [row for row in action["market"] if not (len(row) >= 3 and row[0] == "SELL" and int(prices.get(row[1], -1)) < minimum)]
    return _v3_copy(_v3_atomic(obs, action), len(_v3_get(farm, "hands", []) or []))
def agent(obs, configuration=None):
    if _V3_SPEC["lane"] == "boatlee_v16_rc2_market_relay": base = _V3_BASE_AGENT(obs)
    else: base = _V3_BASE_AGENT(obs, configuration)
    return _v3_apply(obs, base)
'''


def render_standalone(candidate: CompiledCandidate) -> str:
    base = (ROUTES[candidate.lane].parent.parent / "main.py").read_text(encoding="utf-8")
    spec = json.dumps(candidate.runtime_payload(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    cap = "v27_market_order_cap" if candidate.lane == "v27_current_meta" else "boatlee_market_order_cap"
    guard = "v27_guard_min_price" if candidate.lane == "v27_current_meta" else "boatlee_guard_min_price"
    return base.rstrip() + "\n_V3_SPEC = json.loads(" + repr(spec) + ")\n_V3_CAP = " + repr(cap) + "\n_V3_GUARD = " + repr(guard) + "\n" + RUNTIME_SOURCE.strip() + "\n"


def materialize_finalist(candidate: CompiledCandidate, output: Path) -> dict[str, Any]:
    """The only materialization API: callers must explicitly nominate finalists."""
    content = render_standalone(candidate)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    raw = output.read_bytes()
    return {"lane": candidate.lane, "candidate_id": candidate.candidate_id, "path": str(output), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "finalist_only": True}


def static_audit(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(row.name.split(".")[0] for row in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    forbidden = sorted(imports & FORBIDDEN_IMPORTS)
    return {"imports": sorted(imports), "forbidden_imports": forbidden, "pass": not forbidden}


def isolated_import(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="async-v3-finalist-") as temporary:
        copied = Path(temporary) / "main.py"
        copied.write_bytes(path.read_bytes())
        spec = importlib.util.spec_from_file_location(f"async_v3_{hashlib.sha256(copied.read_bytes()).hexdigest()[:12]}", copied)
        if spec is None or spec.loader is None:
            raise ImportError(copied)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {"callable_agent": callable(getattr(module, "agent", None)), "isolated": True}
