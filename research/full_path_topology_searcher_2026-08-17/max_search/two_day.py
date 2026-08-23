"""Auditable approximately-two-day continuation of the stopped maximum search.

This module deliberately does not mutate or resume the signed 300M run.  It
copies the stopped SQLite files into a temporary directory for read-only
inspection, reconstructs an exact completed-game ledger, seeds every island
from lane-local prior evidence, and executes only newly proposed semantics.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .checkpoint import RunManifest, atomic_json, verify_signature
from .contexts import ContextRegistry, verify_opponent_artifacts
from .contract import LANES, MODES, canonical_json, load_contract
from .coordinator import CandidateIndex
from .evolution import FitnessVector, MutationEngine, island_layout, select_survivors_scalable
from .execution import file_identity
from .genome import FullTapeGenome, RootRegistry, candidate_lane
from .preflight import source_snapshot
from .runner import (
    ParallelEvaluator,
    SearchStore,
    _ensure_births,
    _ensure_generation_pruned,
    _evaluate_candidates,
    _novelty,
    _prepare_receipt_retention,
    _score_candidates,
    _select_population,
    _select_promotions,
    _system_cpu_times,
)
from .scoring import ScoringIdentity, paired_row, score_candidate


class TwoDayError(RuntimeError):
    pass


WORKSPACE = Path(__file__).resolve().parents[3]
SEARCH_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OLD_RUN = (
    WORKSPACE / "research" / "cache" / "full_path_topology_searcher_2026-08-17"
    / "max_search_formal_300m_20260821_v1"
)
DEFAULT_OLD_CONTRACT = SEARCH_ROOT / "max_search_contract.json"
DEFAULT_STOP = SEARCH_ROOT / "max_search_formal_stop_20260823.json"
DEFAULT_STOP_DATABASE_IDENTITY = SEARCH_ROOT / "max_search_formal_stop_database_identity_20260823.json"
MINIMUM_FREE_BYTES = 50 * 1024**3
PHYSICAL_WORKERS = 14
RESIDENTS_PER_ISLAND = 64
EXECUTION_GENERATIONS = 16
GEN0_SEEDS_PER_ISLAND = 48
GEN1_SEEDS_PER_ISLAND = 16
GAME_IMPLEMENTATION_FILES = (
    "max_search/__init__.py",
    "max_search/checkpoint.py",
    "max_search/cli.py",
    "max_search/contexts.py",
    "max_search/contract.py",
    "max_search/coordinator.py",
    "max_search/evaluation.py",
    "max_search/evolution.py",
    "max_search/execution.py",
    "max_search/genome.py",
    "max_search/policy.py",
    "max_search/preflight.py",
    "max_search/runner.py",
    "max_search/scoring.py",
)
OFFICIAL_RUNTIME_DEPENDENCY_FILES = (
    "research/job_value_residual_2026-08-12/engine_runner.py",
    "research/job_value_residual_2026-08-12/protocol.py",
    "research/main_approach/performance_optimization_2026_08_11/harness.py",
    "research/job_value_residual_2026-08-12/artifacts/prechange_manifest.json",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _signed(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    if field in payload:
        raise TwoDayError(f"payload already contains {field}")
    result = dict(payload)
    result[field] = _sha_bytes(canonical_json(payload).encode("utf-8"))
    return result


def _identity(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(raw), "sha256": _sha_bytes(raw)}


def _verify_identity(value: Mapping[str, Any]) -> None:
    if not {"path", "bytes", "sha256"}.issubset(value):
        raise TwoDayError("file identity lacks a required field")
    path = Path(str(value["path"]))
    expected = {key: value[key] for key in ("path", "bytes", "sha256")}
    if not path.is_file() or _identity(path) != expected:
        raise TwoDayError(f"artifact drift: {path}")


def _guard_new_artifact_path(path: Path, *, old_run: Path, label: str, directory: bool = False) -> None:
    resolved = path.resolve(strict=False)
    immutable_root = old_run.resolve(strict=True)
    if resolved == immutable_root or resolved.is_relative_to(immutable_root):
        raise TwoDayError(f"{label} cannot be placed inside the immutable stopped run")
    if path.exists() and (not directory or not path.is_dir() or any(path.iterdir())):
        raise TwoDayError(f"{label} must be a new unused path")


def _runtime_dependency_snapshot() -> list[dict[str, Any]]:
    rows = []
    for relative in OFFICIAL_RUNTIME_DEPENDENCY_FILES:
        path = WORKSPACE / relative
        if not path.is_file():
            raise TwoDayError("official runtime dependency closure is incomplete")
        rows.append(_identity(path))
    return rows


def _verify_runtime_dependencies(expected: Sequence[Mapping[str, Any]]) -> None:
    if canonical_json(_runtime_dependency_snapshot()) != canonical_json(list(expected)):
        raise TwoDayError("official evaluator runtime dependency drift")


def _write_jsonl_gzip(path: Path, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    canonical_digest = hashlib.sha256()
    count = 0
    try:
        with os.fdopen(descriptor, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as stream:
                    for row in rows:
                        line = canonical_json(row) + "\n"
                        stream.write(line)
                        canonical_digest.update(line.encode("utf-8"))
                        count += 1
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    result = _identity(path)
    result.update({"rows": count, "canonical_uncompressed_sha256": canonical_digest.hexdigest()})
    return result


def _read_jsonl_gzip(identity: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    _verify_identity({key: identity[key] for key in ("path", "bytes", "sha256")})
    path = Path(str(identity["path"]))
    digest = hashlib.sha256()
    count = 0
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.endswith("\n"):
                raise TwoDayError("compressed JSONL contains a partial row")
            digest.update(line.encode("utf-8"))
            count += 1
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TwoDayError("compressed JSONL row is not an object")
            yield value
    if count != identity.get("rows") or digest.hexdigest() != identity.get("canonical_uncompressed_sha256"):
        raise TwoDayError("compressed JSONL row count or canonical digest drift")


def _database_files(root: Path) -> list[Path]:
    result: list[Path] = []
    for base in ("execution_store.sqlite", "execution_candidate_index.sqlite"):
        for suffix in ("", "-wal", "-shm"):
            path = root / f"{base}{suffix}"
            if path.is_file():
                result.append(path)
    return sorted(result, key=lambda value: value.name)


@contextmanager
def copied_old_databases(old_run: Path) -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection, list[dict[str, Any]]]]:
    """Inspect copies so SQLite cannot alter the stopped run's WAL/SHM files."""
    before = [_identity(path) for path in _database_files(old_run)]
    names = {Path(row["path"]).name for row in before}
    if "execution_store.sqlite" not in names or "execution_candidate_index.sqlite" not in names:
        raise TwoDayError("stopped run lacks one of its required SQLite databases")
    with tempfile.TemporaryDirectory(prefix="kaggriculture-two-day-readonly-") as temporary_name:
        temporary = Path(temporary_name)
        for row in before:
            shutil.copy2(Path(str(row["path"])), temporary / Path(str(row["path"])).name)
        store = sqlite3.connect((temporary / "execution_store.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
        index = sqlite3.connect((temporary / "execution_candidate_index.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
        try:
            if store.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise TwoDayError("copied stopped execution store failed quick_check")
            if index.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise TwoDayError("copied stopped candidate index failed quick_check")
            yield store, index, before
        finally:
            store.close()
            index.close()
    after = [_identity(path) for path in _database_files(old_run)]
    if canonical_json(before) != canonical_json(after):
        raise TwoDayError("stopped run database bytes changed during read-only import")


@dataclass(frozen=True)
class TwoDayContract:
    payload: Mapping[str, Any]
    sha256: str

    @property
    def scale(self) -> Mapping[str, int]:
        return self.payload["scale"]

    @property
    def population(self) -> int:
        return int(self.scale["population"])

    @property
    def islands(self) -> int:
        return int(self.scale["islands"])

    @property
    def generations(self) -> int:
        return int(self.scale["generations"])

    @property
    def raw_candidates(self) -> int:
        return int(self.scale["raw_candidates"])

    def birth_quota(self, generation: int) -> int:
        if not isinstance(generation, int) or isinstance(generation, bool) or not 0 <= generation < self.generations:
            raise TwoDayError("generation outside two-day contract")
        if generation == 0:
            return self.population
        return int(self.payload["quotas"]["births_per_island_per_execution_generation"]) * self.islands

    def island_birth_quotas(self, generation: int) -> tuple[int, ...]:
        per_island = (
            int(self.scale["residents_per_island"]) if generation == 0
            else int(self.payload["quotas"]["births_per_island_per_execution_generation"])
        )
        return (per_island,) * self.islands

    def t1_promotion_quota(self, generation: int) -> int:
        if generation == 0:
            return 0
        return int(self.payload["quotas"]["promotions_per_island_per_execution_generation"]) * self.islands


def _contract_without_signature(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not verify_signature(payload, "contract_sha256"):
        raise TwoDayError("two-day contract signature mismatch")
    return payload


def load_two_day_contract(path: Path) -> TwoDayContract:
    payload = _contract_without_signature(path)
    required = {
        "schema_version", "kind", "authority", "formal_execution_authorized", "pool_lanes",
        "scale", "tiers", "lanes", "genome", "selection", "engine", "quotas",
        "reuse", "execution_boundary", "contract_sha256",
    }
    if set(payload) != required or payload.get("schema_version") != 1 or payload.get("kind") != "two_day_full_tape_continuation_contract":
        raise TwoDayError("two-day contract schema is not closed")
    if payload.get("formal_execution_authorized") is not True or payload.get("pool_lanes") is not False:
        raise TwoDayError("two-day contract authorization or lane isolation is malformed")
    if set(payload["lanes"]) != set(LANES):
        raise TwoDayError("two-day contract lane set differs")
    for lane in LANES:
        modes = payload["lanes"][lane].get("modes", {})
        if payload["lanes"][lane].get("islands") != 16 or modes != {mode: 4 for mode in MODES}:
            raise TwoDayError("two-day contract must retain 16 lane-local islands and four islands per mode")
    scale = payload["scale"]
    if scale.get("islands") != 32 or scale.get("residents_per_island") != RESIDENTS_PER_ISLAND:
        raise TwoDayError("two-day contract island topology drift")
    contract = TwoDayContract(payload, str(payload["contract_sha256"]))
    if len(island_layout(contract)) != 32:
        raise TwoDayError("two-day island layout does not close")
    execution_generations = contract.generations - 1
    new_candidates = execution_generations * contract.birth_quota(1)
    promotions = execution_generations * contract.t1_promotion_quota(1)
    t0_games = new_candidates * int(payload["tiers"]["t0"]["games_per_candidate"])
    t1_games = promotions * int(payload["tiers"]["t1"]["additional_games_per_candidate"])
    if (
        new_candidates != scale.get("new_candidates")
        or t0_games != payload["tiers"]["t0"]["newly_executed_candidate_games"]
        or t1_games != payload["tiers"]["t1"]["newly_executed_candidate_games"]
        or t0_games + t1_games != scale.get("newly_executed_t0_t1_games")
        or int(payload["reuse"]["completed_game_keys"]) + t0_games + t1_games
        != scale.get("total_completed_t0_t1_game_keys")
    ):
        raise TwoDayError("two-day quota arithmetic does not close")
    boundary = payload["execution_boundary"]
    if (
        boundary.get("physical_workers") != PHYSICAL_WORKERS
        or not 1 <= int(boundary.get("active_in_flight", 0)) <= PHYSICAL_WORKERS
        or boundary.get("cpu_target_percent") != [50, 65]
        or boundary.get("minimum_free_bytes") != MINIMUM_FREE_BYTES
        or boundary.get("holdout_frozen_untouched") is not True
        or any(boundary.get(key) is not False for key in (
            "automatic_broad_launch", "automatic_promotion", "automatic_submission",
        ))
    ):
        raise TwoDayError("two-day execution boundary drift")
    if (
        payload["reuse"].get("completed_game_keys") != 196272
        or payload["reuse"].get("reused_games_are_not_newly_executed") is not True
        or scale["total_completed_t0_t1_game_keys"] <= 270000
    ):
        raise TwoDayError("two-day reuse or expansion boundary drift")
    return contract


CALIBRATION_CONTEXTS = tuple(
    {
        "context_id": f"cal_{family}_{seed}_{seat}",
        "opponent_family": family, "seed": seed, "seat": seat,
    }
    for family, seeds in (
        ("other_incumbent", (58310471, 58310473)),
        ("kaito_v21", (58310477, 58310479)),
    )
    for seed in seeds for seat in (0, 1)
)
CALIBRATION_CONTEXTS_SHA256 = _sha_bytes(canonical_json(CALIBRATION_CONTEXTS).encode("utf-8"))
CALIBRATION_CONTEXT_PROVENANCE = {
    "allocated_on": "2026-08-23",
    "previous_workspace_evidence_matches_before_allocation": 0,
    "disjoint_from_formal_t0_t1_holdout": True,
    "technical_only_not_efficacy": True,
    "may_reuse_across_calibration_trials": True,
}


_CALIBRATION_KEYS = {
    "schema_version", "kind", "created_at", "old_execution_manifest_sha256",
    "critical_compatibility_sha256", "source_snapshot_sha256", "physical_workers",
    "active_in_flight", "throttle_mode", "logical_cpus", "candidate_batches",
    "technical_contexts", "technical_contexts_sha256", "technical_context_provenance",
    "candidate_lane_counts",
    "contexts_per_batch", "candidate_games", "elapsed_seconds", "games_per_second",
    "whole_interval_cpu_percent", "worker_pids", "worker_processes_observed",
    "technical_failures", "bytes_per_receipt", "free_bytes_before", "free_bytes_after",
    "thermal_before", "thermal_after", "accepted", "acceptance", "calibration_sha256",
}


def _validate_calibration(payload: Mapping[str, Any]) -> None:
    if (
        set(payload) != _CALIBRATION_KEYS
        or not verify_signature(payload, "calibration_sha256")
        or payload.get("schema_version") != 1
        or payload.get("kind") != "two_day_worker_calibration"
        or payload.get("accepted") is not True
        or payload.get("physical_workers") != PHYSICAL_WORKERS
        or payload.get("throttle_mode") != "bounded_active_in_flight"
    ):
        raise TwoDayError("accepted calibration schema, signature, or fixed worker configuration mismatch")
    active = payload.get("active_in_flight")
    if not isinstance(active, int) or isinstance(active, bool) or not 1 <= active <= PHYSICAL_WORKERS:
        raise TwoDayError("accepted calibration active-in-flight value is malformed")
    technical_contexts = payload.get("technical_contexts")
    if (
        technical_contexts != list(CALIBRATION_CONTEXTS)
        or payload.get("technical_contexts_sha256") != CALIBRATION_CONTEXTS_SHA256
        or payload.get("technical_context_provenance") != CALIBRATION_CONTEXT_PROVENANCE
    ):
        raise TwoDayError("accepted calibration technical context mix drift")
    lane_counts = payload.get("candidate_lane_counts")
    batches, contexts, games = payload.get("candidate_batches"), payload.get("contexts_per_batch"), payload.get("candidate_games")
    if (
        any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in (batches, contexts, games))
        or batches % len(LANES) != 0
        or lane_counts != {lane: batches // len(LANES) for lane in LANES}
        or contexts != len(CALIBRATION_CONTEXTS)
        or games != batches * contexts
        or games < max(128, PHYSICAL_WORKERS * 8)
    ):
        raise TwoDayError("accepted calibration game interval is too small or does not close")
    elapsed, rate, cpu = payload.get("elapsed_seconds"), payload.get("games_per_second"), payload.get("whole_interval_cpu_percent")
    if (
        any(not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) <= 0 for value in (elapsed, rate))
        or abs(float(rate) - games / float(elapsed)) > 1e-12
        or not isinstance(cpu, (int, float)) or isinstance(cpu, bool) or not 50.0 <= float(cpu) <= 65.0
    ):
        raise TwoDayError("accepted calibration throughput or whole-interval CPU gate mismatch")
    pids = payload.get("worker_pids")
    expected_processes = min(active, batches)
    if (
        not isinstance(pids, list) or len(pids) != len(set(pids))
        or any(not isinstance(pid, int) or isinstance(pid, bool) or pid < 1 for pid in pids)
        or payload.get("worker_processes_observed") != len(pids)
        or len(pids) < expected_processes
        or payload.get("technical_failures") != 0
        or min(int(payload.get("free_bytes_before", 0)), int(payload.get("free_bytes_after", 0))) < MINIMUM_FREE_BYTES
        or not isinstance(payload.get("bytes_per_receipt"), (int, float))
        or float(payload["bytes_per_receipt"]) <= 0
    ):
        raise TwoDayError("accepted calibration worker, stability, receipt, or storage gate mismatch")
    if payload.get("acceptance") != {
        "minimum_candidate_games": max(128, PHYSICAL_WORKERS * 8),
        "cpu_percent": [50, 65],
        "minimum_free_bytes": MINIMUM_FREE_BYTES,
        "zero_technical_failures": True,
    }:
        raise TwoDayError("accepted calibration acceptance contract drift")
    for field in ("old_execution_manifest_sha256", "critical_compatibility_sha256", "source_snapshot_sha256"):
        value = payload.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise TwoDayError(f"accepted calibration {field} is malformed")


@dataclass(frozen=True)
class ManifestView:
    payload: Mapping[str, Any]
    sha256: str

    @property
    def formal(self) -> bool:
        return True


def _old_authority(old_run: Path, stop_path: Path) -> tuple[Mapping[str, Any], Mapping[str, Any], RunManifest, Any]:
    stop = json.loads(stop_path.read_text(encoding="utf-8"))
    if (
        stop.get("old_run_root") != old_run.relative_to(WORKSPACE).as_posix()
        or stop.get("all_captured_processes_stopped") is not True
        or stop.get("database", {}).get("quick_check") != "ok"
    ):
        raise TwoDayError("formal stop evidence does not authorize this old run")
    raw_manifest = json.loads((old_run / "execution_manifest.json").read_text(encoding="utf-8"))
    raw_checkpoint = json.loads((old_run / "execution_checkpoint.json").read_text(encoding="utf-8"))
    if (
        not verify_signature(raw_manifest, "execution_manifest_sha256")
        or not verify_signature(raw_checkpoint, "execution_checkpoint_sha256")
    ):
        raise TwoDayError("stopped run manifest or checkpoint signature mismatch")
    immutable = stop.get("immutable_artifacts", {})
    if (
        _identity(old_run / "execution_manifest.json")["sha256"] != immutable.get("execution_manifest_sha256")
        or _identity(old_run / "execution_checkpoint.json")["sha256"] != immutable.get("execution_checkpoint_sha256")
        or _identity(old_run / "execution_store.sqlite")["sha256"] != stop.get("database", {}).get("execution_store_sha256")
    ):
        raise TwoDayError("stopped run immutable artifact hash mismatch")
    database_identity = json.loads(DEFAULT_STOP_DATABASE_IDENTITY.read_text(encoding="utf-8"))
    expected_database_keys = {
        "schema_version", "kind", "created_at", "old_run_root", "formal_stop",
        "old_execution_manifest_sha256", "database_files", "quick_check",
        "stopped_process_set_confirmed_empty", "artifact_sha256",
    }
    if (
        set(database_identity) != expected_database_keys
        or not verify_signature(database_identity, "artifact_sha256")
        or database_identity.get("schema_version") != 1
        or database_identity.get("kind") != "stopped_max_search_database_identity"
        or database_identity.get("old_run_root") != old_run.relative_to(WORKSPACE).as_posix()
        or database_identity.get("old_execution_manifest_sha256") != raw_manifest["execution_manifest_sha256"]
        or database_identity.get("quick_check") != {
            "execution_candidate_index.sqlite": "ok", "execution_store.sqlite": "ok",
        }
        or database_identity.get("stopped_process_set_confirmed_empty") is not True
    ):
        raise TwoDayError("stopped-run database identity authority is malformed")
    _verify_identity(database_identity["formal_stop"])
    if _identity(stop_path) != database_identity["formal_stop"]:
        raise TwoDayError("formal stop evidence differs from the database identity authority")
    actual_database_files = [_identity(path) for path in _database_files(old_run)]
    if canonical_json(actual_database_files) != canonical_json(database_identity["database_files"]):
        raise TwoDayError("stopped-run database, WAL, or SHM identity drift")
    old_contract = load_contract(DEFAULT_OLD_CONTRACT)
    development_manifest = RunManifest.load(
        Path(str(raw_manifest["preflight_root"])) / "manifest.json",
        expected_contract_sha256=old_contract.sha256,
    )
    return raw_manifest, raw_checkpoint, development_manifest, old_contract


def _critical_compatibility(
    *, old_run: Path, raw_manifest: Mapping[str, Any], development_manifest: RunManifest,
    context_registry: ContextRegistry, registry: RootRegistry,
) -> dict[str, Any]:
    # Reusing controls and receipts is valid only while every opponent byte
    # named by the frozen context registry still matches its signed identity.
    # Do this before constructing the compatibility digest so the digest
    # cannot merely attest to stale declarations.
    verify_opponent_artifacts(context_registry)
    old_sources = development_manifest.payload["source_snapshot"]
    old_rows = {str(row["path"]): row for row in old_sources["implementation"]["files"]}
    required_paths = {
        f"research/full_path_topology_searcher_2026-08-17/{relative}" for relative in GAME_IMPLEMENTATION_FILES
    }
    if set(old_rows) != required_paths:
        raise TwoDayError("old game implementation inventory differs from the audited 14-file set")
    for relative, expected in old_rows.items():
        actual = _identity(WORKSPACE / relative)
        if actual["bytes"] != expected["bytes"] or actual["sha256"] != expected["sha256"]:
            raise TwoDayError(f"game implementation drift prevents reuse: {relative}")
    if registry.manifest()["manifest_sha256"] != old_sources["root_manifest_sha256"]:
        raise TwoDayError("root registry drift prevents reuse")
    if context_registry.sha256 != raw_manifest["context_registry_sha256"]:
        raise TwoDayError("context registry drift prevents reuse")
    payload = {
        "schema_version": 1,
        "old_execution_manifest_sha256": raw_manifest["execution_manifest_sha256"],
        "context_registry_sha256": context_registry.sha256,
        "engine": old_sources["engine"],
        "controls": old_sources["controls"],
        "routes": old_sources["routes"],
        "root_manifest_sha256": old_sources["root_manifest_sha256"],
        "opponent_artifacts": context_registry.payload["opponent_artifacts"],
        "official_runtime_dependencies": _runtime_dependency_snapshot(),
        "stopped_database_identity": _identity(DEFAULT_STOP_DATABASE_IDENTITY),
        "game_implementation": [old_rows[key] for key in sorted(old_rows)],
        "pool_lanes": False,
        "individual_game_semantics_match": True,
    }
    return _signed(payload, "compatibility_sha256")


def _vector_from_payload(encoded: str, digest: str) -> tuple[FitnessVector, Mapping[str, Any]]:
    if _sha_bytes(encoded.encode("utf-8")) != digest:
        raise TwoDayError("old fitness payload hash mismatch")
    payload = json.loads(encoded)
    return FitnessVector(**payload["vector"]), payload.get("diagnostics", {})


def _score_live_gen1(
    *, store: sqlite3.Connection, index: sqlite3.Connection, development_manifest: RunManifest,
    registry: RootRegistry, context_registry: ContextRegistry,
) -> tuple[dict[str, FitnessVector], dict[str, Mapping[str, Any]]]:
    contexts = {str(row["context_id"]): row for row in context_registry.contexts("t0")}
    controls: dict[tuple[str, str], Mapping[str, Any]] = {}
    for lane, context_id, encoded, digest in store.execute(
        "SELECT lane,context_id,payload_json,payload_sha256 FROM controls"
    ):
        if _sha_bytes(encoded.encode("utf-8")) != digest:
            raise TwoDayError("old control payload hash mismatch")
        controls[(str(lane), str(context_id))] = json.loads(encoded)
    grouped: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for candidate_id, context_id, encoded, digest in store.execute(
        "SELECT candidate_id,context_id,payload_json,payload_sha256 FROM receipts WHERE generation=1 AND tier='t0'"
    ):
        if _sha_bytes(encoded.encode("utf-8")) != digest:
            raise TwoDayError("old live receipt payload hash mismatch")
        grouped[str(candidate_id)][str(context_id)] = json.loads(encoded)
    semantics = {
        str(candidate_id): str(semantic_json)
        for candidate_id, semantic_json in index.execute(
            "SELECT candidate_id,semantic_json FROM candidates WHERE generation=1"
        )
    }
    vectors: dict[str, FitnessVector] = {}
    diagnostics: dict[str, Mapping[str, Any]] = {}
    for candidate_id, receipts in sorted(grouped.items()):
        if set(receipts) != set(contexts):
            raise TwoDayError("Gen1 live candidate has a partial T0 context block")
        semantic_json = semantics.get(candidate_id)
        if semantic_json is None:
            raise TwoDayError("Gen1 receipt candidate is absent from the old semantic index")
        genome_payload = json.loads(semantic_json)
        genome_payload["candidate_id"] = candidate_id
        genome = FullTapeGenome.from_dict(genome_payload)
        identity = ScoringIdentity.from_manifest(development_manifest, genome)
        paired = []
        for context_id in sorted(contexts):
            context = contexts[context_id]
            control = controls[(genome.lane, context_id)]
            candidate = receipts[context_id]
            paired.append(paired_row(
                identity=identity,
                opponent_family=str(context["opponent_family"]), seed=int(context["seed"]),
                seat=int(context["seat"]), control_margin=float(control["margin"]),
                candidate_margin=float(candidate["margin"]), control_own_bank=float(control["own_bank"]),
                candidate_own_bank=float(candidate["own_bank"]),
                technical_pass=bool(control["technical_pass"] and candidate["technical_pass"]),
                effective_change=control["behavior_sha256"] != candidate["behavior_sha256"],
            ))
        vector, detail = score_candidate(
            identity, paired, complexity=genome.edit_distance_from_root(), novelty=_novelty(genome, registry),
        )
        vectors[candidate_id] = vector
        diagnostics[candidate_id] = detail
    return vectors, diagnostics


def _select_seed_population(
    *, store: sqlite3.Connection, index: sqlite3.Connection, old_checkpoint: Mapping[str, Any],
    development_manifest: RunManifest, registry: RootRegistry, context_registry: ContextRegistry,
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]], dict[str, Any]]:
    gen0_vectors: dict[str, FitnessVector] = {}
    gen0_diagnostics: dict[str, Mapping[str, Any]] = {}
    for candidate_id, encoded, digest in store.execute(
        "SELECT candidate_id,payload_json,payload_sha256 FROM fitness WHERE generation=0 AND scope='t0'"
    ):
        vector, detail = _vector_from_payload(encoded, digest)
        gen0_vectors[str(candidate_id)] = vector
        gen0_diagnostics[str(candidate_id)] = detail
    gen1_vectors, gen1_diagnostics = _score_live_gen1(
        store=store, index=index, development_manifest=development_manifest,
        registry=registry, context_registry=context_registry,
    )
    island_for = {
        str(candidate_id): str(island_id)
        for candidate_id, island_id in index.execute("SELECT candidate_id,island_id FROM candidates")
    }
    populations: dict[str, list[str]] = {}
    seed_rows: dict[str, dict[str, Any]] = {}
    source_counts: Counter[str] = Counter()
    gen1_islands_seeded: list[str] = []
    for island in island_layout(TwoDayContract(_prototype_payload(), "0" * 64)):
        gen0_ids = list(old_checkpoint["population_ids"][island.island_id])
        gen0_pool = [gen0_vectors[candidate_id] for candidate_id in gen0_ids]
        gen1_pool = [
            vector for candidate_id, vector in gen1_vectors.items()
            if island_for.get(candidate_id) == island.island_id
        ]
        eligible_gen1 = [row for row in gen1_pool if row.technical_pass and row.effective_change]
        gen1_capacity = GEN1_SEEDS_PER_ISLAND if len(eligible_gen1) >= GEN1_SEEDS_PER_ISLAND else 0
        gen0_capacity = RESIDENTS_PER_ISLAND - gen1_capacity
        chosen0 = select_survivors_scalable(gen0_pool, gen0_capacity)
        chosen1 = select_survivors_scalable(gen1_pool, gen1_capacity) if gen1_capacity else ()
        if gen1_capacity:
            gen1_islands_seeded.append(island.island_id)
        chosen = list(chosen0) + list(chosen1)
        if len({row.candidate_id for row in chosen}) != RESIDENTS_PER_ISLAND:
            raise TwoDayError("seed selection produced a duplicate or short island")
        populations[island.island_id] = [row.candidate_id for row in chosen]
        for row in chosen:
            source = "gen0_frontier" if row.candidate_id in gen0_vectors else "gen1_live_t0"
            source_counts[source] += 1
            semantic = index.execute(
                "SELECT semantic_json FROM candidates WHERE candidate_id=?", (row.candidate_id,),
            ).fetchone()
            if semantic is None:
                raise TwoDayError("selected seed is absent from old candidate index")
            genome_payload = json.loads(semantic[0])
            genome_payload["candidate_id"] = row.candidate_id
            seed_rows[row.candidate_id] = {
                "source": source,
                "island_id": island.island_id,
                "genome": FullTapeGenome.from_dict(genome_payload).to_dict(),
                "fitness_t0": asdict(row),
                "fitness_t0_diagnostics": (
                    gen0_diagnostics[row.candidate_id] if source == "gen0_frontier"
                    else gen1_diagnostics[row.candidate_id]
                ),
            }
    combined = {}
    for candidate_id, encoded, digest in store.execute(
        "SELECT candidate_id,payload_json,payload_sha256 FROM fitness WHERE generation=0 AND scope='combined'"
    ):
        if str(candidate_id) in seed_rows:
            vector, detail = _vector_from_payload(encoded, digest)
            combined[str(candidate_id)] = {"vector": asdict(vector), "diagnostics": detail}
    summary = {
        "selected": len(seed_rows),
        "source_counts": dict(sorted(source_counts.items())),
        "combined_fitness_reused": len(combined),
        "per_island": RESIDENTS_PER_ISLAND,
        "gen0_per_gen1_covered_island": GEN0_SEEDS_PER_ISLAND,
        "gen1_per_covered_island": GEN1_SEEDS_PER_ISLAND,
        "gen1_islands_seeded": gen1_islands_seeded,
        "gen1_coverage_is_lane_local_and_not_imputed": True,
    }
    for candidate_id, payload in combined.items():
        seed_rows[candidate_id]["fitness_combined"] = payload["vector"]
        seed_rows[candidate_id]["fitness_combined_diagnostics"] = payload["diagnostics"]
    return populations, seed_rows, summary


def _prototype_payload() -> dict[str, Any]:
    base = json.loads(DEFAULT_OLD_CONTRACT.read_text(encoding="utf-8"))
    return {
        "scale": {"population": 32 * RESIDENTS_PER_ISLAND, "islands": 32, "residents_per_island": RESIDENTS_PER_ISLAND,
                  "generations": EXECUTION_GENERATIONS + 1, "raw_candidates": 32 * RESIDENTS_PER_ISLAND + 32 * 40 * EXECUTION_GENERATIONS},
        "tiers": {"t0": {"games_per_candidate": 6}, "t1": {"candidate_count": 32 * 6 * EXECUTION_GENERATIONS,
                                                               "additional_games_per_candidate": 24}},
        "lanes": base["lanes"], "genome": base["genome"], "selection": base["selection"],
        "engine": base["engine"], "quotas": {"births_per_island_per_execution_generation": 40,
                                                  "promotions_per_island_per_execution_generation": 6},
    }


def _thermal_snapshot() -> Mapping[str, Any]:
    if os.name != "nt":
        return {"available": False, "reason": "non-Windows host"}
    command = (
        "Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty CurrentTemperature"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=15,
    )
    values = []
    for token in completed.stdout.split():
        try:
            values.append(float(token) / 10.0 - 273.15)
        except ValueError:
            pass
    return {"available": bool(values), "celsius": values, "provider": "MSAcpi_ThermalZoneTemperature"}


def calibrate(
    *, old_run: Path, stop_path: Path, output: Path, physical_workers: int,
    active_in_flight: int, candidate_batches: int, require_gates: bool,
) -> dict[str, Any]:
    _guard_new_artifact_path(output, old_run=old_run, label="calibration output")
    if physical_workers != PHYSICAL_WORKERS or not 1 <= active_in_flight <= physical_workers:
        raise TwoDayError("two-day calibration requires 14 configured workers and an explicit bounded active limit")
    if candidate_batches < len(LANES) or candidate_batches % len(LANES) != 0:
        raise TwoDayError("calibration candidate batches must be positive and lane-balanced")
    raw_manifest, _checkpoint, development_manifest, _old_contract = _old_authority(old_run, stop_path)
    context_registry = ContextRegistry.load(old_run / "context_registry.json", require_mode="formal")
    formal_seeds = {
        int(row["seed"])
        for stage in ("t0", "t1", "holdout")
        for row in context_registry.contexts(stage)
    }
    calibration_seeds = {int(row["seed"]) for row in CALIBRATION_CONTEXTS}
    if formal_seeds.intersection(calibration_seeds):
        raise TwoDayError("technical calibration seeds overlap the formal or holdout registry")
    registry = RootRegistry.load_workspace(WORKSPACE, include_public=True)
    compatibility = _critical_compatibility(
        old_run=old_run, raw_manifest=raw_manifest, development_manifest=development_manifest,
        context_registry=context_registry, registry=registry,
    )
    prototype = TwoDayContract(_prototype_payload(), "0" * 64)
    sources = source_snapshot(WORKSPACE, prototype, registry)
    source_digest = _sha_bytes(canonical_json(sources).encode("utf-8"))
    # Measure the expensive formal mix, not only the cheaper T0 control mix.
    # T1 is evenly split between the other incumbent and Kaito; use fresh
    # technical-only seeds with both seats for each family.  These contexts are
    # never admitted to search fitness or the completed-game ledger.
    contexts = list(CALIBRATION_CONTEXTS)
    layout = island_layout(prototype)
    layout_by_lane = {lane: [row for row in layout if row.lane == lane] for lane in LANES}
    mutation = MutationEngine(registry, proposal_seed=99182731)
    tasks = []
    seen: set[str] = set()
    ordinal = 0
    while len(tasks) < candidate_batches:
        lane = LANES[len(tasks) % len(LANES)]
        lane_ordinal = len(tasks) // len(LANES)
        island = layout_by_lane[lane][lane_ordinal % len(layout_by_lane[lane])]
        parent = mutation.initial_genome(island, ordinal)
        child, _ = mutation.child(parent, island, generation=9999, ordinal=ordinal)
        ordinal += 1
        if child.candidate_id in seen:
            continue
        seen.add(child.candidate_id)
        tasks.append({
            "kind": "candidate", "backend": "official", "lane": child.lane,
            "genome": child.to_dict(), "contexts": contexts, "tier": "calibration",
            "generation": -2, "island_id": island.island_id,
        })
    disk_before = shutil.disk_usage(output.parent if output.parent.exists() else WORKSPACE).free
    thermal_before = _thermal_snapshot()
    idle_before, total_before = _system_cpu_times()
    started = time.perf_counter()
    results = []
    pids: set[int] = set()
    with ParallelEvaluator(
        workspace=WORKSPACE,
        root_manifest_sha256=development_manifest.payload["root_manifest"]["manifest_sha256"],
        workers=physical_workers, max_in_flight=active_in_flight,
    ) as evaluator:
        for batch in evaluator.run(tasks):
            pids.add(int(batch["worker_pid"]))
            results.extend(batch["results"])
    elapsed = time.perf_counter() - started
    idle_after, total_after = _system_cpu_times()
    thermal_after = _thermal_snapshot()
    delta_total, delta_idle = total_after - total_before, idle_after - idle_before
    if delta_total <= 0 or elapsed <= 0:
        raise TwoDayError("calibration interval is empty")
    cpu_percent = 100.0 * (delta_total - delta_idle) / delta_total
    technical_failures = sum(result.get("technical_pass") is not True for result in results)
    candidate_games = len(results)
    candidate_lane_counts = dict(Counter(str(task["lane"]) for task in tasks))
    encoded_bytes = sum(len(canonical_json(result).encode("utf-8")) for result in results)
    accepted = bool(
        candidate_games >= max(128, physical_workers * 8)
        and technical_failures == 0
        and 50.0 <= cpu_percent <= 65.0
        and disk_before >= MINIMUM_FREE_BYTES
        and len(pids) >= min(active_in_flight, candidate_batches)
    )
    payload = _signed({
        "schema_version": 1,
        "kind": "two_day_worker_calibration",
        "created_at": _utc_now(),
        "old_execution_manifest_sha256": raw_manifest["execution_manifest_sha256"],
        "critical_compatibility_sha256": compatibility["compatibility_sha256"],
        "source_snapshot_sha256": source_digest,
        "physical_workers": physical_workers,
        "active_in_flight": active_in_flight,
        "throttle_mode": "bounded_active_in_flight",
        "logical_cpus": int(os.cpu_count() or 1),
        "candidate_batches": candidate_batches,
        "technical_contexts": contexts,
        "technical_contexts_sha256": CALIBRATION_CONTEXTS_SHA256,
        "technical_context_provenance": CALIBRATION_CONTEXT_PROVENANCE,
        "candidate_lane_counts": candidate_lane_counts,
        "contexts_per_batch": len(contexts),
        "candidate_games": candidate_games,
        "elapsed_seconds": elapsed,
        "games_per_second": candidate_games / elapsed,
        "whole_interval_cpu_percent": cpu_percent,
        "worker_pids": sorted(pids),
        "worker_processes_observed": len(pids),
        "technical_failures": technical_failures,
        "bytes_per_receipt": encoded_bytes / candidate_games,
        "free_bytes_before": disk_before,
        "free_bytes_after": shutil.disk_usage(output.parent if output.parent.exists() else WORKSPACE).free,
        "thermal_before": thermal_before,
        "thermal_after": thermal_after,
        "accepted": accepted,
        "acceptance": {
            "minimum_candidate_games": max(128, physical_workers * 8),
            "cpu_percent": [50, 65],
            "minimum_free_bytes": MINIMUM_FREE_BYTES,
            "zero_technical_failures": True,
        },
    }, "calibration_sha256")
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output, payload)
    if require_gates and not accepted:
        raise TwoDayError("formal two-day calibration failed one or more gates")
    return payload


def _choose_quotas(games_per_second: float, reused_games: int) -> dict[str, Any]:
    if games_per_second <= 0:
        raise TwoDayError("calibrated throughput must be positive")
    choices = []
    for births in range(8, 129):
        for promotions in range(1, births):
            ratio = promotions / births
            if not 0.12 <= ratio <= 0.20:
                continue
            new_games = EXECUTION_GENERATIONS * 32 * (births * 6 + promotions * 24)
            hours = new_games / games_per_second / 3600.0
            total = reused_games + new_games
            if hours <= 45.5:
                preferred = 44.0 <= hours <= 45.5 and 400_000 <= total <= 500_000
                choices.append((preferred, hours, total, new_games, births, promotions))
    if not choices:
        raise TwoDayError("calibration cannot support a nontrivial two-day quota")
    preferred_rows = [row for row in choices if row[0]]
    pool = preferred_rows or choices
    chosen = max(pool, key=lambda row: (row[3], -abs(row[1] - 45.0), row[2]))
    _preferred, hours, total, new_games, births, promotions = chosen
    return {
        "execution_generations": EXECUTION_GENERATIONS,
        "births_per_island_per_execution_generation": births,
        "promotions_per_island_per_execution_generation": promotions,
        "new_candidates": EXECUTION_GENERATIONS * 32 * births,
        "new_promoted_candidates": EXECUTION_GENERATIONS * 32 * promotions,
        "newly_executed_t0_games": EXECUTION_GENERATIONS * 32 * births * 6,
        "newly_executed_t1_games": EXECUTION_GENERATIONS * 32 * promotions * 24,
        "newly_executed_t0_t1_games": new_games,
        "reused_completed_games": reused_games,
        "total_completed_t0_t1_game_keys": total,
        "projected_search_hours": hours,
        "target_search_hours": 45.0,
        "maximum_search_hours": 45.5,
        "reserved_two_day_buffer_hours": 2.5,
    }


def _build_contract(
    *, calibration: Mapping[str, Any], compatibility: Mapping[str, Any], ledger_summary: Mapping[str, Any],
) -> dict[str, Any]:
    base = json.loads(DEFAULT_OLD_CONTRACT.read_text(encoding="utf-8"))
    quotas = _choose_quotas(float(calibration["games_per_second"]), int(ledger_summary["completed_game_keys"]))
    population = 32 * RESIDENTS_PER_ISLAND
    raw_candidates = population + int(quotas["new_candidates"])
    payload = {
        "schema_version": 1,
        "kind": "two_day_full_tape_continuation_contract",
        "authority": "current chat authorization 2026-08-23; approximately two-day 14-worker continuation",
        "formal_execution_authorized": True,
        "pool_lanes": False,
        "scale": {
            "population": population,
            "generations": EXECUTION_GENERATIONS + 1,
            "raw_candidates": raw_candidates,
            "new_candidates": quotas["new_candidates"],
            "newly_executed_t0_t1_games": quotas["newly_executed_t0_t1_games"],
            "total_completed_t0_t1_game_keys": quotas["total_completed_t0_t1_game_keys"],
            "broad_finalists": 100,
            "islands": 32,
            "residents_per_island": RESIDENTS_PER_ISLAND,
        },
        "tiers": {
            "t0": {"candidate_count": quotas["new_candidates"], "games_per_candidate": 6,
                   "newly_executed_candidate_games": quotas["newly_executed_t0_games"]},
            "t1": {"candidate_count": quotas["new_promoted_candidates"], "additional_games_per_candidate": 24,
                   "newly_executed_candidate_games": quotas["newly_executed_t1_games"]},
            "control_cache_games_in_t0_t1_budget": False,
            "broad_games_in_t0_t1_budget": False,
        },
        "lanes": base["lanes"],
        "genome": base["genome"],
        "selection": base["selection"],
        "engine": base["engine"],
        "quotas": quotas,
        "reuse": {
            "completed_game_keys": ledger_summary["completed_game_keys"],
            "gen0_t0": ledger_summary["counts"]["gen0_reconstructed_t0"],
            "gen0_t1": ledger_summary["counts"]["gen0_reconstructed_t1"],
            "gen1_live_t0": ledger_summary["counts"]["gen1_live_t0"],
            "critical_compatibility_sha256": compatibility["compatibility_sha256"],
            "reused_games_are_not_newly_executed": True,
        },
        "execution_boundary": {
            "physical_workers": PHYSICAL_WORKERS,
            "active_in_flight": calibration["active_in_flight"],
            "cpu_target_percent": [50, 65],
            "storage_retention": base["execution_boundary"]["storage_retention"],
            "minimum_free_bytes": MINIMUM_FREE_BYTES,
            "holdout_frozen_untouched": True,
            "automatic_broad_launch": False,
            "automatic_promotion": False,
            "automatic_submission": False,
        },
    }
    return _signed(payload, "contract_sha256")


def _completed_ledger_rows(
    *, store: sqlite3.Connection, index: sqlite3.Connection, context_registry: ContextRegistry,
    compatibility_sha256: str,
) -> Iterator[dict[str, Any]]:
    t0 = sorted(context_registry.contexts("t0"), key=lambda row: str(row["context_id"]))
    t1 = sorted(context_registry.contexts("t1"), key=lambda row: str(row["context_id"]))
    candidate_lanes = {
        str(candidate_id): candidate_lane(str(candidate_id))
        for (candidate_id,) in index.execute("SELECT candidate_id FROM candidates WHERE generation=0 ORDER BY candidate_id")
    }
    seen: set[str] = set()

    def emit(candidate_id: str, lane: str, tier: str, context_id: str, source: str, payload_sha256: str | None) -> dict[str, Any]:
        key_payload = {
            "candidate_id": candidate_id, "lane": lane, "tier": tier,
            "context_id": context_id, "compatibility_sha256": compatibility_sha256,
        }
        digest = _sha_bytes(canonical_json(key_payload).encode("utf-8"))
        if digest in seen:
            raise TwoDayError("completed-game ledger contains a duplicate key")
        seen.add(digest)
        return {
            **key_payload, "game_key_sha256": digest, "source": source,
            "receipt_payload_sha256": payload_sha256,
        }

    for candidate_id in sorted(candidate_lanes):
        for context in t0:
            yield emit(candidate_id, candidate_lanes[candidate_id], "t0", str(context["context_id"]), "gen0_reconstructed_pruned", None)
    promotions = [str(row[0]) for row in store.execute(
        "SELECT candidate_id FROM promotions WHERE generation=0 ORDER BY candidate_id"
    )]
    if len(promotions) != 2730 or len(set(promotions)) != len(promotions):
        raise TwoDayError("old Gen0 promotion ledger does not contain exactly 2,730 candidates")
    for candidate_id in promotions:
        lane = candidate_lanes.get(candidate_id)
        if lane is None:
            raise TwoDayError("Gen0 promotion is absent from the initial candidate set")
        for context in t1:
            yield emit(candidate_id, lane, "t1", str(context["context_id"]), "gen0_reconstructed_pruned", None)
    live = store.execute(
        "SELECT candidate_id,lane,tier,context_id,payload_sha256 FROM receipts "
        "WHERE generation=1 ORDER BY candidate_id,tier,context_id"
    ).fetchall()
    if len(live) != 32448:
        raise TwoDayError("old Gen1 live receipt count is not exactly 32,448")
    per_candidate: Counter[str] = Counter(str(row[0]) for row in live)
    if set(per_candidate.values()) != {len(t0)}:
        raise TwoDayError("old Gen1 live receipts do not form complete T0 blocks")
    for candidate_id, lane, tier, context_id, digest in live:
        if tier != "t0" or candidate_lane(str(candidate_id)) != lane:
            raise TwoDayError("old Gen1 live receipt tier or lane mismatch")
        yield emit(str(candidate_id), str(lane), str(tier), str(context_id), "gen1_live_receipt", str(digest))


def _control_cache_digest(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    rows = connection.execute(
        "SELECT lane,context_id,payload_json,payload_sha256 FROM controls ORDER BY lane,context_id"
    ).fetchall()
    if len(rows) != 60:
        raise TwoDayError("control cache does not contain exactly 60 lane-context rows")
    for lane, context_id, encoded, payload_sha256 in rows:
        if _sha_bytes(str(encoded).encode("utf-8")) != payload_sha256:
            raise TwoDayError("control cache payload hash mismatch")
        digest.update((canonical_json({
            "lane": str(lane), "context_id": str(context_id),
            "payload_json": str(encoded), "payload_sha256": str(payload_sha256),
        }) + "\n").encode("utf-8"))
    return digest.hexdigest()


def prepare(
    *, old_run: Path, stop_path: Path, calibration_path: Path, output_root: Path,
    run_id: str, authorization_id: str,
) -> dict[str, Any]:
    _guard_new_artifact_path(output_root, old_run=old_run, label="two-day run root", directory=True)
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    _validate_calibration(calibration)
    raw_manifest, old_checkpoint, development_manifest, _old_contract = _old_authority(old_run, stop_path)
    context_registry = ContextRegistry.load(old_run / "context_registry.json", require_mode="formal")
    registry = RootRegistry.load_workspace(WORKSPACE, include_public=True)
    compatibility = _critical_compatibility(
        old_run=old_run, raw_manifest=raw_manifest, development_manifest=development_manifest,
        context_registry=context_registry, registry=registry,
    )
    current_sources = source_snapshot(WORKSPACE, TwoDayContract(_prototype_payload(), "0" * 64), registry)
    current_source_digest = _sha_bytes(canonical_json(current_sources).encode("utf-8"))
    if (
        calibration.get("source_snapshot_sha256") != current_source_digest
        or calibration.get("critical_compatibility_sha256") != compatibility["compatibility_sha256"]
    ):
        raise TwoDayError("implementation or compatibility drift since calibration")
    if shutil.disk_usage(output_root.parent if output_root.parent.exists() else WORKSPACE).free < MINIMUM_FREE_BYTES:
        raise TwoDayError("two-day preparation lacks the 50 GiB dynamic-storage reserve")

    output_root.mkdir(parents=True, exist_ok=True)
    context_path = output_root / "context_registry.json"
    atomic_json(context_path, context_registry.payload)
    compatibility_path = output_root / "reuse_compatibility.json"
    atomic_json(compatibility_path, compatibility)

    with copied_old_databases(old_run) as (store, index, old_database_identities):
        control_cache_sha256 = _control_cache_digest(store)
        if store.execute("SELECT COUNT(*) FROM receipt_prunes WHERE generation=0").fetchone()[0] != 1:
            raise TwoDayError("old Gen0 prune ledger is absent")
        prune = store.execute(
            "SELECT t0_count,t1_count FROM receipt_prunes WHERE generation=0"
        ).fetchone()
        if tuple(prune) != (98304, 65520):
            raise TwoDayError("old Gen0 prune counts differ from the stop contract")
        ledger_path = output_root / "completed_game_keys.jsonl.gz"
        ledger_identity = _write_jsonl_gzip(
            ledger_path,
            _completed_ledger_rows(
                store=store, index=index, context_registry=context_registry,
                compatibility_sha256=str(compatibility["compatibility_sha256"]),
            ),
        )
        if ledger_identity["rows"] != 196272:
            raise TwoDayError("completed-game key ledger does not close at 196,272")
        ledger_summary = _signed({
            "schema_version": 1,
            "kind": "two_day_completed_game_ledger",
            "created_at": _utc_now(),
            "old_execution_manifest_sha256": raw_manifest["execution_manifest_sha256"],
            "compatibility_sha256": compatibility["compatibility_sha256"],
            "completed_game_keys": ledger_identity["rows"],
            "counts": {"gen0_reconstructed_t0": 98304, "gen0_reconstructed_t1": 65520, "gen1_live_t0": 32448},
            "reused_games_are_not_newly_executed": True,
            "ledger_artifact": ledger_identity,
        }, "ledger_summary_sha256")
        ledger_summary_path = output_root / "completed_game_ledger_summary.json"
        atomic_json(ledger_summary_path, ledger_summary)

        populations, seeds, seed_summary = _select_seed_population(
            store=store, index=index, old_checkpoint=old_checkpoint,
            development_manifest=development_manifest, registry=registry,
            context_registry=context_registry,
        )
        seed_payload = _signed({
            "schema_version": 1,
            "kind": "two_day_seed_population",
            "created_at": _utc_now(),
            "old_execution_manifest_sha256": raw_manifest["execution_manifest_sha256"],
            "compatibility_sha256": compatibility["compatibility_sha256"],
            "population_ids": populations,
            "seeds": seeds,
            "summary": seed_summary,
            "pool_lanes": False,
        }, "seed_population_sha256")
        seed_path = output_root / "seed_population.json"
        atomic_json(seed_path, seed_payload)

        catalog_path = output_root / "imported_candidate_catalog.jsonl.gz"
        catalog_rows = (
            {
                "candidate_id": str(candidate_id), "old_generation": int(generation),
                "island_id": str(island_id), "semantic_json": str(semantic_json),
                "semantic_sha256": str(semantic_sha256),
            }
            for candidate_id, semantic_sha256, semantic_json, generation, island_id in index.execute(
                "SELECT candidate_id,semantic_sha256,semantic_json,generation,island_id FROM candidates ORDER BY candidate_id"
            )
        )
        catalog_identity = _write_jsonl_gzip(catalog_path, catalog_rows)
        if catalog_identity["rows"] != 31384:
            raise TwoDayError("imported semantic catalog does not contain exactly 31,384 candidates")

        contract_payload = _build_contract(
            calibration=calibration, compatibility=compatibility, ledger_summary=ledger_summary,
        )
        contract_path = output_root / "two_day_contract.json"
        atomic_json(contract_path, contract_payload)
        contract = load_two_day_contract(contract_path)
        context_reference = _signed({
            "schema_version": 1,
            "kind": "two_day_context_registry_reference",
            "source_registry_path": str((old_run / "context_registry.json").resolve()),
            "source_registry_sha256": context_registry.sha256,
            "copied_registry": _identity(context_path),
            "stage_counts": {stage: len(context_registry.contexts(stage)) for stage in ("t0", "t1", "holdout")},
            "holdout_untouched": True,
        }, "context_reference_sha256")
        context_reference_path = output_root / "context_registry_reference.json"
        atomic_json(context_reference_path, context_reference)

        preflight = _signed({
            "schema_version": 1,
            "kind": "two_day_preflight",
            "created_at": _utc_now(),
            "old_run_root": str(old_run.resolve()),
            "old_database_identities_before_and_after_readonly_copy": old_database_identities,
            "old_database_identities_stable_after_readonly_copy": True,
            "control_cache_sha256": control_cache_sha256,
            "old_execution_manifest": _identity(old_run / "execution_manifest.json"),
            "old_execution_checkpoint": _identity(old_run / "execution_checkpoint.json"),
            "formal_stop": _identity(stop_path),
            "stopped_database_identity": _identity(DEFAULT_STOP_DATABASE_IDENTITY),
            "source_snapshot": current_sources,
            "source_snapshot_sha256": current_source_digest,
            "official_runtime_dependencies": compatibility["official_runtime_dependencies"],
            "root_manifest_sha256": registry.manifest()["manifest_sha256"],
            "compatibility": _identity(compatibility_path),
            "completed_game_ledger": _identity(ledger_summary_path),
            "imported_candidate_catalog": catalog_identity,
            "seed_population": _identity(seed_path),
            "context_registry_reference": _identity(context_reference_path),
            "calibration": _identity(calibration_path),
            "contract": _identity(contract_path),
            "free_bytes": shutil.disk_usage(output_root).free,
            "minimum_free_bytes": MINIMUM_FREE_BYTES,
            "old_run_read_only": True,
            "production_sources_modified": False,
            "holdout_executed": False,
        }, "preflight_sha256")
        preflight_path = output_root / "preflight.json"
        atomic_json(preflight_path, preflight)

        manifest_payload = _signed({
            "schema_version": 1,
            "kind": "two_day_execution_manifest",
            "run_id": run_id,
            "created_at": _utc_now(),
            "formal_execution_authorized": True,
            "formal_authorization_id": authorization_id,
            "contract": _identity(contract_path),
            "preflight": _identity(preflight_path),
            "context_registry": _identity(context_path),
            "context_registry_sha256": context_registry.sha256,
            "context_registry_reference": _identity(context_reference_path),
            "compatibility": _identity(compatibility_path),
            "completed_game_ledger": _identity(ledger_summary_path),
            "seed_population": _identity(seed_path),
            "imported_candidate_catalog": catalog_identity,
            "calibration": _identity(calibration_path),
            "old_development_manifest_path": str((Path(str(raw_manifest["preflight_root"])) / "manifest.json").resolve()),
            "old_development_manifest_sha256": development_manifest.sha256,
            "proposal_seed": int(development_manifest.payload["proposal_seed"]),
            "physical_workers": PHYSICAL_WORKERS,
            "active_in_flight": int(calibration["active_in_flight"]),
            "throttle_mode": "bounded_active_in_flight",
            "backend": "official",
            "retention_policy": contract.payload["execution_boundary"]["storage_retention"],
            "minimum_free_bytes": MINIMUM_FREE_BYTES,
            "baseline_imported_candidates": catalog_identity["rows"],
            "imported_seed_t0_fitness": seed_summary["selected"],
            "imported_seed_combined_fitness": seed_summary["combined_fitness_reused"],
            "control_cache_sha256": control_cache_sha256,
            "reused_completed_game_keys": ledger_summary["completed_game_keys"],
            "newly_executed_games_at_prepare": 0,
            "pool_lanes": False,
            "holdout_executed": False,
            "automatic_broad_launch": False,
            "automatic_promotion": False,
            "automatic_submission": False,
        }, "manifest_sha256")
        manifest_path = output_root / "execution_manifest.json"
        atomic_json(manifest_path, manifest_payload)
        manifest = ManifestView(manifest_payload, str(manifest_payload["manifest_sha256"]))

        with CandidateIndex(output_root / "execution_candidate_index.sqlite", manifest_sha256=manifest.sha256) as new_index:
            layout_lanes = {row.island_id: row.lane for row in island_layout(contract)}
            for row in _read_jsonl_gzip(catalog_identity):
                genome_payload = json.loads(row["semantic_json"])
                genome_payload["candidate_id"] = row["candidate_id"]
                genome = FullTapeGenome.from_dict(genome_payload)
                if not new_index.add(genome, -1, str(row["island_id"]), expected_lane=layout_lanes[str(row["island_id"])]):
                    raise TwoDayError("imported semantic catalog contains a duplicate candidate")
            new_index.commit()
            if new_index.count() != 31384:
                raise TwoDayError("new candidate index baseline count mismatch")

        with SearchStore(output_root / "execution_store.sqlite", execution_manifest_sha256=manifest.sha256) as new_store:
            for lane, _context_id, encoded, digest in store.execute(
                "SELECT lane,context_id,payload_json,payload_sha256 FROM controls ORDER BY lane,context_id"
            ):
                if _sha_bytes(encoded.encode("utf-8")) != digest:
                    raise TwoDayError("old control payload hash mismatch during import")
                new_store.put_control(str(lane), json.loads(encoded))
            for candidate_id, row in seeds.items():
                new_store.put_fitness(
                    FitnessVector(**row["fitness_t0"]), scope="t0", generation=0,
                    island_id=str(row["island_id"]),
                    diagnostics={"imported_from": row["source"], "old": row["fitness_t0_diagnostics"]},
                )
                if "fitness_combined" in row:
                    new_store.put_fitness(
                        FitnessVector(**row["fitness_combined"]), scope="combined", generation=0,
                        island_id=str(row["island_id"]),
                        diagnostics={"imported_from": row["source"], "old": row["fitness_combined_diagnostics"]},
                    )
            new_store.commit()
            counts = new_store.counts()
            expected = {
                "controls": 60, "t0": 0, "t1": 0,
                "fitness_t0": seed_summary["selected"],
                "fitness_combined": seed_summary["combined_fitness_reused"],
            }
            if counts != expected:
                raise TwoDayError("prepared store import counts do not close")

    checkpoint = _signed({
        "schema_version": 1,
        "kind": "two_day_execution_checkpoint",
        "run_id": run_id,
        "manifest_sha256": manifest_payload["manifest_sha256"],
        "status": "prepared",
        "last_completed_generation": 0,
        "next_generation": 1,
        "population_ids": populations,
        "baseline_imported_candidates": 31384,
        "new_candidates_created": 0,
        "reused_completed_game_keys": 196272,
        "new_t0_games_executed": 0,
        "new_t1_games_executed": 0,
        "newly_executed_games": 0,
        "total_completed_game_keys": 196272,
        "holdout_executed": False,
    }, "checkpoint_sha256")
    atomic_json(output_root / "execution_checkpoint.json", checkpoint)
    return {
        "run_root": str(output_root), "manifest_sha256": manifest_payload["manifest_sha256"],
        "contract_sha256": contract.sha256, "reused_completed_game_keys": 196272,
        "newly_executed_games": 0, "quota": contract.payload["quotas"],
        "seed_summary": seed_summary, "physical_workers": PHYSICAL_WORKERS,
        "active_in_flight": calibration["active_in_flight"], "formal_execution_authorized": True,
    }


def _load_manifest(run_root: Path) -> tuple[ManifestView, TwoDayContract, ContextRegistry, Mapping[str, Any]]:
    payload = json.loads((run_root / "execution_manifest.json").read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version", "kind", "run_id", "created_at", "formal_execution_authorized",
        "formal_authorization_id", "contract", "preflight", "context_registry",
        "context_registry_sha256", "context_registry_reference", "compatibility",
        "completed_game_ledger", "seed_population", "imported_candidate_catalog",
        "calibration", "old_development_manifest_path", "old_development_manifest_sha256",
        "proposal_seed", "physical_workers", "active_in_flight", "throttle_mode", "backend",
        "retention_policy", "minimum_free_bytes", "baseline_imported_candidates",
        "imported_seed_t0_fitness", "imported_seed_combined_fitness", "control_cache_sha256",
        "reused_completed_game_keys", "newly_executed_games_at_prepare", "pool_lanes",
        "holdout_executed", "automatic_broad_launch", "automatic_promotion",
        "automatic_submission", "manifest_sha256",
    }
    if (
        set(payload) != expected_keys
        or not verify_signature(payload, "manifest_sha256")
        or payload.get("schema_version") != 1
        or payload.get("kind") != "two_day_execution_manifest"
    ):
        raise TwoDayError("two-day execution manifest signature or kind mismatch")
    if (
        payload.get("formal_execution_authorized") is not True
        or payload.get("physical_workers") != PHYSICAL_WORKERS
        or not isinstance(payload.get("active_in_flight"), int)
        or not 1 <= payload["active_in_flight"] <= PHYSICAL_WORKERS
        or payload.get("throttle_mode") != "bounded_active_in_flight"
        or payload.get("backend") != "official"
        or payload.get("minimum_free_bytes") != MINIMUM_FREE_BYTES
        or payload.get("baseline_imported_candidates") != 31384
        or payload.get("imported_seed_t0_fitness") != 2048
        or payload.get("reused_completed_game_keys") != 196272
        or payload.get("newly_executed_games_at_prepare") != 0
        or payload.get("pool_lanes") is not False
        or payload.get("holdout_executed") is not False
        or any(payload.get(key) is not False for key in (
            "automatic_broad_launch", "automatic_promotion", "automatic_submission",
        ))
    ):
        raise TwoDayError("two-day execution manifest boundary drift")
    for key in (
        "contract", "preflight", "context_registry", "context_registry_reference", "compatibility",
        "completed_game_ledger", "seed_population", "imported_candidate_catalog", "calibration",
    ):
        _verify_identity(payload[key])
    contract = load_two_day_contract(Path(str(payload["contract"]["path"])))
    context_registry = ContextRegistry.load(Path(str(payload["context_registry"]["path"])), require_mode="formal")
    if context_registry.sha256 != payload["context_registry_sha256"]:
        raise TwoDayError("two-day context registry drift")
    verify_opponent_artifacts(context_registry)
    preflight = json.loads(Path(str(payload["preflight"]["path"])).read_text(encoding="utf-8"))
    if not verify_signature(preflight, "preflight_sha256"):
        raise TwoDayError("two-day preflight signature mismatch")
    if (
        payload["retention_policy"] != contract.payload["execution_boundary"]["storage_retention"]
        or payload["active_in_flight"] != contract.payload["execution_boundary"]["active_in_flight"]
        or payload["control_cache_sha256"] != preflight.get("control_cache_sha256")
    ):
        raise TwoDayError("manifest, contract, and preflight execution boundary mismatch")
    calibration = json.loads(Path(str(payload["calibration"]["path"])).read_text(encoding="utf-8"))
    _validate_calibration(calibration)
    if (
        calibration["active_in_flight"] != payload["active_in_flight"]
        or calibration["source_snapshot_sha256"] != preflight["source_snapshot_sha256"]
    ):
        raise TwoDayError("manifest calibration drift")
    compatibility = json.loads(Path(str(payload["compatibility"]["path"])).read_text(encoding="utf-8"))
    if not verify_signature(compatibility, "compatibility_sha256"):
        raise TwoDayError("reuse compatibility signature mismatch")
    if (
        compatibility["compatibility_sha256"] != contract.payload["reuse"]["critical_compatibility_sha256"]
        or compatibility["compatibility_sha256"] != calibration["critical_compatibility_sha256"]
    ):
        raise TwoDayError("reuse compatibility differs across contract and calibration")
    _verify_runtime_dependencies(compatibility["official_runtime_dependencies"])
    ledger = json.loads(Path(str(payload["completed_game_ledger"]["path"])).read_text(encoding="utf-8"))
    if (
        not verify_signature(ledger, "ledger_summary_sha256")
        or ledger.get("completed_game_keys") != 196272
        or ledger.get("reused_games_are_not_newly_executed") is not True
    ):
        raise TwoDayError("completed-game ledger summary mismatch")
    _verify_identity(ledger["ledger_artifact"])
    seed = json.loads(Path(str(payload["seed_population"]["path"])).read_text(encoding="utf-8"))
    if (
        not verify_signature(seed, "seed_population_sha256")
        or seed.get("summary", {}).get("selected") != 2048
        or seed.get("pool_lanes") is not False
    ):
        raise TwoDayError("seed population signature or lane boundary mismatch")
    context_reference = json.loads(Path(str(payload["context_registry_reference"]["path"])).read_text(encoding="utf-8"))
    if (
        not verify_signature(context_reference, "context_reference_sha256")
        or context_reference.get("source_registry_sha256") != context_registry.sha256
        or context_reference.get("holdout_untouched") is not True
    ):
        raise TwoDayError("context registry reference mismatch")
    registry = RootRegistry.load_workspace(WORKSPACE, include_public=True)
    current = source_snapshot(WORKSPACE, contract, registry)
    if _sha_bytes(canonical_json(current).encode("utf-8")) != preflight["source_snapshot_sha256"]:
        raise TwoDayError("source, engine, controls, routes, roots, or implementation drift since preflight")
    if shutil.disk_usage(run_root).free < int(payload["minimum_free_bytes"]):
        raise TwoDayError("two-day execution lacks its dynamic-storage reserve")
    return ManifestView(payload, str(payload["manifest_sha256"])), contract, context_registry, compatibility


def _validate_imported_state(
    *, manifest: ManifestView, checkpoint: Mapping[str, Any], index: CandidateIndex, store: SearchStore,
) -> None:
    catalog_rows = _read_jsonl_gzip(manifest.payload["imported_candidate_catalog"])
    database_rows = index.connection.execute(
        "SELECT candidate_id,semantic_sha256,semantic_json,island_id FROM candidates "
        "WHERE generation=-1 ORDER BY candidate_id"
    )
    count = 0
    for artifact_row, database_row in zip(catalog_rows, database_rows, strict=True):
        expected = (
            artifact_row["candidate_id"], artifact_row["semantic_sha256"],
            artifact_row["semantic_json"], artifact_row["island_id"],
        )
        if tuple(database_row) != expected:
            raise TwoDayError("prepared candidate-index baseline differs from signed imported catalog")
        count += 1
    if count != int(manifest.payload["baseline_imported_candidates"]):
        raise TwoDayError("prepared candidate-index baseline count mismatch")
    if _control_cache_digest(store.connection) != manifest.payload["control_cache_sha256"]:
        raise TwoDayError("prepared control cache differs from signed import")
    seed = json.loads(Path(str(manifest.payload["seed_population"]["path"])).read_text(encoding="utf-8"))
    if checkpoint["population_ids"] != seed["population_ids"] and checkpoint["last_completed_generation"] == 0:
        raise TwoDayError("prepared checkpoint population differs from signed seed population")
    for candidate_id, row in seed["seeds"].items():
        if asdict(store.fitness(candidate_id, "t0")) != row["fitness_t0"]:
            raise TwoDayError("prepared T0 fitness differs from signed seed evidence")
        if "fitness_combined" in row and asdict(store.fitness(candidate_id, "combined")) != row["fitness_combined"]:
            raise TwoDayError("prepared combined fitness differs from signed seed evidence")


def _load_checkpoint(path: Path, *, manifest: ManifestView, contract: TwoDayContract) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version", "kind", "run_id", "manifest_sha256", "status",
        "last_completed_generation", "next_generation", "population_ids",
        "baseline_imported_candidates", "new_candidates_created",
        "reused_completed_game_keys", "new_t0_games_executed", "new_t1_games_executed",
        "newly_executed_games", "total_completed_game_keys", "holdout_executed",
        "checkpoint_sha256",
    }
    if (
        set(payload) != expected_keys
        or not verify_signature(payload, "checkpoint_sha256")
        or payload.get("schema_version") != 1
        or payload.get("kind") != "two_day_execution_checkpoint"
        or payload.get("manifest_sha256") != manifest.sha256
    ):
        raise TwoDayError("two-day checkpoint signature or manifest drift")
    if payload.get("holdout_executed") is not False:
        raise TwoDayError("two-day checkpoint claims holdout execution")
    next_generation = payload.get("next_generation")
    if not isinstance(next_generation, int) or not 1 <= next_generation <= contract.generations:
        raise TwoDayError("two-day checkpoint cursor is malformed")
    last = payload.get("last_completed_generation")
    if not isinstance(last, int) or isinstance(last, bool) or next_generation != last + 1:
        raise TwoDayError("two-day checkpoint generation cursor does not advance by one")
    expected_progress = _expected_counts(contract, manifest, last) if last >= 1 else {
        "new_candidates": 0, "promotions": 0, "new_t0": 0, "new_t1": 0,
    }
    if (
        payload.get("baseline_imported_candidates") != 31384
        or payload.get("new_candidates_created") != expected_progress["new_candidates"]
        or payload.get("reused_completed_game_keys") != 196272
        or payload.get("new_t0_games_executed") != expected_progress["new_t0"]
        or payload.get("new_t1_games_executed") != expected_progress["new_t1"]
        or payload.get("newly_executed_games") != expected_progress["new_t0"] + expected_progress["new_t1"]
        or payload.get("total_completed_game_keys") != 196272 + expected_progress["new_t0"] + expected_progress["new_t1"]
    ):
        raise TwoDayError("two-day checkpoint reused/new counter closure mismatch")
    expected_status = "completed" if next_generation == contract.generations else "prepared" if next_generation == 1 else "running"
    if payload.get("status") != expected_status:
        raise TwoDayError("two-day checkpoint status differs from its cursor")
    populations = payload.get("population_ids")
    layout = {row.island_id: row for row in island_layout(contract)}
    if not isinstance(populations, Mapping) or set(populations) != set(layout):
        raise TwoDayError("two-day checkpoint island set differs")
    all_ids = []
    for island_id, values in populations.items():
        if not isinstance(values, list) or len(values) != RESIDENTS_PER_ISLAND:
            raise TwoDayError("two-day checkpoint island capacity differs")
        if any(candidate_lane(candidate_id) != layout[island_id].lane for candidate_id in values):
            raise TwoDayError("two-day checkpoint crosses lane ownership")
        all_ids.extend(values)
    if len(all_ids) != len(set(all_ids)):
        raise TwoDayError("two-day checkpoint duplicates a resident")
    return payload


def _generation_paths(run_root: Path, generation: int) -> tuple[Path, Path]:
    stem = f"two_day_generation_{generation:04d}"
    return run_root / f"{stem}_prepared.json", run_root / f"{stem}_summary.json"


def _expected_counts(contract: TwoDayContract, manifest: ManifestView, generation: int) -> dict[str, int]:
    completed_generations = generation
    births = completed_generations * contract.birth_quota(1)
    promotions = completed_generations * contract.t1_promotion_quota(1)
    new_t0 = births * len(ContextRegistry.load(Path(str(manifest.payload["context_registry"]["path"]))).contexts("t0"))
    new_t1 = promotions * len(ContextRegistry.load(Path(str(manifest.payload["context_registry"]["path"]))).contexts("t1"))
    return {"new_candidates": births, "promotions": promotions, "new_t0": new_t0, "new_t1": new_t1}


def _checkpoint_advanced(
    checkpoint: Mapping[str, Any], *, completion: Mapping[str, Any], contract: TwoDayContract,
) -> dict[str, Any]:
    generation = int(completion["generation"])
    next_generation = generation + 1
    expected = completion["expected_progress"]
    return _signed({
        "schema_version": 1,
        "kind": "two_day_execution_checkpoint",
        "run_id": checkpoint["run_id"],
        "manifest_sha256": checkpoint["manifest_sha256"],
        "status": "completed" if next_generation == contract.generations else "running",
        "last_completed_generation": generation,
        "next_generation": next_generation,
        "population_ids": completion["next_population_ids"],
        "baseline_imported_candidates": checkpoint["baseline_imported_candidates"],
        "new_candidates_created": expected["new_candidates"],
        "reused_completed_game_keys": checkpoint["reused_completed_game_keys"],
        "new_t0_games_executed": expected["new_t0"],
        "new_t1_games_executed": expected["new_t1"],
        "newly_executed_games": expected["new_t0"] + expected["new_t1"],
        "total_completed_game_keys": checkpoint["reused_completed_game_keys"] + expected["new_t0"] + expected["new_t1"],
        "holdout_executed": False,
    }, "checkpoint_sha256")


def _validate_completion(
    payload: Mapping[str, Any], *, manifest: ManifestView, contract: TwoDayContract,
    store: SearchStore, index: CandidateIndex,
) -> None:
    expected_keys = {
        "schema_version", "kind", "manifest_sha256", "generation", "candidate_count",
        "t1_promotions", "expected_progress", "store_counts", "candidate_index_count",
        "worker_pids", "elapsed_seconds", "games_per_second", "birth_artifact_sha256",
        "next_population_ids", "receipt_retention", "holdout_executed", "artifact_sha256",
    }
    if (
        set(payload) != expected_keys
        or not verify_signature(payload, "artifact_sha256")
        or payload.get("schema_version") != 1
        or payload.get("kind") != "two_day_generation_complete"
        or payload.get("manifest_sha256") != manifest.sha256
        or payload.get("holdout_executed") is not False
    ):
        raise TwoDayError("generation completion signature or manifest drift")
    generation = int(payload["generation"])
    expected = _expected_counts(contract, manifest, generation)
    if payload.get("expected_progress") != expected:
        raise TwoDayError("generation progress differs from the exact quota")
    imported_t0 = int(manifest.payload["imported_seed_t0_fitness"])
    imported_combined = int(manifest.payload["imported_seed_combined_fitness"])
    expected_store = {
        "controls": 60, "t0": expected["new_t0"], "t1": expected["new_t1"],
        "fitness_t0": imported_t0 + expected["new_candidates"],
        "fitness_combined": imported_combined + expected["promotions"],
    }
    if payload.get("store_counts") != expected_store or store.counts() != expected_store:
        raise TwoDayError("generation store counts do not close")
    if index.count() != int(manifest.payload["baseline_imported_candidates"]) + expected["new_candidates"]:
        raise TwoDayError("generation candidate index count does not close")
    if payload.get("candidate_count") != contract.birth_quota(generation):
        raise TwoDayError("generation candidate count differs from quota")
    if payload.get("t1_promotions") != contract.t1_promotion_quota(generation):
        raise TwoDayError("generation T1 promotions differ from quota")
    if payload.get("candidate_index_count") != index.count():
        raise TwoDayError("generation summary candidate-index count mismatch")
    if index.generation_count(generation) != contract.birth_quota(generation):
        raise TwoDayError("candidate index generation shard count mismatch")
    retention = payload.get("receipt_retention", {})
    if retention.get("receipt_counts") != {
        "t0": contract.birth_quota(generation) * 6,
        "t1": contract.t1_promotion_quota(generation) * 24,
    }:
        raise TwoDayError("generation retention counts differ from the tier quotas")
    pids = payload.get("worker_pids")
    if not isinstance(pids, list) or any(not isinstance(pid, int) or isinstance(pid, bool) or pid < 1 for pid in pids):
        raise TwoDayError("generation worker PID evidence is malformed")
    for field in ("elapsed_seconds", "games_per_second"):
        value = payload.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) <= 0:
            raise TwoDayError(f"generation {field} is malformed")
    if not isinstance(payload.get("birth_artifact_sha256"), str) or len(payload["birth_artifact_sha256"]) != 64:
        raise TwoDayError("generation birth artifact digest is malformed")
    populations = payload.get("next_population_ids")
    layout = {row.island_id: row for row in island_layout(contract)}
    if not isinstance(populations, Mapping) or set(populations) != set(layout):
        raise TwoDayError("generation next-population island set differs")
    all_ids: list[str] = []
    for island_id, values in populations.items():
        if (
            not isinstance(values, list) or len(values) != RESIDENTS_PER_ISLAND
            or any(candidate_lane(candidate_id) != layout[island_id].lane for candidate_id in values)
        ):
            raise TwoDayError("generation next population capacity or lane differs")
        all_ids.extend(values)
    if len(all_ids) != len(set(all_ids)):
        raise TwoDayError("generation next population duplicates a resident")


