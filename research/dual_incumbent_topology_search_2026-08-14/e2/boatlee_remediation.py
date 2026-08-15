"""Attributable Boatlee S2 remediation on consumed diagnostic contexts only."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import json
import multiprocessing as mp
from pathlib import Path
import statistics
from typing import Any

import formal_s1 as s1
from compiler import compile_genome
from materialize import isolated_import, materialize_finalist, static_audit
from model import AsyncGenome, MarketEditGene


HERE = s1.HERE
ROOT = s1.ROOT
RUN_ID = "e2_s2_boatlee_remediation_20260815_v1"
DEFAULT_ROOT = HERE / "artifacts" / "remediation" / RUN_ID
LANE = "boatlee_v16_rc2_market_relay"
OTHER_LANE = "v27_current_meta"
FULL_CANDIDATE_ID = "ac_3aa759d7d7fc4a409c409326"
S1_ROOT = HERE / "artifacts" / "formal" / s1.RUN_ID
S2_ROOT = HERE / "artifacts" / "formal" / "e2_s2_20260815_boatlee_tail_v1"
S2_DECISION = HERE / "s2_decision.json"
CONSUMED_SEEDS = (42284410, 73912654, 95715007, 41193493, 61594307, 58893729)
OPPONENTS = s1.OPPONENTS
SEATS = s1.SEATS
WORKER_LIMIT = 15


def remediation_candidates() -> dict[str, Any]:
    common = {
        "parent_id": FULL_CANDIDATE_ID,
        "causal_bundle_id": "e2_s2_boatlee_steps_240_241",
    }
    step_240 = AsyncGenome(
        LANE,
        market_edits=(
            MarketEditGene(240, 0, "quantity", 0, ("SELL", "WOOL", 18), 0),
            MarketEditGene(240, 1, "remove", 1, ("SELL", "WHEAT", 2), 1),
        ),
        mutation_id="retain_step_240_only",
        **common,
    )
    step_241 = AsyncGenome(
        LANE,
        market_edits=(
            MarketEditGene(241, 0, "insert", 0, ("SELL", "FERTILIZER", 16)),
            MarketEditGene(241, 1, "move", 9, ("HIRE",), 7),
        ),
        mutation_id="retain_step_241_only",
        **common,
    )
    candidates = {
        "step_240_only": compile_genome(LANE, step_240),
        "step_241_only": compile_genome(LANE, step_241),
    }
    if not all(candidate.accepted for candidate in candidates.values()):
        raise RuntimeError("Boatlee remediation ablation did not compile")
    expected = {
        "step_240_only": {
            240: [
                ["SELL", "WOOL", 18], ["BUY_LAND"],
                *[["HIRE"] for _ in range(7)],
            ],
        },
        "step_241_only": {
            241: [
                ["SELL", "FERTILIZER", 16],
                *[["HIRE"] for _ in range(6)],
                ["BUY_SEED", "MELON", 7], ["HIRE"],
            ],
        },
    }
    for name, candidate in candidates.items():
        observed = {int(row["step"]): row["market"] for row in candidate.patches}
        if observed != expected[name]:
            raise RuntimeError(f"unexpected {name} patch: {observed}")
    return candidates


def _context_key(context: dict[str, Any]) -> str:
    return "|".join((
        str(context["opponent"]), str(int(context["seed"])), str(int(context["seat"])),
    ))


def _formal_evidence() -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for tier, formal_root in (("s1", S1_ROOT), ("s2", S2_ROOT)):
        manifest = json.loads((formal_root / "manifest.json").read_text(encoding="utf-8"))
        for job in manifest["candidate_jobs"]:
            if job["context"]["lane"] != LANE:
                continue
            shard_path = formal_root / "formal" / "candidates" / "shards" / f"{job['job_id']}.json"
            shard = json.loads(shard_path.read_text(encoding="utf-8"))
            body = dict(shard)
            embedded = body.pop("shard_sha256", None)
            if embedded != s1.payload_hash(body):
                raise RuntimeError(f"invalid formal shard: {shard_path}")
            if shard.get("status") != "complete" or shard.get("result", {}).get("technical_status") != "complete":
                raise RuntimeError(f"incomplete formal evidence: {shard_path}")
            result = shard["result"]
            reference = {key: value for key, value in result.items() if key != "control"}
            key = _context_key(job["context"])
            if key in evidence:
                raise RuntimeError(f"duplicate formal context: {key}")
            evidence[key] = {
                "tier": tier,
                "context": job["context"],
                "control": result["control"],
                "full_reference": reference,
                "source_job_id": job["job_id"],
                "source_shard_sha256": embedded,
            }
    expected = len(CONSUMED_SEEDS) * len(OPPONENTS) * len(SEATS)
    if len(evidence) != expected:
        raise RuntimeError(f"expected {expected} formal Boatlee contexts, found {len(evidence)}")
    if {row["context"]["seed"] for row in evidence.values()} != set(CONSUMED_SEEDS):
        raise RuntimeError("formal evidence seeds differ from frozen consumed set")
    return evidence


def _frozen_paths(root: Path) -> dict[str, Any]:
    return {
        "controls": {
            lane: root / "inputs" / "controls" / lane / "main.py"
            for lane in (LANE, OTHER_LANE)
        },
        "candidates": {
            "full_block_reference": root / "inputs" / "candidates" / "full_block_reference" / "main.py",
            "step_240_only": root / "inputs" / "candidates" / "step_240_only" / "main.py",
            "step_241_only": root / "inputs" / "candidates" / "step_241_only" / "main.py",
        },
        "opponents": {
            family: root / "inputs" / "opponents" / family / "main.py"
            for family in s1.SOURCE_PUBLIC_OPPONENTS
        },
    }


def _s2_decision_authority() -> dict[str, Any]:
    decision = json.loads(S2_DECISION.read_text(encoding="utf-8"))
    canonical, valid = s1._canonical_file(S2_DECISION, "s2_decision_sha256")
    checks = {
        "canonical": valid,
        "decision": decision.get("overall_decision") == "E2_S2_REMEDIATION_REQUIRED",
        "candidate": decision["lanes"][LANE]["candidate_id"] == FULL_CANDIDATE_ID,
        "new_version_required": decision["required_remediation"]["new_attributable_version_required"] is True,
        "diagnostic_seed_reuse_only": decision["required_remediation"]["consumed_s1_s2_seeds_may_be_used_for_diagnostics_not_efficacy"] is True,
        "later_tier": decision.get("later_tier_launched") is False,
    }
    return {
        "pass": all(checks.values()), "checks": checks,
        "file_sha256": s1.file_sha256(S2_DECISION),
        "canonical_sha256": canonical,
    }


def _jobs(root: Path, artifacts: dict[str, dict[str, Any]], evidence: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for variant in ("full_block_reference", "step_240_only", "step_241_only"):
        for row in evidence.values():
            context = row["context"]
            job = {
                "kind": "consumed_seed_diagnostic",
                "evaluation_mode": "e2_s2_boatlee_atomic_ablation",
                "variant": variant,
                "candidate_id": artifacts[variant]["candidate_id"],
                "context": context,
                "formal_source_tier": row["tier"],
                "artifact": {
                    "path": artifacts[variant]["path"],
                    "sha256": artifacts[variant]["sha256"],
                },
                "run_root": str(root),
                "efficacy_claim": None,
                "formal_fresh": False,
            }
            job["job_id"] = "rem_" + s1.payload_hash(job)[:24]
            jobs.append(job)
    return sorted(jobs, key=lambda row: row["job_id"])


def prepare(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if root.exists():
        raise FileExistsError(f"new remediation root required: {root}")
    authority = s1.verify_authority()
    decision_authority = _s2_decision_authority()
    if not authority["pass"] or not decision_authority["pass"]:
        raise RuntimeError("E1c or S2 decision authority failed")
    engine = s1.RUNNER.assert_engine_current()
    candidates = remediation_candidates()
    evidence = _formal_evidence()
    source_protocol = json.loads((S2_ROOT / "protocol.json").read_text(encoding="utf-8"))
    root.mkdir(parents=True)
    frozen = _frozen_paths(root)
    copied_controls = {
        lane: s1._copy_exact(
            S2_ROOT / "inputs" / "controls" / lane / "main.py",
            frozen["controls"][lane],
        )
        for lane in (LANE, OTHER_LANE)
    }
    if any(copied_controls[lane]["sha256"] != source_protocol["control_hashes"][lane] for lane in copied_controls):
        raise RuntimeError("remediation control differs from formal S2")
    copied_opponents: dict[str, Any] = {}
    for family, filenames in s1.PUBLIC_OPPONENT_FILES.items():
        source_dir = S2_ROOT / "inputs" / "opponents" / family
        target_dir = frozen["opponents"][family].parent
        files = {name: s1._copy_exact(source_dir / name, target_dir / name) for name in filenames}
        copied_opponents[family] = {"files": files, "entrypoint": str(frozen["opponents"][family])}

    artifacts: dict[str, dict[str, Any]] = {}
    full = s1._copy_exact(
        S2_ROOT / "inputs" / "candidates" / LANE / FULL_CANDIDATE_ID / "main.py",
        frozen["candidates"]["full_block_reference"],
    )
    artifacts["full_block_reference"] = {**full, "candidate_id": FULL_CANDIDATE_ID, "role": "exact_s2_replay_reference"}
    for variant, candidate in candidates.items():
        built = materialize_finalist(candidate, frozen["candidates"][variant])
        artifacts[variant] = {
            **built, "role": "consumed_seed_atomic_diagnostic",
            "genome": candidate.genome.payload(),
            "patches": list(candidate.patches),
            "lineage": candidate.genome.lineage_payload(),
        }
    audits = {
        variant: {
            "static": static_audit(Path(row["path"])),
            "isolated_import": isolated_import(Path(row["path"])),
        }
        for variant, row in artifacts.items()
    }
    if not all(row["static"]["pass"] and row["isolated_import"]["callable_agent"] for row in audits.values()):
        raise RuntimeError(f"standalone audit failed: {audits}")
    jobs = _jobs(root, artifacts, evidence)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "e2_s2_boatlee_remediation_manifest",
        "run_id": RUN_ID,
        "run_root": str(root),
        "purpose": "atom-level attribution and public-feature capture",
        "efficacy_claim": None,
        "new_formal_fresh_seeds_executed": False,
        "consumed_seed_diagnostics_authorized": True,
        "consumed_seeds": list(CONSUMED_SEEDS),
        "contexts": len(evidence),
        "variants": artifacts,
        "standalone_audits": audits,
        "controls": copied_controls,
        "opponents": copied_opponents,
        "engine_fingerprint": engine,
        "s2_decision_authority": decision_authority,
        "formal_evidence_sha256": s1.payload_hash(evidence),
        "jobs_sha256": s1.payload_hash(jobs),
        "job_count": len(jobs),
        "implementation_sha256": s1.file_sha256(Path(__file__)),
        "later_tier_launched": False,
    }
    manifest["manifest_sha256"] = s1.payload_hash({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    s1.atomic_json(root / "manifest.json", manifest)
    s1.atomic_json(root / "formal_evidence.json", {"evidence": evidence, "formal_evidence_sha256": manifest["formal_evidence_sha256"]})
    s1.atomic_json(root / "jobs.json", {"jobs": jobs, "jobs_sha256": manifest["jobs_sha256"]})
    return {
        "pass": True, "run_id": RUN_ID,
        "manifest_sha256": manifest["manifest_sha256"],
        "job_count": len(jobs),
        "candidate_ids": {name: row["candidate_id"] for name, row in artifacts.items()},
        "new_formal_fresh_seeds_executed": False,
    }


def _opponent_path(root: Path, family: str) -> Path:
    frozen = _frozen_paths(root)
    if family == "other_incumbent":
        return frozen["controls"][OTHER_LANE]
    if family in frozen["opponents"]:
        return frozen["opponents"][family]
    raise KeyError(family)


def _tile_counts(farm: dict[str, Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in farm.get("tiles", []) or []:
        for tile in row or []:
            if not isinstance(tile, dict):
                continue
            kind = str(tile.get("kind", "UNKNOWN"))
            counts[f"tile_kind_{kind}"] += 1
            if tile.get("crop"):
                counts[f"crop_{tile['crop']}"] += 1
            if tile.get("animal"):
                counts[f"animal_{tile['animal']}"] += 1
    return dict(sorted(counts.items()))


def public_features(observation: dict[str, Any]) -> dict[str, int]:
    if "private" not in observation:
        raise RuntimeError("runner observation schema unexpectedly lacks private boundary")
    player = int(observation["player"])
    farms = observation.get("farms", [])
    market = observation.get("market", {})
    town = observation.get("town", {})
    if len(farms) < 2 or not isinstance(market, dict) or not isinstance(town, dict):
        raise RuntimeError("missing public selector feature source")
    features: dict[str, int] = {"step": int(observation["step"]), "player": player}
    for role, index in (("own", player), ("opponent", 1 - player)):
        farm = farms[index]
        features[f"{role}_money"] = int(farm.get("money", 0) or 0)
        features[f"{role}_hands"] = len(farm.get("hands", []) or [])
        features[f"{role}_unlocked_quadrants"] = len(farm.get("unlocked_quadrants", []) or [])
        for key, value in _tile_counts(farm).items():
            features[f"{role}_{key}"] = int(value)
    for product, value in sorted((market.get("prices", {}) or {}).items()):
        features[f"market_price_{product}"] = int(value or 0)
    for product, value in sorted((market.get("inventory", {}) or {}).items()):
        features[f"market_inventory_{product}"] = int(value or 0)
    features["town_unlocked_shops"] = len(town.get("unlocked_shops", []) or [])
    return dict(sorted(features.items()))


def _evaluate_job(job: dict[str, Any]) -> dict[str, Any]:
    try:
        if job.get("evaluation_mode") != "e2_s2_boatlee_atomic_ablation":
            raise ValueError("unknown remediation evaluation mode")
        if job.get("formal_fresh") is not False or int(job["context"]["seed"]) not in CONSUMED_SEEDS:
            raise PermissionError("remediation accepts consumed diagnostic seeds only")
        artifact = Path(job["artifact"]["path"])
        if s1.file_sha256(artifact) != job["artifact"]["sha256"]:
            raise RuntimeError("remediation artifact hash mismatch")
        root = Path(job["run_root"])
        original = s1.RUNNER.opponent_path
        s1.RUNNER.opponent_path = lambda _lane, family: _opponent_path(root, family)
        context = job["context"]
        try:
            run = s1.RUNNER.run_game(
                LANE, artifact, context["opponent"], int(context["seed"]),
                int(context["seat"]), capture_trace=True,
            )
        finally:
            s1.RUNNER.opponent_path = original
        outcome = s1._outcome(run)
        if outcome["technical_status"] != "complete":
            return {"job_id": job["job_id"], "status": "technical_invalid", "efficacy": None, "result": outcome}
        frame = run.trace[240]
        if frame.step != 240:
            raise RuntimeError("missing step-240 decision frame")
        return {
            "job_id": job["job_id"], "status": "complete", "efficacy": None,
            "variant": job["variant"], "candidate_id": job["candidate_id"],
            "context": context, "public_features": public_features(frame.observation),
            "result": outcome,
        }
    except Exception as error:
        return {
            "job_id": job.get("job_id"), "status": "infrastructure_failed", "efficacy": None,
            "infrastructure_failure": {"type": type(error).__name__, "detail": str(error)},
        }


def _valid_shard(path: Path, job_id: str) -> dict[str, Any] | None:
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
        body = dict(row)
        embedded = body.pop("shard_sha256", None)
        return row if row.get("job_id") == job_id and embedded == s1.payload_hash(body) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _run_jobs(root: Path, jobs: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    shards = root / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    retained: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for job in jobs:
        path = shards / f"{job['job_id']}.json"
        valid = _valid_shard(path, job["job_id"]) if path.exists() else None
        if valid is not None:
            retained.append(valid)
        else:
            if path.exists():
                path.replace(path.with_name(f"{path.stem}.corrupt-{s1.file_sha256(path)[:12]}.json"))
            pending.append(job)
    context = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        futures = {pool.submit(_evaluate_job, job): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = {
                    "job_id": job["job_id"], "status": "infrastructure_failed", "efficacy": None,
                    "infrastructure_failure": {"type": "worker", "detail": str(error)},
                }
            body = dict(row)
            body["shard_sha256"] = s1.payload_hash(body)
            s1.atomic_json(shards / f"{job['job_id']}.json", body)
            retained.append(body)
    return sorted(retained, key=lambda row: row["job_id"])


def _paired(outcome: dict[str, Any], control: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(outcome)
    result["paired"] = {
        "margin_delta": (
            result["own_reward"] - result["opponent_reward"]
            - control["own_reward"] + control["opponent_reward"]
        ),
        "own_bank_delta": result["own_bank"] - control["own_bank"],
        "win_delta": int(result["own_reward"] > result["opponent_reward"]) - int(control["own_reward"] > control["opponent_reward"]),
    }
    result["effective_change"] = s1._classify(result, control)
    return result


def _behavior_identity(observed: dict[str, Any], expected: dict[str, Any]) -> bool:
    keys = ("own_reward", "opponent_reward", "own_bank", "opponent_bank")
    return (
        all(observed[key] == expected[key] for key in keys)
        and observed["evidence"]["action_digest"] == expected["evidence"]["action_digest"]
        and observed["evidence"]["receipt_digest"] == expected["evidence"]["receipt_digest"]
        and observed["evidence"]["public_state_digest"] == expected["evidence"]["public_state_digest"]
        and observed["evidence"]["economic_diagnostics"] == expected["evidence"]["economic_diagnostics"]
    )


def _variant_summary(variant: str, jobs: list[dict[str, Any]], rows: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    selected = [job for job in jobs if job["variant"] == variant]
    results: list[tuple[dict[str, Any], dict[str, Any]]] = []
    replay_match: list[bool] = []
    for job in selected:
        row = rows[job["job_id"]]
        authority = evidence[_context_key(job["context"])]
        paired = _paired(row["result"], authority["control"])
        results.append((job, paired))
        if variant == "full_block_reference":
            replay_match.append(_behavior_identity(row["result"], authority["full_reference"]))
    margins = [float(result["paired"]["margin_delta"]) for _job, result in results]
    banks = [float(result["paired"]["own_bank_delta"]) for _job, result in results]
    by_opponent: dict[str, Any] = {}
    for opponent in OPPONENTS:
        values = [
            float(result["paired"]["margin_delta"])
            for job, result in results if job["context"]["opponent"] == opponent
        ]
        by_opponent[opponent] = {
            "contexts": len(values),
            "paired_margin_wdl": [sum(value > 0 for value in values), sum(value == 0 for value in values), sum(value < 0 for value in values)],
            "mean_paired_margin": sum(values) / len(values),
            "median_paired_margin": statistics.median(values),
            "worst_paired_margin": min(values),
        }
    return {
        "variant": variant,
        "candidate_id": selected[0]["candidate_id"],
        "contexts": len(results),
        "complete": len(results) == len(CONSUMED_SEEDS) * len(OPPONENTS) * len(SEATS),
        "effective_contexts": sum(result["effective_change"]["effective"] for _job, result in results),
        "paired_margin_wdl": [sum(value > 0 for value in margins), sum(value == 0 for value in margins), sum(value < 0 for value in margins)],
        "mean_paired_margin": sum(margins) / len(margins),
        "median_paired_margin": statistics.median(margins),
        "mean_own_bank_delta": sum(banks) / len(banks),
        "worst_paired_margin": min(margins),
        "actual_win_delta": sum(int(result["paired"]["win_delta"]) for _job, result in results),
        "by_opponent": by_opponent,
        "exact_formal_replay": all(replay_match) if replay_match else None,
        "efficacy_claim": None,
    }


def run(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    if not 1 <= int(workers) <= WORKER_LIMIT:
        raise ValueError(f"workers must be in 1..{WORKER_LIMIT}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    body = dict(manifest)
    embedded = body.pop("manifest_sha256", None)
    if embedded != s1.payload_hash(body):
        raise RuntimeError("remediation manifest canonical hash mismatch")
    if manifest["implementation_sha256"] != s1.file_sha256(Path(__file__)):
        raise RuntimeError("remediation implementation changed after prepare")
    if s1.RUNNER.assert_engine_current() != manifest["engine_fingerprint"]:
        raise RuntimeError("remediation engine changed after prepare")
    jobs_payload = json.loads((root / "jobs.json").read_text(encoding="utf-8"))
    jobs = jobs_payload["jobs"]
    if jobs_payload["jobs_sha256"] != manifest["jobs_sha256"] or s1.payload_hash(jobs) != manifest["jobs_sha256"]:
        raise RuntimeError("remediation job manifest mismatch")
    evidence_payload = json.loads((root / "formal_evidence.json").read_text(encoding="utf-8"))
    evidence = evidence_payload["evidence"]
    if s1.payload_hash(evidence) != manifest["formal_evidence_sha256"]:
        raise RuntimeError("formal evidence changed after prepare")
    execution = {
        "schema_version": 1, "kind": "e2_s2_boatlee_remediation_execution",
        "run_id": RUN_ID, "workers": int(workers),
        "consumed_seed_diagnostics_executed": True,
        "executed_consumed_seeds": list(CONSUMED_SEEDS),
        "new_formal_fresh_seeds_executed": False,
        "efficacy_claim": None, "later_tier_launched": False,
    }
    execution["execution_sha256"] = s1.payload_hash({key: value for key, value in execution.items() if key != "execution_sha256"})
    s1.atomic_json(root / "execution.json", execution)
    rows = _run_jobs(root / "diagnostics", jobs, int(workers))
    if not all(row.get("status") == "complete" and row.get("result", {}).get("technical_status") == "complete" for row in rows):
        raise RuntimeError("remediation diagnostic jobs incomplete")
    by_id = {row["job_id"]: row for row in rows}
    summaries = {
        variant: _variant_summary(variant, jobs, by_id, evidence)
        for variant in ("full_block_reference", "step_240_only", "step_241_only")
    }
    feature_groups: dict[str, list[str]] = {}
    for job in jobs:
        feature_groups.setdefault(_context_key(job["context"]), []).append(
            s1.payload_hash(by_id[job["job_id"]]["public_features"])
        )
    feature_consistency = all(
        len(values) == 3 and len(set(values)) == 1
        for values in feature_groups.values()
    )
    summary = {
        "schema_version": 1,
        "kind": "e2_s2_boatlee_atomic_ablation_summary",
        "run_id": RUN_ID,
        "manifest_sha256": manifest["manifest_sha256"],
        "contexts": len(evidence), "jobs": len(rows),
        "variants": summaries,
        "public_feature_contexts": len(feature_groups),
        "public_feature_consistency": feature_consistency,
        "all_features_public_allowlist": True,
        "consumed_seed_diagnostics_executed": True,
        "new_formal_fresh_seeds_executed": False,
        "efficacy_claim": None,
        "complete": all(row["complete"] for row in summaries.values()) and feature_consistency,
        "later_tier_launched": False,
    }
    summary["summary_sha256"] = s1.payload_hash({key: value for key, value in summary.items() if key != "summary_sha256"})
    s1.atomic_json(root / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    run_parser.add_argument("--workers", type=int, required=True)
    args = parser.parse_args()
    result = prepare(args.output_root) if args.command == "prepare" else run(args.output_root, args.workers)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))


if __name__ == "__main__":
    main()
