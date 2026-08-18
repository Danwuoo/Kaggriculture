"""Command-line surface for development-only topology search."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from atlas import build_atlas, first_irreversible_divergence
from authority import validate_registry
from compiler import compile_candidate, technical_evaluate
from model import BranchSpec
from proposal import rank_proposals
from verify import calibration, write_report


LANE = Path(__file__).resolve().parent


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    atlas = commands.add_parser("build-atlas")
    atlas.add_argument("--output", type=Path, required=True)
    atlas.add_argument("--skip-channel-entropy", action="store_true")
    forensics = commands.add_parser("forensics")
    forensics.add_argument("--control", type=Path, required=True)
    forensics.add_argument("--candidate", type=Path, required=True)
    forensics.add_argument("--output", type=Path, required=True)
    propose = commands.add_parser("propose")
    propose.add_argument("--lane", choices=("v27_current_meta", "boatlee_v16_rc2_market_relay"), required=True)
    propose.add_argument("--output", type=Path, required=True)
    compile_parser = commands.add_parser("compile")
    compile_parser.add_argument("--spec", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    technical = commands.add_parser("technical-evaluate")
    technical.add_argument("--candidate", type=Path, required=True)
    report = commands.add_parser("report")
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--include-entropy", action="store_true")
    args = parser.parse_args()

    if args.command == "validate":
        result = {"authority": validate_registry(), "calibration": calibration()}
    elif args.command == "build-atlas":
        result = build_atlas(include_channel_entropy=not args.skip_channel_entropy); _write(args.output, result)
    elif args.command == "forensics":
        result = first_irreversible_divergence(_read(args.control), _read(args.candidate)); _write(args.output, result)
    elif args.command == "propose":
        motifs = _read(LANE / "frontier_motifs.json")["motifs"]
        result = {"lane": args.lane, "development_budget_only": True, "proposals": rank_proposals(motifs, args.lane)}; _write(args.output, result)
    elif args.command == "compile":
        result = compile_candidate(BranchSpec.from_dict(_read(args.spec)), args.output)
    elif args.command == "technical-evaluate":
        result = technical_evaluate(args.candidate)
    else:
        result = write_report(args.output, include_entropy=args.include_entropy)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
