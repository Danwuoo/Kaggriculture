"""Deadline-aware closed-loop farm task generation and greedy assignment."""

from dataclasses import dataclass

from constants import ANIMALS, CROPS, shed_tiles
from economy import can_finish_crop, crop_economic_value, fertilizer_incremental_value
from parameters import MAX_STRAWBERRY_PLANTS_PER_DAY, PLANT_CUTOFF_HOUR, RECOVERY_TURNS, SHED_SOFT_LIMIT
from strategy import desired_animals, desired_crops


@dataclass
class Job:
    priority: int
    deadline: int
    value: float
    positions: tuple
    action: list
    key: tuple
    requires: str = ""
    unit_idx: int = -1
    intent: tuple = ()


class Scheduler:
    def __init__(self, paths):
        self.paths = paths
        self.intents = {}
        self.last_day = -1

    def reset(self):
        self.intents.clear()
        self.last_day = -1

    def _recovery_jobs(self, state):
        jobs = []
        for idx, intent in list(self.intents.items()):
            if idx >= len(state.positions) or state.step > intent["expires"]:
                self.intents.pop(idx, None)
                continue
            pos = intent["pos"]
            tile = state.tile(pos)
            original = list(intent["action"])
            complete = (
                original[0] == "PLANT" and isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == original[1]
            ) or (
                original[0].startswith("BUILD_") and isinstance(tile, dict) and tile.get("kind") == original[0].replace("BUILD_", "")
            )
            if complete:
                self.intents.pop(idx, None)
                continue
            if isinstance(tile, dict) and tile.get("kind") == "WEED":
                jobs.append(Job(2, state.step + 2, 350, (pos,), ["DIG"], ("recover-dig", pos), unit_idx=idx, intent=tuple(original)))
            elif tile is None:
                if original[0] == "PLANT":
                    if state.seeds.get(original[1], 0) <= 0 or not can_finish_crop(state, original[1], pos):
                        self.intents.pop(idx, None)
                        continue
                    # A recovery may cross the normal planting cutoff while a
                    # worker is travelling. Wait for the next day rather than
                    # creating a plant that cannot be watered before refresh.
                    if state.hour > PLANT_CUTOFF_HOUR:
                        continue
                jobs.append(Job(2, state.step + 3, 300, (pos,), original, ("recover-retry", pos), unit_idx=idx, intent=tuple(original)))
            elif tile != "LOCKED":
                self.intents.pop(idx, None)
        return jobs

    def build_jobs(self, state, macro):
        if state.day != self.last_day:
            # Hands are destroyed and re-indexed at day boundaries. Keeping a
            # stale hand intent would route a different worker.
            self.intents = {0: self.intents[0]} if 0 in self.intents else {}
            self.last_day = state.day
        jobs = self._recovery_jobs(state)
        day_end = state.step + (23 - state.hour)
        animal_layout = desired_animals(state, macro)
        crop_layout = desired_crops(state, macro)
        # The engine checks LOCKED before PICKUP/DROP even on a shed-adjacent
        # center tile.  Route logistics only through currently usable access
        # tiles; otherwise the shadow inventory records a pickup that the final
        # legality projector correctly turns into a silent PASS.
        usable_shed = tuple(pos for pos in shed_tiles(state.size) if state.tile(pos) != "LOCKED")

        # Existing assets always generate maintenance jobs, independent of the
        # current economic target. This is the safety backbone of closed loop.
        urgent_feed = 0
        fertilizer_targets = []
        for pos, tile in state.iter_tiles():
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "PLANT":
                crop = tile["crop"]
                age = state.day - tile.get("planted_day", state.day)
                if not tile.get("watered_today", False):
                    critical = tile.get("consecutive_unwatered", 0) >= 1
                    production_window = age >= ((CROPS[crop]["max_day"] + 1) // 2)
                    priority = 0 if critical else (2 if production_window else 3)
                    jobs.append(Job(priority, day_end, 420 if critical else 130, (pos,), ["WATER"], ("water", pos)))
                yield_units = tile.get("yield_units", 0)
                mature = age >= CROPS[crop]["max_day"] or yield_units >= CROPS[crop]["max_yield"]
                if CROPS[crop]["ongoing"]:
                    mature = yield_units > 0
                decay_step = tile.get("max_lifespan_step", -1)
                decaying = decay_step >= 0 and decay_step <= state.step + 8
                if yield_units > 0 and (mature or decaying or state.terminal):
                    priority = 1 if decaying or state.terminal or yield_units >= CROPS[crop]["max_yield"] else 3
                    jobs.append(Job(priority, min(718, decay_step if decay_step >= 0 else state.step + 24), 90 + yield_units * state.market_prices[crop], (pos,), ["HARVEST"], ("harvest", pos)))
                fert_value = fertilizer_incremental_value(state, tile)
                if fert_value > 0 and tile.get("fertilized_until_day", -1) < state.day + 1 and not state.terminal:
                    fertilizer_targets.append((pos, fert_value))
                    jobs.append(Job(2, day_end, fert_value, (pos,), ["FERTILIZE"], ("fertilize", pos), requires="FERTILIZER"))
            elif tile.get("animal") in ANIMALS:
                animal = tile["animal"]
                if not tile.get("fed_today", False):
                    critical = tile.get("consecutive_unfed", 0) >= 1
                    urgent_feed += int(critical)
                    jobs.append(Job(0 if critical else 3, day_end, 600 if critical else 220, (pos,), ["FEED"], ("feed", pos), requires="WHEAT"))
                if tile.get("yield_units", 0) > 0:
                    held = tile["yield_units"]
                    full = held >= ANIMALS[animal]["max_held"]
                    jobs.append(Job(1 if full or state.terminal else 3, state.step + (2 if full else 24), 100 + held * state.market_prices[ANIMALS[animal]["product"]], (pos,), ["HARVEST"], ("animal-harvest", pos)))
                if not tile.get("cared_today", False):
                    jobs.append(Job(3, day_end, 55 + state.market_prices[ANIMALS[animal]["product"]] * .3, (pos,), ["CARE"], ("care", pos)))
                if tile.get("fertilizer_available", False):
                    jobs.append(Job(4, day_end, state.market_prices["FERTILIZER"] * .55, (pos,), ["COLLECT_FERTILIZER"], ("collect", pos)))

        # Carrying an animal is a high-risk tied-up capital task.
        empty_structures = {}
        for pos, wanted in animal_layout.items():
            tile = state.tile(pos)
            structure = ANIMALS[wanted]["structure"]
            if tile is None:
                jobs.append(Job(5, state.step + 24, 120, (pos,), ["BUILD_" + structure], ("build", pos), intent=("BUILD_" + structure,)))
            elif isinstance(tile, dict) and tile.get("kind") == "WEED":
                jobs.append(Job(2, state.step + 5, 180, (pos,), ["DIG"], ("layout-dig", pos), intent=("BUILD_" + structure,)))
            elif isinstance(tile, dict) and tile.get("kind") == structure and not tile.get("animal"):
                empty_structures.setdefault(wanted, []).append(pos)

        for animal, positions in empty_structures.items():
            for n in range(sum(inv.get(animal, 0) for inv in state.inventories)):
                jobs.append(Job(1, state.step + 12, 550, tuple(positions), ["PLACE", animal], ("place", animal, n), requires=animal))
            for n in range(state.shed.get(animal, 0)):
                jobs.append(Job(2, state.step + 10, 420, usable_shed, ["PICKUP", animal, 1], ("pickup-animal", animal, n)))

        # Feed staging: a few workers take a route-sized bundle at the shed.
        unfed = sum(1 for _, tile in state.iter_tiles() if isinstance(tile, dict) and tile.get("animal") and not tile.get("fed_today", False))
        if unfed and state.shed.get("WHEAT", 0) > 0:
            bundles = min(len(state.positions), max(2, (unfed + 3) // 4))
            for n in range(bundles):
                jobs.append(Job(0 if urgent_feed else 3, day_end, 360 if urgent_feed else 140, usable_shed, ["PICKUP", "WHEAT", min(6, state.shed["WHEAT"])], ("pickup-feed", n)))

        if fertilizer_targets and state.shed.get("FERTILIZER", 0) > 0:
            for n in range(min(2, state.shed["FERTILIZER"], len(fertilizer_targets))):
                jobs.append(Job(2, day_end, 120, usable_shed, ["PICKUP", "FERTILIZER", 1], ("pickup-fertilizer", n)))

        # Desired crop topology. Existing off-plan crops remain maintained above.
        strawberries_today = sum(
            1 for _, tile in state.iter_tiles()
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "STRAWBERRY" and tile.get("planted_day") == state.day
        )
        strawberry_room = max(0, MAX_STRAWBERRY_PLANTS_PER_DAY - strawberries_today)
        for pos, crop in crop_layout.items():
            tile = state.tile(pos)
            if isinstance(tile, dict) and tile.get("kind") == "WEED":
                if can_finish_crop(state, crop, pos):
                    jobs.append(Job(2, state.step + 5, 160, (pos,), ["DIG"], ("crop-dig", pos), intent=("PLANT", crop)))
                continue
            if tile is not None or state.hour > PLANT_CUTOFF_HOUR or not can_finish_crop(state, crop, pos):
                continue
            if crop == "STRAWBERRY":
                if strawberry_room <= 0:
                    continue
                strawberry_room -= 1
            if state.seeds.get(crop, 0) > 0:
                jobs.append(Job(5, day_end - 1, crop_economic_value(state, crop), (pos,), ["PLANT", crop], ("plant", pos), intent=("PLANT", crop)))

        # Backpack logistics are unit-specific. Start terminal trips early enough
        # for movement + DROP, not just at steps 717-718.
        for idx, (pos, inv) in enumerate(zip(state.positions, state.inventories)):
            load = sum(inv.values())
            sale_load = sum(n for item, n in inv.items() if item not in ANIMALS and not (item == "WHEAT" and unfed))
            distance = self.paths.distance_to_shed(pos)
            terminal_due = state.remaining_actions <= distance + 2
            if load and (terminal_due or sale_load >= 5 or state.hour >= 20 or state.shed_load >= SHED_SOFT_LIMIT):
                priority = 1 if terminal_due or state.shed_load >= SHED_SOFT_LIMIT else 3
                jobs.append(Job(priority, min(718, state.step + distance + 1), 300 + sale_load * 20, usable_shed, ["DROP"], ("drop", idx), unit_idx=idx))
        return jobs

    @staticmethod
    def _eligible(job, idx, inventories):
        if job.unit_idx >= 0 and job.unit_idx != idx:
            return False
        if job.requires and inventories[idx].get(job.requires, 0) <= 0:
            return False
        return True

    def assign(self, state, macro):
        jobs = self.build_jobs(state, macro)
        deduplicated = []
        seen_local = set()
        local_ops = {"DIG", "PLANT", "WATER", "HARVEST", "FERTILIZE", "FEED", "CARE", "COLLECT_FERTILIZER", "BUILD_COOP", "BUILD_PASTURE"}
        for job in jobs:
            signature = None
            if job.action[0] in local_ops and len(job.positions) == 1:
                signature = (tuple(job.action), job.positions[0])
            if signature is not None and signature in seen_local:
                continue
            if signature is not None:
                seen_local.add(signature)
            deduplicated.append(job)
        jobs = deduplicated
        jobs.sort(key=lambda job: (job.priority, job.deadline, -job.value, job.key))
        actions = [["PASS"] for _ in state.positions]
        free = set(range(len(state.positions)))
        seeds = dict(state.seeds)
        shed = dict(state.shed)
        inventories = [dict(inv) for inv in state.inventories]

        for job in jobs:
            candidates = []
            for idx in free:
                if not self._eligible(job, idx, inventories):
                    continue
                target = self.paths.nearest(state.positions[idx], job.positions)
                if target is None:
                    continue
                distance = self.paths.distance(state.positions[idx], target)
                # Carrying animals is a severe opportunity cost for unrelated jobs.
                tied_capital = 50 if any(inventories[idx].get(a, 0) for a in ANIMALS) and job.action[0] != "PLACE" else 0
                candidates.append((distance + tied_capital, idx, target))
            if not candidates:
                continue
            _, idx, target = min(candidates)
            distance = self.paths.distance(state.positions[idx], target)
            action = list(job.action)
            if distance:
                actions[idx] = self.paths.next_action(state.positions[idx], target)
            else:
                if action[0] == "PLANT":
                    crop = action[1]
                    if seeds.get(crop, 0) <= 0:
                        continue
                    seeds[crop] -= 1
                elif action[0] == "PICKUP":
                    item = action[1]
                    count = min(int(action[2]), shed.get(item, 0))
                    if count <= 0:
                        continue
                    action[2] = count
                    shed[item] -= count
                    inventories[idx][item] = inventories[idx].get(item, 0) + count
                elif action[0] in ("FEED", "FERTILIZE"):
                    item = "WHEAT" if action[0] == "FEED" else "FERTILIZER"
                    if inventories[idx].get(item, 0) <= 0:
                        continue
                    inventories[idx][item] -= 1
                elif action[0] == "PLACE" and action[1] in ANIMALS:
                    if inventories[idx].get(action[1], 0) <= 0:
                        continue
                    inventories[idx][action[1]] -= 1
                actions[idx] = action
            free.remove(idx)
            if job.intent:
                self.intents[idx] = {"pos": target, "action": tuple(job.intent), "expires": state.step + RECOVERY_TURNS}

        # A hand spawned on LOCKED must always move out even when there are no
        # remaining jobs. All cells are pathable, farm actions are not.
        unlocked_positions = tuple(pos for pos, tile in state.iter_tiles() if tile != "LOCKED")
        for idx in sorted(free):
            if state.tile(state.positions[idx]) == "LOCKED" and unlocked_positions:
                goal = self.paths.nearest(state.positions[idx], unlocked_positions)
                actions[idx] = self.paths.next_action(state.positions[idx], goal)
        return {"farmer": actions[0], "hands": actions[1:], "market": []}

    def safe_schedule(self, state):
        """Level 2: only local survival, harvest, return, and LOCKED escape."""
        actions = []
        urgent = []
        for pos, tile in state.iter_tiles():
            if isinstance(tile, dict) and (
                (tile.get("kind") == "PLANT" and not tile.get("watered_today"))
                or (tile.get("animal") and not tile.get("fed_today"))
            ):
                urgent.append(pos)
        for idx, pos in enumerate(state.positions):
            tile = state.tile(pos)
            inv = state.inventories[idx]
            action = ["PASS"]
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" and not tile.get("watered_today"):
                action = ["WATER"]
            elif isinstance(tile, dict) and tile.get("animal") and not tile.get("fed_today") and inv.get("WHEAT", 0):
                action = ["FEED"]
            elif isinstance(tile, dict) and tile.get("yield_units", 0) > 0:
                action = ["HARVEST"]
            elif sum(inv.values()) and state.at_shed(pos) and state.shed_load < 100:
                action = ["DROP"]
            elif sum(inv.values()) and (state.terminal or state.hour >= 20):
                goal = self.paths.nearest(pos, state.shed_access)
                action = self.paths.next_action(pos, goal)
            elif tile == "LOCKED":
                goals = tuple(p for p, t in state.iter_tiles() if t != "LOCKED")
                goal = self.paths.nearest(pos, goals)
                action = self.paths.next_action(pos, goal) if goal else ["PASS"]
            elif urgent:
                goal = self.paths.nearest(pos, urgent)
                action = self.paths.next_action(pos, goal)
            actions.append(action)
        return {"farmer": actions[0], "hands": actions[1:], "market": []}
