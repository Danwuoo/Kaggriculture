"""Action legality, resource consistency, and final safety projection."""

from constants import ANIMALS, CROPS, FARM_OPS, LAND_PRICES, MARKET_OPS, MOVES, PRODUCTS
from market import hire_cost, market_price


def plant_will_die(tile):
    return isinstance(tile, dict) and tile.get("kind") == "PLANT" and not tile.get("watered_today") and tile.get("consecutive_unwatered", 0) >= 1


def animal_will_escape(tile):
    return isinstance(tile, dict) and tile.get("animal") in ANIMALS and not tile.get("fed_today") and tile.get("consecutive_unfed", 0) >= 1


def is_action_schema(action, hand_count=None):
    if not isinstance(action, dict) or set(action) != {"farmer", "hands", "market"}:
        return False
    if not isinstance(action["farmer"], list) or not action["farmer"]:
        return False
    if not isinstance(action["hands"], list) or not isinstance(action["market"], list) or len(action["market"]) > 10:
        return False
    if hand_count is not None and len(action["hands"]) != hand_count:
        return False
    return all(isinstance(x, list) and x for x in action["hands"] + action["market"])


def _unit_action(state, idx, action, shed, seeds, inventories):
    if not isinstance(action, list) or not action or action[0] not in FARM_OPS:
        return ["PASS"]
    op = action[0]
    pos = state.positions[idx]
    x, y = pos
    tile = state.tile(pos)
    inv = inventories[idx]
    if op in MOVES:
        dx, dy = MOVES[op]
        return action if 0 <= x + dx < state.size and 0 <= y + dy < state.size else ["PASS"]
    if op == "PASS":
        return ["PASS"]
    if tile == "LOCKED":
        return ["PASS"]
    if op == "DROP":
        if not state.at_shed(pos) or not sum(inv.values()):
            return ["PASS"]
        for item, count in list(inv.items()):
            room = max(0, 100 - sum(shed.values()))
            shed[item] = shed.get(item, 0) + min(count, room)
            inv[item] = 0
        return ["DROP"]
    if op == "PICKUP":
        if not state.at_shed(pos) or len(action) < 2:
            return ["PASS"]
        item = action[1]
        if item not in shed:
            return ["PASS"]
        try:
            count = int(action[2]) if len(action) > 2 else 1
        except (TypeError, ValueError):
            return ["PASS"]
        count = min(max(0, count), shed.get(item, 0))
        if count <= 0:
            return ["PASS"]
        shed[item] -= count
        inv[item] = inv.get(item, 0) + count
        return ["PICKUP", item, count]
    if op == "PLANT":
        if len(action) < 2 or action[1] not in CROPS or tile is not None or seeds.get(action[1], 0) <= 0:
            return ["PASS"]
        seeds[action[1]] -= 1
        return ["PLANT", action[1]]
    if op == "WATER":
        return ["WATER"] if isinstance(tile, dict) and tile.get("kind") == "PLANT" and not tile.get("watered_today") else ["PASS"]
    if op == "HARVEST":
        if not isinstance(tile, dict) or tile.get("yield_units", 0) <= 0:
            return ["PASS"]
        if tile.get("kind") == "PLANT" and state.day - tile.get("planted_day", state.day) < CROPS[tile["crop"]]["first"]:
            return ["PASS"]
        return ["HARVEST"]
    if op == "FERTILIZE":
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT" and inv.get("FERTILIZER", 0) > 0):
            return ["PASS"]
        inv["FERTILIZER"] -= 1
        return ["FERTILIZE"]
    if op == "DIG":
        return ["DIG"] if tile is not None and not (isinstance(tile, dict) and tile.get("animal")) else ["PASS"]
    if op in ("BUILD_COOP", "BUILD_PASTURE"):
        return [op] if tile is None else ["PASS"]
    if op == "PLACE":
        if len(action) < 2:
            return ["PASS"]
        item = action[1]
        if item in ANIMALS and isinstance(tile, dict) and tile.get("kind") == ANIMALS[item]["structure"] and not tile.get("animal") and inv.get(item, 0) > 0:
            inv[item] -= 1
            return ["PLACE", item]
        if state.at_shed(pos) and item in inv:
            try:
                count = int(action[2]) if len(action) > 2 else 1
            except (TypeError, ValueError):
                return ["PASS"]
            count = min(max(0, count), inv[item], max(0, 100 - sum(shed.values())))
            if count:
                inv[item] -= count
                shed[item] += count
                return ["PLACE", item, count]
        return ["PASS"]
    if op == "FEED":
        if not (isinstance(tile, dict) and tile.get("animal") and not tile.get("fed_today") and inv.get("WHEAT", 0) > 0):
            return ["PASS"]
        inv["WHEAT"] -= 1
        return ["FEED"]
    if op == "COLLECT_FERTILIZER":
        return [op] if isinstance(tile, dict) and tile.get("animal") and tile.get("fertilizer_available") else ["PASS"]
    if op == "CARE":
        return ["CARE"] if isinstance(tile, dict) and tile.get("animal") and not tile.get("cared_today") else ["PASS"]
    return ["PASS"]


