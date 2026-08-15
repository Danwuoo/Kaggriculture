"""Read-only validation of the frozen E1b authority and regression anchors."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from model import canonical_bytes, payload_hash


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUN_RELATIVE = Path("research/dual_incumbent_topology_search_2026-08-14/async_v2/artifacts/formal/async_e1b_20260815_consumed_small_screen_v2/run")
SOURCE_ROOT = Path(r"C:\Users\wurre\Downloads\Kaggriculture")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_fixture(path: Path = HERE / "fixtures" / "e1b_regression_fixtures.json") -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != 1 or set(fixture.get("lanes", ())) != {"v27_current_meta", "boatlee_v16_rc2_market_relay"}:
        raise ValueError("invalid E1b regression fixture schema")
    return fixture


def _canonical_file(path: Path, field: str) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = dict(payload)
    embedded = body.pop(field, None)
    actual = payload_hash(body)
    if embedded != actual:
        raise ValueError(f"embedded canonical hash mismatch: {path}")
    return actual


def _source_run() -> Path:
    # Authority asks for source commit bytes; source checkout is read-only.  A
    # worktree rewrites absolute paths in raw JSON, so its raw file SHA differs
    # while the canonical payload must remain identical.
    candidate = SOURCE_ROOT / RUN_RELATIVE
    return candidate if candidate.is_dir() else ROOT / RUN_RELATIVE


def _find_candidate(run: Path, lane: str, candidate_id: str, generation_file: str) -> dict[str, Any] | None:
    path = run / generation_file
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    for row in payload.get("candidates", {}).get(lane, []):
        if row.get("candidate_id") == candidate_id:
            return row
    return None


def verify_frozen_evidence(path: Path = HERE / "fixtures" / "e1b_regression_fixtures.json") -> dict[str, Any]:
    fixture = load_fixture(path)
    authority = fixture["authority"]
    run = _source_run()
    worktree_run = ROOT / RUN_RELATIVE
    errors: list[str] = []
    evidence: dict[str, Any] = {"authority_run": str(run), "worktree_run": str(worktree_run), "anchors": {}}
    try:
        manifest = run / "search_manifest.json"
        summary = run / "search_summary.json"
        if file_sha256(summary) != authority["search_summary_file_sha256"]:
            errors.append("authority summary raw SHA-256 mismatch")
        if _canonical_file(manifest, "manifest_sha256") != authority["search_manifest_canonical_sha256"]:
            errors.append("manifest canonical SHA-256 mismatch")
        if _canonical_file(summary, "summary_sha256") != authority["search_summary_canonical_sha256"]:
            errors.append("summary canonical SHA-256 mismatch")
        # The worktree itself remains independently frozen: no normalisation of
        # v2 is permitted. Its canonical content must equal authority content.
        if _canonical_file(worktree_run / "search_manifest.json", "manifest_sha256") != authority["search_manifest_canonical_sha256"]:
            errors.append("worktree manifest canonical mismatch")
        if _canonical_file(worktree_run / "search_summary.json", "summary_sha256") != authority["search_summary_canonical_sha256"]:
            errors.append("worktree summary canonical mismatch")
        for lane, entries in fixture["lanes"].items():
            for name, anchor in entries.items():
                generation = run / anchor["first_generation_file"]
                canonical = _canonical_file(generation, "generation_sha256")
                present = _find_candidate(run, lane, anchor["candidate_id"], anchor["first_generation_file"])
                ok = canonical == anchor["first_generation_canonical_sha256"] and present is not None
                if not ok:
                    errors.append(f"anchor mismatch: {lane}/{name}")
                evidence["anchors"][anchor["candidate_id"]] = {"generation": anchor["first_generation_file"], "present": present is not None, "canonical": canonical, "pass": ok}
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        errors.append(f"{type(error).__name__}: {error}")
    return {
        "pass": not errors, "errors": errors, "fixture_sha256": file_sha256(path),
        "fixture_canonical_sha256": payload_hash(fixture), "authority": authority,
        "formal_fresh_seeds_executed": False, "evidence": evidence,
    }
