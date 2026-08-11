"""Exact-engine behavior and latency harness for main-approach optimization."""

from __future__ import annotations

import copy
import gc
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from types import ModuleType, SimpleNamespace
import random
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
ENGINE_COMMIT = "bded87b0d7879078c726a93a4884d044f79c4eed"
ENGINE_RELATIVE = "kaggle_environments/envs/kaggriculture/kaggriculture.py"
CONFIG_RELATIVE = "kaggle_environments/envs/kaggriculture/kaggriculture.json"
ENGINE_BLOB = "4b78842d0f2d4abf6e318a8248b6306454f5c714"
CONFIG_BLOB = "0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8"
ENGINE_SHA256 = "fb9215c5e21a25243e2d13e75b3d70a79cf7d78fff150a90f1bb5eacf9ba2bcf"
CONFIG_SHA256 = "7f196f4aaf9b4e482fbd61ba4bf19f5cec4da0f81938ece756954035a65c0bb5"

STRATEGIES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
PUBLIC = {
    "kaito_v21": ROOT / "research/public_agents/kaito_v21_top30/extracted/main.py",
    "roman_lb950": ROOT / "research/public_agents/roman_lb950/extracted/main.py",
    "saiteja_3000": ROOT / "research/public_agents/saiteja_mega_ensemble_3000/extracted/main.py",
    "guarded_v27": ROOT / "research/main_approach/v27_current_meta_safety_guarded/main.py",
}
MEGA_SIBLINGS = ("agent_frontier", "agent_hamburger", "agent_moon", "agent_v14")

_RUNTIME: tempfile.TemporaryDirectory[str] | None = None
_ENGINE: ModuleType | None = None
_SPEC: dict[str, Any] | None = None


class Struct(dict):
    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError as error:
            raise AttributeError(key) from error

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def structify(value: Any) -> Any:
    if isinstance(value, dict):
        return Struct({key: structify(item) for key, item in value.items()})
    if isinstance(value, list):
        return [structify(item) for item in value]
    return value


def plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


def _vendor_repo() -> Path:
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = ROOT / common_path
    repo = common_path.resolve().parent / ".vendor" / "kaggle-environments"
    if not repo.is_dir():
        raise FileNotFoundError(repo)
    return repo


def _git_bytes(relative: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(_vendor_repo()), "show", f"{ENGINE_COMMIT}:{relative}"]
    )


def engine_fingerprint() -> dict[str, Any]:
    repo = _vendor_repo()
    python = _git_bytes(ENGINE_RELATIVE)
    configuration = _git_bytes(CONFIG_RELATIVE)
    python_blob = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", f"{ENGINE_COMMIT}:{ENGINE_RELATIVE}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    config_blob = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", f"{ENGINE_COMMIT}:{CONFIG_RELATIVE}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    result = {
        "commit": ENGINE_COMMIT,
        "python_blob": python_blob,
        "configuration_blob": config_blob,
        "python_sha256": hashlib.sha256(python).hexdigest(),
        "configuration_sha256": hashlib.sha256(configuration).hexdigest(),
        "python_bytes": len(python),
        "configuration_bytes": len(configuration),
        "vendor_repo": str(repo),
    }
    expected = {
        "python_blob": ENGINE_BLOB,
        "configuration_blob": CONFIG_BLOB,
        "python_sha256": ENGINE_SHA256,
        "configuration_sha256": CONFIG_SHA256,
    }
    for key, value in expected.items():
        if result[key] != value:
            raise RuntimeError(f"official engine {key} mismatch: {result[key]} != {value}")
    return result


