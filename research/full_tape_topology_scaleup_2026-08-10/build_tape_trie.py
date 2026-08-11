"""Build a disk-backed full-action prefix trie and family market-residual audit.

Input is only the compressed target-player canonical tapes written by
``streaming_corpus.py``. SQLite keeps memory bounded for a 1,500-tape run;
opponent private replay fields are never opened or consulted.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = ROOT / "research" / "cache" / "full_tape_topology_scaleup_2026-08-10"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def action_digest(action: Any) -> str:
    return hashlib.sha256(canonical(action)).hexdigest()


def rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def representatives(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_teams: set[int] = set()
    seen_submissions: set[int] = set()
    result = []
    for item in sorted(items, key=lambda value: (int(value["rank"]), int(value["episode_id"]))):
        team, submission = int(item["team_id"]), int(item["submission_id"])
        if team in seen_teams or submission in seen_submissions:
            continue
        seen_teams.add(team)
        seen_submissions.add(submission)
        result.append(item)
    return result


def load_tape(cache: Path, record: dict[str, Any]) -> list[dict[str, Any]]:
    path = cache / record["feature_path"]
    with gzip.open(path, "rb") as handle:
        feature = json.loads(handle.read().decode("utf-8"))
    tape = cache / feature["tapes"]["full_tape_path"]
    with gzip.open(tape, "rb") as handle:
        actions = json.loads(handle.read().decode("utf-8"))["actions"]
    if len(actions) != 719:
        raise ValueError(f"invalid tape length for episode {record['episode_id']}")
    return actions


def setup(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    DROP TABLE IF EXISTS nodes;
    CREATE TABLE nodes (
      prefix TEXT PRIMARY KEY,
      parent TEXT NOT NULL,
      depth INTEGER NOT NULL,
      action_digest TEXT NOT NULL,
      support INTEGER NOT NULL,
      first_episode INTEGER NOT NULL,
      first_rank INTEGER NOT NULL
    );
    CREATE INDEX nodes_parent_idx ON nodes(parent);
    CREATE INDEX nodes_support_idx ON nodes(support, depth);
    """)


def build(cache: Path, output: Path) -> dict[str, Any]:
    manifest = representatives(rows(cache / "corpus" / "manifest.jsonl"))
    database = cache / "corpus" / "full_action_prefix_trie.sqlite"
    connection = sqlite3.connect(database)
    try:
        setup(connection)
        for record in manifest:
            parent = "ROOT"
            rolling = b""
            for depth, action in enumerate(load_tape(cache, record), start=1):
                digest = action_digest(action)
                rolling = hashlib.sha256(rolling + bytes.fromhex(digest)).digest()
                prefix = rolling.hex()
                connection.execute(
                    """INSERT INTO nodes(prefix,parent,depth,action_digest,support,first_episode,first_rank)
                       VALUES(?,?,?,?,1,?,?)
                       ON CONFLICT(prefix) DO UPDATE SET support=support+1""",
                    (prefix, parent, depth, digest, int(record["episode_id"]), int(record["rank"])),
                )
                parent = prefix
        connection.commit()
        counts = connection.execute("SELECT COUNT(*), MAX(depth) FROM nodes").fetchone()
        common = connection.execute("SELECT depth,support,first_rank,first_episode FROM nodes WHERE support >= 2 ORDER BY support DESC, depth DESC LIMIT 100").fetchall()
        branches = connection.execute(
            """SELECT parent, COUNT(*) AS children, MAX(depth)-1 AS branch_turn,
                      SUM(support) AS child_support
               FROM nodes GROUP BY parent HAVING COUNT(*) > 1
               ORDER BY child_support DESC, branch_turn DESC LIMIT 100"""
        ).fetchall()
    finally:
        connection.close()

    unit_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in manifest:
        unit_groups[record["unit_tape"]].append(record)
    residuals = []
    for unit_digest, members in sorted(unit_groups.items(), key=lambda item: (-len(item[1]), item[0]))[:10]:
        if len(members) < 2:
            continue
        phase_sells: list[Counter[str]] = [Counter() for _ in range(30)]
        terminal = Counter()
        market_digests = Counter()
        for record in members:
            actions = load_tape(cache, record)
            market_digests[record["market_tape"]] += 1
            for step, action in enumerate(actions):
                phase = min(step // 24, 29)
                for order in action.get("market", []):
                    if isinstance(order, list) and len(order) >= 3 and order[0] == "SELL":
                        phase_sells[phase][f"{order[1]}:{int(order[2])}"] += 1
                if step >= 716:
                    terminal[json.dumps(action.get("market", []), sort_keys=True, separators=(",", ":"))] += 1
        residuals.append({
            "unit_tape": unit_digest, "support": len(members), "ranks": sorted(int(item["rank"]) for item in members),
            "distinct_market_tapes": len(market_digests),
            "phase_sell_modes": [{"phase": index, "top": counter.most_common(5)} for index, counter in enumerate(phase_sells) if counter],
            "terminal_market_shapes": [{"shape": shape, "support": support} for shape, support in terminal.most_common(10)],
        })
    report = {
        "cache_absolute_path": str(cache.resolve()), "sqlite_path": str(database.resolve()),
        "information_boundary": "Trie and residual summaries read canonical target-player actions only; no replay observations or opponent private state.",
        "representative_tapes": len(manifest), "nodes": int(counts[0]), "max_depth": int(counts[1] or 0),
        "common_prefixes_support_ge_2": [{"depth": int(depth), "support": int(support), "first_rank": int(rank), "first_episode": int(episode)} for depth, support, rank, episode in common],
        "branch_boundaries": [{"children": int(children), "turn": int(turn), "aggregate_child_support": int(support)} for _parent, children, turn, support in branches],
        "family_market_residuals": residuals,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.cache.resolve(), args.output)
    print(json.dumps({"representative_tapes": report["representative_tapes"], "nodes": report["nodes"], "max_depth": report["max_depth"], "common_prefixes": report["common_prefixes_support_ge_2"][:5], "branch_boundaries": report["branch_boundaries"][:5]}, indent=2))


if __name__ == "__main__":
    main()
