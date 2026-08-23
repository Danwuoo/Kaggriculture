"""Crash-resumable, physically parallel, multi-generation maximum-search runner."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict
import gzip
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .checkpoint import RunManifest, RunState, atomic_json, verify_signature
from .contexts import ContextRegistry, verify_opponent_artifacts
from .contract import LANES, SearchContract, canonical_json
from .coordinator import (
    CandidateBirth, CandidateIndex, propose_generation, read_birth_shard,
    seed_index, write_birth_shard,
)
from .evolution import FitnessVector, island_layout, select_survivors_scalable
from .execution import ExecutionError, ExecutionManifest, ExecutionState, file_identity, write_execution_state
from .genome import FullTapeGenome, RootRegistry
from .preflight import source_snapshot
from .scoring import ScoringIdentity, paired_row, score_candidate


class RunnerError(RuntimeError):
    pass


_WORKER_ROOT: Path | None = None
_WORKER_REGISTRY: RootRegistry | None = None


def _worker_initialize(workspace: str, expected_root_manifest_sha256: str) -> None:
    global _WORKER_ROOT, _WORKER_REGISTRY
    _WORKER_ROOT = Path(workspace)
    _WORKER_REGISTRY = RootRegistry.load_workspace(_WORKER_ROOT, include_public=True)
    if _WORKER_REGISTRY.manifest()["manifest_sha256"] != expected_root_manifest_sha256:
        raise RunnerError("worker root registry differs from the execution manifest")


def _technical_pass(summary: Mapping[str, Any]) -> bool:
    issue_values = summary.get("action_issues", {})
    opponent_issues = summary.get("opponent_action_issues", {})
    opponent_structural_issues = (
        opponent_issues.get("malformed", 1),
        opponent_issues.get("hand_alignment", 1),
        opponent_issues.get("market_overflow", 1),
    ) if isinstance(opponent_issues, Mapping) else (1,)
    return bool(
        summary.get("statuses") == ["DONE", "DONE"]
        and summary.get("calls") == 719
        and summary.get("opponent_calls") == 719
        and summary.get("exception") is None
        and summary.get("opponent_exception") is None
        and summary.get("timeout_calls") == 0
        and summary.get("opponent_timeout_calls") == 0
        and summary.get("overage_exhausted") is False
        and summary.get("opponent_overage_exhausted") is False
        and isinstance(issue_values, Mapping)
        and isinstance(opponent_issues, Mapping)
        and all(value == 0 for value in issue_values.values())
        # Opponent seed overcommit is its own engine-cancelled economic action,
        # not a candidate validity failure. Structural opponent faults remain
        # fatal because they make the paired context unreliable.
        and all(value == 0 for value in opponent_structural_issues)
        and isinstance(summary.get("max_market_orders"), int)
        and summary.get("max_market_orders") <= 10
        and isinstance(summary.get("opponent_max_market_orders"), int)
        and summary.get("opponent_max_market_orders") <= 10
    )


def _economic_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rewards": summary.get("rewards"),
        "money": summary.get("money"),
        "diagnostics": summary.get("diagnostics"),
        "terminal_inventory": summary.get("terminal_inventory"),
    }


def _compact_official_result(
    run: Any,
    *,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    summary = run.summary
    seat = int(context["seat"])
    rewards = summary.get("rewards")
    money = summary.get("money")
    if (not isinstance(rewards, list) or len(rewards) != 2
            or not isinstance(money, list) or len(money) != 2):
        margin, own_bank = 0.0, 0.0
        technical = False
    else:
        margin = float(rewards[seat]) - float(rewards[1 - seat])
        own_bank = float(money[seat])
        technical = _technical_pass(summary)
    behavior = _economic_view(summary)
    failure = None if technical else {
        key: summary.get(key) for key in (
            "statuses", "calls", "opponent_calls", "exception", "opponent_exception",
            "timeout_calls", "opponent_timeout_calls", "overage_exhausted",
            "opponent_overage_exhausted", "action_issues", "opponent_action_issues",
            "max_market_orders", "opponent_max_market_orders",
        )
    }
    return {
        "context_id": context["context_id"],
        "opponent_family": context["opponent_family"],
        "seed": int(context["seed"]),
        "seat": seat,
        "margin": margin,
        "own_bank": own_bank,
        "technical_pass": technical,
        "behavior_sha256": hashlib.sha256(canonical_json(behavior).encode("utf-8")).hexdigest(),
        "action_digest": summary.get("action_digest"),
        "failure": failure,
        "diagnostics": summary.get("diagnostics"),
        "terminal_inventory": summary.get("terminal_inventory"),
        "worker_pid": os.getpid(),
    }


def _mock_result(
    *,
    lane: str,
    candidate_id: str | None,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    control_token = hashlib.sha256(canonical_json([
        "control", lane, context["context_id"],
    ]).encode("utf-8")).digest()
    control_margin = float(int.from_bytes(control_token[:2], "big") % 401 - 200)
    control_bank = float(1000 + int.from_bytes(control_token[2:4], "big") % 2000)
    if candidate_id is None:
        margin, bank = control_margin, control_bank
        behavior_key = [lane, context["context_id"], "control", margin, bank]
        action_digest = hashlib.sha256(canonical_json(behavior_key).encode("utf-8")).hexdigest()
    else:
        token = hashlib.sha256(canonical_json([
            candidate_id, lane, context["context_id"],
        ]).encode("utf-8")).digest()
        delta = float(1 + int.from_bytes(token[:2], "big") % 41)
        if token[2] % 5 == 0:
            delta = -delta
        margin = control_margin + delta
        bank = control_bank + float(int.from_bytes(token[3:5], "big") % 31 - 10)
        behavior_key = [lane, context["context_id"], candidate_id, margin, bank]
        action_digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()
    return {
        "context_id": context["context_id"],
        "opponent_family": context["opponent_family"],
        "seed": int(context["seed"]),
        "seat": int(context["seat"]),
        "margin": margin,
        "own_bank": bank,
        "technical_pass": True,
        "behavior_sha256": hashlib.sha256(canonical_json(behavior_key).encode("utf-8")).hexdigest(),
        "action_digest": action_digest,
        "failure": None,
        "diagnostics": {
            "animal_escapes": 0, "crop_deaths": 0, "fresh_crop_deaths": 0,
            "shed_overflow_events": 0, "shed_overflow_units": 0,
        },
        "terminal_inventory": {"marked_value": 0.0, "units": 0},
        "worker_pid": os.getpid(),
    }


def _worker_batch(task: Mapping[str, Any]) -> dict[str, Any]:
    if _WORKER_ROOT is None or _WORKER_REGISTRY is None:
        raise RunnerError("parallel worker was not initialized")
    kind = task["kind"]
    backend = task["backend"]
    lane = task["lane"]
    contexts = task["contexts"]
    genome: FullTapeGenome | None = None
    candidate_id: str | None = None
    if kind == "candidate":
        genome = FullTapeGenome.from_dict(task["genome"])
        candidate_id = genome.candidate_id
        if genome.lane != lane:
            raise RunnerError("worker candidate lane differs from task lane")
    elif kind != "control":
        raise RunnerError("unknown worker task kind")

    results: list[dict[str, Any]] = []
    if backend == "deterministic_mock":
        for context in contexts:
            results.append(_mock_result(lane=lane, candidate_id=candidate_id, context=context))
    elif backend == "official":
        from .evaluation import run_game, make_policy_factory

        candidate_path = _WORKER_ROOT / "research" / "main_approach" / lane / "main.py"
        policy_factory = None
        if genome is not None:
            policy_factory = make_policy_factory(genome, _WORKER_REGISTRY.get(genome.root_id))
        for context in contexts:
            try:
                run = run_game(
                    lane, candidate_path, str(context["opponent_family"]),
                    int(context["seed"]), int(context["seat"]),
                    policy_factory=policy_factory, capture_trace=False,
                )
                results.append(_compact_official_result(run, context=context))
            except Exception as error:
                results.append({
                    "context_id": context["context_id"],
                    "opponent_family": context["opponent_family"],
                    "seed": int(context["seed"]),
                    "seat": int(context["seat"]),
                    "margin": 0.0,
                    "own_bank": 0.0,
                    "technical_pass": False,
                    "behavior_sha256": hashlib.sha256(
                        f"worker-error:{type(error).__name__}:{error}".encode("utf-8")
                    ).hexdigest(),
                    "action_digest": None,
                    "failure": {"worker_error": f"{type(error).__name__}: {error}"},
                    "diagnostics": None,
                    "terminal_inventory": None,
                    "worker_pid": os.getpid(),
                })
    else:
        raise RunnerError("unknown worker backend")
    return {
        "kind": kind,
        "lane": lane,
        "candidate_id": candidate_id,
        "generation": task.get("generation"),
        "island_id": task.get("island_id"),
        "tier": task.get("tier"),
        "results": results,
        "worker_pid": os.getpid(),
    }


class ParallelEvaluator:
    """One persistent spawn pool shared by controls and every generation phase."""

    def __init__(
        self,
        *,
        workspace: Path,
        root_manifest_sha256: str,
        workers: int,
        max_in_flight: int,
    ):
        self.workspace = workspace
        self.root_manifest_sha256 = root_manifest_sha256
        self.workers = workers
        self.max_in_flight = max_in_flight
        self.pool: ProcessPoolExecutor | None = None

    def __enter__(self) -> "ParallelEvaluator":
        context = multiprocessing.get_context("spawn")
        self.pool = ProcessPoolExecutor(
            max_workers=self.workers,
            mp_context=context,
            initializer=_worker_initialize,
            initargs=(str(self.workspace), self.root_manifest_sha256),
        )
        return self

    def __exit__(self, *_args: Any) -> None:
        if self.pool is not None:
            self.pool.shutdown(wait=True, cancel_futures=False)
            self.pool = None

    def run(self, tasks: Iterable[Mapping[str, Any]]) -> Iterator[dict[str, Any]]:
        if self.pool is None:
            raise RunnerError("parallel evaluator is not active")
        iterator = iter(tasks)
        pending: dict[Any, None] = {}
        exhausted = False
        while pending or not exhausted:
            while not exhausted and len(pending) < self.max_in_flight:
                try:
                    task = next(iterator)
                except StopIteration:
                    exhausted = True
                    break
                pending[self.pool.submit(_worker_batch, task)] = None
            if not pending:
                continue
            completed, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
            for future in completed:
                del pending[future]
                yield future.result()


def _bounded_parallel(
    tasks: Iterable[Mapping[str, Any]],
    *,
    workspace: Path,
    root_manifest_sha256: str,
    workers: int,
    max_in_flight: int,
) -> Iterator[dict[str, Any]]:
    """Compatibility wrapper used by focused worker-pool tests."""
    with ParallelEvaluator(
        workspace=workspace, root_manifest_sha256=root_manifest_sha256,
        workers=workers, max_in_flight=max_in_flight,
    ) as evaluator:
        yield from evaluator.run(tasks)


class SearchStore:
    """Exact idempotent game/fitness ledger for restart and long-run streaming."""

    def __init__(self, path: Path, *, execution_manifest_sha256: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS controls(
                lane TEXT NOT NULL, context_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL, PRIMARY KEY(lane, context_id));
            CREATE TABLE IF NOT EXISTS receipts(
                candidate_id TEXT NOT NULL, tier TEXT NOT NULL, context_id TEXT NOT NULL,
                lane TEXT NOT NULL, generation INTEGER NOT NULL, island_id TEXT NOT NULL,
                payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                PRIMARY KEY(candidate_id, tier, context_id));
            CREATE TABLE IF NOT EXISTS fitness(
                candidate_id TEXT NOT NULL, scope TEXT NOT NULL, lane TEXT NOT NULL,
                generation INTEGER NOT NULL, island_id TEXT NOT NULL,
                technical_pass INTEGER NOT NULL, effective_change INTEGER NOT NULL,
                net_wdl_transition INTEGER NOT NULL, w_to_l INTEGER NOT NULL,
                negative_tails INTEGER NOT NULL, cvar_01 REAL NOT NULL, cvar_05 REAL NOT NULL,
                worst_margin REAL NOT NULL, mean_margin REAL NOT NULL, mean_own_bank REAL NOT NULL,
                complexity INTEGER NOT NULL, novelty REAL NOT NULL,
                payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                PRIMARY KEY(candidate_id, scope));
            CREATE TABLE IF NOT EXISTS promotions(
                generation INTEGER NOT NULL, island_id TEXT NOT NULL, rank INTEGER NOT NULL,
                candidate_id TEXT NOT NULL, PRIMARY KEY(generation, island_id, rank),
                UNIQUE(generation, candidate_id));
            CREATE TABLE IF NOT EXISTS generation_summaries(
                generation INTEGER PRIMARY KEY, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipt_prunes(
                generation INTEGER PRIMARY KEY, t0_count INTEGER NOT NULL, t1_count INTEGER NOT NULL,
                adverse_count INTEGER NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS receipts_tier_index ON receipts(tier, candidate_id);
            CREATE INDEX IF NOT EXISTS fitness_scope_lane_order ON fitness(
                scope, lane, technical_pass DESC, effective_change DESC,
                net_wdl_transition DESC, w_to_l ASC, negative_tails ASC,
                cvar_01 DESC, cvar_05 DESC, worst_margin DESC, mean_margin DESC,
                mean_own_bank DESC, complexity ASC, novelty DESC, candidate_id DESC);
            """
        )
        existing = self.connection.execute(
            "SELECT value FROM metadata WHERE key='execution_manifest_sha256'"
        ).fetchone()
        if existing is None:
            self.connection.execute(
                "INSERT INTO metadata(key,value) VALUES('execution_manifest_sha256',?)",
                (execution_manifest_sha256,),
            )
        elif existing[0] != execution_manifest_sha256:
            self.connection.close()
            raise RunnerError("search store execution-manifest provenance mismatch")
        self.connection.commit()

    def __enter__(self) -> "SearchStore":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.connection.close()

    @staticmethod
    def _encoded(payload: Mapping[str, Any]) -> tuple[str, str]:
        encoded = canonical_json(payload)
        return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _idempotent_insert(self, table: str, key_where: str, key_values: tuple[Any, ...], sql: str, values: tuple[Any, ...], payload: Mapping[str, Any]) -> None:
        encoded, digest = self._encoded(payload)
        existing = self.connection.execute(
            f"SELECT payload_json,payload_sha256 FROM {table} WHERE {key_where}", key_values,
        ).fetchone()
        if existing is not None:
            if existing != (encoded, digest):
                raise RunnerError(f"{table} idempotent key contains different evidence")
            return
        self.connection.execute(sql, (*values, encoded, digest))

    def put_control(self, lane: str, payload: Mapping[str, Any]) -> None:
        context_id = str(payload["context_id"])
        self._idempotent_insert(
            "controls", "lane=? AND context_id=?", (lane, context_id),
            "INSERT INTO controls(lane,context_id,payload_json,payload_sha256) VALUES(?,?,?,?)",
            (lane, context_id), payload,
        )

    def control(self, lane: str, context_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT payload_json,payload_sha256 FROM controls WHERE lane=? AND context_id=?",
            (lane, context_id),
        ).fetchone()
        if row is None or hashlib.sha256(row[0].encode("utf-8")).hexdigest() != row[1]:
            raise RunnerError(f"missing or corrupt control receipt {lane}/{context_id}")
        return json.loads(row[0])

    def missing_control_contexts(self, lane: str, contexts: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        existing = {row[0] for row in self.connection.execute("SELECT context_id FROM controls WHERE lane=?", (lane,))}
        return [row for row in contexts if row["context_id"] not in existing]

    def put_receipt(self, result: Mapping[str, Any]) -> None:
        candidate_id, tier, context_id = str(result["candidate_id"]), str(result["tier"]), str(result["context_id"])
        payload = result["payload"]
        generation = int(result["generation"])
        if self.connection.execute(
            "SELECT 1 FROM receipt_prunes WHERE generation=?", (generation,),
        ).fetchone() is not None:
            raise RunnerError("cannot insert a receipt after its generation was compacted")
        self._idempotent_insert(
            "receipts", "candidate_id=? AND tier=? AND context_id=?", (candidate_id, tier, context_id),
            "INSERT INTO receipts(candidate_id,tier,context_id,lane,generation,island_id,payload_json,payload_sha256) VALUES(?,?,?,?,?,?,?,?)",
            (candidate_id, tier, context_id, result["lane"], generation, result["island_id"]), payload,
        )

    def missing_contexts(self, candidate_id: str, tier: str, contexts: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        existing = {row[0] for row in self.connection.execute(
            "SELECT context_id FROM receipts WHERE candidate_id=? AND tier=?", (candidate_id, tier),
        )}
        return [row for row in contexts if row["context_id"] not in existing]

    def candidate_receipts(self, candidate_id: str, tiers: Sequence[str]) -> dict[str, dict[str, Any]]:
        placeholders = ",".join("?" for _ in tiers)
        rows = self.connection.execute(
            f"SELECT context_id,payload_json,payload_sha256 FROM receipts WHERE candidate_id=? AND tier IN ({placeholders})",
            (candidate_id, *tiers),
        ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for context_id, encoded, digest in rows:
            if hashlib.sha256(encoded.encode("utf-8")).hexdigest() != digest:
                raise RunnerError("candidate receipt hash mismatch")
            if context_id in result:
                raise RunnerError("candidate has duplicate context across requested tiers")
            result[context_id] = json.loads(encoded)
        return result

    def put_fitness(self, vector: FitnessVector, *, scope: str, generation: int, island_id: str, diagnostics: Mapping[str, Any]) -> None:
        payload = {"vector": asdict(vector), "diagnostics": dict(diagnostics)}
        encoded, digest = self._encoded(payload)
        values = (
            vector.candidate_id, scope, vector.lane, generation, island_id,
            int(vector.technical_pass), int(vector.effective_change), vector.net_wdl_transition,
            vector.w_to_l, vector.repeatable_family_seat_negative_tails, vector.cvar_01,
            vector.cvar_05, vector.worst_margin, vector.mean_margin, vector.mean_own_bank,
            vector.complexity, vector.novelty, encoded, digest,
        )
        existing = self.connection.execute(
            "SELECT payload_json,payload_sha256 FROM fitness WHERE candidate_id=? AND scope=?",
            (vector.candidate_id, scope),
        ).fetchone()
        if existing is not None:
            if existing != (encoded, digest):
                raise RunnerError("fitness idempotent key contains different evidence")
            return
        self.connection.execute(
            "INSERT INTO fitness(candidate_id,scope,lane,generation,island_id,technical_pass,effective_change,net_wdl_transition,w_to_l,negative_tails,cvar_01,cvar_05,worst_margin,mean_margin,mean_own_bank,complexity,novelty,payload_json,payload_sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            values,
        )

    def fitness(self, candidate_id: str, scope: str) -> FitnessVector:
        row = self.connection.execute(
            "SELECT payload_json,payload_sha256 FROM fitness WHERE candidate_id=? AND scope=?",
            (candidate_id, scope),
        ).fetchone()
        if row is None or hashlib.sha256(row[0].encode("utf-8")).hexdigest() != row[1]:
            raise RunnerError(f"missing or corrupt {scope} fitness for {candidate_id}")
        return FitnessVector(**json.loads(row[0])["vector"])

    def put_promotions(self, generation: int, island_id: str, candidate_ids: Sequence[str]) -> None:
        existing = [row[0] for row in self.connection.execute(
            "SELECT candidate_id FROM promotions WHERE generation=? AND island_id=? ORDER BY rank",
            (generation, island_id),
        )]
        if existing:
            if existing != list(candidate_ids):
                raise RunnerError("stored T1 promotions differ from deterministic selection")
            return
        self.connection.executemany(
            "INSERT INTO promotions(generation,island_id,rank,candidate_id) VALUES(?,?,?,?)",
            [(generation, island_id, rank, candidate_id) for rank, candidate_id in enumerate(candidate_ids)],
        )

    def promotions(self, generation: int, island_id: str) -> list[str]:
        return [row[0] for row in self.connection.execute(
            "SELECT candidate_id FROM promotions WHERE generation=? AND island_id=? ORDER BY rank",
            (generation, island_id),
        )]

    def counts(self) -> dict[str, int]:
        pruned = self.connection.execute(
            "SELECT COALESCE(SUM(t0_count),0),COALESCE(SUM(t1_count),0) FROM receipt_prunes"
        ).fetchone()
        return {
            "controls": int(self.connection.execute("SELECT COUNT(*) FROM controls").fetchone()[0]),
            "t0": int(pruned[0]) + int(self.connection.execute("SELECT COUNT(*) FROM receipts WHERE tier='t0'").fetchone()[0]),
            "t1": int(pruned[1]) + int(self.connection.execute("SELECT COUNT(*) FROM receipts WHERE tier='t1'").fetchone()[0]),
            "fitness_t0": int(self.connection.execute("SELECT COUNT(*) FROM fitness WHERE scope='t0'").fetchone()[0]),
            "fitness_combined": int(self.connection.execute("SELECT COUNT(*) FROM fitness WHERE scope='combined'").fetchone()[0]),
        }

    def live_receipt_counts(self, generation: int | None = None) -> dict[str, int]:
        where, values = ("", ()) if generation is None else (" WHERE generation=?", (generation,))
        rows = self.connection.execute(
            f"SELECT tier,COUNT(*) FROM receipts{where} GROUP BY tier", values,
        ).fetchall()
        found = {str(tier): int(count) for tier, count in rows}
        return {"t0": found.get("t0", 0), "t1": found.get("t1", 0)}

    def generation_receipts(self, generation: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT candidate_id,tier,context_id,lane,island_id,payload_json,payload_sha256
               FROM receipts WHERE generation=? ORDER BY candidate_id,tier,context_id""",
            (generation,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for candidate_id, tier, context_id, lane, island_id, encoded, digest in rows:
            if hashlib.sha256(encoded.encode("utf-8")).hexdigest() != digest:
                raise RunnerError("generation receipt hash mismatch before compaction")
            result.append({
                "candidate_id": candidate_id, "tier": tier, "context_id": context_id,
                "lane": lane, "generation": generation, "island_id": island_id,
                "payload": json.loads(encoded), "payload_sha256": digest,
            })
        return result

    def receipt_prune(self, generation: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT payload_json,payload_sha256 FROM receipt_prunes WHERE generation=?", (generation,),
        ).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row[0].encode("utf-8")).hexdigest() != row[1]:
            raise RunnerError("receipt-prune record hash mismatch")
        return json.loads(row[0])

    def apply_receipt_prune(self, generation: int, payload: Mapping[str, Any]) -> None:
        encoded, digest = self._encoded(payload)
        existing = self.connection.execute(
            "SELECT payload_json,payload_sha256 FROM receipt_prunes WHERE generation=?", (generation,),
        ).fetchone()
        if existing is not None:
            if existing != (encoded, digest):
                raise RunnerError("receipt-prune generation contains different evidence")
            if sum(self.live_receipt_counts(generation).values()) != 0:
                raise RunnerError("compacted generation unexpectedly retains raw receipts")
            return
        counts = self.live_receipt_counts(generation)
        expected = payload.get("receipt_counts")
        if not isinstance(expected, Mapping) or counts != dict(expected):
            raise RunnerError("receipt-prune counts differ from live generation receipts")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            self.connection.execute(
                "INSERT INTO receipt_prunes(generation,t0_count,t1_count,adverse_count,payload_json,payload_sha256) VALUES(?,?,?,?,?,?)",
                (generation, counts["t0"], counts["t1"], int(payload["adverse_rows"]), encoded, digest),
            )
            self.connection.execute("DELETE FROM receipts WHERE generation=?", (generation,))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def top_combined(self, lane: str, limit: int) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """SELECT payload_json,payload_sha256 FROM fitness
               WHERE scope='combined' AND lane=? AND technical_pass=1 AND effective_change=1
               ORDER BY net_wdl_transition DESC, w_to_l ASC, negative_tails ASC,
                        cvar_01 DESC, cvar_05 DESC, worst_margin DESC, mean_margin DESC,
                        mean_own_bank DESC, complexity ASC, novelty DESC, candidate_id DESC
               LIMIT ?""",
            (lane, limit),
        ).fetchall()
        result = []
        for encoded, digest in rows:
            if hashlib.sha256(encoded.encode("utf-8")).hexdigest() != digest:
                raise RunnerError("broad-fitness payload hash mismatch")
            result.append(json.loads(encoded))
        return result

    def put_generation_summary(self, generation: int, payload: Mapping[str, Any]) -> None:
        encoded, digest = self._encoded(payload)
        existing = self.connection.execute(
            "SELECT payload_json,payload_sha256 FROM generation_summaries WHERE generation=?", (generation,),
        ).fetchone()
        if existing is not None:
            if existing != (encoded, digest):
                raise RunnerError("generation summary differs from stored evidence")
            return
        self.connection.execute(
            "INSERT INTO generation_summaries(generation,payload_json,payload_sha256) VALUES(?,?,?)",
            (generation, encoded, digest),
        )

    def commit(self) -> None:
        self.connection.commit()


def _signed_artifact(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(payload)
    result[field] = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return result


_ECONOMIC_DIAGNOSTIC_COUNTS = (
    "animal_escapes", "crop_deaths", "fresh_crop_deaths",
    "shed_overflow_events", "shed_overflow_units",
)


def _worse_economic_diagnostic(candidate: Any, control: Any) -> bool:
    if not isinstance(candidate, Mapping):
        return False
    control_row = control if isinstance(control, Mapping) else {}
    for field in _ECONOMIC_DIAGNOSTIC_COUNTS:
        candidate_value, control_value = candidate.get(field, 0), control_row.get(field, 0)
        if (isinstance(candidate_value, (int, float)) and not isinstance(candidate_value, bool)
                and isinstance(control_value, (int, float)) and not isinstance(control_value, bool)
                and float(candidate_value) > float(control_value)):
            return True
    return False


def _receipt_retention_paths(run_root: Path, generation: int) -> tuple[Path, Path]:
    stem = f"execution_generation_{generation:04d}_adverse_receipts"
    return run_root / f"{stem}.jsonl.gz", run_root / f"{stem}_summary.json"


def _write_deterministic_gzip(path: Path, lines: Sequence[str]) -> tuple[int, str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    uncompressed = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as text_stream:
                    for line in lines:
                        encoded = (line + "\n").encode("utf-8")
                        uncompressed.update(encoded)
                        text_stream.write(line + "\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    raw = path.read_bytes()
    return len(raw), hashlib.sha256(raw).hexdigest(), uncompressed.hexdigest()


def _validate_receipt_retention(
    payload: Mapping[str, Any], *, run_root: Path, manifest: ExecutionManifest, generation: int,
) -> None:
    expected = {
        "schema_version", "kind", "execution_manifest_sha256", "generation",
        "policy", "receipt_counts", "adverse_rows", "deleted_raw_rows",
        "all_receipts_canonical_sha256", "adverse_artifact", "artifact_sha256",
    }
    if set(payload) != expected or not verify_signature(payload, "artifact_sha256"):
        raise RunnerError("receipt-retention schema or signature mismatch")
    if (payload.get("schema_version") != 1
            or payload.get("kind") != "maximum_search_generation_receipt_retention"
            or payload.get("execution_manifest_sha256") != manifest.sha256
            or payload.get("generation") != generation
            or payload.get("policy") != manifest.payload["retention_policy"]):
        raise RunnerError("receipt-retention provenance or policy mismatch")
    counts = payload.get("receipt_counts")
    if (not isinstance(counts, Mapping) or set(counts) != {"t0", "t1"}
            or any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counts.values())):
        raise RunnerError("receipt-retention counts are malformed")
    if payload.get("deleted_raw_rows") != int(counts["t0"]) + int(counts["t1"]):
        raise RunnerError("receipt-retention deleted count does not close")
    adverse_rows = payload.get("adverse_rows")
    if not isinstance(adverse_rows, int) or isinstance(adverse_rows, bool) or not 0 <= adverse_rows <= payload["deleted_raw_rows"]:
        raise RunnerError("receipt-retention adverse count is malformed")
    digest = payload.get("all_receipts_canonical_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise RunnerError("receipt-retention all-receipt digest is malformed")
    artifact = payload.get("adverse_artifact")
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "path", "rows", "bytes", "sha256", "canonical_uncompressed_sha256",
    }:
        raise RunnerError("receipt-retention adverse artifact identity is malformed")
    path = Path(str(artifact["path"]))
    expected_path, _ = _receipt_retention_paths(run_root, generation)
    if path != expected_path or artifact.get("rows") != adverse_rows or not path.is_file():
        raise RunnerError("receipt-retention adverse artifact path or row count differs")
    raw = path.read_bytes()
    if len(raw) != artifact.get("bytes") or hashlib.sha256(raw).hexdigest() != artifact.get("sha256"):
        raise RunnerError("receipt-retention adverse artifact bytes differ")
    uncompressed = hashlib.sha256()
    rows = 0
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if not line.endswith("\n"):
                raise RunnerError("receipt-retention adverse artifact has a partial row")
            json.loads(line)
            uncompressed.update(line.encode("utf-8"))
            rows += 1
    if rows != adverse_rows or uncompressed.hexdigest() != artifact.get("canonical_uncompressed_sha256"):
        raise RunnerError("receipt-retention adverse artifact content differs")


def _prepare_receipt_retention(
    run_root: Path,
    *,
    store: SearchStore,
    manifest: ExecutionManifest,
    generation: int,
) -> dict[str, Any]:
    adverse_path, summary_path = _receipt_retention_paths(run_root, generation)
    if summary_path.is_file():
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        _validate_receipt_retention(
            payload, run_root=run_root, manifest=manifest, generation=generation,
        )
        return dict(payload)
    if store.receipt_prune(generation) is not None:
        raise RunnerError("receipt-prune ledger exists without its signed retention summary")
    rows = store.generation_receipts(generation)
    counts = {"t0": 0, "t1": 0}
    all_receipts = hashlib.sha256()
    adverse_lines: list[str] = []
    for row in rows:
        tier = str(row["tier"])
        if tier not in counts:
            raise RunnerError("receipt-retention found an unknown tier")
        counts[tier] += 1
        canonical = canonical_json(row)
        all_receipts.update((canonical + "\n").encode("utf-8"))
        candidate = row["payload"]
        control = store.control(str(row["lane"]), str(row["context_id"]))
        margin_delta = float(candidate["margin"]) - float(control["margin"])
        economic_adverse = _worse_economic_diagnostic(
            candidate.get("diagnostics"), control.get("diagnostics"),
        )
        if candidate.get("technical_pass") is not True or margin_delta < 0 or economic_adverse:
            adverse_lines.append(canonical_json({
                **row,
                "control": {
                    "margin": control.get("margin"), "own_bank": control.get("own_bank"),
                    "diagnostics": control.get("diagnostics"),
                    "terminal_inventory": control.get("terminal_inventory"),
                    "behavior_sha256": control.get("behavior_sha256"),
                },
                "margin_delta": margin_delta,
                "economic_adverse_vs_control": economic_adverse,
            }))
    compressed_bytes, compressed_sha, uncompressed_sha = _write_deterministic_gzip(
        adverse_path, adverse_lines,
    )
    payload = _signed_artifact({
        "schema_version": 1,
        "kind": "maximum_search_generation_receipt_retention",
        "execution_manifest_sha256": manifest.sha256,
        "generation": generation,
        "policy": manifest.payload["retention_policy"],
        "receipt_counts": counts,
        "adverse_rows": len(adverse_lines),
        "deleted_raw_rows": len(rows),
        "all_receipts_canonical_sha256": all_receipts.hexdigest(),
        "adverse_artifact": {
            "path": str(adverse_path), "rows": len(adverse_lines),
            "bytes": compressed_bytes, "sha256": compressed_sha,
            "canonical_uncompressed_sha256": uncompressed_sha,
        },
    }, "artifact_sha256")
    atomic_json(summary_path, payload)
    _validate_receipt_retention(
        payload, run_root=run_root, manifest=manifest, generation=generation,
    )
    return payload


def _ensure_generation_pruned(
    run_root: Path,
    *,
    store: SearchStore,
    manifest: ExecutionManifest,
    generation: int,
    retention: Mapping[str, Any],
) -> None:
    _validate_receipt_retention(
        retention, run_root=run_root, manifest=manifest, generation=generation,
    )
    store.apply_receipt_prune(generation, retention)


def _load_initial_artifact(path: Path, development_manifest: RunManifest) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version", "manifest_sha256", "candidate_count", "candidates",
    }:
        raise RunnerError("preflight initial population schema is not closed")
    if payload.get("schema_version") != 1 or payload.get("manifest_sha256") != development_manifest.sha256:
        raise RunnerError("preflight initial population provenance mismatch")
    if not isinstance(payload.get("candidates"), Mapping) or payload.get("candidate_count") != len(payload["candidates"]):
        raise RunnerError("preflight initial population candidate count mismatch")
    return dict(payload)


def prepare_execution(
    *,
    workspace: Path,
    contract: SearchContract,
    preflight_root: Path,
    context_registry: ContextRegistry,
    output_root: Path,
    run_id: str,
    physical_workers: int,
    max_in_flight: int,
    backend: str,
    formal_execution_authorized: bool,
    formal_authorization_id: str | None,
    development_generations: int | None,
    development_residents_per_island: int | None,
    development_births_per_island: int | None,
    development_t1_promotions_per_island: int | None,
    calibration_path: Path | None = None,
) -> dict[str, Any]:
    if output_root.exists() and any(output_root.iterdir()):
        raise RunnerError("execution output root already exists and is nonempty")
    development_manifest = RunManifest.load(
        preflight_root / "manifest.json", expected_contract_sha256=contract.sha256,
    )
    development_state = RunState.load(
        preflight_root / "checkpoint.json", development_manifest, contract,
    )
    initial_source_path = preflight_root / "initial_population.json"
    initial_source = _load_initial_artifact(initial_source_path, development_manifest)
    capacity = int(contract.scale["residents_per_island"]) if formal_execution_authorized else int(
        development_residents_per_island or 0
    )
    populations = {
        island_id: list(values if formal_execution_authorized else values[-capacity:])
        for island_id, values in development_state.payload["population_ids"].items()
    }
    selected_ids = {candidate_id for values in populations.values() for candidate_id in values}
    catalog = {
        candidate_id: initial_source["candidates"][candidate_id]
        for candidate_id in sorted(selected_ids)
    }
    initial_payload = _signed_artifact({
        "schema_version": 1,
        "kind": "maximum_search_execution_initial_population",
        "development_manifest_sha256": development_manifest.sha256,
        "capacity_per_island": capacity,
        "candidate_count": len(catalog),
        "population_ids": populations,
        "candidates": catalog,
    }, "artifact_sha256")
    output_root.mkdir(parents=True, exist_ok=True)
    initial_path = output_root / "execution_initial_population.json"
    context_path = output_root / "context_registry.json"
    atomic_json(initial_path, initial_payload)
    atomic_json(context_path, context_registry.payload)
    manifest = ExecutionManifest.create(
        run_id=run_id, contract=contract, development_manifest=development_manifest,
        preflight_root=preflight_root, initial_population_path=initial_path,
        context_registry=context_registry, physical_workers=physical_workers,
        max_in_flight=max_in_flight, backend=backend,
        formal_execution_authorized=formal_execution_authorized,
        formal_authorization_id=formal_authorization_id,
        development_generations=development_generations,
        development_residents_per_island=development_residents_per_island,
        development_births_per_island=development_births_per_island,
        development_t1_promotions_per_island=development_t1_promotions_per_island,
        calibration_path=calibration_path,
    )
    state = ExecutionState.initial(manifest, contract, populations)
    atomic_json(output_root / "execution_manifest.json", manifest.payload)
    write_execution_state(output_root / "execution_checkpoint.json", state)
    return {
        "schema_version": 1,
        "kind": "maximum_search_execution_prepared",
        "run_root": str(output_root),
        "execution_manifest_sha256": manifest.sha256,
        "context_registry_sha256": context_registry.sha256,
        "formal_execution_authorized": manifest.formal,
        "physical_workers": physical_workers,
        "backend": backend,
        "initial_candidates": len(catalog),
        "games_run": 0,
    }


def _load_execution_initial(path: Path, manifest: ExecutionManifest) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version", "kind", "development_manifest_sha256", "capacity_per_island",
        "candidate_count", "population_ids", "candidates", "artifact_sha256",
    } or not verify_signature(payload, "artifact_sha256"):
        raise RunnerError("execution initial-population schema or signature mismatch")
    if payload.get("development_manifest_sha256") != manifest.payload["development_manifest_sha256"]:
        raise RunnerError("execution initial-population development-manifest drift")
    if payload.get("candidate_count") != len(payload.get("candidates", {})):
        raise RunnerError("execution initial-population count mismatch")
    return (
        {key: list(value) for key, value in payload["population_ids"].items()},
        {key: dict(value) for key, value in payload["candidates"].items()},
    )


def _verify_runtime_sources(
    workspace: Path,
    contract: SearchContract,
    development_manifest: RunManifest,
    registry: RootRegistry,
    contexts: ContextRegistry,
) -> None:
    current = source_snapshot(workspace, contract, registry)
    if canonical_json(current) != canonical_json(development_manifest.payload["source_snapshot"]):
        raise RunnerError("source, engine, control, route, root, or implementation drift since preflight")
    if registry.manifest()["manifest_sha256"] != development_manifest.payload["root_manifest"]["manifest_sha256"]:
        raise RunnerError("root registry drift since preflight")
    verify_opponent_artifacts(contexts)


def _ensure_controls(
    store: SearchStore,
    *,
    evaluator: ParallelEvaluator,
    manifest: ExecutionManifest,
    contexts: Sequence[Mapping[str, Any]],
) -> set[int]:
    tasks = []
    for lane in LANES:
        missing = store.missing_control_contexts(lane, contexts)
        if missing:
            tasks.append({
                "kind": "control", "backend": manifest.payload["backend"], "lane": lane,
                "contexts": missing, "tier": "control", "generation": -1, "island_id": "control",
            })
    pids: set[int] = set()
    for batch in evaluator.run(tasks):
        pids.add(int(batch["worker_pid"]))
        for result in batch["results"]:
            store.put_control(batch["lane"], result)
    store.commit()
    for lane in LANES:
        for context in contexts:
            receipt = store.control(lane, str(context["context_id"]))
            if receipt.get("technical_pass") is not True:
                raise RunnerError(f"control cache failed technical gate for {lane}/{context['context_id']}")
    return pids


def _candidate_tasks(
    *,
    store: SearchStore,
    catalog: Mapping[str, Mapping[str, Any]],
    candidates_by_island: Mapping[str, Sequence[str]],
    generation: int,
    tier: str,
    contexts: Sequence[Mapping[str, Any]],
    backend: str,
) -> Iterator[dict[str, Any]]:
    for island_id, candidate_ids in sorted(candidates_by_island.items()):
        for candidate_id in candidate_ids:
            missing = store.missing_contexts(candidate_id, tier, contexts)
            if not missing:
                continue
            genome = FullTapeGenome.from_dict(catalog[candidate_id])
            yield {
                "kind": "candidate", "backend": backend, "lane": genome.lane,
                "genome": genome.to_dict(), "contexts": missing, "tier": tier,
                "generation": generation, "island_id": island_id,
            }


def _evaluate_candidates(
    store: SearchStore,
    *,
    evaluator: ParallelEvaluator,
    manifest: ExecutionManifest,
    index: CandidateIndex,
    candidates_by_island: Mapping[str, Sequence[str]],
    generation: int,
    tier: str,
    contexts: Sequence[Mapping[str, Any]],
) -> set[int]:
    candidate_ids = [candidate_id for values in candidates_by_island.values() for candidate_id in values]
    catalog = index.catalog(candidate_ids)
    tasks = _candidate_tasks(
        store=store, catalog=catalog, candidates_by_island=candidates_by_island,
        generation=generation, tier=tier, contexts=contexts,
        backend=str(manifest.payload["backend"]),
    )
    pids: set[int] = set()
    completed_batches = 0
    for batch in evaluator.run(tasks):
        pids.add(int(batch["worker_pid"]))
        for payload in batch["results"]:
            store.put_receipt({
                "candidate_id": batch["candidate_id"], "tier": tier,
                "context_id": payload["context_id"], "lane": batch["lane"],
                "generation": generation, "island_id": batch["island_id"], "payload": payload,
            })
        completed_batches += 1
        if completed_batches % 32 == 0:
            store.commit()
    store.commit()
    return pids


def _novelty(genome: FullTapeGenome, registry: RootRegistry) -> float:
    root = registry.get(genome.root_id)
    root_component = 0.5 if root.source_kind != "lane_incumbent" else 0.0
    edit_component = 0.5 * min(1.0, genome.edit_distance_from_root() / 719.0)
    return root_component + edit_component


def _score_candidates(
    store: SearchStore,
    *,
    development_manifest: RunManifest,
    index: CandidateIndex,
    registry: RootRegistry,
    candidates_by_island: Mapping[str, Sequence[str]],
    generation: int,
    scope: str,
    tiers: Sequence[str],
    contexts: Sequence[Mapping[str, Any]],
) -> dict[str, FitnessVector]:
    context_by_id = {str(row["context_id"]): row for row in contexts}
    candidate_ids = [candidate_id for values in candidates_by_island.values() for candidate_id in values]
    catalog = index.catalog(candidate_ids)
    result: dict[str, FitnessVector] = {}
    for island_id, candidate_ids in sorted(candidates_by_island.items()):
        for candidate_id in candidate_ids:
            genome = FullTapeGenome.from_dict(catalog[candidate_id])
            receipts = store.candidate_receipts(candidate_id, tiers)
            if set(receipts) != set(context_by_id):
                raise RunnerError(f"{candidate_id} lacks complete {scope} receipts")
            identity = ScoringIdentity.from_manifest(development_manifest, genome)
            rows = []
            for context_id in sorted(context_by_id):
                context = context_by_id[context_id]
                control = store.control(genome.lane, context_id)
                candidate = receipts[context_id]
                rows.append(paired_row(
                    identity=identity,
                    opponent_family=str(context["opponent_family"]), seed=int(context["seed"]),
                    seat=int(context["seat"]), control_margin=float(control["margin"]),
                    candidate_margin=float(candidate["margin"]),
                    control_own_bank=float(control["own_bank"]),
                    candidate_own_bank=float(candidate["own_bank"]),
                    technical_pass=bool(control["technical_pass"] and candidate["technical_pass"]),
                    effective_change=control["behavior_sha256"] != candidate["behavior_sha256"],
                ))
            vector, diagnostics = score_candidate(
                identity, rows, complexity=genome.edit_distance_from_root(),
                novelty=_novelty(genome, registry),
            )
            store.put_fitness(
                vector, scope=scope, generation=generation,
                island_id=island_id, diagnostics=diagnostics,
            )
            result[candidate_id] = vector
    store.commit()
    return result


def _promotion_quotas(
    contract: SearchContract,
    manifest: ExecutionManifest,
    generation: int,
) -> tuple[int, ...]:
    if not manifest.formal:
        return (int(manifest.limits["t1_promotions_per_island"]),) * contract.islands
    total = contract.t1_promotion_quota(generation)
    base, remainder = divmod(total, contract.islands)
    start = (generation * 19) % contract.islands
    extras = {(start + offset) % contract.islands for offset in range(remainder)}
    result = tuple(base + int(index in extras) for index in range(contract.islands))
    if sum(result) != total:
        raise RunnerError("T1 island promotion quotas do not close")
    return result


def _select_promotions(
    store: SearchStore,
    *,
    contract: SearchContract,
    manifest: ExecutionManifest,
    generation: int,
    candidates_by_island: Mapping[str, Sequence[str]],
    t0_fitness: Mapping[str, FitnessVector],
) -> dict[str, list[str]]:
    quotas = _promotion_quotas(contract, manifest, generation)
    result: dict[str, list[str]] = {}
    for island in island_layout(contract):
        candidates = list(candidates_by_island[island.island_id])
        quota = quotas[island.index]
        eligible = [t0_fitness[candidate_id] for candidate_id in candidates
                    if t0_fitness[candidate_id].technical_pass and t0_fitness[candidate_id].effective_change]
        if len(eligible) < quota:
            raise RunnerError(
                f"{island.island_id} has {len(eligible)} eligible T1 candidates for quota {quota}"
            )
        selected = list(select_survivors_scalable(eligible, quota)) if quota else []
        candidate_ids = [row.candidate_id for row in selected]
        store.put_promotions(generation, island.island_id, candidate_ids)
        result[island.island_id] = candidate_ids
    store.commit()
    return result


def _select_population(
    *,
    contract: SearchContract,
    manifest: ExecutionManifest,
    store: SearchStore,
    previous: Mapping[str, Sequence[str]],
    births: Mapping[str, Sequence[str]],
) -> dict[str, list[str]]:
    capacity = int(contract.scale["residents_per_island"]) if manifest.formal else int(
        manifest.limits["residents_per_island"]
    )
    result: dict[str, list[str]] = {}
    for island in island_layout(contract):
        pool = list(previous[island.island_id]) + list(births[island.island_id])
        vectors = [store.fitness(candidate_id, "t0") for candidate_id in pool]
        eligible = [row for row in vectors if row.technical_pass and row.effective_change]
        if len(eligible) < capacity:
            raise RunnerError(
                f"{island.island_id} hard gate leaves {len(eligible)} candidates for capacity {capacity}"
            )
        result[island.island_id] = [row.candidate_id for row in select_survivors_scalable(eligible, capacity)]
    return result


def _birth_artifact_paths(run_root: Path, generation: int) -> tuple[Path, Path, Path]:
    stem = f"execution_generation_{generation:04d}"
    return (
        run_root / f"{stem}_births.jsonl.gz",
        run_root / f"{stem}_births_prepared.json",
        run_root / f"{stem}_births_summary.json",
    )


def _load_birth_artifact(
    path: Path,
    *,
    shard_path: Path,
    manifest: ExecutionManifest,
    generation: int,
    expected_counts: Mapping[str, int],
) -> tuple[list[CandidateBirth], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version", "kind", "execution_manifest_sha256", "generation",
        "birth_shard", "summary", "artifact_sha256",
    } or not verify_signature(payload, "artifact_sha256"):
        raise RunnerError("birth artifact schema or signature mismatch")
    if (payload.get("schema_version") != 1 or payload.get("kind") != "maximum_search_execution_births"
            or payload.get("execution_manifest_sha256") != manifest.sha256
            or payload.get("generation") != generation):
        raise RunnerError("birth artifact provenance mismatch")
    shard = payload.get("birth_shard")
    if not isinstance(shard, Mapping) or set(shard) != {
        "path", "rows", "canonical_uncompressed_sha256", "bytes",
    } or shard.get("path") != str(shard_path) or not shard_path.is_file() or shard.get("bytes") != shard_path.stat().st_size:
        raise RunnerError("birth shard identity mismatch")
    births = list(read_birth_shard(shard_path))
    canonical = hashlib.sha256("".join(
        canonical_json(row.to_dict()) + "\n" for row in births
    ).encode("utf-8")).hexdigest()
    if len(births) != shard["rows"] or canonical != shard["canonical_uncompressed_sha256"]:
        raise RunnerError("birth shard content mismatch")
    actual: dict[str, list[int]] = {island_id: [] for island_id in expected_counts}
    for birth in births:
        if birth.generation != generation or birth.island_id not in actual:
            raise RunnerError("birth shard contains wrong generation or island")
        actual[birth.island_id].append(birth.ordinal)
    if any(sorted(actual[key]) != list(range(value)) for key, value in expected_counts.items()):
        raise RunnerError("birth shard island quota or ordinals differ")
    return births, dict(payload)


def _ensure_births(
    *,
    run_root: Path,
    contract: SearchContract,
    manifest: ExecutionManifest,
    development_manifest: RunManifest,
    registry: RootRegistry,
    index: CandidateIndex,
    generation: int,
    populations: Mapping[str, Sequence[str]],
) -> tuple[list[CandidateBirth], dict[str, Any]]:
    shard_path, prepared_path, final_path = _birth_artifact_paths(run_root, generation)
    layout = island_layout(contract)
    island_lanes = {row.island_id: row.lane for row in layout}
    formal_counts = contract.island_birth_quotas(generation)
    expected_counts = {
        island.island_id: formal_counts[island.index] if manifest.formal else min(
            formal_counts[island.index], int(manifest.limits["births_per_island"])
        )
        for island in layout
    }
    artifact_path = final_path if final_path.is_file() else prepared_path if prepared_path.is_file() else None
    if artifact_path is not None:
        births, artifact = _load_birth_artifact(
            artifact_path, shard_path=shard_path, manifest=manifest,
            generation=generation, expected_counts=expected_counts,
        )
        index.reconcile_generation(generation, births, island_lanes=island_lanes)
        if artifact_path == prepared_path:
            os.replace(prepared_path, final_path)
        return births, artifact

    if index.generation_count(generation):
        raise RunnerError("candidate index contains an unjournaled execution generation")
    # A crash can leave only the atomically completed shard before its prepared
    # journal is written. Deterministic reproposal safely overwrites that orphan
    # while the still-uncommitted index transaction is absent.
    parent_ids = [candidate_id for values in populations.values() for candidate_id in values]
    catalog = index.catalog(parent_ids)
    births, proposal = propose_generation(
        contract=contract, registry=registry,
        proposal_seed=int(development_manifest.payload["proposal_seed"]),
        generation=generation, populations=populations, catalog=catalog, index=index,
        development_limit_per_island=None if manifest.formal else int(manifest.limits["births_per_island"]),
    )
    shard = write_birth_shard(shard_path, births)
    artifact = _signed_artifact({
        "schema_version": 1,
        "kind": "maximum_search_execution_births",
        "execution_manifest_sha256": manifest.sha256,
        "generation": generation,
        "birth_shard": shard,
        "summary": proposal,
    }, "artifact_sha256")
    atomic_json(prepared_path, artifact)
    index.commit()
    index.validate_generation(generation, births, island_lanes=island_lanes)
    os.replace(prepared_path, final_path)
    return births, artifact


def _generation_completion_paths(run_root: Path, generation: int) -> tuple[Path, Path]:
    stem = f"execution_generation_{generation:04d}"
    return run_root / f"{stem}_prepared.json", run_root / f"{stem}_summary.json"


def _expected_progress(
    contract: SearchContract,
    manifest: ExecutionManifest,
    generation: int,
) -> dict[str, int]:
    if manifest.formal:
        per_generation = [contract.birth_quota(index) for index in range(generation + 1)]
        promotions = [contract.t1_promotion_quota(index) for index in range(generation + 1)]
    else:
        residents = int(manifest.limits["residents_per_island"])
        births_limit = int(manifest.limits["births_per_island"])
        per_generation = [contract.islands * residents]
        per_generation.extend(
            sum(min(value, births_limit) for value in contract.island_birth_quotas(index))
            for index in range(1, generation + 1)
        )
        promotions = [
            contract.islands * int(manifest.limits["t1_promotions_per_island"])
            for _index in range(generation + 1)
        ]
    candidates = sum(per_generation)
    promoted = sum(promotions)
    t0_games = candidates * int(manifest.payload["context_counts"]["t0"])
    t1_games = promoted * int(manifest.payload["context_counts"]["t1"])
    return {
        "generation_candidates": per_generation[-1],
        "generation_promotions": promotions[-1],
        "raw_candidates": candidates,
        "promoted_candidates": promoted,
        "t0_games": t0_games,
        "t1_games": t1_games,
        "controls": len(LANES) * (
            int(manifest.payload["context_counts"]["t0"])
            + int(manifest.payload["context_counts"]["t1"])
        ),
    }


def _validate_generation_completion(
    payload: Mapping[str, Any],
    *,
    manifest: ExecutionManifest,
    contract: SearchContract,
    generation: int,
) -> None:
    if set(payload) != {
        "schema_version", "kind", "execution_manifest_sha256", "generation",
        "candidate_count", "t1_promotions", "store_counts", "worker_pids",
        "elapsed_seconds", "candidate_games_per_second", "next_population_ids",
        "raw_candidates_created", "receipt_retention", "artifact_sha256",
    } or not verify_signature(payload, "artifact_sha256"):
        raise RunnerError("generation completion schema or signature mismatch")
    if (payload.get("schema_version") != 1 or payload.get("kind") != "maximum_search_generation_complete"
            or payload.get("execution_manifest_sha256") != manifest.sha256
            or payload.get("generation") != generation):
        raise RunnerError("generation completion provenance mismatch")
    expected_progress = _expected_progress(contract, manifest, generation)
    if payload.get("candidate_count") != expected_progress["generation_candidates"]:
        raise RunnerError("generation completion candidate count differs from the execution plan")
    if payload.get("t1_promotions") != expected_progress["generation_promotions"]:
        raise RunnerError("generation completion T1 count differs from the execution plan")
    if payload.get("raw_candidates_created") != expected_progress["raw_candidates"]:
        raise RunnerError("generation completion raw-candidate count differs from the execution plan")
    retention = payload.get("receipt_retention")
    if (not isinstance(retention, Mapping)
            or retention.get("generation") != generation
            or retention.get("execution_manifest_sha256") != manifest.sha256
            or retention.get("receipt_counts") != {
                "t0": expected_progress["generation_candidates"] * int(manifest.payload["context_counts"]["t0"]),
                "t1": expected_progress["generation_promotions"] * int(manifest.payload["context_counts"]["t1"]),
            }):
        raise RunnerError("generation completion receipt-retention counts differ from the execution plan")
    counts = payload.get("store_counts")
    expected_counts = {
        "controls": expected_progress["controls"],
        "t0": expected_progress["t0_games"],
        "t1": expected_progress["t1_games"],
        "fitness_t0": expected_progress["raw_candidates"],
        "fitness_combined": expected_progress["promoted_candidates"],
    }
    if not isinstance(counts, Mapping) or dict(counts) != expected_counts:
        raise RunnerError("generation completion store counts differ from the exact execution plan")
    pids = payload.get("worker_pids")
    if not isinstance(pids, list) or any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in pids):
        raise RunnerError("generation completion worker PID evidence is malformed")
    for field in ("elapsed_seconds", "candidate_games_per_second"):
        value = payload.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) < 0:
            raise RunnerError(f"generation completion {field} is malformed")
    capacity = int(contract.scale["residents_per_island"]) if manifest.formal else int(
        manifest.limits["residents_per_island"]
    )
    populations = payload.get("next_population_ids")
    if not isinstance(populations, Mapping):
        raise RunnerError("generation completion lacks next populations")
    expected_islands = {row.island_id: row for row in island_layout(contract)}
    if set(populations) != set(expected_islands):
        raise RunnerError("generation completion island set differs")
    all_ids: list[str] = []
    for island_id, values in populations.items():
        if not isinstance(values, list) or len(values) != capacity:
            raise RunnerError(f"{island_id} completion capacity mismatch")
        all_ids.extend(values)
    if len(all_ids) != len(set(all_ids)):
        raise RunnerError("generation completion contains duplicate residents")


def _state_from_completion(
    *,
    state: ExecutionState,
    completion: Mapping[str, Any],
    manifest: ExecutionManifest,
    contract: SearchContract,
) -> ExecutionState:
    counts = completion["store_counts"]
    candidate_games = int(counts["t0"]) + int(counts["t1"])
    return state.advanced(
        manifest=manifest, contract=contract,
        completed_generation=int(completion["generation"]),
        population_ids=completion["next_population_ids"],
        raw_candidates_created=int(completion["raw_candidates_created"]),
        t0_games_completed=int(counts["t0"]), t1_games_completed=int(counts["t1"]),
        development_games_completed=candidate_games,
    )


def _verify_completion_storage(
    payload: Mapping[str, Any],
    *,
    store: SearchStore,
    index: CandidateIndex,
) -> None:
    if store.counts() != dict(payload["store_counts"]):
        raise RunnerError("generation completion journal differs from the game/fitness ledger")
    if index.count() != int(payload["raw_candidates_created"]):
        raise RunnerError("generation completion journal differs from the candidate index")
    resident_ids = [
        candidate_id
        for values in payload["next_population_ids"].values()
        for candidate_id in values
    ]
    index.catalog(resident_ids)


def _recover_completion(
    *,
    run_root: Path,
    state: ExecutionState,
    manifest: ExecutionManifest,
    contract: SearchContract,
    store: SearchStore,
    index: CandidateIndex,
) -> ExecutionState:
    last = int(state.payload["last_completed_generation"])
    if last >= 0:
        prior_prepared, prior_final = _generation_completion_paths(run_root, last)
        if prior_prepared.is_file():
            if prior_final.exists():
                raise RunnerError("both prepared and final prior-generation completions exist")
            prior_payload = json.loads(prior_prepared.read_text(encoding="utf-8"))
            _validate_generation_completion(
                prior_payload, manifest=manifest, contract=contract, generation=last,
            )
            _ensure_generation_pruned(
                run_root, store=store, manifest=manifest, generation=last,
                retention=prior_payload["receipt_retention"],
            )
            _verify_completion_storage(prior_payload, store=store, index=index)
            store.put_generation_summary(last, prior_payload)
            store.commit()
            os.replace(prior_prepared, prior_final)
    generation = int(state.payload["next_generation"])
    maximum = contract.generations if manifest.formal else int(manifest.limits["generations"])
    if generation == maximum:
        return state
    prepared, final = _generation_completion_paths(run_root, generation)
    path = final if final.is_file() else prepared if prepared.is_file() else None
    if path is None:
        return state
    payload = json.loads(path.read_text(encoding="utf-8"))
    _validate_generation_completion(
        payload, manifest=manifest, contract=contract, generation=generation,
    )
    _ensure_generation_pruned(
        run_root, store=store, manifest=manifest, generation=generation,
        retention=payload["receipt_retention"],
    )
    _verify_completion_storage(payload, store=store, index=index)
    store.put_generation_summary(generation, payload)
    store.commit()
    advanced = _state_from_completion(
        state=state, completion=payload, manifest=manifest, contract=contract,
    )
    write_execution_state(run_root / "execution_checkpoint.json", advanced)
    if path == prepared:
        os.replace(prepared, final)
    return advanced


def _write_broad_finalists(
    run_root: Path,
    *,
    store: SearchStore,
    manifest: ExecutionManifest,
) -> dict[str, Any]:
    per_lane = 50 if manifest.formal else 50
    rows = {lane: store.top_combined(lane, per_lane) for lane in LANES}
    if manifest.formal and any(len(values) != per_lane for values in rows.values()):
        raise RunnerError("formal run completed with fewer than 50 eligible finalists per lane")
    payload = _signed_artifact({
        "schema_version": 1,
        "kind": "maximum_search_broad_finalists",
        "execution_manifest_sha256": manifest.sha256,
        "formal_execution_authorized": manifest.formal,
        "automatic_broad_launch": False,
        "automatic_promotion": False,
        "automatic_submission": False,
        "selection_order": [
            "net_wdl_transition_desc", "w_to_l_asc", "negative_tails_asc",
            "cvar_01_desc", "cvar_05_desc", "worst_margin_desc", "mean_margin_desc",
            "mean_own_bank_desc", "complexity_asc", "novelty_desc", "candidate_id_desc",
        ],
        "by_lane": rows,
    }, "artifact_sha256")
    atomic_json(run_root / "broad_finalists.json", payload)
    return payload


def run_execution(
    *,
    workspace: Path,
    contract: SearchContract,
    run_root: Path,
    stop_after_generation: int | None = None,
) -> dict[str, Any]:
    context_registry = ContextRegistry.load(run_root / "context_registry.json")
    preflight_root = Path(json.loads((run_root / "execution_manifest.json").read_text(encoding="utf-8"))["preflight_root"])
    development_manifest = RunManifest.load(
        preflight_root / "manifest.json", expected_contract_sha256=contract.sha256,
    )
    manifest = ExecutionManifest.load(
        run_root / "execution_manifest.json", contract=contract,
        development_manifest=development_manifest, context_registry=context_registry,
    )
    if manifest.formal is not (context_registry.mode == "formal"):
        raise RunnerError("execution and context modes differ")
    if manifest.formal:
        projection = manifest.payload.get("resource_projection")
        if (not isinstance(projection, Mapping)
                or shutil.disk_usage(run_root).free < int(projection["minimum_runtime_free_bytes"])):
            raise RunnerError("formal execution no longer has its dynamic-storage reserve")
    state = ExecutionState.load(
        run_root / "execution_checkpoint.json", manifest=manifest, contract=contract,
    )
    maximum = contract.generations if manifest.formal else int(manifest.limits["generations"])
    if stop_after_generation is not None:
        if (not isinstance(stop_after_generation, int) or isinstance(stop_after_generation, bool)
                or not 0 <= stop_after_generation < maximum):
            raise RunnerError("stop-after generation is outside the execution plan")
        maximum_this_call = stop_after_generation + 1
    else:
        maximum_this_call = maximum

    registry = RootRegistry.load_workspace(workspace, include_public=True)
    _verify_runtime_sources(workspace, contract, development_manifest, registry, context_registry)
    initial_path = Path(manifest.payload["initial_population_artifact"]["path"])
    initial_populations, initial_catalog = _load_execution_initial(initial_path, manifest)
    layout = island_layout(contract)
    island_lanes = {row.island_id: row.lane for row in layout}
    index_path = run_root / "execution_candidate_index.sqlite"
    started_all = time.perf_counter()
    with CandidateIndex(index_path, manifest_sha256=manifest.sha256) as index, SearchStore(
        run_root / "execution_store.sqlite", execution_manifest_sha256=manifest.sha256,
    ) as store, ParallelEvaluator(
        workspace=workspace,
        root_manifest_sha256=development_manifest.payload["root_manifest"]["manifest_sha256"],
        workers=int(manifest.payload["physical_workers"]),
        max_in_flight=int(manifest.payload["max_in_flight"]),
    ) as evaluator:
        if index.count() == 0:
            seed_index(index, initial_catalog, initial_populations, island_lanes=island_lanes)
        else:
            index.validate_initial(initial_catalog, initial_populations, island_lanes=island_lanes)
        state = _recover_completion(
            run_root=run_root, state=state, manifest=manifest, contract=contract,
            store=store, index=index,
        )
        all_contexts = tuple(context_registry.contexts("t0")) + tuple(context_registry.contexts("t1"))
        control_pids = _ensure_controls(
            store, evaluator=evaluator, manifest=manifest, contexts=all_contexts,
        )

        generations_completed_this_call = 0
        observed_pids = set(control_pids)
        while int(state.payload["next_generation"]) < maximum_this_call:
            generation = int(state.payload["next_generation"])
            if manifest.formal and shutil.disk_usage(run_root).free < int(
                manifest.payload["resource_projection"]["minimum_runtime_free_bytes"]
            ):
                raise RunnerError("formal execution paused before generation because free storage is below reserve")
            _verify_runtime_sources(workspace, contract, development_manifest, registry, context_registry)
            started = time.perf_counter()
            previous = {key: list(value) for key, value in state.payload["population_ids"].items()}
            if generation == 0:
                candidates_by_island = previous
                births_by_island = {island.island_id: [] for island in layout}
            else:
                births, _birth_artifact = _ensure_births(
                    run_root=run_root, contract=contract, manifest=manifest,
                    development_manifest=development_manifest, registry=registry,
                    index=index, generation=generation, populations=previous,
                )
                births_by_island = {island.island_id: [] for island in layout}
                for birth in births:
                    births_by_island[birth.island_id].append(birth.genome.candidate_id)
                candidates_by_island = births_by_island

            worker_pids = set(control_pids)
            worker_pids.update(_evaluate_candidates(
                store, evaluator=evaluator, manifest=manifest, index=index,
                candidates_by_island=candidates_by_island, generation=generation,
                tier="t0", contexts=context_registry.contexts("t0"),
            ))
            t0_fitness = _score_candidates(
                store, development_manifest=development_manifest, index=index, registry=registry,
                candidates_by_island=candidates_by_island, generation=generation, scope="t0",
                tiers=("t0",), contexts=context_registry.contexts("t0"),
            )
            promotions = _select_promotions(
                store, contract=contract, manifest=manifest, generation=generation,
                candidates_by_island=candidates_by_island, t0_fitness=t0_fitness,
            )
            worker_pids.update(_evaluate_candidates(
                store, evaluator=evaluator, manifest=manifest, index=index,
                candidates_by_island=promotions, generation=generation,
                tier="t1", contexts=context_registry.contexts("t1"),
            ))
            observed_pids.update(worker_pids)
            combined_contexts = tuple(context_registry.contexts("t0")) + tuple(context_registry.contexts("t1"))
            _score_candidates(
                store, development_manifest=development_manifest, index=index, registry=registry,
                candidates_by_island=promotions, generation=generation, scope="combined",
                tiers=("t0", "t1"), contexts=combined_contexts,
            )

            next_populations = previous if generation == 0 else _select_population(
                contract=contract, manifest=manifest, store=store,
                previous=previous, births=births_by_island,
            )
            counts = store.counts()
            elapsed = time.perf_counter() - started
            candidate_count = sum(len(values) for values in candidates_by_island.values())
            generation_candidate_games = candidate_count * len(context_registry.contexts("t0")) + sum(
                len(values) for values in promotions.values()
            ) * len(context_registry.contexts("t1"))
            retention = _prepare_receipt_retention(
                run_root, store=store, manifest=manifest, generation=generation,
            )
            completion = _signed_artifact({
                "schema_version": 1,
                "kind": "maximum_search_generation_complete",
                "execution_manifest_sha256": manifest.sha256,
                "generation": generation,
                "candidate_count": candidate_count,
                "t1_promotions": sum(len(values) for values in promotions.values()),
                "store_counts": counts,
                "worker_pids": sorted(worker_pids),
                "elapsed_seconds": elapsed,
                "candidate_games_per_second": generation_candidate_games / elapsed if elapsed else 0.0,
                "next_population_ids": next_populations,
                "raw_candidates_created": index.count(),
                "receipt_retention": retention,
            }, "artifact_sha256")
            _validate_generation_completion(
                completion, manifest=manifest, contract=contract, generation=generation,
            )
            prepared_path, final_path = _generation_completion_paths(run_root, generation)
            atomic_json(prepared_path, completion)
            _ensure_generation_pruned(
                run_root, store=store, manifest=manifest, generation=generation,
                retention=retention,
            )
            _verify_completion_storage(completion, store=store, index=index)
            store.put_generation_summary(generation, completion)
            store.commit()
            state = _state_from_completion(
                state=state, completion=completion, manifest=manifest, contract=contract,
            )
            write_execution_state(run_root / "execution_checkpoint.json", state)
            os.replace(prepared_path, final_path)
            generations_completed_this_call += 1

        finalists = None
        if int(state.payload["next_generation"]) == maximum:
            if manifest.formal:
                if (state.payload["raw_candidates_created"] != contract.raw_candidates
                        or state.payload["formal_t0_candidate_games_completed"] != int(contract.payload["tiers"]["t0"]["candidate_games"])
                        or state.payload["formal_t1_candidate_games_completed"] != int(contract.payload["tiers"]["t1"]["candidate_games"])):
                    raise RunnerError("formal completion counters do not close the 30M/300M contract")
            finalists = _write_broad_finalists(run_root, store=store, manifest=manifest)
        counts = store.counts()
    return {
        "schema_version": 1,
        "kind": "maximum_search_execution_result",
        "run_root": str(run_root),
        "execution_manifest_sha256": manifest.sha256,
        "formal_execution_authorized": manifest.formal,
        "status": state.payload["status"],
        "next_generation": state.payload["next_generation"],
        "generations_completed_this_call": generations_completed_this_call,
        "physical_workers": manifest.payload["physical_workers"],
        "worker_processes_observed": len(observed_pids),
        "store_counts": counts,
        "elapsed_seconds_this_call": time.perf_counter() - started_all,
        "broad_finalists_written": finalists is not None,
        "automatic_broad_launch": False,
        "automatic_promotion": False,
        "automatic_submission": False,
    }


def execution_status(run_root: Path) -> dict[str, Any]:
    manifest_path = run_root / "execution_manifest.json"
    checkpoint_path = run_root / "execution_checkpoint.json"
    if not run_root.exists():
        return {"exists": False, "run_root": str(run_root)}
    if not manifest_path.is_file() or not checkpoint_path.is_file():
        return {"exists": True, "complete_metadata": False, "run_root": str(run_root)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    store_path = run_root / "execution_store.sqlite"
    result = {
        "exists": True,
        "complete_metadata": True,
        "run_root": str(run_root),
        "run_id": manifest.get("run_id"),
        "formal_execution_authorized": manifest.get("formal_execution_authorized"),
        "backend": manifest.get("backend"),
        "physical_workers": manifest.get("physical_workers"),
        "execution_manifest_signature_valid": verify_signature(manifest, "execution_manifest_sha256"),
        "execution_checkpoint_signature_valid": verify_signature(checkpoint, "execution_checkpoint_sha256"),
        "status": checkpoint.get("status"),
        "last_completed_generation": checkpoint.get("last_completed_generation"),
        "next_generation": checkpoint.get("next_generation"),
        "raw_candidates_created": checkpoint.get("raw_candidates_created"),
        "formal_t0_candidate_games_completed": checkpoint.get("formal_t0_candidate_games_completed"),
        "formal_t1_candidate_games_completed": checkpoint.get("formal_t1_candidate_games_completed"),
        "development_games_completed": checkpoint.get("development_games_completed"),
        "store_bytes": store_path.stat().st_size if store_path.is_file() else 0,
    }
    return result


def _system_cpu_times() -> tuple[int, int]:
    """Return system idle and total ticks without a third-party dependency."""
    if os.name == "nt":
        import ctypes

        class FileTime(ctypes.Structure):
            _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

            def value(self) -> int:
                return (int(self.high) << 32) | int(self.low)

        idle, kernel, user = FileTime(), FileTime(), FileTime()
        if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user),
        ):
            raise RunnerError("GetSystemTimes failed during worker calibration")
        return idle.value(), kernel.value() + user.value()
    stat = Path("/proc/stat")
    if stat.is_file():
        values = [int(value) for value in stat.read_text(encoding="utf-8").splitlines()[0].split()[1:]]
        if len(values) < 4:
            raise RunnerError("/proc/stat CPU row is malformed")
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return idle, sum(values)
    raise RunnerError("system CPU utilization sampling is unavailable")


def calibrate_execution(
    *,
    workspace: Path,
    contract: SearchContract,
    run_root: Path,
    output: Path,
) -> dict[str, Any]:
    raw_manifest = json.loads((run_root / "execution_manifest.json").read_text(encoding="utf-8"))
    if raw_manifest.get("formal_execution_authorized") is not False or raw_manifest.get("backend") != "official":
        raise RunnerError("worker calibration requires a development official-backend execution")
    raw_state = json.loads((run_root / "execution_checkpoint.json").read_text(encoding="utf-8"))
    if raw_state.get("next_generation") != 0 or raw_state.get("status") != "prepared":
        raise RunnerError("worker calibration requires a fresh prepared execution")
    preflight_root = Path(str(raw_manifest["preflight_root"]))
    development_manifest = RunManifest.load(
        preflight_root / "manifest.json", expected_contract_sha256=contract.sha256,
    )
    source_digest = hashlib.sha256(canonical_json(
        development_manifest.payload["source_snapshot"]
    ).encode("utf-8")).hexdigest()
    idle_before, total_before = _system_cpu_times()
    started = time.perf_counter()
    result = run_execution(workspace=workspace, contract=contract, run_root=run_root)
    elapsed = time.perf_counter() - started
    idle_after, total_after = _system_cpu_times()
    delta_total, delta_idle = total_after - total_before, idle_after - idle_before
    if delta_total <= 0 or elapsed <= 0:
        raise RunnerError("worker calibration interval is empty")
    cpu_percent = 100.0 * (delta_total - delta_idle) / delta_total
    counts = result["store_counts"]
    receipt_rows = int(counts["t0"]) + int(counts["t1"])
    if receipt_rows < 1:
        raise RunnerError("worker calibration produced no candidate receipts")
    store_path = run_root / "execution_store.sqlite"
    store_bytes = sum(
        path.stat().st_size for path in (
            store_path, Path(str(store_path) + "-wal"), Path(str(store_path) + "-shm"),
        ) if path.is_file()
    )
    payload = _signed_artifact({
        "schema_version": 1,
        "kind": "maximum_search_worker_calibration",
        "contract_sha256": contract.sha256,
        "source_snapshot_sha256": source_digest,
        "execution_manifest_sha256": result["execution_manifest_sha256"],
        "backend": "official",
        "physical_workers": int(result["physical_workers"]),
        "logical_cpus": int(os.cpu_count() or 1),
        "candidate_games": receipt_rows,
        "elapsed_seconds": elapsed,
        "games_per_second": receipt_rows / elapsed,
        "cpu_percent": cpu_percent,
        "receipt_rows": receipt_rows,
        "store_bytes": store_bytes,
        "bytes_per_receipt": store_bytes / receipt_rows,
    }, "calibration_sha256")
    atomic_json(output, payload)
    return payload


def resource_estimate(
    *,
    contract: SearchContract,
    measured_games_per_second: float,
    measured_bytes_per_receipt: float,
    physical_workers: int,
) -> dict[str, Any]:
    if measured_games_per_second <= 0 or measured_bytes_per_receipt <= 0 or physical_workers < 1:
        raise RunnerError("resource estimate inputs must be positive")
    candidate_games = int(contract.scale["t0_t1_candidate_games"])
    seconds = candidate_games / measured_games_per_second
    return {
        "schema_version": 1,
        "kind": "maximum_search_resource_estimate",
        "contract_sha256": contract.sha256,
        "physical_workers": physical_workers,
        "measured_games_per_second": measured_games_per_second,
        "measured_bytes_per_receipt": measured_bytes_per_receipt,
        "projected_seconds": seconds,
        "projected_days": seconds / 86400.0,
        "projected_receipt_bytes": candidate_games * measured_bytes_per_receipt,
        "projected_receipt_gib": candidate_games * measured_bytes_per_receipt / (1024.0 ** 3),
        "formal_execution_authorized": False,
    }
