"""Exact engine price curve plus adaptive, ordered market control."""

import math

from constants import ANIMALS, CROPS, LAND_PRICES, PRODUCTS, SHOPS
from parameters import (
    FEED_DAYS_IN_SHED,
    MAX_MARKET_ORDERS,
    MIN_CASH_RESERVE,
    NORMAL_BATCH,
    RESERVE_FRACTIONS,
    SHED_HARD_LIMIT,
    SHED_SOFT_LIMIT,
)


def _shape(name, x):
    x = max(0.0, float(x))
    if name == "linear":
        return x
    if name == "sq":
        return x * x
    if name == "sqrt":
        return math.sqrt(x)
    if name == "log":
        return math.log(1.0 + x)
    if name == "log10":
        return math.log10(1.0 + x)
    return x


def market_price(item, inventory, params):
    """Bit-for-bit equivalent to the engine for normal numeric parameters."""
    p = params[item]
    base, i0, throughput = p["base"], p["I0"], p["T"]
    if inventory < i0:
        func = p["below_func"]
        amp = p["below_target"] * base / _shape(func, throughput)
        value = base + amp * _shape(func, i0 - inventory)
    else:
        func = p["above_func"]
        amp = p["above_target"] * base / _shape(func, throughput)
        value = base - amp * _shape(func, inventory - i0)
    return max(1, int(round(value)))


def projected_sale(item, quantity, inventory, params):
    revenue = 0
    inv = int(inventory)
    for _ in range(max(0, int(quantity))):
        price = market_price(item, inv, params)
        revenue += price
        if price > 1:
            inv += 1
    return revenue, inv


def projected_buy(item, quantity, inventory, params):
    cost = 0
    inv = int(inventory)
    bought = 0
    for _ in range(max(0, int(quantity))):
        price = market_price(item, inv - 1, params)
        cost += price
        inv -= 1
        bought += 1
    return cost, inv, bought


def hire_cost(n):
    a, b = 1, 1
    for _ in range(max(0, int(n))):
        a, b = b, a + b
    return a


def demand_rate(item, shops):
    """Expected public inventory drain per turn from currently unlocked shops."""
    rate = 1.0 / 12.0
    for shop in shops:
        products = SHOPS.get(shop, ())
        if item in products:
            rate += (2.0 if len(products) == 1 else 1.0) / 4.0
    return rate


