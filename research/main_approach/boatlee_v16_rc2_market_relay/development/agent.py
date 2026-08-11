"""Boatlee V16-RC2 development entrypoint."""

from .base_agent import _V16_OFFICIAL_CONFIGURATION, _v16_agent_impl
from .relay import _rc2_market_relay
from .route import _REBALANCE_ACTIONS
from .runtime import _align_hands, _farm, _get, _seat

def agent(obs):
    try:
        configuration = _V16_OFFICIAL_CONFIGURATION
        step = min(max(0, int(_get(obs, "step", 0) or 0)), len(_REBALANCE_ACTIONS) - 1)
        action = _v16_agent_impl(obs, configuration)
        action = _rc2_market_relay(obs, action, step, configuration)
        return _align_hands(action, obs)
    except Exception:
        farm = _farm(obs, _seat(obs))
        return {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in (_get(farm, "hands", []) or [])],
            "market": [],
        }
