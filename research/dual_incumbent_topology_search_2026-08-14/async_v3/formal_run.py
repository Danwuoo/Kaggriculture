"""Frozen, resumable E1c orchestration.

The module deliberately separates *preparing* a retained-seed run from
executing it.  Development calls only ``dry_mock`` and cannot reach the game
engine.  A later authorized call must opt in to ``formal_exact`` explicitly.
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from compiler import compile_genome, compile_fixture_anchors, phenotype_report
from evaluator import CONTROLS, FORMAL_RETAINED_SEEDS, engine_fingerprint, formal_finalist_parity
from evolution import initial_lane_roots, next_generation, refill_population
from fixture import HERE, file_sha256, load_fixture, verify_frozen_evidence
from model import AsyncGenome, CompiledCandidate, LANES, compiled_from_payload, payload_hash
from ranking import rank_frontiers
from scheduler import SchedulerFailure, atomic_json, canonical_job_id, evaluate_jobs, load_resume, read_status


FORMAL_OPPONENTS = ("other_incumbent", "kaito_v21")
FORMAL_SEATS = (0, 1)
FORMAL_SEED_REGISTRY = tuple(
    {"seed": seed, "classification": "retained_consumed", "fresh": False, "purpose": "e1c_retained_only"}
    for seed in FORMAL_RETAINED_SEEDS
)
DEFAULT_POPULATION = 12
DEFAULT_GENERATIONS = 2
DEFAULT_PROPOSAL_SEED = 271828


def _registry_hash() -> str:
    return payload_hash({"schema_version": 3, "seeds": FORMAL_SEED_REGISTRY, "opponents": FORMAL_OPPONENTS, "seats": FORMAL_SEATS})


def _context_rows(lane: str) -> list[dict[str, Any]]:
    return [
        {"lane": lane, "opponent": opponent, "seed": seed["seed"], "seat": seat}
        for opponent in FORMAL_OPPONENTS for seed in FORMAL_SEED_REGISTRY for seat in FORMAL_SEATS
    ]


def _compile_population(fixture_path: Path, population: int, generations: int, proposal_seed: int) -> tuple[dict[str, list[list[CompiledCandidate]]], dict[str, Any]]:
    roots = initial_lane_roots(fixture_path)
    if population < max(len(rows) for rows in roots.values()):
        raise ValueError("population must contain control, all fixture roots, and explicit remove-one ablations")
    output: dict[str, list[list[CompiledCandidate]]] = {lane: [] for lane in LANES}
    saturation: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}
    for lane in LANES:
        genomes, report = refill_population(tuple(roots[lane]), target=population, seed=proposal_seed, max_attempts=population * 32)
        saturation[lane].append(report)
        for generation in range(generations):
            compiled = [compile_genome(lane, genome) for genome in genomes]
            accepted_by_id = {row.candidate_id: row for row in compiled if row.accepted}
            accepted = [accepted_by_id[key] for key in sorted(accepted_by_id)]
            if not accepted:
                raise RuntimeError(f"lane {lane} generation {generation} has no accepted proposals")
            output[lane].append(accepted)
            if generation + 1 < generations:
                genomes, report = next_generation(
                    [row.genome for row in accepted], target=population, proposal_seed=proposal_seed,
                    generation=generation + 1, max_attempts=population * 32,
                )
                saturation[lane].append(report)
    anchors = compile_fixture_anchors(fixture_path)
    root_ids = {row.fixture_candidate_id for row in anchors}
    present = {
        lane: sorted(
            row.fixture_candidate_id for generation in output[lane] for row in generation
            if row.fixture_candidate_id in root_ids
        )
        for lane in LANES
    }
    # Source IDs only annotate compile_fixture_anchors.  Compare genomes to
    # retain root provenance even after V3 candidate identity changes.
    root_genomes = {row.lane: {row.genome.genome_id for row in anchors if row.lane == row.lane} for row in anchors}
    fixture_root_presence = {
        lane: all(any(candidate.genome.genome_id == anchor.genome.genome_id for generation in output[lane] for candidate in generation) for anchor in anchors if anchor.lane == lane)
        for lane in LANES
    }
    return output, {"saturation": saturation, "fixture_root_presence": fixture_root_presence, "fixture_source_ids": present}


def _control_jobs(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lane in LANES:
        for context in _context_rows(lane):
            seed_record = next(row for row in FORMAL_SEED_REGISTRY if row["seed"] == context["seed"])
            job = {"kind": "control", "evaluation_mode": "formal_exact", "context": context, "seed_record": seed_record, "payload": {"lane": lane, "control_sha256": file_sha256(CONTROLS[lane])}}
            job["job_id"] = canonical_job_id(job)
            rows.append(job)
    return sorted(rows, key=lambda row: row["job_id"])


def _candidate_jobs(root: Path, populations: dict[str, list[list[CompiledCandidate]]], controls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    control_by_context = {
        (row["context"]["lane"], row["context"]["opponent"], row["context"]["seed"], row["context"]["seat"]): row["job_id"]
        for row in controls
    }
    rows: list[dict[str, Any]] = []
    # Semantic candidate/context caching is decided before launch.  A retained
    # genome in a later generation keeps lineage in the generation manifest but
    # cannot consume a duplicate game.
    seen_contexts: set[str] = set()
    for lane, generations in populations.items():
        for generation, candidates in enumerate(generations):
            for candidate in candidates:
                for context in _context_rows(lane):
                    context_key = payload_hash({"candidate_id": candidate.candidate_id, "context": context})
                    if context_key in seen_contexts:
                        continue
                    seen_contexts.add(context_key)
                    seed_record = next(row for row in FORMAL_SEED_REGISTRY if row["seed"] == context["seed"])
                    control_id = control_by_context[(lane, context["opponent"], context["seed"], context["seat"])]
                    job = {
                        "kind": "candidate", "evaluation_mode": "formal_exact", "generation": generation,
                        "context": context, "seed_record": seed_record, "candidate": candidate.runtime_payload(),
                        "control_job_id": control_id, "control_cache_path": str(root / "control_cache.json"),
                        "payload": {"candidate_id": candidate.candidate_id, "genome_id": candidate.genome.genome_id, "generation": generation},
                    }
                    job["job_id"] = canonical_job_id(job)
                    rows.append(job)
    return sorted(rows, key=lambda row: row["job_id"])


def _manifest_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: manifest[key] for key in ("manifest", "engine", "control", "fixture", "registry", "jobs")}


def _signed(payload: dict[str, Any], field: str) -> dict[str, Any]:
    body = dict(payload)
    body[field] = payload_hash(body)
    return body


def preflight(
    root: Path,
    *,
    proposal_seed: int = DEFAULT_PROPOSAL_SEED,
    population: int = DEFAULT_POPULATION,
    generations: int = DEFAULT_GENERATIONS,
    workers: int = 1,
    resume: bool = False,
) -> dict[str, Any]:
    """Freeze every executable input before a worker can be launched."""
    if not 1 <= int(workers) <= 15:
        raise ValueError("workers must be in 1..15")
    if int(generations) < 1 or int(population) < 1:
        raise ValueError("population and generations must be positive")
    fixture_path = HERE / "fixtures" / "e1b_regression_fixtures.json"
    fixture = verify_frozen_evidence(fixture_path)
    if not fixture["pass"]:
        raise RuntimeError("frozen fixture evidence is invalid")
    engine = engine_fingerprint()
    populations, population_report = _compile_population(fixture_path, int(population), int(generations), int(proposal_seed))
    controls = _control_jobs(root)
    candidates = _candidate_jobs(root, populations, controls)
    protocol = {
        "proposal_seed": int(proposal_seed), "population": int(population), "generations": int(generations), "workers": int(workers),
        "seeds": list(FORMAL_SEED_REGISTRY), "opponents": list(FORMAL_OPPONENTS), "seats": list(FORMAL_SEATS),
        "formal_fresh_seeds_executed": False,
    }
    generation_payload = {
        lane: [[row.runtime_payload() for row in generation] for generation in rows]
        for lane, rows in populations.items()
    }
    fixture_metadata = {"path": str(fixture_path), "sha256": file_sha256(fixture_path), "canonical_sha256": fixture["fixture_canonical_sha256"]}
    registry_metadata = {"sha256": _registry_hash(), "seed_registry": list(FORMAL_SEED_REGISTRY)}
    body: dict[str, Any] = {
        "schema_version": 3, "kind": "async_v3_e1c_formal_manifest", "run_root": str(root),
        "protocol": protocol, "engine_fingerprint": engine, "control_hashes": {lane: file_sha256(path) for lane, path in CONTROLS.items()},
        "fixture_metadata": fixture_metadata, "registry_metadata": registry_metadata,
        "population": generation_payload, "population_report": population_report,
        "control_jobs": controls, "candidate_jobs": candidates,
        "formal_fresh_seeds_executed": False,
    }
    body["engine"] = payload_hash(engine)
    body["control"] = payload_hash(body["control_hashes"])
    body["fixture"] = payload_hash(fixture_metadata)
    body["registry"] = payload_hash(registry_metadata)
    body["jobs"] = payload_hash({"control": controls, "candidate": candidates})
    body["manifest"] = payload_hash({key: value for key, value in body.items() if key not in {"manifest", "created"}})
    if resume:
        existing = load_resume(root, _manifest_identity(body))
        if existing is None:
            raise SchedulerFailure("--resume requested but no formal manifest exists")
        return existing
    if (root / "manifest.json").exists():
        raise SchedulerFailure("formal manifest already exists; use --resume with identical inputs")
    atomic_json(root / "manifest.json", body)
    atomic_json(root / "protocol.json", {"protocol": protocol, "fixture": fixture, "fixture_metadata": fixture_metadata, "registry_metadata": registry_metadata, "engine": engine, "population_report": population_report})
    atomic_json(root / "jobs" / "controls.json", _signed({"manifest": body["manifest"], "jobs": controls}, "job_manifest_sha256"))
    for generation in range(int(generations)):
        jobs = [row for row in candidates if int(row["generation"]) == generation]
        atomic_json(root / "jobs" / f"generation_{generation:03d}.json", _signed({"manifest": body["manifest"], "generation": generation, "jobs": jobs}, "job_manifest_sha256"))
    return body


def formal_status(root: Path) -> dict[str, Any]:
    """Read-only status.  It never creates a run directory or checkpoint."""
    status = read_status(root)
    if not status.get("exists"):
        return {**status, "formal_fresh_seeds_executed": False}
    manifest = status.get("manifest", {})
    checkpoint = root / "checkpoint.json"
    return {
        "exists": True, "manifest_valid": bool(status.get("manifest_valid")), "run_root": str(root),
        "manifest": {key: manifest.get(key) for key in ("schema_version", "kind", "manifest", "engine", "control", "fixture", "registry", "jobs", "formal_fresh_seeds_executed")},
        "checkpoint_exists": checkpoint.is_file(), "formal_fresh_seeds_executed": False,
    }


def _mock_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**row, "evaluation_mode": "development_mock"} for row in jobs]


def _write_control_cache(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    cache: dict[str, Any] = {}
    for row in rows:
        if row.get("status") != "complete" or not isinstance(row.get("result"), dict):
            raise RuntimeError("control context did not complete; no candidate score is legal")
        cache[row["job_id"]] = row["result"]
    atomic_json(root / "control_cache.json", cache)
    return cache


def _score_rows(manifest: dict[str, Any], candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for job in manifest["candidate_jobs"]:
        expected[str(job["candidate"]["candidate_id"])].append(job)
    actual = {row["job_id"]: row for row in candidate_rows}
    score_rows: list[dict[str, Any]] = []
    for candidate_id, jobs in sorted(expected.items()):
        candidate = jobs[0]["candidate"]
        observations = [actual.get(job["job_id"]) for job in jobs]
        complete = all(row and row.get("status") == "complete" and row.get("result", {}).get("technical_status") == "complete" for row in observations)
        if not complete:
            score_rows.append({"candidate_id": candidate_id, "lane": candidate["lane"], "generation": jobs[0]["generation"], "contexts_expected": len(jobs), "contexts_complete": sum(bool(row and row.get("status") == "complete") for row in observations), "score": None, "metrics": {"technical_pass": False, "all_contexts_complete": False, "action_changed_contexts": 0, "opponent_nonnegative_families": 0, "worst_paired_margin": None, "mean_paired_margin": None, "actual_win_delta": 0, "complexity": None}})
            continue
        results = [row["result"] for row in observations if row is not None]
        margins = [float(row["paired"]["margin_delta"]) for row in results]
        banks = [float(row["paired"]["own_bank_delta"]) for row in results]
        wins = [int(row["paired"]["win_delta"]) for row in results]
        by_family: dict[str, list[float]] = defaultdict(list)
        changed = 0
        for job, result in zip(jobs, results):
            by_family[str(job["context"]["opponent"])].append(float(result["paired"]["margin_delta"]))
            changed += int(result["evidence"]["action_digest"] != result["control"]["evidence"]["action_digest"])
        complexity = len(candidate["genome"]["route_blocks"]) + len(candidate["genome"]["market_edits"]) + len(candidate["genome"]["constants"])
        metrics = {
            "technical_pass": True, "all_contexts_complete": True, "action_changed_contexts": changed,
            "opponent_nonnegative_families": sum(min(values) >= 0.0 for values in by_family.values()),
            "worst_paired_margin": min(margins), "mean_paired_margin": sum(margins) / len(margins),
            "mean_own_bank_delta": sum(banks) / len(banks), "actual_win_delta": sum(wins), "complexity": complexity,
        }
        score_rows.append({"candidate_id": candidate_id, "lane": candidate["lane"], "generation": jobs[0]["generation"], "contexts_expected": len(jobs), "contexts_complete": len(jobs), "score": metrics["mean_paired_margin"], "metrics": metrics, "lineage": candidate.get("lineage", {})})
    return score_rows


def _summarize(root: Path, manifest: dict[str, Any], controls: list[dict[str, Any]], candidates: list[dict[str, Any]], *, dry_run: bool) -> dict[str, Any]:
    scores = _score_rows(manifest, candidates)
    lanes = {lane: [row for row in scores if row["lane"] == lane] for lane in LANES}
    frontiers = rank_frontiers({"epsilon": 1.0, "lanes": lanes})
    candidate_jobs = {row["job_id"]: row for row in manifest["candidate_jobs"]}
    candidate_cache = {
        payload_hash({"candidate_id": candidate_jobs[row["job_id"]]["candidate"]["candidate_id"], "context": candidate_jobs[row["job_id"]]["context"]}): {
            "job_id": row["job_id"], "candidate_id": candidate_jobs[row["job_id"]]["candidate"]["candidate_id"],
            "context": candidate_jobs[row["job_id"]]["context"], "status": row.get("status"),
            "result_sha256": payload_hash(row.get("result")),
        }
        for row in candidates
    }
    atomic_json(root / "candidate_context_cache.json", _signed({"manifest": manifest["manifest"], "contexts": candidate_cache}, "candidate_context_cache_sha256"))
    for generation in range(int(manifest["protocol"]["generations"])):
        generation_scores = [row for row in scores if int(row["generation"]) == generation]
        generation_jobs = [row["job_id"] for row in manifest["candidate_jobs"] if int(row["generation"]) == generation]
        atomic_json(root / "generations" / f"generation_{generation:03d}.json", _signed({"manifest": manifest["manifest"], "generation": generation, "jobs": generation_jobs, "scores": generation_scores, "complete": all(row["score"] is not None for row in generation_scores)}, "generation_sha256"))
    phenotype = {}
    for lane in LANES:
        compiled = []
        for payload in manifest["population"][lane]:
            for item in payload:
                # Runtime payload can be reproduced only by compiling the
                # canonical genome, never by importing a generated artifact.
                from model import genome_from_payload
                compiled.append(compile_genome(lane, genome_from_payload(item["genome"], lineage=item.get("lineage"))))
        phenotype[lane] = phenotype_report(compiled)
    body = {
        "schema_version": 3, "kind": "async_v3_e1c_search_summary", "manifest": manifest["manifest"], "jobs": manifest["jobs"],
        "dry_run": bool(dry_run), "formal_fresh_seeds_executed": False,
        "seed_accounting": {"technical_seeds": [], "formal_retained_consumed": list(FORMAL_RETAINED_SEEDS), "executed_formal_seeds": [] if dry_run else list(FORMAL_RETAINED_SEEDS), "fresh_executed": False},
        "control_contexts": len(controls), "candidate_contexts": len(candidates), "scores": scores,
        "frontiers": frontiers, "phenotype_dedup": phenotype,
        "complete": all(row["score"] is not None for row in scores),
    }
    body["search_summary_sha256"] = payload_hash({key: value for key, value in body.items() if key != "search_summary_sha256"})
    atomic_json(root / "search_summary.json", body)
    return body


def _materialize_exact_finalists(root: Path, manifest: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    """Materialize only one selected score representative per lane after scoring."""
    payloads = {
        item["candidate_id"]: item
        for lane in LANES for generation in manifest["population"][lane] for item in generation
    }
    results: dict[str, Any] = {}
    for lane, frontier in summary["frontiers"]["lanes"].items():
        selected = frontier.get("causal_representative") or (frontier.get("high_upside") or [None])[0]
        if selected is None:
            results[lane] = {"selected": None, "pass": False, "reason": "no_frontier_finalist"}
            continue
        candidate = compiled_from_payload(payloads[selected])
        rows = []
        for opponent in FORMAL_OPPONENTS:
            for seed_record in FORMAL_SEED_REGISTRY:
                for seat in FORMAL_SEATS:
                    output = root / "finalists" / lane / selected / "main.py"
                    rows.append(formal_finalist_parity(candidate, output, opponent=opponent, seed=seed_record["seed"], seat=seat, seed_record=seed_record))
        results[lane] = {"selected": selected, "rows": rows, "pass": all(row["equal"] and row["fast"]["technical_status"] == "complete" and row["standalone"]["technical_status"] == "complete" for row in rows)}
    return results


def run_formal(root: Path, *, workers: int, resume: bool = False, dry_run: bool = False, execute_retained_e1c: bool = False) -> dict[str, Any]:
    """Execute frozen jobs or an explicit development mock of the same pipeline."""
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise SchedulerFailure("run requires a frozen preflight manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = _manifest_identity(manifest)
    load_resume(root, expected)
    if int(workers) != int(manifest["protocol"]["workers"]):
        raise SchedulerFailure("worker count differs from frozen formal manifest")
    if not dry_run and not execute_retained_e1c:
        raise PermissionError("formal exact execution requires explicit --execute-retained-e1c")
    controls = _mock_jobs(manifest["control_jobs"]) if dry_run else manifest["control_jobs"]
    candidates = _mock_jobs(manifest["candidate_jobs"]) if dry_run else manifest["candidate_jobs"]
    # The phases are intentionally separate: candidate workers can only read a
    # complete, lane-relative control cache produced before their launch.
    control_rows = evaluate_jobs(root / ("dry_mock" if dry_run else "formal") / "controls", controls, int(workers))
    _write_control_cache(root, control_rows)
    candidate_rows = evaluate_jobs(root / ("dry_mock" if dry_run else "formal") / "candidates", candidates, int(workers))
    summary = _summarize(root, manifest, control_rows, candidate_rows, dry_run=dry_run)
    if not dry_run:
        summary["finalist_parity"] = _materialize_exact_finalists(root, manifest, summary)
        summary["complete"] = bool(summary["complete"]) and all(row["pass"] for row in summary["finalist_parity"].values())
        summary["search_summary_sha256"] = payload_hash({key: value for key, value in summary.items() if key != "search_summary_sha256"})
        atomic_json(root / "search_summary.json", summary)
    checkpoint = {
        "schema_version": 3, "manifest": manifest["manifest"], "jobs": manifest["jobs"], "dry_run": bool(dry_run),
        "control_shards": [row["job_id"] for row in control_rows], "candidate_shards": [row["job_id"] for row in candidate_rows],
        "search_summary_sha256": summary["search_summary_sha256"], "complete": summary["complete"], "formal_fresh_seeds_executed": False,
    }
    checkpoint["checkpoint_sha256"] = payload_hash({key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"})
    atomic_json(root / "checkpoint.json", checkpoint)
    return {"manifest": manifest, "summary": summary, "checkpoint": checkpoint}


def _dry_mock_once(root: Path, *, workers: int, population: int, generations: int) -> dict[str, Any]:
    manifest = preflight(root, proposal_seed=DEFAULT_PROPOSAL_SEED, population=population, generations=generations, workers=workers, resume=(root / "manifest.json").is_file())
    result = run_formal(root, workers=workers, dry_run=True)
    return {"manifest": manifest, "summary": result["summary"], "checkpoint": result["checkpoint"]}


def dry_mock_proof(root: Path, *, workers: int = 1, compare_workers: int | None = None, population: int = 6, generations: int = 2) -> dict[str, Any]:
    """Run and, when requested, compare full serial/parallel formal plumbing."""
    primary = _dry_mock_once(root, workers=workers, population=population, generations=generations)
    parallel: dict[str, Any] | None = None
    equal = True
    if compare_workers is not None:
        comparison_root = root.with_name(f"{root.name}_workers_{compare_workers}")
        parallel = _dry_mock_once(comparison_root, workers=int(compare_workers), population=population, generations=generations)
        view = lambda result: {"scores": result["summary"]["scores"], "frontiers": result["summary"]["frontiers"], "complete": result["summary"]["complete"]}
        equal = view(primary) == view(parallel)
    return {
        "pass": primary["summary"]["complete"] and not primary["summary"]["formal_fresh_seeds_executed"] and equal,
        "manifest": primary["manifest"]["manifest"], "summary": primary["summary"], "checkpoint": primary["checkpoint"],
        "workers": {"requested": workers, "compare": compare_workers, "canonical_equal": equal},
        "parallel_summary_sha256": parallel["summary"]["search_summary_sha256"] if parallel else None,
    }
