"""Frozen, lane-isolated E2 S1 preflight, launcher, and exact worker."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import copy
import hashlib
import importlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from authority import HERE, ROOT, file_sha256, payload_hash, verify_authority


V3 = HERE.parent / "async_v3"
if str(V3) not in sys.path:
    sys.path.insert(0, str(V3))
from scheduler import atomic_json, canonical_job_id  # noqa: E402


RUN_ID = "e2_s1_20260815_fresh_v4"
DEFAULT_ROOT = HERE / "artifacts" / "formal" / RUN_ID
PRIOR_FAILED_RUN = HERE / "artifacts" / "formal" / "e2_s1_20260815_fresh_v2"
SUPERSEDED_PREFLIGHT_RUN = HERE / "artifacts" / "formal" / "e2_s1_20260815_fresh_v3"
SEED_REGISTRY = HERE / "s1_seed_registry_20260815.json"
PROTOCOL_TEMPLATE = HERE / "protocol_template.json"
DEVELOPMENT_REGISTRY = HERE / "development_candidate_registry.json"
DEVELOPMENT_VERIFICATION = (
    HERE / "artifacts" / "development" / "e2_development_20260815_v3"
    / "development_verification.json"
)
DEVELOPMENT_RUN = DEVELOPMENT_VERIFICATION.parent
OPPONENTS = ("kaito_v21", "other_incumbent", "roman_lb950", "saiteja_3000")
SEATS = (0, 1)
WORKER_LIMIT = 15
LANES = ("boatlee_v16_rc2_market_relay", "v27_current_meta")
EXPECTED_CANDIDATES = {
    "boatlee_v16_rc2_market_relay": "ac_3aa759d7d7fc4a409c409326",
    "v27_current_meta": "e2v27_8b3ebcb128a4f4709ea94ce3",
}
SOURCE_CONTROLS = {
    "boatlee_v16_rc2_market_relay": ROOT / "research" / "main_approach" / "boatlee_v16_rc2_market_relay" / "main.py",
    "v27_current_meta": ROOT / "research" / "main_approach" / "v27_current_meta" / "main.py",
}
SOURCE_ROUTES = {
    lane: path.parent / "development" / "route_actions.json"
    for lane, path in SOURCE_CONTROLS.items()
}
SOURCE_CANDIDATES = {
    "boatlee_v16_rc2_market_relay": DEVELOPMENT_RUN / "registered" / "boatlee_v16_rc2_market_relay" / EXPECTED_CANDIDATES["boatlee_v16_rc2_market_relay"] / "main.py",
    "v27_current_meta": DEVELOPMENT_RUN / "selectors" / EXPECTED_CANDIDATES["v27_current_meta"] / "main.py",
}
SOURCE_PUBLIC_OPPONENTS = {
    "kaito_v21": ROOT / "research" / "public_agents" / "kaito_v21_top30" / "extracted" / "main.py",
    "roman_lb950": ROOT / "research" / "public_agents" / "roman_lb950" / "extracted" / "main.py",
    "saiteja_3000": ROOT / "research" / "public_agents" / "saiteja_mega_ensemble_3000" / "extracted" / "main.py",
}
PUBLIC_OPPONENT_FILES = {
    "kaito_v21": ("main.py",),
    "roman_lb950": ("main.py",),
    "saiteja_3000": (
        "main.py", "agent_frontier.py", "agent_moon.py", "agent_v14.py",
        "agent_hamburger.py",
    ),
}


def _load_runner() -> Any:
    path = ROOT / "research" / "job_value_residual_2026-08-12"
    old_path = list(sys.path)
    prior_protocol = sys.modules.pop("protocol", None)
    prior_runner = sys.modules.pop("engine_runner", None)
    try:
        sys.path.insert(0, str(path))
        return importlib.import_module("engine_runner")
    finally:
        sys.path[:] = old_path
        if prior_protocol is not None:
            sys.modules["protocol"] = prior_protocol
        if prior_runner is not None:
            sys.modules["engine_runner"] = prior_runner


RUNNER = _load_runner()


def _canonical_file(path: Path, field: str) -> tuple[str, bool]:
    row = json.loads(path.read_text(encoding="utf-8"))
    body = dict(row)
    embedded = body.pop(field, None)
    observed = payload_hash(body)
    return observed, embedded == observed


def _copy_exact(source: Path, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if file_sha256(source) != file_sha256(target):
        raise RuntimeError(f"frozen copy mismatch: {source}")
    return {"path": str(target), "sha256": file_sha256(target), "bytes": target.stat().st_size}


def _freshness_scan(seed_registry: dict[str, Any], output_root: Path) -> dict[str, Any]:
    excluded = {SEED_REGISTRY.resolve()}
    if PRIOR_FAILED_RUN.exists():
        excluded.update(path.resolve() for path in PRIOR_FAILED_RUN.rglob("*") if path.is_file())
    if SUPERSEDED_PREFLIGHT_RUN.exists():
        excluded.update(path.resolve() for path in SUPERSEDED_PREFLIGHT_RUN.rglob("*") if path.is_file())
    if output_root.exists():
        excluded.update(path.resolve() for path in output_root.rglob("*") if path.is_file())
    rows = []
    for item in seed_registry["seeds"]:
        seed = int(item["seed"])
        hits: list[str] = []
        for raw_root in seed_registry["freshness_scan_roots"]:
            scan_root = Path(raw_root)
            if not scan_root.exists():
                continue
            completed = subprocess.run(
                ["rg", "-uu", "-l", "-F", "--", str(seed), str(scan_root)],
                capture_output=True, text=True,
            )
            if completed.returncode not in (0, 1):
                raise RuntimeError(f"freshness rg failed for {scan_root}: {completed.returncode}")
            for value in completed.stdout.splitlines():
                path = Path(value).resolve()
                if path not in excluded:
                    hits.append(str(path))
        rows.append({"seed": seed, "unexpected_hits": sorted(set(hits)), "pass": not hits})
    return {"rows": rows, "pass": all(row["pass"] for row in rows)}


def _prior_failure_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    execution_path = PRIOR_FAILED_RUN / "execution.json"
    manifest_path = PRIOR_FAILED_RUN / "manifest.json"
    shards = PRIOR_FAILED_RUN / "formal" / "controls" / "shards"
    candidate_shards = PRIOR_FAILED_RUN / "formal" / "candidates" / "shards"
    if not execution_path.is_file() or not manifest_path.is_file() or not shards.is_dir():
        raise RuntimeError("prior infrastructure-failed S1 authority is incomplete")
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    prior_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in shards.glob("*.json")]
    expected_seeds = [int(row["seed"]) for row in records]
    observed_seeds = sorted({int(job["context"]["seed"]) for job in prior_manifest["control_jobs"]})
    candidate_count = len(list(candidate_shards.glob("*.json"))) if candidate_shards.is_dir() else 0
    checks = {
        "same_seeds": sorted(expected_seeds) == observed_seeds == sorted(execution["executed_formal_seeds"]),
        "fresh_execution_recorded": execution.get("formal_fresh_seeds_executed") is True,
        "all_controls_infrastructure_failed": len(rows) == 32 and all(row.get("status") == "infrastructure_failed" for row in rows),
        "no_efficacy": all(row.get("efficacy") is None for row in rows),
        "no_candidate_execution": candidate_count == 0,
        "no_later_tier": execution.get("later_tier_launched") is False,
    }
    return {
        "pass": all(checks.values()), "checks": checks,
        "run_id": execution["run_id"], "execution_sha256": execution["execution_sha256"],
        "control_shards": len(rows), "candidate_shards": candidate_count,
        "reuse_classification": "same_s1_seed_tier_after_infrastructure_failure",
    }


def _seed_records() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    registry = json.loads(SEED_REGISTRY.read_text(encoding="utf-8"))
    records = registry.get("seeds", [])
    values = [int(row["seed"]) for row in records]
    if len(values) != 2 or len(set(values)) != 2:
        raise RuntimeError("E2 S1 requires exactly two distinct fresh seeds")
    if any(
        row.get("classification") != "formal_fresh"
        or row.get("fresh") is not True
        or int(row.get("preselection_repository_hits", -1)) != 0
        or row.get("executed") is not False
        for row in records
    ):
        raise RuntimeError("fresh seed registry is not in the pre-execution state")
    if set(values) & {811407, 81426017, 81426029}:
        raise RuntimeError("technical or consumed seed entered E2 S1")
    return records, registry


def _spawn_import_worker(payload: dict[str, str]) -> dict[str, Any]:
    try:
        _module, agent, _latency = RUNNER.harness.load_agent(
            Path(payload["path"]), f"e2_s1_spawn_smoke_{payload['tag']}",
        )
        return {"tag": payload["tag"], "callable_agent": callable(agent), "pass": callable(agent)}
    except BaseException as error:
        return {"tag": payload["tag"], "callable_agent": False, "pass": False, "error": f"{type(error).__name__}: {error}"}


def _spawn_import_smoke(frozen: dict[str, dict[str, Path]], workers: int) -> dict[str, Any]:
    tasks = [
        {"tag": f"saiteja_{index}", "path": str(frozen["opponents"]["saiteja_3000"])}
        for index in range(max(2, int(workers)))
    ]
    tasks.extend(
        {"tag": family, "path": str(frozen["opponents"][family])}
        for family in ("kaito_v21", "roman_lb950")
    )
    context = mp.get_context("spawn")
    rows: list[dict[str, Any]] = []
    try:
        with ProcessPoolExecutor(max_workers=int(workers), mp_context=context) as pool:
            futures = [pool.submit(_spawn_import_worker, task) for task in tasks]
            rows = [future.result() for future in futures]
    except BaseException as error:
        return {"pass": False, "rows": rows, "pool_error": f"{type(error).__name__}: {error}"}
    return {"pass": all(row["pass"] for row in rows), "rows": rows, "workers": int(workers)}


def _frozen_paths(root: Path) -> dict[str, dict[str, Path]]:
    controls = {lane: root / "inputs" / "controls" / lane / "main.py" for lane in LANES}
    candidates = {
        lane: root / "inputs" / "candidates" / lane / EXPECTED_CANDIDATES[lane] / "main.py"
        for lane in LANES
    }
    opponents = {
        family: root / "inputs" / "opponents" / family / "main.py"
        for family in SOURCE_PUBLIC_OPPONENTS
    }
    return {"controls": controls, "candidates": candidates, "opponents": opponents}


def _jobs(
    root: Path,
    records: list[dict[str, Any]],
    frozen: dict[str, dict[str, Path]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    controls: list[dict[str, Any]] = []
    for lane in LANES:
        for opponent in OPPONENTS:
            for seed_record in records:
                for seat in SEATS:
                    job = {
                        "kind": "control", "evaluation_mode": "e2_s1_formal_exact",
                        "context": {"lane": lane, "opponent": opponent, "seed": int(seed_record["seed"]), "seat": seat},
                        "seed_record": seed_record,
                        "artifact": {"path": str(frozen["controls"][lane]), "sha256": file_sha256(frozen["controls"][lane])},
                    }
                    job["job_id"] = canonical_job_id(job)
                    controls.append(job)
    control_by_context = {
        (row["context"]["lane"], row["context"]["opponent"], row["context"]["seed"], row["context"]["seat"]): row["job_id"]
        for row in controls
    }
    candidates: list[dict[str, Any]] = []
    for lane in LANES:
        for opponent in OPPONENTS:
            for seed_record in records:
                for seat in SEATS:
                    context = {"lane": lane, "opponent": opponent, "seed": int(seed_record["seed"]), "seat": seat}
                    job = {
                        "kind": "candidate", "evaluation_mode": "e2_s1_formal_exact",
                        "candidate_id": EXPECTED_CANDIDATES[lane], "context": context,
                        "seed_record": seed_record,
                        "artifact": {"path": str(frozen["candidates"][lane]), "sha256": file_sha256(frozen["candidates"][lane])},
                        "control_job_id": control_by_context[(lane, opponent, int(seed_record["seed"]), seat)],
                        "control_cache_path": str(root / "control_cache" / f"{lane}.json"),
                    }
                    job["job_id"] = canonical_job_id(job)
                    candidates.append(job)
    return sorted(controls, key=lambda row: row["job_id"]), sorted(candidates, key=lambda row: row["job_id"])


def preflight(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    if not 1 <= int(workers) <= WORKER_LIMIT:
        raise ValueError(f"workers must be in 1..{WORKER_LIMIT}")
    if root.exists():
        raise FileExistsError(f"new E2 S1 root required: {root}")
    authority = verify_authority()
    if not authority["pass"]:
        raise RuntimeError("E1c authority verification failed")
    verification = json.loads(DEVELOPMENT_VERIFICATION.read_text(encoding="utf-8"))
    canonical, canonical_ok = _canonical_file(DEVELOPMENT_VERIFICATION, "development_verification_sha256")
    if verification.get("decision") != "READY_FOR_E2_S1" or not canonical_ok:
        raise RuntimeError("E2 development verification is not ready or canonical")
    development_registry = json.loads(DEVELOPMENT_REGISTRY.read_text(encoding="utf-8"))
    if any(
        development_registry["lanes"][lane]["candidate_id"] != EXPECTED_CANDIDATES[lane]
        for lane in LANES
    ):
        raise RuntimeError("development candidate registry differs from frozen S1 candidates")
    records, registry = _seed_records()
    prior_failure = _prior_failure_audit(records)
    if not prior_failure["pass"]:
        raise RuntimeError("prior failed S1 run is not eligible for same-tier seed reuse")
    scan = _freshness_scan(registry, root)
    if not scan["pass"]:
        raise RuntimeError(f"selected seed is not fresh: {scan}")
    engine = RUNNER.assert_engine_current()
    root.mkdir(parents=True)
    frozen = _frozen_paths(root)
    copied: dict[str, Any] = {
        "controls": {lane: _copy_exact(SOURCE_CONTROLS[lane], frozen["controls"][lane]) for lane in LANES},
        "candidates": {lane: _copy_exact(SOURCE_CANDIDATES[lane], frozen["candidates"][lane]) for lane in LANES},
        "opponents": {},
    }
    for family, filenames in PUBLIC_OPPONENT_FILES.items():
        source_dir = SOURCE_PUBLIC_OPPONENTS[family].parent
        target_dir = frozen["opponents"][family].parent
        files = {name: _copy_exact(source_dir / name, target_dir / name) for name in filenames}
        copied["opponents"][family] = {
            "entrypoint": str(frozen["opponents"][family]), "files": files,
            "package_sha256": payload_hash(files),
        }
    opponent_import_smoke: dict[str, Any] = {}
    for family in SOURCE_PUBLIC_OPPONENTS:
        try:
            _module, agent, _latency = RUNNER.harness.load_agent(
                frozen["opponents"][family], f"e2_s1_preflight_{family}",
            )
            opponent_import_smoke[family] = {"callable_agent": callable(agent), "pass": callable(agent)}
        except Exception as error:
            opponent_import_smoke[family] = {"callable_agent": False, "pass": False, "error": f"{type(error).__name__}: {error}"}
    if not all(row["pass"] for row in opponent_import_smoke.values()):
        raise RuntimeError(f"frozen opponent import smoke failed: {opponent_import_smoke}")
    spawned_import_smoke = _spawn_import_smoke(frozen, int(workers))
    if not spawned_import_smoke["pass"]:
        raise RuntimeError(f"spawned frozen opponent import smoke failed: {spawned_import_smoke}")
    expected_verification_hashes = {
        lane: (
            verification["registered_candidate_parity"][lane]["artifact"]["sha256"]
            if lane == "boatlee_v16_rc2_market_relay"
            else next(iter(verification["selector_development_ablations"].values()))["artifact"]["sha256"]
        )
        for lane in LANES
    }
    if any(copied["candidates"][lane]["sha256"] != expected_verification_hashes[lane] for lane in LANES):
        raise RuntimeError("candidate artifact differs from passed development verification")
    controls, candidates = _jobs(root, records, frozen)
    expected_per_lane = len(OPPONENTS) * len(records) * len(SEATS)
    if len(controls) != expected_per_lane * len(LANES) or len(candidates) != expected_per_lane * len(LANES):
        raise RuntimeError("unexpected S1 job count")
    template = json.loads(PROTOCOL_TEMPLATE.read_text(encoding="utf-8"))
    protocol = copy.deepcopy(template)
    protocol.update({
        "status": "frozen_authorized_s1", "formal_authorized": True,
        "authorization": "User explicitly instructed: 啟動 S1",
        "run_id": RUN_ID, "run_root": str(root), "workers": int(workers),
        "formal_fresh_seeds_executed": False,
        "evaluation_seeds": [int(row["seed"]) for row in records],
        "seed_registry": {"path": str(SEED_REGISTRY), "sha256": file_sha256(SEED_REGISTRY), "records": records},
        "seed_reuse_authority": prior_failure,
        "engine_fingerprint": engine,
        "control_hashes": {lane: copied["controls"][lane]["sha256"] for lane in LANES},
        "route_hashes": {lane: file_sha256(SOURCE_ROUTES[lane]) for lane in LANES},
        "candidate_registry_sha256": file_sha256(HERE / "candidate_registry.json"),
        "development_candidate_registry_sha256": file_sha256(DEVELOPMENT_REGISTRY),
        "development_verification": {"canonical_sha256": canonical, "file_sha256": file_sha256(DEVELOPMENT_VERIFICATION)},
        "candidate_artifacts": copied["candidates"],
        "opponent_artifacts": copied["opponents"],
        "opponent_import_smoke": opponent_import_smoke,
        "spawned_opponent_import_smoke": spawned_import_smoke,
        "job_counts": {"per_lane_controls": expected_per_lane, "per_lane_candidates": expected_per_lane, "controls": len(controls), "candidates": len(candidates), "total_games": len(controls) + len(candidates)},
        "implementation_hashes": {"formal_s1.py": file_sha256(Path(__file__)), "selector.py": file_sha256(HERE / "selector.py"), "effective_change.py": file_sha256(HERE / "effective_change.py")},
    })
    protocol["job_manifest_sha256"] = payload_hash({"controls": controls, "candidates": candidates})
    protocol["protocol_sha256"] = payload_hash({key: value for key, value in protocol.items() if key != "protocol_sha256"})
    manifest: dict[str, Any] = {
        "schema_version": 1, "kind": "e2_s1_formal_manifest", "run_id": RUN_ID,
        "run_root": str(root), "protocol_sha256": protocol["protocol_sha256"],
        "engine_sha256": payload_hash(engine), "controls_sha256": payload_hash(copied["controls"]),
        "candidates_sha256": payload_hash(copied["candidates"]), "opponents_sha256": payload_hash(copied["opponents"]),
        "seed_registry_sha256": file_sha256(SEED_REGISTRY),
        "jobs_sha256": protocol["job_manifest_sha256"],
        "control_jobs": controls, "candidate_jobs": candidates,
        "formal_fresh_seeds_executed": False,
    }
    manifest["manifest_sha256"] = payload_hash({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    atomic_json(root / "protocol.json", protocol)
    atomic_json(root / "manifest.json", manifest)
    atomic_json(root / "jobs" / "controls.json", {"manifest_sha256": manifest["manifest_sha256"], "jobs": controls, "job_manifest_sha256": payload_hash(controls)})
    atomic_json(root / "jobs" / "candidates.json", {"manifest_sha256": manifest["manifest_sha256"], "jobs": candidates, "job_manifest_sha256": payload_hash(candidates)})
    dry = {
        "schema_version": 1, "kind": "e2_s1_dry_preflight", "run_id": RUN_ID,
        "pass": True, "formal_authorized": True, "formal_fresh_seeds_executed": False,
        "freshness_scan": scan, "candidate_count": len(EXPECTED_CANDIDATES),
        "seed_reuse_authority": prior_failure,
        "opponent_import_smoke": opponent_import_smoke,
        "spawned_opponent_import_smoke": spawned_import_smoke,
        "seed_tier": {"name": "S1", "fresh_seed_count": len(records), "seeds": [int(row["seed"]) for row in records]},
        "job_counts": protocol["job_counts"], "manifest_sha256": manifest["manifest_sha256"],
        "protocol_sha256": protocol["protocol_sha256"], "registry_sha256": file_sha256(SEED_REGISTRY),
    }
    dry["dry_preflight_sha256"] = payload_hash({key: value for key, value in dry.items() if key != "dry_preflight_sha256"})
    atomic_json(root / "dry_preflight.json", dry)
    return dry


def _load_frozen(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    protocol_body = {key: value for key, value in protocol.items() if key != "protocol_sha256"}
    if manifest.get("manifest_sha256") != payload_hash(manifest_body):
        raise RuntimeError("formal manifest canonical hash mismatch")
    if protocol.get("protocol_sha256") != payload_hash(protocol_body):
        raise RuntimeError("formal protocol canonical hash mismatch")
    if manifest.get("protocol_sha256") != protocol.get("protocol_sha256"):
        raise RuntimeError("manifest/protocol identity mismatch")
    if protocol.get("formal_authorized") is not True or protocol.get("status") != "frozen_authorized_s1":
        raise PermissionError("S1 protocol is not explicitly authorized")
    if protocol.get("job_manifest_sha256") != payload_hash({"controls": manifest["control_jobs"], "candidates": manifest["candidate_jobs"]}):
        raise RuntimeError("job manifest hash mismatch")
    return manifest, protocol


def validate_preflight(root: Path) -> dict[str, Any]:
    manifest, protocol = _load_frozen(root.resolve())
    controls = manifest["control_jobs"]
    candidates = manifest["candidate_jobs"]
    checks = {
        "run_id": manifest["run_id"] == RUN_ID == protocol["run_id"],
        "two_fresh_seeds": len(protocol["evaluation_seeds"]) == 2 and len(set(protocol["evaluation_seeds"])) == 2,
        "candidate_count": sum(len(protocol["lanes"][lane]["candidates"]) for lane in LANES) == 2,
        "job_count": len(controls) == 32 and len(candidates) == 32,
        "both_seats": set(row["context"]["seat"] for row in controls + candidates) == {0, 1},
        "opponents": set(row["context"]["opponent"] for row in controls + candidates) == set(OPPONENTS),
        "lane_controls_isolated": all("control_cache" not in row for row in controls) and all(Path(row["control_cache_path"]).stem == row["context"]["lane"] for row in candidates),
        "inputs_match": all(file_sha256(Path(row["artifact"]["path"])) == row["artifact"]["sha256"] for row in controls + candidates),
        "opponents_match": all(
            file_sha256(Path(file_row["path"])) == file_row["sha256"]
            for package in protocol["opponent_artifacts"].values()
            for file_row in package["files"].values()
        ),
        "opponents_imported": all(row["pass"] and row["callable_agent"] for row in protocol["opponent_import_smoke"].values()),
        "opponents_imported_in_spawn_workers": protocol["spawned_opponent_import_smoke"]["pass"] is True,
        "seed_reuse_authorized": protocol["seed_reuse_authority"]["pass"] is True,
        "registries_match": (
            file_sha256(SEED_REGISTRY) == protocol["seed_registry"]["sha256"]
            and file_sha256(HERE / "candidate_registry.json") == protocol["candidate_registry_sha256"]
            and file_sha256(DEVELOPMENT_REGISTRY) == protocol["development_candidate_registry_sha256"]
        ),
        "implementation_match": all(
            file_sha256(Path(__file__) if name == "formal_s1.py" else HERE / name) == expected
            for name, expected in protocol["implementation_hashes"].items()
        ),
        "engine": RUNNER.assert_engine_current() == protocol["engine_fingerprint"],
        "not_executed": manifest["formal_fresh_seeds_executed"] is False and protocol["formal_fresh_seeds_executed"] is False,
    }
    return {
        "pass": all(checks.values()), "checks": checks,
        "manifest_sha256": manifest["manifest_sha256"], "protocol_sha256": protocol["protocol_sha256"],
        "seed_registry_sha256": protocol["seed_registry"]["sha256"],
        "job_counts": protocol["job_counts"], "formal_fresh_seeds_executed": False,
    }


def _opponent_path(root: Path, lane: str, family: str) -> Path:
    frozen = _frozen_paths(root)
    if family == "other_incumbent":
        other = "v27_current_meta" if lane == "boatlee_v16_rc2_market_relay" else "boatlee_v16_rc2_market_relay"
        return frozen["controls"][other]
    if family in frozen["opponents"]:
        return frozen["opponents"][family]
    raise KeyError(family)


def _technical_valid(summary: dict[str, Any]) -> bool:
    return (
        summary.get("statuses") == ["DONE", "DONE"]
        and summary.get("exception") is None and summary.get("opponent_exception") is None
        and int(summary.get("timeout_calls", 0)) == 0 and not bool(summary.get("overage_exhausted"))
        and int(summary.get("max_market_orders", 0)) <= 10
        and not any(summary.get("action_issues", {}).values())
    )


def _public_observation(observation: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in observation.items() if key not in {"private", "remainingOverageTime"}}


def _outcome(run: Any) -> dict[str, Any]:
    summary = run.summary
    seat = int(run.seat)
    public_states = [_public_observation(frame.observation) for frame in run.trace]
    receipts = [list(item) for frame in run.trace for item in frame.market_receipts]
    mechanism: dict[str, Any]
    if run.incumbent == "v27_current_meta":
        frame = run.trace[494]
        market = frame.observation["market"]
        mechanism = {
            "step": 494, "wheat_price": int(market["prices"]["WHEAT"]),
            "wheat_inventory": int(market["inventory"]["WHEAT"]),
            "wheat_buy_present": ["BUY_PRODUCT", "WHEAT", 2] in frame.action.get("market", []),
        }
    else:
        mechanism = {"steps": {str(step): run.trace[step].action.get("market", []) for step in (240, 241)}}
    rewards = summary["rewards"]
    money = summary["money"]
    return {
        "technical_status": "complete" if _technical_valid(summary) else "technical_invalid",
        "summary": summary,
        "evidence": {
            "action_digest": summary["action_digest"],
            "public_state_digest": payload_hash(public_states),
            "receipt_digest": payload_hash(receipts), "receipts": receipts,
            "economic_diagnostics": summary.get("diagnostics", {}),
        },
        "mechanism": mechanism,
        "own_reward": float(rewards[seat]), "opponent_reward": float(rewards[1 - seat]),
        "own_bank": float(money[seat]), "opponent_bank": float(money[1 - seat]),
    }


def _classify(candidate: dict[str, Any], control: dict[str, Any]) -> dict[str, Any]:
    changes = {
        "action": candidate["evidence"]["action_digest"] != control["evidence"]["action_digest"],
        "receipt": candidate["evidence"]["receipt_digest"] != control["evidence"]["receipt_digest"],
        "public_economic_state": candidate["evidence"]["public_state_digest"] != control["evidence"]["public_state_digest"],
        "terminal_bank_or_reward": any(float(candidate[key]) != float(control[key]) for key in ("own_reward", "opponent_reward", "own_bank", "opponent_bank")),
        "economic_diagnostics": candidate["evidence"]["economic_diagnostics"] != control["evidence"]["economic_diagnostics"],
    }
    effective = any(value for key, value in changes.items() if key != "action")
    return {"changes": changes, "effective": effective, "action_only_noop": changes["action"] and not effective}


def _evaluate_job(job: dict[str, Any]) -> dict[str, Any]:
    try:
        if job.get("evaluation_mode") != "e2_s1_formal_exact":
            raise ValueError("unknown evaluation mode")
        seed_record = job["seed_record"]
        if seed_record.get("classification") != "formal_fresh" or seed_record.get("fresh") is not True:
            raise PermissionError("job seed is not registered fresh")
        artifact = Path(job["artifact"]["path"])
        if file_sha256(artifact) != job["artifact"]["sha256"]:
            raise RuntimeError("job artifact hash mismatch")
        context = job["context"]
        if job.get("run_root"):
            root = Path(job["run_root"])
        elif job["kind"] == "candidate":
            root = Path(job["control_cache_path"]).parents[1]
        else:
            root = artifact.parents[3]
        original = RUNNER.opponent_path
        RUNNER.opponent_path = lambda lane, family: _opponent_path(root, lane, family)
        try:
            run = RUNNER.run_game(
                context["lane"], artifact, context["opponent"], int(context["seed"]),
                int(context["seat"]), capture_trace=True,
            )
        finally:
            RUNNER.opponent_path = original
        outcome = _outcome(run)
        if outcome["technical_status"] != "complete":
            return {"job_id": job["job_id"], "status": "technical_invalid", "efficacy": None, "result": outcome}
        row: dict[str, Any] = {"job_id": job["job_id"], "status": "complete", "result": outcome}
        if job["kind"] == "control":
            row["efficacy"] = None
        else:
            cache = json.loads(Path(job["control_cache_path"]).read_text(encoding="utf-8"))
            control = cache.get(job["control_job_id"])
            if not isinstance(control, dict) or control.get("technical_status") != "complete":
                raise RuntimeError("lane-relative control cache missing")
            outcome["control_job_id"] = job["control_job_id"]
            outcome["control"] = control
            outcome["paired"] = {
                "margin_delta": (outcome["own_reward"] - outcome["opponent_reward"]) - (control["own_reward"] - control["opponent_reward"]),
                "own_bank_delta": outcome["own_bank"] - control["own_bank"],
                "win_delta": int(outcome["own_reward"] > outcome["opponent_reward"]) - int(control["own_reward"] > control["opponent_reward"]),
            }
            outcome["effective_change"] = _classify(outcome, control)
            row["efficacy"] = {"formal": True, "lane": context["lane"]}
        return row
    except Exception as error:
        return {
            "job_id": job.get("job_id"), "status": "infrastructure_failed", "efficacy": None,
            "infrastructure_failure": {"type": type(error).__name__, "detail": str(error)},
        }


def _valid_shard(path: Path, job_id: str) -> dict[str, Any] | None:
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
        body = dict(row)
        expected = body.pop("shard_sha256", None)
        return row if row.get("job_id") == job_id and expected == payload_hash(body) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _run_jobs(root: Path, jobs: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    shards = root / "shards"
    shards.mkdir(parents=True, exist_ok=True)
    retained: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for original in jobs:
        job = {**original, "run_root": str(root.parents[1].resolve())}
        path = shards / f"{job['job_id']}.json"
        if path.exists():
            valid = _valid_shard(path, job["job_id"])
            if valid is not None:
                retained.append(valid)
                continue
            preserved = path.with_name(f"{path.stem}.corrupt-{file_sha256(path)[:12]}.json")
            path.replace(preserved)
        pending.append(job)
    context = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        futures = {pool.submit(_evaluate_job, job): job for job in pending}
        for future in as_completed(futures):
            job = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = {"job_id": job["job_id"], "status": "infrastructure_failed", "efficacy": None, "infrastructure_failure": {"type": "worker", "detail": str(error)}}
            body = dict(row)
            body["shard_sha256"] = payload_hash(body)
            atomic_json(shards / f"{row['job_id']}.json", body)
            retained.append(body)
    return sorted(retained, key=lambda row: row["job_id"])


def _lane_summary(lane: str, jobs: list[dict[str, Any]], rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    lane_jobs = [job for job in jobs if job["context"]["lane"] == lane]
    observed = [rows.get(job["job_id"]) for job in lane_jobs]
    complete = all(row and row.get("status") == "complete" and row.get("result", {}).get("technical_status") == "complete" for row in observed)
    if not complete:
        return {"lane": lane, "candidate_id": EXPECTED_CANDIDATES[lane], "complete": False, "score": None, "contexts_expected": len(lane_jobs), "contexts_complete": sum(bool(row and row.get("status") == "complete") for row in observed)}
    results = [row["result"] for row in observed if row is not None]
    margins = [float(row["paired"]["margin_delta"]) for row in results]
    banks = [float(row["paired"]["own_bank_delta"]) for row in results]
    wins = [int(row["paired"]["win_delta"]) for row in results]
    by_opponent: dict[str, list[float]] = {opponent: [] for opponent in OPPONENTS}
    effective = 0
    labels: dict[str, list[dict[str, Any]]] = {}
    for job, result in zip(lane_jobs, results):
        by_opponent[job["context"]["opponent"]].append(float(result["paired"]["margin_delta"]))
        effective += int(result["effective_change"]["effective"])
        if lane == "v27_current_meta":
            branch = "incumbent" if result["mechanism"]["wheat_buy_present"] else "suppress_buy"
            labels.setdefault(branch, []).append({"context": job["context"], "margin_delta": result["paired"]["margin_delta"], "own_bank_delta": result["paired"]["own_bank_delta"]})
    return {
        "lane": lane, "candidate_id": EXPECTED_CANDIDATES[lane], "complete": True,
        "contexts_expected": len(lane_jobs), "contexts_complete": len(results),
        "effective_contexts": effective, "mean_paired_margin": sum(margins) / len(margins),
        "worst_paired_margin": min(margins), "mean_own_bank_delta": sum(banks) / len(banks),
        "actual_win_delta": sum(wins),
        "by_opponent_mean_margin": {key: sum(values) / len(values) for key, values in by_opponent.items()},
        "selector_fresh_labels": labels if lane == "v27_current_meta" else None,
        "score": sum(margins) / len(margins),
    }


def run(root: Path, workers: int, execute_s1: bool) -> dict[str, Any]:
    root = root.resolve()
    if not execute_s1:
        raise PermissionError("formal exact E2 S1 requires --execute-s1")
    manifest, protocol = _load_frozen(root)
    if not validate_preflight(root)["pass"]:
        raise RuntimeError("frozen preflight no longer validates")
    if int(protocol["workers"]) != int(workers):
        raise RuntimeError("worker count differs from frozen protocol")
    for name, expected in protocol["implementation_hashes"].items():
        path = Path(__file__) if name == "formal_s1.py" else HERE / name
        if file_sha256(path) != expected:
            raise RuntimeError(f"implementation changed after preflight: {name}")
    execution = {
        "schema_version": 1, "kind": "e2_s1_execution", "run_id": RUN_ID,
        "manifest_sha256": manifest["manifest_sha256"], "protocol_sha256": protocol["protocol_sha256"],
        "formal_fresh_seeds_executed": True, "executed_formal_seeds": protocol["evaluation_seeds"],
        "later_tier_launched": False,
    }
    execution["execution_sha256"] = payload_hash({key: value for key, value in execution.items() if key != "execution_sha256"})
    atomic_json(root / "execution.json", execution)
    control_rows = _run_jobs(root / "formal" / "controls", manifest["control_jobs"], workers)
    if not all(row.get("status") == "complete" and row.get("result", {}).get("technical_status") == "complete" for row in control_rows):
        raise RuntimeError("control phase incomplete; candidate phase not launched")
    for lane in LANES:
        lane_jobs = [job for job in manifest["control_jobs"] if job["context"]["lane"] == lane]
        by_id = {row["job_id"]: row["result"] for row in control_rows}
        cache = {job["job_id"]: by_id[job["job_id"]] for job in lane_jobs}
        atomic_json(root / "control_cache" / f"{lane}.json", cache)
    candidate_rows = _run_jobs(root / "formal" / "candidates", manifest["candidate_jobs"], workers)
    by_id = {row["job_id"]: row for row in candidate_rows}
    lane_results = {lane: _lane_summary(lane, manifest["candidate_jobs"], by_id) for lane in LANES}
    complete = all(row["complete"] for row in lane_results.values())
    summary = {
        "schema_version": 1, "kind": "e2_s1_summary", "run_id": RUN_ID,
        "manifest_sha256": manifest["manifest_sha256"], "protocol_sha256": protocol["protocol_sha256"],
        "formal_fresh_seeds_executed": True, "executed_formal_seeds": protocol["evaluation_seeds"],
        "control_contexts": len(control_rows), "candidate_contexts": len(candidate_rows),
        "lanes": lane_results, "complete": complete, "later_tier_launched": False,
    }
    summary["s1_summary_sha256"] = payload_hash({key: value for key, value in summary.items() if key != "s1_summary_sha256"})
    atomic_json(root / "s1_summary.json", summary)
    checkpoint = {
        "schema_version": 1, "manifest_sha256": manifest["manifest_sha256"],
        "control_shards": [row["job_id"] for row in control_rows],
        "candidate_shards": [row["job_id"] for row in candidate_rows],
        "complete": complete, "s1_summary_sha256": summary["s1_summary_sha256"],
        "formal_fresh_seeds_executed": True, "later_tier_launched": False,
    }
    checkpoint["checkpoint_sha256"] = payload_hash({key: value for key, value in checkpoint.items() if key != "checkpoint_sha256"})
    atomic_json(root / "checkpoint.json", checkpoint)
    return summary


def launch(root: Path, workers: int) -> dict[str, Any]:
    root = root.resolve()
    validation = validate_preflight(root)
    if not validation["pass"]:
        raise RuntimeError(f"dry preflight failed: {validation}")
    frozen_protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    if int(workers) != int(frozen_protocol["workers"]):
        raise RuntimeError("launch worker count differs from frozen protocol")
    stdout_path = root / "logs" / "stdout.log"
    stderr_path = root / "logs" / "stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), "run", "--output-root", str(root), "--workers", str(workers), "--execute-s1"]
    creationflags = 0
    for name in ("CREATE_NO_WINDOW", "CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS"):
        creationflags |= int(getattr(subprocess, name, 0))
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            close_fds=True, creationflags=creationflags,
        )
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    record = {
        "schema_version": 1, "kind": "e2_s1_launch", "run_id": RUN_ID,
        "pid": int(process.pid), "command": command, "workers": int(workers),
        "manifest_sha256": manifest["manifest_sha256"], "protocol_sha256": protocol["protocol_sha256"],
        "registry_sha256": protocol["seed_registry"]["sha256"],
        "stdout": str(stdout_path), "stderr": str(stderr_path),
        "control_shards": str(root / "formal" / "controls" / "shards"),
        "candidate_shards": str(root / "formal" / "candidates" / "shards"),
        "execution_launched": True, "completion_audited": False,
        "formal_fresh_seeds_executed": False, "later_tier_launched": False,
    }
    record["launch_sha256"] = payload_hash({key: value for key, value in record.items() if key != "launch_sha256"})
    atomic_json(root / "launch.json", record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "validate", "launch", "run"):
        command = commands.add_parser(name)
        command.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
        if name in {"preflight", "launch", "run"}:
            command.add_argument("--workers", type=int, required=True)
        if name == "run":
            command.add_argument("--execute-s1", action="store_true")
    args = parser.parse_args()
    if args.command == "preflight":
        result = preflight(args.output_root, args.workers)
    elif args.command == "validate":
        result = validate_preflight(args.output_root)
    elif args.command == "launch":
        result = launch(args.output_root, args.workers)
    else:
        result = run(args.output_root, args.workers, args.execute_s1)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))


if __name__ == "__main__":
    main()
