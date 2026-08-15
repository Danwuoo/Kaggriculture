"""Run the bounded E1b development verification commands and retain output."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from evaluator import TECHNICAL_SEED, engine_fingerprint
from library import atomic_json
from model import payload_hash


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def _run(name: str, command: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    return {
        "name": name,
        "command": command,
        "returncode": int(completed.returncode),
        "wall_seconds": time.perf_counter() - started,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "pass": completed.returncode == 0,
    }


def run(output: Path, transcript: Path, technical_run_root: Path) -> dict[str, Any]:
    commands = [
        (
            "async_v2_unit_property_integration",
            [sys.executable, "-m", "unittest", "discover", "-s", str(HERE.relative_to(ROOT)), "-p", "test_*.py", "-v"],
        ),
        (
            "v27_builder_check",
            [sys.executable, r"research\main_approach\v27_current_meta\development\build_standalone.py", "--check"],
        ),
        (
            "boatlee_builder_check",
            [sys.executable, r"research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py", "--check"],
        ),
        (
            "shared_source_contract",
            [sys.executable, "-m", "unittest", "research.main_approach.test_development_sources", "-v"],
        ),
        (
            "technical_status_read_only",
            [sys.executable, str(HERE / "cli.py"), "status", "--run-root", str(technical_run_root)],
        ),
        ("git_diff_check", ["git", "diff", "--check"]),
        ("git_status", ["git", "status", "-sb"]),
    ]
    rows = [_run(name, command) for name, command in commands]
    engine = engine_fingerprint()
    body = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "E1b technical-only development verification",
        "technical_seed": TECHNICAL_SEED,
        "evaluation_seeds": [TECHNICAL_SEED],
        "formal_fresh_seeds_executed": False,
        "e1_seeds_reexecuted": False,
        "e2_games_executed": False,
        "engine": engine,
        "commands": rows,
        "pass": all(row["pass"] for row in rows),
    }
    result = {**body, "machine_checks_sha256": payload_hash(body)}
    atomic_json(output, result)
    transcript.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Kaggriculture Async E1b technical-only command transcript",
        f"created_at_utc={body['created_at_utc']}",
        f"technical_seed={TECHNICAL_SEED}",
        "formal_fresh_seeds_executed=false",
        "e1_seeds_reexecuted=false",
        "e2_games_executed=false",
        "",
    ]
    for row in rows:
        lines.extend((
            f"[{row['name']}]",
            "command=" + json.dumps(row["command"], ensure_ascii=True),
            f"returncode={row['returncode']} wall_seconds={row['wall_seconds']:.6f}",
            "stdout:",
            row["stdout"].rstrip(),
            "stderr:",
            row["stderr"].rstrip(),
            "",
        ))
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--technical-run-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output, args.transcript, args.technical_run_root)
    print(json.dumps({"pass": result["pass"], "sha256": result["machine_checks_sha256"], "output": str(args.output)}, sort_keys=True))
