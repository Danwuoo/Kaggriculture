"""Boatlee V16 route execution before RC2 relay."""

from .livestock import _v16_convert_livestock
from .market import _rank_sell_slots
from .runtime import _copy_action
from .weed_repair import _weed_repair_action
from .wool import _v16_wool_controller


def _v16_dynamic_action(
    obs, configuration, template, actions, step, seat, farm, weed_game, weed, yarn
):
    action = _copy_action(template)
    if weed:
        _weed_repair_action(action, actions, step, farm, weed_game)
    if yarn:
        _v16_convert_livestock(action, step, yarn)
        _v16_wool_controller(action, obs, step, seat, yarn)
    _rank_sell_slots(obs, action, configuration)
    return action


# Current official Kaggriculture defaults used by the audited two-argument route.
_V16_OFFICIAL_CONFIGURATION = {
    'turnsPerDay': 24,
    'townShopSellInterval': 4,
    'townCenterSellInterval': 24,
}
