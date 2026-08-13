"""Exact current-engine transition audit for selected live source replays."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from kaggle.api.kaggle_api_extended import KaggleApi


ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parent
CACHE = ROOT / "research" / "cache" / "highscore_route_refresh_2026-08-13"
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_top50_replays as replay_audit  # noqa: E402
from replay_engine_versions import load_engine, verify_pinned_source  # noqa: E402


SELECTED_RANKS = (1, 3)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def action(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    return {
        "farmer": list(value.get("farmer") or ["PASS"]),
        "hands": [list(row or ["PASS"]) for row in (value.get("hands") or [])],
        "market": [list(row or []) for row in (value.get("market") or [])],
    }


def retry(call, *args, **kwargs):
    for attempt in range(7):
        try:
            return call(*args, **kwargs)
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status not in (429, 500, 502, 503, 504) or attempt == 6:
                raise
            time.sleep(min(2 ** (attempt + 1), 20))


def run(output: Path) -> dict[str, Any]:
    rows = {int(row["rank"]): row for row in read_jsonl(CACHE / "corpus" / "manifest.jsonl")}
    engine = load_engine("1.32.6", 813)
    api = KaggleApi()
    api.authenticate()
    active = CACHE / "active_transition_audit_one_file"
    active.mkdir(parents=True, exist_ok=True)
    summaries = []
    for rank in SELECTED_RANKS:
        entry = rows[rank]
        raw = active / f"episode-{entry['episode_id']}-replay.json"
        if raw.exists():
            raise RuntimeError(f"unexpected stale raw: {raw}")
        retry(api.competition_episode_replay, int(entry["episode_id"]), path=str(active), quiet=True)
        try:
            replay = json.loads(raw.read_text(encoding="utf-8"))
            for transition in range(1, 720):
                replay_audit._audit_transition(engine, replay, transition)
            seat = int(entry["target_agent_index"])
            aligned = [action(step[seat].get("action")) for step in replay["steps"][1:]]
            unaligned = [action(step[seat].get("action")) for step in replay["steps"][:-1]]
            aligned_sha256 = hashlib.sha256(canonical(aligned)).hexdigest()
            if aligned_sha256 != entry["full_tape"]:
                raise RuntimeError(f"aligned tape mismatch for rank {rank}")
            summaries.append({
                "rank": rank, "team_name": entry["team_name"], "episode_id": int(entry["episode_id"]),
                "module_version": replay.get("module_version"), "transitions_passed": 719,
                "aligned_mapping": "replay rows 1..719 map to observation steps 0..718",
                "aligned_full_tape_sha256": aligned_sha256,
                "manifest_full_tape_sha256": entry["full_tape"],
                "excluded_unaligned_full_tape_sha256": hashlib.sha256(canonical(unaligned)).hexdigest(),
                "first_aligned_action": aligned[0], "last_aligned_action": aligned[-1],
                "schema_safety": replay_audit._schema_safety(replay, seat),
                "asset_loss_safety": replay_audit._asset_loss_safety(replay, seat),
                "rewards": replay.get("rewards"), "statuses": replay.get("statuses"),
            })
        except Exception:
            retained = CACHE / "retained_invalid_raw"
            retained.mkdir(parents=True, exist_ok=True)
            os.replace(raw, retained / raw.name)
            raise
        else:
            raw.unlink()
    result = {
        "schema_version": 1, "engine": verify_pinned_source(),
        "raw_success_bytes_retained": 0,
        "information_boundary": "Private observations are used only inside same-transition correctness checks for their owning player and are not retained or compared across players.",
        "summaries": summaries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=LANE / "artifacts" / "selected_transition_audit.json")
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps(result["summaries"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
