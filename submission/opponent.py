"""Public-information-only crop/animal cohort forecast."""

from constants import ANIMALS, CROPS, PRODUCTS, shed_tiles


WINDOWS = (1, 3, 6, 12, 24)


def _distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class OpponentModel:
    def forecast(self, state):
        result = {window: {item: 0 for item in PRODUCTS} for window in WINDOWS}
        exposure = {item: 0 for item in PRODUCTS}
        opponents = []
        for player_id, farm in enumerate(state.farms):
            if player_id == state.player:
                continue
            units = (farm["farmer"],) + tuple(farm["hands"])
            cohort = {"money": farm["money"], "workers": len(units), "animals": 0, "crops": 0, "land": len(farm["unlocked_quadrants"])}
            for pos, tile in state.iter_tiles(farm):
                if not isinstance(tile, dict):
                    continue
                if tile.get("kind") == "PLANT":
                    cohort["crops"] += 1
                    item = tile["crop"]
                    units_ready = self._crop_units(state, tile, 24)
                elif tile.get("animal") in ANIMALS:
                    cohort["animals"] += 1
                    item = ANIMALS[tile["animal"]]["product"]
                    units_ready = self._animal_units(state, tile, 24)
                else:
                    continue
                nearest_worker = min((_distance(pos, p) for p in units), default=20)
                to_shed = min(_distance(pos, p) for p in shed_tiles(state.size))
                shipping = nearest_worker + 1 + to_shed + 1
                for window in WINDOWS:
                    quantity = self._crop_units(state, tile, window) if tile.get("kind") == "PLANT" else self._animal_units(state, tile, window)
                    if quantity and shipping <= window:
                        result[window][item] += quantity
                if units_ready and shipping <= 24:
                    exposure[item] += units_ready
            opponents.append(cohort)
        return {"windows": result, "exposure": exposure, "cohorts": opponents}

    @staticmethod
    def _crop_units(state, tile, horizon):
        crop = tile["crop"]
        data = CROPS[crop]
        current = int(tile.get("yield_units", 0))
        future_day = state.day + (state.hour + horizon) // 24
        age = future_day - int(tile.get("planted_day", state.day))
        if not data["ongoing"]:
            if age < data["first"]:
                return 0
            # Public watering history is incomplete; current yield is the safe
            # lower bound and max-yield age supplies a bounded estimate.
            return max(current, min(data["max_yield"], 1 + max(0, age - ((data["max_day"] + 1) // 2) + 1)))
        if age < data["first"]:
            return current
        produced = min(data["max_yield"], (age - data["first"]) // data["interval"] + 1)
        return max(current, produced)

    @staticmethod
    def _animal_units(state, tile, horizon):
        animal = tile["animal"]
        data = ANIMALS[animal]
        current = int(tile.get("yield_units", 0))
        future_day = state.day + (state.hour + horizon) // 24
        age = future_day - int(tile.get("placed_day", state.day))
        if age < data["first"]:
            return current
        ticks = (age - data["first"]) // data["interval"] + 1
        return min(data["max_held"], current + ticks)