def load_engine() -> tuple[ModuleType, dict[str, Any]]:
    global _RUNTIME, _ENGINE, _SPEC
    if _ENGINE is not None and _SPEC is not None:
        return _ENGINE, _SPEC
    engine_fingerprint()
    _RUNTIME = tempfile.TemporaryDirectory(prefix="kaggriculture-current-engine-")
    runtime = Path(_RUNTIME.name)
    engine_path = runtime / ENGINE_RELATIVE
    config_path = runtime / CONFIG_RELATIVE
    engine_path.parent.mkdir(parents=True, exist_ok=True)
    engine_path.write_bytes(_git_bytes(ENGINE_RELATIVE))
    config_path.write_bytes(_git_bytes(CONFIG_RELATIVE))

    # Kaggriculture imports only this utility from the framework.  Providing
    # the exact helper locally avoids importing every bundled environment (and
    # native DLLs) while preserving the audited interpreter semantics.
    package = ModuleType("kaggle_environments")
    utils = ModuleType("kaggle_environments.utils")

    def resolve_episode_seed(env, *, config_key="seed", fallback=None):
        if not hasattr(env, "info") or env.info is None:
            env.info = {}
        seed = env.info.get("seed")
        config = env.configuration
        if seed is None:
            seed = getattr(config, config_key, None)
            if seed is None and isinstance(config, dict):
                seed = config.get(config_key)
        if seed is None:
            seed = fallback() if fallback is not None else random.randrange(2**31)
        try:
            setattr(config, config_key, None)
        except (AttributeError, TypeError):
            config[config_key] = None
        env.info["seed"] = seed
        return seed

    utils.resolve_episode_seed = resolve_episode_seed
    package.utils = utils
    sys.modules["kaggle_environments"] = package
    sys.modules["kaggle_environments.utils"] = utils
    spec = importlib.util.spec_from_file_location("_exact_current_kaggriculture", engine_path)
    if spec is None or spec.loader is None:
        raise ImportError(engine_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    configuration = json.loads(config_path.read_text(encoding="utf-8"))
    _ENGINE, _SPEC = module, configuration
    return module, configuration


def configuration(seed: int) -> Struct:
    _, specification = load_engine()
    values = {}
    for key, item in specification["configuration"].items():
        values[key] = item.get("default") if isinstance(item, dict) else item
    values["seed"] = int(seed)
    return structify(values)


def _new_state() -> list[Struct]:
    return [
        structify(
            {
                "observation": {"player": player, "step": 0, "remainingOverageTime": 60.0},
                "action": {"farmer": ["PASS"], "hands": [], "market": []},
                "status": "ACTIVE",
                "reward": 0.0,
            }
        )
        for player in range(2)
    ]


def _clear_local_modules() -> None:
    for name in tuple(sys.modules):
        if name == "development" or name.startswith("development.") or name in MEGA_SIBLINGS:
            sys.modules.pop(name, None)


def load_agent(path: Path, tag: str) -> tuple[Any, Callable[..., dict], float]:
    _clear_local_modules()
    name = f"optimization_{tag}_{time.time_ns()}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    old_path = list(sys.path)
    started = time.perf_counter()
    try:
        sys.path.insert(0, str(path.parent))
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = old_path
    duration_ms = (time.perf_counter() - started) * 1000.0
    agent = getattr(module, "agent", None)
    if not callable(agent):
        raise TypeError(f"no callable agent in {path}")
    return module, agent, duration_ms


def invoke(agent: Callable[..., dict], observation: Any, config: Any) -> dict:
    if len(inspect.signature(agent).parameters) >= 2:
        return agent(observation, config)
    return agent(observation)


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] * (high - index) + ordered[high] * (index - low)


def latency_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "calls": len(values),
        "total": sum(values),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "max": max(values, default=0.0),
    }


def _action_issues(obs: dict[str, Any], action: Any) -> dict[str, int]:
    if not isinstance(action, dict):
        return {"malformed": 1, "hand_alignment": 1, "seed_overcommit": 0, "market_overflow": 0}
    farmer = action.get("farmer")
    hands = action.get("hands")
    market = action.get("market")
    malformed = int(
        not isinstance(farmer, list)
        or not isinstance(hands, list)
        or not isinstance(market, list)
        or (isinstance(hands, list) and any(not isinstance(order, list) for order in hands))
        or (isinstance(market, list) and any(not isinstance(order, list) for order in market))
    )
    farm = obs["farms"][obs["player"]]
    plants: dict[str, int] = {}
    if isinstance(hands, list):
        for order in [farmer, *hands]:
            if isinstance(order, list) and len(order) >= 2 and order[0] == "PLANT":
                plants[str(order[1])] = plants.get(str(order[1]), 0) + 1
    seeds = (obs.get("private", {}) or {}).get("seeds", {}) or {}
    return {
        "malformed": malformed,
        "hand_alignment": int(not isinstance(hands, list) or len(hands) != len(farm.get("hands", []) or [])),
        "seed_overcommit": sum(max(0, count - int(seeds.get(crop, 0) or 0)) for crop, count in plants.items()),
        "market_overflow": int(isinstance(market, list) and len(market) > 10),
    }


def _tile_events(before: list, after: list, day: int) -> tuple[int, int, int]:
    escapes = crop_deaths = fresh_crop_deaths = 0
    for y, row in enumerate(before):
        for x, old in enumerate(row):
            new = after[y][x]
            if isinstance(old, dict) and old.get("animal"):
                escapes += int(not (isinstance(new, dict) and new.get("animal") == old.get("animal")))
            if isinstance(old, dict) and old.get("kind") == "PLANT" and isinstance(new, dict) and new.get("kind") == "WEED":
                crop_deaths += 1
                fresh_crop_deaths += int(int(old.get("planted_day", -1000)) == day)
    return escapes, crop_deaths, fresh_crop_deaths


