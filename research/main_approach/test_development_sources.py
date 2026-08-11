"""Source, builder, and entrypoint contracts for editable main approaches."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
APPROACH_ROOT = Path(__file__).resolve().parent
STRATEGIES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")


def _route_digest(actions) -> str:
    raw = json.dumps(actions, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(path.parent))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = old_path
    return module


class DevelopmentSourceTests(unittest.TestCase):
    def test_readable_routes_match_generated_standalones(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                base = APPROACH_ROOT / strategy
                actions = json.loads(
                    (base / "development" / "route_actions.json").read_text(encoding="utf-8")
                )
                manifest = json.loads(
                    (base / "development" / "source_manifest.json").read_text(encoding="utf-8")
                )
                standalone = _load_module(base / "main.py", f"standalone_{strategy}")
                self.assertEqual(719, len(actions))
                self.assertEqual(manifest["route_sha256"], _route_digest(actions))
                self.assertEqual(actions, standalone._LEGACY_ACTIONS)

    def test_development_sources_are_not_compressed(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                development = APPROACH_ROOT / strategy / "development"
                source = "\n".join(
                    path.read_text(encoding="utf-8")
                    for path in development.glob("*.py")
                    if path.name not in {"build_standalone.py", "_generated_main.py"}
                )
                self.assertNotIn("b85decode", source)
                self.assertNotIn("zlib.decompress", source)

    def test_generated_standalones_are_current(self):
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy):
                builder = APPROACH_ROOT / strategy / "development" / "build_standalone.py"
                result = subprocess.run(
                    [sys.executable, str(builder), "--check"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
