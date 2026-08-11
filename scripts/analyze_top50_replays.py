"""Audit and summarize the retained Kaggriculture top-50 replay snapshot.

This analysis deliberately separates issued market quantities from quantities
that the engine actually executes.  Each transition is replayed with the
recorded engine-version semantics and compared to the official next state.
Private observations are used only to audit the same player; route clustering
uses public farms, actions, market/town state, and rewards.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from replay_engine_versions import VERSION_COMMITS, VENDOR_ROOT, load_engine, make_env_stub, verify_pinned_source


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT.parent / "Kaggriculture-archive" / "2026-08-10"
DEFAULT_DATASET = ROOT / "data" / "public_replays" / "top50-2026-08-09"
DEFAULT_REPLAY_ROOT = ARCHIVE_ROOT / "data" / "public_replays" / "top50-2026-08-09"
DEFAULT_OUTPUT = ARCHIVE_ROOT / "reports" / "replay_clone_study"
ASSETS = ("GOOSE", "COW", "SHEEP", "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def _jsonable(value):
    return json.loads(json.dumps(value, separators=(",", ":")))


def _hash_json(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _tile_counts(farm):
    counts = Counter()
    coords = defaultdict(list)
    for y, row in enumerate(farm.get("tiles", [])):
        for x, tile in enumerate(row):
            if not isinstance(tile, dict):
                continue
            if tile.get("animal"):
                item = tile["animal"]
            elif tile.get("kind") == "PLANT":
                item = tile["crop"]
            elif tile.get("kind") == "WEED":
                item = "WEED"
            elif tile.get("kind") in ("COOP", "PASTURE"):
                item = "EMPTY_" + tile["kind"]
            else:
                continue
            counts[item] += 1
            coords[item].append([x, y])
    return counts, coords


def _inventory_load(private):
    shed = sum(int(v) for v in private.get("shed", {}).values())
    carried = sum(sum(int(v) for v in inv.values()) for inv in private.get("inventories", []))
    return shed, carried


def _market_key(op, item=None):
    return op if not item else f"{op}:{item}"


def _requested_market(action):
    totals = Counter()
    positions = Counter()
    for index, order in enumerate((action or {}).get("market", []) or []):
        if not isinstance(order, list) or not order:
            continue
        op = order[0]
        item = order[1] if len(order) > 1 else None
        key = _market_key(op, item)
        positions[f"{key}@{index}"] += 1
        if op in ("HIRE", "BUY_LAND"):
            totals[key] += 1
        elif op in ("SELL", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL") and len(order) >= 3:
            try:
                totals[key] += max(0, int(order[2]))
            except (TypeError, ValueError):
                totals[f"MALFORMED:{key}"] += 1
    return totals, positions


def _inventory_orders(data, transition_index, player):
    """Recover inventory insertion order lost by replay JSON key sorting.

    End-of-day overflow is item-order dependent.  A unit action can introduce
    only one inventory item, so presence changes across same-day observations
    recover the original dict order exactly without using the other player's
    private data.
    """
    previous_index = transition_index - 1
    start = (previous_index // 24) * 24
    orders = []
    for index in range(start, transition_index):
        inventories = data["steps"][index][player]["observation"].get("private", {}).get("inventories", [])
        if len(orders) > len(inventories):
            orders = orders[:len(inventories)]
        while len(orders) < len(inventories):
            orders.append([])
        for unit, inventory in enumerate(inventories):
            present = {item for item, count in inventory.items() if count > 0}
            orders[unit] = [item for item in orders[unit] if item in present]
            for item, count in inventory.items():
                if count > 0 and item not in orders[unit]:
                    orders[unit].append(item)
    return orders


def _build_state(data, transition_index):
    if str(VENDOR_ROOT) not in sys.path:
        sys.path.insert(0, str(VENDOR_ROOT))
    from kaggle_environments.utils import structify

    state = []
    for player in range(len(data["steps"][transition_index])):
        record = copy.deepcopy(data["steps"][transition_index - 1][player])
        inventories = record.get("observation", {}).get("private", {}).get("inventories", [])
        for inventory, order in zip(inventories, _inventory_orders(data, transition_index, player)):
            reordered = {item: inventory[item] for item in order if item in inventory}
            reordered.update({item: count for item, count in inventory.items() if item not in reordered})
            inventory.clear()
            inventory.update(reordered)
        record["action"] = copy.deepcopy(data["steps"][transition_index][player].get("action"))
        state.append(structify(record))
    return state


def _audit_transition(engine, data, transition_index):
    """Replay one transition and return exact executed market units."""
    state = _build_state(data, transition_index)
    env = make_env_stub(data["configuration"], data["info"]["seed"])
    farms = state[0].observation["farms"]
    player_by_farm = {id(farm): player for player, farm in enumerate(farms)}
    trace = []

    original_commit = engine._commit_unit
    original_hire = engine._do_hire
    original_land = engine._do_buy_land

    def traced_commit(op, item, price, farm, private, market, shed_capacity=100):
        ok = original_commit(op, item, price, farm, private, market, shed_capacity)
        if ok:
            trace.append({
                "player": player_by_farm[id(farm)],
                "op": op,
                "item": item,
                "quantity": 1,
                "coins": float(price),
            })
        return ok

    def traced_hire(farm, private, board_size, mult=engine.FARM_HAND_COST_MULT):
        before_money = float(farm["money"])
        before_hires = int(farm["hires_today"])
        original_hire(farm, private, board_size, mult)
        if int(farm["hires_today"]) > before_hires:
            trace.append({
                "player": player_by_farm[id(farm)], "op": "HIRE", "item": None,
                "quantity": 1, "coins": before_money - float(farm["money"]),
            })

    def traced_land(farm, board_size):
        before_money = float(farm["money"])
        before_land = len(farm["unlocked_quadrants"])
        original_land(farm, board_size)
        if len(farm["unlocked_quadrants"]) > before_land:
            trace.append({
                "player": player_by_farm[id(farm)], "op": "BUY_LAND", "item": None,
                "quantity": 1, "coins": before_money - float(farm["money"]),
            })

    engine._commit_unit = traced_commit
    engine._do_hire = traced_hire
    engine._do_buy_land = traced_land
    try:
        output = engine.interpreter(state, env)
    finally:
        engine._commit_unit = original_commit
        engine._do_hire = original_hire
        engine._do_buy_land = original_land

    compared = ("day", "hour", "farms", "market", "town", "private")
    for player, result in enumerate(output):
        predicted = _jsonable(result.observation)
        expected = data["steps"][transition_index][player]["observation"]
        mismatches = [key for key in compared if predicted.get(key) != expected.get(key)]
        if mismatches:
            raise RuntimeError(
                f"transition mismatch episode={data.get('id')} step={transition_index} "
                f"player={player} fields={mismatches}"
            )
    return trace


def _schema_safety(data, player):
    malformed = 0
    market_overflow = 0
    seed_overcommit = 0
    for index in range(1, len(data["steps"])):
        record = data["steps"][index][player]
        action = record.get("action")
        pre = data["steps"][index - 1][player]["observation"]
        hand_count = len(pre["farms"][player].get("hands", []))
        if not isinstance(action, dict):
            malformed += 1
            continue
        if set(action) != {"farmer", "hands", "market"}:
            malformed += 1
        hands = action.get("hands", [])
        market = action.get("market", [])
        if not isinstance(hands, list) or len(hands) != hand_count:
            malformed += 1
        if not isinstance(market, list):
            malformed += 1
            market = []
        if len(market) > 10:
            market_overflow += 1
        units = [action.get("farmer", ["PASS"]), *hands]
        demand = Counter(
            unit[1] for unit in units
            if isinstance(unit, list) and len(unit) >= 2 and unit[0] == "PLANT"
        )
        seeds = pre.get("private", {}).get("seeds", {})
        seed_overcommit += sum(1 for crop, amount in demand.items() if amount > seeds.get(crop, 0))
    return {
        "malformed_actions": malformed,
        "market_overflow_turns": market_overflow,
        "seed_overcommit_turns": seed_overcommit,
    }


def _asset_loss_safety(data, player):
    escapes = 0
    fresh_crop_deaths = 0
    overflow_states = 0
    for index in range(1, len(data["steps"])):
        pre = data["steps"][index - 1][player]["observation"]
        post = data["steps"][index][player]["observation"]
        pre_tiles = pre["farms"][player]["tiles"]
        post_tiles = post["farms"][player]["tiles"]
        for y, row in enumerate(pre_tiles):
            for x, tile in enumerate(row):
                after = post_tiles[y][x]
                if isinstance(tile, dict) and tile.get("animal"):
                    if not (isinstance(after, dict) and after.get("animal") == tile.get("animal")):
                        escapes += 1
                if (
                    isinstance(tile, dict) and tile.get("kind") == "PLANT"
                    and tile.get("planted_day") == pre.get("day")
                    and isinstance(after, dict) and after.get("kind") == "WEED"
                ):
                    fresh_crop_deaths += 1
        if sum(post.get("private", {}).get("shed", {}).values()) > 100:
            overflow_states += 1
    return {
        "animal_escapes": escapes,
        "fresh_crop_deaths": fresh_crop_deaths,
        "shed_overflow_states": overflow_states,
    }


def summarize_entry(entry, data, engine, audit_transitions=True):
    player = int(entry["target_agent_index"])
    steps = data["steps"]
    peak = Counter()
    tile_observations = Counter()
    first_day = {}
    land_days = []
    last_land = 1
    max_hands = 0
    hands_by_day = Counter()
    daily_last = {}
    requested = Counter()
    request_positions = Counter()
    executed = Counter()
    executed_coins = Counter()
    unit_stream = []
    market_shape_stream = []

    for index, all_records in enumerate(steps):
        record = all_records[player]
        obs = record["observation"]
        farm = obs["farms"][player]
        day = int(obs.get("day", index // 24))
        counts, coords = _tile_counts(farm)
        peak |= counts
        for asset in ASSETS:
            tile_observations[asset] += counts[asset]
            if counts[asset] and asset not in first_day:
                first_day[asset] = day
        hands = len(farm.get("hands", []))
        max_hands = max(max_hands, hands)
        hands_by_day[day] = max(hands_by_day[day], hands)
        land = len(farm.get("unlocked_quadrants", []))
        if land > last_land:
            land_days.extend([day] * (land - last_land))
            last_land = land
        shed, carried = _inventory_load(obs.get("private", {}))
        daily_last[day] = {
            "day": day,
            "money": float(farm.get("money", 0)),
            "land": land,
            "hands": hands_by_day[day],
            "assets": {asset: counts[asset] for asset in ASSETS if counts[asset]},
            "weeds": counts["WEED"],
            "shed": shed,
            "carried": carried,
            "topology": {asset: coords[asset] for asset in (*ASSETS, "WEED") if coords[asset]},
        }
        if index == 0:
            continue
        action = record.get("action") or {}
        totals, positions = _requested_market(action)
        requested.update(totals)
        request_positions.update(positions)
        unit_stream.append([action.get("farmer"), action.get("hands")])
        market_shape_stream.append([
            [order[0], order[1] if len(order) > 1 else None]
            for order in action.get("market", []) or []
            if isinstance(order, list) and order
        ])
        if audit_transitions:
            for event in _audit_transition(engine, data, index):
                if event["player"] != player:
                    continue
                key = _market_key(event["op"], event["item"])
                executed[key] += event["quantity"]
                executed_coins[key] += event["coins"]

    final_private = steps[-1][player]["observation"].get("private", {})
    terminal_shed = {key: value for key, value in final_private.get("shed", {}).items() if value}
    terminal_carried = Counter()
    for inventory in final_private.get("inventories", []):
        terminal_carried.update(inventory)
    safety = _schema_safety(data, player)
    safety.update(_asset_loss_safety(data, player))
    macro_fingerprint = {
        "land_days": land_days,
        "max_hands": max_hands,
        "peak_assets": [peak[asset] for asset in ASSETS],
        "first_days": [first_day.get(asset) for asset in ASSETS],
    }
    return {
        "rank": entry["rank"],
        "team_name": entry["team_name"],
        "leaderboard_score": float(entry["leaderboard_score"]),
        "episode_id": entry["episode_id"],
        "module_version": entry["module_version"],
        "source_commit": VERSION_COMMITS[entry["module_version"]],
        "target_player": player,
        "reward": float(entry["target_reward"]),
        "opponent_reward": float(entry["opponent"]["reward"]),
        "won_selected_episode": bool(entry["target_reward"] > entry["opponent"]["reward"]),
        "land_unlock_days": land_days,
        "max_hands": max_hands,
        "hands_by_day": {str(day): hands_by_day[day] for day in sorted(hands_by_day)},
        "peak_assets": {asset: peak[asset] for asset in ASSETS},
        "tile_days": {asset: round(tile_observations[asset] / 24.0, 3) for asset in ASSETS},
        "first_asset_days": first_day,
        "daily": [daily_last[day] for day in sorted(daily_last)],
        "requested_market": dict(sorted(requested.items())),
        "executed_market": dict(sorted(executed.items())),
        "executed_market_coins": {key: round(value, 3) for key, value in sorted(executed_coins.items())},
        "market_request_positions": dict(sorted(request_positions.items())),
        "unit_action_sha256": _hash_json(unit_stream),
        "market_shape_sha256": _hash_json(market_shape_stream),
        "macro_fingerprint": macro_fingerprint,
        "macro_fingerprint_sha256": _hash_json(macro_fingerprint),
        "terminal_shed": terminal_shed,
        "terminal_carried": dict(terminal_carried),
        "safety": safety,
    }


def _replay_path(dataset, replay_root, entry):
    local_path = dataset / entry["file"]
    if local_path.is_file():
        return local_path
    return replay_root / entry["file"]


def verify_dataset(dataset, replay_root, manifest, verify_checksums=True):
    entries = manifest.get("entries", [])
    if len(entries) != 50 or manifest.get("downloaded_count") != 50:
        raise RuntimeError(f"expected fixed 50-entry snapshot, got {len(entries)} entries")
    total = 0
    for entry in entries:
        path = _replay_path(dataset, replay_root, entry)
        if not path.is_file():
            raise FileNotFoundError(path)
        size = path.stat().st_size
        if size != entry["bytes"]:
            raise RuntimeError(f"byte-size mismatch for {path.name}: {size} != {entry['bytes']}")
        total += size
        if verify_checksums:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest.lower() != entry["sha256"].lower():
                raise RuntimeError(f"checksum mismatch for {path.name}")
    if total != manifest.get("total_bytes"):
        raise RuntimeError(f"dataset total-byte mismatch: {total} != {manifest.get('total_bytes')}")
    return {"entries": len(entries), "total_bytes": total, "checksums_verified": bool(verify_checksums)}


def _cluster_rows(summaries, key):
    grouped = defaultdict(list)
    for row in summaries:
        grouped[row[key]].append(row)
    clusters = []
    for digest, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        rewards = [member["reward"] for member in members]
        scores = [member["leaderboard_score"] for member in members]
        clusters.append({
            "sha256": digest,
            "count": len(members),
            "ranks": [member["rank"] for member in members],
            "wins_in_selected_episodes": sum(member["won_selected_episode"] for member in members),
            "reward_median": statistics.median(rewards),
            "reward_min": min(rewards),
            "reward_max": max(rewards),
            "leaderboard_score_median": statistics.median(scores),
        })
    return clusters


def _selected_route_specs(summaries):
    by_rank = {row["rank"]: row for row in summaries}
    selected = {
        "dominant_8c6s": by_rank[24],
        "rank1_fullmap_10c11s": by_rank[1],
        "cow_heavy_12c2s": by_rank[33],
    }
    out = {}
    for name, row in selected.items():
        out[name] = {
            "source_rank": row["rank"],
            "source_team": row["team_name"],
            "source_episode": row["episode_id"],
            "module_version": row["module_version"],
            "land_unlock_days": row["land_unlock_days"],
            "peak_assets": row["peak_assets"],
            "hands_by_day": row["hands_by_day"],
            "daily": row["daily"],
            "requested_market": row["requested_market"],
            "executed_market": row["executed_market"],
            "information_boundary": "private fields audit only the same player; route fields are public",
        }
    return out


def _analysis_markdown(result):
    macro = result["clusters"]["macro"]
    unit = result["clusters"]["unit_action"]
    selected = result["route_specs"]
    lines = [
        "# Top-50 公開回放策略分析（2026-08-09）",
        "",
        "## 結論",
        "",
        f"- 固定資料集含 {result['dataset_validation']['entries']} 場、"
        f"{result['dataset_validation']['total_bytes']:,} bytes；全部為 720-step DONE/DONE 回放。",
        f"- 最大宏觀群有 {macro[0]['count']}/50 個完全相同指紋；最大逐回合 unit-action 群有 "
        f"{unit[0]['count']}/50 個完全相同序列。",
        "- 這證明路線在榜上高度普及，但每隊樣本都是該 submission 的最高 reward 單場，不能視為勝率或期望 reward。",
        "- 市場統計使用官方 interpreter 實際成交量，不把未成交的大額 request 納入產能或收益。",
        "",
        "## 凍結研究路線",
        "",
    ]
    for name, spec in selected.items():
        peaks = spec["peak_assets"]
        lines.append(
            f"- `{name}`：Rank {spec['source_rank']} / episode {spec['source_episode']}；"
            f"COW {peaks['COW']}、SHEEP {peaks['SHEEP']}、STRAWBERRY {peaks['STRAWBERRY']}、"
            f"MELON {peaks['MELON']}；買地日 {spec['land_unlock_days']}。"
        )
    lines += [
        "",
        "## 正確性與資訊界線",
        "",
        f"- Transition audit：{result['transition_audit']['episodes_passed']}/"
        f"{result['transition_audit']['episodes_requested']} episodes 通過；"
        f"money／market／farm／same-player private mismatch 均為 0。",
        "- 兩位玩家 private observation 只各自用於 transition correctness；跨玩家分群未使用 shed、seeds 或 inventories。",
        "- 1.32.4、1.32.5、1.32.6 依回放 module version 使用對應官方語意。",
        "",
        "## 研究限制",
        "",
        "- Rank 1 與 Rank 33 各只有一個目標樣本，屬可重現候選，不是已證實最優策略。",
        "- 複製代理採閉環 route goals、P0/P1 安全與合法性投影，不把原始 action tape 當 runtime 策略。",
        "- 競爭效果必須由 fresh seeds、雙座位、保留所有 losses 的官方引擎矩陣另行判斷。",
        "",
    ]
    return "\n".join(lines)


def run(dataset, replay_root, output, verify_checksums=True, audit_transitions=True, limit=None):
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    validation = verify_dataset(dataset, replay_root, manifest, verify_checksums)
    engine_info = verify_pinned_source()
    entries = manifest["entries"][:limit] if limit else manifest["entries"]
    engines = {version: load_engine(version, index) for index, version in enumerate(sorted({e["module_version"] for e in entries}))}
    summaries = []
    for index, entry in enumerate(entries, 1):
        path = _replay_path(dataset, replay_root, entry)
        data = json.loads(path.read_text(encoding="utf-8"))
        if len(data.get("steps", [])) != 720 or data.get("statuses") != ["DONE", "DONE"]:
            raise RuntimeError(f"invalid terminal replay shape: {path.name}")
        summary = summarize_entry(entry, data, engines[entry["module_version"]], audit_transitions)
        summaries.append(summary)
        print(
            f"[{index:02d}/{len(entries):02d}] rank={entry['rank']} episode={entry['episode_id']} "
            f"version={entry['module_version']} reward={entry['target_reward']:.0f}",
            flush=True,
        )
    result = {
        "dataset": manifest.get("dataset"),
        "captured_at": manifest.get("captured_at"),
        "dataset_validation": validation,
        "engine": engine_info,
        "transition_audit": {
            "enabled": bool(audit_transitions),
            "episodes_requested": len(entries),
            "episodes_passed": len(entries) if audit_transitions else 0,
            "money_mismatches": 0,
            "market_mismatches": 0,
            "farm_mismatches": 0,
            "same_player_private_mismatches": 0,
            "audit_errors": 0,
        },
        "clusters": {
            "macro": _cluster_rows(summaries, "macro_fingerprint_sha256"),
            "unit_action": _cluster_rows(summaries, "unit_action_sha256"),
            "market_shape": _cluster_rows(summaries, "market_shape_sha256"),
        },
        "summaries": summaries,
    }
    if len(entries) >= 33:
        result["route_specs"] = _selected_route_specs(summaries)
    else:
        result["route_specs"] = {}
    output.mkdir(parents=True, exist_ok=True)
    (output / "top50_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "route_specs.json").write_text(
        json.dumps(result["route_specs"], indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if result["route_specs"]:
        (output / "analysis.md").write_text(_analysis_markdown(result), encoding="utf-8")
    return result


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--replay-root", type=Path, default=DEFAULT_REPLAY_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-checksums", action="store_true")
    parser.add_argument("--skip-transition-audit", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        args.dataset.resolve(), args.replay_root.resolve(), args.output.resolve(),
        verify_checksums=not args.skip_checksums,
        audit_transitions=not args.skip_transition_audit,
        limit=args.limit,
    )
