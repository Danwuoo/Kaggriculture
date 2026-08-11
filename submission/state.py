"""Defensive observation normalization and derived state."""

from collections.abc import Mapping

from constants import ALL_SHED_ITEMS, CROPS, MARKET_PARAMS, PRODUCTS, QUADRANTS, shed_tiles


def _get(obj, key, default=None):
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _int(value, default=0, low=None, high=None):
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        value = default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _counts(value, keys):
    src = value if isinstance(value, Mapping) else {}
    return {key: _int(_get(src, key, 0), 0, 0) for key in keys}


def _position(value, size, default=(0, 0)):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return default
    x, y = _int(value[0], default[0]), _int(value[1], default[1])
    if not (0 <= x < size and 0 <= y < size):
        return default
    return (x, y)


def _tile(value, errors, x, y):
    if value is None or value == "LOCKED":
        return value
    if not isinstance(value, Mapping):
        errors.append("invalid tile at %s,%s" % (x, y))
        return "LOCKED"
    kind = _get(value, "kind")
    if kind == "WEED":
        return {"kind": "WEED"}
    if kind == "PLANT" and _get(value, "crop") in CROPS:
        return {
            "kind": "PLANT",
            "crop": _get(value, "crop"),
            "planted_day": _int(_get(value, "planted_day", 0), 0, 0),
            "watered_today": bool(_get(value, "watered_today", False)),
            "consecutive_unwatered": _int(_get(value, "consecutive_unwatered", 0), 0, 0),
            "yield_units": _int(_get(value, "yield_units", 0), 0, 0),
            "max_lifespan_step": _int(_get(value, "max_lifespan_step", -1), -1),
            "fertilized_until_day": _int(_get(value, "fertilized_until_day", -1), -1),
        }
    if kind in ("COOP", "PASTURE"):
        out = {"kind": kind}
        animal = _get(value, "animal", None)
        if animal is not None:
            from constants import ANIMALS
            if animal not in ANIMALS or ANIMALS[animal]["structure"] != kind:
                errors.append("invalid animal tile at %s,%s" % (x, y))
                return "LOCKED"
            out.update({
                "animal": animal,
                "placed_day": _int(_get(value, "placed_day", 0), 0, 0),
                "yield_units": _int(_get(value, "yield_units", 0), 0, 0),
                "fed_today": bool(_get(value, "fed_today", False)),
                "consecutive_unfed": _int(_get(value, "consecutive_unfed", 0), 0, 0),
                "cared_today": bool(_get(value, "cared_today", False)),
                "fertilizer_available": bool(_get(value, "fertilizer_available", False)),
                "pending_care_bonus": _int(_get(value, "pending_care_bonus", 0), 0, 0),
            })
        return out
    errors.append("unknown tile at %s,%s" % (x, y))
    return "LOCKED"


