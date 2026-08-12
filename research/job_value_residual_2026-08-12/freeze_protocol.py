"""Freeze current incumbent artifacts and the exact experiment protocol."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from protocol import (
    CONFIG_BLOB,
    CONFIG_SHA256,
    CONFIRMATION_SEEDS,
    DISCOVERY_SEEDS,
    ENGINE_BLOB,
    ENGINE_COMMIT,
    ENGINE_SHA256,
    INCUMBENTS,
    LANE_ROOT,
    OPPONENT_FAMILIES,
    REPORT_ROOT,
    ROOT,
    SCREEN_SEEDS,
    candidate_path,
    control_path,
    opponent_path,
    stage_contexts,
)


HARNESS_ROOT = ROOT / "research" / "main_approach" / "performance_optimization_2026_08_11"
if str(HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARNESS_ROOT))

from harness import engine_fingerprint  # noqa: E402


SEEDS = DISCOVERY_SEEDS + SCREEN_SEEDS + CONFIRMATION_SEEDS
MANIFEST_PATH = LANE_ROOT / "artifacts" / "prechange_manifest.json"


def freeze_file(source: Path, target: Path) -> dict[str, Any]:
    """Copy a control once, rejecting an attempt to replace frozen bytes."""
    raw = source.read_bytes()
    if target.exists() and target.read_bytes() != raw:
        raise RuntimeError(f"frozen control differs: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(raw)
    return {
        "path": str(target),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _is_outside_new_lane(path: Path) -> bool:
    resolved = path.resolve()
    return not (
        resolved.is_relative_to(LANE_ROOT.resolve())
        or resolved.is_relative_to(REPORT_ROOT.resolve())
    )


def scan_prior_seed_hits() -> dict[str, list[dict[str, Any]]]:
    """Find every reserved seed in retained reports and research evidence."""
    patterns = {seed: re.compile(rf"(?<!\d){seed}(?!\d)") for seed in SEEDS}
    hits: dict[str, list[dict[str, Any]]] = {str(seed): [] for seed in SEEDS}
    for base in (ROOT / "reports", ROOT / "research"):
        for path in sorted(base.rglob("*")):
            if not path.is_file() or not _is_outside_new_lane(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for seed, pattern in patterns.items():
                lines = [
                    number
                    for number, line in enumerate(text.splitlines(), start=1)
                    if pattern.search(line)
                ]
                if lines:
                    hits[str(seed)].append(
                        {
                            "path": path.relative_to(ROOT).as_posix(),
                            "lines": lines,
                        }
                    )
    return hits


def _assert_expected_engine(fingerprint: dict[str, Any]) -> None:
    expected = {
        "commit": ENGINE_COMMIT,
        "python_blob": ENGINE_BLOB,
        "configuration_blob": CONFIG_BLOB,
        "python_sha256": ENGINE_SHA256,
        "configuration_sha256": CONFIG_SHA256,
    }
    for key, value in expected.items():
        if fingerprint.get(key) != value:
            raise RuntimeError(
                f"official engine {key} mismatch: {fingerprint.get(key)} != {value}"
            )


def manifest_payload() -> dict[str, Any]:
    """Build the deterministic manifest after controls have been frozen."""
    fingerprint = engine_fingerprint()
    _assert_expected_engine(fingerprint)
    controls = {
        incumbent: freeze_file(candidate_path(incumbent), control_path(incumbent))
        for incumbent in INCUMBENTS
    }
    opponents = {
        incumbent: {
            family: {
                "path": str(opponent_path(incumbent, family)),
                "bytes": opponent_path(incumbent, family).stat().st_size,
                "sha256": hashlib.sha256(
                    opponent_path(incumbent, family).read_bytes()
                ).hexdigest(),
            }
            for family in OPPONENT_FAMILIES
        }
        for incumbent in INCUMBENTS
    }
    prior_seed_hits = scan_prior_seed_hits()
    return {
        "schema_version": 1,
        "engine": fingerprint,
        "controls": controls,
        "opponents": opponents,
        "seed_pools": {
            "discovery": list(DISCOVERY_SEEDS),
            "screen": list(SCREEN_SEEDS),
            "confirmation": list(CONFIRMATION_SEEDS),
        },
        "stage_context_counts": {
            stage: len(stage_contexts(stage))
            for stage in ("discovery", "screen", "confirmation")
        },
        "prior_seed_hits": prior_seed_hits,
    }


def freeze_protocol() -> Path:
    """Write the immutable manifest, refusing any conflicting rerun."""
    payload = manifest_payload()
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if MANIFEST_PATH.exists() and MANIFEST_PATH.read_bytes() != raw:
        raise RuntimeError(f"frozen manifest differs: {MANIFEST_PATH}")
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MANIFEST_PATH.exists():
        MANIFEST_PATH.write_bytes(raw)
    return MANIFEST_PATH


if __name__ == "__main__":
    print(freeze_protocol())
