"""Spawn-isolated, resumable, deterministic asynchronous topology search."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import statistics
from typing import Any, Iterable

from compiler import CONTROLS, compile_genome, phenotype_id, semantic_noop
from evaluator import (
    TECHNICAL_SEED,
    behavior_view,
    engine_fingerprint,
    paired_view,
    run_control,
    run_fast,
    run_standalone,
    technical_valid,
)
from evolution import (
    deduplicate_scores,
    genome_island,
    initial_genomes,
    mutate,
    next_generation,
    pareto,
    ranking_key,
)
from library import atomic_json, file_sha256, load_library
from materialize import isolated_import, materialize, static_audit
from model import (
    AsyncGenome,
    CompiledAsyncCandidate,
    LANES,
    StaticRejection,
    candidate_from_payload,
    canonical_bytes,
    payload_hash,
    stable_id,
)
from seed_accounting import DEFAULT_REGISTRY, classify_evaluation_seeds, load_seed_registry


SEARCH_VERSION = "async-search-e1b-v3"
DEFAULT_OPPONENTS = ("other_incumbent", "kaito_v21")
MAX_WORKERS = 15


def _write_hashed(path: Path, body: dict[str, Any], field: str) -> dict[str, Any]:
    payload = {**body, field: payload_hash(body)}
    atomic_json(path, payload)
    return payload


def _load_hashed(path: Path, field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = dict(payload)
    expected = body.pop(field, None)
    actual = payload_hash(body)
    if not expected or expected != actual:
        raise ValueError(f"hash mismatch for {path}: expected={expected} actual={actual}")
    return payload


def _manifest_body(
    library_path: Path,
    library: dict[str, Any],
    population: int,
    generations: int,
    opponents: tuple[str, ...],
    proposal_seed: int,
    evaluation_seeds: tuple[int, ...],
    formal_authorized: bool,
    authority: dict[str, Any] | None,
    fresh_evaluation_seeds: tuple[int, ...] = (),
    seed_registry_path: Path = DEFAULT_REGISTRY,
    seed_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    seed_registry_path = Path(seed_registry_path).resolve()
    seed_registry = seed_registry or load_seed_registry(seed_registry_path)
    seed_accounting = classify_evaluation_seeds(
        evaluation_seeds,
        formal_authorized=formal_authorized,
        registry=seed_registry,
        registry_path=seed_registry_path,
        explicit_fresh_seeds=fresh_evaluation_seeds,
    )
    return {
        "schema_version": 4,
        "search_version": SEARCH_VERSION,
        "technical_seed": TECHNICAL_SEED,
        "evaluation_seeds": list(evaluation_seeds),
        "formal_authorized": bool(formal_authorized),
        "seed_accounting": seed_accounting,
        "seed_registry_path": str(seed_registry_path),
        "seed_registry_run_id": seed_accounting["registry_run_id"],
        "seed_registry_file_sha256": seed_accounting["seed_registry_file_sha256"],
        "execution_started": False,
        "execution_completed": False,
        "formal_fresh_seeds_executed": seed_accounting["formal_fresh_seeds_executed"],
        "retained_e1_seeds_executed": seed_accounting["retained_e1_seeds_executed"],
        "authority": authority,
        "lanes": list(LANES),
        "population": int(population),
        "generations": int(generations),
        "opponents": list(opponents),
        "seats": [0, 1],
        "proposal_seed": int(proposal_seed),
        "library_path": str(library_path),
        "library_file_sha256": file_sha256(library_path),
        "library_sha256": library["library_sha256"],
        "controls": {lane: file_sha256(CONTROLS[lane]) for lane in LANES},
        "engine": engine_fingerprint(),
        "pairing": "lane-relative; no cross-lane reward or margin pooling",
    }


def _reference_traces() -> dict[str, list[Any]]:
    return {
        lane: run_control(lane, "other_incumbent", TECHNICAL_SEED, 0, capture_trace=True).trace
        for lane in LANES
    }


def _compile_population(
    lane: str,
    genomes: list[AsyncGenome],
    library: dict[str, Any],
    trace: list[Any],
    size: int,
    proposal_seed: int,
    generation: int,
) -> tuple[list[CompiledAsyncCandidate], list[dict[str, Any]]]:
    import random

    rng = random.Random((int(proposal_seed) << 20) ^ (generation << 8) ^ sum(map(ord, lane)))
    queue = list(genomes)
    compiled: list[CompiledAsyncCandidate] = []
    rejected: list[dict[str, Any]] = []
    seen = set()
    seen_phenotypes: set[str] = set()
    island_counts: Counter[str] = Counter()
    island_quota = max(0, int(size) // 4)
    attempts = 0
    while queue and len(compiled) < int(size) and attempts < int(size) * 256:
        genome = queue.pop(0)
        attempts += 1
        if genome.genome_id in seen:
            continue
        seen.add(genome.genome_id)
        result = compile_genome(lane, genome, library, trace)
        if isinstance(result, StaticRejection):
            rejected.append(result.payload())
            child = mutate(genome, lane, library, rng)
            if child.genome_id not in seen:
                queue.append(child)
            continue
        if semantic_noop(result):
            rejected.append(StaticRejection(
                lane,
                genome.genome_id,
                "semantic_no_op",
                "compiled genome has no executable delta from its lane control",
            ).payload())
            child = mutate(genome, lane, library, rng, island=genome_island(genome))
            if child.genome_id not in seen:
                queue.append(child)
            continue
        phenotype = phenotype_id(result)
        if phenotype in seen_phenotypes:
            rejected.append(StaticRejection(
                lane,
                genome.genome_id,
                "duplicate_phenotype",
                "compiled genome duplicates an already retained executable phenotype",
                (("phenotype_id", phenotype),),
            ).payload())
            child = mutate(genome, lane, library, rng, island=genome_island(genome))
            if child.genome_id not in seen:
                queue.append(child)
            continue
        island = genome_island(genome)
        missing_island = any(island_counts[name] < island_quota for name in ("route", "market", "constants", "coupled"))
        if island_quota and missing_island and island_counts[island] >= island_quota:
            target_island = next(
                name for name in ("route", "market", "constants", "coupled")
                if island_counts[name] < island_quota
            )
            child = mutate(AsyncGenome(), lane, library, rng, island=target_island)
            if target_island == "coupled":
                for _ in range(8):
                    if genome_island(child) == "coupled":
                        break
                    child = mutate(child, lane, library, rng, island="coupled")
            if child.genome_id not in seen:
                queue.append(child)
            continue
        seen_phenotypes.add(phenotype)
        compiled.append(result)
        island_counts[island] += 1
        if len(compiled) < int(size):
            child = mutate(genome, lane, library, rng)
            if child.genome_id not in seen:
                queue.append(child)
    if len(compiled) < int(size):
        raise RuntimeError(f"could compile only {len(compiled)}/{size} candidates for {lane}")
    return compiled, rejected


def compile_smoke(library_path: Path, output: Path, *, population: int = 8, proposal_seed: int = 8142026) -> dict[str, Any]:
    library = load_library(library_path)
    traces = _reference_traces()
    lanes = {}
    for lane in LANES:
        genomes = initial_genomes(lane, library, int(population), int(proposal_seed))
        compiled, rejected = _compile_population(lane, genomes, library, traces[lane], int(population), int(proposal_seed), 0)
        lanes[lane] = {
            "compiled": [row.runtime_payload() for row in compiled],
            "rejected": rejected,
            "island_counts": dict(sorted(Counter(genome_island(row.genome) for row in compiled).items())),
            "multi_gene_candidates": sum(
                len(row.genome.route_blocks) + len(row.genome.market_policy) + len(row.genome.constants) >= 2
                for row in compiled
            ),
        }
    body = {
        "schema_version": 2,
        "technical_seed": TECHNICAL_SEED,
        "formal_fresh_seeds_executed": False,
        "library_sha256": library["library_sha256"],
        "engine": engine_fingerprint(),
        "lanes": lanes,
    }
    return _write_hashed(output, body, "compile_smoke_sha256")


def _control_path(run_root: Path, lane: str, opponent: str, seed: int, seat: int) -> Path:
    identity = {"lane": lane, "opponent": opponent, "seed": int(seed), "seat": int(seat), "control": file_sha256(CONTROLS[lane])}
    return run_root / "controls" / f"{stable_id('control', identity)}.json"


def _control(
    run_root: Path,
    lane: str,
    opponent: str,
    seed: int,
    seat: int,
    formal_seeds: frozenset[int],
) -> dict[str, Any]:
    path = _control_path(run_root, lane, opponent, seed, seat)
    if path.is_file():
        return _load_hashed(path, "control_cache_sha256")
    run = run_control(lane, opponent, seed, seat, formal_seeds=formal_seeds)
    body = {
        "lane": lane, "opponent": opponent, "seed": int(seed), "seat": int(seat),
        "control_sha256": file_sha256(CONTROLS[lane]),
        "behavior": behavior_view(run),
        "latency_ms": run.summary["latency_ms"],
        "technical_pass": technical_valid(run.summary),
    }
    return _write_hashed(path, body, "control_cache_sha256")


def _worker(job: dict[str, Any]) -> dict[str, Any]:
    injection = job.get("failure_injection")
    if injection == "worker_exception":
        raise RuntimeError("injected async topology worker failure")
    if injection == "engine_import":
        raise ImportError("injected async topology engine import failure")
    candidate = candidate_from_payload(job["candidate"])
    run = run_fast(
        candidate,
        job["opponent"],
        int(job["seed"]),
        int(job["seat"]),
        formal_seeds=frozenset(int(seed) for seed in job.get("formal_seeds", [])),
    )
    behavior = behavior_view(run)
    body = {
        "job_id": job["job_id"], "generation": int(job["generation"]),
        "lane": candidate.lane, "candidate_id": candidate.candidate_id,
        "opponent": job["opponent"], "seed": int(job["seed"]), "seat": int(job["seat"]),
        "status": "complete", "candidate_behavior": behavior,
        "latency_ms": run.summary["latency_ms"],
        "technical_pass": technical_valid(run.summary),
        "phenotype_id": job["phenotype_id"],
        "context_cache_id": job["context_cache_id"],
    }
    return {**body, "shard_sha256": payload_hash(body)}


def _job(
    candidate: CompiledAsyncCandidate,
    generation: int,
    opponent: str,
    seat: int,
    *,
    seed: int = TECHNICAL_SEED,
    formal_seeds: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    identity = {
        "generation": int(generation), "lane": candidate.lane, "candidate_id": candidate.candidate_id,
        "opponent": opponent, "seed": int(seed), "seat": int(seat),
    }
    cache_identity = {
        "search_version": SEARCH_VERSION,
        "lane": candidate.lane,
        "phenotype_id": phenotype_id(candidate),
        "opponent": opponent,
        "seed": int(seed),
        "seat": int(seat),
    }
    return {
        **identity,
        "job_id": stable_id("job", identity),
        "phenotype_id": cache_identity["phenotype_id"],
        "context_cache_id": stable_id("context", cache_identity),
        "candidate": candidate.runtime_payload(),
        "formal_seeds": sorted(formal_seeds),
    }


def _shard_path(run_root: Path, job_id: str) -> Path:
    return run_root / "shards" / f"{job_id}.json"


def _context_cache_path(run_root: Path, context_cache_id: str) -> Path:
    return run_root / "candidate_context_cache" / f"{context_cache_id}.json"


def _cache_from_shard(shard: dict[str, Any]) -> dict[str, Any]:
    body = {
        key: shard[key]
        for key in (
            "lane", "candidate_id", "phenotype_id", "context_cache_id",
            "opponent", "seed", "seat", "candidate_behavior", "latency_ms",
            "technical_pass",
        )
    }
    return {**body, "candidate_context_cache_sha256": payload_hash(body)}


def _valid_context_cache(path: Path, context_cache_id: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        body = dict(payload)
        expected = body.pop("candidate_context_cache_sha256", None)
        if payload.get("context_cache_id") != context_cache_id or expected != payload_hash(body):
            return None
        return payload
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _shard_from_cache(job: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    body = {
        "job_id": job["job_id"], "generation": int(job["generation"]),
        "lane": job["lane"], "candidate_id": job["candidate_id"],
        "phenotype_id": job["phenotype_id"], "context_cache_id": job["context_cache_id"],
        "opponent": job["opponent"], "seed": int(job["seed"]), "seat": int(job["seat"]),
        "status": "complete", "candidate_behavior": cache["candidate_behavior"],
        "latency_ms": cache["latency_ms"], "technical_pass": cache["technical_pass"],
        "cache_hit": True,
    }
    return {**body, "shard_sha256": payload_hash(body)}


def _valid_shard(path: Path, job_id: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        body = dict(payload)
        expected = body.pop("shard_sha256", None)
        return payload if payload.get("job_id") == job_id and expected == payload_hash(body) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _preserve_corrupt(path: Path) -> None:
    if not path.exists():
        return
    suffix = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    destination = path.with_name(f"{path.stem}.corrupt-{suffix}{path.suffix}")
    if destination.exists():
        destination = path.with_name(f"{path.stem}.corrupt-{suffix}-{os.getpid()}{path.suffix}")
    path.replace(destination)


def _evaluate_jobs(run_root: Path, jobs: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    if not 1 <= int(workers) <= MAX_WORKERS:
        raise ValueError(f"workers must be in 1..{MAX_WORKERS}")
    run_root.joinpath("shards").mkdir(parents=True, exist_ok=True)
    run_root.joinpath("candidate_context_cache").mkdir(parents=True, exist_ok=True)
    rows = []
    pending = []
    for job in jobs:
        path = _shard_path(run_root, job["job_id"])
        shard = _valid_shard(path, job["job_id"])
        if shard is not None and shard.get("status", "complete") == "complete":
            rows.append(shard)
        else:
            if path.exists():
                _preserve_corrupt(path)
            cache_path = _context_cache_path(run_root, job["context_cache_id"])
            cache = None if job.get("failure_injection") else _valid_context_cache(
                cache_path, job["context_cache_id"]
            )
            if cache is not None:
                shard = _shard_from_cache(job, cache)
                atomic_json(path, shard)
                rows.append(shard)
            else:
                if cache_path.exists():
                    _preserve_corrupt(cache_path)
                pending.append(job)
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=max(1, int(workers)), mp_context=context) as pool:
        futures = {pool.submit(_worker, job): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                shard = future.result()
            except BaseException as error:
                body = {
                    "job_id": job["job_id"], "generation": int(job["generation"]),
                    "lane": job["lane"], "candidate_id": job["candidate_id"],
                    "opponent": job["opponent"], "seed": int(job["seed"]), "seat": int(job["seat"]),
                    "status": "infrastructure_failed",
                    "infrastructure_failure": {"type": type(error).__name__, "message": str(error)},
                }
                shard = {**body, "shard_sha256": payload_hash(body)}
            atomic_json(_shard_path(run_root, job["job_id"]), shard)
            if shard.get("status") == "complete":
                cache_path = _context_cache_path(run_root, shard["context_cache_id"])
                cached = _valid_context_cache(cache_path, shard["context_cache_id"])
                if cached is None:
                    if cache_path.exists():
                        _preserve_corrupt(cache_path)
                    atomic_json(cache_path, _cache_from_shard(shard))
            rows.append(shard)
    return sorted(rows, key=lambda row: row["job_id"])


def _outcome(rewards: list[float], seat: int) -> int:
    margin = float(rewards[seat]) - float(rewards[1 - seat])
    return 1 if margin > 0 else -1 if margin < 0 else 0


def _score_candidate(
    candidate: CompiledAsyncCandidate,
    rows: list[dict[str, Any]],
    controls: dict[tuple[str, str, int, int], dict[str, Any]],
) -> dict[str, Any]:
    margins = []
    own = []
    candidate_outcomes = []
    control_outcomes = []
    by_opponent: dict[str, list[float]] = {}
    latency_p95 = []
    latency_max = []
    technical = []
    diagnostics = Counter()
    action_changes = 0
    action_digest_vector = []
    for row in rows:
        control = controls[(candidate.lane, row["opponent"], int(row["seed"]), int(row["seat"]))]
        paired = paired_view(control["behavior"], row["candidate_behavior"], int(row["seat"]))
        margins.append(float(paired["paired_margin_delta"]))
        own.append(float(paired["own_bank_delta"]))
        by_opponent.setdefault(row["opponent"], []).append(float(paired["paired_margin_delta"]))
        candidate_outcomes.append(_outcome(paired["candidate_rewards"], int(row["seat"])))
        control_outcomes.append(_outcome(paired["control_rewards"], int(row["seat"])))
        latency_p95.append(float(row["latency_ms"]["p95"]))
        latency_max.append(float(row["latency_ms"]["max"]))
        technical.append(bool(row["technical_pass"]))
        for key, value in row["candidate_behavior"]["diagnostics"].items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                diagnostics[key] += value
        action_changes += int(row["candidate_behavior"]["action_digest"] != control["behavior"]["action_digest"])
        action_digest_vector.append({
            "opponent": row["opponent"],
            "seed": int(row["seed"]),
            "seat": int(row["seat"]),
            "action_digest": row["candidate_behavior"]["action_digest"],
        })
    paired_wdl = {"win": sum(value > 0 for value in margins), "draw": sum(value == 0 for value in margins), "loss": sum(value < 0 for value in margins)}
    candidate_wdl = {"win": candidate_outcomes.count(1), "draw": candidate_outcomes.count(0), "loss": candidate_outcomes.count(-1)}
    control_wdl = {"win": control_outcomes.count(1), "draw": control_outcomes.count(0), "loss": control_outcomes.count(-1)}
    complexity = len(candidate.genome.route_blocks) + len(candidate.genome.market_policy) + len(candidate.genome.constants)
    opponent_means = {key: statistics.fmean(values) for key, values in sorted(by_opponent.items())}
    digest_vector = sorted(action_digest_vector, key=lambda row: (row["opponent"], row["seed"], row["seat"]))
    return {
        "lane": candidate.lane,
        "candidate_id": candidate.candidate_id,
        "genome_id": candidate.genome.genome_id,
        "genome": candidate.genome.payload(),
        "island": genome_island(candidate.genome),
        "phenotype_id": phenotype_id(candidate),
        "contexts": len(rows),
        "technical_pass": all(technical) and max(latency_p95, default=0.0) < 150.0 and max(latency_max, default=0.0) < 750.0,
        "paired_wdl": paired_wdl,
        "candidate_wdl": candidate_wdl,
        "control_wdl": control_wdl,
        "actual_win_delta": candidate_wdl["win"] - control_wdl["win"],
        "mean_paired_margin": statistics.fmean(margins) if margins else float("-inf"),
        "median_paired_margin": statistics.median(margins) if margins else float("-inf"),
        "worst_paired_margin": min(margins, default=float("-inf")),
        "mean_own_bank": statistics.fmean(own) if own else float("-inf"),
        "by_opponent_mean_margin": opponent_means,
        "opponent_positive_families": sum(value > 0 for value in opponent_means.values()),
        "opponent_nonnegative_families": sum(value >= 0 for value in opponent_means.values()),
        "opponent_worst_mean_margin": min(opponent_means.values(), default=float("-inf")),
        "opponent_margin_spread": (
            max(opponent_means.values()) - min(opponent_means.values()) if opponent_means else float("inf")
        ),
        "latency_ms": {"worst_p95": max(latency_p95, default=0.0), "maximum": max(latency_max, default=0.0)},
        "diagnostic_totals": dict(sorted(diagnostics.items())),
        "action_changed_contexts": action_changes,
        "behavior_changing": action_changes > 0,
        "efficacy_eligible": action_changes > 0 and all(technical),
        "action_digest_vector_sha256": payload_hash(digest_vector),
        "complexity": complexity,
    }


def _generation_file(run_root: Path, generation: int) -> Path:
    return run_root / f"generation_{generation:03d}.json"


def _job_manifest_file(run_root: Path, generation: int) -> Path:
    return run_root / f"job_manifest_{generation:03d}.json"


def _freeze_job_manifest(
    run_root: Path,
    manifest_sha256: str,
    generation: int,
    jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    path = _job_manifest_file(run_root, generation)
    body = {
        "manifest_sha256": manifest_sha256,
        "generation": int(generation),
        "jobs": [
            {
                "job_id": job["job_id"],
                "lane": job["lane"],
                "candidate_id": job["candidate_id"],
                "opponent": job["opponent"],
                "seed": int(job["seed"]),
                "seat": int(job["seat"]),
            }
            for job in jobs
        ],
    }
    if path.exists():
        frozen = _load_hashed(path, "job_manifest_sha256")
        actual = dict(frozen)
        actual.pop("job_manifest_sha256")
        if actual != body:
            raise ValueError(f"frozen generation-{generation} job manifest mismatch")
        return frozen
    return _write_hashed(path, body, "job_manifest_sha256")


def _load_generation(path: Path) -> dict[str, Any]:
    return _load_hashed(path, "generation_sha256")


def _load_checkpoint(
    run_root: Path,
    manifest_sha256: str,
    *,
    preserve_corrupt: bool,
) -> dict[str, Any] | None:
    path = run_root / "checkpoint.json"
    if not path.is_file():
        return None
    try:
        payload = _load_hashed(path, "checkpoint_sha256")
        if payload.get("manifest_sha256") != manifest_sha256:
            raise ValueError("checkpoint manifest hash mismatch")
        return payload
    except Exception:
        if preserve_corrupt:
            _preserve_corrupt(path)
            return None
        raise


def _materialize_generation(run_root: Path, candidates: list[CompiledAsyncCandidate]) -> list[dict[str, Any]]:
    result = []
    for candidate in candidates:
        path = run_root / "candidates" / candidate.lane / candidate.candidate_id / "main.py"
        result.append(materialize(candidate, path))
    return result


def _parity(run_root: Path, finalists: dict[str, list[CompiledAsyncCandidate]]) -> dict[str, Any]:
    parity_path = run_root / "parity.json"
    expected_ids = {
        lane: [candidate.candidate_id for candidate in candidates]
        for lane, candidates in finalists.items()
    }
    if parity_path.is_file():
        frozen = _load_hashed(parity_path, "parity_sha256")
        actual_ids = {
            lane: [row["candidate_id"] for row in frozen.get("lanes", {}).get(lane, {}).get("finalists", [])]
            for lane in finalists
        }
        if actual_ids == expected_ids and frozen.get("technical_seed") == TECHNICAL_SEED:
            return frozen
        suffix = hashlib.sha256(parity_path.read_bytes()).hexdigest()[:12]
        superseded = parity_path.with_name(f"parity.superseded-{suffix}.json")
        if not superseded.exists():
            parity_path.replace(superseded)
        else:
            parity_path.unlink()
    lanes = {}
    for lane, candidates in finalists.items():
        rows = []
        for candidate in candidates:
            path = run_root / "candidates" / lane / candidate.candidate_id / "main.py"
            if not path.is_file():
                materialize(candidate, path)
            seats = []
            for seat in (0, 1):
                fast = run_fast(candidate, "other_incumbent", TECHNICAL_SEED, seat)
                standalone = run_standalone(candidate, path, "other_incumbent", TECHNICAL_SEED, seat)
                seats.append({
                    "seat": seat,
                    "equal": behavior_view(fast) == behavior_view(standalone),
                    "fast_action_digest": fast.summary["action_digest"],
                    "standalone_action_digest": standalone.summary["action_digest"],
                    "fast_latency_ms": fast.summary["latency_ms"],
                    "standalone_latency_ms": standalone.summary["latency_ms"],
                })
            static = static_audit(path)
            isolated = isolated_import(path)
            rows.append({
                "candidate_id": candidate.candidate_id,
                "phenotype_id": phenotype_id(candidate),
                "artifact": str(path),
                "static": static,
                "isolated": isolated,
                "seats": seats,
                "pass": all(row["equal"] for row in seats) and static["pass"] and isolated["callable_agent"],
            })
        lanes[lane] = {
            "finalists": rows,
            "count": len(rows),
            "pass": bool(rows) and all(row["pass"] for row in rows),
        }
    body = {
        "technical_seed": TECHNICAL_SEED,
        "formal_fresh_seeds_executed": False,
        "lanes": lanes,
        "pass": all(row["pass"] for row in lanes.values()),
    }
    return _write_hashed(parity_path, body, "parity_sha256")


def run_search(
    library_path: Path,
    run_root: Path,
    *,
    population: int,
    generations: int,
    workers: int,
    opponents: tuple[str, ...] = DEFAULT_OPPONENTS,
    proposal_seed: int = 8142026,
    evaluation_seeds: tuple[int, ...] = (TECHNICAL_SEED,),
    formal_authorized: bool = False,
    authority: dict[str, Any] | None = None,
    fresh_evaluation_seeds: tuple[int, ...] = (),
    seed_registry_path: Path = DEFAULT_REGISTRY,
) -> dict[str, Any]:
    if int(population) < 2 or int(generations) < 1:
        raise ValueError("population >=2 and generations >=1 required")
    if not 1 <= int(workers) <= MAX_WORKERS:
        raise ValueError(f"workers must be in 1..{MAX_WORKERS}")
    evaluation_seeds = tuple(int(seed) for seed in evaluation_seeds)
    if not evaluation_seeds or len(set(evaluation_seeds)) != len(evaluation_seeds):
        raise ValueError("evaluation seeds must be non-empty and unique")
    fresh_evaluation_seeds = tuple(int(seed) for seed in fresh_evaluation_seeds)
    seed_registry_path = Path(seed_registry_path).resolve()
    seed_registry = load_seed_registry(seed_registry_path)
    seed_accounting = classify_evaluation_seeds(
        evaluation_seeds,
        formal_authorized=formal_authorized,
        registry=seed_registry,
        registry_path=seed_registry_path,
        explicit_fresh_seeds=fresh_evaluation_seeds,
    )
    if seed_accounting["unclassified_seeds"]:
        raise ValueError(f"unclassified evaluation seeds: {seed_accounting['unclassified_seeds']}")
    if formal_authorized:
        if TECHNICAL_SEED in evaluation_seeds or not authority:
            raise PermissionError("formal search requires non-technical seeds and frozen authority hashes")
        actual_registry_hash = seed_accounting["seed_registry_file_sha256"]
        if authority.get("seed_registry_file_sha256") != actual_registry_hash:
            raise ValueError("formal seed registry hash differs from frozen authority")
        if authority.get("seed_accounting") != seed_accounting:
            raise ValueError("formal seed registry identity/classification differs from frozen authority")
        formal_seeds = frozenset(evaluation_seeds)
    else:
        if fresh_evaluation_seeds:
            raise PermissionError("technical search cannot classify fresh seeds")
        if evaluation_seeds != (TECHNICAL_SEED,):
            raise PermissionError("non-formal search is restricted to technical seed 811407")
        formal_seeds = frozenset()
    library = load_library(library_path)
    run_root.mkdir(parents=True, exist_ok=True)
    manifest_path = run_root / "search_manifest.json"
    expected_body = _manifest_body(
        library_path, library, population, generations, opponents, proposal_seed,
        evaluation_seeds, formal_authorized, authority, fresh_evaluation_seeds,
        seed_registry_path, seed_registry,
    )
    if manifest_path.exists():
        manifest = _load_hashed(manifest_path, "manifest_sha256")
        actual_body = dict(manifest)
        actual_body.pop("manifest_sha256")
        if actual_body != expected_body:
            raise ValueError("resume manifest/config/hash mismatch")
    else:
        manifest = _write_hashed(manifest_path, expected_body, "manifest_sha256")
    _load_checkpoint(run_root, manifest["manifest_sha256"], preserve_corrupt=True)
    traces: dict[str, list[Any]] | None = None
    controls = {
        (lane, opponent, seed, seat): _control(run_root, lane, opponent, seed, seat, formal_seeds)
        for lane in LANES for opponent in opponents for seed in evaluation_seeds for seat in (0, 1)
    }
    previous_parents: dict[str, list[AsyncGenome]] = {}
    all_scores: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}
    digest_duplicates: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}
    candidate_by_id: dict[str, CompiledAsyncCandidate] = {}
    for generation in range(int(generations)):
        path = _generation_file(run_root, generation)
        if path.exists():
            frozen = _load_generation(path)
            candidates = [candidate_from_payload(row) for lane in LANES for row in frozen["candidates"][lane]]
        else:
            if traces is None:
                traces = _reference_traces()
            candidates = []
            rejected_by_lane = {}
            for lane in LANES:
                if generation == 0:
                    genomes = initial_genomes(lane, library, population, proposal_seed)
                else:
                    genomes = next_generation(lane, library, previous_parents[lane], population, proposal_seed, generation)
                compiled, rejected = _compile_population(
                    lane, genomes, library, traces[lane], population, proposal_seed, generation,
                )
                candidates.extend(compiled)
                rejected_by_lane[lane] = rejected
            body = {
                "generation": generation,
                "manifest_sha256": manifest["manifest_sha256"],
                "candidates": {
                    lane: [row.runtime_payload() for row in candidates if row.lane == lane]
                    for lane in LANES
                },
                "rejections": rejected_by_lane,
                "artifacts": _materialize_generation(run_root, candidates),
            }
            frozen = _write_hashed(path, body, "generation_sha256")
        for candidate in candidates:
            candidate_by_id[candidate.candidate_id] = candidate
        jobs = [
            _job(candidate, generation, opponent, seat, seed=seed, formal_seeds=formal_seeds)
            for candidate in candidates for opponent in opponents
            for seed in evaluation_seeds for seat in (0, 1)
        ]
        _freeze_job_manifest(run_root, manifest["manifest_sha256"], generation, jobs)
        rows = _evaluate_jobs(run_root, jobs, workers)
        failures = [row for row in rows if row.get("status", "complete") != "complete"]
        if failures:
            raise RuntimeError(f"generation {generation} has {len(failures)} infrastructure failures; no efficacy score emitted")
        scores = []
        for candidate in candidates:
            candidate_rows = [row for row in rows if row["candidate_id"] == candidate.candidate_id]
            scores.append(_score_candidate(candidate, candidate_rows, controls))
        generation_scores = {
            lane: [row for row in scores if row["lane"] == lane]
            for lane in LANES
        }
        for lane in LANES:
            all_scores[lane].extend(generation_scores[lane])
            unique, duplicates = deduplicate_scores(generation_scores[lane])
            digest_duplicates[lane].extend({"generation": generation, **row} for row in duplicates)
            frontier = pareto(unique)
            ranked = frontier + [row for row in sorted(unique, key=ranking_key) if row not in frontier]
            selected = []
            for island in ("route", "market", "constants", "coupled"):
                row = next((item for item in ranked if item.get("island") == island), None)
                if row is not None and row not in selected:
                    selected.append(row)
            selected.extend(row for row in ranked if row not in selected)
            previous_parents[lane] = [
                candidate_by_id[row["candidate_id"]].genome
                for row in selected[: max(2, population // 2)]
            ]
        score_body = {
            "generation": generation,
            "scores": generation_scores,
            "pareto": {lane: pareto(generation_scores[lane]) for lane in LANES},
            "action_digest_duplicates": {
                lane: deduplicate_scores(generation_scores[lane])[1] for lane in LANES
            },
            "ranking": "opponent consistency, paired W/L, worst downside, own bank, complexity",
        }
        _write_hashed(run_root / f"scores_{generation:03d}.json", score_body, "scores_sha256")
        checkpoint_body = {
            "manifest_sha256": manifest["manifest_sha256"], "completed_generation": generation,
            "parents": {lane: [row.payload() for row in previous_parents[lane]] for lane in LANES},
        }
        _write_hashed(run_root / "checkpoint.json", checkpoint_body, "checkpoint_sha256")
    final_frontiers = {lane: pareto(all_scores[lane]) for lane in LANES}
    best = {}
    for lane in LANES:
        unique, duplicates = deduplicate_scores(all_scores[lane])
        digest_duplicates[lane] = duplicates
        ranked = final_frontiers[lane] or sorted(unique, key=ranking_key)
        best[lane] = candidate_by_id[ranked[0]["candidate_id"]]
    finalists = {
        lane: [candidate_by_id[row["candidate_id"]] for row in final_frontiers[lane]]
        or [best[lane]]
        for lane in LANES
    }
    parity = _parity(run_root, finalists)
    novelty_body = {
        "manifest_sha256": manifest["manifest_sha256"],
        "lanes": {
            lane: {
                "phenotypes": sorted({row["phenotype_id"] for row in all_scores[lane]}),
                "action_digest_vectors": sorted({row["action_digest_vector_sha256"] for row in all_scores[lane]}),
                "island_counts": dict(sorted(Counter(row["island"] for row in all_scores[lane]).items())),
            }
            for lane in LANES
        },
    }
    novelty = _write_hashed(run_root / "novelty_archive.json", novelty_body, "novelty_archive_sha256")
    shard_rows = [
        payload
        for path in sorted((run_root / "shards").glob("job_*.json"))
        if (payload := _valid_shard(path, path.stem)) is not None
    ]
    completed_seed_accounting = classify_evaluation_seeds(
        evaluation_seeds,
        formal_authorized=formal_authorized,
        registry=seed_registry,
        registry_path=seed_registry_path,
        explicit_fresh_seeds=fresh_evaluation_seeds,
        execution_started=True,
        execution_completed=True,
    )
    body = {
        "manifest_sha256": manifest["manifest_sha256"],
        "technical_seed": TECHNICAL_SEED,
        "evaluation_seeds": list(evaluation_seeds),
        "formal_authorized": bool(formal_authorized),
        "seed_accounting": completed_seed_accounting,
        "seed_registry_path": str(seed_registry_path),
        "seed_registry_run_id": completed_seed_accounting["registry_run_id"],
        "seed_registry_file_sha256": completed_seed_accounting["seed_registry_file_sha256"],
        "execution_started": True,
        "execution_completed": True,
        "formal_fresh_seeds_executed": completed_seed_accounting["formal_fresh_seeds_executed"],
        "retained_e1_seeds_executed": completed_seed_accounting["retained_e1_seeds_executed"],
        "scores": all_scores,
        "final_pareto": final_frontiers,
        "action_digest_duplicates": digest_duplicates,
        "novelty_archive_sha256": novelty["novelty_archive_sha256"],
        "cache": {
            "candidate_context_entries": len(list((run_root / "candidate_context_cache").glob("context_*.json"))),
            "shard_cache_hits": sum(bool(row.get("cache_hit")) for row in shard_rows),
        },
        "best_candidate_ids": {lane: candidate.candidate_id for lane, candidate in best.items()},
        "finalist_candidate_ids": {lane: [row.candidate_id for row in candidates] for lane, candidates in finalists.items()},
        "parity_sha256": parity["parity_sha256"],
        "pass": bool(parity["pass"]),
    }
    return _write_hashed(run_root / "search_summary.json", body, "summary_sha256")


def status(run_root: Path) -> dict[str, Any]:
    """Read-only snapshot.  It never creates, replaces, or repairs a path."""
    manifest_path = run_root / "search_manifest.json"
    if not manifest_path.is_file():
        return {"exists": False, "run_root": str(run_root)}
    try:
        manifest = _load_hashed(manifest_path, "manifest_sha256")
    except Exception as error:
        return {"exists": True, "manifest_valid": False, "error": f"{type(error).__name__}: {error}"}
    generations = []
    for generation in range(int(manifest["generations"])):
        path = _generation_file(run_root, generation)
        if not path.is_file():
            generations.append({"generation": generation, "frozen": False})
            continue
        try:
            payload = _load_generation(path)
            jobs = [
                _job(
                    candidate_from_payload(row), generation, opponent, seat,
                    seed=seed,
                    formal_seeds=frozenset(manifest["evaluation_seeds"] if manifest["formal_authorized"] else ()),
                )
                for lane in LANES for row in payload["candidates"][lane]
                for opponent in manifest["opponents"] for seed in manifest["evaluation_seeds"] for seat in (0, 1)
            ]
            counts = Counter()
            for job in jobs:
                shard_path = _shard_path(run_root, job["job_id"])
                shard = _valid_shard(shard_path, job["job_id"])
                if shard is not None:
                    counts[str(shard.get("status", "complete"))] += 1
                elif shard_path.exists():
                    counts["corrupt"] += 1
                else:
                    counts["missing"] += 1
            generations.append({"generation": generation, "frozen": True, "jobs": len(jobs), "counts": dict(counts)})
        except Exception as error:
            generations.append({"generation": generation, "frozen": True, "valid": False, "error": f"{type(error).__name__}: {error}"})
    checkpoint = None
    checkpoint_path = run_root / "checkpoint.json"
    if checkpoint_path.is_file():
        try:
            loaded = _load_checkpoint(run_root, manifest["manifest_sha256"], preserve_corrupt=False)
            checkpoint = {
                "exists": True,
                "valid": True,
                "completed_generation": int(loaded["completed_generation"]) if loaded else None,
            }
        except Exception as error:
            checkpoint = {"exists": True, "valid": False, "error": f"{type(error).__name__}: {error}"}
    else:
        checkpoint = {"exists": False}
    reported_accounting = manifest.get("seed_accounting")
    reported_started = bool(manifest.get("execution_started", False))
    reported_completed = bool(manifest.get("execution_completed", False))
    summary_path = run_root / "search_summary.json"
    if summary_path.is_file():
        try:
            summary = _load_hashed(summary_path, "summary_sha256")
            if summary.get("manifest_sha256") == manifest["manifest_sha256"]:
                reported_accounting = summary.get("seed_accounting", reported_accounting)
                reported_started = bool(summary.get("execution_started", reported_started))
                reported_completed = bool(summary.get("execution_completed", reported_completed))
        except Exception:
            pass
    return {
        "exists": True, "manifest_valid": True, "manifest_sha256": manifest["manifest_sha256"],
        "technical_seed": manifest["technical_seed"], "formal_authorized": manifest["formal_authorized"],
        "seed_accounting": reported_accounting,
        "seed_registry_path": manifest.get("seed_registry_path"),
        "seed_registry_run_id": manifest.get("seed_registry_run_id"),
        "seed_registry_file_sha256": manifest.get("seed_registry_file_sha256"),
        "execution_started": reported_started,
        "execution_completed": reported_completed,
        "formal_fresh_seeds_executed": bool((reported_accounting or {}).get("formal_fresh_seeds_executed", False)),
        "retained_e1_seeds_executed": bool((reported_accounting or {}).get("retained_e1_seeds_executed", False)),
        "evaluation_seeds": manifest["evaluation_seeds"],
        "generations": generations,
        "checkpoint": checkpoint,
        "candidate_context_cache_entries": (
            len(list((run_root / "candidate_context_cache").glob("context_*.json")))
            if (run_root / "candidate_context_cache").is_dir() else 0
        ),
        "summary_exists": summary_path.is_file(),
    }
