"""Collect one high-reward public replay for each leading Kaggriculture team.

The selection is based on one fixed leaderboard snapshot.  For each team, the
script identifies the active submission whose public score matches the snapshot,
then chooses that team's highest-reward completed public episode.  Episode IDs
are kept unique in leaderboard order; a later team uses its next-best episode if
its best game was already selected for an earlier team.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_BASE = ROOT / "data" / "public_replays"
_THREAD_LOCAL = threading.local()


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _enum_name(value):
    return getattr(value, "name", str(value).split(".")[-1])


def _api():
    api = getattr(_THREAD_LOCAL, "api", None)
    if api is None:
        api = KaggleApi()
        api.authenticate()
        _THREAD_LOCAL.api = api
    return api


def _retry(call, *args, **kwargs):
    for attempt in range(7):
        try:
            return call(*args, **kwargs)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status not in (429, 500, 502, 503, 504) or attempt == 6:
                raise
            delay = min(2 ** (attempt + 1), 20)
            print(f"Kaggle API returned {status}; retrying in {delay}s", flush=True)
            time.sleep(delay)


def _leaderboard_snapshot(competition, candidate_limit):
    api = KaggleApi()
    api.authenticate()
    rows = _retry(api.competition_leaderboard_view, competition, page_size=candidate_limit)
    result = []
    for rank, row in enumerate(rows or [], start=1):
        result.append(
            {
                "rank": rank,
                "team_id": int(row.team_id),
                "team_name": row.team_name,
                "leaderboard_score": row.score,
                "submission_date": _iso(row.submission_date),
            }
        )
    return result


def _matching_submission(api, row):
    submissions = list(_retry(api.competition_team_submissions, row["team_id"]) or [])
    exact = [submission for submission in submissions if str(submission.public_score) == str(row["leaderboard_score"])]
    if not exact:
        raise RuntimeError(
            f"no active submission score matches leaderboard score {row['leaderboard_score']}; "
            f"active scores={[str(s.public_score) for s in submissions]}"
        )
    exact.sort(key=lambda submission: (submission.date_submitted, submission.id), reverse=True)
    return exact[0]


def _episode_candidates(row):
    api = _api()
    submission = _matching_submission(api, row)
    episodes = list(_retry(api.competition_list_episodes, submission.id) or [])
    candidates = []
    for episode in episodes:
        if _enum_name(episode.state) != "COMPLETED" or _enum_name(episode.type) != "EPISODE_TYPE_PUBLIC":
            continue
        agents = list(episode.agents or [])
        target = next(
            (
                agent
                for agent in agents
                if int(agent.submission_id) == int(submission.id)
            ),
            None,
        )
        if target is None:
            continue
        opponent = next((agent for agent in agents if agent is not target), None)
        candidates.append(
            {
                "episode_id": int(episode.id),
                "create_time": _iso(episode.create_time),
                "end_time": _iso(episode.end_time),
                "target_reward": float(target.reward),
                "target_agent_index": int(target.index),
                "opponent": {
                    "team_id": int(opponent.team_id) if opponent else None,
                    "team_name": opponent.team_name if opponent else None,
                    "submission_id": int(opponent.submission_id) if opponent else None,
                    "reward": float(opponent.reward) if opponent else None,
                    "agent_index": int(opponent.index) if opponent else None,
                },
            }
        )
    candidates.sort(key=lambda item: (-item["target_reward"], item["episode_id"]))
    if not candidates:
        raise RuntimeError(f"submission {submission.id} has no completed public episode with a reward")
    return {
        **row,
        "submission_id": int(submission.id),
        "submission_public_score": str(submission.public_score),
        "submission_created_at": _iso(submission.date_submitted),
        "episode_candidates": candidates,
    }


def _select_unique(team_records, count):
    selected = []
    used_episode_ids = set()
    for record in sorted(team_records, key=lambda item: item["rank"]):
        choice_index = next(
            (
                index
                for index, candidate in enumerate(record["episode_candidates"])
                if candidate["episode_id"] not in used_episode_ids
            ),
            None,
        )
        if choice_index is None:
            continue
        choice = record["episode_candidates"][choice_index]
        used_episode_ids.add(choice["episode_id"])
        selected.append(
            {
                key: value
                for key, value in record.items()
                if key != "episode_candidates"
            }
            | choice
            | {
                "team_reward_rank_within_submission": choice_index + 1,
                "selection_reason": "highest_reward_unique_public_episode",
            }
        )
        if len(selected) == count:
            break
    return selected


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_replay(path, selected):
    with path.open("r", encoding="utf-8") as handle:
        replay = json.load(handle)
    episode_id = int(replay.get("info", {}).get("EpisodeId", -1))
    if episode_id != selected["episode_id"]:
        raise RuntimeError(f"episode ID mismatch in {path}: {episode_id}")
    steps = replay.get("steps")
    rewards = replay.get("rewards")
    statuses = replay.get("statuses")
    if not isinstance(steps, list) or len(steps) != 720:
        raise RuntimeError(f"unexpected step count in {path}: {len(steps) if isinstance(steps, list) else None}")
    if statuses != ["DONE", "DONE"]:
        raise RuntimeError(f"unexpected statuses in {path}: {statuses}")
    index = selected["target_agent_index"]
    if not isinstance(rewards, list) or index >= len(rewards) or float(rewards[index]) != selected["target_reward"]:
        raise RuntimeError(f"target reward mismatch in {path}: {rewards}")
    return {
        "file": f"replays/{path.name}",
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "steps": len(steps),
        "statuses": statuses,
        "replay_rewards": rewards,
        "seed": replay.get("info", {}).get("seed"),
        "module_version": replay.get("module_version"),
        "schema_version": replay.get("schema_version"),
        "team_names": replay.get("info", {}).get("TeamNames"),
    }


def _download_one(output, selected):
    replay_dir = output / "replays"
    replay_dir.mkdir(parents=True, exist_ok=True)
    path = replay_dir / f"episode-{selected['episode_id']}-replay.json"
    if not path.exists():
        api = _api()
        _retry(api.competition_episode_replay, selected["episode_id"], path=str(replay_dir), quiet=True)
    validation = _validate_replay(path, selected)
    return selected | validation


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--competition", default="kaggriculture")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--candidate-limit", type=int, default=80)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.count < 1 or args.candidate_limit < args.count:
        parser.error("candidate-limit must be at least count, and count must be positive")

    output = (
        args.output
        if args.output is not None
        else DEFAULT_OUTPUT_BASE / f"top{args.count}-{datetime.now().astimezone().date().isoformat()}"
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    leaderboard = _leaderboard_snapshot(args.competition, args.candidate_limit)
    if len(leaderboard) < args.count:
        raise RuntimeError(f"leaderboard returned only {len(leaderboard)} rows")
    _write_json(
        output / "leaderboard_snapshot.json",
        {
            "competition": args.competition,
            "captured_at": captured_at,
            "requested_rows": args.candidate_limit,
            "rows": leaderboard,
        },
    )
    print(f"Captured {len(leaderboard)} leaderboard rows", flush=True)

    records = []
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_episode_candidates, row): row for row in leaderboard}
        for completed, future in enumerate(as_completed(futures), start=1):
            row = futures[future]
            try:
                record = future.result()
                records.append(record)
                print(
                    f"metadata {completed}/{len(futures)} rank={row['rank']} "
                    f"team={row['team_name']} episodes={len(record['episode_candidates'])}",
                    flush=True,
                )
            except Exception as exc:
                failures.append({**row, "stage": "metadata", "error": str(exc)})
                print(f"metadata failed rank={row['rank']} team={row['team_name']}: {exc}", flush=True)

    selected = _select_unique(records, args.count)
    if len(selected) < args.count:
        _write_json(output / "failures.json", failures)
        raise RuntimeError(f"could select only {len(selected)} unique episodes; need {args.count}")
    print(f"Selected {len(selected)} unique episodes; downloading", flush=True)

    downloaded = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_download_one, output, item): item for item in selected}
        for completed, future in enumerate(as_completed(futures), start=1):
            item = futures[future]
            try:
                record = future.result()
                downloaded.append(record)
                print(
                    f"download {completed}/{len(futures)} episode={item['episode_id']} "
                    f"team={item['team_name']} bytes={record['bytes']}",
                    flush=True,
                )
            except Exception as exc:
                failures.append({**item, "stage": "download_or_validation", "error": str(exc)})
                print(f"download failed episode={item['episode_id']}: {exc}", flush=True)

    downloaded.sort(key=lambda item: item["rank"])
    manifest = {
        "dataset": "Kaggriculture top-team high-reward public replays",
        "competition": args.competition,
        "captured_at": captured_at,
        "selection_policy": {
            "leaderboard_snapshot": "single live public leaderboard snapshot",
            "submission": "active team submission whose public score exactly matches the snapshot score",
            "episode": "highest target-team reward among completed public episodes",
            "uniqueness": "episode IDs are unique in leaderboard order; later duplicate uses next-highest reward",
            "tie_break": "lower episode ID",
            "backfill": f"scan leaderboard ranks 1-{args.candidate_limit} until {args.count} files are selected",
        },
        "tooling": {
            "collector": "scripts/collect_top_public_replays.py",
            "kaggle_cli_version": package_version("kaggle"),
        },
        "requested_count": args.count,
        "downloaded_count": len(downloaded),
        "total_bytes": sum(item["bytes"] for item in downloaded),
        "entries": downloaded,
    }
    _write_json(output / "manifest.json", manifest)
    _write_json(output / "failures.json", failures)
    if len(downloaded) != args.count or failures:
        raise RuntimeError(f"dataset incomplete: downloaded={len(downloaded)} failures={len(failures)}")
    print(
        f"Complete: {len(downloaded)} replays, {manifest['total_bytes']} bytes, manifest={output / 'manifest.json'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
