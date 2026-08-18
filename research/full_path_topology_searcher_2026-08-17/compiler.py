"""Bounded branch compiler and standalone materializer.

Compilation is development-only.  It preserves the incumbent outside an
explicit branch window and fails closed to the incumbent on malformed or
missing state.
"""

from __future__ import annotations

from dataclasses import asdict
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

try:
    from .model import BranchSpec, canonical_json
except ImportError:
    from model import BranchSpec, canonical_json


LANE_DIR = Path(__file__).resolve().parent
ROOT = LANE_DIR.parents[1]
INCUMBENTS = {
    "v27_current_meta": ROOT / "research/main_approach/v27_current_meta/main.py",
    "boatlee_v16_rc2_market_relay": ROOT / "research/main_approach/boatlee_v16_rc2_market_relay/main.py",
}
FORBIDDEN_IMPORTS = {"multiprocessing", "pandas", "requests", "sklearn", "socket", "subprocess"}
MAX_CANDIDATE_BYTES = 5 * 1024 * 1024
PROTECTED_OUTPUT_ROOTS = (
    ROOT / "research/main_approach",
    ROOT / "research/dual_incumbent_topology_search_2026-08-14",
)
MOTIF_FIELDS = {"kind", "patches"}
PATCH_FIELDS = {"step", "farmer", "actor_actions", "market", "market_mode", "market_index"}