def validate_and_project(state, action):
    """Return engine-legal actions and the post-unit-action shed projection."""
    source = action if isinstance(action, dict) else {}
    raw_units = [source.get("farmer", ["PASS"])] + list(source.get("hands", []) if isinstance(source.get("hands", []), list) else [])
    while len(raw_units) < len(state.positions):
        raw_units.append(["PASS"])
    shed, seeds = dict(state.shed), dict(state.seeds)
    inventories = [dict(inv) for inv in state.inventories]
    units = [_unit_action(state, idx, raw_units[idx], shed, seeds, inventories) for idx in range(len(state.positions))]

    raw_market = source.get("market", []) if isinstance(source.get("market", []), list) else []
    market = []
    money = float(state.me["money"])
    market_inv = dict(state.market_inventory)
    hires = state.me["hires_today"]
    unlocked = len(state.me["unlocked_quadrants"])
    for order in raw_market[:10]:
        if not isinstance(order, list) or not order or order[0] not in MARKET_OPS:
            continue
        op = order[0]
        if op == "SELL":
            if len(order) < 3 or order[1] not in PRODUCTS:
                continue
            try:
                quantity = min(max(0, int(order[2])), shed.get(order[1], 0))
            except (TypeError, ValueError):
                continue
            if quantity <= 0:
                continue
            item = order[1]
            sold = 0
            for _ in range(quantity):
                price = market_price(item, market_inv[item], state.market_params)
                money += price
                shed[item] -= 1
                sold += 1
                if price > 1:
                    market_inv[item] += 1
            market.append(["SELL", item, sold])
        elif op in ("BUY_SEED", "BUY_ANIMAL", "BUY_PRODUCT"):
            if len(order) < 3:
                continue
            item = order[1]
            valid = (op == "BUY_SEED" and item in CROPS) or (op == "BUY_ANIMAL" and item in ANIMALS) or (op == "BUY_PRODUCT" and item in ("WHEAT", "FERTILIZER"))
            if not valid:
                continue
            try:
                requested = max(0, int(order[2]))
            except (TypeError, ValueError):
                continue
            bought = 0
            for _ in range(requested):
                if op == "BUY_SEED":
                    price = CROPS[item]["seed"]
                elif op == "BUY_ANIMAL":
                    price = ANIMALS[item]["cost"]
                else:
                    price = market_price(item, market_inv[item] - 1, state.market_params)
                if money < price or (op != "BUY_SEED" and sum(shed.values()) >= 100):
                    break
                money -= price
                bought += 1
                if op == "BUY_SEED":
                    seeds[item] += 1
                else:
                    shed[item] += 1
                    if op == "BUY_PRODUCT":
                        market_inv[item] -= 1
            if bought:
                market.append([op, item, bought])
        elif op == "HIRE":
            cost = hire_cost(hires)
            if money >= cost:
                money -= cost
                hires += 1
                market.append(["HIRE"])
        elif op == "BUY_LAND" and unlocked - 1 < len(LAND_PRICES):
            cost = LAND_PRICES[unlocked - 1]
            if money >= cost:
                money -= cost
                unlocked += 1
                market.append(["BUY_LAND"])
        if len(market) >= 10:
            break
    result = {"farmer": units[0], "hands": units[1:], "market": market}
    return result, shed

