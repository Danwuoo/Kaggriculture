"""Safely extract public Kaggriculture agents from downloaded notebooks.

Notebook cells are parsed as data and are never executed.  The supported public
notebook patterns are direct ``%%writefile`` cells and base85+zlib literals.
"""

from __future__ import annotations

import ast
import base64
import binascii
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


def _decode_zlib(compressed):
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, MAX_EXTRACTED_BYTES + 1)
    if len(raw) > MAX_EXTRACTED_BYTES or decoder.unconsumed_tail:
        raise ValueError("compressed notebook payload exceeds extraction limit")
    raw += decoder.flush(MAX_EXTRACTED_BYTES + 1 - len(raw))
    if len(raw) > MAX_EXTRACTED_BYTES or not decoder.eof:
        raise ValueError("invalid or oversized compressed notebook payload")
    return raw


def _bounded(value):
    if isinstance(value, (bytes, str)) and len(value) > MAX_EXTRACTED_BYTES * 2:
        raise ValueError("notebook literal exceeds extraction limit")
    return value


def _safe_value(node, values):
    """Evaluate only the literal codec expressions used by public notebooks."""

    if isinstance(node, ast.Constant):
        return _bounded(node.value)
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise ValueError(f"unknown safe value: {node.id}")
        return values[node.id]
    if isinstance(node, ast.List):
        return [_safe_value(item, values) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_safe_value(item, values) for item in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _safe_value(key, values): _safe_value(value, values)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _bounded(_safe_value(node.left, values) + _safe_value(node.right, values))
    if not isinstance(node, ast.Call):
        raise ValueError(f"unsupported safe expression: {type(node).__name__}")

    if node.keywords or len(node.args) != 1:
        raise ValueError("unsupported safe call signature")
    argument = _safe_value(node.args[0], values)
    function = node.func
    if isinstance(function, ast.Attribute) and function.attr == "join":
        separator = _safe_value(function.value, values)
        return _bounded(separator.join(argument))
    if isinstance(function, ast.Attribute) and function.attr == "encode":
        if not isinstance(argument, str):
            raise ValueError("encode codec name must be a string")
        source = _safe_value(function.value, values)
        if not isinstance(source, str) or argument.lower().replace("-", "") != "ascii":
            raise ValueError("only ASCII payload encoding is supported")
        return _bounded(source.encode("ascii"))
    if isinstance(function, ast.Attribute) and function.attr == "decode":
        if not isinstance(argument, str):
            raise ValueError("decode codec name must be a string")
        source = _safe_value(function.value, values)
        codec = argument.lower().replace("-", "")
        if not isinstance(source, bytes) or codec not in {"ascii", "utf8"}:
            raise ValueError("unsupported payload decoding")
        return _bounded(source.decode("utf-8" if codec == "utf8" else "ascii"))

    call = ""
    if isinstance(function, ast.Name):
        call = function.id
    elif isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
        call = f"{function.value.id}.{function.attr}"
    if call in {"base64.b85decode", "b85decode"}:
        return _bounded(base64.b85decode(argument))
    if call in {"base64.b64decode", "b64decode"}:
        return _bounded(base64.b64decode(argument))
    if call in {"zlib.decompress", "decompress"}:
        if not isinstance(argument, bytes):
            raise ValueError("zlib payload must be bytes")
        return _decode_zlib(argument)
    raise ValueError(f"unsupported safe call: {call or type(function).__name__}")


def _safe_assignments(source, initial=None):
    tree = ast.parse(source)
    values = dict(initial or {})
    history = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            value = _safe_value(node.value, values)
        except (ValueError, TypeError, KeyError, binascii.Error, zlib.error):
            continue
        values[target.id] = value
        history.append((target.id, value))
    return values, history


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
    safe_values = {}
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
        try:
            values, history = _safe_assignments(source, safe_values)
        except SyntaxError:
            continue
        safe_values.update(values)
        for name, value in history:
            if name not in {"AGENT_SOURCE", "agent_bytes", "agent_source", "payload", "raw"}:
                continue
            raw = value.encode("utf-8") if isinstance(value, str) else value
            if isinstance(raw, bytes):
                files["main.py"] = raw
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