def _recover(
    *, run_root: Path, checkpoint: dict[str, Any], manifest: ManifestView,
    contract: TwoDayContract, store: SearchStore, index: CandidateIndex,
) -> dict[str, Any]:
    last = int(checkpoint["last_completed_generation"])
    if last >= 1:
        prepared, final = _generation_paths(run_root, last)
        if prepared.is_file():
            if final.exists():
                raise TwoDayError("both prepared and final prior generation summaries exist")
            payload = json.loads(prepared.read_text(encoding="utf-8"))
            _validate_completion(payload, manifest=manifest, contract=contract, store=store, index=index)
            _ensure_generation_pruned(
                run_root, store=store, manifest=manifest, generation=last,
                retention=payload["receipt_retention"],
            )
            _validate_completion(payload, manifest=manifest, contract=contract, store=store, index=index)
            os.replace(prepared, final)
    generation = int(checkpoint["next_generation"])
    if generation == contract.generations:
        return checkpoint
    prepared, final = _generation_paths(run_root, generation)
    path = final if final.is_file() else prepared if prepared.is_file() else None
    if path is None:
        return checkpoint
    payload = json.loads(path.read_text(encoding="utf-8"))
    _validate_completion(payload, manifest=manifest, contract=contract, store=store, index=index)
    _ensure_generation_pruned(
        run_root, store=store, manifest=manifest, generation=generation,
        retention=payload["receipt_retention"],
    )
    _validate_completion(payload, manifest=manifest, contract=contract, store=store, index=index)
    store.put_generation_summary(generation, payload)
    store.commit()
    checkpoint = _checkpoint_advanced(checkpoint, completion=payload, contract=contract)
    atomic_json(run_root / "execution_checkpoint.json", checkpoint)
    if path == prepared:
        os.replace(prepared, final)
    return checkpoint