class GameState:
    """Sanitized view; never mutates the framework observation."""

    def __init__(self, obs):
        self.errors = []
        raw_farms = _get(obs, "farms", [])
        raw_farms = raw_farms if isinstance(raw_farms, (list, tuple)) else []
        guessed_size = 10
        if raw_farms:
            rows = _get(raw_farms[0], "tiles", [])
            if isinstance(rows, (list, tuple)) and 4 <= len(rows) <= 32:
                guessed_size = len(rows)
        self.size = guessed_size
        self.player = _int(_get(obs, "player", 0), 0, 0, max(0, len(raw_farms) - 1))
        self.day = _int(_get(obs, "day", 0), 0, 0)
        self.hour = _int(_get(obs, "hour", 0), 0, 0, 23)
        fallback_step = self.day * 24 + self.hour
        self.step = _int(_get(obs, "step", fallback_step), fallback_step, 0)
        self.farms = [self._farm(f) for f in raw_farms[:2]]
        while len(self.farms) < 2:
            self.farms.append(self._farm({}))
        self.me = self.farms[self.player]

        private = _get(obs, "private", {})
        self.shed = _counts(_get(private, "shed", {}), ALL_SHED_ITEMS)
        self.seeds = _counts(_get(private, "seeds", {}), CROPS)
        raw_inv = _get(private, "inventories", [])
        raw_inv = raw_inv if isinstance(raw_inv, (list, tuple)) else []
        n_units = 1 + len(self.me["hands"])
        self.inventories = [_counts(raw_inv[i] if i < len(raw_inv) else {}, ALL_SHED_ITEMS) for i in range(n_units)]

        raw_market = _get(obs, "market", {})
        self.market_inventory = _counts(_get(raw_market, "inventory", {}), PRODUCTS)
        self.market_prices = _counts(_get(raw_market, "prices", {}), PRODUCTS)
        for item in PRODUCTS:
            if self.market_inventory[item] == 0:
                self.market_inventory[item] = MARKET_PARAMS[item]["I0"]
            if self.market_prices[item] == 0:
                self.market_prices[item] = MARKET_PARAMS[item]["base"]
        self.market_params = self._market_params(_get(raw_market, "params", {}))
        town = _get(obs, "town", {})
        shops = _get(town, "unlocked_shops", [])
        self.unlocked_shops = tuple(x for x in shops if isinstance(x, str)) if isinstance(shops, (list, tuple)) else ()
        self.shed_load = sum(self.shed.values())
        self.positions = (self.me["farmer"],) + tuple(self.me["hands"])
        self.shed_access = shed_tiles(self.size)
        self.remaining_actions = max(0, 718 - self.step)
        self.terminal = self.step >= 696

    def _farm(self, value):
        rows = _get(value, "tiles", [])
        rows = rows if isinstance(rows, (list, tuple)) else []
        tiles = []
        for y in range(self.size):
            row = rows[y] if y < len(rows) and isinstance(rows[y], (list, tuple)) else []
            tiles.append([_tile(row[x] if x < len(row) else "LOCKED", self.errors, x, y) for x in range(self.size)])
        unlocked = _get(value, "unlocked_quadrants", ["NW"])
        unlocked = tuple(q for q in unlocked if q in QUADRANTS) if isinstance(unlocked, (list, tuple)) else ("NW",)
        return {
            "money": _number(_get(value, "money", 0), 0),
            "tiles": tiles,
            "farmer": _position(_get(value, "farmer", [self.size // 2 - 1] * 2), self.size, (self.size // 2 - 1, self.size // 2 - 1)),
            "hands": tuple(_position(p, self.size) for p in (_get(value, "hands", []) if isinstance(_get(value, "hands", []), (list, tuple)) else [])),
            "unlocked_quadrants": unlocked or ("NW",),
            "hires_today": _int(_get(value, "hires_today", 0), 0, 0),
        }

    @staticmethod
    def _market_params(value):
        overrides = value if isinstance(value, Mapping) else {}
        result = {item: dict(params) for item, params in MARKET_PARAMS.items()}
        for item, patch in overrides.items():
            if item in result and isinstance(patch, Mapping):
                for key in result[item]:
                    if key in patch:
                        result[item][key] = patch[key]
        return result

    def tile(self, pos, farm=None):
        x, y = pos
        return (farm or self.me)["tiles"][y][x]

    def iter_tiles(self, farm=None):
        selected = farm or self.me
        for y, row in enumerate(selected["tiles"]):
            for x, tile in enumerate(row):
                yield (x, y), tile

    def inventory_load(self, idx):
        return sum(self.inventories[idx].values()) if idx < len(self.inventories) else 0

    def total_item(self, item):
        return self.shed.get(item, 0) + sum(inv.get(item, 0) for inv in self.inventories)

    def animal_count(self, animal, include_pending=True):
        total = sum(1 for _, tile in self.iter_tiles() if isinstance(tile, dict) and tile.get("animal") == animal)
        if include_pending:
            total += self.shed.get(animal, 0) + sum(inv.get(animal, 0) for inv in self.inventories)
        return total

    def crop_count(self, crop):
        return sum(1 for _, tile in self.iter_tiles() if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == crop)

    def at_shed(self, pos):
        return tuple(pos) in self.shed_access

    def unlocked(self, pos):
        return self.tile(pos) != "LOCKED"


def generic_safe_action(obs=None):
    """Last-ditch schema-safe action, including the observed hand count."""
    count = 0
    try:
        farms = _get(obs, "farms", [])
        player = _int(_get(obs, "player", 0), 0, 0)
        if isinstance(farms, (list, tuple)) and player < len(farms):
            hands = _get(farms[player], "hands", [])
            count = len(hands) if isinstance(hands, (list, tuple)) else 0
    except Exception:
        count = 0
    return {"farmer": ["PASS"], "hands": [["PASS"] for _ in range(count)], "market": []}

