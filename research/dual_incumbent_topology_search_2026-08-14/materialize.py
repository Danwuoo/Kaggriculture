"""Deterministic research-standalone materialization and isolation checks."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from typing import Any

from model import CompiledCandidate
from runtime_patch import render_runtime


FORBIDDEN_RUNTIME_IMPORTS = {
    "subprocess",
    "multiprocessing",
    "threading",
    "socket",
    "requests",
    "pandas",
    "sklearn",
}


def render_standalone(control_path: Path, candidate: CompiledCandidate) -> str:
    base = control_path.read_text(encoding="utf-8")
    return base.rstrip() + "\n" + render_runtime(candidate)


def materialize(control_path: Path, candidate: CompiledCandidate, output: Path) -> dict[str, Any]:
    content = render_standalone(control_path, candidate)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    raw = output.read_bytes()
    return {
        "lane": candidate.lane,
        "candidate_id": candidate.candidate_id,
        "path": str(output),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def static_runtime_audit(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = set()
    forbidden_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "exec", "eval", "compile", "__import__"}:
            forbidden_calls.append(node.func.id)
    return {
        "imports": sorted(imports),
        "forbidden_imports": sorted(imports & FORBIDDEN_RUNTIME_IMPORTS),
        "forbidden_calls": sorted(forbidden_calls),
        "pass": not (imports & FORBIDDEN_RUNTIME_IMPORTS) and not forbidden_calls,
    }


def isolated_import(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="topology-isolated-") as temp:
        isolated = Path(temp) / "main.py"
        isolated.write_bytes(path.read_bytes())
        spec = importlib.util.spec_from_file_location(f"topology_isolated_{hashlib.sha256(path.read_bytes()).hexdigest()[:12]}", isolated)
        if spec is None or spec.loader is None:
            raise ImportError(isolated)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {"callable_agent": callable(getattr(module, "agent", None)), "path": str(path)}
