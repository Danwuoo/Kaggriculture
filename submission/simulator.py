"""Compressed daily macro planner (no board-state rollout tree at runtime)."""

from constants import ANIMALS
from economy import animal_marginal_value, land_marginal_value
from parameters import OPENING_MELONS


class MacroPlanner:
    def __init__(self):
        self.plan = {}
        self.last_day = -1

    def update(self, state, forecast, force=False):
        if self.plan and not force and state.day == self.last_day:
            return dict(self.plan)
        day = state.day
        money = state.me["money"]

        # Baseline route is a floor/ceiling, not an action tape. Candidate herd
        # sizes are scored against live prices, remaining time, and labor.
        if day <= 3:
            base = (3, 1, 0)
        elif day <= 10:
            base = (5, 3, 2)
        else:
            base = (8, 5 if money < 6000 else 6, 7)
        if day >= 22:
            base = (state.animal_count("COW"), state.animal_count("SHEEP"), state.crop_count("STRAWBERRY"))

        cow_candidates = sorted(set((max(3, base[0] - 2), base[0], min(8, base[0] + 1))))
        sheep_candidates = sorted(set((max(1, base[1] - 2), base[1], min(6, base[1] + 1))))
        strawberry_candidates = sorted(set((max(0, base[2] - 2), base[2], min(7, base[2] + 1))))
        current_cows = state.animal_count("COW")
        current_sheep = state.animal_count("SHEEP")
        best = None
        for cows in cow_candidates:
            for sheep in sheep_candidates:
                for strawberries in strawberry_candidates:
                    buy_cost = max(0, cows - current_cows) * ANIMALS["COW"]["cost"] + max(0, sheep - current_sheep) * ANIMALS["SHEEP"]["cost"]
                    benefit = max(0, cows - current_cows) * animal_marginal_value(state, "COW")
                    benefit += max(0, sheep - current_sheep) * animal_marginal_value(state, "SHEEP")
                    benefit += strawberries * max(0, state.market_prices["STRAWBERRY"] * 2 - 100)
                    workload = (cows + sheep) * 3.4 + strawberries * 1.25
                    labor_capacity = max(1, min(12, 2 + int(workload / 16))) * 18
                    penalty = max(0, workload - labor_capacity) * 120 + max(0, buy_cost - money + 300) * 2
                    score = benefit - penalty - abs(cows - base[0]) * 25 - abs(sheep - base[1]) * 20
                    candidate = (score, -buy_cost, cows, sheep, strawberries, workload)
                    if best is None or candidate > best:
                        best = candidate
        _, _, cows, sheep, strawberries, workload = best

        # Preserve the explicitly requested reliable opening even when early
        # market noise makes a one-day local estimate pessimistic.
        if day <= 3:
            cows, sheep = 3, 1

        unlocked = len(state.me["unlocked_quadrants"])
        land = unlocked
        occupied = sum(1 for _, tile in state.iter_tiles() if tile not in (None, "LOCKED"))
        if day >= 4 and unlocked == 1 and money >= 1250 and occupied >= 10:
            land = 2
        elif day >= 9 and unlocked == 2 and money >= 2600 and occupied >= 16:
            land = 3
        elif day <= 18 and unlocked == 3 and money >= 5200 and occupied >= 50 and land_marginal_value(state, "SE") > 300:
            land = 4

        safety_jobs = sum(
            1 for _, tile in state.iter_tiles()
            if isinstance(tile, dict) and (
                (tile.get("kind") == "PLANT" and not tile.get("watered_today"))
                or (tile.get("animal") and not tile.get("fed_today"))
            )
        )
        labor_floor = 6 if day <= 3 else (8 if day <= 10 else 10)
        hands = min(12, max(labor_floor, int((workload + safety_jobs + 10) / 10)))
        if money < 100:
            hands = min(hands, 5)

        seed_needs = {"WHEAT": max(1, 4 - state.crop_count("WHEAT"))}
        if day <= 7:
            seed_needs["MELON"] = max(0, OPENING_MELONS - state.crop_count("MELON"))
        elif day <= 18:
            seed_needs["STRAWBERRY"] = min(2, max(0, strawberries - state.crop_count("STRAWBERRY")))

        self.plan = {
            "cows": cows,
            "sheep": sheep,
            "geese": 0,
            "strawberries": strawberries,
            "melons": OPENING_MELONS if day <= 10 else 0,
            "wheat": 4,
            "hands": hands,
            "land": land,
            "seed_needs": seed_needs,
        }
        self.last_day = day
        return dict(self.plan)
