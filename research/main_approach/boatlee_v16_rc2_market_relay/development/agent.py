"""Boatlee V16-RC2 development entrypoint."""

from .base_agent import _V16_OFFICIAL_CONFIGURATION, _v16_dynamic_action
from .livestock import _V16_ROUTE_STATE, _v16_reset, _v16_yarn_route
from .relay import _RC2_ROUTE_STATE, _rc2_market_relay, _rc2_needs_relay, _rc2_reset, _rc2_update_state
from .route import _MULTI_SELL_STEPS, _REBALANCE_ACTIONS, _ROUTE_HAND_COUNTS, _WEED_CANDIDATE_STEPS
from .runtime import _get, _project_action, _project_atomic_plants, _runtime_context
from .weed_repair import _WEED_STATE, _weed_needs_repair, _weed_reset
from .wool import _v16_wool_reset

def agent(obs):
    try:
        configuration = _V16_OFFICIAL_CONFIGURATION
        step, seat, farm, expected_hands, reset = _runtime_context(obs, len(_REBALANCE_ACTIONS) - 1)
        if reset:
            weed_game = _weed_reset(seat)
            _v16_reset(seat)
            _v16_wool_reset(seat)
            relay_state = _rc2_reset(seat)
        else:
            weed_game = _WEED_STATE[seat]
            relay_state = _RC2_ROUTE_STATE[seat]
        template = _REBALANCE_ACTIONS[step]
        aligned = _ROUTE_HAND_COUNTS[step] == expected_hands
        yarn = _v16_yarn_route(obs, step, seat)
        relay_state = _rc2_update_state(obs, step, seat)
        relay = _rc2_needs_relay(relay_state, step)
        weed = _weed_needs_repair(farm, template, weed_game, step in _WEED_CANDIDATE_STEPS)
        if (
            aligned
            and not yarn
            and not relay
            and not weed
            and step not in _MULTI_SELL_STEPS
        ):
            return _project_atomic_plants(obs, template)
        action = _v16_dynamic_action(
            obs, configuration, template, _REBALANCE_ACTIONS, step, seat, farm,
            weed_game, weed, yarn,
        )
        if relay:
            _rc2_market_relay(obs, action, step, configuration, relay_state)
        action = _project_atomic_plants(obs, action)
        return _project_action(action, expected_hands)
    except Exception:
        farms = _get(obs, "farms", []) or []
        seat = 1 if int(_get(obs, "player", 0) or 0) == 1 else 0
        farm = farms[seat] if seat < len(farms) else {}
        return {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in (_get(farm, "hands", []) or [])],
            "market": [],
        }