def _write_finalists(run_root: Path, *, manifest: ManifestView, store: SearchStore) -> Mapping[str, Any]:
    rows = {lane: store.top_combined(lane, 50) for lane in LANES}
    if any(len(values) != 50 for values in rows.values()):
        raise TwoDayError("completed two-day run has fewer than 50 eligible finalists in a lane")
    payload = _signed({
        "schema_version": 1,
        "kind": "two_day_broad_finalists",
        "manifest_sha256": manifest.sha256,
        "by_lane": rows,
        "finalists_per_lane": 50,
        "pool_lanes": False,
        "holdout_executed": False,
        "automatic_broad_launch": False,
        "automatic_promotion": False,
        "automatic_submission": False,
    }, "artifact_sha256")
    atomic_json(run_root / "broad_finalists.json", payload)
    return payload


def run(*, run_root: Path, stop_after_generation: int | None = None) -> dict[str, Any]:
    manifest, contract, context_registry, compatibility_payload = _load_manifest(run_root)
    checkpoint_path = run_root / "execution_checkpoint.json"
    checkpoint = _load_checkpoint(checkpoint_path, manifest=manifest, contract=contract)
    if stop_after_generation is not None and not 1 <= stop_after_generation < contract.generations:
        raise TwoDayError("stop-after generation is outside the execution generations")
    maximum = contract.generations if stop_after_generation is None else stop_after_generation + 1
    old_contract = load_contract(DEFAULT_OLD_CONTRACT)
    development_manifest = RunManifest.load(
        Path(str(manifest.payload["old_development_manifest_path"])),
        expected_contract_sha256=old_contract.sha256,
    )
    if (
        development_manifest.sha256 != manifest.payload["old_development_manifest_sha256"]
        or int(development_manifest.payload["proposal_seed"]) != int(manifest.payload["proposal_seed"])
    ):
        raise TwoDayError("old development manifest hash or proposal seed drift")
    registry = RootRegistry.load_workspace(WORKSPACE, include_public=True)
    runtime_dependencies = list(compatibility_payload["official_runtime_dependencies"])
    observed_pids: set[int] = set()
    started_all = time.perf_counter()
    with CandidateIndex(
        run_root / "execution_candidate_index.sqlite", manifest_sha256=manifest.sha256,
    ) as index, SearchStore(
        run_root / "execution_store.sqlite", execution_manifest_sha256=manifest.sha256,
    ) as store, ParallelEvaluator(
        workspace=WORKSPACE,
        root_manifest_sha256=development_manifest.payload["root_manifest"]["manifest_sha256"],
        workers=int(manifest.payload["physical_workers"]),
        max_in_flight=int(manifest.payload["active_in_flight"]),
    ) as evaluator:
        _validate_imported_state(
            manifest=manifest, checkpoint=checkpoint, index=index, store=store,
        )
        checkpoint = _recover(
            run_root=run_root, checkpoint=checkpoint, manifest=manifest,
            contract=contract, store=store, index=index,
        )
        generations_completed = 0
        while int(checkpoint["next_generation"]) < maximum:
            if shutil.disk_usage(run_root).free < int(manifest.payload["minimum_free_bytes"]):
                raise TwoDayError("two-day run paused before generation because free storage is below reserve")
            # Opponent files are executable game inputs, not documentation.
            # Recheck their actual bytes at every generation boundary so a
            # long run cannot combine reused evidence with drifted new games.
            verify_opponent_artifacts(context_registry)
            _verify_runtime_dependencies(runtime_dependencies)
            current_sources = source_snapshot(WORKSPACE, contract, registry)
            preflight = json.loads(Path(str(manifest.payload["preflight"]["path"])).read_text(encoding="utf-8"))
            if _sha_bytes(canonical_json(current_sources).encode("utf-8")) != preflight["source_snapshot_sha256"]:
                raise TwoDayError("runtime source drift before generation")
            generation = int(checkpoint["next_generation"])
            started = time.perf_counter()
            previous = {key: list(value) for key, value in checkpoint["population_ids"].items()}
            births, birth_artifact = _ensure_births(
                run_root=run_root, contract=contract, manifest=manifest,
                development_manifest=development_manifest, registry=registry,
                index=index, generation=generation, populations=previous,
            )
            candidates = {row.island_id: [] for row in island_layout(contract)}
            for birth in births:
                candidates[birth.island_id].append(birth.genome.candidate_id)
            pids = _evaluate_candidates(
                store, evaluator=evaluator, manifest=manifest, index=index,
                candidates_by_island=candidates, generation=generation, tier="t0",
                contexts=context_registry.contexts("t0"),
            )
            t0_fitness = _score_candidates(
                store, development_manifest=development_manifest, index=index, registry=registry,
                candidates_by_island=candidates, generation=generation, scope="t0",
                tiers=("t0",), contexts=context_registry.contexts("t0"),
            )
            promotions = _select_promotions(
                store, contract=contract, manifest=manifest, generation=generation,
                candidates_by_island=candidates, t0_fitness=t0_fitness,
            )
            pids.update(_evaluate_candidates(
                store, evaluator=evaluator, manifest=manifest, index=index,
                candidates_by_island=promotions, generation=generation, tier="t1",
                contexts=context_registry.contexts("t1"),
            ))
            observed_pids.update(pids)
            _score_candidates(
                store, development_manifest=development_manifest, index=index, registry=registry,
                candidates_by_island=promotions, generation=generation, scope="combined",
                tiers=("t0", "t1"),
                contexts=tuple(context_registry.contexts("t0")) + tuple(context_registry.contexts("t1")),
            )
            next_populations = _select_population(
                contract=contract, manifest=manifest, store=store,
                previous=previous, births=candidates,
            )
            retention = _prepare_receipt_retention(
                run_root, store=store, manifest=manifest, generation=generation,
            )
            expected = _expected_counts(contract, manifest, generation)
            completion = _signed({
                "schema_version": 1,
                "kind": "two_day_generation_complete",
                "manifest_sha256": manifest.sha256,
                "generation": generation,
                "candidate_count": len(births),
                "t1_promotions": sum(len(values) for values in promotions.values()),
                "expected_progress": expected,
                "store_counts": store.counts(),
                "candidate_index_count": index.count(),
                "worker_pids": sorted(pids),
                "elapsed_seconds": time.perf_counter() - started,
                "games_per_second": (
                    (len(births) * len(context_registry.contexts("t0"))
                     + sum(len(values) for values in promotions.values()) * len(context_registry.contexts("t1")))
                    / max(time.perf_counter() - started, 1e-9)
                ),
                "birth_artifact_sha256": birth_artifact["artifact_sha256"],
                "next_population_ids": next_populations,
                "receipt_retention": retention,
                "holdout_executed": False,
            }, "artifact_sha256")
            prepared, final = _generation_paths(run_root, generation)
            _validate_completion(completion, manifest=manifest, contract=contract, store=store, index=index)
            atomic_json(prepared, completion)
            _ensure_generation_pruned(
                run_root, store=store, manifest=manifest, generation=generation,
                retention=retention,
            )
            _validate_completion(completion, manifest=manifest, contract=contract, store=store, index=index)
            store.put_generation_summary(generation, completion)
            store.commit()
            checkpoint = _checkpoint_advanced(checkpoint, completion=completion, contract=contract)
            atomic_json(checkpoint_path, checkpoint)
            os.replace(prepared, final)
            generations_completed += 1
        finalists = None
        if int(checkpoint["next_generation"]) == contract.generations:
            if checkpoint["newly_executed_games"] != contract.scale["newly_executed_t0_t1_games"]:
                raise TwoDayError("formal completion does not close the new-execution quota")
            if checkpoint["total_completed_game_keys"] != contract.scale["total_completed_t0_t1_game_keys"]:
                raise TwoDayError("formal completion does not close reused plus new game keys")
            finalists = _write_finalists(run_root, manifest=manifest, store=store)
    return {
        "schema_version": 1,
        "kind": "two_day_execution_result",
        "run_root": str(run_root),
        "manifest_sha256": manifest.sha256,
        "status": checkpoint["status"],
        "next_generation": checkpoint["next_generation"],
        "generations_completed_this_call": generations_completed,
        "reused_completed_game_keys": checkpoint["reused_completed_game_keys"],
        "newly_executed_games": checkpoint["newly_executed_games"],
        "total_completed_game_keys": checkpoint["total_completed_game_keys"],
        "physical_workers": manifest.payload["physical_workers"],
        "active_in_flight": manifest.payload["active_in_flight"],
        "worker_processes_observed": len(observed_pids),
        "elapsed_seconds_this_call": time.perf_counter() - started_all,
        "broad_finalists_written": finalists is not None,
        "holdout_executed": False,
        "automatic_broad_launch": False,
        "automatic_promotion": False,
        "automatic_submission": False,
    }


