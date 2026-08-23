"""Development CLI for the maximum full-tape population search."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


LANE = Path(__file__).resolve().parents[1]
ROOT = LANE.parents[1]
if str(LANE) not in sys.path:
    sys.path.insert(0, str(LANE))

from max_search.checkpoint import RunManifest, RunState, atomic_json, read_status  # noqa: E402
from max_search.coordinator import (  # noqa: E402
    CandidateIndex, propose_generation, read_birth_shard, seed_index, write_birth_shard,
)
from max_search.contract import SearchContract, canonical_json, load_contract  # noqa: E402
from max_search.contexts import ContextRegistry, opponent_artifact_snapshot  # noqa: E402
from max_search.evolution import MutationEngine, island_layout  # noqa: E402
from max_search.evaluation import official_mutation_smoke, official_noop_smoke  # noqa: E402
from max_search.runner import (  # noqa: E402
    calibrate_execution, execution_status, prepare_execution, resource_estimate, run_execution,
)
from max_search.genome import FullTapeGenome, GenomeError, RootRegistry, candidate_lane  # noqa: E402
from max_search.preflight import source_snapshot  # noqa: E402


DEFAULT_CONTRACT = LANE / "max_search_contract.json"


def _write(path: Path, value: Any) -> None:
    atomic_json(path, value)


def _initial_population(
    contract: SearchContract,
    registry: RootRegistry,
    *,
    proposal_seed: int,
    per_island: int | None = None,
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]], dict[str, Any]]:
    engine = MutationEngine(registry, proposal_seed=proposal_seed)
    populations: dict[str, list[str]] = {}
    catalog: dict[str, dict[str, Any]] = {}
    collisions = 0
    for island in island_layout(contract):
        target = island.capacity if per_island is None else min(island.capacity, per_island)
        rows: list[str] = []
        for ordinal in range(target):
            base = engine.initial_genome(island, ordinal)
            genome = base
            attempt = 0
            while genome.candidate_id in catalog:
                collisions += 1
                attempt += 1
                if attempt > 4096:
                    raise RuntimeError(f"initial population saturated for {island.island_id}")
                # Generation zero stays sparse: choose one deterministic donor
                # action at one deterministic step relative to the selected
                # root. Large 24..719-turn neighborhoods begin in generation
                # one and never inflate the initialization catalog.
                donors = registry.roots(source_kind="deduplicated_public_tape") or registry.roots()
                token = hashlib.sha256(json.dumps(
                    [proposal_seed, island.island_id, ordinal, attempt],
                    separators=(",", ":"),
                ).encode("utf-8")).digest()
                step = int.from_bytes(token[:4], "big") % 719
                donor = donors[int.from_bytes(token[4:8], "big") % len(donors)]
                genome = base.with_actions({step: donor.action_at(step)}, registry.get(base.root_id))
            catalog[genome.candidate_id] = genome.to_dict()
            rows.append(genome.candidate_id)
        populations[island.island_id] = rows
    return populations, catalog, {
        "candidate_count": len(catalog),
        "collision_retries": collisions,
        "island_count": len(populations),
        "per_island": per_island or int(contract.scale["residents_per_island"]),
    }


def _load(args: argparse.Namespace) -> SearchContract:
    return load_contract(args.contract.resolve())


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    return _load(args).plan_summary()


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    result = command_validate(args)
    _write(args.output.resolve(), result)
    return result


def command_preflight(args: argparse.Namespace) -> dict[str, Any]:
    contract = _load(args)
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("preflight output root already exists and is nonempty")
    registry = RootRegistry.load_workspace(ROOT, include_public=not args.no_public_roots)
    sources = source_snapshot(ROOT, contract, registry)
    manifest = RunManifest.create(
        run_id=args.run_id,
        contract=contract,
        source_snapshot=sources,
        root_manifest=registry.manifest(),
        proposal_seed=args.proposal_seed,
        formal_execution_authorized=False,
    )
    populations, catalog, initial = _initial_population(contract, registry, proposal_seed=args.proposal_seed)
    state = RunState.initial(manifest, contract, populations)
    _write(output_root / "manifest.json", manifest.payload)
    _write(output_root / "initial_population.json", {
        "schema_version": 1,
        "manifest_sha256": manifest.sha256,
        "candidate_count": len(catalog),
        "candidates": catalog,
    })
    _write(output_root / "checkpoint.json", state.payload)
    result = {
        "run_root": str(output_root),
        "manifest_sha256": manifest.sha256,
        "contract_sha256": contract.sha256,
        "root_count": len(registry),
        "initial_population": initial,
        "formal_execution_authorized": False,
        "games_run": 0,
    }
    _write(output_root / "preflight_summary.json", result)
    return result


def command_miniature(args: argparse.Namespace) -> dict[str, Any]:
    contract = _load(args)
    registry = RootRegistry.load_workspace(ROOT, include_public=not args.no_public_roots)
    populations, catalog, initial = _initial_population(
        contract, registry, proposal_seed=args.proposal_seed, per_island=args.per_island,
    )
    engine = MutationEngine(registry, proposal_seed=args.proposal_seed)
    generated: set[str] = set(catalog)
    mutation_counts: dict[str, int] = {}
    for generation in range(1, args.generations):
        for island in island_layout(contract):
            parent_ids = populations[island.island_id]
            next_ids: list[str] = []
            for ordinal, parent_id in enumerate(parent_ids):
                parent = FullTapeGenome.from_dict(catalog[parent_id])
                mate = FullTapeGenome.from_dict(catalog[parent_ids[(ordinal + 1) % len(parent_ids)]])
                child, metadata = engine.child(parent, island, generation=generation, ordinal=ordinal, mate=mate)
                key = str(metadata["operation"])
                mutation_counts[key] = mutation_counts.get(key, 0) + 1
                if child.candidate_id in generated:
                    next_ids.append(parent_id)
                    continue
                generated.add(child.candidate_id)
                catalog[child.candidate_id] = child.to_dict()
                next_ids.append(child.candidate_id)
            populations[island.island_id] = next_ids
    result = {
        "schema_version": 1,
        "kind": "maximum_search_deterministic_miniature",
        "contract_sha256": contract.sha256,
        "proposal_seed": args.proposal_seed,
        "generations": args.generations,
        "islands": len(populations),
        "resident_candidates": sum(len(values) for values in populations.values()),
        "unique_candidates_seen": len(generated),
        "initial": initial,
        "mutation_counts": dict(sorted(mutation_counts.items())),
        "population_digest": __import__("hashlib").sha256(
            json.dumps(populations, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "games_run": 0,
        "formal_execution_authorized": False,
    }
    if args.output is not None:
        _write(args.output.resolve(), result)
    return result


def command_official_smoke(args: argparse.Namespace) -> dict[str, Any]:
    contract = _load(args)
    registry = RootRegistry.load_workspace(ROOT, include_public=False)
    sources = source_snapshot(ROOT, contract, registry)
    result = official_noop_smoke(registry, technical_seed=args.technical_seed)
    result["contract_sha256"] = contract.sha256
    result["source_snapshot"] = sources
    if args.output is not None:
        _write(args.output.resolve(), result)
    if not result["passed"]:
        raise RuntimeError("official-engine no-op smoke failed")
    return result


def command_official_mutation_smoke(args: argparse.Namespace) -> dict[str, Any]:
    contract = _load(args)
    registry = RootRegistry.load_workspace(ROOT, include_public=False)
    sources = source_snapshot(ROOT, contract, registry)
    result = official_mutation_smoke(registry, technical_seed=args.technical_seed)
    result["contract_sha256"] = contract.sha256
    result["source_snapshot"] = sources
    if args.output is not None:
        _write(args.output.resolve(), result)
    if not result["passed"]:
        raise RuntimeError("official-engine mutation smoke failed")
    return result


def command_freeze_contexts(args: argparse.Namespace) -> dict[str, Any]:
    draft = json.loads(args.draft.resolve().read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise RuntimeError("context draft root must be an object")
    stages = draft.get("stages")
    if not isinstance(stages, dict):
        raise RuntimeError("context draft lacks stages")
    families = sorted({
        row["opponent_family"]
        for rows in stages.values() if isinstance(rows, list)
        for row in rows if isinstance(row, dict) and isinstance(row.get("opponent_family"), str)
    })
    artifacts = opponent_artifact_snapshot(ROOT, families)
    registry = ContextRegistry.create(draft, opponent_artifacts=artifacts)
    _write(args.output.resolve(), registry.payload)
    return {
        "schema_version": 1,
        "kind": "maximum_search_context_registry_frozen",
        "output": str(args.output.resolve()),
        "mode": registry.mode,
        "registry_sha256": registry.sha256,
        "t0_contexts": len(registry.contexts("t0")),
        "t1_contexts": len(registry.contexts("t1")),
        "holdout_contexts": len(registry.contexts("holdout")),
        "formal_execution_authorized": False,
    }


def command_prepare_execution(args: argparse.Namespace) -> dict[str, Any]:
    contract = _load(args)
    registry = ContextRegistry.load(
        args.context_registry.resolve(), require_mode="formal" if args.formal else "development",
    )
    workers = int(args.workers)
    max_in_flight = int(args.max_in_flight) if args.max_in_flight is not None else workers * 4
    return prepare_execution(
        workspace=ROOT, contract=contract, preflight_root=args.preflight_root.resolve(),
        context_registry=registry, output_root=args.output_root.resolve(), run_id=args.run_id,
        physical_workers=workers, max_in_flight=max_in_flight, backend=args.backend,
        formal_execution_authorized=bool(args.formal),
        formal_authorization_id=args.formal_authorization_id,
        development_generations=None if args.formal else args.generations,
        development_residents_per_island=None if args.formal else args.residents_per_island,
        development_births_per_island=None if args.formal else args.births_per_island,
        development_t1_promotions_per_island=None if args.formal else args.t1_promotions_per_island,
        calibration_path=args.calibration.resolve() if args.calibration is not None else None,
    )


def command_run_execution(args: argparse.Namespace) -> dict[str, Any]:
    return run_execution(
        workspace=ROOT, contract=_load(args), run_root=args.output_root.resolve(),
        stop_after_generation=args.stop_after_generation,
    )


def command_resource_estimate(args: argparse.Namespace) -> dict[str, Any]:
    result = resource_estimate(
        contract=_load(args), measured_games_per_second=args.games_per_second,
        measured_bytes_per_receipt=args.bytes_per_receipt, physical_workers=args.workers,
    )
    if args.output is not None:
        _write(args.output.resolve(), result)
    return result


def command_calibrate_execution(args: argparse.Namespace) -> dict[str, Any]:
    return calibrate_execution(
        workspace=ROOT, contract=_load(args), run_root=args.output_root.resolve(),
        output=args.output.resolve(),
    )


def command_dry_generation(args: argparse.Namespace) -> dict[str, Any]:
    contract = _load(args)
    if args.generation != 1:
        raise RuntimeError("development dry-generation is intentionally limited to generation 1")
    run_root = args.output_root.resolve()
    summary_path = run_root / f"development_generation_{args.generation:04d}_summary.json"
    prepared_path = run_root / f"development_generation_{args.generation:04d}_prepared.json"
    shard_path = run_root / f"development_generation_{args.generation:04d}_births.jsonl.gz"

    manifest = RunManifest.load(run_root / "manifest.json", expected_contract_sha256=contract.sha256)
    state = RunState.load(run_root / "checkpoint.json", manifest, contract)
    initial = json.loads((run_root / "initial_population.json").read_text(encoding="utf-8"))
    if initial.get("manifest_sha256") != manifest.sha256:
        raise RuntimeError("initial population manifest hash mismatch")
    catalog = initial.get("candidates")
    populations = state.payload.get("population_ids")
    if not isinstance(catalog, dict) or not isinstance(populations, dict):
        raise RuntimeError("initial population artifact is malformed")
    registry = RootRegistry.load_workspace(ROOT, include_public=True)
    current_sources = source_snapshot(ROOT, contract, registry)
    if canonical_json(current_sources) != canonical_json(manifest.payload.get("source_snapshot")):
        raise RuntimeError("source, engine, control, route, or implementation drift since preflight")
    if registry.manifest()["manifest_sha256"] != manifest.payload["root_manifest"]["manifest_sha256"]:
        raise RuntimeError("root registry drift since preflight")
    layout = island_layout(contract)
    island_lanes = {island.island_id: island.lane for island in layout}

    def restore_artifact(metadata: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
        if set(metadata) != {
            "schema_version", "kind", "manifest_sha256", "formal_execution_authorized",
            "games_run", "generation", "birth_shard",
        }:
            raise RuntimeError("dry-generation summary schema is not closed")
        if (type(metadata.get("schema_version")) is not int or metadata.get("schema_version") != 1
                or metadata.get("kind") != "maximum_search_development_dry_generation"
                or metadata.get("formal_execution_authorized") is not False
                or type(metadata.get("games_run")) is not int or metadata.get("games_run") != 0):
            raise RuntimeError("dry-generation summary claims invalid status or games")
        if metadata.get("manifest_sha256") != manifest.sha256:
            raise RuntimeError("dry-generation summary manifest mismatch")
        shard = metadata.get("birth_shard", {})
        if (not isinstance(shard, dict)
                or set(shard) != {"path", "rows", "canonical_uncompressed_sha256", "bytes"}
                or shard.get("path") != str(shard_path)
                or type(shard.get("rows")) is not int or type(shard.get("bytes")) is not int
                or not isinstance(shard.get("canonical_uncompressed_sha256"), str)
                or len(shard.get("canonical_uncompressed_sha256")) != 64
                or not shard_path.is_file() or shard.get("bytes") != shard_path.stat().st_size):
            raise RuntimeError("existing dry-generation shard size drift")
        restored = list(read_birth_shard(shard_path))
        canonical = hashlib.sha256("".join(
            json.dumps(row.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in restored
        ).encode("utf-8")).hexdigest()
        if len(restored) != shard.get("rows") or canonical != shard.get("canonical_uncompressed_sha256"):
            raise RuntimeError("existing dry-generation shard content drift")
        if any(row.generation != args.generation for row in restored):
            raise RuntimeError("birth shard contains the wrong generation")
        expected_counts = {
            island.island_id: min(contract.island_birth_quotas(args.generation)[island.index], args.per_island)
            for island in layout
        }
        actual_ordinals: dict[str, list[int]] = {island.island_id: [] for island in layout}
        for row in restored:
            if row.island_id not in actual_ordinals:
                raise RuntimeError("birth shard contains an unknown island")
            expected_lane = island_lanes[row.island_id]
            try:
                parent_lane = candidate_lane(row.parent_id)
                mate_lane = candidate_lane(row.mate_id) if row.mate_id is not None else expected_lane
            except GenomeError as error:
                raise RuntimeError("birth shard contains malformed parent identity") from error
            if row.genome.lane != expected_lane or parent_lane != expected_lane or mate_lane != expected_lane:
                raise RuntimeError("birth shard candidate lineage crosses island lane ownership")
            actual_ordinals[row.island_id].append(row.ordinal)
        if any(sorted(actual_ordinals[island]) != list(range(expected)) for island, expected in expected_counts.items()):
            raise RuntimeError("birth shard island quota or ordinal drift")
        generation = metadata.get("generation")
        if not isinstance(generation, dict) or set(generation) != {
            "generation", "contract_birth_target", "effective_birth_target", "births",
            "rejected_duplicate_proposals", "saturated_islands", "candidate_index_count",
            "development_limited",
        }:
            raise RuntimeError("dry-generation statistics schema is not closed")
        expected_births = sum(expected_counts.values())
        expected_statistics = {
            "generation": args.generation,
            "contract_birth_target": contract.birth_quota(args.generation),
            "effective_birth_target": expected_births,
            "births": expected_births,
            "saturated_islands": [],
            "candidate_index_count": len(catalog) + expected_births,
            "development_limited": True,
        }
        integer_fields = {
            "generation", "contract_birth_target", "effective_birth_target", "births", "candidate_index_count",
        }
        if any(type(generation.get(key)) is not int for key in integer_fields):
            raise RuntimeError("dry-generation integer statistics are malformed")
        if type(generation.get("development_limited")) is not bool:
            raise RuntimeError("dry-generation development flag is malformed")
        if any(generation.get(key) != value for key, value in expected_statistics.items()):
            raise RuntimeError("dry-generation statistics differ from requested execution")
        rejected = generation.get("rejected_duplicate_proposals")
        if not isinstance(rejected, int) or isinstance(rejected, bool) or rejected < 0:
            raise RuntimeError("dry-generation duplicate count is malformed")
        return restored, metadata

    index_path = run_root / "development_candidate_index.sqlite"
    with CandidateIndex(index_path, manifest_sha256=manifest.sha256) as index:
        if index.count() == 0:
            seed_index(index, catalog, populations, island_lanes=island_lanes)
        else:
            index.validate_initial(catalog, populations, island_lanes=island_lanes)

        if summary_path.is_file():
            if prepared_path.exists():
                raise RuntimeError("both final and prepared generation summaries exist")
            existing = json.loads(summary_path.read_text(encoding="utf-8"))
            restored, existing = restore_artifact(existing)
            index.reconcile_generation(args.generation, restored, island_lanes=island_lanes)
            if index.generations() != {0, args.generation} or index.count() != len(catalog) + len(restored):
                raise RuntimeError("candidate index contains rows outside the development shard")
            return existing

        if prepared_path.is_file():
            prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
            restored, prepared = restore_artifact(prepared)
            index.reconcile_generation(args.generation, restored, island_lanes=island_lanes)
            if index.generations() != {0, args.generation} or index.count() != len(catalog) + len(restored):
                raise RuntimeError("candidate index contains rows outside the prepared development shard")
            os.replace(prepared_path, summary_path)
            return prepared

        if index.generations() != {0} or index.count() != len(catalog):
            raise RuntimeError("candidate index contains an unjournaled or unexpected generation")
        births, summary = propose_generation(
            contract=contract, registry=registry,
            proposal_seed=int(manifest.payload["proposal_seed"]), generation=args.generation,
            populations=populations, catalog=catalog, index=index,
            development_limit_per_island=args.per_island,
        )
        shard = write_birth_shard(shard_path, births)
        if index.generations() != {0, args.generation} or index.count() != len(catalog) + len(births):
            raise RuntimeError("candidate index proposal transaction contains unexpected rows")
        result = {
            "schema_version": 1,
            "kind": "maximum_search_development_dry_generation",
            "manifest_sha256": manifest.sha256,
            "formal_execution_authorized": False,
            "games_run": 0,
            "generation": summary,
            "birth_shard": shard,
        }
        # Prepared metadata is durable before the SQLite transaction commits.
        # Recovery can then reconcile either a rolled-back or committed index
        # against the exact canonical shard before publishing the final name.
        _write(prepared_path, result)
        index.commit()
        if index.generations() != {0, args.generation} or index.count() != len(catalog) + len(births):
            raise RuntimeError("committed candidate index differs from prepared generation")
        os.replace(prepared_path, summary_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-contract")
    validate.set_defaults(handler=command_validate)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--output", type=Path, required=True)
    plan.set_defaults(handler=command_plan)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--output-root", type=Path, required=True)
    preflight.add_argument("--run-id", required=True)
    preflight.add_argument("--proposal-seed", type=int, required=True)
    preflight.add_argument("--no-public-roots", action="store_true")
    preflight.set_defaults(handler=command_preflight)

    miniature = subparsers.add_parser("miniature")
    miniature.add_argument("--proposal-seed", type=int, default=271828)
    miniature.add_argument("--per-island", type=int, default=2, choices=range(1, 17))
    miniature.add_argument("--generations", type=int, default=3, choices=range(1, 17))
    miniature.add_argument("--output", type=Path)
    miniature.add_argument("--no-public-roots", action="store_true")
    miniature.set_defaults(handler=command_miniature)

    official = subparsers.add_parser("official-smoke")
    official.add_argument("--technical-seed", type=int, default=811407)
    official.add_argument("--output", type=Path)
    official.set_defaults(handler=command_official_smoke)

    mutation_smoke = subparsers.add_parser("official-mutation-smoke")
    mutation_smoke.add_argument("--technical-seed", type=int, default=811407)
    mutation_smoke.add_argument("--output", type=Path)
    mutation_smoke.set_defaults(handler=command_official_mutation_smoke)

    freeze_contexts = subparsers.add_parser("freeze-contexts")
    freeze_contexts.add_argument("--draft", type=Path, required=True)
    freeze_contexts.add_argument("--output", type=Path, required=True)
    freeze_contexts.set_defaults(handler=command_freeze_contexts)

    prepare_execution_parser = subparsers.add_parser("prepare-execution")
    prepare_execution_parser.add_argument("--preflight-root", type=Path, required=True)
    prepare_execution_parser.add_argument("--context-registry", type=Path, required=True)
    prepare_execution_parser.add_argument("--output-root", type=Path, required=True)
    prepare_execution_parser.add_argument("--run-id", required=True)
    prepare_execution_parser.add_argument("--workers", type=int, required=True)
    prepare_execution_parser.add_argument("--max-in-flight", type=int)
    prepare_execution_parser.add_argument("--backend", choices=("official", "deterministic_mock"), default="official")
    prepare_execution_parser.add_argument("--generations", type=int, default=3)
    prepare_execution_parser.add_argument("--residents-per-island", type=int, default=2)
    prepare_execution_parser.add_argument("--births-per-island", type=int, default=2)
    prepare_execution_parser.add_argument("--t1-promotions-per-island", type=int, default=1)
    prepare_execution_parser.add_argument("--formal", action="store_true")
    prepare_execution_parser.add_argument("--formal-authorization-id")
    prepare_execution_parser.add_argument("--calibration", type=Path)
    prepare_execution_parser.set_defaults(handler=command_prepare_execution)

    run_execution_parser = subparsers.add_parser("run-execution")
    run_execution_parser.add_argument("--output-root", type=Path, required=True)
    run_execution_parser.add_argument("--stop-after-generation", type=int)
    run_execution_parser.set_defaults(handler=command_run_execution)

    execution_status_parser = subparsers.add_parser("execution-status")
    execution_status_parser.add_argument("--output-root", type=Path, required=True)
    execution_status_parser.set_defaults(handler=lambda args: execution_status(args.output_root.resolve()))

    calibrate = subparsers.add_parser("calibrate-execution")
    calibrate.add_argument("--output-root", type=Path, required=True)
    calibrate.add_argument("--output", type=Path, required=True)
    calibrate.set_defaults(handler=command_calibrate_execution)

    estimate = subparsers.add_parser("resource-estimate")
    estimate.add_argument("--games-per-second", type=float, required=True)
    estimate.add_argument("--bytes-per-receipt", type=float, required=True)
    estimate.add_argument("--workers", type=int, required=True)
    estimate.add_argument("--output", type=Path)
    estimate.set_defaults(handler=command_resource_estimate)

    dry_generation = subparsers.add_parser("dry-generation")
    dry_generation.add_argument("--output-root", type=Path, required=True)
    dry_generation.add_argument("--generation", type=int, default=1)
    dry_generation.add_argument("--per-island", type=int, default=2, choices=range(1, 65))
    dry_generation.set_defaults(handler=command_dry_generation)

    status = subparsers.add_parser("status")
    status.add_argument("--output-root", type=Path, required=True)
    status.set_defaults(handler=lambda args: read_status(args.output_root.resolve()))

    args = parser.parse_args()
    result = args.handler(args)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
