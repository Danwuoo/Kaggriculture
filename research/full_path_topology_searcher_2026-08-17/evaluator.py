"""WDL-primary paired evaluation; economics are diagnostics and tie-breaks."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import re
from typing import Any, Iterable, Mapping

try:
    from .model import ConditionalOutcomeValue
except ImportError:
    from model import ConditionalOutcomeValue


ORDER = {"L": 0, "D": 1, "W": 2}
LANE_DIR = Path(__file__).resolve().parent
ROOT = LANE_DIR.parents[1]


def _registry() -> dict[str, Any]:
    return json.loads((LANE_DIR / "evidence_registry.json").read_text(encoding="utf-8"))


def _sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _verified_candidate(registry: Mapping[str, Any], protocol: Mapping[str, Any], lane: str | None) -> bool:
    sources = {row.get("id"): row for row in registry.get("sources", []) if isinstance(row, Mapping)}
    source = sources.get(protocol.get("candidate_source_id"))
    if (not isinstance(source, Mapping) or source.get("candidate_artifact") is not True
            or source.get("technical_verified") is not True or source.get("mutable") is not False or source.get("lane") != lane
            or protocol.get("candidate_sha256") != source.get("sha256")):
        return False
    path_value = source.get("path")
    if not isinstance(path_value, str) or not path_value or Path(path_value).is_absolute():
        return False
    path = (ROOT / path_value).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError:
        return False
    if not path.is_file():
        return False
    raw = path.read_bytes()
    return len(raw) == source.get("bytes") and hashlib.sha256(raw).hexdigest() == source.get("sha256")


def outcome(rewards: Iterable[float], seat: int) -> str:
    values = list(rewards)
    if (len(values) != 2 or not isinstance(seat, int) or isinstance(seat, bool) or seat not in (0, 1)
            or any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) for value in values)):
        raise ValueError("rewards must contain two finite numeric values and seat must be 0/1")
    if values[seat] > values[1 - seat]:
        return "W"
    if values[seat] < values[1 - seat]:
        return "L"
    return "D"


def _interval(rows: list[Mapping[str, Any]]) -> dict[str, float]:
    if not rows:
        return {"mean_ordinal_delta": 0.0, "cluster_bootstrap_p025": 0.0, "cluster_bootstrap_p975": 0.0}
    clusters: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        clusters[str(row["seed"])].append(int(row["delta"]))
    keys = sorted(clusters)
    seed = int(hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(1000):
        selected = [rng.choice(keys) for _ in keys]
        values = [value for key in selected for value in clusters[key]]
        draws.append(sum(values) / len(values))
    draws.sort()
    observed = [int(row["delta"]) for row in rows]
    return {
        "mean_ordinal_delta": sum(observed) / len(observed),
        "cluster_bootstrap_p025": draws[24],
        "cluster_bootstrap_p975": draws[974],
    }


def evaluate_pairs(pairs: Iterable[Mapping[str, Any]], freshness: str, lane: str | None = None,
                   protocol: Mapping[str, Any] | None = None) -> ConditionalOutcomeValue:
    registry = _registry()
    expected_engine = registry["engine"]
    incumbent_hashes = {row.get("lane"): row["sha256"] for row in registry["sources"] if row["id"].endswith("_incumbent")}
    consumed = {int(seed) for seed in registry["consumed_seeds"]}
    protocol = dict(protocol or {})
    declared_seeds = protocol.get("seeds", [])
    declared_context_rows = protocol.get("contexts", [])
    declared_contexts = {
        (row.get("seed"), row.get("family"), row.get("context_id"))
        for row in declared_context_rows if isinstance(row, Mapping)
    } if isinstance(declared_context_rows, list) else set()
    registered_protocols = {
        row.get("protocol_id"): row for row in registry.get("paired_protocols", []) if isinstance(row, Mapping)
    }
    registered_protocol = registered_protocols.get(protocol.get("protocol_id"))
    protocol_registered = isinstance(registered_protocol, Mapping) and protocol == dict(registered_protocol)
    candidate_verified = protocol_registered and _verified_candidate(registry, protocol, lane)
    declared_protocol = bool(
        lane in ("v27_current_meta", "boatlee_v16_rc2_market_relay")
        and protocol.get("paired") is True
        and protocol.get("matched_contexts") is True
        and protocol.get("control_lane") == lane
        and protocol.get("candidate_lane") == lane
        and isinstance(protocol.get("seats"), list)
        and len(protocol["seats"]) == 2
        and all(isinstance(seat, int) and not isinstance(seat, bool) for seat in protocol["seats"])
        and sorted(protocol["seats"]) == [0, 1]
        and isinstance(protocol.get("protocol_id"), str) and bool(protocol.get("protocol_id"))
        and isinstance(declared_seeds, list) and bool(declared_seeds)
        and all(isinstance(seed, int) and not isinstance(seed, bool) for seed in declared_seeds)
        and isinstance(declared_context_rows, list) and bool(declared_context_rows)
        and len(declared_contexts) == len(declared_context_rows)
        and all(isinstance(seed, int) and not isinstance(seed, bool) and isinstance(family, str) and family and isinstance(context_id, str) and context_id for seed, family, context_id in declared_contexts)
        and {seed for seed, _family, _context_id in declared_contexts} == set(declared_seeds)
        and protocol.get("engine") == expected_engine
        and protocol.get("control_sha256") == incumbent_hashes.get(lane)
        and protocol_registered
        and candidate_verified
        and _sha(protocol.get("candidate_sha256"))
        and protocol.get("candidate_sha256") != protocol.get("control_sha256")
    )
    rows = []
    control = Counter({key: 0 for key in ORDER})
    candidate = Counter({key: 0 for key in ORDER})
    transitions = Counter({f"{a}->{b}": 0 for a in ORDER for b in ORDER})
    strata: dict[str, Counter[str]] = defaultdict(Counter)
    effective = False
    technical_valid = True
    observed_seats: set[int] = set()
    lane_isolated = True
    observed_seeds: set[int] = set()
    context_seats: dict[tuple[int, str, str], set[int]] = defaultdict(set)
    matched_keys: set[tuple[int, str, str, int]] = set()
    reasons: list[str] = []
    for raw in pairs:
        row = dict(raw)
        try:
            seed = row["seed"]
            seat = row["seat"]
            family = row["family"]
            context_id = row["context_id"]
            if (not isinstance(seed, int) or isinstance(seed, bool)
                    or not isinstance(seat, int) or isinstance(seat, bool) or seat not in (0, 1)
                    or not isinstance(family, str) or not family or not isinstance(context_id, str) or not context_id):
                raise ValueError("invalid context identity")
            c0 = outcome(row["control_rewards"], seat)
            c1 = outcome(row["candidate_rewards"], seat)
            if row.get("control_outcome", c0) != c0 or row.get("candidate_outcome", c1) != c1:
                reasons.append("reward_outcome_mismatch")
            if row.get("engine") != expected_engine or row.get("control_sha256") != protocol.get("control_sha256") or row.get("candidate_sha256") != protocol.get("candidate_sha256"):
                reasons.append("row_provenance_mismatch")
            key_tuple = (seed, family, context_id, seat)
            if key_tuple in matched_keys:
                reasons.append("duplicate_matched_context")
            matched_keys.add(key_tuple)
            context_seats[(seed, family, context_id)].add(seat)
            observed_seeds.add(seed)
        except (KeyError, TypeError, ValueError):
            reasons.append("invalid_raw_pair_schema")
            technical_valid = False
            continue
        row["delta"] = ORDER[c1] - ORDER[c0]
        observed_seats.add(seat)
        lane_isolated = lane_isolated and row.get("lane") == lane
        control[c0] += 1
        candidate[c1] += 1
        transitions[f"{c0}->{c1}"] += 1
        key = f"{family}|seat{seat}"
        strata[key]["improve" if row["delta"] > 0 else "worsen" if row["delta"] < 0 else "same"] += 1
        change_fields = ("receipt_changed", "public_state_changed", "economic_state_changed", "terminal_state_changed")
        if any(name in row and not isinstance(row[name], bool) for name in change_fields) or not isinstance(row.get("technical_valid"), bool):
            reasons.append("nonboolean_validity_or_change_flag")
            technical_valid = False
        effective = effective or any(row.get(name) is True for name in change_fields)
        technical_valid = technical_valid and row.get("technical_valid") is True
        rows.append(row)
    improve = sum(1 for row in rows if row["delta"] > 0)
    worsen = sum(1 for row in rows if row["delta"] < 0)
    if not rows:
        reasons.append("no_paired_support")
    if improve == 0:
        reasons.append("no_primary_wdl_improvement")
    if not effective:
        reasons.append("no_executed_public_economic_or_terminal_change")
    if not technical_valid:
        reasons.append("technical_validity_not_established")
    if not declared_protocol:
        reasons.append("paired_protocol_not_declared")
    if not protocol_registered:
        reasons.append("protocol_not_registered")
    if not candidate_verified:
        reasons.append("candidate_artifact_not_verified")
    if observed_seats != {0, 1}:
        reasons.append("both_seats_not_observed")
    if not lane_isolated:
        reasons.append("mixed_or_unattributed_incumbent_lane")
    if any(seats != {0, 1} for seats in context_seats.values()):
        reasons.append("context_missing_declared_seat")
    if set(context_seats) != declared_contexts:
        reasons.append("observed_contexts_do_not_match_protocol")
    if observed_seeds != set(declared_seeds):
        reasons.append("observed_seeds_do_not_match_protocol")
    authoritative_fresh = bool(observed_seeds) and not (observed_seeds & consumed)
    derived_freshness = "fresh_paired" if authoritative_fresh else "consumed_or_unverified"
    if freshness != "fresh_paired" or derived_freshness != "fresh_paired":
        reasons.append("nonfresh_evidence")
    if transitions["W->L"]:
        reasons.append("high_risk_w_to_l")
    for name, values in sorted(strata.items()):
        if values["worsen"] >= 2 and values["worsen"] > values["improve"]:
            reasons.append(f"repeatable_stratum_worsening:{name}")
    net_ordinal_delta = sum(int(row["delta"]) for row in rows)
    if improve <= worsen or net_ordinal_delta <= 0:
        reasons.append("nonpositive_primary_wdl_movement")
    wdl_gate_passed = bool(rows) and technical_valid and effective and improve > worsen and net_ordinal_delta > 0 and not reasons
    formal_authorized = registry.get("formal_efficacy_authorized") is True
    if not formal_authorized:
        reasons.append("formal_efficacy_not_authorized")
    efficacy = wdl_gate_passed and formal_authorized
    margins = [float(row["paired_margin_delta"]) for row in rows if row.get("paired_margin_delta") is not None]
    banks = [float(row["own_bank_delta"]) for row in rows if row.get("own_bank_delta") is not None]
    economics = {
        "mean_paired_margin_delta": sum(margins) / len(margins) if margins else None,
        "mean_own_bank_delta": sum(banks) / len(banks) if banks else None,
        "tie_break_scope": "identical_transition_profiles_only",
        "net_ordinal_delta": net_ordinal_delta,
    }
    return ConditionalOutcomeValue(
        lane=lane or "unattributed", protocol=protocol,
        control_wdl=dict(control), candidate_wdl=dict(candidate), transition_matrix=dict(transitions),
        improve=improve, same=len(rows) - improve - worsen, worsen=worsen,
        strata={key: dict(value) for key, value in sorted(strata.items())},
        uncertainty=_interval(rows), support=len(rows), freshness=derived_freshness,
        technical_valid=technical_valid, effective_change=effective, wdl_gate_passed=wdl_gate_passed,
        efficacy_eligible=efficacy,
        economics=economics, stop_reasons=tuple(dict.fromkeys(reasons)),
    )


def classify_summary_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Classify aggregate-only evidence without pretending it is paired raw evidence."""
    claimed = dict(fixture.get("claimed_wdl", {}))
    has_primary = int(claimed.get("wins", 0)) > 0
    level = str(fixture.get("evidence_level", "summary_only"))
    return {
        "fixture_id": fixture["id"], "proposal_rank_signal": has_primary,
        "efficacy_eligible": False,
        "rejection_reason": f"aggregate_{level}_must_use_raw_attributed_rows_through_evaluate_pairs",
    }
