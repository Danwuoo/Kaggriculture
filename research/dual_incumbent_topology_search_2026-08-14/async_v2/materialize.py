"""Materialize lane-specific asynchronous topology standalones."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
from pathlib import Path
import tempfile
from typing import Any

from compiler import CONTROLS
from model import CompiledAsyncCandidate
from runtime import render_runtime


FORBIDDEN = {"subprocess", "multiprocessing", "threading", "socket", "requests", "pandas", "sklearn"}


def render_standalone(candidate: CompiledAsyncCandidate) -> str:
    control = CONTROLS[candidate.lane].read_text(encoding="utf-8")
    return control.rstrip() + "\n" + render_runtime(candidate)


def materialize(candidate: CompiledAsyncCandidate, output: Path) -> dict[str, Any]:
    content = render_standalone(candidate)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    raw = output.read_bytes()
    return {"lane": candidate.lane, "candidate_id": candidate.candidate_id, "path": str(output), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def static_audit(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return {"imports": sorted(imports), "forbidden_imports": sorted(imports & FORBIDDEN), "pass": not bool(imports & FORBIDDEN)}


def isolated_import(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="async-topology-") as temp:
        copy = Path(temp) / "main.py"
        copy.write_bytes(path.read_bytes())
        spec = importlib.util.spec_from_file_location(f"async_{hashlib.sha256(copy.read_bytes()).hexdigest()[:12]}", copy)
        if spec is None or spec.loader is None:
            raise ImportError(copy)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {"callable_agent": callable(getattr(module, "agent", None)), "path": str(path)}
