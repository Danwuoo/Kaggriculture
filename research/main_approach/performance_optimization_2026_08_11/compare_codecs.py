"""Compare deterministic Base85 and Base64 standalone route codecs."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import zlib


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STRATEGIES = ("v27_current_meta", "boatlee_v16_rc2_market_relay")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cold_import(path: Path) -> float:
    code = (
        "import importlib.util,sys,time;"
        "p=sys.argv[1];s=importlib.util.spec_from_file_location('m',p);"
        "m=importlib.util.module_from_spec(s);t=time.perf_counter();"
        "s.loader.exec_module(m);print((time.perf_counter()-t)*1000)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip().splitlines()[-1])


def _decode_times(payload: bytes, decoder, repetitions: int) -> list[float]:
    values = []
    for _ in range(repetitions):
        started = time.perf_counter()
        json.loads(zlib.decompress(decoder(payload)).decode("utf-8"))
        values.append((time.perf_counter() - started) * 1000.0)
    return values


def compare(repetitions: int) -> dict:
    results = {}
    with tempfile.TemporaryDirectory(prefix="kaggriculture-codecs-") as temp:
        temp_root = Path(temp)
        for strategy in STRATEGIES:
            base = ROOT / "research/main_approach" / strategy
            builder = _load(base / "development/build_standalone.py", f"builder_{strategy}")
            rendered = {codec: builder.render(codec) for codec in ("b85", "b64")}
            paths = {}
            for codec, source in rendered.items():
                path = temp_root / f"{strategy}_{codec}.py"
                path.write_text(source, encoding="utf-8", newline="\n")
                paths[codec] = path
            cold = {"b85": [], "b64": []}
            for repetition in range(repetitions):
                order = ("b85", "b64") if repetition % 2 == 0 else ("b64", "b85")
                for codec in order:
                    cold[codec].append(_cold_import(paths[codec]))
            actions = json.loads((base / "development/route_actions.json").read_text(encoding="utf-8"))
            raw = json.dumps(actions, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            compressed = zlib.compress(raw, level=9)
            payloads = {
                "b85": base64.b85encode(compressed),
                "b64": base64.b64encode(compressed),
            }
            decode = {
                "b85": _decode_times(payloads["b85"], base64.b85decode, repetitions * 5),
                "b64": _decode_times(payloads["b64"], base64.b64decode, repetitions * 5),
            }
            modules = {codec: _load(path, f"route_{strategy}_{codec}") for codec, path in paths.items()}
            digest = lambda route: hashlib.sha256(json.dumps(route, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            route_digests = {codec: digest(module._LEGACY_ACTIONS) for codec, module in modules.items()}
            results[strategy] = {
                "raw_bytes": len(raw),
                "compressed_bytes": len(compressed),
                "payload_bytes": {codec: len(value) for codec, value in payloads.items()},
                "artifact_bytes": {codec: len(source.encode("utf-8")) for codec, source in rendered.items()},
                "deterministic_render": {codec: rendered[codec] == builder.render(codec) for codec in rendered},
                "route_digests": route_digests,
                "route_equal": len(set(route_digests.values())) == 1,
                "cold_import_ms": {
                    codec: {"median": statistics.median(values), "min": min(values), "max": max(values), "raw": values}
                    for codec, values in cold.items()
                },
                "decode_json_ms": {
                    codec: {"median": statistics.median(values), "min": min(values), "max": max(values), "raw": values}
                    for codec, values in decode.items()
                },
            }
    supported = all(
        row["route_equal"]
        and all(row["deterministic_render"].values())
        and row["artifact_bytes"]["b64"] < 5 * 1024 * 1024
        and row["cold_import_ms"]["b64"]["median"] < row["cold_import_ms"]["b85"]["median"]
        and row["decode_json_ms"]["b64"]["median"] < row["decode_json_ms"]["b85"]["median"]
        for row in results.values()
    )
    return {"decision": "BASE64" if supported else "BASE85", "repetitions": repetitions, "strategies": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=21)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": result["decision"],
        "strategies": {
            strategy: {
                "b85_cold_ms": row["cold_import_ms"]["b85"]["median"],
                "b64_cold_ms": row["cold_import_ms"]["b64"]["median"],
                "b85_decode_ms": row["decode_json_ms"]["b85"]["median"],
                "b64_decode_ms": row["decode_json_ms"]["b64"]["median"],
                "b85_bytes": row["artifact_bytes"]["b85"],
                "b64_bytes": row["artifact_bytes"]["b64"],
            }
            for strategy, row in result["strategies"].items()
        },
    }, indent=2))


if __name__ == "__main__":
    main()
