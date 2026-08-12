"""Conservative, mutually-exclusive labels for paired job-window traces."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from schema import CandidateWindow, HorizonEffect, MarketShift


PRODUCT_FROM_ANIMAL = {"COW": "MILK", "SHEEP": "WOOL"}
SHED_TILES = ((4, 4), (5, 4), (4, 5), (5, 5))


@dataclass(frozen=True)
class LedgerBreakdown:
    cash: float
    liquidatable: float
    asset: float
    capacity: float
    market: float

    @property
    def total(self) -> float:
        return self.cash + self.liquidatable + self.asset + self.capacity + self.market


def _distinct_buckets(effect: HorizonEffect) -> bool:
    seen: set[str] = set()
    for bucket in (effect.liquidatable, effect.asset, effect.capacity):
        for row in bucket:
            if len(row) != 3 or str(row[2]) in seen:
                return False
            seen.add(str(row[2]))
    return True


def _bucket_value(rows: Iterable[tuple[str, int, str]], quotes: Mapping[str, Any]) -> float | None:
    total = 0.0
    for product, quantity, _provenance in rows:
        quote = quotes.get(product)
        if not isinstance(quote, (int, float)):
            return None
        total += int(quantity) * float(quote)
    return total


def value_effect(
    effect: HorizonEffect,
    conservative_quotes: Mapping[str, Any],
    timing_adjustments: Mapping[str, Any],
) -> LedgerBreakdown | None:
    """Price one horizon without counting a product unit in two buckets."""
    if not _distinct_buckets(effect):
        return None
    liquidatable = _bucket_value(effect.liquidatable, conservative_quotes)
    asset = _bucket_value(effect.asset, conservative_quotes)
    capacity = _bucket_value(effect.capacity, conservative_quotes)
    if liquidatable is None or asset is None or capacity is None:
        return None
    market = 0.0
    for shift in effect.market:
        adjustment = (
            shift.candidate_receipt - shift.control_receipt
            if shift.control_receipt is not None and shift.candidate_receipt is not None
            else timing_adjustments.get(shift.provenance)
        )
        if not isinstance(adjustment, (int, float)):
            return None
        market += float(adjustment)
    return LedgerBreakdown(float(effect.cash_coins), liquidatable, asset, capacity, market)


def _frame_value(frame: Any, name: str, default: Any = None) -> Any:
    if isinstance(frame, Mapping):
        return frame.get(name, default)
    return getattr(frame, name, default)


def _frame_context(frame: Any) -> tuple[str, str, int, int] | None:
    value = _frame_value(frame, "context")
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        return None
    try:
        return str(value[0]), str(value[1]), int(value[2]), int(value[3])
    except (TypeError, ValueError):
        return None


def _frames_by_step(trace: Sequence[Any]) -> dict[int, Any]:
    frames: dict[int, Any] = {}
    for frame in trace:
        step = _frame_value(frame, "step")
        if isinstance(step, int):
            frames[step] = frame
    return frames


def _own_private(observation: Mapping[str, Any]) -> Mapping[str, Any] | None:
    private = observation.get("private")
    return private if isinstance(private, Mapping) else None


def _product_inventory(observation: Mapping[str, Any], product: str) -> int | None:
    private = _own_private(observation)
    if private is None:
        return None
    total = 0
    shed = private.get("shed")
    if not isinstance(shed, Mapping):
        return None
    total += max(0, int(shed.get(product, 0) or 0))
    inventories = private.get("inventories")
    if not isinstance(inventories, list):
        return None
    for inventory in inventories:
        if not isinstance(inventory, Mapping):
            return None
        total += max(0, int(inventory.get(product, 0) or 0))
    return total


def _own_money(observation: Mapping[str, Any]) -> float | None:
    farms, player = observation.get("farms"), observation.get("player")
    if not isinstance(farms, list) or not isinstance(player, int) or not (0 <= player < len(farms)):
        return None
    value = farms[player].get("money") if isinstance(farms[player], Mapping) else None
    return float(value) if isinstance(value, (int, float)) else None


def _tile_yield(observation: Mapping[str, Any], tile: tuple[int, int]) -> tuple[str, int] | None:
    farms, player = observation.get("farms"), observation.get("player")
    if not isinstance(farms, list) or not isinstance(player, int) or not (0 <= player < len(farms)):
        return None
    farm = farms[player]
    tiles = farm.get("tiles") if isinstance(farm, Mapping) else None
    x, y = tile
    if not isinstance(tiles, list) or y < 0 or y >= len(tiles) or not isinstance(tiles[y], list) or x < 0 or x >= len(tiles[y]):
        return None
    item = tiles[y][x]
    if not isinstance(item, Mapping):
        return None
    product = item.get("crop") if item.get("kind") == "PLANT" else PRODUCT_FROM_ANIMAL.get(item.get("animal"))
    yield_units = item.get("yield_units")
    if not isinstance(product, str) or not isinstance(yield_units, (int, float)):
        return None
    return product, int(yield_units)


def _market_sales(trace: Sequence[Any], start: int, end: int) -> dict[str, list[tuple[int, int, int, float]]] | None:
    """Bind each SELL order to actual committed unit receipts from the runner."""
    sales: dict[str, list[tuple[int, int, int, float]]] = {}
    for frame in trace:
        step = _frame_value(frame, "step")
        if not isinstance(step, int) or not start <= step <= end:
            continue
        action = _frame_value(frame, "action", {})
        observation = _frame_value(frame, "observation", {})
        if not isinstance(action, Mapping) or not isinstance(observation, Mapping):
            continue
        receipts = _frame_value(frame, "market_receipts", ())
        if not isinstance(receipts, (tuple, list)):
            return None
        by_product: dict[str, list[float]] = {}
        for receipt in receipts:
            if not isinstance(receipt, (tuple, list)) or len(receipt) != 3 or receipt[0] != step or not isinstance(receipt[2], (int, float)):
                return None
            by_product.setdefault(str(receipt[1]), []).append(float(receipt[2]))
        for order_index, order in enumerate(action.get("market", []) or []):
            if not isinstance(order, (list, tuple)) or len(order) < 3 or order[0] != "SELL":
                continue
            product, quantity = str(order[1]), int(order[2] or 0)
            if quantity <= 0:
                continue
            committed = by_product.get(product, [])[:quantity]
            by_product[product] = by_product.get(product, [])[quantity:]
            if len(committed) != quantity:
                return None
            sales.setdefault(product, []).extend(
                (step, order_index, unit_index, receipt)
                for unit_index, receipt in enumerate(committed)
            )
        if any(values for values in by_product.values()):
            return None
    return sales


def _shift_for_product(
    product: str,
    control: list[tuple[int, int, int, float]],
    candidate: list[tuple[int, int, int, float]],
    trigger: int,
) -> tuple[MarketShift, ...] | None:
    if len(control) != len(candidate):
        return None
    shifts: list[MarketShift] = []
    left, right = list(control), list(candidate)
    # Preserve same-step/same-order units first.  Their receipt difference is a
    # cash effect, not a timing premium, even if a shifted sibling changed price.
    matched_left: set[int] = set()
    matched_right: set[int] = set()
    for left_index, (left_step, left_order, _left_unit, _left_receipt) in enumerate(left):
        for right_index, (right_step, right_order, _right_unit, _right_receipt) in enumerate(right):
            if right_index not in matched_right and (left_step, left_order) == (right_step, right_order):
                matched_left.add(left_index)
                matched_right.add(right_index)
                break
    left = [item for index, item in enumerate(left) if index not in matched_left]
    right = [item for index, item in enumerate(right) if index not in matched_right]
    if len(left) != len(right):
        return None
    index = 0
    for control_unit, candidate_unit in zip(sorted(left), sorted(right)):
        c_step, _c_order, _c_unit, c_receipt = control_unit
        d_step, _d_order, _d_unit, d_receipt = candidate_unit
        if c_step != d_step:
            shifts.append(MarketShift(
                product, 1, c_step - trigger, d_step - trigger,
                f"sale:{product}:{index}", c_receipt, d_receipt,
            ))
            index += 1
    return tuple(shifts)


def _capacity_rows(frame: Any) -> dict[str, tuple[str, int]] | None:
    """Read only runner-recorded capacity-delayed units, rejecting ambiguity."""
    raw = _frame_value(frame, "capacity_inflight", ())
    if not isinstance(raw, (list, tuple)):
        return None
    certification = _frame_value(frame, "capacity_certification")
    if raw and certification != "certified_capacity_inflight":
        return None
    if not raw and not isinstance(certification, str):
        return None
    rows: dict[str, tuple[str, int]] = {}
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            return None
        product, quantity, provenance = str(item[0]), item[1], str(item[2])
        if not isinstance(quantity, int) or quantity < 0 or provenance in rows:
            return None
        rows[provenance] = (product, quantity)
    return rows


def derive_horizon_effects(control_trace: Sequence[Any], candidate_trace: Sequence[Any], window: CandidateWindow) -> tuple[HorizonEffect, ...] | None:
    """Build 24/48-turn effects, refusing incomplete or non-conserved paired traces."""
    control_frames, candidate_frames = _frames_by_step(control_trace), _frames_by_step(candidate_trace)
    if not control_frames or not candidate_frames:
        return None
    trigger_control = control_frames.get(window.trigger_step)
    trigger_candidate = candidate_frames.get(window.trigger_step)
    context = _frame_context(trigger_control) if trigger_control is not None else None
    if (
        context is None
        or context[0] != window.incumbent
        or trigger_candidate is None
        or _frame_context(trigger_candidate) != context
    ):
        return None
    products = {directive.product for directive in window.sell_directives}
    for tile in window.touched_tiles:
        for frames in (control_frames, candidate_frames):
            frame = frames.get(window.trigger_step)
            observation = _frame_value(frame, "observation", {}) if frame is not None else {}
            tile_product = _tile_yield(observation, tile) if isinstance(observation, Mapping) else None
            if tile_product is not None:
                products.add(tile_product[0])
    results: list[HorizonEffect] = []
    for horizon in sorted({min(24, max(1, 718 - window.trigger_step)), min(48, max(1, 718 - window.trigger_step))}):
        step = min(window.trigger_step + horizon, 718)
        control_frame, candidate_frame = control_frames.get(step), candidate_frames.get(step)
        if control_frame is None or candidate_frame is None:
            return None
        if _frame_context(control_frame) != context or _frame_context(candidate_frame) != context:
            return None
        control_obs, candidate_obs = _frame_value(control_frame, "observation", {}), _frame_value(candidate_frame, "observation", {})
        if not isinstance(control_obs, Mapping) or not isinstance(candidate_obs, Mapping):
            return None
        control_money, candidate_money = _own_money(control_obs), _own_money(candidate_obs)
        if control_money is None or candidate_money is None:
            return None
        liquidatable: list[tuple[str, int, str]] = []
        asset: list[tuple[str, int, str]] = []
        for product in sorted(products):
            control_units, candidate_units = _product_inventory(control_obs, product), _product_inventory(candidate_obs, product)
            if control_units is None or candidate_units is None:
                return None
            delta = candidate_units - control_units
            if delta:
                liquidatable.append((product, delta, f"inventory:{product}"))
        for tile in sorted(window.touched_tiles):
            before = _tile_yield(control_obs, tile)
            after = _tile_yield(candidate_obs, tile)
            if before is None or after is None or before[0] != after[0]:
                continue
            delta = after[1] - before[1]
            if delta:
                asset.append((after[0], delta, f"tile:{tile[0]},{tile[1]}"))
        control_sales = _market_sales(control_trace, window.trigger_step, step)
        candidate_sales = _market_sales(candidate_trace, window.trigger_step, step)
        if control_sales is None or candidate_sales is None:
            return None
        shifts: list[MarketShift] = []
        for product in sorted(set(control_sales) | set(candidate_sales) | products):
            found = _shift_for_product(product, control_sales.get(product, []), candidate_sales.get(product, []), window.trigger_step)
            if found is None:
                return None
            shifts.extend(found)
        # Timing adjustments are deliberately omitted from cash only when a shifted sale is observed.
        timing = 0.0
        for shift in shifts:
            if shift.control_receipt is None or shift.candidate_receipt is None:
                return None
            timing += shift.candidate_receipt - shift.control_receipt
        control_capacity = _capacity_rows(control_frame)
        candidate_capacity = _capacity_rows(candidate_frame)
        if control_capacity is None or candidate_capacity is None:
            return None
        capacity: list[tuple[str, int, str]] = []
        for provenance in sorted(set(control_capacity) | set(candidate_capacity)):
            before = control_capacity.get(provenance)
            after = candidate_capacity.get(provenance)
            if before is not None and after is not None and before[0] != after[0]:
                return None
            product = (after or before)[0]
            delta = (after[1] if after else 0) - (before[1] if before else 0)
            if delta:
                capacity.append((product, delta, provenance))
        effect = HorizonEffect(
            horizon, candidate_money - control_money - timing,
            tuple(liquidatable), tuple(asset), tuple(capacity), tuple(shifts),
            context,
        )
        if not _distinct_buckets(effect):
            return None
        results.append(effect)
    return tuple(results)


def estimate_window(
    effects: Sequence[HorizonEffect], conservative_quotes: Mapping[str, Any], timing_adjustments: Mapping[str, Any],
) -> dict[int, LedgerBreakdown] | None:
    """Return a deterministic horizon-to-breakdown map, or unknown as a whole."""
    values: dict[int, LedgerBreakdown] = {}
    for effect in sorted(effects, key=lambda item: item.horizon):
        priced = value_effect(effect, conservative_quotes, timing_adjustments)
        if priced is None:
            return None
        values[effect.horizon] = priced
    return values


def _public_snapshot(observation: Mapping[str, Any], opponent: int) -> dict[str, Any] | None:
    farms = observation.get("farms")
    if not isinstance(farms, list) or not (0 <= opponent < len(farms)) or not isinstance(farms[opponent], Mapping):
        return None
    farm = farms[opponent]
    market = observation.get("market") if isinstance(observation.get("market"), Mapping) else {}
    return {
        "step": observation.get("step"), "day": observation.get("day"), "hour": observation.get("hour"),
        "farmer": farm.get("farmer"), "hands": farm.get("hands"), "tiles": farm.get("tiles"),
        "market_inventory": market.get("inventory"),
    }


def _actors(snapshot: Mapping[str, Any]) -> list[tuple[int, tuple[int, int]]]:
    result: list[tuple[int, tuple[int, int]]] = []
    for index, raw in enumerate([snapshot.get("farmer"), *(snapshot.get("hands") or [])]):
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            try:
                result.append((index, (int(raw[0]), int(raw[1]))))
            except (TypeError, ValueError):
                pass
    return result


def _public_tile(snapshot: Mapping[str, Any], x: int, y: int) -> Mapping[str, Any] | None:
    tiles = snapshot.get("tiles")
    if not isinstance(tiles, list) or y < 0 or y >= len(tiles) or not isinstance(tiles[y], list) or x < 0 or x >= len(tiles[y]):
        return None
    item = tiles[y][x]
    return item if isinstance(item, Mapping) else None


def _distance_to_shed(position: tuple[int, int]) -> int:
    return min(abs(position[0] - x) + abs(position[1] - y) for x, y in SHED_TILES)


def update_public_inbound(state: Mapping[str, Any], observation: Mapping[str, Any], seat: int) -> dict[str, Any]:
    """Infer lower-bound opponent cargo using public consecutive farm snapshots only."""
    opponent = 1 - int(seat)
    current = _public_snapshot(observation, opponent)
    if current is None:
        return {"previous": None, "bounds": {}}
    previous = state.get("previous") if isinstance(state, Mapping) else None
    if not isinstance(previous, Mapping):
        return {"previous": current, "bounds": {}}
    bounds = dict(state.get("bounds") or {})
    if (
        not isinstance(current.get("step"), int)
        or current["step"] != previous.get("step", -2) + 1
        or current.get("day") != previous.get("day")
        or len(current.get("hands") or []) != len(previous.get("hands") or [])
    ):
        return {"previous": current, "bounds": {}}
    old_market, new_market = previous.get("market_inventory"), current.get("market_inventory")
    if isinstance(old_market, Mapping) and isinstance(new_market, Mapping) and any(
        int(new_market.get(product, 0) or 0) > int(old_market.get(product, 0) or 0) for product in set(old_market) | set(new_market)
    ):
        return {"previous": current, "bounds": {}}
    # The lower bound belongs to a public actor index.  Move its key with that
    # actor's consecutive public position so the stored distance cannot go stale.
    current_actors = dict(_actors(current))
    rekeyed: dict[str, dict[str, Any]] = {}
    for key, entry in bounds.items():
        try:
            actor = int(str(key).split(":", 1)[0])
        except (TypeError, ValueError):
            return {"previous": current, "bounds": {}}
        position = current_actors.get(actor)
        if position is None or not isinstance(entry, Mapping):
            return {"previous": current, "bounds": {}}
        new_key = f"{actor}:{position}"
        if new_key in rekeyed:
            return {"previous": current, "bounds": {}}
        moved = dict(entry)
        moved["distance_to_shed"] = _distance_to_shed(position)
        rekeyed[new_key] = moved
    bounds = rekeyed
    actors = _actors(previous)
    for y, row in enumerate(previous.get("tiles") or []):
        if not isinstance(row, list):
            continue
        for x, old in enumerate(row):
            new = _public_tile(current, x, y)
            if not isinstance(old, Mapping) or not isinstance(new, Mapping):
                continue
            old_yield, new_yield = old.get("yield_units"), new.get("yield_units")
            if not isinstance(old_yield, (int, float)) or not isinstance(new_yield, (int, float)) or new_yield >= old_yield:
                continue
            product = old.get("crop") if old.get("kind") == "PLANT" else PRODUCT_FROM_ANIMAL.get(old.get("animal"))
            occupants = [(actor, position) for actor, position in actors if position == (x, y)]
            if not isinstance(product, str) or len(occupants) != 1:
                return {"previous": current, "bounds": {}}
            actor, position = occupants[0]
            key = f"{actor}:{position}"
            entry = dict(bounds.get(key) or {})
            entry[product] = int(entry.get(product, 0) or 0) + int(old_yield - new_yield)
            entry["distance_to_shed"] = _distance_to_shed(position)
            bounds[key] = entry
    return {"previous": current, "bounds": bounds}


def stable_median_effect(effects: Sequence[HorizonEffect]) -> tuple[HorizonEffect, ...] | None:
    """Aggregate only same-signed, same-bucket effects observed at least twice."""
    if len(effects) < 2:
        return None
    grouped: dict[int, list[HorizonEffect]] = {}
    for effect in effects:
        grouped.setdefault(effect.horizon, []).append(effect)
    output: list[HorizonEffect] = []
    for horizon, rows in sorted(grouped.items()):
        if len(rows) < 2:
            return None
        contexts = [row.context for row in rows]
        if any(context is None for context in contexts) or len(set(contexts)) < 2:
            return None
        liquidatable = _median_bucket([row.liquidatable for row in rows])
        asset = _median_bucket([row.asset for row in rows])
        capacity = _median_bucket([row.capacity for row in rows])
        market = _median_market([row.market for row in rows])
        if liquidatable is None or asset is None or capacity is None or market is None:
            return None
        numeric_groups = [[row.cash_coins for row in rows]]
        for bucket_name in ("liquidatable", "asset", "capacity"):
            numeric_groups.extend(
                [[getattr(row, bucket_name)[index][1] for row in rows] for index in range(len(getattr(rows[0], bucket_name)))]
            )
        numeric_groups.extend(
            [[getattr(row.market[index], field) for row in rows] for index in range(len(rows[0].market)) for field in ("quantity", "control_offset", "candidate_offset")]
        )
        if any(not _same_sign(values) for values in numeric_groups if values):
            return None
        output.append(HorizonEffect(horizon, float(median(row.cash_coins for row in rows)), liquidatable, asset, capacity, market))
    return tuple(output)


def _same_sign(values: Iterable[float | int]) -> bool:
    return len({0 if value == 0 else (1 if value > 0 else -1) for value in values}) == 1


def _median_bucket(rows: Sequence[tuple[tuple[str, int, str], ...]]) -> tuple[tuple[str, int, str], ...] | None:
    """Median amounts while keeping bucket identity/provenance exact."""
    if not rows:
        return ()
    identity = tuple((product, provenance) for product, _quantity, provenance in rows[0])
    if any(tuple((product, provenance) for product, _quantity, provenance in row) != identity for row in rows):
        return None
    return tuple(
        (product, int(median(row[index][1] for row in rows)), provenance)
        for index, (product, provenance) in enumerate(identity)
    )


def _median_market(rows: Sequence[tuple[MarketShift, ...]]) -> tuple[MarketShift, ...] | None:
    if not rows:
        return ()
    identity = tuple((item.product, item.provenance) for item in rows[0])
    if any(tuple((item.product, item.provenance) for item in row) != identity for row in rows):
        return None
    if any(
        item.control_receipt is None or item.candidate_receipt is None
        for row in rows for item in row
    ):
        return None
    return tuple(
        MarketShift(
            product,
            int(median(row[index].quantity for row in rows)),
            int(median(row[index].control_offset for row in rows)),
            int(median(row[index].candidate_offset for row in rows)),
            provenance,
            float(median(row[index].control_receipt for row in rows)),
            float(median(row[index].candidate_receipt for row in rows)),
        )
        for index, (product, provenance) in enumerate(identity)
    )
