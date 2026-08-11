"""Version-aware Kaggriculture engine loading for offline replay research.

The workspace pins kaggle-environments at the 1.32.4 Kaggriculture semantics.
Public replays in the retained top-50 snapshot additionally use 1.32.5 and
1.32.6.  This module loads a fresh copy of the pinned interpreter and applies
only the two audited upstream semantic patches in memory:

* 1.32.5: shed operations from locked shed-access cells.
* 1.32.6: flat daily town-center demand and shop draws with replacement.

Nothing under .vendor is modified.  The patched interpreter is used only by
offline analysis and arena scripts.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import random
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / ".vendor" / "kaggle-environments"
ENGINE_PATH = VENDOR_ROOT / "kaggle_environments" / "envs" / "kaggriculture" / "kaggriculture.py"
JSON_PATH = ENGINE_PATH.with_suffix(".json")

VERSION_COMMITS = {
    "1.32.4": "a4dce5ae6e2ffe3c1afea8ec4b24b562df74cc07",
    "1.32.5": "bbcdd460accc16fdb1d1074b8c5b1d30ea92da4a",
    "1.32.6": "bded87b0d7879078c726a93a4884d044f79c4eed",
}

# Hashes use LF-normalized UTF-8 text, matching Path.read_text/newline handling.
PINNED_ENGINE_NORMALIZED_SHA256 = "9741C0470A8DB98A70644491D5121AE6295413343D1A08EF9FCEE35E0B76F2C5"
CURRENT_ENGINE_NORMALIZED_SHA256 = "FB9215C5E21A25243E2D13E75B3D70A79CF7D78FFF150A90F1BB5EACF9BA2BCF"
CURRENT_JSON_SHA256 = "7F196F4AAF9B4E482FBD61BA4BF19F5CEC4DA0F81938ECE756954035A65C0BB5"


def _normalized_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def verify_pinned_source() -> dict:
    """Verify the immutable local source used as the semantic patch base."""
    if not ENGINE_PATH.is_file() or not JSON_PATH.is_file():
        raise FileNotFoundError("missing pinned Kaggriculture engine under .vendor")
    digest = _normalized_hash(ENGINE_PATH)
    if digest != PINNED_ENGINE_NORMALIZED_SHA256:
        raise RuntimeError(
            "pinned Kaggriculture source hash mismatch: "
            f"expected {PINNED_ENGINE_NORMALIZED_SHA256}, got {digest}"
        )
    return {
        "engine_path": str(ENGINE_PATH),
        "pinned_commit": VERSION_COMMITS["1.32.4"],
        "normalized_sha256": digest,
        "current_commit": VERSION_COMMITS["1.32.6"],
        "current_normalized_sha256": CURRENT_ENGINE_NORMALIZED_SHA256,
        "current_json_sha256": CURRENT_JSON_SHA256,
    }


def _load_fresh_pinned_module(serial: int = 0) -> ModuleType:
    verify_pinned_source()
    if str(VENDOR_ROOT) not in sys.path:
        sys.path.insert(0, str(VENDOR_ROOT))
    name = f"_replay_kaggriculture_{serial}_{random.randrange(1 << 30)}"
    spec = importlib.util.spec_from_file_location(name, ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Kaggriculture engine from {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch_locked_shed_access(module: ModuleType) -> None:
    original = module._apply_unit_action

    def patched(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity=100):
        op = action[0] if isinstance(action, list) and action else None
        pos = module._farmer_position(farm, idx)
        if op in ("DROP", "PICKUP", "PLACE") and pos is not None:
            x, y = int(pos[0]), int(pos[1])
            if (
                farm["tiles"][y][x] == "LOCKED"
                and module._is_shed_adjacent((x, y), board_size)
            ):
                # The 1.32.5 source moved shed operations before the LOCKED
                # guard.  Temporarily exposing an empty standing tile is
                # behaviorally identical: animal placement cannot match None,
                # while DROP/PICKUP/shed-PLACE use only the coordinate.
                farm["tiles"][y][x] = None
                try:
                    return original(
                        farm, private, idx, action, board_size, day,
                        turns_per_day, shed_capacity,
                    )
                finally:
                    farm["tiles"][y][x] = "LOCKED"
        return original(
            farm, private, idx, action, board_size, day,
            turns_per_day, shed_capacity,
        )

    module._apply_unit_action = patched


def _patch_town_rebalance(module: ModuleType) -> None:
    module.MAX_SHOP_INSTANCES = 8

    def town_consume(env, state, step):
        obs0 = state[0].observation
        market = obs0.market
        town = obs0.town
        cfg = env.configuration
        shop_interval = max(1, int(module.get(cfg, "townShopSellInterval", 4)))
        center_interval = max(1, int(module.get(cfg, "townCenterSellInterval", 24)))
        if step % shop_interval == 0:
            for shop_name in town.get("unlocked_shops", []):
                products = module.SHOPS[shop_name]
                multiplier = 2 if len(products) == 1 else 1
                for item in products:
                    market["inventory"][item] -= multiplier
        if step % center_interval == 0:
            for item in module.TOWN_CENTER_PRODUCTS:
                market["inventory"][item] -= 1
        module._refresh_prices(market)

    def end_of_day(state, env, day):
        obs0 = state[0].observation
        cfg = env.configuration
        board_size = int(module.get(cfg, "boardSize", 10))
        turns_per_day = max(1, int(module.get(cfg, "turnsPerDay", 24)))
        weed_chance = float(module.get(cfg, "weedSpawnChance", 0.005))
        shed_cap = int(module.get(cfg, "shedCapacity", 100))
        shop_interval = max(1, int(module.get(cfg, "townShopUnlockInterval", 3)))
        seed = env.info.get("seed", 0)
        rng = random.Random((seed * 1_000_003) ^ day)
        for player_id, farm in enumerate(obs0.farms):
            private = state[player_id].observation.private
            module._daily_refresh_plants(farm, day, turns_per_day)
            module._daily_refresh_animals(farm, day)
            module._spawn_weeds(farm, board_size, weed_chance, rng)
            module._drop_inventories_to_shed(private, shed_cap)
            farm["farmer"] = list(module._default_spawn(board_size))
            farm["hands"] = []
            farm["hires_today"] = 0
            private["inventories"] = [{}]
        next_day = day + 1
        town = obs0.town
        if next_day > 0 and next_day % shop_interval == 0:
            if len(town["unlocked_shops"]) < module.MAX_SHOP_INSTANCES:
                town["unlocked_shops"].append(rng.choice(sorted(module.SHOPS)))

    module._town_consume = town_consume
    module._end_of_day = end_of_day


def patch_engine_module(module: ModuleType, version: str = "1.32.6") -> ModuleType:
    """Patch a pinned engine module in place to the requested replay version."""
    if version not in VERSION_COMMITS:
        raise ValueError(f"unsupported Kaggriculture replay version: {version}")
    if version in ("1.32.5", "1.32.6"):
        _patch_locked_shed_access(module)
    if version == "1.32.6":
        _patch_town_rebalance(module)
    module.REPLAY_MODULE_VERSION = version
    module.REPLAY_COMMIT = VERSION_COMMITS[version]
    return module


def load_engine(version: str, serial: int = 0) -> ModuleType:
    """Return a fresh isolated interpreter with replay-version semantics."""
    return patch_engine_module(_load_fresh_pinned_module(serial), version)


def patch_registered_engine_current() -> ModuleType:
    """Patch the registered local engine used by kaggle_environments.make."""
    if str(VENDOR_ROOT) not in sys.path:
        sys.path.insert(0, str(VENDOR_ROOT))
    from kaggle_environments.envs.kaggriculture import kaggriculture

    if getattr(kaggriculture, "REPLAY_MODULE_VERSION", None) != "1.32.6":
        patch_engine_module(kaggriculture, "1.32.6")
    return kaggriculture


def make_env_stub(configuration: dict, seed: int):
    """Minimal env object accepted by the official interpreter."""
    if str(VENDOR_ROOT) not in sys.path:
        sys.path.insert(0, str(VENDOR_ROOT))
    from kaggle_environments.utils import structify

    return SimpleNamespace(
        configuration=structify(copy.deepcopy(configuration)),
        info={"seed": int(seed)},
        done=False,
    )

