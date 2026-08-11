"""Safely extract public Kaggriculture agents from downloaded notebooks.

Notebook cells are parsed as data and are never executed.  The supported public
notebook patterns are direct ``%%writefile`` cells and base85+zlib literals.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "research" / "public_agents"
MAX_EXTRACTED_BYTES = 5_000_000
DANGEROUS_IMPORTS = {
    "ctypes",
    "http",
    "marshal",
    "pickle",
    "requests",
    "socket",
    "subprocess",
    "urllib",
}
DANGEROUS_CALLS = {
    "__import__",
    "eval",
    "exec",
    "os.popen",
    "os.system",
    "subprocess.call",
    "subprocess.Popen",
    "subprocess.run",
}


def _cell_source(cell):
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _decode_payload(encoded):
    compressed = base64.b85decode(encoded)
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, MAX_EXTRACTED_BYTES + 1)
    if len(raw) > MAX_EXTRACTED_BYTES or decoder.unconsumed_tail:
        raise ValueError("compressed notebook payload exceeds extraction limit")
    raw += decoder.flush(MAX_EXTRACTED_BYTES + 1 - len(raw))
    if len(raw) > MAX_EXTRACTED_BYTES or not decoder.eof:
        raise ValueError("invalid or oversized compressed notebook payload")
    return raw


def _literal_assignments(source):
    tree = ast.parse(source)
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            values[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return values


def _safe_name(name):
    path = Path(name)
    if path.name != name or path.suffix != ".py":
        raise ValueError(f"unsafe extracted filename: {name!r}")
    return name


def _add_file(files, name, raw):
    name = _safe_name(name)
    if len(raw) > MAX_EXTRACTED_BYTES:
        raise ValueError(f"extracted file is too large: {name}")
    previous = files.get(name)
    if previous is not None and previous != raw:
        raise ValueError(f"conflicting notebook payloads for {name}")
    files[name] = raw


def _extract_notebook(path):
    notebook = json.loads(path.read_text(encoding="utf-8"))
    files = {}
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = _cell_source(cell)
        if source.startswith("%%writefile "):
            first, separator, body = source.partition("\n")
            if not separator:
                continue
            name = first.removeprefix("%%writefile ").strip()
            _add_file(files, name, body.encode("utf-8"))
            continue
        if "b85decode" not in source or "zlib.decompress" not in source:
            continue
        values = _literal_assignments(source)
        if isinstance(values.get("agent_payload"), str):
            _add_file(files, "main.py", _decode_payload(values["agent_payload"]))
        parts = values.get("_AGENT_B85_PARTS")
        if isinstance(parts, list) and parts and all(isinstance(part, str) for part in parts):
            _add_file(files, "main.py", _decode_payload("".join(parts)))
        payloads = values.get("payloads")
        if isinstance(payloads, dict):
            for name, encoded in payloads.items():
                if not isinstance(name, str) or not isinstance(encoded, str):
                    raise ValueError("unexpected public-agent payload map")
                _add_file(files, name, _decode_payload(encoded))
    if "main.py" not in files:
        raise ValueError(f"no main.py payload found in {path}")
    return files


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _audit_python(name, raw):
    text = raw.decode("utf-8")
    tree = ast.parse(text, filename=name)
    imports = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            calls.add(_call_name(node.func))
    flagged_imports = sorted(imports & DANGEROUS_IMPORTS)
    flagged_calls = sorted(call for call in calls if call in DANGEROUS_CALLS)
    return {
        "imports": sorted(imports),
        "flagged_imports": flagged_imports,
        "flagged_calls": flagged_calls,
    }


def extract_all():
    manifest = {"sources": []}
    for source_dir in sorted(path for path in SOURCE_ROOT.iterdir() if path.is_dir()):
        notebooks = sorted(source_dir.glob("*.ipynb"))
        if len(notebooks) != 1:
            raise ValueError(f"expected one notebook in {source_dir}, found {len(notebooks)}")
        notebook = notebooks[0]
        files = _extract_notebook(notebook)
        output = source_dir / "extracted"
        output.mkdir(exist_ok=True)
        records = []
        for name, raw in sorted(files.items()):
            audit = _audit_python(name, raw)
            destination = output / name
            destination.write_bytes(raw)
            records.append(
                {
                    "name": name,
                    "bytes": len(raw),
                    "sha256": _sha256(raw),
                    **audit,
                }
            )
        metadata_path = source_dir / "kernel-metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        manifest["sources"].append(
            {
                "directory": source_dir.name,
                "kernel": metadata.get("id"),
                "title": metadata.get("title"),
                "notebook": notebook.name,
                "notebook_sha256": _sha256(notebook.read_bytes()),
                "files": records,
            }
        )
    destination = SOURCE_ROOT / "extraction_manifest.json"
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(extract_all(), indent=2, sort_keys=True))
