"""WDL-primary, tail-preserving paired scoring without scalar collapse."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
import statistics
from typing import Any, Iterable, Mapping

from .evolution import FitnessVector
from .contract import LANES
from .checkpoint import RunManifest, verify_signature
from .genome import FullTapeGenome, GenomeError, candidate_lane


class ScoringError(ValueError):
    pass


OUTCOME_RANK = {"L": 0, "D": 1, "W": 2}


def _manifest_controls(manifest: RunManifest) -> dict[str, str]:
    if manifest.sha256 != manifest.payload.get("manifest_sha256") or not verify_signature(manifest.payload, "manifest_sha256"):
        raise ScoringError("scoring manifest signature mismatch")
    snapshot = manifest.payload.get("source_snapshot")
    if not isinstance(snapshot, Mapping) or snapshot.get("pool_lanes") is not False:
        raise ScoringError("scoring manifest does not preserve lane isolation")
    controls = snapshot.get("controls")
    if not isinstance(controls, Mapping) or set(controls) != set(LANES):
        raise ScoringError("scoring manifest lacks both lane controls")
    result: dict[str, str] = {}
    for lane in LANES:
        row = controls[lane]
        digest = row.get("sha256") if isinstance(row, Mapping) else None
        if (not isinstance(digest, str) or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)):
            raise ScoringError(f"scoring manifest has malformed {lane} control hash")
        result[lane] = digest
    return result


@dataclass(frozen=True, init=False)
class ScoringIdentity:
    _manifest: RunManifest
    _genome: FullTapeGenome

    @classmethod
    def from_manifest(cls, manifest: RunManifest, genome: FullTapeGenome) -> "ScoringIdentity":
        _manifest_controls(manifest)
        result = object.__new__(cls)
        object.__setattr__(result, "_manifest", manifest)
        object.__setattr__(result, "_genome", genome)
        result.validate()
        return result

    @property
    def manifest_sha256(self) -> str:
        return self._manifest.sha256

    @property
    def candidate_id(self) -> str:
        return self._genome.candidate_id

    @property
    def lane(self) -> str:
        return self._genome.lane

    @property
    def control_sha256(self) -> str:
        return _manifest_controls(self._manifest)[self.lane]

    def validate(self) -> None:
        controls = _manifest_controls(self._manifest)
        try:
            if candidate_lane(self.candidate_id) != self.lane:
                raise ScoringError("candidate identity and scoring lane differ")
        except GenomeError as error:
            raise ScoringError("candidate identity is malformed") from error
        if self.control_sha256 != controls[self.lane]:
            raise ScoringError("scoring control differs from the signed manifest")
        for label, digest in (("manifest", self.manifest_sha256), ("control", self.control_sha256)):
            if (not isinstance(digest, str) or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)):
                raise ScoringError(f"scoring {label} identity must be a full SHA-256")


def outcome(margin: float) -> str:
    return "W" if margin > 0 else "L" if margin < 0 else "D"


def _cvar(values: list[float], fraction: float) -> float:
    count = max(1, math.ceil(len(values) * fraction))
    return statistics.fmean(sorted(values)[:count])


def paired_row(
    *,
    identity: ScoringIdentity,
    opponent_family: str,
    seed: int,
    seat: int,
    control_margin: float,
    candidate_margin: float,
    control_own_bank: float,
    candidate_own_bank: float,
    technical_pass: bool,
    effective_change: bool,
) -> dict[str, Any]:
    identity.validate()
    if not isinstance(seed, int) or isinstance(seed, bool) or not isinstance(seat, int) or isinstance(seat, bool) or seat not in (0, 1):
        raise ScoringError("paired context requires exact integer seed and seat")
    if not isinstance(opponent_family, str) or not opponent_family:
        raise ScoringError("paired context requires opponent family")
    if type(technical_pass) is not bool or type(effective_change) is not bool:
        raise ScoringError("paired context flags must be strict booleans")
    for label, value in (
        ("control_margin", control_margin), ("candidate_margin", candidate_margin),
        ("control_own_bank", control_own_bank), ("candidate_own_bank", candidate_own_bank),
    ):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise ScoringError(f"{label} must be finite")
    control_outcome = outcome(float(control_margin))
    candidate_outcome = outcome(float(candidate_margin))
    return {
        "provenance": {
            "manifest_sha256": identity.manifest_sha256,
            "candidate_id": identity.candidate_id,
            "lane": identity.lane,
            "control_sha256": identity.control_sha256,
        },
        "context": {"opponent_family": opponent_family, "seed": seed, "seat": seat},
        "control_margin": float(control_margin),
        "candidate_margin": float(candidate_margin),
        "margin_delta": float(candidate_margin) - float(control_margin),
        "control_own_bank": float(control_own_bank),
        "candidate_own_bank": float(candidate_own_bank),
        "control_outcome": control_outcome,
        "candidate_outcome": candidate_outcome,
        "outcome_rank_delta": OUTCOME_RANK[candidate_outcome] - OUTCOME_RANK[control_outcome],
        "own_bank_delta": float(candidate_own_bank) - float(control_own_bank),
        "technical_pass": bool(technical_pass),
        "effective_change": bool(effective_change),
    }


def score_candidate(
    identity: ScoringIdentity,
    rows: Iterable[Mapping[str, Any]],
    *,
    complexity: int,
    novelty: float,
) -> tuple[FitnessVector, dict[str, Any]]:
    identity.validate()
    if not isinstance(complexity, int) or isinstance(complexity, bool) or complexity < 0:
        raise ScoringError("complexity must be a non-negative integer")
    if not isinstance(novelty, (int, float)) or isinstance(novelty, bool) or not math.isfinite(float(novelty)) or novelty < 0:
        raise ScoringError("novelty must be finite and non-negative")
    values = list(rows)
    if not values:
        raise ScoringError("candidate score requires paired rows")
    contexts = []
    seen: set[tuple[str, int, int]] = set()
    for row in values:
        if set(row) != {
            "provenance", "context", "control_margin", "candidate_margin", "margin_delta",
            "control_own_bank", "candidate_own_bank", "own_bank_delta", "control_outcome",
            "candidate_outcome", "outcome_rank_delta", "technical_pass", "effective_change",
        }:
            raise ScoringError("paired row schema is not closed")
        provenance = row.get("provenance")
        expected_provenance = {
            "manifest_sha256": identity.manifest_sha256,
            "candidate_id": identity.candidate_id,
            "lane": identity.lane,
            "control_sha256": identity.control_sha256,
        }
        if not isinstance(provenance, Mapping) or dict(provenance) != expected_provenance:
            raise ScoringError("paired row provenance differs from the manifest-derived scoring identity")
        context = row.get("context")
        if not isinstance(context, Mapping) or set(context) != {"opponent_family", "seed", "seat"}:
            raise ScoringError("paired row lacks context")
        key = (context.get("opponent_family"), context.get("seed"), context.get("seat"))
        if (not isinstance(key[0], str) or not key[0] or not isinstance(key[1], int) or isinstance(key[1], bool)
                or not isinstance(key[2], int) or isinstance(key[2], bool) or key[2] not in (0, 1)):
            raise ScoringError("paired row context is malformed")
        if key in seen:
            raise ScoringError("duplicate paired context")
        seen.add(key)
        contexts.append(key)
        for field in (
            "control_margin", "candidate_margin", "margin_delta", "control_own_bank",
            "candidate_own_bank", "own_bank_delta", "outcome_rank_delta",
        ):
            if (not isinstance(row.get(field), (int, float)) or isinstance(row.get(field), bool)
                    or not math.isfinite(float(row[field]))):
                raise ScoringError(f"paired row {field} is malformed")
        if not isinstance(row["outcome_rank_delta"], int) or isinstance(row["outcome_rank_delta"], bool):
            raise ScoringError("paired row outcome rank delta must be an integer")
        expected_control_outcome = outcome(float(row["control_margin"]))
        expected_candidate_outcome = outcome(float(row["candidate_margin"]))
        expected_margin_delta = float(row["candidate_margin"]) - float(row["control_margin"])
        expected_bank_delta = float(row["candidate_own_bank"]) - float(row["control_own_bank"])
        expected_rank_delta = OUTCOME_RANK[expected_candidate_outcome] - OUTCOME_RANK[expected_control_outcome]
        if (row.get("control_outcome") != expected_control_outcome
                or row.get("candidate_outcome") != expected_candidate_outcome):
            raise ScoringError("paired row outcome is malformed")
        if (float(row["margin_delta"]) != expected_margin_delta
                or float(row["own_bank_delta"]) != expected_bank_delta
                or row["outcome_rank_delta"] != expected_rank_delta):
            raise ScoringError("paired row derived fields differ from raw receipts")
        if type(row.get("technical_pass")) is not bool or type(row.get("effective_change")) is not bool:
            raise ScoringError("paired row flags must be strict booleans")

    deltas = [float(row["candidate_margin"]) - float(row["control_margin"]) for row in values]
    bank = [float(row["candidate_own_bank"]) - float(row["control_own_bank"]) for row in values]
    grouped_negative_seeds: dict[tuple[str, int], set[int]] = defaultdict(set)
    for row, (family, seed, seat) in zip(values, contexts):
        if float(row["candidate_margin"]) - float(row["control_margin"]) < 0:
            grouped_negative_seeds[(family, seat)].add(seed)
    tails = [
        {"opponent_family": family, "seat": seat, "negative_seeds": sorted(seeds), "negative_seed_count": len(seeds)}
        for (family, seat), seeds in sorted(grouped_negative_seeds.items()) if len(seeds) >= 2
    ]
    transitions: dict[str, int] = defaultdict(int)
    for row in values:
        transitions[f"{outcome(float(row['control_margin']))}_TO_{outcome(float(row['candidate_margin']))}"] += 1
    effective = sum(row["effective_change"] is True for row in values)
    vector = FitnessVector(
        candidate_id=identity.candidate_id,
        lane=identity.lane,
        control_sha256=identity.control_sha256,
        manifest_sha256=identity.manifest_sha256,
        technical_pass=all(row["technical_pass"] is True for row in values),
        effective_change=effective > 0,
        net_wdl_transition=sum(
            OUTCOME_RANK[outcome(float(row["candidate_margin"]))]
            - OUTCOME_RANK[outcome(float(row["control_margin"]))]
            for row in values
        ),
        w_to_l=transitions.get("W_TO_L", 0),
        repeatable_family_seat_negative_tails=len(tails),
        cvar_01=_cvar(deltas, 0.01),
        cvar_05=_cvar(deltas, 0.05),
        worst_margin=min(deltas),
        mean_margin=statistics.fmean(deltas),
        mean_own_bank=statistics.fmean(bank),
        complexity=int(complexity),
        novelty=float(novelty),
    )
    diagnostics = {
        "contexts": len(values),
        "effective_contexts": effective,
        "transition_matrix": dict(sorted(transitions.items())),
        "paired_margin_wdl": [sum(value > 0 for value in deltas), sum(value == 0 for value in deltas), sum(value < 0 for value in deltas)],
        "repeatable_family_seat_negative_tails": tails,
        "fitness": {
            "technical_pass": vector.technical_pass,
            "effective_change": vector.effective_change,
            "net_wdl_transition": vector.net_wdl_transition,
            "w_to_l": vector.w_to_l,
            "cvar_01": vector.cvar_01,
            "cvar_05": vector.cvar_05,
            "worst_margin": vector.worst_margin,
            "mean_margin": vector.mean_margin,
            "mean_own_bank": vector.mean_own_bank,
            "complexity": vector.complexity,
            "novelty": vector.novelty,
        },
    }
    return vector, diagnostics


def select_broad_finalists(
    rows_by_lane: Mapping[str, Iterable[FitnessVector]],
    *,
    manifest: RunManifest,
) -> dict[str, tuple[FitnessVector, ...]]:
    from .evolution import select_survivors

    if set(rows_by_lane) != set(LANES):
        raise ScoringError("broad finalists require both independent incumbent lanes")
    expected_control_sha256_by_lane = _manifest_controls(manifest)
    per_lane = 50
    result: dict[str, tuple[FitnessVector, ...]] = {}
    for lane in LANES:
        rows = list(rows_by_lane[lane])
        if any(
            row.lane != lane or row.control_sha256 != expected_control_sha256_by_lane[lane]
            or row.manifest_sha256 != manifest.sha256
            for row in rows
        ):
            raise ScoringError(f"{lane} contains cross-lane, cross-run, or wrong-control fitness")
        eligible = [row for row in rows if row.technical_pass and row.effective_change]
        if len(eligible) < per_lane:
            raise ScoringError(f"{lane} has fewer than {per_lane} eligible broad finalists")
        result[lane] = select_survivors(eligible, per_lane)
    return result