class MarketController:
    def plan(self, state, macro, forecast, projected_shed, fertilizer_reserve=0):
        orders = []
        shed = dict(projected_shed)
        inv = dict(state.market_inventory)
        money = float(state.me["money"])
        load = sum(shed.values())
        herd = sum(state.animal_count(a) for a in ANIMALS)
        feed_reserve = 0 if state.step >= 696 else herd * FEED_DAYS_IN_SHED

        candidates = []
        exposure = forecast.get("exposure", {}) if isinstance(forecast, dict) else {}
        for item in PRODUCTS:
            quantity = shed.get(item, 0)
            keep = feed_reserve if item == "WHEAT" else (fertilizer_reserve if item == "FERTILIZER" else 0)
            available = max(0, quantity - keep)
            if available <= 0:
                continue
            current = market_price(item, inv[item], state.market_params)
            base = state.market_params[item]["base"]
            pressure = load >= SHED_SOFT_LIMIT or state.step >= 696
            imminent = exposure.get(item, 0) > 0
            if not pressure and not imminent and current < base * RESERVE_FRACTIONS[item]:
                recovery_units = demand_rate(item, state.unlocked_shops) * min(24, max(0, 718 - state.step))
                recovered = market_price(item, inv[item] - recovery_units, state.market_params)
                if recovered >= current:
                    continue
            batch = available if state.step >= 712 or load >= SHED_HARD_LIMIT else min(available, NORMAL_BATCH[item])
            if imminent:
                batch = min(available, max(batch, min(available, int(exposure[item]) + 1)))
            # Premium/glut-sensitive goods and exposed cohorts go first.
            sensitivity = float(state.market_params[item]["above_target"])
            priority = (2.5 if imminent else 0.0) + (2.0 if pressure else 0.0) + sensitivity + current / max(1.0, base)
            candidates.append((-priority, item, batch))

        for _, item, quantity in sorted(candidates):
            if len(orders) >= MAX_MARKET_ORDERS:
                break
            quantity = min(quantity, shed[item])
            if quantity <= 0:
                continue
            orders.append(["SELL", item, quantity])
            revenue, inv[item] = projected_sale(item, quantity, inv[item], state.market_params)
            money += revenue
            shed[item] -= quantity
            load -= quantity

        # Daily labor is cheap early in the Fibonacci curve and is the main
        # protection against feed/water deadline failures.
        target_hands = int(macro.get("hands", 0))
        hires = int(state.me["hires_today"])
        if state.hour <= 2:
            while hires < target_hands and len(orders) < MAX_MARKET_ORDERS:
                cost = hire_cost(hires)
                if money - cost < min(80, MIN_CASH_RESERVE // 2):
                    break
                orders.append(["HIRE"])
                money -= cost
                hires += 1

        # Animals are bought only while their first production and logistics
        # can finish. Aggregate orders still execute unit-by-unit in-engine.
        for animal in ("COW", "SHEEP", "GOOSE"):
            if len(orders) >= MAX_MARKET_ORDERS:
                break
            wanted = int(macro.get({"COW": "cows", "SHEEP": "sheep", "GOOSE": "geese"}[animal], 0))
            missing = max(0, wanted - state.animal_count(animal))
            latest = 718 - (ANIMALS[animal]["first"] * 24 + 18)
            affordable = int(max(0, money - MIN_CASH_RESERVE) // ANIMALS[animal]["cost"])
            room = max(0, 100 - load)
            buy = min(missing, affordable, room, 3)
            if state.step <= latest and buy > 0:
                orders.append(["BUY_ANIMAL", animal, buy])
                money -= buy * ANIMALS[animal]["cost"]
                shed[animal] += buy
                load += buy

        # Keep several feed days in physical stock. BUY_PRODUCT lands in the
        # shed and therefore observes capacity.
        if len(orders) < MAX_MARKET_ORDERS and state.step < 696:
            carried_wheat = sum(unit.get("WHEAT", 0) for unit in state.inventories)
            desired = herd * FEED_DAYS_IN_SHED
            need = max(0, desired - shed.get("WHEAT", 0) - carried_wheat)
            room = max(0, 100 - load)
            buy = min(need, room, 36)
            if buy:
                actual = 0
                cost = 0
                shadow_inv = inv["WHEAT"]
                for _ in range(buy):
                    unit_cost = market_price("WHEAT", shadow_inv - 1, state.market_params)
                    if money - cost - unit_cost < MIN_CASH_RESERVE:
                        break
                    cost += unit_cost
                    shadow_inv -= 1
                    actual += 1
                if actual:
                    orders.append(["BUY_PRODUCT", "WHEAT", actual])
                    money -= cost
                    inv["WHEAT"] = shadow_inv
                    shed["WHEAT"] += actual
                    load += actual

        # Seeds do not occupy shed capacity. Desired counts are based on empty
        # target cells and are deliberately bought one turn before use.
        for crop, wanted in macro.get("seed_needs", {}).items():
            if len(orders) >= MAX_MARKET_ORDERS or crop not in CROPS or wanted <= 0:
                continue
            missing = max(0, int(wanted) - state.seeds.get(crop, 0))
            if missing <= 0:
                continue
            cost = CROPS[crop]["seed"]
            buy = min(missing, int(max(0, money - MIN_CASH_RESERVE) // cost), 8)
            if buy:
                orders.append(["BUY_SEED", crop, buy])
                money -= buy * cost

        # Land unlock is deliberately late in the order: sells can finance it,
        # while same-turn land cannot supply already-processed field actions.
        unlocked = len(state.me["unlocked_quadrants"])
        desired_land = int(macro.get("land", unlocked))
        if len(orders) < MAX_MARKET_ORDERS and unlocked < desired_land and unlocked - 1 < len(LAND_PRICES):
            cost = LAND_PRICES[unlocked - 1]
            if money - cost >= max(MIN_CASH_RESERVE, herd * 35):
                orders.append(["BUY_LAND"])

        return orders[:MAX_MARKET_ORDERS]
