"""Small public-only fixtures for job-window discovery tests."""

from __future__ import annotations

from copy import deepcopy


SELLABLE = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")


def observation_fixture(*, hands: int = 1, step: int = 10, farmer=(0, 0), hand_positions=None):
    """Return a new public observation with private state only for its owner."""
    if hand_positions is None:
        hand_positions = [(1, 1)] * hands
    tiles = [[None for _ in range(10)] for _ in range(10)]
    farm = {"money": 3000, "farmer": list(farmer), "hands": [list(p) for p in hand_positions], "tiles": tiles}
    return {
        "player": 0,
        "step": step,
        "farms": [farm, deepcopy(farm)],
        "private": {
            "shed": {product: 0 for product in SELLABLE},
            "inventories": [{product: 0 for product in SELLABLE} for _ in range(hands + 1)],
        },
        "market": {"inventory": {product: 10000 for product in SELLABLE}, "prices": {product: 10 for product in SELLABLE}},
        "town": {"unlocked_shops": []},
    }


def candidate_fixture():
    """Return a legal four-turn actor-one productive detour."""
    from schema import CandidateWindow

    return CandidateWindow(
        candidate_id="fixture",
        incumbent="v27_current_meta",
        family="productive_detour",
        trigger_step=10,
        actor=1,
        rejoin_step=14,
        actions=(("EAST",), ("HARVEST",), ("WEST",), ("PASS",)),
        expected_positions=((1, 1), (2, 1), (2, 1), (1, 1), (1, 1)),
        requirements=(),
        sell_directives=(),
        displaced_actions=(("PASS",),) * 4,
        touched_tiles=((2, 1),),
    )


def base_policy(obs, configuration=None):
    farm = obs["farms"][int(obs.get("player", 0))]
    return {
        "farmer": ["PASS"],
        "hands": [["PASS"] for _ in farm.get("hands", [])],
        "market": [],
    }


def passing_discovery_summary():
    return {
        incumbent: {
            "positive": 4,
            "negative": 4,
            "families": ["maintenance_trade", "productive_detour"],
            "legal_rejoin_rate": 1.0,
            "technical_failures": 0,
            "score_accuracy": 0.75,
            "constant_accuracy": 0.5,
            "family_accuracy": 0.5,
            "incumbent_accuracy": 0.5,
        }
        for incumbent in ("v27_current_meta", "boatlee_v16_rc2_market_relay")
    }


def matched_rows(outcomes, *, families=("other_incumbent",), seats=(0,), seeds=(1,)):
    rows = []
    for index, (control, candidate) in enumerate(outcomes):
        rows.append({
            "control_outcome": control,
            "candidate_outcome": candidate,
            "margin_delta": candidate - control,
            "opponent_family": families[index % len(families)],
            "seat": seats[index % len(seats)],
            "seed": seeds[index % len(seeds)],
        })
    return rows