RUNTIME_SOURCE = r'''
# ---- full-path topology searcher bounded runtime ----
_FP_BASE_AGENT = agent
_FP_STATE = {0: {"last": -1, "active": False, "status": "idle"}, 1: {"last": -1, "active": False, "status": "idle"}}
def _fp_get(value, key, default=None):
    if isinstance(value, dict): return value.get(key, default)
    getter = getattr(value, "get", None)
    return getter(key, default) if callable(getter) else getattr(value, key, default)
def _fp_path(value, path):
    keys = path.split("."); current = value
    if keys[0] in ("own_farm", "opponent_farm"):
        player = _fp_get(value, "player", None)
        if not isinstance(player, int) or isinstance(player, bool) or player not in (0, 1): return None, False
        seat = player
        index = seat if keys[0] == "own_farm" else 1 - seat
        farms = _fp_get(value, "farms", []) or []
        if not isinstance(farms, list) or index >= len(farms): return None, False
        current = farms[index]; keys = keys[1:]
    for key in keys:
        if isinstance(current, dict):
            if key not in current: return None, False
            current = current[key]
        elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        else:
            current = _fp_get(current, key, None)
            if current is None: return None, False
    return current, True
def _fp_compare(actual, op, expected, tolerance=0):
    if op == "eq":
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)): return abs(float(actual)-float(expected)) <= float(tolerance)
        return actual == expected
    if op == "ge": return actual >= expected
    if op == "gt": return actual > expected
    if op == "le": return actual <= expected
    if op == "lt": return actual < expected
    if op == "in": return actual in expected
    return False
def _fp_trigger(obs):
    trigger = _FP_SPEC.get("trigger", {})
    clauses = trigger.get("all", [])
    if not isinstance(clauses, list): return False
    for clause in clauses:
        if not isinstance(clause, dict) or not isinstance(clause.get("path"), str): return False
        actual, present = _fp_path(obs, clause["path"])
        if not present or not _fp_compare(actual, clause.get("op", "eq"), clause.get("value"), clause.get("tolerance", 0)): return False
    return True
def _fp_copy(action, hands):
    action = action if isinstance(action, dict) else {}
    hand_rows = [list(row or ["PASS"]) for row in list(action.get("hands") or [])[:hands]]
    hand_rows.extend([["PASS"] for _ in range(max(0, hands - len(hand_rows)))])
    return {"farmer": list(action.get("farmer") or ["PASS"]), "hands": hand_rows, "market": [list(row or []) for row in list(action.get("market") or [])[:10] if isinstance(row, list)]}
_FP_CROPS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"}
_FP_ANIMALS = {"GOOSE", "COW", "SHEEP"}
_FP_PRODUCTS = _FP_CROPS | {"EGG", "MILK", "WOOL", "FERTILIZER"}
def _fp_positive_int(value): return isinstance(value, int) and not isinstance(value, bool) and value > 0
def _fp_valid_unit(row):
    if not isinstance(row, list) or not row or not isinstance(row[0], str): return False
    op = row[0]
    if op in {"NORTH", "SOUTH", "EAST", "WEST", "PASS", "DROP", "WATER", "HARVEST", "FERTILIZE", "BUILD_COOP", "BUILD_PASTURE", "DIG", "FEED", "COLLECT_FERTILIZER", "CARE"}: return len(row) == 1
    if op == "PLANT": return len(row) == 2 and row[1] in _FP_CROPS
    if op in {"PICKUP", "PLACE"}: return len(row) in (2, 3) and row[1] in (_FP_PRODUCTS | _FP_ANIMALS) and (len(row) == 2 or _fp_positive_int(row[2]))
    return False
def _fp_valid_market(row):
    if not isinstance(row, list) or not row or not isinstance(row[0], str): return False
    if row[0] in {"HIRE", "BUY_LAND"}: return len(row) == 1
    if len(row) != 3 or not _fp_positive_int(row[2]): return False
    if row[0] == "BUY_SEED": return row[1] in _FP_CROPS
    if row[0] == "BUY_PRODUCT": return row[1] in {"WHEAT", "FERTILIZER"}
    if row[0] == "BUY_ANIMAL": return row[1] in _FP_ANIMALS
    if row[0] == "SELL": return row[1] in _FP_PRODUCTS
    return False
def _fp_valid_action(action):
    return isinstance(action, dict) and _fp_valid_unit(action.get("farmer")) and all(_fp_valid_unit(row) for row in action.get("hands", [])) and len(action.get("market", [])) <= 10 and all(_fp_valid_market(row) for row in action.get("market", []))
def _fp_has_plant(action):
    return isinstance(action, dict) and any(isinstance(row, list) and row and row[0] == "PLANT" for row in [action.get("farmer"), *(action.get("hands") or [])])
def _fp_seed_ledger_ready(obs, action):
    if not _fp_has_plant(action): return True
    private = _fp_get(obs, "private", None); seeds = _fp_get(private, "seeds", None)
    requested = {str(row[1]) for row in [action.get("farmer"), *(action.get("hands") or [])] if isinstance(row, list) and len(row) >= 2 and row[0] == "PLANT"}
    return isinstance(seeds, dict) and all(crop in seeds and isinstance(seeds[crop], int) and not isinstance(seeds[crop], bool) and seeds[crop] >= 0 for crop in requested)
def _fp_atomic(obs, action):
    private = _fp_get(obs, "private", None); seeds = _fp_get(private, "seeds", None)
    if not _fp_seed_ledger_ready(obs, action): return None
    demand = {}
    for row in [action.get("farmer"), *(action.get("hands") or [])]:
        if isinstance(row, list) and len(row) >= 2 and row[0] == "PLANT": demand[str(row[1])] = demand.get(str(row[1]), 0) + 1
    blocked = {crop for crop, count in demand.items() if count > int(seeds.get(crop, 0) or 0)}
    if not blocked: return action
    if len(action["farmer"]) >= 2 and action["farmer"][0] == "PLANT" and str(action["farmer"][1]) in blocked: action["farmer"] = ["PASS"]
    action["hands"] = [["PASS"] if len(row) >= 2 and row[0] == "PLANT" and str(row[1]) in blocked else row for row in action["hands"]]
    return action
def _fp_project(obs, action):
    try:
        base_hands = len(action.get("hands", []) or []) if isinstance(action, dict) and isinstance(action.get("hands", []), list) else 0
        player = _fp_get(obs, "player", None)
        farms = _fp_get(obs, "farms", []) or []
        farm = farms[player] if isinstance(player, int) and not isinstance(player, bool) and player in (0, 1) and player < len(farms) and isinstance(farms[player], dict) else {}
        hand_count = len(_fp_get(farm, "hands", []) or []) if farm else base_hands
        atomic = _fp_atomic(obs, _fp_copy(action, hand_count))
        if atomic is None: raise ValueError("missing atomic seed ledger")
        projected = _fp_copy(atomic, hand_count)
        if _fp_valid_action(projected): return projected
    except Exception:
        hand_count = 0
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(hand_count)], "market": []}
def _fp_compatible(obs):
    try:
        contract = _FP_SPEC["continuation"].get("rejoin", {})
        expected = contract.get("expected", {}); tolerances = contract.get("tolerances", {})
        for path in contract.get("compatibility_fields", []):
            actual, present = _fp_path(obs, path)
            if not present: return None
            if not _fp_compare(actual, "eq", expected.get(path), tolerances.get(path, 0)): return False
        return True
    except Exception:
        return None
def _fp_patch(obs, base, step):
    action = _fp_project(obs, base)
    patch = next((row for row in _FP_SPEC.get("motif", {}).get("patches", []) if int(row.get("step", -1)) == step), None)
    if patch is None: return action, True
    if "farmer" in patch: action["farmer"] = list(patch["farmer"])
    for actor, order in patch.get("actor_actions", []):
        actor = int(actor)
        if not 0 <= actor < len(action["hands"]): return _fp_project(obs, base), False
        action["hands"][actor] = list(order)
    mode = patch.get("market_mode", "preserve")
    orders = [list(row) for row in patch.get("market", []) if isinstance(row, list)]
    if mode == "replace": action["market"] = orders
    elif mode == "append": action["market"] = action["market"] + orders
    elif mode == "insert":
        index = int(patch.get("market_index", 0)); action["market"] = action["market"][:index] + orders + action["market"][index:]
    elif mode == "remove": action["market"] = [row for row in action["market"] if row not in orders]
    elif mode != "preserve": return _fp_project(obs, base), False
    if len(action["market"]) > 10 or not _fp_valid_action(action) or not _fp_seed_ledger_ready(obs, action):
        return _fp_project(obs, base), False
    projected = _fp_project(obs, action)
    return (projected, True) if _fp_valid_action(projected) else (_fp_project(obs, base), False)
def _fp_apply(obs, base):
    try:
        step = _fp_get(obs, "step", None); player = _fp_get(obs, "player", None)
        if (not isinstance(step, int) or isinstance(step, bool) or not 0 <= step <= 718
                or not isinstance(player, int) or isinstance(player, bool) or player not in (0, 1)):
            return _fp_project(obs, base)
        seat = player
        state = _FP_STATE[seat]
        if step == 0 or step < state["last"]: state.update({"last": step, "active": False, "status": "reset"})
        else: state["last"] = step
        if not _fp_valid_action(base):
            state.update({"active": False, "status": "technical_failure"}); return _fp_project(obs, base)
        if not _fp_seed_ledger_ready(obs, base):
            state.update({"active": False, "status": "technical_failure"}); return _fp_project(obs, base)
        decision = int(_FP_SPEC["decision_step"]); continuation = _FP_SPEC["continuation"]
        if step == decision and _fp_trigger(obs): state.update({"active": True, "status": "triggered"})
        if not state["active"]: return _fp_project(obs, base)
        if step > int(continuation["max_end_step"]):
            state.update({"active": False, "status": "continuation_failure"}); return _fp_project(obs, base)
        mode = continuation["mode"]
        if mode == "state_rejoin" and step >= int(continuation["min_end_step"]):
            compatible = _fp_compatible(obs)
            if compatible is None:
                state.update({"active": False, "status": "technical_failure"}); return _fp_project(obs, base)
            if compatible:
                state.update({"active": False, "status": "rejoined"}); return _fp_project(obs, base)
        action, patch_ok = _fp_patch(obs, base, step)
        if not patch_ok:
            state.update({"active": False, "status": "technical_failure"}); return _fp_project(obs, base)
        if mode == "immediate" or (mode == "fixed" and step >= int(continuation["max_end_step"])):
            state.update({"active": False, "status": "complete"})
        elif mode == "terminal_handoff" and step >= int(continuation["max_end_step"]):
            state.update({"active": False, "status": "complete"})
        return action
    except Exception:
        try: _FP_STATE[seat].update({"active": False, "status": "technical_failure"})
        except Exception: pass
        return _fp_project(obs, base)
def agent(obs, configuration=None):
    try:
        base = _FP_BASE_AGENT(obs) if _FP_SPEC["lane"] == "boatlee_v16_rc2_market_relay" else _FP_BASE_AGENT(obs, configuration)
    except Exception:
        try:
            player = _fp_get(obs, "player", None)
            if isinstance(player, int) and not isinstance(player, bool) and player in (0, 1):
                _FP_STATE[player].update({"active": False, "status": "technical_failure"})
        except Exception: pass
        return _fp_project(obs, {})
    return _fp_apply(obs, base)
def _kaggle_submission_entrypoint(obs, configuration=None):
    return agent(obs, configuration)
'''


