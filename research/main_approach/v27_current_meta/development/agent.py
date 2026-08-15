"""v27 development entrypoint."""

from .market import _rank_sell_slots
from .route import _LEGACY_ACTIONS, _MULTI_SELL_STEPS, _REBALANCE_ACTIONS, _ROUTE_HAND_COUNTS, _WEED_CANDIDATE_STEPS
from .runtime import _copy_action, _get, _project_action, _project_atomic_plants, _runtime_context
from .weed_repair import _WEED_STATE, _weed_needs_repair, _weed_repair_action, _weed_reset

def agent(obs, configuration=None):
    try:
        actions = _REBALANCE_ACTIONS
        step, seat, farm, expected_hands, reset = _runtime_context(obs, len(actions) - 1)
        game = _weed_reset(seat) if reset else _WEED_STATE[seat]
        template = actions[step]
        aligned = _ROUTE_HAND_COUNTS[step] == expected_hands
        weed = _weed_needs_repair(farm, template, game, step in _WEED_CANDIDATE_STEPS)
        if (
            aligned
            and not weed
            and step not in _MULTI_SELL_STEPS
        ):
            return _project_atomic_plants(obs, template)
        action = _copy_action(template)
        if weed:
            _weed_repair_action(action, actions, step, farm, game)
        if step in _MULTI_SELL_STEPS:
            _rank_sell_slots(obs, action, configuration)
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


def _kaggle_submission_entrypoint(obs, configuration=None):
    return agent(obs, configuration)
