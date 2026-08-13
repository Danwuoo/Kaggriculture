"""Build deterministic, standalone research-only replay-tape agents."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import zlib


ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parent
CACHE_ROOT = ROOT / "research" / "cache" / "highscore_route_refresh_2026-08-13"
CACHE = CACHE_ROOT / "corpus" / "tapes"
SHARED_UNIT = "7a200e767030483fb65faeb4060ac4b6bc6580b9ca493180d067c43fdd07ca30"
CANDIDATES = {
    "rank1_10c4s": {"tape": "b7d8875565704bc04c4c03fefe4ccbc92f170a251dd9cb8f224624769e9f5464", "guarded": False},
    "dominant_8c4s": {"tape": "59e6cf8aa76737b50cf27e3059bb75d6095b88f8e93e70a888487ca5c63efd0c", "guarded": False},
}


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def specifications() -> dict[str, dict[str, object]]:
    result = {name: dict(value) for name, value in CANDIDATES.items()}
    manifest = [
        json.loads(line)
        for line in (CACHE_ROOT / "corpus" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in sorted(manifest, key=lambda item: int(item["rank"])):
        if row["unit_tape"] != SHARED_UNIT:
            continue
        result[f"shared_guarded_r{int(row['rank']):02d}"] = {
            "tape": row["full_tape"], "guarded": True, "rank": int(row["rank"]),
            "team_name": row["team_name"], "leaderboard_score": float(row["leaderboard_score"]),
            "unit_tape": row["unit_tape"], "market_tape": row["market_tape"],
        }
    return result


def render(name: str, tape_sha256: str, guarded: bool) -> str:
    with gzip.open(CACHE / f"{tape_sha256}.json.gz", "rt", encoding="utf-8") as stream:
        actions = json.load(stream)["actions"]
    if len(actions) != 719 or hashlib.sha256(canonical(actions)).hexdigest() != tape_sha256:
        raise ValueError(f"invalid source tape: {name}")
    encoded = base64.b64encode(zlib.compress(canonical(actions), level=9)).decode("ascii")
    guard_helpers = r'''
def _at(farm, position):
    try:
        x, y = int(position[0]), int(position[1])
        return farm.get("tiles", [])[y][x]
    except (IndexError, TypeError, ValueError):
        return "LOCKED"

def _route_actor(step, index):
    source = _ACTIONS[min(max(0, int(step)), 718)]
    units = [source.get("farmer") or ["PASS"], *(source.get("hands") or [])]
    return list(units[index] if index < len(units) else ["PASS"])

def _guard(obs, step, seat, action, state):
    farm = obs["farms"][seat]
    positions = [farm.get("farmer"), *(farm.get("hands", []) or [])]
    units = [action["farmer"], *action["hands"]]
    active = state["active"]
    for index, transaction in list(active.items()):
        if index >= len(units):
            active.pop(index, None)
            continue
        age = step - transaction["start"]
        if age == 1:
            units[index] = list(transaction["intended"])
        elif 2 <= age <= 9:
            units[index] = _route_actor(step - 1, index)
        else:
            active.pop(index, None)
    for index, (position, intended) in enumerate(zip(positions, units)):
        if index in active or not intended or intended[0] not in ("BUILD_PASTURE", "PLANT"):
            continue
        tile = _at(farm, position)
        if isinstance(tile, dict) and tile.get("kind") == "WEED":
            active[index] = {"start": step, "intended": list(intended)}
            units[index] = ["DIG"]
            state["weed_repairs"] += 1
    seeds = (obs.get("private", {}) or {}).get("seeds", {}) or {}
    used = {}
    for index, intended in enumerate(units):
        if not intended or intended[0] != "PLANT" or len(intended) < 2:
            continue
        crop = str(intended[1])
        count = used.get(crop, 0)
        if count >= max(0, int(seeds.get(crop, 0) or 0)):
            units[index] = ["PASS"]
            state["seed_trims"] += 1
        else:
            used[crop] = count + 1
    action["farmer"] = units[0]
    action["hands"] = units[1:]
    return action
'''
    helpers = guard_helpers if guarded else ""
    guard_call = "    action = _guard(obs, step, seat, action, state)\n" if guarded else ""
    reset_fields = ', "active": {}, "weed_repairs": 0, "seed_trims": 0' if guarded else ""
    return f'''"""Generated research-only high-score route transplant: {name}."""
import base64
import json
import zlib

_TAPE_SHA256 = "{tape_sha256}"
_ACTIONS = json.loads(zlib.decompress(base64.b64decode("{encoded}")))
_STATE = {{0: {{}}, 1: {{}}}}
{helpers}

def stats(seat=None):
    if seat is None:
        return {{key: dict(value) for key, value in _STATE.items()}}
    return dict(_STATE.get(seat, {{}}))

def agent(obs, configuration=None):
    step = min(max(0, int(obs.get("step", 0) or 0)), 718)
    seat = int(obs.get("player", 0) or 0)
    state = _STATE.get(seat, {{}})
    if step == 0 or step < state.get("last_step", -1):
        state = {{"last_step": step, "alignment_changes": 0{reset_fields}}}
        _STATE[seat] = state
    state["last_step"] = step
    source = _ACTIONS[step]
    expected = len(obs["farms"][seat].get("hands", []) or [])
    hands = [list(row or ["PASS"]) for row in (source.get("hands", []) or [])]
    if len(hands) != expected:
        state["alignment_changes"] += 1
        hands = (hands + [["PASS"] for _ in range(max(0, expected - len(hands)))])[:expected]
    action = {{
        "farmer": list(source.get("farmer") or ["PASS"]),
        "hands": hands,
        "market": [list(row or []) for row in (source.get("market", []) or [])][:10],
    }}
{guard_call}    return action
'''


def build(check: bool) -> dict[str, dict[str, str | int]]:
    result = {}
    for name, spec in specifications().items():
        tape = str(spec["tape"])
        guarded = bool(spec["guarded"])
        path = LANE / "candidates" / name / "main.py"
        content = render(name, tape, guarded)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"stale generated artifact: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        raw = content.encode("utf-8")
        result[name] = {
            "path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "source_tape_sha256": tape, **spec,
        }
    if not check:
        manifest = LANE / "artifacts" / "candidate_manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(args.check), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