def status(run_root: Path) -> dict[str, Any]:
    if not run_root.exists():
        return {"exists": False, "run_root": str(run_root)}
    manifest_path = run_root / "execution_manifest.json"
    checkpoint_path = run_root / "execution_checkpoint.json"
    if not manifest_path.is_file() or not checkpoint_path.is_file():
        return {"exists": True, "complete_metadata": False, "run_root": str(run_root)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    return {
        "exists": True,
        "complete_metadata": True,
        "run_root": str(run_root),
        "run_id": manifest.get("run_id"),
        "manifest_signature_valid": verify_signature(manifest, "manifest_sha256"),
        "checkpoint_signature_valid": verify_signature(checkpoint, "checkpoint_sha256"),
        "status": checkpoint.get("status"),
        "last_completed_generation": checkpoint.get("last_completed_generation"),
        "next_generation": checkpoint.get("next_generation"),
        "reused_completed_game_keys": checkpoint.get("reused_completed_game_keys"),
        "newly_executed_games": checkpoint.get("newly_executed_games"),
        "total_completed_game_keys": checkpoint.get("total_completed_game_keys"),
        "physical_workers": manifest.get("physical_workers"),
        "active_in_flight": manifest.get("active_in_flight"),
        "holdout_executed": checkpoint.get("holdout_executed"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    calibration = subparsers.add_parser("calibrate")
    calibration.add_argument("--old-run-root", type=Path, default=DEFAULT_OLD_RUN)
    calibration.add_argument("--stop-evidence", type=Path, default=DEFAULT_STOP)
    calibration.add_argument("--output", type=Path, required=True)
    calibration.add_argument("--workers", type=int, default=PHYSICAL_WORKERS)
    calibration.add_argument("--active-in-flight", type=int, required=True)
    calibration.add_argument("--candidate-batches", type=int, default=22)
    calibration.add_argument("--require-gates", action="store_true")

    preparation = subparsers.add_parser("prepare")
    preparation.add_argument("--old-run-root", type=Path, default=DEFAULT_OLD_RUN)
    preparation.add_argument("--stop-evidence", type=Path, default=DEFAULT_STOP)
    preparation.add_argument("--calibration", type=Path, required=True)
    preparation.add_argument("--output-root", type=Path, required=True)
    preparation.add_argument("--run-id", required=True)
    preparation.add_argument("--authorization-id", required=True)

    execution = subparsers.add_parser("run")
    execution.add_argument("--run-root", type=Path, required=True)
    execution.add_argument("--stop-after-generation", type=int)

    inspection = subparsers.add_parser("status")
    inspection.add_argument("--run-root", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "calibrate":
        result = calibrate(
            old_run=args.old_run_root.resolve(), stop_path=args.stop_evidence.resolve(),
            output=args.output.resolve(), physical_workers=args.workers,
            active_in_flight=args.active_in_flight, candidate_batches=args.candidate_batches,
            require_gates=args.require_gates,
        )
    elif args.command == "prepare":
        result = prepare(
            old_run=args.old_run_root.resolve(), stop_path=args.stop_evidence.resolve(),
            calibration_path=args.calibration.resolve(), output_root=args.output_root.resolve(),
            run_id=args.run_id, authorization_id=args.authorization_id,
        )
    elif args.command == "run":
        result = run(run_root=args.run_root.resolve(), stop_after_generation=args.stop_after_generation)
    else:
        result = status(args.run_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
