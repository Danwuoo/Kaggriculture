"""Read-only source, route, atlas, and audited-engine preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from .contract import LANES, SearchContract, canonical_json
from .genome import RootRegistry


class PreflightError(RuntimeError):
    pass


def _sha(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _git_blob(root: Path, commit: str, relative: str) -> tuple[bytes, str]:
    vendor = root / ".vendor" / "kaggle-environments"
    raw = subprocess.check_output(["git", "-C", str(vendor), "show", f"{commit}:{relative}"])
    blob = subprocess.run(
        ["git", "-C", str(vendor), "rev-parse", f"{commit}:{relative}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return raw, blob


def _implementation_manifest(root: Path) -> dict[str, Any]:
    source_root = root / "research" / "full_path_topology_searcher_2026-08-17" / "max_search"
    rows = []
    for path in sorted(source_root.glob("*.py"), key=lambda value: value.name):
        raw = path.read_bytes()
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    if not rows:
        raise PreflightError("maximum-search implementation source inventory is empty")
    return {
        "files": rows,
        "file_count": len(rows),
        "manifest_sha256": hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest(),
    }


def source_snapshot(root: Path, contract: SearchContract, registry: RootRegistry) -> dict[str, Any]:
    engine = contract.payload["engine"]
    py_relative = "kaggle_environments/envs/kaggriculture/kaggriculture.py"
    json_relative = "kaggle_environments/envs/kaggriculture/kaggriculture.json"
    py_raw, py_blob = _git_blob(root, engine["commit"], py_relative)
    json_raw, json_blob = _git_blob(root, engine["commit"], json_relative)
    actual_engine = {
        "commit": engine["commit"],
        "python_blob": py_blob,
        "configuration_blob": json_blob,
        "python_sha256": hashlib.sha256(py_raw).hexdigest(),
        "configuration_sha256": hashlib.sha256(json_raw).hexdigest(),
        "python_bytes": len(py_raw),
        "configuration_bytes": len(json_raw),
    }
    if actual_engine["python_sha256"] != engine["python_sha256"] or actual_engine["configuration_sha256"] != engine["configuration_sha256"]:
        raise PreflightError("audited engine Python/configuration fingerprint mismatch")

    controls: dict[str, Any] = {}
    routes: dict[str, Any] = {}
    for lane in LANES:
        control_path = root / "research" / "main_approach" / lane / "main.py"
        route_path = root / "research" / "main_approach" / lane / "development" / "route_actions.json"
        route = json.loads(route_path.read_text(encoding="utf-8"))
        if not isinstance(route, list) or len(route) != 719:
            raise PreflightError(f"{lane} route is not exactly 719 turns")
        controls[lane] = _sha(control_path)
        routes[lane] = _sha(route_path)
    if routes[LANES[0]]["sha256"] == routes[LANES[1]]["sha256"]:
        # Equality is permitted but ownership remains separate and explicit.
        route_relation = "byte_equal_but_lane_owned_separately"
    else:
        route_relation = "lane_distinct"
    return {
        "schema_version": 2,
        "repo_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip(),
        "engine": actual_engine,
        "controls": controls,
        "routes": routes,
        "route_relation": route_relation,
        "root_manifest_sha256": registry.manifest()["manifest_sha256"],
        "root_count": len(registry),
        "implementation": _implementation_manifest(root),
        "pool_lanes": False,
    }
