"""Deterministic labels and per-incumbent discovery stop gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from protocol import INCUMBENTS


THRESHOLDS = (0.0, 25.0, 50.0, 100.0, 200.0)
_OUTCOME_RANK = {"L": 0, "D": 1, "W": 2}


@dataclass(frozen=True)
class Label:
    sign: str
    outcome_transition: str
    margin_delta: float
    control_outcome: str
    candidate_outcome: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def outcome(margin: Any) -> str:
    """Return W/D/L from the incumbent's paired terminal margin."""
    value = float(margin)
    return "W" if value > 0 else "L" if value < 0 else "D"


def label_pair(control: Mapping[str, Any], candidate: Mapping[str, Any]) -> Label:
    """Classify a paired result, letting result transitions beat raw margin."""
    control_margin, candidate_margin = float(control["margin"]), float(candidate["margin"])
    left, right = outcome(control_margin), outcome(candidate_margin)
    transition = f"{left}_TO_{right}"
    difference = candidate_margin - control_margin
    if _OUTCOME_RANK[right] != _OUTCOME_RANK[left]:
        sign = "positive" if _OUTCOME_RANK[right] > _OUTCOME_RANK[left] else "negative"
    else:
        sign = "positive" if difference > 0 else "negative" if difference < 0 else "neutral"
    return Label(sign, transition, difference, left, right)


def _candidate_score(row: Mapping[str, Any]) -> float | None:
    try:
        left, right = float(row["delta_value_24"]), float(row["delta_value_48"])
    except (KeyError, TypeError, ValueError):
        return None
    if left == 0 or right == 0 or (left > 0) != (right > 0):
        return None
    return min(left, right)


def _label_sign(row: Mapping[str, Any]) -> str:
    label = row.get("label", {})
    return str(label.get("sign", "neutral")) if isinstance(label, Mapping) else "neutral"


def _accuracy(predictions: Iterable[tuple[str, str]]) -> float:
    pairs = [(truth, predicted) for truth, predicted in predictions if truth in {"positive", "negative"}]
    return sum(truth == predicted for truth, predicted in pairs) / len(pairs) if pairs else 0.0


def _metadata_status(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata", {})
    return str(metadata.get("status", "")) if isinstance(metadata, Mapping) else ""


def _technical_failure(row: Mapping[str, Any]) -> bool:
    return bool(row.get("technical_failure", False))


def _logistics_delivery_valid(row: Mapping[str, Any]) -> bool:
    candidate = row.get("candidate", {})
    if not isinstance(candidate, Mapping) or candidate.get("family") != "logistics_market":
        return True
    return bool(row.get("logistics_delivery_valid", False))


def _stratum(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    labeled = [row for row in rows if _label_sign(row) in {"positive", "negative"}]
    scored = [(row, _candidate_score(row)) for row in labeled]
    scoreable = [(row, score) for row, score in scored if score is not None]
    choices: list[dict[str, Any]] = []
    for threshold in THRESHOLDS:
        eligible = [(row, score) for row, score in scoreable if abs(score) >= threshold]
        score_accuracy = _accuracy((_label_sign(row), "positive" if score > 0 else "negative") for row, score in eligible)
        coverage = len(eligible)
        choices.append({"threshold": threshold, "score_accuracy": score_accuracy, "coverage": coverage})
    selected = max(choices, key=lambda item: (item["score_accuracy"], item["coverage"], item["threshold"]))
    selected_threshold = float(selected["threshold"])
    predictions = [(row, score) for row, score in scoreable if abs(score) >= selected_threshold]
    truth = [_label_sign(row) for row in labeled]
    baseline_always = _accuracy((sign, "positive") for sign in truth)
    baseline_maintenance = _accuracy(
        (_label_sign(row), "positive" if (row.get("candidate") or {}).get("family") == "maintenance_trade" else "negative")
        for row in labeled
    )
    baseline_incumbent = _accuracy((sign, "negative") for sign in truth)
    families = sorted({str((row.get("candidate") or {}).get("family")) for row in labeled if (row.get("candidate") or {}).get("family")})
    return {
        "candidates": len(rows),
        "labeled": len(labeled),
        "positive": sum(sign == "positive" for sign in truth),
        "negative": sum(sign == "negative" for sign in truth),
        "neutral": sum(_label_sign(row) == "neutral" for row in rows),
        "families": families,
        "legal_rejoins": sum(_metadata_status(row) == "rejoined" for row in rows),
        "legal_rejoin_rate": sum(_metadata_status(row) == "rejoined" for row in rows) / len(rows) if rows else 0.0,
        "technical_failures": sum(_technical_failure(row) for row in rows),
        "invalid_logistics": sum(not _logistics_delivery_valid(row) for row in rows),
        "threshold": selected_threshold,
        "threshold_choices": choices,
        "score_accuracy": selected["score_accuracy"],
        "score_coverage": selected["coverage"],
        "always_intervene_accuracy": baseline_always,
        "maintenance_first_accuracy": baseline_maintenance,
        "always_incumbent_accuracy": baseline_incumbent,
        # Stable aliases keep the frozen protocol's test fixtures intentionally small.
        "constant_accuracy": baseline_always,
        "family_accuracy": baseline_maintenance,
        "incumbent_accuracy": baseline_incumbent,
    }


def summarize_discovery(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Summarize candidate games separately; controls are never pooled as labels."""
    grouped = {incumbent: [] for incumbent in INCUMBENTS}
    for row in rows:
        incumbent = row.get("incumbent")
        if incumbent in grouped:
            grouped[incumbent].append(row)
    return {incumbent: _stratum(grouped[incumbent]) for incumbent in INCUMBENTS}


def discovery_gate(summary: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Apply the immutable dual-incumbent continuation gate without pooling."""
    strata: dict[str, dict[str, Any]] = {}
    for incumbent in INCUMBENTS:
        item = summary.get(incumbent, {})
        failures: list[str] = []
        if int(item.get("technical_failures", 0)) != 0:
            failures.append("technical_failures")
        if int(item.get("positive", 0)) < 4:
            failures.append("positive_labels_lt_4")
        if int(item.get("negative", 0)) < 4:
            failures.append("negative_labels_lt_4")
        if len(item.get("families", [])) < 2:
            failures.append("job_families_lt_2")
        if float(item.get("legal_rejoin_rate", 0.0)) <= 0.5:
            failures.append("legal_rejoin_rate_le_0_5")
        score = float(item.get("score_accuracy", 0.0))
        for key, failure in (
            ("always_intervene_accuracy", "not_better_than_always_intervene"),
            ("maintenance_first_accuracy", "not_better_than_maintenance_first"),
            ("always_incumbent_accuracy", "not_better_than_always_incumbent"),
        ):
            legacy = {"always_intervene_accuracy": "constant_accuracy", "maintenance_first_accuracy": "family_accuracy", "always_incumbent_accuracy": "incumbent_accuracy"}[key]
            baseline = float(item.get(key, item.get(legacy, 0.0)))
            if score <= baseline:
                failures.append(failure)
        if int(item.get("invalid_logistics", 0)) != 0:
            failures.append("logistics_without_harvest_or_drop_before_sell")
        strata[incumbent] = {"pass": not failures, "failures": failures}
    return {"pass": all(value["pass"] for value in strata.values()), "strata": strata}
