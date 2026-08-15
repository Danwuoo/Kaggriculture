"""Exercise the formal launch process flags without running a game."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from library import atomic_json


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    stdout_path = args.output.with_suffix(".stdout.log")
    stderr_path = args.output.with_suffix(".stderr.log")
    code = (
        "import json,sys; "
        f"sys.path.insert(0,{str(HERE)!r}); "
        "from evaluator import engine_fingerprint; "
        "print(json.dumps(engine_fingerprint(),sort_keys=True))"
    )
    command = [sys.executable, "-c", code]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=flags,
            close_fds=True,
        )
        returncode = process.wait(timeout=30)
    stdout_text = stdout_path.read_text(encoding="utf-8")
    stderr_text = stderr_path.read_text(encoding="utf-8")
    engine = json.loads(stdout_text) if returncode == 0 else None
    result = {
        "schema_version": 1,
        "purpose": "no-game detached engine fingerprint probe",
        "command": command,
        "creationflags": int(flags),
        "returncode": int(returncode),
        "engine": engine,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "stderr_text": stderr_text,
        "formal_fresh_seeds_executed": False,
        "pass": returncode == 0,
    }
    atomic_json(args.output, result)
    print(json.dumps({"pass": result["pass"], "returncode": returncode}, sort_keys=True))
    if returncode:
        raise SystemExit(returncode)


if __name__ == "__main__":
    main()
