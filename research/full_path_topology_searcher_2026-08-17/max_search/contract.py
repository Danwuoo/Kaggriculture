"""Closed scale contract and exact quota arithmetic for the maximum search."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


LANES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
MODES = ("coordinate", "large_neighborhood", "de_novo", "novelty")
EXPECTED_SCALE = {
    "population": 16_384,
    "generations": 2_000,
    "raw_candidates": 30_000_000,
    "t0_t1_candidate_games": 300_000_000,
    "broad_finalists": 100,
    "islands": 32,
    "residents_per_island": 512,
}
EXPECTED_T0 = {"candidate_count": 30_000_000, "games_per_candidate": 6, "candidate_games": 180_000_000}
EXPECTED_T1 = {"candidate_count": 5_000_000, "additional_games_per_candidate": 24, "candidate_games": 120_000_000}
EXPECTED_CHANNELS = ["farmer", "hands", "market", "full"]
EXPECTED_ROOT_FAMILIES = ["lane_incumbent", "deduplicated_public_tape", "pass_tape"]
EXPECTED_TAIL_FIELDS = ["w_to_l", "repeatable_family_seat_negative_tails", "cvar_01", "cvar_05", "worst_margin"]
EXPECTED_TIE_BREAK_FIELDS = ["mean_margin", "mean_own_bank", "lower_complexity", "novelty"]
EXPECTED_ENGINE = {
    "commit": "bded87b0d7879078c726a93a4884d044f79c4eed",
    "python_sha256": "fb9215c5e21a25243e2d13e75b3d70a79cf7d78fff150a90f1bb5eacf9ba2bcf",
    "configuration_sha256": "7f196f4aaf9b4e482fbd61ba4bf19f5cec4da0f81938ece756954035a65c0bb5",
}


class ContractError(ValueError):
    """Raised when the maximum-search contract is not exact and closed."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ContractError(f"{label} fields differ: missing={sorted(expected-actual)} extra={sorted(actual-expected)}")


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ContractError(f"{label} must be an integer >= {minimum}")
    return value


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{label} must be an array")
    return value


