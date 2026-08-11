"""Stable spatial roles and adaptive desired farm topology."""

from constants import quadrant_of


# Near-shed animal logistics first; six NE cells are used only after unlock.
ANIMAL_SLOTS = (
    (4, 4), (3, 4), (2, 4), (1, 4), (0, 4), (4, 3), (3, 3), (2, 3),
    (5, 4), (6, 4), (7, 4), (8, 4), (9, 4), (5, 3),
)

NW_CROP_SLOTS = (
    (0, 0), (1, 0), (2, 0), (3, 0), (4, 0),
    (0, 1), (1, 1), (2, 1), (3, 1), (4, 1), (0, 2), (1, 2),
)
SW_CROP_SLOTS = (
    (4, 5), (3, 5), (2, 5), (1, 5), (0, 5),
    (4, 6), (3, 6), (2, 6), (1, 6), (0, 6),
)


def _available(state, positions):
    unlocked = set(state.me["unlocked_quadrants"])
    return tuple(pos for pos in positions if quadrant_of(pos[0], pos[1], state.size) in unlocked)


def desired_animals(state, macro):
    count_cows = int(macro.get("cows", 0))
    count_sheep = int(macro.get("sheep", 0))
    # The first four slots are the robust 3C1S opening. Expansion alternates to
    # avoid a long single-product cohort and keeps the assignment stable.
    types = ["COW", "COW", "COW", "SHEEP"]
    types += ["COW", "SHEEP", "COW", "SHEEP", "COW", "SHEEP", "COW", "SHEEP", "COW", "SHEEP"]
    remaining = {"COW": count_cows, "SHEEP": count_sheep}
    selected = []
    for animal in types:
        if remaining.get(animal, 0) > 0:
            selected.append(animal)
            remaining[animal] -= 1
    slots = _available(state, ANIMAL_SLOTS)
    return {pos: animal for pos, animal in zip(slots, selected)}


def desired_crops(state, macro):
    mapping = {}
    nw = _available(state, NW_CROP_SLOTS)
    if state.day <= 10:
        for pos in nw[: int(macro.get("melons", 0))]:
            mapping[pos] = "MELON"
        start = int(macro.get("melons", 0))
        for pos in nw[start:start + int(macro.get("wheat", 0))]:
            mapping[pos] = "WHEAT"
    else:
        crop_slots = _available(state, SW_CROP_SLOTS) or nw
        wanted = int(macro.get("strawberries", 0))
        for idx, pos in enumerate(crop_slots[:wanted]):
            # Two-tile cohorts every two days. A missed cohort is still capped
            # by the scheduler's per-day planting guard.
            if state.day >= 8 + 2 * (idx // 2):
                mapping[pos] = "STRAWBERRY"
        used = set(mapping)
        wheat_slots = [pos for pos in nw if pos not in used]
        for pos in wheat_slots[: int(macro.get("wheat", 0))]:
            mapping[pos] = "WHEAT"
    return mapping

