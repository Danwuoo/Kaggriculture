"""In-memory genome execution with a final legality and atomic-plant boundary."""

from __future__ import annotations

import copy
from typing import Any, Callable, Mapping

from .genome import FullTapeGenome, RootTape


CROPS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"}
ANIMALS = {"GOOSE", "COW", "SHEEP"}
PRODUCTS = CROPS | {"EGG", "MILK", "WOOL", "FERTILIZER"}
SIMPLE_UNIT = {
    "NORTH", "SOUTH", "EAST", "WEST", "PASS", "DROP", "WATER", "HARVEST",
    "BUILD_COOP", "BUILD_PASTURE", "DIG", "COLLECT_FERTILIZER", "CARE",
}


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _unit(row: Any) -> list[Any]:
    if not isinstance(row, list) or not row or not isinstance(row[0], str):
        return ["PASS"]
    op = row[0]
    if op in SIMPLE_UNIT and len(row) == 1:
        return copy.deepcopy(row)
    if op == "FEED" and (len(row) == 1 or (len(row) == 2 and row[1] == "WHEAT")):
        return copy.deepcopy(row)
    if op == "FERTILIZE" and (len(row) == 1 or (len(row) == 2 and row[1] == "FERTILIZER")):
        return copy.deepcopy(row)
    if op == "PLANT" and len(row) == 2 and row[1] in CROPS:
        return copy.deepcopy(row)
    if op in {"PICKUP", "PLACE"} and len(row) in {2, 3} and row[1] in PRODUCTS | ANIMALS:
        if len(row) == 2 or _positive_int(row[2]):
            return copy.deepcopy(row)
    return ["PASS"]


def _market(row: Any) -> list[Any] | None:
    if not isinstance(row, list) or not row or not isinstance(row[0], str):
        return None
    op = row[0]
    if op in {"HIRE", "BUY_LAND"}:
        return copy.deepcopy(row) if len(row) == 1 else None
    if len(row) != 3 or not _positive_int(row[2]):
        return None
    item = row[1]
    if op == "BUY_SEED" and item in CROPS:
        return copy.deepcopy(row)
    if op == "BUY_PRODUCT" and item in {"WHEAT", "FERTILIZER"}:
        return copy.deepcopy(row)
    if op == "BUY_ANIMAL" and item in ANIMALS:
        return copy.deepcopy(row)
    if op == "SELL" and item in PRODUCTS:
        return copy.deepcopy(row)
    return None


def _plain_observation(obs: Any) -> Mapping[str, Any] | None:
    if isinstance(obs, Mapping):
        return obs
    try:
        return {key: getattr(obs, key) for key in ("player", "step", "farms", "private")}
    except (AttributeError, TypeError):
        return None


def project_action(observation: Any, candidate: Any, incumbent: Mapping[str, Any]) -> dict[str, Any]:
    """Project immediately before return; malformed state preserves incumbent."""
    view = _plain_observation(observation)
    if view is None or not isinstance(candidate, Mapping):
        return copy.deepcopy(dict(incumbent))
    player = view.get("player")
    farms = view.get("farms")
    private = view.get("private")
    if (not isinstance(player, int) or isinstance(player, bool) or player not in (0, 1)
            or not isinstance(farms, list) or len(farms) != 2 or not isinstance(farms[player], Mapping)
            or not isinstance(private, Mapping) or not isinstance(private.get("seeds"), Mapping)):
        return copy.deepcopy(dict(incumbent))
    hands_state = farms[player].get("hands")
    if not isinstance(hands_state, list):
        return copy.deepcopy(dict(incumbent))

    farmer = _unit(candidate.get("farmer"))
    hands_raw = candidate.get("hands")
    market_raw = candidate.get("market")
    if not isinstance(hands_raw, list) or not isinstance(market_raw, list):
        return copy.deepcopy(dict(incumbent))
    hands = [_unit(hands_raw[index]) if index < len(hands_raw) else ["PASS"] for index in range(len(hands_state))]
    market = [projected for row in market_raw[:10] if (projected := _market(row)) is not None]

    units = [farmer, *hands]
    requested: dict[str, int] = {}
    for row in units:
        if row[0] == "PLANT":
            requested[row[1]] = requested.get(row[1], 0) + 1
    seeds = private["seeds"]
    for crop, count in requested.items():
        available = seeds.get(crop)
        if not isinstance(available, int) or isinstance(available, bool):
            return copy.deepcopy(dict(incumbent))
        if count > available:
            units = [["PASS"] if row[0] == "PLANT" and row[1] == crop else row for row in units]
    return {"farmer": units[0], "hands": units[1:], "market": market}


def make_policy_factory(genome: FullTapeGenome, root: RootTape) -> Callable[[Any, Callable[..., dict], int], Callable[..., dict]]:
    """Return an engine-runner policy factory without standalone artifacts."""
    tape = genome.materialize(root)
    patched_steps = {patch.step for patch in genome.patches}
    root_is_incumbent = root.source_kind == "lane_incumbent" and root.source_id == genome.lane

    def factory(_module: Any, incumbent_agent: Callable[..., dict], _seat: int) -> Callable[..., dict]:
        def policy(obs: Any, configuration: Any = None) -> dict[str, Any]:
            # Both active local entrypoints accept observation-only invocation;
            # the outer wrapper remains compatible with server-style optional
            # configuration without forwarding an unsupported second argument.
            incumbent = incumbent_agent(obs)
            view = _plain_observation(obs)
            if view is None:
                return incumbent
            step = view.get("step")
            if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step < 719:
                return incumbent
            if root_is_incumbent and step not in patched_steps:
                return incumbent
            # Final projection is deliberately the last operation before return.
            return project_action(obs, tape[step], incumbent)

        policy.metadata = {
            "candidate_id": genome.candidate_id,
            "lane": genome.lane,
            "root_id": root.root_id,
            "root_source_kind": root.source_kind,
            "edit_distance": genome.edit_distance_from_root(),
        }
        return policy

    return factory
