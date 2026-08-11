"""Streaming, resumable full-tape corpus collector for public Kaggriculture replays.

It pages the live leaderboard, selects one high-reward public episode per
leading team, downloads exactly one replay into an isolated one-file temporary
cache, immediately emits compressed canonical features/tapes, and removes only
that successful temporary file.  It never writes raw replay JSON into ``data/``
and never reads an opponent's private observation.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.competitions.types.competition_api_service import ApiGetLeaderboardRequest


ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parent
DEFAULT_CACHE = ROOT / "research" / "cache" / "full_tape_topology_scaleup_2026-08-10"
COMPETITION = "kaggriculture"
MAX_RAW_BYTES = 100 * 1024 * 1024
MAX_LEADERBOARD_PAGE = 200
ASSETS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "GOOSE", "COW", "SHEEP")
THREAD = threading.local()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def enum_name(value: Any) -> str:
    return getattr(value, "name", str(value).split(".")[-1])


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def api() -> KaggleApi:
    result = getattr(THREAD, "api", None)
    if result is None:
        result = KaggleApi()
        result.authenticate()
        THREAD.api = result
    return result


def retry(call, *args, **kwargs):
    for attempt in range(7):
        try:
            return call(*args, **kwargs)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status not in (429, 500, 502, 503, 504) or attempt == 6:
                raise
            time.sleep(min(2 ** (attempt + 1), 20))


def leaderboard_rows(candidate_limit: int) -> list[dict[str, Any]]:
    client = api()
    rows: list[dict[str, Any]] = []
    token = ""
    while len(rows) < candidate_limit:
        with client.build_kaggle_client() as kaggle:
            request = ApiGetLeaderboardRequest()
            request.competition_name = COMPETITION
            request.page_size = min(MAX_LEADERBOARD_PAGE, candidate_limit - len(rows))
            request.page_token = token
            response = retry(kaggle.competitions.competition_api_client.get_leaderboard, request)
        submissions = list(response.submissions or [])
        if not submissions:
            break
        for item in submissions:
            rows.append({
                "rank": len(rows) + 1,
                "team_id": int(item.team_id),
                "team_name": item.team_name,
                "leaderboard_score": str(item.score),
                "submission_date": iso(item.submission_date),
            })
            if len(rows) == candidate_limit:
                break
        token = str(response.next_page_token or "")
        if not token:
            break
    return rows


def team_metadata(row: dict[str, Any]) -> dict[str, Any]:
    client = api()
    submissions = list(retry(client.competition_team_submissions, row["team_id"]) or [])
    matches = [item for item in submissions if str(item.public_score) == row["leaderboard_score"]]
    if not matches:
        raise RuntimeError("no active submission matches live leaderboard score")
    matches.sort(key=lambda item: (item.date_submitted, item.id), reverse=True)
    submission = matches[0]
    episodes = list(retry(client.competition_list_episodes, submission.id) or [])
    candidates = []
    for episode in episodes:
        if enum_name(episode.state) != "COMPLETED" or enum_name(episode.type) != "EPISODE_TYPE_PUBLIC":
            continue
        agents = list(episode.agents or [])
        target = next((item for item in agents if int(item.submission_id) == int(submission.id)), None)
        if target is None:
            continue
        opponent = next((item for item in agents if item is not target), None)
        candidates.append({
            "episode_id": int(episode.id), "target_reward": float(target.reward), "target_agent_index": int(target.index),
            "create_time": iso(episode.create_time), "end_time": iso(episode.end_time),
            "opponent": {"team_id": int(opponent.team_id) if opponent else None, "team_name": opponent.team_name if opponent else None, "submission_id": int(opponent.submission_id) if opponent else None, "reward": float(opponent.reward) if opponent else None, "agent_index": int(opponent.index) if opponent else None},
        })
    candidates.sort(key=lambda item: (-item["target_reward"], item["episode_id"]))
    if not candidates:
        raise RuntimeError("matched submission has no completed public episode")
    return row | {
        "submission_id": int(submission.id), "submission_public_score": str(submission.public_score),
        "submission_created_at": iso(submission.date_submitted), "episode_candidates": candidates,
    }


def select_unique(records: list[dict[str, Any]], requested: int) -> list[dict[str, Any]]:
    used: set[int] = set()
    used_teams: set[int] = set()
    selected = []
    for record in sorted(records, key=lambda item: item["rank"]):
        # A leaderboard-view response can contain multiple rows for one team.
        # One team contributes one selected active-submission episode only.
        if int(record["team_id"]) in used_teams:
            continue
        index = next((i for i, candidate in enumerate(record["episode_candidates"]) if candidate["episode_id"] not in used), None)
        if index is None:
            continue
        episode = record["episode_candidates"][index]
        used.add(episode["episode_id"])
        used_teams.add(int(record["team_id"]))
        selected.append({key: value for key, value in record.items() if key != "episode_candidates"} | episode | {"team_reward_rank_within_submission": index + 1, "selection_reason": "highest_reward_unique_public_episode"})
        if len(selected) == requested:
            break
    return selected


def coverage(cache: Path, requested: int, candidate_limit: int, workers: int, metadata_batch: int = 0) -> dict[str, Any]:
    base = cache / "coverage"
    previous = {int(item["rank"]): item for item in read_jsonl(base / "team_metadata.jsonl") if item.get("status") == "ok"}
    previous_failures = read_jsonl(base / "metadata_failures.jsonl")
    rows = leaderboard_rows(candidate_limit)
    write_json(base / "leaderboard_snapshot.json", {"competition": COMPETITION, "captured_at": iso(datetime.now(timezone.utc)), "candidate_limit": candidate_limit, "rows": rows})
    missing = [row for row in rows if row["rank"] not in previous]
    if metadata_batch > 0:
        missing = missing[:metadata_batch]
    failures = []
    if missing:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(team_metadata, row): row for row in missing}
            for future in as_completed(futures):
                row = futures[future]
                try:
                    record = future.result()
                    append_jsonl(base / "team_metadata.jsonl", {"status": "ok", **record})
                    previous[record["rank"]] = record
                except Exception as exc:
                    failure = {"status": "failed", **row, "error": f"{type(exc).__name__}: {exc}"}
                    append_jsonl(base / "metadata_failures.jsonl", failure)
                    failures.append(failure)
    records = [previous[rank] for rank in sorted(previous) if rank <= len(rows)]
    selected = select_unique(records, requested)
    write_json(base / "selected_episodes.json", selected)
    report = {
        "captured_at": iso(datetime.now(timezone.utc)), "cache_absolute_path": str(cache.resolve()),
        "requested_replays": requested, "candidate_limit": candidate_limit, "leaderboard_rows_returned": len(rows),
        "metadata_ok": len(records), "metadata_failures_this_run": len(failures), "metadata_failures_total": len(previous_failures) + len(failures),
        "metadata_attempted_this_run": len(missing),
        "unique_selected_episodes": len(selected),
        "coverage_complete_for_requested": len(selected) >= requested,
        "blocker": None if len(selected) >= requested else "API metadata/episode availability yielded fewer unique selected public episodes than requested",
        "selection": "one live-score-matched active submission per team; highest target-reward completed public episode; unique episode IDs in rank order",
    }
    write_json(base / "coverage_report.json", report)
    return report


def checkpoint_selection(cache: Path, requested: int, candidate_limit: int) -> dict[str, Any]:
    """Materialize usable coverage after a rate-limited metadata pass, offline."""
    base = cache / "coverage"
    snapshot_path = base / "leaderboard_snapshot.json"
    if not snapshot_path.is_file():
        raise FileNotFoundError("no cached leaderboard snapshot")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rows = list(snapshot.get("rows", []))[:candidate_limit]
    available = {int(item["rank"]): item for item in read_jsonl(base / "team_metadata.jsonl") if item.get("status") == "ok"}
    records = [available[int(row["rank"])] for row in rows if int(row["rank"]) in available]
    selected = select_unique(records, requested)
    write_json(base / "selected_episodes.json", selected)
    report = {
        "captured_at": iso(datetime.now(timezone.utc)), "cache_absolute_path": str(cache.resolve()),
        "requested_replays": requested, "candidate_limit": candidate_limit,
        "leaderboard_rows_cached": len(rows), "metadata_ok": len(records),
        "unique_selected_episodes": len(selected), "coverage_complete_for_requested": len(selected) >= requested,
        "blocker": None if len(selected) >= requested else "partial cached metadata coverage; Kaggle API sweep must resume after rate-limit backoff",
        "selection": "offline selection from successfully checkpointed metadata only",
        "covered_ranks": sorted(int(item["rank"]) for item in records),
    }
    write_json(base / "coverage_report.json", report)
    return report


def canonical_action(value: Any) -> dict[str, Any]:
    action = value if isinstance(value, dict) else {}
    farmer = action.get("farmer", ["PASS"])
    hands = action.get("hands", [])
    market = action.get("market", [])
    return {
        "farmer": list(farmer or ["PASS"]),
        "hands": [list(row or ["PASS"]) for row in (hands or [])],
        "market": [list(row or []) for row in (market or [])],
    }


def unit_tape(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"farmer": action["farmer"], "hands": action["hands"]} for action in actions]


def market_tape(actions: list[dict[str, Any]]) -> list[list[Any]]:
    return [action["market"] for action in actions]


def public_signature(observation: dict[str, Any], seat: int) -> dict[str, Any]:
    farm = (observation.get("farms") or [])[seat]
    counts = {item: 0 for item in ASSETS}
    yields = {item: 0 for item in ASSETS}
    weeds = structures = 0
    for row in farm.get("tiles", []) or []:
        for tile in row or []:
            if not isinstance(tile, dict):
                continue
            item = str(tile.get("crop") or tile.get("animal") or "")
            if item in counts:
                counts[item] += 1
                yields[item] += int(tile.get("yield_units", 0) or 0)
            weeds += int(tile.get("kind") == "WEED")
            structures += int(tile.get("kind") in {"COOP", "PASTURE"})
    return {"day": int(observation.get("day", 0) or 0), "hour": int(observation.get("hour", 0) or 0), "land": len(farm.get("unlocked_quadrants", []) or []), "workers": len(farm.get("hands", []) or []), "assets": [counts[item] for item in ASSETS], "yields": [yields[item] for item in ASSETS], "weeds": weeds, "structures": structures}


def private_label(observation: dict[str, Any]) -> dict[str, int]:
    private = observation.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    seeds = private.get("seeds", {}) or {}
    inventories = private.get("inventories", []) or []
    return {"shed_load": sum(int(value or 0) for value in shed.values()), "seed_total": sum(int(value or 0) for value in seeds.values()), "carried": sum(sum(int(value or 0) for value in (bag or {}).values()) for bag in inventories)}


def macro_family(signatures: list[dict[str, Any]]) -> str:
    by_day = {int(item["day"]): item for item in signatures}
    landmarks = []
    for day in (0, 4, 6, 10, 14, 20, 28):
        item = by_day.get(day, signatures[-1])
        landmarks.append([item["land"], *item["assets"]])
    return digest(landmarks)


def extract_replay(raw: Path, selected: dict[str, Any], cache: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    size = raw.stat().st_size
    if size > MAX_RAW_BYTES:
        raise ValueError(f"raw replay exceeds {MAX_RAW_BYTES} byte safety limit")
    raw_hash = file_sha256(raw)
    with raw.open(encoding="utf-8") as handle:
        replay = json.load(handle)
    if int(replay.get("info", {}).get("EpisodeId", -1)) != int(selected["episode_id"]):
        raise ValueError("episode ID mismatch")
    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) != 720 or replay.get("statuses") != ["DONE", "DONE"]:
        raise ValueError("unexpected replay completion schema")
    seat = int(selected["target_agent_index"])
    if seat not in (0, 1):
        raise ValueError("unsupported target seat")
    actions = [canonical_action((step[seat].get("action") if isinstance(step[seat], dict) else None)) for step in steps[:-1]]
    if len(actions) != 719:
        raise ValueError("expected 719 meaningful actions")
    units, markets = unit_tape(actions), market_tape(actions)
    observations = [step[seat]["observation"] for step in steps]
    daily_indices = [min(day * 24, len(observations) - 1) for day in range(30)]
    signatures = [public_signature(observations[index], seat) for index in daily_indices]
    private = [private_label(observations[index]) for index in daily_indices]
    phase = []
    for start in range(0, 719, 24):
        end = min(start + 24, 719)
        phase.append({"start": start, "end": end, "full": digest(actions[start:end]), "unit": digest(units[start:end]), "market": digest(markets[start:end])})
    full_digest, unit_digest, market_digest = digest(actions), digest(units), digest(markets)
    tape_path = cache / "corpus" / "tapes" / f"{full_digest}.json.gz"
    if not tape_path.is_file():
        tape_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = tape_path.with_suffix(".tmp")
        with gzip.open(temporary, "wb", compresslevel=6) as handle:
            handle.write(canonical({"schema": 1, "actions": actions}))
        os.replace(temporary, tape_path)
    feature = {
        "schema": 1, "episode_id": int(selected["episode_id"]), "rank": int(selected["rank"]), "team_id": int(selected["team_id"]), "submission_id": int(selected["submission_id"]), "target_agent_index": seat,
        "raw": {"sha256": raw_hash, "bytes": size, "retained": False},
        "replay": {"seed": replay.get("info", {}).get("seed"), "module_version": replay.get("module_version"), "schema_version": replay.get("schema_version"), "target_reward": float(selected["target_reward"])},
        "tapes": {"full": full_digest, "unit": unit_digest, "market": market_digest, "full_tape_path": str(tape_path.relative_to(cache)), "turns": 719, "phases": phase},
        "route": {"family": macro_family(signatures), "daily_public_signatures": signatures, "daily_same_player_private_labels": private},
        "information_boundary": "Features access only target-player actions/observation. Private labels are from that player's private field only; no opponent private field is read.",
    }
    feature_path = cache / "corpus" / "features" / f"episode-{selected['episode_id']}.json.gz"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(feature_path, "wb", compresslevel=6) as handle:
        handle.write(canonical(feature))
    manifest = {key: value for key, value in selected.items() if key != "episode_candidates"} | {"feature_path": str(feature_path.relative_to(cache)), "full_tape": full_digest, "unit_tape": unit_digest, "market_tape": market_digest, "family": feature["route"]["family"], "raw_sha256": raw_hash, "raw_bytes": size, "module_version": feature["replay"]["module_version"], "seed": feature["replay"]["seed"]}
    return manifest, feature


def collect(cache: Path, max_downloads: int) -> dict[str, Any]:
    selected_path = cache / "coverage" / "selected_episodes.json"
    if not selected_path.is_file():
        raise FileNotFoundError("run --stage coverage before --stage collect")
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    manifest_path = cache / "corpus" / "manifest.jsonl"
    completed = {int(item["episode_id"]) for item in read_jsonl(manifest_path)}
    pending = [item for item in selected if int(item["episode_id"]) not in completed]
    if max_downloads > 0:
        pending = pending[:max_downloads]
    active = cache / "active_raw_one_file"
    active.mkdir(parents=True, exist_ok=True)
    failures_path = cache / "corpus" / "collection_failures.jsonl"
    processed = retained_invalid = 0
    for item in pending:
        raw = active / f"episode-{item['episode_id']}-replay.json"
        if raw.exists():
            raise RuntimeError(f"unexpected stale raw temporary file: {raw}")
        try:
            retry(api().competition_episode_replay, int(item["episode_id"]), path=str(active), quiet=True)
            manifest, _feature = extract_replay(raw, item, cache)
            append_jsonl(manifest_path, manifest)
            processed += 1
            raw.unlink()  # one successful temporary raw file, only after feature persistence
        except Exception as exc:
            retained = None
            if raw.exists():
                invalid_dir = cache / "retained_invalid_raw"
                invalid_dir.mkdir(parents=True, exist_ok=True)
                target = invalid_dir / raw.name
                os.replace(raw, target)
                retained = str(target.resolve())
                retained_invalid += 1
            append_jsonl(failures_path, {"selected": item, "error": f"{type(exc).__name__}: {exc}", "retained_invalid_raw": retained})
    return audit(cache) | {"processed_this_run": processed, "retained_invalid_raw_this_run": retained_invalid, "pending_after_run": max(0, len(selected) - len(read_jsonl(manifest_path)))}


def cluster(values: list[dict[str, Any]], key: str, label: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for value in values:
        groups[str(value[key])].append(value)
    return [{"id": f"{label}{index:04d}", "digest": name, "support": len(rows), "ranks": sorted(int(row["rank"]) for row in rows), "episodes": sorted(int(row["episode_id"]) for row in rows)[:32]} for index, (name, rows) in enumerate(sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])), start=1)]


def representatives(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep the best-ranked episode per team/submission for support metrics."""
    selected, duplicates = [], []
    seen_teams: set[int] = set()
    seen_submissions: set[int] = set()
    for row in sorted(rows, key=lambda item: (int(item["rank"]), int(item["episode_id"]))):
        team, submission = int(row["team_id"]), int(row["submission_id"])
        if team in seen_teams or submission in seen_submissions:
            duplicates.append(row)
            continue
        selected.append(row)
        seen_teams.add(team)
        seen_submissions.add(submission)
    return selected, duplicates


