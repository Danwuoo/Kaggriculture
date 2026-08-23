"""Streaming generation proposal with SQLite deduplication and bounded refill."""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .contract import SearchContract, canonical_json
from .evolution import IslandSpec, MutationEngine, island_layout
from .genome import FullTapeGenome, RootRegistry


class CoordinatorError(RuntimeError):
    pass


@dataclass(frozen=True)
class GenerationBudget:
    generation: int
    births: int
    births_by_island: tuple[int, ...]
    t0_games: int
    t1_promotions: int
    t1_games: int

    @classmethod
    def from_contract(cls, contract: SearchContract, generation: int) -> "GenerationBudget":
        births = contract.birth_quota(generation)
        by_island = contract.island_birth_quotas(generation)
        promotions = contract.t1_promotion_quota(generation)
        result = cls(
            generation=generation,
            births=births,
            births_by_island=by_island,
            t0_games=births * int(contract.payload["tiers"]["t0"]["games_per_candidate"]),
            t1_promotions=promotions,
            t1_games=promotions * int(contract.payload["tiers"]["t1"]["additional_games_per_candidate"]),
        )
        if sum(by_island) != births:
            raise CoordinatorError("generation island budgets do not close")
        return result


class CandidateIndex:
    """Exact semantic-candidate index; never approximate uniqueness with Bloom filters."""

    def __init__(self, path: Path, *, manifest_sha256: str):
        if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64:
            raise CoordinatorError("candidate index requires manifest provenance")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        columns = self.connection.execute("PRAGMA table_info(candidates)").fetchall()
        if columns and {row[1] for row in columns} != {"candidate_id", "semantic_sha256", "semantic_json", "generation", "island_id"}:
            self.connection.close()
            raise CoordinatorError("candidate index schema differs from the exact semantic index")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS candidates (candidate_id TEXT PRIMARY KEY, semantic_sha256 TEXT NOT NULL, semantic_json TEXT NOT NULL, generation INTEGER NOT NULL, island_id TEXT NOT NULL)"
        )
        existing = self.connection.execute("SELECT value FROM metadata WHERE key='manifest_sha256'").fetchone()
        if existing is None:
            self.connection.execute("INSERT INTO metadata(key,value) VALUES('manifest_sha256',?)", (manifest_sha256,))
        elif existing[0] != manifest_sha256:
            self.connection.close()
            raise CoordinatorError("candidate index manifest provenance mismatch")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CandidateIndex":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def add(self, genome: FullTapeGenome, generation: int, island_id: str, *, expected_lane: str) -> bool:
        if genome.lane != expected_lane:
            raise CoordinatorError("candidate genome lane differs from island ownership")
        candidate_id = genome.candidate_id
        semantic_sha256 = genome.semantic_sha256
        semantic_json = genome.semantic_json
        existing = self.connection.execute(
            "SELECT semantic_sha256,semantic_json FROM candidates WHERE candidate_id=?", (candidate_id,),
        ).fetchone()
        if existing is not None:
            if existing != (semantic_sha256, semantic_json):
                raise CoordinatorError("candidate ID collision with different canonical semantics")
            return False
        self.connection.execute(
            "INSERT INTO candidates(candidate_id,semantic_sha256,semantic_json,generation,island_id) VALUES(?,?,?,?,?)",
            (candidate_id, semantic_sha256, semantic_json, generation, island_id),
        )
        return True

    def commit(self) -> None:
        self.connection.commit()

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0])

    def generation_count(self, generation: int) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM candidates WHERE generation=?", (generation,)).fetchone()[0])

    def generations(self) -> set[int]:
        return {int(row[0]) for row in self.connection.execute("SELECT DISTINCT generation FROM candidates")}

    def genome(self, candidate_id: str) -> FullTapeGenome:
        row = self.connection.execute(
            "SELECT semantic_json FROM candidates WHERE candidate_id=?", (candidate_id,),
        ).fetchone()
        if row is None:
            raise CoordinatorError(f"candidate index lacks genome {candidate_id}")
        payload = json.loads(str(row[0]))
        if not isinstance(payload, dict):
            raise CoordinatorError("candidate semantic payload is malformed")
        payload["candidate_id"] = candidate_id
        try:
            return FullTapeGenome.from_dict(payload)
        except Exception as error:
            raise CoordinatorError("candidate index semantic payload failed canonical reconstruction") from error

    def catalog(self, candidate_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        requested = list(candidate_ids)
        if len(requested) != len(set(requested)):
            raise CoordinatorError("candidate catalog request contains duplicates")
        result: dict[str, dict[str, Any]] = {}
        for start in range(0, len(requested), 800):
            chunk = requested[start:start + 800]
            placeholders = ",".join("?" for _ in chunk)
            rows = self.connection.execute(
                f"SELECT candidate_id,semantic_json FROM candidates WHERE candidate_id IN ({placeholders})",
                chunk,
            ).fetchall()
            for candidate_id, semantic_json in rows:
                payload = json.loads(str(semantic_json))
                if not isinstance(payload, dict):
                    raise CoordinatorError("candidate semantic payload is malformed")
                payload["candidate_id"] = candidate_id
                genome = FullTapeGenome.from_dict(payload)
                result[candidate_id] = genome.to_dict()
        if set(result) != set(requested):
            raise CoordinatorError("candidate index lacks one or more requested genomes")
        return result

    def rollback(self) -> None:
        self.connection.rollback()

    def validate_generation(
        self, generation: int, births: Sequence["CandidateBirth"], *,
        island_lanes: Mapping[str, str], allow_missing: bool = False,
    ) -> bool:
        for birth in births:
            if island_lanes.get(birth.island_id) != birth.genome.lane:
                raise CoordinatorError("birth shard genome lane differs from island ownership")
        rows = self.connection.execute(
            "SELECT candidate_id,semantic_sha256,semantic_json,island_id FROM candidates WHERE generation=? ORDER BY candidate_id",
            (generation,),
        ).fetchall()
        expected = sorted(
            (birth.genome.candidate_id, birth.genome.semantic_sha256, birth.genome.semantic_json, birth.island_id)
            for birth in births
        )
        if not rows and allow_missing:
            return False
        if rows != expected:
            raise CoordinatorError("candidate index generation differs from the birth shard")
        return True

    def reconcile_generation(
        self, generation: int, births: Sequence["CandidateBirth"], *, island_lanes: Mapping[str, str],
    ) -> None:
        if self.validate_generation(generation, births, island_lanes=island_lanes, allow_missing=True):
            return
        for birth in births:
            expected_lane = island_lanes.get(birth.island_id)
            if expected_lane is None:
                raise CoordinatorError("birth shard contains an unknown island")
            if not self.add(birth.genome, generation, birth.island_id, expected_lane=expected_lane):
                raise CoordinatorError("birth shard collides with a candidate from another generation")
        self.commit()
        self.validate_generation(generation, births, island_lanes=island_lanes)

    def validate_initial(
        self, catalog: Mapping[str, Mapping[str, Any]], populations: Mapping[str, Sequence[str]], *,
        island_lanes: Mapping[str, str],
    ) -> None:
        island_by_candidate: dict[str, str] = {}
        for island_id, candidates in populations.items():
            for candidate_id in candidates:
                if candidate_id in island_by_candidate:
                    raise CoordinatorError("initial resident candidate appears in multiple islands")
                island_by_candidate[candidate_id] = island_id
        if set(catalog) != set(island_by_candidate):
            raise CoordinatorError("initial catalog and population IDs differ")
        expected = []
        for candidate_id in sorted(catalog):
            genome = FullTapeGenome.from_dict(catalog[candidate_id])
            if genome.candidate_id != candidate_id:
                raise CoordinatorError("initial catalog key differs from canonical candidate identity")
            if island_lanes.get(island_by_candidate[candidate_id]) != genome.lane:
                raise CoordinatorError("initial candidate genome lane differs from island ownership")
            expected.append((candidate_id, genome.semantic_sha256, genome.semantic_json, island_by_candidate[candidate_id]))
        actual = self.connection.execute(
            "SELECT candidate_id,semantic_sha256,semantic_json,island_id FROM candidates WHERE generation=0 ORDER BY candidate_id"
        ).fetchall()
        if actual != expected:
            raise CoordinatorError("candidate index generation zero differs from the initial population")


@dataclass(frozen=True)
class CandidateBirth:
    generation: int
    island_id: str
    ordinal: int
    parent_id: str
    mate_id: str | None
    genome: FullTapeGenome
    mutation: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "island_id": self.island_id,
            "ordinal": self.ordinal,
            "parent_id": self.parent_id,
            "mate_id": self.mate_id,
            "candidate": self.genome.to_dict(),
            "mutation": dict(self.mutation),
        }


