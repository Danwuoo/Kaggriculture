"""Frozen E2 authority and exact registered-candidate reconstruction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V3 = HERE.parent / "async_v3"
RUN_RELATIVE = Path(
    "research/dual_incumbent_topology_search_2026-08-14/async_v3/artifacts/"
    "formal/async_e1c_20260815_expanded_v1"
)
if str(V3) not in sys.path:
    sys.path.insert(0, str(V3))

from compiler import compile_genome  # noqa: E402
from evaluator import engine_fingerprint  # noqa: E402
from model import genome_from_payload, payload_hash  # noqa: E402


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_file(path: Path, embedded_field: str) -> tuple[str, str | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = dict(payload)
    embedded = body.pop(embedded_field, None)
    return payload_hash(body), embedded


def source_root() -> Path:
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return Path(common).resolve().parent


def source_run() -> Path:
    candidate = source_root() / RUN_RELATIVE
    return candidate if candidate.is_dir() else ROOT / RUN_RELATIVE


def registry() -> dict[str, Any]:
    return json.loads((HERE / "candidate_registry.json").read_text(encoding="utf-8"))


def reconstruct_registered() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for lane, row in registry()["lanes"].items():
        genome = genome_from_payload(row["genome"])
        candidate = compile_genome(lane, genome)
        patches = {str(item["step"]): item["market"] for item in candidate.patches}
        expected_patches = {str(step): value for step, value in row["effective_patches"].items()}
        checks = {
            "accepted": candidate.accepted,
            "candidate_id": candidate.candidate_id == row["candidate_id"],
            "candidate_payload_sha256": payload_hash(candidate.payload()) == row["candidate_payload_sha256"],
            "genome_id": genome.genome_id == row["genome_id"],
            "effective_patches": patches == expected_patches,
        }
        result[lane] = {
            "candidate": candidate,
            "checks": checks,
            "pass": all(checks.values()),
            "observed": {
                "candidate_id": candidate.candidate_id,
                "candidate_payload_sha256": payload_hash(candidate.payload()),
                "genome_id": genome.genome_id,
                "effective_patches": patches,
            },
        }
    return result


def verify_authority() -> dict[str, Any]:
    reg = registry()
    run = ROOT / RUN_RELATIVE
    source = source_run()
    expected = reg["source_run"]
    summary_canonical, summary_embedded = canonical_file(run / "search_summary.json", "search_summary_sha256")
    manifest_canonical, manifest_embedded = canonical_file(source / "manifest.json", "manifest")
    engine = engine_fingerprint()
    reconstructed = reconstruct_registered()
    committed_standalones: dict[str, Any] = {}
    rows = [*reg["lanes"].values(), *reg["negative_regressions"]]
    for row in rows:
        if row.get("standalone_path"):
            observed = file_sha256(ROOT / row["standalone_path"])
            committed_standalones[row["candidate_id"]] = {
                "expected": row["standalone_sha256"], "observed": observed,
                "pass": observed == row["standalone_sha256"],
            }
    checks = {
        "summary_file": file_sha256(run / "search_summary.json") == expected["search_summary_file_sha256"],
        "summary_canonical": summary_canonical == expected["search_summary_canonical_sha256"] == summary_embedded,
        "manifest_file": file_sha256(source / "manifest.json") == expected["manifest_file_sha256"],
        "manifest_canonical": manifest_canonical == expected["manifest_canonical_sha256"] == manifest_embedded,
        "protocol_file": file_sha256(run / "protocol.json") == expected["protocol_file_sha256"],
        "launch_file": file_sha256(run / "launch.json") == expected["launch_file_sha256"],
        "engine": all(engine.get(key) == reg["engine"][key] for key in reg["engine"]),
        "registered_candidates": all(row["pass"] for row in reconstructed.values()),
        "standalones": all(row["pass"] for row in committed_standalones.values()),
        "no_fresh_seed": not reg["formal_fresh_seeds_executed"] and not reg["e2_fresh_seeds"],
    }
    return {
        "pass": all(checks.values()), "checks": checks, "engine": engine,
        "registry_sha256": file_sha256(HERE / "candidate_registry.json"),
        "source_run": str(source), "reconstructed": {
            lane: {key: value for key, value in row.items() if key != "candidate"}
            for lane, row in reconstructed.items()
        },
        "standalones": committed_standalones,
    }