def audit(cache: Path) -> dict[str, Any]:
    rows = read_jsonl(cache / "corpus" / "manifest.jsonl")
    representative_rows, duplicate_rows = representatives(rows)
    report = {
        "cache_absolute_path": str(cache.resolve()), "replays_streamed": len(rows), "ranks_covered": sorted(int(item["rank"]) for item in rows),
        "unique_teams": len({int(item["team_id"]) for item in rows}), "unique_submissions": len({int(item["submission_id"]) for item in rows}), "unique_episodes": len({int(item["episode_id"]) for item in rows}),
        "analysis_representatives": len(representative_rows), "duplicate_team_or_submission_records_excluded_from_support": len(duplicate_rows), "analysis_representative_ranks": sorted(int(item["rank"]) for item in representative_rows),
        "raw_processed_bytes": sum(int(item["raw_bytes"]) for item in rows), "raw_retained_success_bytes": 0,
        "module_versions": dict(Counter(str(item.get("module_version")) for item in rows)),
        "full_tape_clusters": cluster(representative_rows, "full_tape", "F"), "unit_tape_clusters": cluster(representative_rows, "unit_tape", "U"), "market_tape_clusters": cluster(representative_rows, "market_tape", "M"), "route_family_clusters": cluster(representative_rows, "family", "R"),
        "split_protocol": {"random_transition_split_forbidden": True, "group_boundaries": ["team", "submission", "episode", "full_tape_family"], "temporal_boundary": "episode end_time recorded in selected metadata", "biases": ["selected-best-episode", "engine-version drift", "notebook-team identity unresolved"]},
        "information_boundary": "No cross-player private replay observation is extracted or stored.",
    }
    write_json(cache / "corpus" / "corpus_audit.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("coverage", "checkpoint", "collect", "audit"), required=True)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--requested-count", type=int, default=1500)
    parser.add_argument("--candidate-limit", type=int, default=1700)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-downloads", type=int, default=0)
    parser.add_argument("--metadata-batch", type=int, default=0, help="Bound missing team metadata requests in one rate-limit-aware pass; 0 means all.")
    args = parser.parse_args()
    if args.requested_count < 1 or args.candidate_limit < args.requested_count:
        parser.error("candidate limit must cover requested count")
    cache = args.cache.resolve()
    if args.stage == "coverage":
        result = coverage(cache, args.requested_count, args.candidate_limit, args.workers, args.metadata_batch)
    elif args.stage == "checkpoint":
        result = checkpoint_selection(cache, args.requested_count, args.candidate_limit)
    elif args.stage == "collect":
        result = collect(cache, args.max_downloads)
    else:
        result = audit(cache)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
