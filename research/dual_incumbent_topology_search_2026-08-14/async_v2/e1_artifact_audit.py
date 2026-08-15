"""Recompute the retained Async E1 counts and finalist action digests locally."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from library import atomic_json, file_sha256
from model import payload_hash


EXPECTED_CANDIDATES = {
    "boatlee_v16_rc2_market_relay": (
        "ac_a1e05aba3bbec57679ffa9bf",
        "ac_130a8c2110c0be24ed67e73d",
    ),
    "v27_current_meta": (
        "ac_7ec82c0785b5bf8b3a88295a",
        "ac_2a147a5242d39811af8fe8ff",
    ),
}


def _tree_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda row: row.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(bytes.fromhex(file_sha256(path)))
    return digest.hexdigest()


def audit(run_root: Path, output: Path) -> dict[str, Any]:
    generation_paths = sorted(run_root.glob("generation_*.json"))
    score_paths = sorted(run_root.glob("scores_*.json"))
    shard_paths = sorted((run_root / "shards").glob("job_*.json"))
    genomes: dict[tuple[str, str], str] = {}
    candidates: dict[str, tuple[str, str]] = {}
    for path in generation_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for lane, rows in payload["candidates"].items():
            for row in rows:
                key = (lane, row["genome_id"])
                genomes[key] = row["candidate_id"]
                candidates[row["candidate_id"]] = key
    unique_scores: dict[tuple[str, str], dict[str, Any]] = {}
    for path in score_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for lane, rows in payload["scores"].items():
            for row in rows:
                unique_scores[(lane, row["genome_id"])] = row
    no_op = sorted(row["candidate_id"] for row in unique_scores.values() if int(row.get("action_changed_contexts", 0)) == 0)
    changed = sorted(row["candidate_id"] for row in unique_scores.values() if int(row.get("action_changed_contexts", 0)) > 0)

    requested_ids = {candidate for values in EXPECTED_CANDIDATES.values() for candidate in values}
    digest_maps: dict[str, dict[str, str]] = {candidate: {} for candidate in requested_ids}
    generations: dict[str, set[int]] = {candidate: set() for candidate in requested_ids}
    lanes: dict[str, str] = {}
    invalid_shards = []
    for path in shard_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        body = dict(payload)
        expected = body.pop("shard_sha256", None)
        if expected != payload_hash(body):
            invalid_shards.append(path.name)
            continue
        candidate = payload.get("candidate_id")
        if candidate not in requested_ids:
            continue
        context = f"{payload['opponent']}|{int(payload['seed'])}|seat{int(payload['seat'])}"
        digest = payload["candidate_behavior"]["action_digest"]
        previous = digest_maps[candidate].get(context)
        if previous is not None and previous != digest:
            raise RuntimeError(f"retained E1 nondeterminism: {candidate} {context}")
        digest_maps[candidate][context] = digest
        generations[candidate].add(int(payload["generation"]))
        lanes[candidate] = payload["lane"]
    finalist_pairs = {}
    for lane, (left, right) in EXPECTED_CANDIDATES.items():
        finalist_pairs[lane] = {
            "left": left,
            "right": right,
            "left_generations": sorted(generations[left]),
            "right_generations": sorted(generations[right]),
            "left_contexts": len(digest_maps[left]),
            "right_contexts": len(digest_maps[right]),
            "left_digest_map_sha256": payload_hash(digest_maps[left]),
            "right_digest_map_sha256": payload_hash(digest_maps[right]),
            "equal_digest_maps": digest_maps[left] == digest_maps[right],
            "different_contexts": sorted(
                context
                for context in set(digest_maps[left]) | set(digest_maps[right])
                if digest_maps[left].get(context) != digest_maps[right].get(context)
            ),
        }
    counts = {
        "generation_files": len(generation_paths),
        "score_files": len(score_paths),
        "candidate_context_jobs": len(shard_paths),
        "unique_lane_genomes": len(genomes),
        "semantic_no_op": len(no_op),
        "behavior_changing": len(changed),
        "by_lane": {
            lane: {
                "unique": sum(key[0] == lane for key in unique_scores),
                "semantic_no_op": sum(key[0] == lane and int(row.get("action_changed_contexts", 0)) == 0 for key, row in unique_scores.items()),
                "behavior_changing": sum(key[0] == lane and int(row.get("action_changed_contexts", 0)) > 0 for key, row in unique_scores.items()),
            }
            for lane in EXPECTED_CANDIDATES
        },
    }
    checks = {
        "counts": counts["candidate_context_jobs"] == 4096 and counts["unique_lane_genomes"] == 235 and counts["semantic_no_op"] == 36 and counts["behavior_changing"] == 199,
        "all_shards_hashed": not invalid_shards,
        "requested_candidates_present": all(candidate in candidates for candidate in requested_ids),
        "requested_candidates_have_16_contexts": all(len(mapping) == 16 for mapping in digest_maps.values()),
        "requested_candidates_lane_owned": all(lanes.get(candidate) == lane for lane, values in EXPECTED_CANDIDATES.items() for candidate in values),
    }
    body = {
        "schema_version": 1,
        "purpose": "local retained-E1 verification; no game execution",
        "formal_fresh_seeds_executed": False,
        "e1_seeds_reexecuted": False,
        "run_root": str(run_root),
        "counts": counts,
        "negative_evidence": {
            "semantic_no_op_candidate_ids": no_op,
            "behavior_changing_candidate_ids_sha256": payload_hash(changed),
        },
        "requested_action_digests": {
            candidate: {
                "lane": lanes.get(candidate),
                "generations": sorted(generations[candidate]),
                "contexts": dict(sorted(digest_maps[candidate].items())),
                "digest_map_sha256": payload_hash(digest_maps[candidate]),
            }
            for candidate in sorted(requested_ids)
        },
        "finalist_pair_comparison": finalist_pairs,
        "artifact_tree": {
            "generation_files_sha256": _tree_digest(generation_paths),
            "score_files_sha256": _tree_digest(score_paths),
            "shard_files_sha256": _tree_digest(shard_paths),
        },
        "invalid_shards": invalid_shards,
        "checks": checks,
        "pass": all(checks.values()),
    }
    result = {**body, "e1_artifact_audit_sha256": payload_hash(body)}
    atomic_json(output, result)
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run_root, args.output)
    print(json.dumps({"pass": result["pass"], "sha256": result["e1_artifact_audit_sha256"], "output": str(args.output)}, sort_keys=True))
