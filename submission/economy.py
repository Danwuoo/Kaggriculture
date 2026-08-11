"""Marginal return and terminal-feasibility calculations."""

from constants import ANIMALS, CROPS
from market import market_price, projected_sale


def can_finish_crop(state, crop, pos=None):
    data = CROPS[crop]
    grow = data["max_day"] * 24
    logistics = 3
    if pos is not None:
        logistics += min(abs(pos[0] - x) + abs(pos[1] - y) for x, y in state.shed_access)
    return state.step + grow + logistics <= 718


def animal_marginal_value(state, animal):
    data = ANIMALS[animal]
    remaining_days = max(0, (718 - state.step) // 24 - data["first"])
    productions = max(0, remaining_days // data["interval"] + (1 if remaining_days >= 0 else 0))
    price = state.market_prices.get(data["product"], 0)
    feed = max(0, remaining_days) * state.market_prices.get("WHEAT", 25)
    fertilizer = max(0, remaining_days) * state.market_prices.get("FERTILIZER", 100) * .45
    return productions * price * 1.7 + fertilizer - data["cost"] - feed


def land_marginal_value(state, quadrant, crop="STRAWBERRY"):
    costs = {"NE": 1000, "SW": 2000, "SE": 4000}
    remaining_days = max(0, (718 - state.step) / 24.0)
    cycles = max(0.0, (remaining_days - CROPS[crop]["max_day"]) / 17.0 + 1.0)
    unit_price = state.market_prices.get(crop, 0)
    gross = min(12, max(4, len(state.positions))) * 4 * unit_price * cycles
    commute = 22 * max(1, len(state.positions) - 1)
    labor = 18 * min(25, max(0, state.crop_count(crop) + 4))
    return gross - costs.get(quadrant, 4000) - commute - labor


def fertilizer_incremental_value(state, tile):
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return -10 ** 9
    crop = tile["crop"]
    increments = {"WHEAT": 2, "CARROT": 1, "TOMATO": 3, "STRAWBERRY": 2, "MELON": 0}
    extra = increments[crop]
    product_inv = state.market_inventory[crop]
    product_value, _ = projected_sale(crop, extra, product_inv, state.market_params)
    fertilizer_value, _ = projected_sale("FERTILIZER", 1, state.market_inventory["FERTILIZER"], state.market_params)
    land_release = 0
    if crop == "MELON":
        age = state.day - tile.get("planted_day", state.day)
        land_release = max(0, 2 - max(0, age - 6)) * 18
    # Re-fertilizing an already-covered crop rarely beats selling the unit.
    overlap_penalty = 55 if tile.get("fertilized_until_day", -1) >= state.day + 1 else 0
    logistics = 24
    return product_value + land_release - fertilizer_value - logistics - overlap_penalty


def crop_economic_value(state, crop):
    data = CROPS[crop]
    units = 4 if crop not in ("CARROT", "MELON") else (3 if crop == "CARROT" else 6)
    revenue, _ = projected_sale(crop, units, state.market_inventory[crop], state.market_params)
    return revenue - data["seed"]

