"""Async V3 development and frozen formal-orchestration command surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from compiler import compile_fixture_anchors, compile_genome, phenotype_report
from fixture import HERE, load_fixture, verify_frozen_evidence
from model import AsyncGenome, ConstantGene, MarketEditGene, payload_hash
from scheduler import atomic_json
from formal_run import (
    DEFAULT_GENERATIONS,
    DEFAULT_POPULATION,
    DEFAULT_PROPOSAL_SEED,
    formal_status,
    preflight,
    run_formal,
)


ARTIFACTS = HERE / "artifacts" / "development"
TECHNICAL_SEED = 811407


def _technical_seed(value: int) -> None:
    if int(value) != TECHNICAL_SEED:
        raise PermissionError(f"development commands accept only technical seed {TECHNICAL_SEED}")


def verify_fixtures() -> dict:
    return verify_frozen_evidence(HERE / "fixtures" / "e1b_regression_fixtures.json")


def compile_smoke(technical_seed: int) -> dict:
    _technical_seed(technical_seed)
    anchors = compile_fixture_anchors(HERE / "fixtures" / "e1b_regression_fixtures.json")
    coverage = {}
    islands = {}
    for lane in ("v27_current_meta", "boatlee_v16_rc2_market_relay"):
        rows = []
        for index, opcode in enumerate(("HIRE", "BUY_LAND", "BUY_ANIMAL", "BUY_SEED", "BUY_PRODUCT", "SELL")):
            order = {
                "HIRE": ("HIRE",), "BUY_LAND": ("BUY_LAND",), "BUY_ANIMAL": ("BUY_ANIMAL", "COW", 1),
                "BUY_SEED": ("BUY_SEED", "MELON", 1), "BUY_PRODUCT": ("BUY_PRODUCT", "WHEAT", 1), "SELL": ("SELL", "WOOL", 1),
            }[opcode]
            candidate = compile_genome(lane, AsyncGenome(lane, market_edits=(MarketEditGene(0, index, "insert", index, order=order),)))
            rows.append({"opcode": opcode, "candidate_id": candidate.candidate_id, "accepted": candidate.accepted})
        coverage[lane] = rows
        anchor = next(row for row in anchors if row.lane == lane)
        prefix = "v27" if lane == "v27_current_meta" else "boatlee"
        active = compile_genome(lane, AsyncGenome(lane, route_blocks=anchor.genome.route_blocks, constants=(ConstantGene(f"{prefix}_market_order_cap", 4),)))
        inactive = compile_genome(lane, AsyncGenome(lane, constants=(ConstantGene(f"{prefix}_market_order_cap", 10),)))
        islands[lane] = phenotype_report((anchor, active, inactive))
    body = {
        "schema_version": 3, "technical_seed": TECHNICAL_SEED, "formal_fresh_seeds_executed": False,
        "fixture": verify_fixtures(), "anchors": [
            {"lane": row.lane, "fixture_candidate_id": row.fixture_candidate_id, "candidate_id": row.candidate_id, "accepted": row.accepted, "fixture_match": row.fixture_match}
            for row in anchors
        ],
        "opcode_coverage": coverage, "island_capacity": islands,
    }
    body["pass"] = body["fixture"]["pass"] and all(row.accepted and row.fixture_match for row in anchors) and all(all(item["accepted"] for item in rows) for rows in coverage.values()) and all(bool(row["active_constants"]) and bool(row["inactive_constants"]) for row in islands.values())
    body["compile_smoke_sha256"] = payload_hash({key: value for key, value in body.items() if key != "compile_smoke_sha256"})
    atomic_json(ARTIFACTS / "compile_smoke.json", body)
    return body


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("verify-fixtures")
    smoke = command.add_parser("compile-smoke")
    smoke.add_argument("--technical-seed", type=int, required=True)
    preflight_parser = command.add_parser("preflight")
    preflight_parser.add_argument("--output-root", type=Path, required=True)
    preflight_parser.add_argument("--proposal-seed", type=int, default=DEFAULT_PROPOSAL_SEED)
    preflight_parser.add_argument("--population", type=int, default=DEFAULT_POPULATION)
    preflight_parser.add_argument("--generations", type=int, default=DEFAULT_GENERATIONS)
    preflight_parser.add_argument("--workers", type=int, required=True)
    preflight_parser.add_argument("--resume", action="store_true")
    status = command.add_parser("status")
    status.add_argument("--output-root", type=Path, required=True)
    for name in ("run", "search"):
        runner = command.add_parser(name)
        runner.add_argument("--output-root", type=Path, required=True)
        runner.add_argument("--workers", type=int, required=True)
        runner.add_argument("--resume", action="store_true")
        runner.add_argument("--dry-run", action="store_true")
        runner.add_argument("--execute-retained-e1c", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "verify-fixtures":
        result = verify_fixtures()
    elif args.command == "compile-smoke":
        result = compile_smoke(args.technical_seed)
    elif args.command == "preflight":
        result = preflight(args.output_root, proposal_seed=args.proposal_seed, population=args.population, generations=args.generations, workers=args.workers, resume=args.resume)
    elif args.command == "status":
        result = formal_status(args.output_root)
    else:
        result = run_formal(args.output_root, workers=args.workers, resume=args.resume, dry_run=args.dry_run, execute_retained_e1c=args.execute_retained_e1c)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