def validate_motif(spec: BranchSpec) -> None:
    motif = spec.motif
    if not isinstance(motif, dict):
        raise ValueError("motif must be a mapping")
    unknown_motif = set(motif) - MOTIF_FIELDS
    if unknown_motif:
        raise ValueError(f"motif contains non-schema fields: {sorted(unknown_motif)}")
    if motif.get("kind") not in ("action_sequence", "market_edit", "terminal_controller"):
        raise ValueError("unsupported motif kind")
    patches = motif.get("patches")
    if not isinstance(patches, list) or not patches:
        raise ValueError("motif requires at least one patch")
    seen_steps: set[int] = set()
    for patch in patches:
        if not isinstance(patch, dict):
            raise ValueError("every patch must be a mapping")
        unknown_patch = set(patch) - PATCH_FIELDS
        if unknown_patch:
            raise ValueError(f"patch contains non-schema fields: {sorted(unknown_patch)}")
        step = patch.get("step")
        if not isinstance(step, int) or isinstance(step, bool):
            raise ValueError("patch step must be an integer")
        if step in seen_steps:
            raise ValueError(f"duplicate patch step is ambiguous at runtime: {step}")
        seen_steps.add(step)
        if not spec.decision_step <= step <= spec.continuation.max_end_step:
            raise ValueError("patch step lies outside the bounded continuation")
        market = patch.get("market", [])
        if not isinstance(market, list) or len(market) > 10 or any(not isinstance(row, list) for row in market):
            raise ValueError("market patch must be an ordered list capped at ten")
        if spec.continuation.mode == "immediate" and step != spec.decision_step:
            raise ValueError("immediate continuation cannot contain unreachable later patches")
        if "farmer" in patch and not _valid_unit_order(patch["farmer"]):
            raise ValueError("invalid farmer operation or arguments")
        actor_actions = patch.get("actor_actions", [])
        if not isinstance(actor_actions, list) or any(not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], int) or isinstance(row[0], bool) or row[0] < 0 or not _valid_unit_order(row[1]) for row in actor_actions):
            raise ValueError("invalid hand operation or arguments")
        if any(not _valid_market_order(row) for row in market):
            raise ValueError("invalid market operation or arguments")
        if patch.get("market_mode", "preserve") not in ("preserve", "replace", "append", "insert", "remove"):
            raise ValueError("unknown market edit mode")
        if patch["market_mode"] == "preserve" and market:
            raise ValueError("preserve-mode market rows would be ignored at runtime")
        if patch["market_mode"] != "insert" and "market_index" in patch:
            raise ValueError("market_index is meaningful for insert mode only")
        if patch.get("market_mode") == "insert" and (not isinstance(patch.get("market_index", 0), int) or isinstance(patch.get("market_index", 0), bool) or patch.get("market_index", 0) < 0 or patch.get("market_index", 0) > 10):
            raise ValueError("market insertion index must be within 0..10")
        if motif["kind"] == "market_edit" and ("farmer" in patch or patch["actor_actions"]):
            raise ValueError("market_edit patches cannot contain unit actions")
    if motif.get("kind") == "terminal_controller" and spec.continuation.mode != "terminal_handoff":
        raise ValueError("terminal controller requires terminal_handoff continuation")


