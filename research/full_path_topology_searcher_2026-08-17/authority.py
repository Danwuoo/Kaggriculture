"""Evidence registry validation with fail-closed provenance checks."""

from __future__ import annotations

import hashlib
import gzip
import json
from pathlib import Path
import subprocess
from typing import Any


LANE = Path(__file__).resolve().parent
ROOT = LANE.parents[1]
REGISTRY = LANE / "evidence_registry.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _representatives(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_teams: set[int] = set()
    seen_submissions: set[int] = set()
    result = []
    for row in sorted(rows, key=lambda value: (int(value["rank"]), int(value["episode_id"]))):
        team, submission = int(row["team_id"]), int(row["submission_id"])
        if team in seen_teams or submission in seen_submissions:
            continue
        seen_teams.add(team); seen_submissions.add(submission); result.append(row)
    return result


def atlas_inputs_fingerprint() -> dict[str, Any]:
    cache = ROOT / "research/cache/full_tape_topology_scaleup_2026-08-10"
    manifest = cache / "corpus/manifest.jsonl"
    with manifest.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    source_representatives = _representatives(rows)
    paths = {manifest}
    representatives = []
    seen_action_digests: set[str] = set()
    duplicate_count = 0
    for row in source_representatives:
        feature_path = cache / row["feature_path"]
        with gzip.open(feature_path, "rt", encoding="utf-8") as handle:
            feature = json.load(handle)
        tape_path = cache / feature["tapes"]["full_tape_path"]
        with gzip.open(tape_path, "rt", encoding="utf-8") as handle:
            actions = json.load(handle)["actions"]
        digest = hashlib.sha256(json.dumps(actions, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if digest in seen_action_digests:
            duplicate_count += 1
            continue
        seen_action_digests.add(digest)
        representatives.append(row)
        paths.add(feature_path)
        paths.add(tape_path)
    entries = [{"path": str(path.relative_to(ROOT)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in sorted(paths)]
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"source_representative_count": len(source_representatives),
            "representative_count": len(representatives),
            "unique_full_action_digests": len(seen_action_digests),
            "exact_duplicate_count": duplicate_count, "file_count": len(entries),
            "inventory_sha256": hashlib.sha256(encoded).hexdigest(),
            "manifest_sha256": sha256(manifest), "manifest_bytes": manifest.stat().st_size}


def engine_fingerprint(expected: dict[str, Any]) -> dict[str, Any]:
    common = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = ROOT / common_path
    repo = common_path.resolve().parent / ".vendor" / "kaggle-environments"
    relative_python = "kaggle_environments/envs/kaggriculture/kaggriculture.py"
    relative_config = "kaggle_environments/envs/kaggriculture/kaggriculture.json"
    commit = expected["commit"]
    python = subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{relative_python}"])
    configuration = subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{relative_config}"])
    result = {
        "commit": commit,
        "python_blob": subprocess.run(["git", "-C", str(repo), "rev-parse", f"{commit}:{relative_python}"], capture_output=True, text=True, check=True).stdout.strip(),
        "configuration_blob": subprocess.run(["git", "-C", str(repo), "rev-parse", f"{commit}:{relative_config}"], capture_output=True, text=True, check=True).stdout.strip(),
        "python_sha256": hashlib.sha256(python).hexdigest(),
        "configuration_sha256": hashlib.sha256(configuration).hexdigest(),
        "python_bytes": len(python), "configuration_bytes": len(configuration),
    }
    result["passed"] = all(result.get(key) == value for key, value in expected.items())
    return result


def validate_registry() -> dict[str, Any]:
    registry = load_registry()
    findings: list[dict[str, Any]] = []
    source_ids = [source.get("id") for source in registry.get("sources", [])]
    protocols = registry.get("paired_protocols")
    protocol_ids = [row.get("protocol_id") for row in protocols] if isinstance(protocols, list) else []
    registry_contract = {
        "schema_v1": registry.get("schema_version") == 1 and not isinstance(registry.get("schema_version"), bool),
        "strict_formal_boundary": registry.get("formal_efficacy_authorized") is False,
        "unique_source_ids": all(isinstance(value, str) and value for value in source_ids) and len(source_ids) == len(set(source_ids)),
        "paired_protocols_are_unique_list": isinstance(protocols, list) and all(isinstance(value, str) and value for value in protocol_ids) and len(protocol_ids) == len(set(protocol_ids)),
    }
    ok = all(registry_contract.values())
    for source in registry["sources"]:
        path = ROOT / source["path"]
        actual = sha256(path) if path.is_file() else None
        size = path.stat().st_size if path.is_file() else None
        passed = actual == source["sha256"] and size == source["bytes"]
        ok = ok and passed
        findings.append({"id": source["id"], "path": source["path"], "passed": passed,
                         "expected_sha256": source["sha256"], "actual_sha256": actual,
                         "expected_bytes": source["bytes"], "actual_bytes": size})
    engine = engine_fingerprint(registry["engine"])
    atlas_inputs = atlas_inputs_fingerprint()
    expected_inputs = registry["collections"]["atlas_inputs"]
    atlas_inputs["passed"] = all(atlas_inputs.get(key) == value for key, value in expected_inputs.items())
    return {"passed": ok and engine["passed"] and atlas_inputs["passed"], "registry_contract": registry_contract, "sources": findings,
            "collections": {"atlas_inputs": atlas_inputs}, "engine": engine}
