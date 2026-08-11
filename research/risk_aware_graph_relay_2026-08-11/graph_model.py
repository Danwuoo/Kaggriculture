"""Feature graph and tiny learned residuals for the relay experiment."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from engine_runner import engine


PRODUCTS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
)
GLOBAL = len(PRODUCTS)
FERTILIZER = PRODUCTS.index("FERTILIZER")
FEATURES = 10
PRODUCT_INDEX = {item: index for index, item in enumerate(PRODUCTS)}
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}


def _route_distance(obs: dict) -> float:
    def signature(farm: dict) -> tuple[int, int, list[int]]:
        keys = (
            "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "COW", "SHEEP", "GOOSE", "PASTURE", "COOP", "WEED",
        )
        counts = {key: 0 for key in keys}
        for row in farm.get("tiles", []) or []:
            for tile in row:
                if not isinstance(tile, dict):
                    continue
                for field in ("crop", "animal", "kind"):
                    value = str(tile.get(field, "")).upper()
                    if value in counts:
                        counts[value] += 1
                        break
        return (
            len(farm.get("hands", []) or []),
            len(farm.get("unlocked_quadrants", []) or []),
            [counts[key] for key in sorted(counts)],
        )

    farms = obs.get("farms", []) or []
    if len(farms) < 2:
        return 100.0
    left, right = signature(farms[0]), signature(farms[1])
    return float(
        abs(left[0] - right[0])
        + 3 * abs(left[1] - right[1])
        + sum(abs(a - b) for a, b in zip(left[2], right[2]))
    )


def _producer_counts(farm: dict) -> dict[str, int]:
    counts = {item: 0 for item in PRODUCTS}
    for row in farm.get("tiles", []) or []:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            crop = tile.get("crop")
            if crop in counts:
                counts[crop] += 1
            animal = tile.get("animal")
            product = ANIMAL_PRODUCT.get(animal)
            if product:
                counts[product] += 1
    return counts


def _demand_counts(obs: dict) -> dict[str, int]:
    demand = {item: 0 for item in PRODUCTS}
    for shop in (obs.get("town", {}) or {}).get("unlocked_shops", []) or []:
        products = engine.SHOPS.get(shop, ())
        for item in products:
            demand[item] += 2 if len(products) == 1 else 1
    return demand


def graph_features(obs: dict) -> np.ndarray:
    """Build ten public/private-own nodes without opponent-private leakage."""

    player = int(obs.get("player", 0) or 0)
    farms = obs.get("farms", []) or []
    own = farms[player]
    opponent = farms[1 - player]
    private = obs.get("private", {}) or {}
    shed = private.get("shed", {}) or {}
    market = obs.get("market", {}) or {}
    inventory = market.get("inventory", {}) or {}
    prices = market.get("prices", {}) or {}
    own_counts = _producer_counts(own)
    opponent_counts = _producer_counts(opponent)
    demand = _demand_counts(obs)
    step = float(obs.get("step", 0) or 0)
    route = _route_distance(obs)
    x = np.zeros((len(PRODUCTS) + 1, FEATURES), dtype=np.float64)
    for index, item in enumerate(PRODUCTS):
        params = engine.MARKET_PARAMS[item]
        base = max(1.0, float(params["base"]))
        throughput = max(1.0, float(params["T"]))
        x[index] = (
            float(shed.get(item, 0) or 0) / 50.0,
            (float(params["I0"]) - float(inventory.get(item, params["I0"]) or 0)) / throughput,
            float(prices.get(item, base) or 0) / base - 1.0,
            own_counts[item] / 25.0,
            opponent_counts[item] / 25.0,
            demand[item] / 8.0,
            step / 720.0,
            min(route, 60.0) / 30.0,
            1.0 if item == "FERTILIZER" else 0.0,
            1.0,
        )
    total_shed = sum(max(0, int(value or 0)) for value in shed.values())
    x[GLOBAL] = (
        total_shed / 100.0,
        float(own.get("money", 0) or 0) / 150_000.0,
        float(opponent.get("money", 0) or 0) / 150_000.0,
        len(own.get("hands", []) or []) / 10.0,
        len(opponent.get("hands", []) or []) / 10.0,
        len(own.get("unlocked_quadrants", []) or []) / 4.0,
        step / 720.0,
        min(route, 60.0) / 30.0,
        len((obs.get("town", {}) or {}).get("unlocked_shops", []) or []) / 8.0,
        1.0,
    )
    return x


def normalized_adjacency() -> np.ndarray:
    n = len(PRODUCTS) + 1
    a = np.eye(n, dtype=np.float64)

    # Global coupling: money, season, capacity and route context affect all goods.
    for index in range(len(PRODUCTS)):
        a[index, GLOBAL] = a[GLOBAL, index] = 1.0

    # Products co-demanded by a town shop transmit scarcity/glut context.
    for products in engine.SHOPS.values():
        indices = [PRODUCT_INDEX[item] for item in products if item in PRODUCT_INDEX]
        for left in indices:
            for right in indices:
                if left != right:
                    a[left, right] = 1.0

    # Production relations: fertilizer -> crops; wheat -> animal products.
    for crop in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"):
        a[FERTILIZER, PRODUCT_INDEX[crop]] = 1.0
        a[PRODUCT_INDEX[crop], FERTILIZER] = 1.0
    for product in ("EGG", "MILK", "WOOL"):
        a[PRODUCT_INDEX["WHEAT"], PRODUCT_INDEX[product]] = 1.0
        a[PRODUCT_INDEX[product], PRODUCT_INDEX["WHEAT"]] = 1.0

    degree = a.sum(axis=1)
    inv_sqrt = np.diag(1.0 / np.sqrt(np.maximum(degree, 1.0)))
    return inv_sqrt @ a @ inv_sqrt


ADJACENCY = normalized_adjacency()


class Adam:
    def __init__(self, arrays: dict[str, np.ndarray], learning_rate: float = 0.01):
        self.arrays = arrays
        self.learning_rate = learning_rate
        self.m = {key: np.zeros_like(value) for key, value in arrays.items()}
        self.v = {key: np.zeros_like(value) for key, value in arrays.items()}
        self.step = 0

    def update(self, grads: dict[str, np.ndarray]) -> None:
        self.step += 1
        for key, grad in grads.items():
            self.m[key] = 0.9 * self.m[key] + 0.1 * grad
            self.v[key] = 0.999 * self.v[key] + 0.001 * grad * grad
            m_hat = self.m[key] / (1.0 - 0.9**self.step)
            v_hat = self.v[key] / (1.0 - 0.999**self.step)
            self.arrays[key] -= self.learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)


@dataclass
class FitResult:
    train_mae: float
    validation_mae: float
    validation_sign_accuracy: float
    epochs: int


class GraphRegressor:
    """One graph-convolution layer plus fertilizer/global/mean readout."""

    kind = "gcn"

    def __init__(self, hidden: int = 32, seed: int = 7):
        rng = np.random.default_rng(seed)
        self.params = {
            "w": rng.normal(0.0, 0.15, (FEATURES, hidden)),
            "b": np.zeros(hidden),
            "v": rng.normal(0.0, 0.10, hidden * 3),
            "c": np.zeros(1),
        }
        self.target_scale = 1.0

    def _forward(self, x: np.ndarray) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
        ax = np.einsum("ij,bjf->bif", ADJACENCY, x)
        z = ax @ self.params["w"] + self.params["b"]
        h = np.tanh(z)
        pooled = np.concatenate((h[:, FERTILIZER], h[:, GLOBAL], h[:, :GLOBAL].mean(axis=1)), axis=1)
        pred = pooled @ self.params["v"] + self.params["c"][0]
        return pred, (ax, h, pooled)

    def predict(self, x: np.ndarray) -> np.ndarray:
        values = x[None, ...] if x.ndim == 2 else x
        return self._forward(values)[0] * self.target_scale

    def fit(self, x: np.ndarray, y: np.ndarray, validation: tuple[np.ndarray, np.ndarray]) -> FitResult:
        self.target_scale = max(100.0, float(np.median(np.abs(y))) if len(y) else 100.0)
        target = np.clip(y / self.target_scale, -8.0, 8.0)
        optimizer = Adam(self.params, learning_rate=0.012)
        best = None
        patience = 0
        epochs = 0
        for epoch in range(2500):
            epochs = epoch + 1
            pred, (ax, h, pooled) = self._forward(x)
            error = pred - target
            # Huber derivative limits the influence of one lucky market outcome.
            delta = np.where(np.abs(error) <= 1.0, error, np.sign(error)) / max(1, len(y))
            grads = {
                "v": pooled.T @ delta + 2e-4 * self.params["v"],
                "c": np.array([delta.sum()]),
            }
            dpool = delta[:, None] * self.params["v"][None, :]
            hidden = h.shape[-1]
            dh = np.zeros_like(h)
            dh[:, FERTILIZER] += dpool[:, :hidden]
            dh[:, GLOBAL] += dpool[:, hidden : hidden * 2]
            dh[:, :GLOBAL] += dpool[:, hidden * 2 :, None].transpose(0, 2, 1) / GLOBAL
            dz = dh * (1.0 - h * h)
            grads["w"] = np.einsum("bnf,bnh->fh", ax, dz) + 2e-4 * self.params["w"]
            grads["b"] = dz.sum(axis=(0, 1))
            optimizer.update(grads)

            if epoch % 10 == 0:
                val_x, val_y = validation
                mae = float(np.mean(np.abs(self.predict(val_x) - val_y)))
                if best is None or mae < best[0] - 1e-6:
                    best = (mae, {key: value.copy() for key, value in self.params.items()}, epoch + 1)
                    patience = 0
                else:
                    patience += 1
                if patience >= 40:
                    break
        if best is not None:
            self.params = best[1]
            epochs = best[2]
        return _fit_result(self, x, y, validation, epochs)


class FlatMLPRegressor:
    """Parameter-matched flattened-state ablation."""

    kind = "flat_mlp"

    def __init__(self, hidden: int = 4, seed: int = 7):
        rng = np.random.default_rng(seed)
        flat = (len(PRODUCTS) + 1) * FEATURES
        self.params = {
            "w": rng.normal(0.0, 0.08, (flat, hidden)),
            "b": np.zeros(hidden),
            "v": rng.normal(0.0, 0.10, hidden),
            "c": np.zeros(1),
        }
        self.target_scale = 1.0

    def _forward(self, x: np.ndarray) -> tuple[np.ndarray, tuple[np.ndarray, np.ndarray]]:
        flat = x.reshape(len(x), -1)
        h = np.tanh(flat @ self.params["w"] + self.params["b"])
        return h @ self.params["v"] + self.params["c"][0], (flat, h)

    def predict(self, x: np.ndarray) -> np.ndarray:
        values = x[None, ...] if x.ndim == 2 else x
        return self._forward(values)[0] * self.target_scale

    def fit(self, x: np.ndarray, y: np.ndarray, validation: tuple[np.ndarray, np.ndarray]) -> FitResult:
        self.target_scale = max(100.0, float(np.median(np.abs(y))) if len(y) else 100.0)
        target = np.clip(y / self.target_scale, -8.0, 8.0)
        optimizer = Adam(self.params, learning_rate=0.012)
        best = None
        patience = 0
        epochs = 0
        for epoch in range(2500):
            epochs = epoch + 1
            pred, (flat, h) = self._forward(x)
            error = pred - target
            delta = np.where(np.abs(error) <= 1.0, error, np.sign(error)) / max(1, len(y))
            grads = {
                "v": h.T @ delta + 2e-4 * self.params["v"],
                "c": np.array([delta.sum()]),
            }
            dh = delta[:, None] * self.params["v"][None, :]
            dz = dh * (1.0 - h * h)
            grads["w"] = flat.T @ dz + 2e-4 * self.params["w"]
            grads["b"] = dz.sum(axis=0)
            optimizer.update(grads)
            if epoch % 10 == 0:
                val_x, val_y = validation
                mae = float(np.mean(np.abs(self.predict(val_x) - val_y)))
                if best is None or mae < best[0] - 1e-6:
                    best = (mae, {key: value.copy() for key, value in self.params.items()}, epoch + 1)
                    patience = 0
                else:
                    patience += 1
                if patience >= 40:
                    break
        if best is not None:
            self.params = best[1]
            epochs = best[2]
        return _fit_result(self, x, y, validation, epochs)


def _fit_result(model: Any, x: np.ndarray, y: np.ndarray, validation: tuple[np.ndarray, np.ndarray], epochs: int) -> FitResult:
    train_prediction = model.predict(x)
    val_x, val_y = validation
    val_prediction = model.predict(val_x)
    sign = np.sign(val_prediction) == np.sign(val_y)
    return FitResult(
        train_mae=float(np.mean(np.abs(train_prediction - y))),
        validation_mae=float(np.mean(np.abs(val_prediction - val_y))),
        validation_sign_accuracy=float(np.mean(sign)) if len(sign) else 0.0,
        epochs=epochs,
    )


def save_model(model: Any, path: Path) -> None:
    payload = {
        "kind": model.kind,
        "target_scale": model.target_scale,
        "params": {key: value.tolist() for key, value in model.params.items()},
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_model(path: Path) -> Any:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["kind"] == "gcn":
        model = GraphRegressor(hidden=len(payload["params"]["b"]))
    elif payload["kind"] == "flat_mlp":
        model = FlatMLPRegressor(hidden=len(payload["params"]["b"]))
    else:
        raise ValueError(f"unknown model kind: {payload['kind']}")
    model.params = {key: np.asarray(value, dtype=np.float64) for key, value in payload["params"].items()}
    model.target_scale = float(payload["target_scale"])
    return model


def parameter_count(model: Any) -> int:
    return sum(int(np.prod(value.shape)) for value in model.params.values())
