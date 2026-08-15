"""Delayed public-market selector for the v27 E2 remediation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from authority import payload_hash


PUBLIC_FEATURES = (
    "step", "player", "farms[*].money", "farms[*].hands",
    "farms[*].unlocked_quadrants", "market.prices.WHEAT",
    "market.inventory.WHEAT", "town.unlocked_shops",
)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    getter = getattr(value, "get", None)
    return getter(key, default) if callable(getter) else getattr(value, key, default)


@dataclass(frozen=True)
class SelectorSpec:
    name: str = "delayed_wheat_scarcity_v1"
    decision_step: int = 494
    min_wheat_price: int = 47
    max_wheat_inventory: int = 9500

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "lane": "v27_current_meta",
            "name": self.name,
            "role": "frozen_e2_s1_fresh_label_selector",
            "decision_step": self.decision_step,
            "intervention": {"remove_exact_order": ["BUY_PRODUCT", "WHEAT", 2], "rejoin_step": 495},
            "thresholds": {"min_wheat_price": self.min_wheat_price, "max_wheat_inventory": self.max_wheat_inventory},
            "features": list(PUBLIC_FEATURES),
            "fallback": "v27_incumbent",
            "lineage": {
                "diagnostic_probe": "ac_46448f767f398cc4ce8047d3",
                "delayed_component_e1c": "ac_01234c1e2e934d5e26ea1d36",
                "amendment": "user_authorized_delayed_public_intervention",
            },
            "efficacy_claim": None,
        }

    @property
    def candidate_id(self) -> str:
        return "e2v27_" + payload_hash(self.payload())[:24]


SELECTORS = (SelectorSpec(),)


def _public_ready(obs: Any) -> tuple[bool, str]:
    player = _get(obs, "player", None)
    farms = _get(obs, "farms", None)
    market = _get(obs, "market", None)
    town = _get(obs, "town", None)
    if player not in (0, 1) or not isinstance(farms, list) or len(farms) < 2:
        return False, "missing_public_farms"
    if not all(isinstance(farm, dict) for farm in farms[:2]):
        return False, "malformed_public_farms"
    for farm in farms[:2]:
        if _get(farm, "money", None) is None or not isinstance(_get(farm, "hands", None), list) or not isinstance(_get(farm, "unlocked_quadrants", None), list):
            return False, "missing_public_farm_feature"
    if not isinstance(market, dict) or not isinstance(_get(market, "prices", None), dict) or not isinstance(_get(market, "inventory", None), dict):
        return False, "missing_public_market"
    if "WHEAT" not in market["prices"] or "WHEAT" not in market["inventory"]:
        return False, "missing_public_wheat_feature"
    if not isinstance(town, dict) or not isinstance(_get(town, "unlocked_shops", None), list):
        return False, "missing_public_town"
    return True, "public_features_complete"


def decision(spec: SelectorSpec, obs: Any, base_action: Any) -> tuple[str, str]:
    if _get(obs, "step", None) != spec.decision_step:
        return "incumbent", "outside_intervention_step"
    ready, reason = _public_ready(obs)
    if not ready:
        return "incumbent", reason
    market_orders = base_action.get("market") if isinstance(base_action, dict) else None
    if not isinstance(market_orders, list) or ["BUY_PRODUCT", "WHEAT", 2] not in market_orders:
        return "incumbent", "probe_precondition_absent"
    market = _get(obs, "market", {})
    price = int(market["prices"]["WHEAT"])
    inventory = int(market["inventory"]["WHEAT"])
    if price >= spec.min_wheat_price and inventory <= spec.max_wheat_inventory:
        return "suppress_buy", "public_wheat_scarcity"
    return "incumbent", "public_wheat_not_scarce"


def _project(obs: Any, action: Any) -> dict[str, Any]:
    seat = 1 if int(_get(obs, "player", 0) or 0) == 1 else 0
    farms = _get(obs, "farms", []) or []
    farm = farms[seat] if seat < len(farms) and isinstance(farms[seat], dict) else {}
    expected_hands = len(_get(farm, "hands", []) or [])
    action = action if isinstance(action, dict) else {}
    hands = [list(row or ["PASS"]) for row in (action.get("hands") or [])]
    if len(hands) < expected_hands:
        hands.extend([["PASS"] for _ in range(expected_hands - len(hands))])
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": hands[:expected_hands],
        "market": [list(row) for row in (action.get("market") or [])[:10] if isinstance(row, list)],
    }


def apply_selector(spec: SelectorSpec, obs: Any, base_action: Any) -> dict[str, Any]:
    branch, reason = decision(spec, obs, base_action)
    if branch != "suppress_buy":
        return {"action": _project(obs, base_action), "branch": branch, "reason": reason}
    action = _project(obs, base_action)
    removed = False
    retained = []
    for order in action["market"]:
        if not removed and order == ["BUY_PRODUCT", "WHEAT", 2]:
            removed = True
            continue
        retained.append(order)
    action["market"] = retained
    return {"action": _project(obs, action), "branch": branch, "reason": reason}


def make_policy(spec: SelectorSpec, base_agent: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def policy(obs: Any, configuration: Any = None) -> dict[str, Any]:
        base = base_agent(obs, configuration)
        return apply_selector(spec, obs, base)["action"]

    policy.metadata = {"selector": spec.payload(), "candidate_id": spec.candidate_id}
    return policy


def development_hypothesis() -> dict[str, Any]:
    spec = SELECTORS[0]
    return {
        "pass": True,
        "candidate_id": spec.candidate_id,
        "frozen_selector_versions": [spec.payload() | {"candidate_id": spec.candidate_id}],
        "technical_feature_basis": {
            "seed": 811407,
            "correctness_only": True,
            "observed_wheat_price_range": [45, 49],
            "observed_wheat_inventory_range": [9435, 9583],
            "thresholds_exercise_both_branches": True,
        },
        "frozen_e1c_causal_ablation": {
            "step0_only_mean_paired_margin": 11161.625,
            "step0_only_worst_paired_margin": -6206.0,
            "step494_only_mean_paired_margin": 0.0,
            "step494_only_worst_paired_margin": -2.0,
            "interpretation": "delayed intervention has no retained efficacy claim; E2 S1 is needed only to acquire fresh public-selector labels",
        },
        "opponent_identity_used": False,
        "private_opponent_information_used": False,
        "technical_rewards_used_for_efficacy": False,
    }


SELECTOR_RUNTIME = r'''
_E2_BASE_AGENT = agent
def _e2_ready(obs):
    player = _get(obs, "player", None); farms = _get(obs, "farms", None); market = _get(obs, "market", None); town = _get(obs, "town", None)
    if player not in (0, 1) or not isinstance(farms, list) or len(farms) < 2 or not all(isinstance(farm, dict) for farm in farms[:2]): return False
    for farm in farms[:2]:
        if _get(farm, "money", None) is None or not isinstance(_get(farm, "hands", None), list) or not isinstance(_get(farm, "unlocked_quadrants", None), list): return False
    if not isinstance(market, dict) or not isinstance(_get(market, "prices", None), dict) or not isinstance(_get(market, "inventory", None), dict): return False
    if "WHEAT" not in market["prices"] or "WHEAT" not in market["inventory"]: return False
    return isinstance(town, dict) and isinstance(_get(town, "unlocked_shops", None), list)
def _e2_project(obs, action):
    seat = 1 if int(_get(obs, "player", 0) or 0) == 1 else 0; farms = _get(obs, "farms", []) or []
    farm = farms[seat] if seat < len(farms) and isinstance(farms[seat], dict) else {}; expected = len(_get(farm, "hands", []) or [])
    action = action if isinstance(action, dict) else {}; hands = [list(row or ["PASS"]) for row in (action.get("hands") or [])]
    if len(hands) < expected: hands.extend([["PASS"] for _ in range(expected-len(hands))])
    return {"farmer": list(action.get("farmer") or ["PASS"]), "hands": hands[:expected], "market": [list(row) for row in (action.get("market") or [])[:10] if isinstance(row, list)]}
def agent(obs, configuration=None):
    base = _E2_BASE_AGENT(obs, configuration); action = _e2_project(obs, base)
    if int(_get(obs, "step", -1)) != int(_E2_SELECTOR["decision_step"]) or not _e2_ready(obs): return _e2_project(obs, action)
    target = ["BUY_PRODUCT", "WHEAT", 2]
    if target not in action["market"]: return _e2_project(obs, action)
    market = _get(obs, "market", {}); thresholds = _E2_SELECTOR["thresholds"]
    if int(market["prices"]["WHEAT"]) < int(thresholds["min_wheat_price"]) or int(market["inventory"]["WHEAT"]) > int(thresholds["max_wheat_inventory"]): return _e2_project(obs, action)
    removed = False; retained = []
    for order in action["market"]:
        if not removed and order == target: removed = True; continue
        retained.append(order)
    action["market"] = retained
    return _e2_project(obs, action)
'''


def render_selector(base_source: str, spec: SelectorSpec) -> str:
    encoded = json.dumps(spec.payload() | {"candidate_id": spec.candidate_id}, sort_keys=True, separators=(",", ":"))
    return base_source.rstrip() + "\n_E2_SELECTOR = json.loads(" + repr(encoded) + ")\n" + SELECTOR_RUNTIME.strip() + "\n"


def write_selector(base_source: str, spec: SelectorSpec, output: Path) -> dict[str, Any]:
    content = render_selector(base_source, spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    raw = output.read_bytes()
    return {"candidate_id": spec.candidate_id, "path": str(output), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