CROPS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"}
ANIMALS = {"GOOSE", "COW", "SHEEP"}
PRODUCTS = CROPS | {"EGG", "MILK", "WOOL", "FERTILIZER"}


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_unit_order(row: Any) -> bool:
    if not isinstance(row, list) or not row or not isinstance(row[0], str):
        return False
    if row[0] in {"NORTH", "SOUTH", "EAST", "WEST", "PASS", "DROP", "WATER", "HARVEST", "FERTILIZE", "BUILD_COOP", "BUILD_PASTURE", "DIG", "FEED", "COLLECT_FERTILIZER", "CARE"}:
        return len(row) == 1
    if row[0] == "PLANT":
        return len(row) == 2 and row[1] in CROPS
    return row[0] in {"PICKUP", "PLACE"} and len(row) in (2, 3) and row[1] in PRODUCTS | ANIMALS and (len(row) == 2 or _positive_int(row[2]))


def _valid_market_order(row: Any) -> bool:
    if not isinstance(row, list) or not row or not isinstance(row[0], str):
        return False
    if row[0] in {"HIRE", "BUY_LAND"}:
        return len(row) == 1
    if len(row) != 3 or not _positive_int(row[2]):
        return False
    allowed = {"BUY_SEED": CROPS, "BUY_PRODUCT": {"WHEAT", "FERTILIZER"}, "BUY_ANIMAL": ANIMALS, "SELL": PRODUCTS}
    return row[0] in allowed and row[1] in allowed[row[0]]


def validate_attachment_and_evidence(spec: BranchSpec) -> None:
    expected_parent = f"{spec.lane}:spine:{spec.decision_step:03d}"
    if spec.parent_node_id != expected_parent:
        raise ValueError(f"branch parent is not the incumbent decision node: {expected_parent}")
    registry = json.loads((LANE_DIR / "evidence_registry.json").read_text(encoding="utf-8"))
    sources = {row["id"]: row for row in registry["sources"]}
    incumbent_id = "v27_incumbent" if spec.lane == "v27_current_meta" else "boatlee_incumbent"
    incumbent = INCUMBENTS[spec.lane]
    actual_hash = hashlib.sha256(incumbent.read_bytes()).hexdigest()
    if actual_hash != sources[incumbent_id]["sha256"] or incumbent.stat().st_size != sources[incumbent_id]["bytes"]:
        raise ValueError(f"frozen incumbent provenance drift: {spec.lane}")
    for evidence_id in spec.evidence_ids:
        if evidence_id not in sources:
            raise ValueError(f"unregistered evidence: {evidence_id}")
        evidence_lane = sources[evidence_id].get("lane")
        if evidence_lane is not None and evidence_lane != spec.lane:
            raise ValueError(f"cross-lane evidence is not attributable to {spec.lane}: {evidence_id}")


