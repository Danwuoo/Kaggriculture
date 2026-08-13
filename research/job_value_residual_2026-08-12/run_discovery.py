"""Run and reproduce the frozen 16-context, at-most-64-game discovery block."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from analysis import discovery_gate, label_pair, summarize_discovery
from engine_runner import GameRun, behavior_view, run_game
from forced_policy import make_forced_factory
from ledger import estimate_window, derive_horizon_effects
from protocol import INCUMBENTS, LANE_ROOT, control_path, readable_route, stage_contexts
from schema import CandidateWindow, HorizonEffect, from_json, to_json
from window_search import mine_candidates


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _trace_path(output: Path, run: GameRun) -> Path:
    return output / "control_traces" / f"{run.incumbent}__{run.opponent_family}__{run.seed}__seat{run.seat}.json.gz"


def _candidate_trace_path(output: Path, run: GameRun, window: CandidateWindow) -> Path:
    return output / "candidate_traces" / (
        f"{run.incumbent}__{run.opponent_family}__{run.seed}__seat{run.seat}__{window.candidate_id}.json.gz"
    )


def _write_deterministic_trace(path: Path, run: GameRun) -> None:
    """Store all observed control frames with a fixed gzip timestamp and JSON order."""
    payload = {
        "policy_metadata": run.policy_metadata,
        "summary": run.summary,
        "trace": [asdict(frame) for frame in run.trace],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
            stream.write(_canonical_bytes(payload))


def _margin(summary: Mapping[str, Any], seat: int) -> float:
    rewards = summary["rewards"]
    return float(rewards[seat]) - float(rewards[1 - seat])


def _technical_failures(summary: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if list(summary.get("statuses", ())) != ["DONE", "DONE"]:
        failures.append("termination")
    for prefix in ("", "opponent_"):
        if summary.get(f"{prefix}exception") is not None:
            failures.append(f"{prefix}exception")
        if int(summary.get(f"{prefix}timeout_calls", 0)):
            failures.append(f"{prefix}timeout")
        if bool(summary.get(f"{prefix}overage_exhausted", False)):
            failures.append(f"{prefix}overage")
        if int(summary.get(f"{prefix}max_market_orders", 0)) > 10:
            failures.append(f"{prefix}market_overflow")
        issues = summary.get(f"{prefix}action_issues", {})
        if isinstance(issues, Mapping) and any(int(issues.get(name, 0)) for name in ("malformed", "hand_alignment", "market_overflow")):
            failures.append(f"{prefix}action_issues")
    return failures


def _quotes(control: Sequence[Any], candidate: Sequence[Any], effects: Sequence[HorizonEffect]) -> dict[str, float] | None:
    control_frames = {frame.step: frame for frame in control}
    candidate_frames = {frame.step: frame for frame in candidate}
    products = {
        product
        for effect in effects
        for bucket in (effect.liquidatable, effect.asset, effect.capacity)
        for product, _quantity, _provenance in bucket
    }
    quotes: dict[str, float] = {}
    for product in products:
        values: list[float] = []
        for frames in (control_frames, candidate_frames):
            for frame in frames.values():
                prices = (frame.observation.get("market") or {}).get("prices", {})
                value = prices.get(product) if isinstance(prices, Mapping) else None
                if isinstance(value, (int, float)):
                    values.append(float(value))
        if not values:
            return None
        quotes[product] = min(values)
    return quotes


def _effect_values(control: GameRun, candidate: GameRun, window: CandidateWindow) -> tuple[tuple[HorizonEffect, ...], dict[int, float | None]]:
    effects = derive_horizon_effects(control.trace, candidate.trace, window)
    if effects is None:
        return (), {24: None, 48: None}
    # The conservative quote is the lowest public quote seen in either matched trace.
    # This is intentionally stricter than quoting only at a favorable candidate step.
    quotes = _quotes(control.trace, candidate.trace, effects)
    priced = estimate_window(effects, quotes or {}, {}) if quotes is not None else None
    result = {24: None, 48: None}
    if priced is not None:
        for horizon, breakdown in priced.items():
            result[horizon] = breakdown.total
    return effects, result


def _logistics_delivery_valid(window: CandidateWindow) -> bool:
    if window.family != "logistics_market":
        return True
    if not window.sell_directives:
        return False
    for directive in window.sell_directives:
        before = window.actions[:directive.offset + 1]
        if not any(action and action[0] in {"HARVEST", "DROP"} for action in before):
            return False
    return True


def candidate_market_receipts(trace: Sequence[Any]) -> list[dict[str, Any]]:
    """Canonically preserve every committed forced-run SELL unit receipt.

    The official lockstep market can reject an earlier SELL while a later order
    succeeds; the committed receipt stream has no engine-provided order index.
    Preserve its exact per-frame order and retain the deterministic full trace
    reference beside it instead of inventing an ambiguous order association.
    """
    rows: list[dict[str, Any]] = []
    for frame in sorted(trace, key=lambda item: int(item.step)):
        for receipt_index, receipt in enumerate(frame.market_receipts):
            if (
                not isinstance(receipt, (tuple, list))
                or len(receipt) != 3
                or receipt[0] != frame.step
                or not isinstance(receipt[2], (int, float))
            ):
                raise ValueError(f"candidate trace has malformed receipt at step {frame.step}")
            rows.append({
                "step": int(frame.step), "receipt_index": receipt_index,
                "product": str(receipt[1]), "receipt": float(receipt[2]),
            })
    return rows


def _candidate_record(
    control: GameRun, candidate: GameRun, window: CandidateWindow, trace_file: Path, candidate_trace_file: Path,
    candidate_trace_sha256: str,
) -> dict[str, Any]:
    effects, values = _effect_values(control, candidate, window)
    scored_window = replace(window, effects=effects)
    control_view, candidate_view = control.summary, candidate.summary
    label = label_pair(
        {"margin": _margin(control_view, control.seat)},
        {"margin": _margin(candidate_view, candidate.seat)},
    )
    failures = _technical_failures(control_view) + _technical_failures(candidate_view)
    return {
        "kind": "candidate",
        "context": {"incumbent": control.incumbent, "opponent_family": control.opponent_family, "seed": control.seed, "seat": control.seat},
        "incumbent": control.incumbent,
        "opponent_family": control.opponent_family,
        "seed": control.seed,
        "seat": control.seat,
        "control_trace": trace_file.as_posix(),
        "candidate_trace": candidate_trace_file.as_posix(),
        "candidate_trace_sha256": candidate_trace_sha256,
        "candidate": {
            "candidate_id": scored_window.candidate_id,
            "family": scored_window.family,
            "trigger_step": scored_window.trigger_step,
            "actor": scored_window.actor,
            "rejoin_step": scored_window.rejoin_step,
        },
        "window": to_json(scored_window),
        "control": control_view,
        "candidate_run": candidate_view,
        "candidate_market_receipts": candidate_market_receipts(candidate.trace),
        "metadata": candidate.policy_metadata,
        "label": label.to_dict(),
        "delta_value_24": values[24],
        "delta_value_48": values[48],
        "technical_failure": bool(failures),
        "technical_failure_reasons": failures,
        "logistics_delivery_valid": _logistics_delivery_valid(scored_window),
        "effect_provenance": [asdict(effect) for effect in effects],
    }


def _control_record(run: GameRun, trace_file: Path) -> dict[str, Any]:
    return {
        "kind": "control",
        "context": {"incumbent": run.incumbent, "opponent_family": run.opponent_family, "seed": run.seed, "seat": run.seat},
        "incumbent": run.incumbent,
        "opponent_family": run.opponent_family,
        "seed": run.seed,
        "seat": run.seat,
        "trace": trace_file.as_posix(),
        "summary": run.summary,
        "technical_failure": bool(_technical_failures(run.summary)),
        "technical_failure_reasons": _technical_failures(run.summary),
    }


def _abort_if_technical(records: Sequence[Mapping[str, Any]]) -> None:
    for record in records:
        if record.get("technical_failure"):
            raise RuntimeError(f"discovery technical stop: {record.get('technical_failure_reasons')}")


def run_discovery(output: Path) -> dict[str, Any]:
    """Run exactly sixteen controls and up to three forced windows per context."""
    output.mkdir(parents=True, exist_ok=True)
    controls: list[tuple[GameRun, Path]] = []
    records: list[dict[str, Any]] = []
    for incumbent, family, seed, seat in stage_contexts("discovery"):
        run = run_game(incumbent, control_path(incumbent), family, seed, seat, capture_trace=True)
        trace_path = _trace_path(output, run)
        _write_deterministic_trace(trace_path, run)
        record = _control_record(run, trace_path.relative_to(output))
        records.append(record)
        _abort_if_technical((record,))
        controls.append((run, trace_path.relative_to(output)))

    for control, trace_file in controls:
        route = json.loads(readable_route(control.incumbent).read_text(encoding="utf-8"))
        windows = mine_candidates(
            control.incumbent, control.trace, route,
            opponent_family=control.opponent_family, seed=control.seed, seat=control.seat,
        )[:3]
        for window in windows:
            forced = run_game(
                control.incumbent, control_path(control.incumbent), control.opponent_family,
                control.seed, control.seat, policy_factory=make_forced_factory(window), capture_trace=True,
            )
            candidate_trace_path = _candidate_trace_path(output, forced, window)
            _write_deterministic_trace(candidate_trace_path, forced)
            record = _candidate_record(
                control, forced, window, trace_file, candidate_trace_path.relative_to(output), _sha256(candidate_trace_path),
            )
            records.append(record)
            _abort_if_technical((record,))
    games_path = output / "discovery_games.jsonl"
    games_path.write_bytes(b"".join(_canonical_bytes(record) for record in records))
    candidate_rows = [record for record in records if record["kind"] == "candidate"]
    summary = summarize_discovery(candidate_rows)
    gate = discovery_gate(summary)
    manifest = LANE_ROOT / "artifacts" / "prechange_manifest.json"
    windows_payload = {
        "schema_version": 4,
        "candidate_market_receipt_schema": "step-receipt-index-product-receipt-v1",
        "candidate_trace_sha256": "sha256-file-bytes-v1",
        "prechange_manifest_sha256": _sha256(manifest),
        "discovery_games_sha256": _sha256(games_path),
        "rows": [
            {"incumbent": row["incumbent"], "context": row["context"], "window": row["window"], "label": row["label"], "delta_value_24": row["delta_value_24"], "delta_value_48": row["delta_value_48"]}
            for row in candidate_rows
        ],
    }
    _write_json(output / "discovery_windows.json", windows_payload)
    summary_payload = {
        "schema_version": 4,
        "candidate_market_receipt_schema": "step-receipt-index-product-receipt-v1",
        "candidate_trace_sha256": "sha256-file-bytes-v1",
        "prechange_manifest_sha256": _sha256(manifest),
        "discovery_games_sha256": _sha256(games_path),
        "controls": len(controls),
        "candidate_games": len(candidate_rows),
        "total_games": len(records),
        "strata": summary,
        "gate": gate,
    }
    _write_json(output / "discovery_summary.json", summary_payload)
    return summary_payload


def _same_behavior(stored: Mapping[str, Any], fresh: GameRun) -> bool:
    return behavior_view(fresh) == {
        key: stored[key]
        for key in behavior_view(fresh)
    }


def _stored_trace_receipts(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    trace = payload.get("trace")
    if not isinstance(trace, list):
        raise RuntimeError("candidate trace has no trace list")
    rows: list[dict[str, Any]] = []
    for frame in trace:
        if not isinstance(frame, Mapping) or not isinstance(frame.get("step"), int):
            raise RuntimeError("candidate trace has malformed frame")
        receipts = frame.get("market_receipts")
        if not isinstance(receipts, list):
            raise RuntimeError("candidate trace has malformed receipts")
        for index, receipt in enumerate(receipts):
            if not isinstance(receipt, list) or len(receipt) != 3 or receipt[0] != frame["step"]:
                raise RuntimeError("candidate trace has malformed receipt")
            rows.append({
                "step": frame["step"], "receipt_index": index,
                "product": str(receipt[1]), "receipt": float(receipt[2]),
            })
    return rows


def _read_candidate_trace(record: Mapping[str, Any], records_path: Path) -> Mapping[str, Any]:
    relative = record.get("candidate_trace")
    if not isinstance(relative, str):
        raise RuntimeError("candidate row lacks candidate trace reference")
    trace_path = records_path.parent / relative
    if not trace_path.is_file():
        raise RuntimeError("candidate trace is missing")
    expected_hash = record.get("candidate_trace_sha256")
    if not isinstance(expected_hash, str) or _sha256(trace_path) != expected_hash:
        raise RuntimeError("candidate trace hash mismatch")
    try:
        with gzip.open(trace_path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("candidate trace cannot be parsed") from error
    if not isinstance(payload, Mapping):
        raise RuntimeError("candidate trace payload is malformed")
    return payload


def audit_existing(path: Path) -> dict[str, Any]:
    """Offline-only integrity audit for immutable forced-candidate evidence."""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    audited = 0
    for record in records:
        if record.get("kind") != "candidate":
            continue
        payload = _read_candidate_trace(record, path)
        if payload.get("summary") != record.get("candidate_run"):
            raise RuntimeError("candidate trace summary mismatch")
        if payload.get("policy_metadata") != record.get("metadata"):
            raise RuntimeError("candidate trace metadata mismatch")
        if _stored_trace_receipts(payload) != record.get("candidate_market_receipts"):
            raise RuntimeError("candidate trace receipt mismatch")
        audited += 1
    return {"audited_candidates": audited, "pass": True}


def migrate_existing(path: Path) -> dict[str, Any]:
    """Offline-only schema migration for already retained candidate trace files."""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    for record in records:
        if record.get("kind") == "candidate":
            relative = record.get("candidate_trace")
            if not isinstance(relative, str):
                raise RuntimeError("candidate row lacks candidate trace reference")
            trace_path = path.parent / relative
            if not trace_path.is_file():
                raise RuntimeError("candidate trace is missing")
            record["candidate_trace_sha256"] = _sha256(trace_path)
    path.write_bytes(b"".join(_canonical_bytes(record) for record in records))
    games_hash = _sha256(path)
    for name in ("discovery_windows.json", "discovery_summary.json"):
        artifact_path = path.parent / name
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        payload["schema_version"] = 4
        payload["candidate_market_receipt_schema"] = "step-receipt-index-product-receipt-v1"
        payload["candidate_trace_sha256"] = "sha256-file-bytes-v1"
        payload["discovery_games_sha256"] = games_hash
        _write_json(artifact_path, payload)
    return {"migrated_candidates": sum(record.get("kind") == "candidate" for record in records), "discovery_games_sha256": games_hash}


def verify_existing(path: Path) -> dict[str, Any]:
    """Re-run every retained game and reject any action, result, label, or rejoin drift."""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    audit_existing(path)
    controls: dict[tuple[str, str, int, int], GameRun] = {}
    verified = 0
    for record in records:
        context = record["context"]
        key = (context["incumbent"], context["opponent_family"], int(context["seed"]), int(context["seat"]))
        if record["kind"] != "control":
            continue
        fresh = run_game(*key[:1], control_path(key[0]), key[1], key[2], key[3])
        if not _same_behavior(record["summary"], fresh):
            raise RuntimeError(f"control reproduction mismatch: {key}")
        controls[key] = fresh
        verified += 1
    for record in records:
        if record["kind"] != "candidate":
            continue
        context = record["context"]
        key = (context["incumbent"], context["opponent_family"], int(context["seed"]), int(context["seat"]))
        window = from_json(record["window"])
        fresh = run_game(
            key[0], control_path(key[0]), key[1], key[2], key[3],
            policy_factory=make_forced_factory(window), capture_trace=True,
        )
        if not _same_behavior(record["candidate_run"], fresh):
            raise RuntimeError(f"candidate reproduction mismatch: {key} {window.candidate_id}")
        control = controls[key]
        fresh_label = label_pair({"margin": _margin(control.summary, key[3])}, {"margin": _margin(fresh.summary, key[3])}).to_dict()
        if fresh_label != record["label"]:
            raise RuntimeError(f"label reproduction mismatch: {key} {window.candidate_id}")
        if candidate_market_receipts(fresh.trace) != record.get("candidate_market_receipts"):
            raise RuntimeError(f"receipt reproduction mismatch: {key} {window.candidate_id}")
        for name in ("status", "applied_steps", "abort_step", "abort_reason", "observed_rejoin_position"):
            if fresh.policy_metadata.get(name) != record["metadata"].get(name):
                raise RuntimeError(f"rejoin reproduction mismatch: {key} {window.candidate_id} {name}")
        verified += 1
    return {"verified_games": verified, "pass": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-existing", type=Path)
    parser.add_argument("--audit-existing", type=Path)
    parser.add_argument("--migrate-existing", type=Path)
    args = parser.parse_args()
    if sum(value is not None for value in (args.output, args.verify_existing, args.audit_existing, args.migrate_existing)) != 1:
        parser.error("provide exactly one mode")
    if args.output:
        print(json.dumps(run_discovery(args.output), sort_keys=True))
    elif args.verify_existing:
        print(json.dumps(verify_existing(args.verify_existing), sort_keys=True))
    elif args.audit_existing:
        print(json.dumps(audit_existing(args.audit_existing), sort_keys=True))
    else:
        print(json.dumps(migrate_existing(args.migrate_existing), sort_keys=True))


if __name__ == "__main__":
    main()