def seed_index(
    index: CandidateIndex, catalog: Mapping[str, Mapping[str, Any]], populations: Mapping[str, Sequence[str]], *,
    island_lanes: Mapping[str, str],
) -> None:
    island_by_candidate: dict[str, str] = {}
    for island_id, candidates in populations.items():
        for candidate_id in candidates:
            if candidate_id in island_by_candidate:
                raise CoordinatorError("initial resident candidate appears in multiple islands")
            island_by_candidate[candidate_id] = island_id
    if set(catalog) != set(island_by_candidate):
        raise CoordinatorError("initial catalog and population IDs differ")
    for candidate_id in sorted(catalog):
        genome = FullTapeGenome.from_dict(catalog[candidate_id])
        if genome.candidate_id != candidate_id:
            raise CoordinatorError("initial catalog key differs from canonical candidate identity")
        island_id = island_by_candidate[candidate_id]
        expected_lane = island_lanes.get(island_id)
        if expected_lane is None:
            raise CoordinatorError("initial population contains an unknown island")
        if not index.add(genome, 0, island_id, expected_lane=expected_lane):
            raise CoordinatorError("initial candidate index contains duplicates")
    index.commit()
    index.validate_initial(catalog, populations, island_lanes=island_lanes)


def propose_generation(
    *,
    contract: SearchContract,
    registry: RootRegistry,
    proposal_seed: int,
    generation: int,
    populations: Mapping[str, Sequence[str]],
    catalog: Mapping[str, Mapping[str, Any]],
    index: CandidateIndex,
    max_attempts_per_birth: int = 128,
    development_limit_per_island: int | None = None,
) -> tuple[list[CandidateBirth], dict[str, Any]]:
    if generation <= 0:
        raise CoordinatorError("offspring generation must be >= 1")
    layout = island_layout(contract)
    budget = GenerationBudget.from_contract(contract, generation)
    engine = MutationEngine(registry, proposal_seed=proposal_seed)
    births: list[CandidateBirth] = []
    rejected_duplicates = 0
    saturated: list[dict[str, Any]] = []
    for island in layout:
        parents = populations.get(island.island_id)
        if not isinstance(parents, Sequence) or not parents:
            raise CoordinatorError(f"missing resident population for {island.island_id}")
        target = budget.births_by_island[island.index]
        if development_limit_per_island is not None:
            target = min(target, development_limit_per_island)
        produced = 0
        ordinal = 0
        while produced < target:
            parent_id = parents[ordinal % len(parents)]
            mate_id = parents[(ordinal * 17 + 1) % len(parents)] if len(parents) > 1 else None
            parent = FullTapeGenome.from_dict(catalog[parent_id])
            mate = FullTapeGenome.from_dict(catalog[mate_id]) if mate_id is not None else None
            accepted = None
            metadata = None
            for attempt in range(max_attempts_per_birth):
                child, found = engine.child(
                    parent, island, generation=generation,
                    ordinal=ordinal * max_attempts_per_birth + attempt, mate=mate,
                )
                if index.add(child, generation, island.island_id, expected_lane=island.lane):
                    accepted, metadata = child, found
                    break
                rejected_duplicates += 1
            if accepted is None or metadata is None:
                saturated.append({
                    "island_id": island.island_id,
                    "target": target,
                    "produced": produced,
                    "ordinal": ordinal,
                    "max_attempts_per_birth": max_attempts_per_birth,
                })
                break
            births.append(CandidateBirth(
                generation, island.island_id, ordinal, parent_id, mate_id,
                accepted, metadata,
            ))
            produced += 1
            ordinal += 1
    result = {
        "generation": generation,
        "contract_birth_target": budget.births,
        "effective_birth_target": sum(
            min(value, development_limit_per_island) if development_limit_per_island is not None else value
            for value in budget.births_by_island
        ),
        "births": len(births),
        "rejected_duplicate_proposals": rejected_duplicates,
        "saturated_islands": saturated,
        "candidate_index_count": index.count(),
        "development_limited": development_limit_per_island is not None,
    }
    if development_limit_per_island is None and (saturated or len(births) != budget.births):
        raise CoordinatorError(f"full generation saturated before exact quota: {result}")
    return births, result


def write_birth_shard(path: Path, births: Iterable[CandidateBirth]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    count = 0
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with gzip.open(temporary, "wt", encoding="utf-8", newline="\n") as stream:
            for birth in births:
                line = canonical_json(birth.to_dict()) + "\n"
                stream.write(line)
                hasher.update(line.encode("utf-8"))
                count += 1
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"path": str(path), "rows": count, "canonical_uncompressed_sha256": hasher.hexdigest(), "bytes": path.stat().st_size}


def read_birth_shard(path: Path) -> Iterator[CandidateBirth]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            yield CandidateBirth(
                generation=int(row["generation"]),
                island_id=str(row["island_id"]),
                ordinal=int(row["ordinal"]),
                parent_id=str(row["parent_id"]),
                mate_id=row["mate_id"],
                genome=FullTapeGenome.from_dict(row["candidate"]),
                mutation=row["mutation"],
            )
