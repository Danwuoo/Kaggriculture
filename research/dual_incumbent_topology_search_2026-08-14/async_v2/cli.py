"""CLI for coupled asynchronous topology development."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from library import build_library
from search import MAX_WORKERS, compile_smoke, run_search, status


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    library = commands.add_parser("build-library")
    library.add_argument("--output", type=Path, required=True)
    library.add_argument("--donor-limit", type=int, default=40)
    smoke = commands.add_parser("compile-smoke")
    smoke.add_argument("--library", type=Path, required=True)
    smoke.add_argument("--output", type=Path, required=True)
    smoke.add_argument("--population", type=int, default=8)
    search = commands.add_parser("search")
    search.add_argument("--library", type=Path, required=True)
    search.add_argument("--run-root", type=Path, required=True)
    search.add_argument("--population", type=int, default=6)
    search.add_argument("--generations", type=int, default=2)
    search.add_argument("--workers", type=int, choices=range(1, MAX_WORKERS + 1), default=15)
    search.add_argument("--opponent", action="append", dest="opponents")
    snapshot = commands.add_parser("status")
    snapshot.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build-library":
        result = build_library(args.output, donor_limit=args.donor_limit)
        print(json.dumps({"library_sha256": result["library_sha256"], "counts": {lane: len(row["motifs"]) for lane, row in result["lanes"].items()}, "output": str(args.output)}, sort_keys=True))
    elif args.command == "compile-smoke":
        result = compile_smoke(args.library, args.output, population=args.population)
        print(json.dumps({"compile_smoke_sha256": result["compile_smoke_sha256"], "output": str(args.output)}, sort_keys=True))
    elif args.command == "search":
        result = run_search(
            args.library, args.run_root, population=args.population, generations=args.generations,
            workers=args.workers, opponents=tuple(args.opponents or ("other_incumbent", "kaito_v21")),
        )
        print(json.dumps({"summary_sha256": result["summary_sha256"], "best_candidate_ids": result["best_candidate_ids"], "pass": result["pass"], "run_root": str(args.run_root)}, sort_keys=True))
    else:
        print(json.dumps(status(args.run_root), sort_keys=True))


if __name__ == "__main__":
    main()