@dataclass(frozen=True)
class SearchContract:
    payload: Mapping[str, Any]
    sha256: str

    @property
    def scale(self) -> Mapping[str, int]:
        return self.payload["scale"]

    @property
    def raw_candidates(self) -> int:
        return int(self.scale["raw_candidates"])

    @property
    def generations(self) -> int:
        return int(self.scale["generations"])

    @property
    def population(self) -> int:
        return int(self.scale["population"])

    @property
    def islands(self) -> int:
        return int(self.scale["islands"])

    def birth_quota(self, generation: int) -> int:
        """Return exact new semantic candidates assigned to one generation.

        Generation zero owns the resident roots. The remaining budget is spread
        across generations 1..1999 with a deterministic largest-remainder rule.
        """
        if not isinstance(generation, int) or isinstance(generation, bool) or not 0 <= generation < self.generations:
            raise ContractError("generation outside contract")
        if generation == 0:
            return self.population
        remaining = self.raw_candidates - self.population
        slots = self.generations - 1
        base, remainder = divmod(remaining, slots)
        return base + int(generation <= remainder)

    def island_birth_quotas(self, generation: int) -> tuple[int, ...]:
        total = self.birth_quota(generation)
        base, remainder = divmod(total, self.islands)
        # Rotate the extra births so low-numbered islands do not receive all
        # remainder capacity over 2,000 generations.
        start = (generation * 17) % self.islands
        extras = {(start + offset) % self.islands for offset in range(remainder)}
        result = tuple(base + int(index in extras) for index in range(self.islands))
        if sum(result) != total:
            raise AssertionError("island quota arithmetic drift")
        return result

    def t1_promotion_quota(self, generation: int) -> int:
        """Apportion exactly five million T1 promotions over all births."""
        t1_total = int(self.payload["tiers"]["t1"]["candidate_count"])
        before = sum(self.birth_quota(index) for index in range(generation))
        after = before + self.birth_quota(generation)
        return (after * t1_total // self.raw_candidates) - (before * t1_total // self.raw_candidates)

    def plan_summary(self) -> dict[str, Any]:
        birth_counts = Counter(self.birth_quota(index) for index in range(self.generations))
        promotions = sum(self.t1_promotion_quota(index) for index in range(self.generations))
        return {
            "schema_version": 1,
            "kind": "maximum_full_tape_search_plan",
            "contract_sha256": self.sha256,
            "scale": dict(self.scale),
            "birth_quota_distribution": {str(key): value for key, value in sorted(birth_counts.items())},
            "birth_quota_total": sum(key * count for key, count in birth_counts.items()),
            "t1_promotion_total": promotions,
            "t0_candidate_games": self.raw_candidates * int(self.payload["tiers"]["t0"]["games_per_candidate"]),
            "t1_candidate_games": promotions * int(self.payload["tiers"]["t1"]["additional_games_per_candidate"]),
            "island_layout": {
                lane: dict(self.payload["lanes"][lane]["modes"]) for lane in LANES
            },
            "formal_execution_authorized": False,
        }


def _validate(payload: Mapping[str, Any]) -> None:
    _exact_keys(payload, {
        "schema_version", "kind", "status", "authority", "formal_execution_authorized",
        "pool_lanes", "scale", "tiers", "lanes", "genome", "selection", "engine",
        "execution_boundary",
    }, "contract")
    if payload["schema_version"] != 2 or payload["kind"] != "maximum_full_tape_population_search_contract":
        raise ContractError("unsupported maximum-search contract schema")
    if payload["status"] != "development_only_not_launched":
        raise ContractError("contract status must remain development-only")
    if payload["authority"] != "research/full_path_topology_searcher_2026-08-17/CURRENT_TASK.md":
        raise ContractError("contract authority differs from the active task summary")
    if payload["formal_execution_authorized"] is not False or payload["pool_lanes"] is not False:
        raise ContractError("development contract cannot authorize execution or pool lanes")

    scale = _object(payload["scale"], "scale")
    _exact_keys(scale, set(EXPECTED_SCALE), "scale")
    for key, expected in EXPECTED_SCALE.items():
        if _integer(scale[key], f"scale.{key}", minimum=1) != expected:
            raise ContractError(f"scale.{key} must equal fixed maximum {expected}")
    if scale["population"] != scale["islands"] * scale["residents_per_island"]:
        raise ContractError("resident population must divide exactly across islands")

    tiers = _object(payload["tiers"], "tiers")
    _exact_keys(tiers, {"t0", "t1", "control_cache_games_in_t0_t1_budget", "broad_games_in_t0_t1_budget"}, "tiers")
    t0 = _object(tiers["t0"], "tiers.t0")
    t1 = _object(tiers["t1"], "tiers.t1")
    _exact_keys(t0, set(EXPECTED_T0), "tiers.t0")
    _exact_keys(t1, set(EXPECTED_T1), "tiers.t1")
    for label, row in (("t0", t0), ("t1", t1)):
        for key, value in row.items():
            _integer(value, f"tiers.{label}.{key}", minimum=1)
    if t0["candidate_count"] != scale["raw_candidates"]:
        raise ContractError("every raw candidate must receive T0")
    if dict(t0) != EXPECTED_T0 or dict(t1) != EXPECTED_T1:
        raise ContractError("T0/T1 split differs from the fixed 180M/120M plan")
    if t0["candidate_count"] * t0["games_per_candidate"] != t0["candidate_games"]:
        raise ContractError("T0 game arithmetic mismatch")
    if t1["candidate_count"] * t1["additional_games_per_candidate"] != t1["candidate_games"]:
        raise ContractError("T1 game arithmetic mismatch")
    if t0["candidate_games"] + t1["candidate_games"] != scale["t0_t1_candidate_games"]:
        raise ContractError("T0/T1 game budget mismatch")
    if tiers["control_cache_games_in_t0_t1_budget"] is not False or tiers["broad_games_in_t0_t1_budget"] is not False:
        raise ContractError("candidate-game budget scope must remain explicit")

    lanes = _object(payload["lanes"], "lanes")
    _exact_keys(lanes, set(LANES), "lanes")
    for lane in LANES:
        lane_row = _object(lanes[lane], f"lanes.{lane}")
        _exact_keys(lane_row, {"islands", "modes"}, f"lanes.{lane}")
        if _integer(lane_row["islands"], f"lanes.{lane}.islands", minimum=1) != 16:
            raise ContractError(f"{lane} must own exactly 16 islands")
        modes = _object(lane_row["modes"], f"lanes.{lane}.modes")
        _exact_keys(modes, set(MODES), f"lanes.{lane}.modes")
        if any(_integer(value, f"lanes.{lane}.modes.{mode}", minimum=1) != 4 for mode, value in modes.items()):
            raise ContractError(f"{lane} must own four islands per mode")
        if sum(modes.values()) != lane_row["islands"]:
            raise ContractError(f"{lane} island mode total mismatch")

    genome = _object(payload["genome"], "genome")
    _exact_keys(genome, {"meaningful_turns", "replacement_horizons", "channels", "root_families", "operators"}, "genome")
    if genome["meaningful_turns"] != 719:
        raise ContractError("full-tape genome must contain 719 meaningful turns")
    if _array(genome["replacement_horizons"], "genome.replacement_horizons") != [1, 2, 4, 8, 24, 48, 96, 192, 719]:
        raise ContractError("replacement horizons differ from the fixed search surface")
    if _array(genome["channels"], "genome.channels") != EXPECTED_CHANNELS:
        raise ContractError("genome channels differ from the fixed search surface")
    if _array(genome["root_families"], "genome.root_families") != EXPECTED_ROOT_FAMILIES:
        raise ContractError("genome root families differ from the fixed search surface")
    required_operators = {
        "point_replace", "market_insert", "market_remove", "market_replace", "market_reorder",
        "quantity_step", "time_shift", "donor_block", "destroy_repair", "compatible_crossover",
    }
    operators = _array(genome["operators"], "genome.operators")
    if set(operators) != required_operators or len(operators) != len(required_operators):
        raise ContractError("genome operator surface is incomplete or duplicated")

    selection = _object(payload["selection"], "selection")
    _exact_keys(selection, {
        "primary", "hard_technical_gate", "effective_change_required", "broad_finalists_per_lane",
        "tail_fields", "tie_break_fields", "opponent_identity_runtime_feature",
        "opponent_private_runtime_feature",
    }, "selection")
    if selection["primary"] != "net_wdl_transition" or selection["hard_technical_gate"] is not True:
        raise ContractError("selection must remain WDL-primary and technically gated")
    if selection["effective_change_required"] is not True:
        raise ContractError("action-only no-ops must remain ineligible")
    if _integer(selection["broad_finalists_per_lane"], "selection.broad_finalists_per_lane", minimum=1) != 50:
        raise ContractError("each lane must contribute exactly 50 broad finalists")
    if selection["broad_finalists_per_lane"] * len(LANES) != scale["broad_finalists"]:
        raise ContractError("broad finalists must split exactly and independently across lanes")
    if _array(selection["tail_fields"], "selection.tail_fields") != EXPECTED_TAIL_FIELDS:
        raise ContractError("selection tail fields differ from the fixed downside contract")
    if _array(selection["tie_break_fields"], "selection.tie_break_fields") != EXPECTED_TIE_BREAK_FIELDS:
        raise ContractError("selection tie-break fields differ from the fixed contract")
    if selection["opponent_identity_runtime_feature"] is not False or selection["opponent_private_runtime_feature"] is not False:
        raise ContractError("runtime selection cannot use opponent identity or private state")

    engine = _object(payload["engine"], "engine")
    _exact_keys(engine, set(EXPECTED_ENGINE), "engine")
    if dict(engine) != EXPECTED_ENGINE:
        raise ContractError("audited engine fingerprint differs from the fixed contract")

    boundary = _object(payload["execution_boundary"], "execution_boundary")
    _exact_keys(boundary, {
        "seed_registry", "context_registry", "physical_workers", "cpu_target_percent",
        "storage_retention",
        "automatic_broad_launch", "automatic_promotion", "automatic_submission",
    }, "execution_boundary")
    if any(boundary[key] is not None for key in ("seed_registry", "context_registry", "physical_workers")):
        raise ContractError("development contract must not preselect execution inputs")
    if boundary["cpu_target_percent"] != [50, 65]:
        raise ContractError("CPU calibration target must remain 50-65 percent")
    retention = _object(boundary["storage_retention"], "execution_boundary.storage_retention")
    _exact_keys(retention, {
        "mode", "minimum_free_bytes", "retain_all_negative_margin_receipts",
        "retain_all_technical_failures", "retain_worse_economic_diagnostics",
        "hash_all_deleted_receipts", "delete_raw_receipts_after_signed_generation",
    }, "execution_boundary.storage_retention")
    if retention["mode"] != "generation_adverse_compact_prune":
        raise ContractError("formal storage retention mode differs from the authorized dynamic policy")
    if _integer(retention["minimum_free_bytes"], "storage_retention.minimum_free_bytes", minimum=1) < 10 * 1024 ** 3:
        raise ContractError("dynamic storage reserve must be at least 10 GiB")
    if any(retention[key] is not True for key in (
        "retain_all_negative_margin_receipts", "retain_all_technical_failures",
        "retain_worse_economic_diagnostics", "hash_all_deleted_receipts",
        "delete_raw_receipts_after_signed_generation",
    )):
        raise ContractError("dynamic receipt retention guarantees must remain enabled")
    if any(boundary[key] is not False for key in ("automatic_broad_launch", "automatic_promotion", "automatic_submission")):
        raise ContractError("automatic external or later-tier actions are forbidden")


def load_contract(path: Path) -> SearchContract:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ContractError("contract root must be an object")
    _validate(payload)
    contract = SearchContract(payload=payload, sha256=canonical_sha256(payload))
    summary = contract.plan_summary()
    if summary["birth_quota_total"] != contract.raw_candidates:
        raise ContractError("generation birth quotas do not sum to raw candidate budget")
    if summary["t1_promotion_total"] != int(payload["tiers"]["t1"]["candidate_count"]):
        raise ContractError("generation T1 quotas do not sum to promotion budget")
    if summary["t0_candidate_games"] + summary["t1_candidate_games"] != int(contract.scale["t0_t1_candidate_games"]):
        raise ContractError("generation plan does not reproduce T0/T1 game budget")
    return contract
