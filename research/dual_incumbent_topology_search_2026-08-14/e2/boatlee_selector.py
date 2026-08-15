"""Public-state Boatlee selector for the attributed E2 S2 remediation branch."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from authority import payload_hash


CONTROL_STEP_240 = [
    ["SELL", "WOOL", 16], ["SELL", "WHEAT", 2], ["BUY_LAND"],
    *[["HIRE"] for _ in range(7)],
]
CONTROL_STEP_241 = [
    *[["HIRE"] for _ in range(7)], ["BUY_SEED", "MELON", 7],
]
INTERVENTION_STEP_241 = [
    ["SELL", "FERTILIZER", 16],
    *[["HIRE"] for _ in range(6)],
    ["BUY_SEED", "MELON", 7], ["HIRE"],
]
PUBLIC_FEATURES = (
    "step", "player", "market.prices.FERTILIZER",
    "market.inventory.FERTILIZER",
)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    return getter(key, default) if callable(getter) else getattr(value, key, default)


@dataclass(frozen=True)
class BoatleeSelectorSpec:
    name: str = "fertilizer_surplus_v1"
    decision_step: int = 240
    intervention_step: int = 241
    max_fertilizer_price: int = 84
    min_fertilizer_inventory: int = 10082

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "lane": "boatlee_v16_rc2_market_relay",
            "name": self.name,
            "role": "e2_s2_remediation_public_selector",
            "decision_step": self.decision_step,
            "intervention_step": self.intervention_step,
            "intervention_market": INTERVENTION_STEP_241,
            "rejoin_step": 242,
            "thresholds": {
                "max_fertilizer_price": self.max_fertilizer_price,
                "min_fertilizer_inventory": self.min_fertilizer_inventory,
            },
            "features": list(PUBLIC_FEATURES),
            "fallback": "boatlee_incumbent",
            "preconditions": {
                "decision_market": CONTROL_STEP_240,
                "intervention_market": CONTROL_STEP_241,
            },
            "lineage": {
                "s2_candidate": "ac_3aa759d7d7fc4a409c409326",
                "step_240_only_ablation": "ac_501500daa79fcb8068244d0e",
                "step_241_only_ablation": "ac_a85701baf0cd39d61ab067d3",
                "source_decision": "E2_S2_REMEDIATION_REQUIRED",
            },
            "diagnostic_basis": {
                "consumed_contexts": 48,
                "selected_positive": 36,
                "selected_zero": 0,
                "selected_negative": 0,
                "abstained": 12,
                "efficacy_claim": None,
            },
            "opponent_identity_used": False,
            "private_opponent_information_used": False,
            "efficacy_claim": None,
        }

    @property
    def candidate_id(self) -> str:
        return "e2boatlee_" + payload_hash(self.payload())[:24]


SELECTORS = (BoatleeSelectorSpec(),)


def _public_ready(obs: Any) -> tuple[bool, str]:
    if _get(obs, "player", None) not in (0, 1):
        return False, "missing_public_player"
    market = _get(obs, "market", None)
    if not isinstance(market, dict):
        return False, "missing_public_market"
    prices = _get(market, "prices", None)
    inventory = _get(market, "inventory", None)
    if not isinstance(prices, dict) or "FERTILIZER" not in prices:
        return False, "missing_public_fertilizer_price"
    if not isinstance(inventory, dict) or "FERTILIZER" not in inventory:
        return False, "missing_public_fertilizer_inventory"
    return True, "public_features_complete"


def decision(spec: BoatleeSelectorSpec, obs: Any, base_action: Any) -> tuple[str, str]:
    if int(_get(obs, "step", -1)) != spec.decision_step:
        return "incumbent", "outside_decision_step"
    ready, reason = _public_ready(obs)
    if not ready:
        return "incumbent", reason
    market_orders = base_action.get("market") if isinstance(base_action, dict) else None
    if market_orders != CONTROL_STEP_240:
        return "incumbent", "decision_precondition_absent"
    market = _get(obs, "market", {})
    price = int(market["prices"]["FERTILIZER"])
    inventory = int(market["inventory"]["FERTILIZER"])
    if price <= spec.max_fertilizer_price and inventory >= spec.min_fertilizer_inventory:
        return "intervene", "public_fertilizer_surplus"
    return "incumbent", "public_fertilizer_not_surplus"


def _project(obs: Any, action: Any) -> dict[str, Any]:
    player = 1 if int(_get(obs, "player", 0) or 0) == 1 else 0
    farms = _get(obs, "farms", []) or []
    farm = farms[player] if player < len(farms) and isinstance(farms[player], dict) else {}
    expected = len(_get(farm, "hands", []) or [])
    action = action if isinstance(action, dict) else {}
    hands = [list(row or ["PASS"]) for row in (action.get("hands") or [])]
    if len(hands) < expected:
        hands.extend([["PASS"] for _ in range(expected - len(hands))])
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": hands[:expected],
        "market": [list(row) for row in (action.get("market") or [])[:10] if isinstance(row, list)],
    }


def apply_selector(
    spec: BoatleeSelectorSpec,
    obs: Any,
    base_action: Any,
    state: dict[str, Any],
) -> dict[str, Any]:
    step = int(_get(obs, "step", -1))
    last = int(state.get("last_step", -1))
    if step == 0 or step < last:
        state.clear()
        state.update({"last_step": -1, "branch": "incumbent"})
    action = _project(obs, base_action)
    if step == spec.decision_step:
        branch, reason = decision(spec, obs, action)
        state["branch"] = branch
        state["reason"] = reason
    elif step == spec.intervention_step and state.get("branch") == "intervene":
        ready, reason = _public_ready(obs)
        if ready and action["market"] == CONTROL_STEP_241:
            action["market"] = [list(row) for row in INTERVENTION_STEP_241]
            state["reason"] = "applied_public_fertilizer_surplus"
        else:
            state["branch"] = "incumbent"
            state["reason"] = reason if not ready else "intervention_precondition_absent"
    state["last_step"] = step
    return {"action": _project(obs, action), "branch": state.get("branch", "incumbent"), "reason": state.get("reason", "uninitialized")}


def make_policy(
    spec: BoatleeSelectorSpec,
    base_agent: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    states = {0: {"last_step": -1, "branch": "incumbent"}, 1: {"last_step": -1, "branch": "incumbent"}}

    def policy(obs: Any, configuration: Any = None) -> dict[str, Any]:
        del configuration
        base = base_agent(obs)
        seat = 1 if int(_get(obs, "player", 0) or 0) == 1 else 0
        return apply_selector(spec, obs, base, states[seat])["action"]

    policy.metadata = {"selector": spec.payload(), "candidate_id": spec.candidate_id}
    return policy


SELECTOR_RUNTIME = r'''
_E2B_BASE_AGENT = agent
_E2B_STATE = {0: {"last_step": -1, "branch": "incumbent"}, 1: {"last_step": -1, "branch": "incumbent"}}
def _e2b_ready(obs):
    if _get(obs, "player", None) not in (0, 1): return False
    market = _get(obs, "market", None)
    if not isinstance(market, dict): return False
    prices = _get(market, "prices", None); inventory = _get(market, "inventory", None)
    return isinstance(prices, dict) and "FERTILIZER" in prices and isinstance(inventory, dict) and "FERTILIZER" in inventory
def _e2b_project(obs, action):
    seat = 1 if int(_get(obs, "player", 0) or 0) == 1 else 0; farms = _get(obs, "farms", []) or []
    farm = farms[seat] if seat < len(farms) and isinstance(farms[seat], dict) else {}; expected = len(_get(farm, "hands", []) or [])
    action = action if isinstance(action, dict) else {}; hands = [list(row or ["PASS"]) for row in (action.get("hands") or [])]
    if len(hands) < expected: hands.extend([["PASS"] for _ in range(expected-len(hands))])
    return {"farmer": list(action.get("farmer") or ["PASS"]), "hands": hands[:expected], "market": [list(row) for row in (action.get("market") or [])[:10] if isinstance(row, list)]}
def agent(obs, configuration=None):
    del configuration
    base = _e2b_project(obs, _E2B_BASE_AGENT(obs)); step = int(_get(obs, "step", -1)); seat = 1 if int(_get(obs, "player", 0) or 0) == 1 else 0; state = _E2B_STATE[seat]
    if step == 0 or step < int(state.get("last_step", -1)): state.clear(); state.update({"last_step": -1, "branch": "incumbent"})
    if step == int(_E2B_SELECTOR["decision_step"]):
        state["branch"] = "incumbent"
        if _e2b_ready(obs) and base["market"] == _E2B_SELECTOR["preconditions"]["decision_market"]:
            market = _get(obs, "market", {}); thresholds = _E2B_SELECTOR["thresholds"]
            if int(market["prices"]["FERTILIZER"]) <= int(thresholds["max_fertilizer_price"]) and int(market["inventory"]["FERTILIZER"]) >= int(thresholds["min_fertilizer_inventory"]): state["branch"] = "intervene"
    elif step == int(_E2B_SELECTOR["intervention_step"]) and state.get("branch") == "intervene":
        if _e2b_ready(obs) and base["market"] == _E2B_SELECTOR["preconditions"]["intervention_market"]: base["market"] = [list(row) for row in _E2B_SELECTOR["intervention_market"]]
        else: state["branch"] = "incumbent"
    state["last_step"] = step
    return _e2b_project(obs, base)
'''


def render_selector(base_source: str, spec: BoatleeSelectorSpec) -> str:
    encoded = json.dumps(spec.payload() | {"candidate_id": spec.candidate_id}, sort_keys=True, separators=(",", ":"))
    return base_source.rstrip() + "\n_E2B_SELECTOR = json.loads(" + repr(encoded) + ")\n" + SELECTOR_RUNTIME.strip() + "\n"


def write_selector(base_source: str, spec: BoatleeSelectorSpec, output: Path) -> dict[str, Any]:
    content = render_selector(base_source, spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    raw = output.read_bytes()
    return {
        "candidate_id": spec.candidate_id,
        "path": str(output), "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
