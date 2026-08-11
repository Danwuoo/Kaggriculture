"""Boatlee V16 route execution before RC2 relay."""

from .livestock import _v16_convert_livestock
from .market import _rank_sell_slots
from .route import _LEGACY_ACTIONS, _REBALANCE_ACTIONS
from .runtime import _align_hands, _copy_action, _farm, _get, _regime, _seat
from .weed_repair import _weed_repair_action
from .wool import _v16_wool_controller

def _v16_agent_impl(obs, configuration=None):
    try:
        actions = (
            _REBALANCE_ACTIONS
            if _regime(configuration) == "rebalance"
            else _LEGACY_ACTIONS
        )
        step = min(max(0, int(_get(obs, "step", 0) or 0)), len(actions) - 1)
        action = _weed_repair_action(
            obs, _copy_action(actions[step]), actions, step
        )
        action = _v16_convert_livestock(action, obs, step)
        action = _v16_wool_controller(action, obs, step)
        return _align_hands(_rank_sell_slots(obs, action, configuration), obs)
    except Exception:
        farm = _farm(obs, _seat(obs))
        return {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in (_get(farm, "hands", []) or [])],
            "market": [],
        }


# Current official Kaggriculture defaults used by the audited two-argument route.
_V16_OFFICIAL_CONFIGURATION = {
    'turnsPerDay': 24,
    'townShopSellInterval': 4,
    'townCenterSellInterval': 24,
}
