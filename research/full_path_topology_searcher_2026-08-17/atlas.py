"""Read-only structural atlas over retained JSON/SQLite/cache artifacts."""

from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Iterable

try:
    from .model import canonical_json
except ImportError:
    from model import canonical_json


LANE = Path(__file__).resolve().parent
ROOT = LANE.parents[1]
OLD_CACHE = ROOT / "research" / "cache" / "full_tape_topology_scaleup_2026-08-10"
TRIE_DB = OLD_CACHE / "corpus" / "full_action_prefix_trie.sqlite"
ROUTES = {
    "v27_current_meta": ROOT / "research/main_approach/v27_current_meta/development/route_actions.json",
    "boatlee_v16_rc2_market_relay": ROOT / "research/main_approach/boatlee_v16_rc2_market_relay/development/route_actions.json",
}


def representatives(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _read_manifest() -> list[dict[str, Any]]:
    path = OLD_CACHE / "corpus" / "manifest.jsonl"
    with path.open(encoding="utf-8") as handle:
        return representatives(json.loads(line) for line in handle if line.strip())


def _load_actions(record: dict[str, Any]) -> list[dict[str, Any]]:
    with gzip.open(OLD_CACHE / record["feature_path"], "rt", encoding="utf-8") as handle:
        feature = json.load(handle)
    with gzip.open(OLD_CACHE / feature["tapes"]["full_tape_path"], "rt", encoding="utf-8") as handle:
        return json.load(handle)["actions"]


def deduplicated_tapes() -> tuple[list[tuple[dict[str, Any], list[dict[str, Any]], str]], list[dict[str, Any]]]:
    retained: list[tuple[dict[str, Any], list[dict[str, Any]], str]] = []
    first_by_digest: dict[str, dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    for record in _read_manifest():
        actions = _load_actions(record)
        if len(actions) != 719:
            raise ValueError(f"invalid tape length: {record['episode_id']}")
        digest = hashlib.sha256(canonical_json(actions).encode("utf-8")).hexdigest()
        first = first_by_digest.get(digest)
        if first is not None:
            duplicates.append({
                "full_action_digest": digest,
                "kept_episode_id": int(first["episode_id"]),
                "dropped_episode_id": int(record["episode_id"]),
            })
            continue
        first_by_digest[digest] = record
        retained.append((record, actions, digest))
    return retained, duplicates


def _entropy(counter: Counter[str]) -> float:
    total = sum(counter.values())
    return 0.0 if not total else -sum((n / total) * math.log2(n / total) for n in counter.values())


def _channel(action: dict[str, Any], name: str) -> Any:
    if name == "market":
        return action.get("market", [])
    if name == "unit":
        return {key: value for key, value in action.items() if key != "market"}
    return action


def channel_entropy(tapes: list[tuple[dict[str, Any], list[dict[str, Any]], str]]) -> dict[str, list[float]]:
    counts = {name: [Counter() for _ in range(719)] for name in ("full", "unit", "market")}
    for _record, actions, _digest in tapes:
        for step, action in enumerate(actions):
            for name in counts:
                value = json.dumps(_channel(action, name), sort_keys=True, separators=(",", ":"))
                counts[name][step][value] += 1
    return {name: [round(_entropy(counter), 8) for counter in values] for name, values in counts.items()}


def _trie_statistics(tapes: list[tuple[dict[str, Any], list[dict[str, Any]], str]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    for _record, actions, _tape_digest in tapes:
        parent = "ROOT"
        rolling = b""
        for depth, action in enumerate(actions, start=1):
            action_hash = hashlib.sha256(canonical_json(action).encode("utf-8")).digest()
            rolling = hashlib.sha256(rolling + action_hash).digest()
            prefix = rolling.hex()
            node = nodes.setdefault(prefix, {"parent": parent, "depth": depth, "support": 0})
            node["support"] += 1
            parent = prefix
    children: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for prefix, node in nodes.items():
        children[node["parent"]].append((prefix, node))
    boundaries = []
    for parent, rows in children.items():
        if len(rows) > 1:
            boundaries.append({
                "children": len(rows),
                "turn": max(int(node["depth"]) for _prefix, node in rows) - 1,
                "aggregate_child_support": sum(int(node["support"]) for _prefix, node in rows),
                "_parent": parent,
            })
    boundaries.sort(key=lambda row: (-row["aggregate_child_support"], -row["turn"], row["_parent"]))
    structure_hasher = hashlib.sha256()
    for prefix in sorted(nodes):
        structure_hasher.update(prefix.encode("ascii") + b"\n")
    return {
        "nodes": len(nodes),
        "max_depth": max((int(node["depth"]) for node in nodes.values()), default=0),
        "structure_digest": structure_hasher.hexdigest(),
        "branch_boundaries": [{key: value for key, value in row.items() if key != "_parent"} for row in boundaries[:100]],
    }


def build_incumbent_graph(lane: str) -> dict[str, Any]:
    if lane not in ROUTES:
        raise ValueError(f"unknown lane: {lane}")
    actions = json.loads(ROUTES[lane].read_text(encoding="utf-8"))
    if len(actions) != 719:
        raise ValueError("incumbent spine must contain exactly 719 meaningful actions")
    nodes = []
    edges = []
    for step, action in enumerate(actions):
        node_id = f"{lane}:spine:{step:03d}"
        digest = hashlib.sha256(canonical_json(action).encode("utf-8")).hexdigest()
        nodes.append({"id": node_id, "kind": "incumbent_spine", "step": step, "action_digest": digest})
        if step:
            edges.append({"lane": lane, "source": f"{lane}:spine:{step-1:03d}", "target": node_id,
                          "kind": "structural", "evidence_ids": [f"{lane.split('_', 1)[0]}_route"]})
    graph_digest = hashlib.sha256(canonical_json({"nodes": nodes, "edges": edges}).encode("utf-8")).hexdigest()
    return {"lane": lane, "nodes": nodes, "edges": edges, "graph_digest": graph_digest}


def build_atlas(include_channel_entropy: bool = True) -> dict[str, Any]:
    uri = TRIE_DB.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        count, depth = connection.execute("SELECT COUNT(*), MAX(depth) FROM nodes").fetchone()
        legacy_hasher = hashlib.sha256()
        for (prefix,) in connection.execute("SELECT prefix FROM nodes ORDER BY prefix"):
            legacy_hasher.update(str(prefix).encode("ascii") + b"\n")
    finally:
        connection.close()
    source_representatives = _read_manifest()
    tapes, duplicates = deduplicated_tapes()
    statistics = _trie_statistics(tapes)
    if ((int(count), int(depth), legacy_hasher.hexdigest())
            != (statistics["nodes"], statistics["max_depth"], statistics["structure_digest"])):
        raise ValueError("deduplicated trie structure diverges from the legacy node structure")
    result = {
        "schema_version": 1,
        "information_boundary": "Canonical target-player actions only; no opponent private replay fields.",
        "source_representative_tapes": len(source_representatives),
        "representative_tapes": len(tapes),
        "unique_full_action_digests": len({digest for _record, _actions, digest in tapes}),
        "exact_duplicate_tapes_removed": len(duplicates),
        "exact_duplicate_records": duplicates,
        "nodes": statistics["nodes"], "max_depth": statistics["max_depth"],
        "reported_branch_boundaries": statistics["branch_boundaries"],
        "support_population": "canonical_full_action_digest_deduplicated",
        "legacy_support_statistics_used": False,
        "legacy_node_structure_match": True,
        "deduplicated_structure_digest": statistics["structure_digest"],
        "evidence": ["atlas_inputs", "full_action_trie_sqlite"],
        "incumbent_graphs": {},
    }
    for lane in ROUTES:
        graph = build_incumbent_graph(lane)
        result["incumbent_graphs"][lane] = {"nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                                                    "graph_digest": graph["graph_digest"], "pool_lanes": False}
    if include_channel_entropy:
        result["channel_entropy_by_step"] = channel_entropy(tapes)
    return result


def first_irreversible_divergence(control: list[dict[str, Any]], candidate: list[dict[str, Any]], lookback: int = 8) -> dict[str, Any] | None:
    if len(control) != len(candidate):
        raise ValueError("paired traces must have equal length")
    for step, (left, right) in enumerate(zip(control, candidate)):
        if left.get("causal_digest") != right.get("causal_digest"):
            return {"divergence_step": step, "window_start": max(0, step - lookback),
                    "control_digest": left.get("causal_digest"), "candidate_digest": right.get("causal_digest")}
    return None