def render_standalone(spec: BranchSpec) -> str:
    validate_motif(spec)
    validate_attachment_and_evidence(spec)
    base = INCUMBENTS[spec.lane].read_text(encoding="utf-8").rstrip()
    payload = canonical_json(asdict(spec))
    return base + "\n_FP_SPEC = json.loads(" + repr(payload) + ")\n" + RUNTIME_SOURCE.strip() + "\n"


def _validate_output_boundary(output: Path) -> Path:
    resolved = output.resolve()
    for protected in PROTECTED_OUTPUT_ROOTS:
        protected_resolved = protected.resolve()
        try:
            resolved.relative_to(protected_resolved)
        except ValueError:
            continue
        raise ValueError(f"candidate output crosses a protected source/evidence boundary: {protected_resolved}")
    return resolved


def compile_candidate(spec: BranchSpec, output: Path) -> dict[str, Any]:
    output = _validate_output_boundary(Path(output))
    content = render_standalone(spec)
    encoded = content.encode("utf-8")
    if len(encoded) >= MAX_CANDIDATE_BYTES:
        raise ValueError(f"candidate exceeds the strict 5 MiB limit: {len(encoded)} bytes")
    with tempfile.TemporaryDirectory(prefix="full-path-prepublish-") as temporary:
        staged = Path(temporary) / "main.py"
        staged.write_bytes(encoded)
        audit = static_audit(staged)
        imported = isolated_import(staged) if audit["passed"] else {"isolated": False, "callable_agent": False, "callable_server_entrypoint": False}
        if not audit["passed"] or not all(imported.values()):
            raise ValueError(f"candidate prepublication checks failed: audit={audit}, import={imported}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".full-path-", suffix=".tmp", dir=output.parent, delete=False) as handle:
        temporary_output = Path(handle.name)
        handle.write(encoded)
    try:
        temporary_output.replace(output)
    finally:
        temporary_output.unlink(missing_ok=True)
    raw = output.read_bytes()
    return {"branch_id": spec.branch_id, "lane": spec.lane, "path": str(output.resolve()),
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "static_audit": audit,
            **imported, "size_passed": len(raw) < MAX_CANDIDATE_BYTES,
            "passed": len(raw) < MAX_CANDIDATE_BYTES and audit["passed"] and all(imported.values()),
            "development_only": True}


def static_audit(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): imports.update(row.name.split(".")[0] for row in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module: imports.add(node.module.split(".")[0])
    forbidden = sorted(imports & FORBIDDEN_IMPORTS)
    non_standard = sorted(imports - set(sys.stdlib_module_names) - {"__future__"})
    return {"imports": sorted(imports), "forbidden_imports": forbidden, "non_standard_imports": non_standard,
            "passed": not forbidden and not non_standard}


def isolated_import(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="full-path-isolated-") as temporary:
        copied = Path(temporary) / "main.py"
        shutil.copyfile(path, copied)
        spec = importlib.util.spec_from_file_location(f"full_path_{hashlib.sha256(copied.read_bytes()).hexdigest()[:12]}", copied)
        if spec is None or spec.loader is None:
            raise ImportError(copied)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {"isolated": True, "callable_agent": callable(getattr(module, "agent", None)),
                "callable_server_entrypoint": callable(getattr(module, "_kaggle_submission_entrypoint", None))}


def technical_evaluate(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    size_passed = size < MAX_CANDIDATE_BYTES
    if not size_passed:
        return {"passed": False, "bytes": size, "size_passed": False, "static_audit": None,
                "isolated": False, "callable_agent": False, "callable_server_entrypoint": False,
                "efficacy_claim": None, "formal_games_run": 0}
    audit = static_audit(path)
    imported = isolated_import(path) if audit["passed"] else {"isolated": False, "callable_agent": False, "callable_server_entrypoint": False}
    passed = audit["passed"] and all(imported.values())
    return {"passed": passed, "bytes": size, "size_passed": True, "static_audit": audit, **imported,
            "efficacy_claim": None, "formal_games_run": 0}