def _pending_overflow(private: dict[str, Any], capacity: int) -> int:
    total = sum(max(0, int(value or 0)) for value in (private.get("shed", {}) or {}).values())
    for inventory in private.get("inventories", []) or []:
        total += sum(max(0, int(value or 0)) for value in (inventory or {}).values())
    return max(0, total - capacity)


def _terminal_inventory(obs: Any) -> dict[str, float | int]:
    items: dict[str, int] = {}
    private = obs.private
    for source in [private.get("shed", {}), *(private.get("inventories", []) or [])]:
        for item, value in (source or {}).items():
            items[item] = items.get(item, 0) + max(0, int(value or 0))
    prices = obs.market.get("prices", {}) or {}
    return {
        "units": sum(items.values()),
        "marked_value": sum(quantity * float(prices.get(item, 0) or 0) for item, quantity in items.items()),
    }


def _opponent_path(name: str) -> Path:
    if name not in PUBLIC:
        raise KeyError(f"unknown opponent: {name}")
    return PUBLIC[name]


def run_game(
    candidate_path: Path,
    opponent: str,
    seed: int,
    seat: int,
    *,
    capture_observations: bool = False,
    tag: str = "game",
) -> dict[str, Any]:
    engine, _ = load_engine()
    config = configuration(seed)
    env = SimpleNamespace(configuration=config, info={}, done=False, steps=[])
    state = _new_state()
    engine.interpreter(state, env)
    _, candidate, import_ms = load_agent(candidate_path, f"candidate_{tag}")
    _, adversary, _ = load_agent(_opponent_path(opponent), f"opponent_{tag}")
    agents = [adversary, adversary]
    agents[seat] = candidate
    digests = [hashlib.sha256(), hashlib.sha256()]
    timings: list[float] = []
    observations: list[dict[str, Any]] = []
    issues = {"malformed": 0, "hand_alignment": 0, "seed_overcommit": 0, "market_overflow": 0}
    diagnostics = {
        "animal_escapes": 0,
        "crop_deaths": 0,
        "fresh_crop_deaths": 0,
        "shed_overflow_events": 0,
        "shed_overflow_units": 0,
    }
    exceptions: list[str | None] = [None, None]
    overage = [60.0, 60.0]
    calls = [0, 0]
    max_market_orders = 0
    for step in range(int(config.episodeSteps) - 1):
        for index in range(2):
            state[index].observation.step = step
            state[index].observation.remainingOverageTime = overage[index]
        eod = (step + 1) % int(config.turnsPerDay) == 0
        before_tiles = copy.deepcopy(state[seat].observation.farms[seat]["tiles"]) if eod else None
        for index, policy in enumerate(agents):
            observation = structify(copy.deepcopy(plain(state[index].observation)))
            if index == seat and capture_observations:
                observations.append(plain(copy.deepcopy(observation)))
            started = time.perf_counter()
            try:
                action = invoke(policy, observation, config)
            except Exception as error:
                action = {"farmer": ["PASS"], "hands": [], "market": []}
                exceptions[index] = f"{type(error).__name__}: {error}"
            elapsed = time.perf_counter() - started
            calls[index] += 1
            if elapsed > float(config.actTimeout):
                overage[index] -= elapsed - float(config.actTimeout)
            encoded = json.dumps(action, sort_keys=True, separators=(",", ":")).encode()
            digests[index].update(encoded)
            if index == seat:
                timings.append(elapsed * 1000.0)
                found = _action_issues(plain(observation), action)
                for key, value in found.items():
                    issues[key] += value
                market = action.get("market", []) if isinstance(action, dict) else []
                if isinstance(market, list):
                    max_market_orders = max(max_market_orders, len(market))
            state[index].action = structify(action if isinstance(action, dict) else {})
        if exceptions[seat] or exceptions[1 - seat]:
            break
        if eod:
            overflow = _pending_overflow(plain(state[seat].observation.private), int(config.shedCapacity))
            diagnostics["shed_overflow_events"] += int(overflow > 0)
            diagnostics["shed_overflow_units"] += overflow
        engine.interpreter(state, env)
        if eod and before_tiles is not None:
            events = _tile_events(before_tiles, state[seat].observation.farms[seat]["tiles"], step // int(config.turnsPerDay))
            diagnostics["animal_escapes"] += events[0]
            diagnostics["crop_deaths"] += events[1]
            diagnostics["fresh_crop_deaths"] += events[2]
        if all(item.status == "DONE" for item in state):
            break
    scores = [float(state[index].observation.farms[index]["money"]) for index in range(2)]
    return {
        "path": str(candidate_path),
        "opponent": opponent,
        "seed": int(seed),
        "seat": int(seat),
        "statuses": [str(item.status) for item in state],
        "calls": calls[seat],
        "candidate_reward": float(state[seat].reward),
        "opponent_reward": float(state[1 - seat].reward),
        "candidate_money": scores[seat],
        "opponent_money": scores[1 - seat],
        "action_digest": digests[seat].hexdigest(),
        "opponent_action_digest": digests[1 - seat].hexdigest(),
        "action_issues": issues,
        "max_market_orders": max_market_orders,
        "diagnostics": diagnostics,
        "terminal_inventory": _terminal_inventory(state[seat].observation),
        "exception": exceptions[seat],
        "opponent_exception": exceptions[1 - seat],
        "timeout_calls": sum(value >= 1000.0 for value in timings),
        "overage_exhausted": overage[seat] < 0.0,
        "import_ms": import_ms,
        "latency_ms": latency_summary(timings),
        "timings_ms": timings,
        "observations": observations if capture_observations else None,
    }


def behavior_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "statuses", "calls", "candidate_reward", "opponent_reward", "candidate_money",
            "opponent_money", "action_digest", "opponent_action_digest", "action_issues",
            "max_market_orders", "diagnostics", "terminal_inventory", "exception",
            "opponent_exception", "timeout_calls", "overage_exhausted",
        )
    }


