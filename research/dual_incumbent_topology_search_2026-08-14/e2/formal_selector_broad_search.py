"""Large fresh robustness search for the frozen Boatlee public selector."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
import multiprocessing as mp
from pathlib import Path
import subprocess
import sys
from typing import Any

import formal_s1 as s1


HERE = s1.HERE
ROOT = s1.ROOT
RUN_ID = "e2_selector_broad_20260820_v1"
DEFAULT_ROOT = HERE / "artifacts" / "formal" / RUN_ID
SEED_REGISTRY = HERE / "broad_seed_registry_20260820.json"
PRIOR_DECISION = HERE / "selector_confirmation_decision_20260820.json"
PRIOR_ROOT = HERE / "artifacts" / "formal" / "e2_s2_selector_confirmation_20260820_v1"
PRIOR_SUMMARY = PRIOR_ROOT / "summary.json"
PRIOR_PROTOCOL = PRIOR_ROOT / "protocol.json"
PRIMARY_REGISTRY = ROOT / "research" / "public_agents" / "primary_opponents.json"
SOURCE_RUN = HERE / "artifacts" / "remediation" / "e2_s2_boatlee_selector_20260815_v1"
LANE = "boatlee_v16_rc2_market_relay"
OTHER_LANE = "v27_current_meta"
CANDIDATE_ID = "e2boatlee_7f591d609cf14d89e6aa1599"
SOURCE_CANDIDATE = SOURCE_RUN / "inputs" / "candidate" / CANDIDATE_ID / "main.py"
SOURCE_CONTROLS = {
    LANE: SOURCE_RUN / "inputs" / "controls" / LANE / "main.py",
    OTHER_LANE: SOURCE_RUN / "inputs" / "controls" / OTHER_LANE / "main.py",
}
EXPECTED_CANDIDATE_SHA256 = "b4ef9bff8cbba2dfaccacc320a32f707006158fcf905c02db02ad89fe0f6099a"
EXPECTED_CONTROL_SHA256 = "69ce4f657df5a168c676acfa4f9089a373bc291fe3486950de0bca16ad042213"
SEATS = (0, 1)
WORKERS = 14
LOGICAL_PROCESSORS = 18
WORKER_LIMIT = 15


def _package(entrypoint: Path, files: tuple[str, ...] = ("main.py",)) -> dict[str, Any]:
    return {"entrypoint": entrypoint, "files": files}


PUBLIC = ROOT / "research" / "public_agents"
LEGACY = SOURCE_RUN / "inputs" / "opponents"
SOURCE_PACKAGES: dict[str, dict[str, Any]] = {
    "guarded_v27": _package(ROOT / "research" / "main_approach" / "v27_current_meta_safety_guarded" / "main.py"),
    "kaito_v21": _package(LEGACY / "kaito_v21" / "main.py"),
    "roman_lb950": _package(LEGACY / "roman_lb950" / "main.py"),
    "saiteja_3000": _package(
        LEGACY / "saiteja_3000" / "main.py",
        ("main.py", "agent_frontier.py", "agent_moon.py", "agent_v14.py", "agent_hamburger.py"),
    ),
    "lb01_boatlee_rc5": _package(PUBLIC / "lb20260816_01_boatlee_v16_rc5" / "extracted" / "main.py"),
    "lb02_kaito_v25": _package(PUBLIC / "lb20260816_02_kaito_v25" / "extracted" / "main.py"),
    "lb04_rayk_c95": _package(PUBLIC / "lb20260816_04_rayk_zero_to_top" / "extracted" / "main.py"),
    "lb05_boatlee_rc5_r5a": _package(PUBLIC / "lb20260816_05_boatlee_v16_rc5_r5a" / "extracted" / "main.py"),
    "lb06_boatlee_v14": _package(PUBLIC / "lb20260816_06_boatlee_v14_clone_preemption" / "extracted" / "main.py"),
    "lb07_kunal_ttv1": _package(PUBLIC / "lb20260816_07_kunal_ttv1" / "extracted" / "main.py"),
    "lb09_bruce_pipeline": _package(PUBLIC / "lb20260816_09_bruce_high_score_pipeline" / "extracted" / "main.py"),
    "lb10_prvsiyan_soil": _package(PUBLIC / "lb20260816_10_prvsiyan_soil" / "extracted" / "main.py"),
}
OPPONENTS = ("other_incumbent", *SOURCE_PACKAGES.keys())


def _seed_records() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    registry = json.loads(SEED_REGISTRY.read_text(encoding="utf-8"))
    values = [int(value) for value in registry.get("seeds", [])]
    rejected = {int(value) for value in registry.get("rejected_collisions", [])}
    if len(values) != 256 or len(set(values)) != 256 or registry.get("seed_count") != 256:
        raise RuntimeError("broad search requires exactly 256 unique seeds")
    if set(values) & rejected:
        raise RuntimeError("rejected seed collision entered broad search")
    records = [
        {
            "seed": value, "classification": "formal_fresh", "fresh": True,
            "purpose": "e2_boatlee_selector_broad_robustness",
            "selection_index": index, "preselection_repository_hits": 0,
            "executed": False,
        }
        for index, value in enumerate(values)
    ]
    return records, registry


def _freshness_scan(registry: dict[str, Any], output_root: Path) -> dict[str, Any]:
    values = [str(int(value)) for value in registry["seeds"]]
    pattern = "|".join(values)
    excluded = {SEED_REGISTRY.resolve()}
    if output_root.exists():
        excluded.update(path.resolve() for path in output_root.rglob("*") if path.is_file())
    hits: list[str] = []
    scanned = []
    for raw_root in registry["freshness_scan_roots"]:
        scan_root = Path(raw_root)
        if not scan_root.exists():
            continue
        scanned.append(str(scan_root.resolve()))
        completed = subprocess.run(
            ["rg", "-uu", "-l", "-e", pattern, str(scan_root)],
            capture_output=True, text=True,
        )
        if completed.returncode not in (0, 1):
            raise RuntimeError(f"freshness scan failed for {scan_root}: {completed.returncode}")
        for value in completed.stdout.splitlines():
            path = Path(value).resolve()
            if path not in excluded:
                hits.append(str(path))
    return {
        "pass": not hits, "seed_count": len(values), "scan_roots": scanned,
        "unexpected_hit_files": sorted(set(hits)),
        "method": "single-pass exact-alternation ripgrep over all 256 seed strings",
    }


def _prior_authority() -> dict[str, Any]:
    decision = json.loads(PRIOR_DECISION.read_text(encoding="utf-8"))
    summary = json.loads(PRIOR_SUMMARY.read_text(encoding="utf-8"))
    protocol = json.loads(PRIOR_PROTOCOL.read_text(encoding="utf-8"))
    summary_canonical, summary_ok = s1._canonical_file(PRIOR_SUMMARY, "summary_sha256")
    protocol_canonical, protocol_ok = s1._canonical_file(PRIOR_PROTOCOL, "protocol_sha256")
    checks = {
        "decision": decision.get("decision") == "PASS_MINIMUM_FRESH_CONFIRMATION_ADVANCE_TO_BROAD_ROBUSTNESS",
        "candidate": decision.get("candidate_id") == CANDIDATE_ID,
        "summary_canonical": summary_ok and summary_canonical == summary.get("summary_sha256"),
        "protocol_canonical": protocol_ok and protocol_canonical == protocol.get("protocol_sha256"),
        "source_hashes": (
            decision.get("source_summary_file_sha256") == s1.file_sha256(PRIOR_SUMMARY)
            and decision.get("source_summary_canonical_sha256") == summary_canonical
            and decision.get("source_protocol_file_sha256") == s1.file_sha256(PRIOR_PROTOCOL)
        ),
        "complete": summary.get("complete") is True,
        "fresh": summary.get("formal_fresh_seeds_executed") is True,
        "wdl": summary.get("result", {}).get("paired_margin_wdl") == [12, 4, 0],
        "no_tail": summary.get("result", {}).get("tail_falsifier_triggered") is False,
        "broad_authorized": decision.get("broad_robustness_search_authorized") is True,
        "not_promoted": decision.get("promotion_authorized") is False,
        "no_later_tier": summary.get("later_tier_launched") is False,
    }
    return {
        "pass": all(checks.values()), "checks": checks,
        "decision_file_sha256": s1.file_sha256(PRIOR_DECISION),
        "summary_file_sha256": s1.file_sha256(PRIOR_SUMMARY),
        "summary_canonical_sha256": summary_canonical,
        "protocol_file_sha256": s1.file_sha256(PRIOR_PROTOCOL),
        "protocol_canonical_sha256": protocol_canonical,
    }


def _frozen_paths(root: Path) -> dict[str, Any]:
    return {
        "controls": {
            lane: root / "inputs" / "controls" / lane / "main.py"
            for lane in (LANE, OTHER_LANE)
        },
        "candidate": root / "inputs" / "candidate" / CANDIDATE_ID / "main.py",
        "opponents": {
            family: root / "inputs" / "opponents" / family / "main.py"
            for family in SOURCE_PACKAGES
        },
    }


def _frozen_opponent_path(root: Path, family: str) -> Path:
    frozen = _frozen_paths(root)
    if family == "other_incumbent":
        return frozen["controls"][OTHER_LANE]
    if family in frozen["opponents"]:
        return frozen["opponents"][family]
    raise KeyError(family)


def _copy_inputs(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    frozen = _frozen_paths(root)
    copied: dict[str, Any] = {
        "controls": {
            lane: s1._copy_exact(SOURCE_CONTROLS[lane], frozen["controls"][lane])
            for lane in (LANE, OTHER_LANE)
        },
        "candidate": s1._copy_exact(SOURCE_CANDIDATE, frozen["candidate"]),
        "opponents": {},
    }
    copied["opponents"]["other_incumbent"] = {
        "entrypoint": str(frozen["controls"][OTHER_LANE]),
        "files": {"main.py": copied["controls"][OTHER_LANE]},
        "package_sha256": s1.payload_hash({"main.py": copied["controls"][OTHER_LANE]}),
    }
    for family, package in SOURCE_PACKAGES.items():
        source_dir = Path(package["entrypoint"]).parent
        target_dir = frozen["opponents"][family].parent
        files = {
            name: s1._copy_exact(source_dir / name, target_dir / name)
            for name in package["files"]
        }
        copied["opponents"][family] = {
            "entrypoint": str(frozen["opponents"][family]),
            "files": files, "package_sha256": s1.payload_hash(files),
        }
    return frozen, copied


def _import_worker(task: dict[str, str]) -> dict[str, Any]:
    try:
        _module, agent, _latency = s1.RUNNER.harness.load_agent(
            Path(task["path"]), f"broad_spawn_{task['family']}",
        )
        return {"family": task["family"], "callable_agent": callable(agent), "pass": callable(agent)}
    except BaseException as error:
        return {"family": task["family"], "callable_agent": False, "pass": False, "error": f"{type(error).__name__}: {error}"}


def _import_smoke(root: Path, workers: int) -> dict[str, Any]:
    tasks = [
        {"family": family, "path": str(_frozen_opponent_path(root, family))}
        for family in OPPONENTS
    ]
    direct = []
    for task in tasks:
        direct.append(_import_worker(task))
    context = mp.get_context("spawn")
    spawned: list[dict[str, Any]] = []
    try:
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            spawned = [future.result() for future in [pool.submit(_import_worker, task) for task in tasks]]
    except BaseException as error:
        return {"pass": False, "direct": direct, "spawned": spawned, "pool_error": f"{type(error).__name__}: {error}"}
    return {
        "pass": all(row["pass"] for row in direct + spawned),
        "direct": direct, "spawned": spawned, "workers": workers,
    }


def _jobs(root: Path, records: list[dict[str, Any]], frozen: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    controls: list[dict[str, Any]] = []
    for opponent in OPPONENTS:
        for seed_record in records:
            for seat in SEATS:
                job = {
                    "kind": "control", "evaluation_mode": "e2_s1_formal_exact",
                    "context": {"lane": LANE, "opponent": opponent, "seed": int(seed_record["seed"]), "seat": seat},
                    "seed_record": seed_record,
                    "artifact": {"path": str(frozen["controls"][LANE]), "sha256": s1.file_sha256(frozen["controls"][LANE])},
                }
                job["job_id"] = s1.canonical_job_id(job)
                controls.append(job)
    control_by_context = {
        (row["context"]["opponent"], row["context"]["seed"], row["context"]["seat"]): row["job_id"]
        for row in controls
    }
    candidates: list[dict[str, Any]] = []
    for opponent in OPPONENTS:
        for seed_record in records:
            for seat in SEATS:
                context = {"lane": LANE, "opponent": opponent, "seed": int(seed_record["seed"]), "seat": seat}
                control_id = control_by_context[(opponent, int(seed_record["seed"]), seat)]
                job = {
                    "kind": "candidate", "evaluation_mode": "e2_s1_formal_exact",
                    "candidate_id": CANDIDATE_ID, "context": context,
                    "seed_record": seed_record,
                    "artifact": {"path": str(frozen["candidate"]), "sha256": s1.file_sha256(frozen["candidate"])},
                    "control_job_id": control_id,
                    "control_cache_path": str(root / "control_cache" / f"{control_id}.json"),
                }
                job["job_id"] = s1.canonical_job_id(job)
                candidates.append(job)
    return sorted(controls, key=lambda row: row["job_id"]), sorted(candidates, key=lambda row: row["job_id"])


def preflight(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    if workers != WORKERS or not 1 <= workers <= WORKER_LIMIT:
        raise ValueError(f"broad search workers are frozen at {WORKERS}")
    if root.exists():
        raise FileExistsError(f"new broad-search root required: {root}")
    authority = _prior_authority()
    if not authority["pass"]:
        raise RuntimeError(f"prior confirmation authority failed: {authority}")
    records, registry = _seed_records()
    scan = _freshness_scan(registry, root)
    if not scan["pass"]:
        raise RuntimeError(f"selected broad-search seed is not fresh: {scan}")
    engine = s1.RUNNER.assert_engine_current()
    if s1.file_sha256(SOURCE_CANDIDATE) != EXPECTED_CANDIDATE_SHA256:
        raise RuntimeError("frozen selector bytes drifted")
    if s1.file_sha256(SOURCE_CONTROLS[LANE]) != EXPECTED_CONTROL_SHA256:
        raise RuntimeError("frozen Boatlee control bytes drifted")
    root.mkdir(parents=True)
    frozen, copied = _copy_inputs(root)
    smoke = _import_smoke(root, workers)
    if not smoke["pass"]:
        raise RuntimeError(f"opponent import smoke failed: {smoke}")
    unique_opponents = {row["files"]["main.py"]["sha256"] for row in copied["opponents"].values()}
    if len(unique_opponents) != len(OPPONENTS):
        raise RuntimeError("broad opponent families contain an exact duplicate artifact")
    controls, candidates = _jobs(root, records, frozen)
    expected = len(OPPONENTS) * len(records) * len(SEATS)
    if len(controls) != expected or len(candidates) != expected:
        raise RuntimeError("unexpected broad-search job count")
    protocol: dict[str, Any] = {
        "schema_version": 1, "kind": "e2_boatlee_selector_broad_fresh_protocol",
        "status": "frozen_authorized_broad_search", "formal_authorized": True,
        "authorization": "User explicitly instructed on 2026-08-20: 直接進行一次全面的搜尋，能多大就多大，cpu 約使用 70-85%",
        "run_id": RUN_ID, "run_root": str(root), "workers": workers,
        "logical_processors": LOGICAL_PROCESSORS, "worker_ratio": workers / LOGICAL_PROCESSORS,
        "formal_fresh_seeds_executed": False,
        "evaluation_seeds": [int(row["seed"]) for row in records],
        "seats": list(SEATS), "opponents": list(OPPONENTS),
        "lane": LANE, "candidate_id": CANDIDATE_ID,
        "candidate_mutation": None, "pool_with_v27": False,
        "seed_registry": {"path": str(SEED_REGISTRY), "sha256": s1.file_sha256(SEED_REGISTRY), "records": records},
        "freshness_scan": scan, "prior_authority": authority,
        "engine_fingerprint": engine,
        "control_artifacts": copied["controls"], "candidate_artifact": copied["candidate"],
        "opponent_artifacts": copied["opponents"], "opponent_import_smoke": smoke,
        "primary_opponent_registry_sha256": s1.file_sha256(PRIMARY_REGISTRY),
        "job_counts": {"controls": expected, "candidates": expected, "paired_contexts": expected, "total_games": expected * 2},
        "decision_contract": {
            "minimum_independent_seeds": 256,
            "minimum_opponent_families": len(OPPONENTS),
            "both_seats_required": True,
            "technical_gate": "all retained subject games DONE/DONE; zero subject exception, timeout, malformed action, overage exhaustion, seed overcommit, or market overflow",
            "reporting": ["paired_margin_wdl", "actual_win_delta", "mean_and_worst_margin", "own_bank_delta", "family", "seat", "seed", "seed_family_cluster", "negative_contexts", "latency"],
            "promotion_falsifier": "any renewed Roman negative context or repeatable family-and-seat negative tail blocks promotion",
            "positive_rule": "positive seed-family clusters must exceed negative clusters and the two-sided 95% Wilson lower bound among nonzero clusters must exceed 0.5",
            "family_rule": "no opponent family may have negative mean paired margin",
            "automatic_promotion": False,
            "automatic_later_tier": False,
        },
        "implementation_hashes": {"formal_selector_broad_search.py": s1.file_sha256(Path(__file__)), "formal_s1.py": s1.file_sha256(HERE / "formal_s1.py")},
        "later_tier_launched": False,
    }
    protocol["job_manifest_sha256"] = s1.payload_hash({"controls": controls, "candidates": candidates})
    protocol["protocol_sha256"] = s1.payload_hash({key: value for key, value in protocol.items() if key != "protocol_sha256"})
    manifest: dict[str, Any] = {
        "schema_version": 1, "kind": "e2_boatlee_selector_broad_fresh_manifest",
        "run_id": RUN_ID, "run_root": str(root),
        "protocol_sha256": protocol["protocol_sha256"],
        "engine_sha256": s1.payload_hash(engine),
        "seed_registry_sha256": s1.file_sha256(SEED_REGISTRY),
        "jobs_sha256": protocol["job_manifest_sha256"],
        "control_jobs": controls, "candidate_jobs": candidates,
        "formal_fresh_seeds_executed": False, "later_tier_launched": False,
    }
    manifest["manifest_sha256"] = s1.payload_hash({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    s1.atomic_json(root / "protocol.json", protocol)
    s1.atomic_json(root / "manifest.json", manifest)
    s1.atomic_json(root / "jobs" / "controls.json", {"manifest_sha256": manifest["manifest_sha256"], "jobs": controls, "job_manifest_sha256": s1.payload_hash(controls)})
    s1.atomic_json(root / "jobs" / "candidates.json", {"manifest_sha256": manifest["manifest_sha256"], "jobs": candidates, "job_manifest_sha256": s1.payload_hash(candidates)})
    dry = {
        "schema_version": 1, "kind": "e2_boatlee_selector_broad_dry_preflight",
        "run_id": RUN_ID, "pass": True, "formal_authorized": True,
        "formal_fresh_seeds_executed": False,
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "registry_sha256": s1.file_sha256(SEED_REGISTRY),
        "seed_count": len(records), "opponent_family_count": len(OPPONENTS),
        "job_counts": protocol["job_counts"], "workers": workers,
        "logical_processors": LOGICAL_PROCESSORS, "worker_ratio": workers / LOGICAL_PROCESSORS,
        "freshness_scan": scan, "opponent_import_smoke_pass": smoke["pass"],
    }
    dry["dry_preflight_sha256"] = s1.payload_hash({key: value for key, value in dry.items() if key != "dry_preflight_sha256"})
    s1.atomic_json(root / "dry_preflight.json", dry)
    return dry


def _load_frozen(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    protocol_body = {key: value for key, value in protocol.items() if key != "protocol_sha256"}
    if manifest.get("manifest_sha256") != s1.payload_hash(manifest_body):
        raise RuntimeError("broad manifest canonical hash mismatch")
    if protocol.get("protocol_sha256") != s1.payload_hash(protocol_body):
        raise RuntimeError("broad protocol canonical hash mismatch")
    if manifest.get("protocol_sha256") != protocol.get("protocol_sha256"):
        raise RuntimeError("broad manifest/protocol identity mismatch")
    if protocol.get("formal_authorized") is not True or protocol.get("status") != "frozen_authorized_broad_search":
        raise PermissionError("broad protocol is not explicitly authorized")
    expected = s1.payload_hash({"controls": manifest["control_jobs"], "candidates": manifest["candidate_jobs"]})
    if protocol.get("job_manifest_sha256") != expected:
        raise RuntimeError("broad job manifest hash mismatch")
    return manifest, protocol


def validate_preflight(root: Path) -> dict[str, Any]:
    manifest, protocol = _load_frozen(root.resolve())
    jobs = manifest["control_jobs"] + manifest["candidate_jobs"]
    expected = 256 * len(OPPONENTS) * len(SEATS)
    checks = {
        "run_id": manifest["run_id"] == RUN_ID == protocol["run_id"],
        "workers": protocol["workers"] == WORKERS and 0.70 <= protocol["worker_ratio"] <= 0.85,
        "seeds": len(protocol["evaluation_seeds"]) == 256 and len(set(protocol["evaluation_seeds"])) == 256,
        "families": len(protocol["opponents"]) == len(OPPONENTS) and set(protocol["opponents"]) == set(OPPONENTS),
        "jobs": len(manifest["control_jobs"]) == expected and len(manifest["candidate_jobs"]) == expected,
        "both_seats": {row["context"]["seat"] for row in jobs} == {0, 1},
        "lane_isolated": all(row["context"]["lane"] == LANE for row in jobs),
        "artifacts": all(s1.file_sha256(Path(row["artifact"]["path"])) == row["artifact"]["sha256"] for row in jobs),
        "candidate": protocol["candidate_artifact"]["sha256"] == EXPECTED_CANDIDATE_SHA256,
        "control": protocol["control_artifacts"][LANE]["sha256"] == EXPECTED_CONTROL_SHA256,
        "opponents": all(s1.file_sha256(Path(file_row["path"])) == file_row["sha256"] for package in protocol["opponent_artifacts"].values() for file_row in package["files"].values()),
        "imports": protocol["opponent_import_smoke"]["pass"] is True,
        "seed_registry": s1.file_sha256(SEED_REGISTRY) == protocol["seed_registry"]["sha256"],
        "prior_decision": s1.file_sha256(PRIOR_DECISION) == protocol["prior_authority"]["decision_file_sha256"],
        "engine": s1.RUNNER.assert_engine_current() == protocol["engine_fingerprint"],
        "implementation": s1.file_sha256(Path(__file__)) == protocol["implementation_hashes"]["formal_selector_broad_search.py"] and s1.file_sha256(HERE / "formal_s1.py") == protocol["implementation_hashes"]["formal_s1.py"],
        "not_executed": manifest["formal_fresh_seeds_executed"] is False and protocol["formal_fresh_seeds_executed"] is False,
    }
    return {
        "pass": all(checks.values()), "checks": checks,
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "job_counts": protocol["job_counts"],
        "formal_fresh_seeds_executed": False,
    }


def _evaluate_job(job: dict[str, Any]) -> dict[str, Any]:
    old = s1._opponent_path
    s1._opponent_path = lambda root, lane, family: _frozen_opponent_path(root, family)
    try:
        return s1._evaluate_job(job)
    finally:
        s1._opponent_path = old


def _run_jobs(root: Path, jobs: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    shards = root / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    retained: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for original in jobs:
        job = {**original, "run_root": str(root.parents[1].resolve())}
        path = shards / f"{job['job_id']}.json"
        if path.exists():
            valid = s1._valid_shard(path, job["job_id"])
            if valid is not None:
                retained.append(valid)
                continue
            preserved = path.with_name(f"{path.stem}.corrupt-{s1.file_sha256(path)[:12]}.json")
            path.replace(preserved)
        pending.append(job)
    context = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        futures = {pool.submit(_evaluate_job, job): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                row = future.result()
            except BaseException as error:
                row = {"job_id": job["job_id"], "status": "infrastructure_failed", "efficacy": None, "infrastructure_failure": {"type": "worker", "detail": str(error)}}
            body = dict(row)
            body["shard_sha256"] = s1.payload_hash(body)
            s1.atomic_json(shards / f"{row['job_id']}.json", body)
            retained.append(body)
    return sorted(retained, key=lambda row: row["job_id"])


def _wilson(positive: int, total: int) -> list[float]:
    if total <= 0:
        return [0.0, 1.0]
    z = 1.959963984540054
    phat = positive / total
    center = (phat + z * z / (2 * total)) / (1 + z * z / total)
    radius = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [center - radius, center + radius]


def _group(contexts: list[dict[str, Any]], field: str) -> dict[str, Any]:
    result = {}
    for value in sorted({row[field] for row in contexts}, key=str):
        rows = [row for row in contexts if row[field] == value]
        margins = [float(row["margin_delta"]) for row in rows]
        result[str(value)] = {
            "contexts": len(rows),
            "paired_margin_wdl": [sum(v > 0 for v in margins), sum(v == 0 for v in margins), sum(v < 0 for v in margins)],
            "mean_paired_margin": sum(margins) / len(margins),
            "worst_paired_margin": min(margins),
            "mean_own_bank_delta": sum(float(row["own_bank_delta"]) for row in rows) / len(rows),
            "actual_win_delta": sum(int(row["win_delta"]) for row in rows),
            "effective_contexts": sum(bool(row["effective"]) for row in rows),
        }
    return result


def _summary(jobs: list[dict[str, Any]], rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    contexts: list[dict[str, Any]] = []
    for job in jobs:
        row = rows[job["job_id"]]["result"]
        paired = row["paired"]
        contexts.append({
            "job_id": job["job_id"], "opponent": job["context"]["opponent"],
            "seed": job["context"]["seed"], "seat": job["context"]["seat"],
            "margin_delta": float(paired["margin_delta"]),
            "own_bank_delta": float(paired["own_bank_delta"]),
            "win_delta": int(paired["win_delta"]),
            "effective": bool(row["effective_change"]["effective"]),
            "p95_ms": float(row["summary"]["latency_ms"]["p95"]),
            "max_ms": float(row["summary"]["latency_ms"]["max"]),
        })
    margins = [row["margin_delta"] for row in contexts]
    clusters = []
    for opponent in OPPONENTS:
        for seed in sorted({row["seed"] for row in contexts}):
            rows_for_cluster = [row for row in contexts if row["opponent"] == opponent and row["seed"] == seed]
            cluster_margin = sum(row["margin_delta"] for row in rows_for_cluster) / len(rows_for_cluster)
            clusters.append({"opponent": opponent, "seed": seed, "mean_margin": cluster_margin})
    cluster_positive = sum(row["mean_margin"] > 0 for row in clusters)
    cluster_negative = sum(row["mean_margin"] < 0 for row in clusters)
    cluster_nonzero = cluster_positive + cluster_negative
    family = _group(contexts, "opponent")
    roman_negative = [row for row in contexts if row["opponent"] == "roman_lb950" and row["margin_delta"] < 0]
    negative = sorted((row for row in contexts if row["margin_delta"] < 0), key=lambda row: row["margin_delta"])
    repeated_seat_tail = []
    for opponent in OPPONENTS:
        for seat in SEATS:
            rows_for_stratum = [row for row in contexts if row["opponent"] == opponent and row["seat"] == seat]
            negatives = [row for row in rows_for_stratum if row["margin_delta"] < 0]
            if len({row["seed"] for row in negatives}) >= 2:
                repeated_seat_tail.append({"opponent": opponent, "seat": seat, "negative_seeds": sorted({row["seed"] for row in negatives}), "negative_contexts": len(negatives)})
    lower = _wilson(cluster_positive, cluster_nonzero)
    promotion_falsified = bool(roman_negative or repeated_seat_tail or any(row["mean_paired_margin"] < 0 for row in family.values()) or lower[0] <= 0.5)
    return {
        "contexts": len(contexts),
        "paired_margin_wdl": [sum(v > 0 for v in margins), sum(v == 0 for v in margins), sum(v < 0 for v in margins)],
        "mean_paired_margin": sum(margins) / len(margins),
        "worst_paired_margin": min(margins),
        "mean_own_bank_delta": sum(row["own_bank_delta"] for row in contexts) / len(contexts),
        "actual_win_delta": sum(row["win_delta"] for row in contexts),
        "effective_contexts": sum(row["effective"] for row in contexts),
        "seed_family_clusters": len(clusters),
        "cluster_margin_wdl": [cluster_positive, len(clusters) - cluster_nonzero, cluster_negative],
        "cluster_positive_wilson_95": lower,
        "by_family": family, "by_seat": _group(contexts, "seat"),
        "by_seed": _group(contexts, "seed"),
        "roman_negative_contexts": roman_negative,
        "repeated_family_seat_negative_tails": repeated_seat_tail,
        "negative_context_count": len(negative), "negative_contexts": negative,
        "maximum_candidate_p95_ms": max(row["p95_ms"] for row in contexts),
        "maximum_candidate_call_ms": max(row["max_ms"] for row in contexts),
        "promotion_falsified": promotion_falsified,
        "automatic_promotion": False, "automatic_later_tier": False,
    }


def run(root: Path, workers: int, execute_broad: bool) -> dict[str, Any]:
    root = root.resolve()
    if not execute_broad:
        raise PermissionError("formal broad search requires --execute-broad")
    manifest, protocol = _load_frozen(root)
    validation = validate_preflight(root)
    if not validation["pass"]:
        raise RuntimeError(f"frozen broad preflight failed: {validation}")
    if workers != int(protocol["workers"]):
        raise RuntimeError("worker count differs from frozen broad protocol")
    execution = {
        "schema_version": 1, "kind": "e2_boatlee_selector_broad_execution",
        "run_id": RUN_ID, "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "formal_fresh_seeds_executed": True,
        "executed_formal_seeds": protocol["evaluation_seeds"],
        "candidate_id": CANDIDATE_ID, "workers": workers,
        "later_tier_launched": False,
    }
    execution["execution_sha256"] = s1.payload_hash({key: value for key, value in execution.items() if key != "execution_sha256"})
    s1.atomic_json(root / "execution.json", execution)
    control_rows = _run_jobs(root / "formal" / "controls", manifest["control_jobs"], workers)
    if not all(row.get("status") == "complete" and row.get("result", {}).get("technical_status") == "complete" for row in control_rows):
        raise RuntimeError("broad control phase incomplete; candidate phase not launched")
    cache_dir = root / "control_cache"
    for row in control_rows:
        s1.atomic_json(cache_dir / f"{row['job_id']}.json", {row["job_id"]: row["result"]})
    candidate_rows = _run_jobs(root / "formal" / "candidates", manifest["candidate_jobs"], workers)
    by_id = {row["job_id"]: row for row in candidate_rows}
    complete = all(
        by_id.get(job["job_id"], {}).get("status") == "complete"
        and by_id[job["job_id"]].get("result", {}).get("technical_status") == "complete"
        for job in manifest["candidate_jobs"]
    )
    result = _summary(manifest["candidate_jobs"], by_id) if complete else None
    summary = {
        "schema_version": 1, "kind": "e2_boatlee_selector_broad_fresh_summary",
        "run_id": RUN_ID, "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "formal_fresh_seeds_executed": True,
        "executed_formal_seed_count": len(protocol["evaluation_seeds"]),
        "control_contexts": len(control_rows), "candidate_contexts": len(candidate_rows),
        "complete": complete, "result": result,
        "decision_written": False, "later_tier_launched": False,
    }
    summary["summary_sha256"] = s1.payload_hash({key: value for key, value in summary.items() if key != "summary_sha256"})
    s1.atomic_json(root / "summary.json", summary)
    checkpoint = {
        "schema_version": 1, "run_id": RUN_ID,
        "manifest_sha256": manifest["manifest_sha256"],
        "control_shards": len(control_rows), "candidate_shards": len(candidate_rows),
        "complete": complete, "summary_sha256": summary["summary_sha256"],
        "formal_fresh_seeds_executed": True, "later_tier_launched": False,
    }
    checkpoint["checkpoint_sha256"] = s1.payload_hash({key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"})
    s1.atomic_json(root / "checkpoint.json", checkpoint)
    return summary


def launch(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    validation = validate_preflight(root)
    if not validation["pass"]:
        raise RuntimeError(f"broad dry preflight failed: {validation}")
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    if workers != int(protocol["workers"]):
        raise RuntimeError("launch worker count differs from frozen broad protocol")
    stdout_path = root / "logs" / "stdout.log"
    stderr_path = root / "logs" / "stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), "run", "--output-root", str(root), "--workers", str(workers), "--execute-broad"]
    creationflags = 0
    for name in ("CREATE_NO_WINDOW", "CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS"):
        creationflags |= int(getattr(subprocess, name, 0))
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, close_fds=True, creationflags=creationflags)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    record = {
        "schema_version": 1, "kind": "e2_boatlee_selector_broad_launch",
        "run_id": RUN_ID, "pid": int(process.pid), "command": command,
        "workers": workers, "logical_processors": LOGICAL_PROCESSORS,
        "worker_ratio": workers / LOGICAL_PROCESSORS,
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"],
        "registry_sha256": protocol["seed_registry"]["sha256"],
        "stdout": str(stdout_path), "stderr": str(stderr_path),
        "control_shards": str(root / "formal" / "controls" / "shards"),
        "candidate_shards": str(root / "formal" / "candidates" / "shards"),
        "execution_launched": True, "completion_audited": False,
        "formal_fresh_seeds_executed": False, "later_tier_launched": False,
    }
    record["launch_sha256"] = s1.payload_hash({key: value for key, value in record.items() if key != "launch_sha256"})
    s1.atomic_json(root / "launch.json", record)
    return record


def status(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest, protocol = _load_frozen(root)
    phases = {}
    for phase, key in (("controls", "control_jobs"), ("candidates", "candidate_jobs")):
        shard_dir = root / "formal" / phase / "shards"
        valid = 0
        failed = 0
        for job in manifest[key]:
            path = shard_dir / f"{job['job_id']}.json"
            row = s1._valid_shard(path, job["job_id"]) if path.exists() else None
            valid += int(row is not None)
            failed += int(bool(row and row.get("status") != "complete"))
        phases[phase] = {"expected": len(manifest[key]), "valid_shards": valid, "failed_shards": failed}
    return {
        "run_id": RUN_ID, "workers": protocol["workers"],
        "phases": phases, "execution_exists": (root / "execution.json").exists(),
        "summary_exists": (root / "summary.json").exists(),
        "checkpoint_exists": (root / "checkpoint.json").exists(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "validate", "launch", "run", "status"):
        command = commands.add_parser(name)
        command.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
        if name in {"preflight", "launch", "run"}:
            command.add_argument("--workers", type=int, required=True)
        if name == "run":
            command.add_argument("--execute-broad", action="store_true")
    args = parser.parse_args()
    if args.command == "preflight":
        result = preflight(args.output_root, args.workers)
    elif args.command == "validate":
        result = validate_preflight(args.output_root)
    elif args.command == "launch":
        result = launch(args.output_root, args.workers)
    elif args.command == "run":
        result = run(args.output_root, args.workers, args.execute_broad)
    else:
        result = status(args.output_root)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))


if __name__ == "__main__":
    main()
