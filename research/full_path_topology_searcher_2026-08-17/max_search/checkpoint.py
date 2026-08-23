"""Atomic, hash-bound manifest and checkpoint state for long-running search."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .contract import SearchContract, canonical_json
from .evolution import island_layout
from .genome import GenomeError, candidate_lane


class CheckpointError(RuntimeError):
    pass


def _signed(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    if field in payload:
        raise CheckpointError(f"payload already contains signature field {field}")
    result = dict(payload)
    result[field] = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return result


def verify_signature(payload: Mapping[str, Any], field: str) -> bool:
    signature = payload.get(field)
    unsigned = {key: value for key, value in payload.items() if key != field}
    return isinstance(signature, str) and signature == hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class RunManifest:
    payload: Mapping[str, Any]
    sha256: str

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        contract: SearchContract,
        source_snapshot: Mapping[str, Any],
        root_manifest: Mapping[str, Any],
        proposal_seed: int,
        seed_registry: Mapping[str, Any] | None = None,
        context_registry: Mapping[str, Any] | None = None,
        physical_workers: int | None = None,
        formal_execution_authorized: bool = False,
    ) -> "RunManifest":
        if not isinstance(run_id, str) or not run_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in run_id):
            raise CheckpointError("run_id must be a nonempty filesystem-safe token")
        if not isinstance(proposal_seed, int) or isinstance(proposal_seed, bool) or proposal_seed < 0:
            raise CheckpointError("proposal_seed must be a non-negative integer")
        if formal_execution_authorized:
            raise CheckpointError("schema-v2 development contract cannot authorize formal execution")
        if seed_registry is not None or context_registry is not None or physical_workers is not None:
            raise CheckpointError("development manifest cannot preselect formal execution inputs")
        payload = {
            "schema_version": 1,
            "kind": "maximum_full_tape_search_run_manifest",
            "run_id": run_id,
            "contract_sha256": contract.sha256,
            "source_snapshot": dict(source_snapshot),
            "root_manifest": dict(root_manifest),
            "proposal_seed": proposal_seed,
            "seed_registry": seed_registry,
            "context_registry": context_registry,
            "physical_workers": physical_workers,
            "formal_execution_authorized": bool(formal_execution_authorized),
            "automatic_broad_launch": False,
            "automatic_promotion": False,
            "automatic_submission": False,
        }
        signed = _signed(payload, "manifest_sha256")
        return cls(signed, signed["manifest_sha256"])

    @classmethod
    def load(cls, path: Path, *, expected_contract_sha256: str | None = None) -> "RunManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping) or not verify_signature(payload, "manifest_sha256"):
            raise CheckpointError("manifest signature mismatch")
        expected_fields = {
            "schema_version", "kind", "run_id", "contract_sha256", "source_snapshot", "root_manifest",
            "proposal_seed", "seed_registry", "context_registry", "physical_workers",
            "formal_execution_authorized", "automatic_broad_launch", "automatic_promotion",
            "automatic_submission", "manifest_sha256",
        }
        if set(payload) != expected_fields or payload.get("schema_version") != 1 or payload.get("kind") != "maximum_full_tape_search_run_manifest":
            raise CheckpointError("manifest schema is not closed")
        if expected_contract_sha256 is not None and payload.get("contract_sha256") != expected_contract_sha256:
            raise CheckpointError("manifest contract hash mismatch")
        if payload.get("formal_execution_authorized") is not False:
            raise CheckpointError("development manifest cannot authorize formal execution")
        if any(payload.get(key) is not None for key in ("seed_registry", "context_registry", "physical_workers")):
            raise CheckpointError("development manifest contains formal execution inputs")
        if any(payload.get(key) is not False for key in ("automatic_broad_launch", "automatic_promotion", "automatic_submission")):
            raise CheckpointError("development manifest contains automatic later-tier action")
        return cls(payload, str(payload["manifest_sha256"]))


def _validate_population_ids(contract: SearchContract, populations: Any) -> None:
    if not isinstance(populations, Mapping):
        raise CheckpointError("checkpoint population IDs must be an object")
    layout = island_layout(contract)
    expected = {row.island_id: row for row in layout}
    if set(populations) != set(expected):
        raise CheckpointError("checkpoint island IDs differ from the fixed layout")
    all_ids: list[str] = []
    for island_id, island in expected.items():
        values = populations[island_id]
        if not isinstance(values, list) or len(values) != island.capacity:
            raise CheckpointError(f"{island_id} resident capacity mismatch")
        for candidate_id in values:
            try:
                lane = candidate_lane(candidate_id)
            except GenomeError as error:
                raise CheckpointError(f"{island_id} contains malformed candidate ID") from error
            if lane != island.lane:
                raise CheckpointError(f"{island_id} contains cross-lane candidate")
        all_ids.extend(values)
    if len(set(all_ids)) != len(all_ids):
        raise CheckpointError("checkpoint resident candidates must be globally unique")


@dataclass(frozen=True)
class RunState:
    payload: Mapping[str, Any]

    @classmethod
    def initial(cls, manifest: RunManifest, contract: SearchContract, population_ids: Mapping[str, list[str]]) -> "RunState":
        if manifest.payload["contract_sha256"] != contract.sha256:
            raise CheckpointError("manifest and contract differ")
        _validate_population_ids(contract, population_ids)
        payload = {
            "schema_version": 1,
            "kind": "maximum_full_tape_search_checkpoint",
            "run_id": manifest.payload["run_id"],
            "manifest_sha256": manifest.sha256,
            "contract_sha256": contract.sha256,
            "status": "development_initialized" if not manifest.payload["formal_execution_authorized"] else "ready",
            "generation": 0,
            "raw_candidates_created": contract.birth_quota(0),
            "t0_candidate_games_completed": 0,
            "t1_candidate_games_completed": 0,
            "population_ids": {key: list(values) for key, values in sorted(population_ids.items())},
        }
        return cls(_signed(payload, "checkpoint_sha256"))

    def validate(self, manifest: RunManifest, contract: SearchContract) -> None:
        if not verify_signature(self.payload, "checkpoint_sha256"):
            raise CheckpointError("checkpoint signature mismatch")
        expected_fields = {
            "schema_version", "kind", "run_id", "manifest_sha256", "contract_sha256", "status",
            "generation", "raw_candidates_created", "t0_candidate_games_completed",
            "t1_candidate_games_completed", "population_ids", "checkpoint_sha256",
        }
        if set(self.payload) != expected_fields or self.payload.get("schema_version") != 1 or self.payload.get("kind") != "maximum_full_tape_search_checkpoint":
            raise CheckpointError("checkpoint schema is not closed")
        if self.payload.get("run_id") != manifest.payload.get("run_id"):
            raise CheckpointError("checkpoint run ID differs from manifest")
        if self.payload.get("manifest_sha256") != manifest.sha256 or self.payload.get("contract_sha256") != contract.sha256:
            raise CheckpointError("checkpoint provenance mismatch")
        generation = self.payload.get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool) or not 0 <= generation < contract.generations:
            raise CheckpointError("checkpoint generation outside contract")
        raw = self.payload.get("raw_candidates_created")
        if not isinstance(raw, int) or isinstance(raw, bool) or not contract.population <= raw <= contract.raw_candidates:
            raise CheckpointError("checkpoint raw-candidate count outside contract")
        t0 = self.payload.get("t0_candidate_games_completed")
        t1 = self.payload.get("t1_candidate_games_completed")
        if not isinstance(t0, int) or isinstance(t0, bool) or not 0 <= t0 <= int(contract.payload["tiers"]["t0"]["candidate_games"]):
            raise CheckpointError("checkpoint T0 count outside contract")
        if not isinstance(t1, int) or isinstance(t1, bool) or not 0 <= t1 <= int(contract.payload["tiers"]["t1"]["candidate_games"]):
            raise CheckpointError("checkpoint T1 count outside contract")
        if manifest.payload["formal_execution_authorized"] is False:
            if generation != 0 or raw != contract.population or t0 != 0 or t1 != 0 or self.payload.get("status") != "development_initialized":
                raise CheckpointError("development checkpoint cannot claim search progress")
        _validate_population_ids(contract, self.payload.get("population_ids"))

    @classmethod
    def load(cls, path: Path, manifest: RunManifest, contract: SearchContract) -> "RunState":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise CheckpointError("checkpoint root must be an object")
        result = cls(payload)
        result.validate(manifest, contract)
        return result


def read_status(root: Path) -> dict[str, Any]:
    """Read status without creating a missing run root or any files."""
    manifest_path = root / "manifest.json"
    checkpoint_path = root / "checkpoint.json"
    if not root.exists():
        return {"exists": False, "run_root": str(root)}
    if not manifest_path.is_file() or not checkpoint_path.is_file():
        return {"exists": True, "complete_metadata": False, "run_root": str(root)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    return {
        "exists": True,
        "complete_metadata": True,
        "run_root": str(root),
        "run_id": manifest.get("run_id"),
        "formal_execution_authorized": manifest.get("formal_execution_authorized"),
        "status": checkpoint.get("status"),
        "generation": checkpoint.get("generation"),
        "raw_candidates_created": checkpoint.get("raw_candidates_created"),
        "t0_candidate_games_completed": checkpoint.get("t0_candidate_games_completed"),
        "t1_candidate_games_completed": checkpoint.get("t1_candidate_games_completed"),
        "manifest_signature_valid": verify_signature(manifest, "manifest_sha256"),
        "checkpoint_signature_valid": verify_signature(checkpoint, "checkpoint_sha256"),
    }