def _gc_collections() -> int:
    return sum(int(row["collections"]) for row in gc.get_stats())


def replay_benchmark(
    path: Path,
    observations: list[dict[str, Any]],
    seed: int,
    *,
    repetitions: int = 11,
    tag: str = "replay",
) -> dict[str, Any]:
    runs = []
    for repetition in range(repetitions):
        module, policy, import_ms = load_agent(path, f"{tag}_{repetition}")
        config = configuration(seed)
        gc.collect()
        blocks_before = sys.getallocatedblocks()
        collections_before = _gc_collections()
        digest = hashlib.sha256()
        timings = []
        static_returns = 0
        route = getattr(module, "_REBALANCE_ACTIONS", None)
        for raw in observations:
            observation = structify(raw)
            started = time.perf_counter()
            action = invoke(policy, observation, config)
            timings.append((time.perf_counter() - started) * 1000.0)
            step = int(raw.get("step", 0) or 0)
            static_returns += int(route is not None and 0 <= step < len(route) and action is route[step])
            digest.update(json.dumps(action, sort_keys=True, separators=(",", ":")).encode())
        summary = latency_summary(timings)
        summary.update(
            {
                "repetition": repetition,
                "import_ms": import_ms,
                "action_digest": digest.hexdigest(),
                "allocated_blocks_delta": sys.getallocatedblocks() - blocks_before,
                "gc_collections_delta": _gc_collections() - collections_before,
                "static_returns": static_returns,
                "dynamic_returns": len(observations) - static_returns,
            }
        )
        runs.append(summary)

    _, policy, _ = load_agent(path, f"{tag}_allocation")
    config = configuration(seed)
    gc.collect()
    blocks_before = sys.getallocatedblocks()
    collections_before = _gc_collections()
    tracemalloc.start()
    before_current, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    for raw in observations:
        invoke(policy, structify(raw), config)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    allocation = {
        "traced_current_delta_bytes": current - before_current,
        "traced_peak_delta_bytes": peak - before_current,
        "allocated_blocks_delta": sys.getallocatedblocks() - blocks_before,
        "gc_collections_delta": _gc_collections() - collections_before,
    }
    totals = [float(row["total"]) for row in runs]
    digests = sorted({str(row["action_digest"]) for row in runs})
    return {
        "path": str(path),
        "repetitions": repetitions,
        "stable_digest": len(digests) == 1,
        "action_digests": digests,
        "season_total_ms": {
            "median": statistics.median(totals),
            "mean": statistics.fmean(totals),
            "min": min(totals),
            "max": max(totals),
            "relative_range": (max(totals) - min(totals)) / max(statistics.median(totals), 1e-12),
        },
        "per_turn_ms_median_run": min(runs, key=lambda row: abs(float(row["total"]) - statistics.median(totals))),
        "allocation": allocation,
        "runs": runs,
    }


def cold_import_benchmark(path: Path, repetitions: int = 11) -> dict[str, Any]:
    code = (
        "import importlib.util,sys,time;"
        "p=sys.argv[1];n='cold_'+str(time.time_ns());"
        "s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);"
        "t=time.perf_counter();s.loader.exec_module(m);"
        "print((time.perf_counter()-t)*1000.0)"
    )
    values = []
    for _ in range(repetitions):
        result = subprocess.run(
            [sys.executable, "-c", code, str(path.resolve())],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        values.append(float(result.stdout.strip().splitlines()[-1]))
    return {
        "path": str(path),
        "repetitions": repetitions,
        "median_ms": statistics.median(values),
        "p95_ms": _percentile(values, 0.95),
        "min_ms": min(values),
        "max_ms": max(values),
        "raw_ms": values,
    }


def file_fingerprint(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def compact_game(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop("timings_ms", None)
    result.pop("observations", None)
    return result
