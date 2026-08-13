"""Stream three source replays into compact public-only topology evidence."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any

from kaggle.api.kaggle_api_extended import KaggleApi


ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parent
CACHE = ROOT / "research" / "cache" / "highscore_route_refresh_2026-08-13"
SELECTED_RANKS = (1, 2, 3)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def retry(call, *args, **kwargs):
    for attempt in range(7):
        try:
            return call(*args, **kwargs)
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status not in (429, 500, 502, 503, 504) or attempt == 6:
                raise
            time.sleep(min(2 ** (attempt + 1), 20))


def public_tile(tile: Any) -> tuple[str, str] | None:
    if not isinstance(tile, dict):
        return None
    if tile.get("animal"):
        return "ANIMAL", str(tile["animal"])
    if tile.get("kind") == "PLANT":
        return "PLANT", str(tile.get("crop"))
    if tile.get("kind") in ("COOP", "PASTURE", "WEED"):
        return str(tile["kind"]), str(tile["kind"])
    return None


def topology(farm: dict[str, Any]) -> dict[str, list[list[int]]]:
    result: dict[str, list[list[int]]] = defaultdict(list)
    for y, row in enumerate(farm.get("tiles", []) or []):
        for x, tile in enumerate(row or []):
            found = public_tile(tile)
            if found is not None:
                result[found[1]].append([x, y])
    return {key: value for key, value in sorted(result.items())}


def tile_events(previous: dict[str, Any], current: dict[str, Any], day: int) -> list[dict[str, Any]]:
    events = []
    old_tiles = previous.get("tiles", []) or []
    new_tiles = current.get("tiles", []) or []
    for y, row in enumerate(old_tiles):
        for x, old in enumerate(row or []):
            new = new_tiles[y][x]
            if isinstance(old, dict) and old.get("animal"):
                if not (isinstance(new, dict) and new.get("animal") == old.get("animal")):
                    events.append({"type": "animal_escape", "asset": old.get("animal"), "x": x, "y": y})
            if (
                isinstance(old, dict) and old.get("kind") == "PLANT"
                and isinstance(new, dict) and new.get("kind") == "WEED"
            ):
                events.append({
                    "type": "crop_death", "asset": old.get("crop"), "x": x, "y": y,
                    "fresh": int(old.get("planted_day", -1000)) == int(day),
                })
    return events


def summarize(entry: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    seat = int(entry["target_agent_index"])
    records = [step[seat] for step in replay["steps"]]
    public_farms = [record["observation"]["farms"][seat] for record in records]
    positions = [
        {"farmer": list(farm.get("farmer", [])), "hands": [list(item) for item in farm.get("hands", []) or []]}
        for farm in public_farms
    ]
    events = []
    for step in range(1, len(public_farms)):
        day = int(records[step]["observation"].get("day", step // 24))
        for event in tile_events(public_farms[step - 1], public_farms[step], day):
            events.append({"step": step - 1, **event})
    landmarks = []
    for day in range(30):
        index = min(day * 24, len(records) - 1)
        farm = public_farms[index]
        landmarks.append({
            "day": day,
            "money": float(farm.get("money", 0)),
            "unlocked_quadrants": list(farm.get("unlocked_quadrants", []) or []),
            "farmer": list(farm.get("farmer", [])),
            "hands": [list(item) for item in farm.get("hands", []) or []],
            "topology": topology(farm),
        })
    event_counts = Counter(event["type"] for event in events)
    event_counts["fresh_crop_death"] = sum(event.get("fresh", False) for event in events)
    return {
        "rank": int(entry["rank"]), "team_name": entry["team_name"],
        "leaderboard_score": float(entry["leaderboard_score"]), "episode_id": int(entry["episode_id"]),
        "target_agent_index": seat, "seed": replay.get("info", {}).get("seed"),
        "module_version": replay.get("module_version"), "statuses": replay.get("statuses"),
        "rewards": replay.get("rewards"), "target_reward": float(entry["target_reward"]),
        "max_hands": max(len(farm.get("hands", []) or []) for farm in public_farms),
        "position_stream_sha256": hashlib.sha256(json.dumps(positions, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "public_asset_events": events,
        "public_asset_event_counts": dict(sorted(event_counts.items())),
        "daily_public_route": landmarks,
        "terminal_public_money": float(public_farms[-1].get("money", 0)),
    }


def run(output: Path) -> dict[str, Any]:
    rows = {int(row["rank"]): row for row in read_jsonl(CACHE / "corpus" / "manifest.jsonl")}
    api = KaggleApi()
    api.authenticate()
    active = CACHE / "active_source_audit_one_file"
    active.mkdir(parents=True, exist_ok=True)
    summaries = []
    for rank in SELECTED_RANKS:
        entry = rows[rank]
        raw = active / f"episode-{entry['episode_id']}-replay.json"
        if raw.exists():
            raise RuntimeError(f"unexpected stale raw file: {raw}")
        retry(api.competition_episode_replay, int(entry["episode_id"]), path=str(active), quiet=True)
        try:
            replay = json.loads(raw.read_text(encoding="utf-8"))
            if int(replay.get("info", {}).get("EpisodeId", -1)) != int(entry["episode_id"]):
                raise ValueError("episode mismatch")
            if len(replay.get("steps", [])) != 720 or replay.get("statuses") != ["DONE", "DONE"]:
                raise ValueError("invalid replay completion")
            summaries.append(summarize(entry, replay))
        except Exception:
            retained = CACHE / "retained_invalid_raw"
            retained.mkdir(parents=True, exist_ok=True)
            os.replace(raw, retained / raw.name)
            raise
        else:
            raw.unlink()
    result = {
        "schema_version": 1,
        "selected_ranks": list(SELECTED_RANKS),
        "raw_success_bytes_retained": 0,
        "information_boundary": "Only target-player actions and public farm state are read. No private observation field from either player is accessed.",
        "summaries": summaries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=LANE / "artifacts" / "selected_source_public_routes.json")
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps([
        {key: row[key] for key in ("rank", "team_name", "max_hands", "public_asset_event_counts", "terminal_public_money")}
        for row in result["summaries"]
    ], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
