"""Closed execution manifest and resumable state for multi-generation search."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping

from .checkpoint import RunManifest, atomic_json, verify_signature
from .contexts import ContextRegistry
from .contract import SearchContract, canonical_json
from .evolution import island_layout
from .genome import GenomeError, candidate_lane


class ExecutionError(RuntimeError):
    pass


def _signed(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    if field in payload:
        raise ExecutionError(f"payload already contains {field}")
    result = dict(payload)
    result[field] = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return result


def file_identity(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _safe_token(value: Any, label: str) -> str:
    if (not isinstance(value, str) or not value
            or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in value)):
        raise ExecutionError(f"{label} must be a nonempty filesystem-safe token")
    return value


def load_calibration_artifact(
    path: Path,
    *,
    contract: SearchContract,
    source_snapshot_sha256: str,
    physical_workers: int,
) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schema_version", "kind", "contract_sha256", "source_snapshot_sha256",
        "execution_manifest_sha256", "backend", "physical_workers", "logical_cpus",
        "candidate_games", "elapsed_seconds", "games_per_second", "cpu_percent",
        "receipt_rows", "store_bytes", "bytes_per_receipt", "calibration_sha256",
    }
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise ExecutionError("calibration artifact schema is not closed")
    if not verify_signature(payload, "calibration_sha256"):
        raise ExecutionError("calibration artifact signature mismatch")
    if payload.get("schema_version") != 1 or payload.get("kind") != "maximum_search_worker_calibration":
        raise ExecutionError("unsupported calibration artifact")
    if payload.get("contract_sha256") != contract.sha256 or payload.get("source_snapshot_sha256") != source_snapshot_sha256:
        raise ExecutionError("calibration contract or source snapshot drift")
    if payload.get("backend") != "official" or payload.get("physical_workers") != physical_workers:
        raise ExecutionError("formal worker count lacks matching official calibration")
    for field in ("candidate_games", "logical_cpus", "receipt_rows", "store_bytes"):
        value = payload.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ExecutionError(f"calibration {field} is malformed")
    for field in ("elapsed_seconds", "games_per_second", "cpu_percent", "bytes_per_receipt"):
        value = payload.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) <= 0:
            raise ExecutionError(f"calibration {field} is malformed")
    minimum_games = max(128, physical_workers * 8)
    if payload["candidate_games"] < minimum_games:
        raise ExecutionError(
            f"formal calibration requires at least {minimum_games} candidate games for {physical_workers} workers"
        )
    cpu_target = contract.payload["execution_boundary"]["cpu_target_percent"]
    lower_cpu, upper_cpu = float(cpu_target[0]), float(cpu_target[1])
    if not lower_cpu <= float(payload["cpu_percent"]) <= upper_cpu:
        raise ExecutionError(
            f"formal calibration must measure {lower_cpu:g}-{upper_cpu:g} percent CPU utilization"
        )
    return payload


@dataclass(frozen=True)
class ExecutionManifest:
    payload: Mapping[str, Any]
    sha256: str

    @property
    def formal(self) -> bool:
        return bool(self.payload["formal_execution_authorized"])

    @property
    def limits(self) -> Mapping[str, Any]:
        return self.payload["limits"]

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        contract: SearchContract,
        development_manifest: RunManifest,
        preflight_root: Path,
        initial_population_path: Path,
        context_registry: ContextRegistry,
        physical_workers: int,
        max_in_flight: int,
        backend: str,
        formal_execution_authorized: bool,
        formal_authorization_id: str | None,
        development_generations: int | None = None,
        development_residents_per_island: int | None = None,
        development_births_per_island: int | None = None,
        development_t1_promotions_per_island: int | None = None,
        calibration_path: Path | None = None,
        storage_free_bytes: int | None = None,
    ) -> "ExecutionManifest":
        _safe_token(run_id, "execution run_id")
        if development_manifest.payload.get("contract_sha256") != contract.sha256:
            raise ExecutionError("development manifest and execution contract differ")
        if not isinstance(physical_workers, int) or isinstance(physical_workers, bool) or physical_workers < 1:
            raise ExecutionError("physical worker count must be a positive integer")
        logical_cpus = os.cpu_count() or 1
        if physical_workers > logical_cpus:
            raise ExecutionError(f"physical workers exceed detected logical CPUs ({logical_cpus})")
        if (not isinstance(max_in_flight, int) or isinstance(max_in_flight, bool)
                or max_in_flight < physical_workers or max_in_flight > physical_workers * 16):
            raise ExecutionError("max_in_flight must be between workers and workers*16")
        if backend not in {"official", "deterministic_mock"}:
            raise ExecutionError("execution backend must be official or deterministic_mock")

        if formal_execution_authorized:
            if context_registry.mode != "formal" or backend != "official":
                raise ExecutionError("formal execution requires a formal registry and official backend")
            authorization_id = _safe_token(formal_authorization_id, "formal authorization ID")
            supplied = (
                development_generations,
                development_residents_per_island,
                development_births_per_island,
                development_t1_promotions_per_island,
            )
            if any(value is not None for value in supplied):
                raise ExecutionError("formal execution cannot contain development limits")
            limits = {
                "generations": None,
                "residents_per_island": None,
                "births_per_island": None,
                "t1_promotions_per_island": None,
            }
            if calibration_path is None or not calibration_path.is_file():
                raise ExecutionError("formal execution requires a calibration artifact")
            source_snapshot_sha256 = hashlib.sha256(canonical_json(
                development_manifest.payload["source_snapshot"]
            ).encode("utf-8")).hexdigest()
            calibration = load_calibration_artifact(
                calibration_path, contract=contract,
                source_snapshot_sha256=source_snapshot_sha256,
                physical_workers=physical_workers,
            )
            calibration_identity: Mapping[str, Any] | None = file_identity(calibration_path)
            unbounded_receipt_bytes = int(
                int(contract.scale["t0_t1_candidate_games"]) * float(calibration["bytes_per_receipt"])
            )
            measured_free = shutil.disk_usage(initial_population_path.parent).free if storage_free_bytes is None else storage_free_bytes
            if not isinstance(measured_free, int) or isinstance(measured_free, bool) or measured_free < 1:
                raise ExecutionError("formal storage-free measurement is malformed")
            retention_policy = dict(contract.payload["execution_boundary"]["storage_retention"])
            required_free_bytes = int(retention_policy["minimum_free_bytes"])
            if measured_free < required_free_bytes:
                raise ExecutionError(
                    f"formal execution storage gate failed: free={measured_free} required={required_free_bytes}"
                )
            resource_projection: Mapping[str, Any] | None = {
                "measured_games_per_second": float(calibration["games_per_second"]),
                "measured_bytes_per_receipt": float(calibration["bytes_per_receipt"]),
                "projected_seconds": int(contract.scale["t0_t1_candidate_games"]) / float(calibration["games_per_second"]),
                "unbounded_raw_receipt_projection_bytes": unbounded_receipt_bytes,
                "dynamic_pruning_enabled": True,
                "minimum_runtime_free_bytes": required_free_bytes,
                "available_free_bytes": int(measured_free),
                "cpu_percent": float(calibration["cpu_percent"]),
            }
        else:
            if formal_authorization_id is not None:
                raise ExecutionError("development execution cannot contain a formal authorization ID")
            authorization_id = None
            if context_registry.mode != "development":
                raise ExecutionError("development execution requires a development context registry")
            values = {
                "generations": development_generations,
                "residents_per_island": development_residents_per_island,
                "births_per_island": development_births_per_island,
                "t1_promotions_per_island": development_t1_promotions_per_island,
            }
            if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in values.values()):
                raise ExecutionError("all development execution limits must be positive integers")
            if int(values["generations"]) > contract.generations:
                raise ExecutionError("development generation limit exceeds contract")
            if int(values["residents_per_island"]) > int(contract.scale["residents_per_island"]):
                raise ExecutionError("development resident limit exceeds island capacity")
            maximum_births = max(contract.island_birth_quotas(generation)[island.index]
                                 for generation in range(1, contract.generations)
                                 for island in island_layout(contract))
            if int(values["births_per_island"]) > maximum_births:
                raise ExecutionError("development birth limit exceeds formal island quota")
            if int(values["t1_promotions_per_island"]) > max(
                int(values["residents_per_island"]), int(values["births_per_island"])
            ):
                raise ExecutionError("development T1 promotion limit exceeds available generation candidates")
            limits = values
            if calibration_path is not None:
                raise ExecutionError("development execution does not bind a formal calibration artifact")
            if storage_free_bytes is not None:
                raise ExecutionError("development execution cannot override storage measurement")
            calibration_identity = None
            resource_projection = None
            retention_policy = dict(contract.payload["execution_boundary"]["storage_retention"])

        payload = {
            "schema_version": 1,
            "kind": "maximum_search_execution_manifest",
            "run_id": run_id,
            "contract_sha256": contract.sha256,
            "development_manifest_sha256": development_manifest.sha256,
            "preflight_root": str(preflight_root.resolve()),
            "initial_population_artifact": file_identity(initial_population_path),
            "context_registry_sha256": context_registry.sha256,
            "context_counts": {
                "t0": len(context_registry.contexts("t0")),
                "t1": len(context_registry.contexts("t1")),
                "holdout": len(context_registry.contexts("holdout")),
            },
            "physical_workers": physical_workers,
            "max_in_flight": max_in_flight,
            "backend": backend,
            "formal_execution_authorized": bool(formal_execution_authorized),
            "formal_authorization_id": authorization_id,
            "limits": limits,
            "calibration_artifact": calibration_identity,
            "resource_projection": resource_projection,
            "retention_policy": retention_policy,
            "automatic_broad_launch": False,
            "automatic_promotion": False,
            "automatic_submission": False,
        }
        signed = _signed(payload, "execution_manifest_sha256")
        return cls(signed, signed["execution_manifest_sha256"])

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        contract: SearchContract,
        development_manifest: RunManifest,
        context_registry: ContextRegistry,
    ) -> "ExecutionManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected = {
            "schema_version", "kind", "run_id", "contract_sha256",
            "development_manifest_sha256", "preflight_root", "initial_population_artifact",
            "context_registry_sha256", "context_counts", "physical_workers", "max_in_flight", "backend",
            "formal_execution_authorized", "formal_authorization_id", "limits",
            "calibration_artifact", "resource_projection",
            "retention_policy",
            "automatic_broad_launch", "automatic_promotion", "automatic_submission",
            "execution_manifest_sha256",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ExecutionError("execution manifest schema is not closed")
        if not verify_signature(payload, "execution_manifest_sha256"):
            raise ExecutionError("execution manifest signature mismatch")
        if payload.get("schema_version") != 1 or payload.get("kind") != "maximum_search_execution_manifest":
            raise ExecutionError("unsupported execution manifest")
        if payload.get("contract_sha256") != contract.sha256:
            raise ExecutionError("execution manifest contract drift")
        if payload.get("development_manifest_sha256") != development_manifest.sha256:
            raise ExecutionError("execution manifest preflight drift")
        if payload.get("context_registry_sha256") != context_registry.sha256:
            raise ExecutionError("execution manifest context drift")
        if any(payload.get(key) is not False for key in (
            "automatic_broad_launch", "automatic_promotion", "automatic_submission",
        )):
            raise ExecutionError("execution manifest contains an automatic later-tier action")
        initial = payload.get("initial_population_artifact")
        if not isinstance(initial, Mapping) or set(initial) != {"path", "bytes", "sha256"}:
            raise ExecutionError("execution initial-population identity is malformed")
        initial_path = Path(str(initial["path"]))
        if not initial_path.is_file() or file_identity(initial_path) != dict(initial):
            raise ExecutionError("execution initial-population artifact drift")
        _safe_token(payload.get("run_id"), "execution run_id")
        formal = payload.get("formal_execution_authorized")
        limits = payload.get("limits")
        if type(formal) is not bool or not isinstance(limits, Mapping) or set(limits) != {
            "generations", "residents_per_island", "births_per_island", "t1_promotions_per_island",
        }:
            raise ExecutionError("execution mode or limits are malformed")
        # Rebuild the manifest to close all semantic validation paths.
        rebuilt = cls.create(
            run_id=str(payload["run_id"]), contract=contract,
            development_manifest=development_manifest,
            preflight_root=Path(str(payload["preflight_root"])),
            initial_population_path=initial_path,
            context_registry=context_registry,
            physical_workers=payload["physical_workers"],
            max_in_flight=payload["max_in_flight"], backend=str(payload["backend"]),
            formal_execution_authorized=formal,
            formal_authorization_id=payload.get("formal_authorization_id"),
            development_generations=limits["generations"],
            development_residents_per_island=limits["residents_per_island"],
            development_births_per_island=limits["births_per_island"],
            development_t1_promotions_per_island=limits["t1_promotions_per_island"],
            calibration_path=(Path(payload["calibration_artifact"]["path"])
                              if isinstance(payload.get("calibration_artifact"), Mapping) else None),
            storage_free_bytes=(int(payload["resource_projection"]["available_free_bytes"])
                                if isinstance(payload.get("resource_projection"), Mapping) else None),
        )
        if canonical_json(rebuilt.payload) != canonical_json(payload):
            raise ExecutionError("execution manifest canonical content mismatch")
        return rebuilt


def _validate_populations(
    populations: Any,
    *,
    contract: SearchContract,
    capacity: int,
) -> None:
    if not isinstance(populations, Mapping):
        raise ExecutionError("execution populations must be an object")
    layout = {row.island_id: row for row in island_layout(contract)}
    if set(populations) != set(layout):
        raise ExecutionError("execution population islands differ from the contract")
    seen: set[str] = set()
    for island_id, island in layout.items():
        values = populations[island_id]
        if not isinstance(values, list) or len(values) != capacity:
            raise ExecutionError(f"{island_id} execution population capacity mismatch")
        for candidate_id in values:
            try:
                lane = candidate_lane(candidate_id)
            except GenomeError as error:
                raise ExecutionError(f"{island_id} contains malformed candidate identity") from error
            if lane != island.lane or candidate_id in seen:
                raise ExecutionError(f"{island_id} contains cross-lane or duplicate candidate")
            seen.add(candidate_id)


@dataclass(frozen=True)
class ExecutionState:
    payload: Mapping[str, Any]

    @classmethod
    def initial(
        cls,
        manifest: ExecutionManifest,
        contract: SearchContract,
        population_ids: Mapping[str, list[str]],
    ) -> "ExecutionState":
        capacity = int(contract.scale["residents_per_island"]) if manifest.formal else int(
            manifest.limits["residents_per_island"]
        )
        _validate_populations(population_ids, contract=contract, capacity=capacity)
        count = sum(len(values) for values in population_ids.values())
        payload = {
            "schema_version": 1,
            "kind": "maximum_search_execution_checkpoint",
            "run_id": manifest.payload["run_id"],
            "execution_manifest_sha256": manifest.sha256,
            "status": "prepared",
            "last_completed_generation": -1,
            "next_generation": 0,
            "raw_candidates_created": count,
            "formal_t0_candidate_games_completed": 0,
            "formal_t1_candidate_games_completed": 0,
            "development_games_completed": 0,
            "population_ids": {key: list(value) for key, value in sorted(population_ids.items())},
        }
        return cls(_signed(payload, "execution_checkpoint_sha256"))

    def validate(self, manifest: ExecutionManifest, contract: SearchContract) -> None:
        expected = {
            "schema_version", "kind", "run_id", "execution_manifest_sha256", "status",
            "last_completed_generation", "next_generation", "raw_candidates_created",
            "formal_t0_candidate_games_completed", "formal_t1_candidate_games_completed",
            "development_games_completed", "population_ids", "execution_checkpoint_sha256",
        }
        if set(self.payload) != expected or not verify_signature(self.payload, "execution_checkpoint_sha256"):
            raise ExecutionError("execution checkpoint schema or signature mismatch")
        if self.payload.get("schema_version") != 1 or self.payload.get("kind") != "maximum_search_execution_checkpoint":
            raise ExecutionError("unsupported execution checkpoint")
        if self.payload.get("run_id") != manifest.payload["run_id"] or self.payload.get("execution_manifest_sha256") != manifest.sha256:
            raise ExecutionError("execution checkpoint provenance mismatch")
        last = self.payload.get("last_completed_generation")
        next_generation = self.payload.get("next_generation")
        maximum = contract.generations if manifest.formal else int(manifest.limits["generations"])
        if (not isinstance(last, int) or isinstance(last, bool) or not -1 <= last < maximum
                or not isinstance(next_generation, int) or isinstance(next_generation, bool)
                or next_generation != last + 1 or not 0 <= next_generation <= maximum):
            raise ExecutionError("execution checkpoint generation cursor is malformed")
        status = self.payload.get("status")
        if status not in {"prepared", "running", "completed"}:
            raise ExecutionError("execution checkpoint status is malformed")
        if (status == "completed") != (next_generation == maximum):
            raise ExecutionError("execution completion status differs from generation cursor")
        for field in (
            "raw_candidates_created", "formal_t0_candidate_games_completed",
            "formal_t1_candidate_games_completed", "development_games_completed",
        ):
            value = self.payload.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ExecutionError(f"execution checkpoint {field} is malformed")
        if manifest.formal:
            if self.payload["development_games_completed"] != 0:
                raise ExecutionError("formal checkpoint contains development games")
            if self.payload["formal_t0_candidate_games_completed"] > int(contract.payload["tiers"]["t0"]["candidate_games"]):
                raise ExecutionError("formal T0 counter exceeds contract")
            if self.payload["formal_t1_candidate_games_completed"] > int(contract.payload["tiers"]["t1"]["candidate_games"]):
                raise ExecutionError("formal T1 counter exceeds contract")
        elif (self.payload["formal_t0_candidate_games_completed"] != 0
              or self.payload["formal_t1_candidate_games_completed"] != 0):
            raise ExecutionError("development checkpoint contains formal game claims")
        capacity = int(contract.scale["residents_per_island"]) if manifest.formal else int(
            manifest.limits["residents_per_island"]
        )
        _validate_populations(self.payload["population_ids"], contract=contract, capacity=capacity)

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        manifest: ExecutionManifest,
        contract: SearchContract,
    ) -> "ExecutionState":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ExecutionError("execution checkpoint root must be an object")
        state = cls(payload)
        state.validate(manifest, contract)
        return state

    def advanced(
        self,
        *,
        manifest: ExecutionManifest,
        contract: SearchContract,
        completed_generation: int,
        population_ids: Mapping[str, list[str]],
        raw_candidates_created: int,
        t0_games_completed: int,
        t1_games_completed: int,
        development_games_completed: int,
    ) -> "ExecutionState":
        maximum = contract.generations if manifest.formal else int(manifest.limits["generations"])
        if completed_generation != self.payload["next_generation"]:
            raise ExecutionError("execution checkpoint cannot skip or replay an advanced generation")
        next_generation = completed_generation + 1
        payload = {
            "schema_version": 1,
            "kind": "maximum_search_execution_checkpoint",
            "run_id": manifest.payload["run_id"],
            "execution_manifest_sha256": manifest.sha256,
            "status": "completed" if next_generation == maximum else "running",
            "last_completed_generation": completed_generation,
            "next_generation": next_generation,
            "raw_candidates_created": raw_candidates_created,
            "formal_t0_candidate_games_completed": t0_games_completed if manifest.formal else 0,
            "formal_t1_candidate_games_completed": t1_games_completed if manifest.formal else 0,
            "development_games_completed": 0 if manifest.formal else development_games_completed,
            "population_ids": {key: list(value) for key, value in sorted(population_ids.items())},
        }
        result = ExecutionState(_signed(payload, "execution_checkpoint_sha256"))
        result.validate(manifest, contract)
        return result


def write_execution_state(path: Path, state: ExecutionState) -> None:
    atomic_json(path, state.payload)
