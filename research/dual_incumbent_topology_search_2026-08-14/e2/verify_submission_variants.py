"""Verify the independently packaged Boatlee E2 submission variants."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ASYNC_V3 = HERE.parent / "async_v3"
sys.path[:0] = [str(HERE), str(ASYNC_V3)]

import formal_s1 as s1  # noqa: E402
from authority import payload_hash  # noqa: E402
from build_submission_variants import VARIANTS, build  # noqa: E402
from materialize import isolated_import, static_audit  # noqa: E402


OUTPUT = HERE / "submission_variant_verification.json"
TECHNICAL_SEED = 811407
LANE = "boatlee_v16_rc2_market_relay"
OPPONENT = ROOT / "research" / "main_approach" / "v27_current_meta" / "main.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _technical_view(summary: dict[str, Any], seat: int) -> dict[str, Any]:
    checks = {
        "done": summary["statuses"] == ["DONE", "DONE"],
        "calls_719": int(summary["calls"]) == 719,
        "no_exception": summary["exception"] is None,
        "opponent_no_exception": summary["opponent_exception"] is None,
        "no_timeout": int(summary["timeout_calls"]) == 0,
        "no_overage_exhaustion": not bool(summary["overage_exhausted"]),
        "valid_action_schema": not any(summary["action_issues"].values()),
        "market_cap": int(summary["max_market_orders"]) <= 10,
    }
    return {
        "seat": seat,
        "pass": all(checks.values()),
        "checks": checks,
        "statuses": summary["statuses"],
        "rewards": summary["rewards"],
        "money": summary["money"],
        "action_digest": summary["action_digest"],
        "max_market_orders": summary["max_market_orders"],
        "latency_ms": summary["latency_ms"],
    }


def verify() -> dict[str, Any]:
    build_result = build(check=True)
    engine = s1.RUNNER.assert_engine_current()
    variants: dict[str, Any] = {}
    original_opponent_path = s1.RUNNER.opponent_path
    try:
        s1.RUNNER.opponent_path = lambda _lane, _family: OPPONENT
        for name, metadata in VARIANTS.items():
            source = Path(metadata["directory"]) / "main.py"
            entries = sorted(path.name for path in source.parent.iterdir())
            with tempfile.TemporaryDirectory(prefix=f"e2-{name}-archive-") as temporary:
                extracted = Path(temporary) / "main.py"
                extracted.write_bytes(source.read_bytes())
                imported = isolated_import(extracted)
                games = []
                for seat in (0, 1):
                    run = s1.RUNNER.run_game(
                        LANE,
                        extracted,
                        "other_incumbent",
                        TECHNICAL_SEED,
                        seat,
                        capture_trace=False,
                    )
                    games.append(_technical_view(run.summary, seat))
            audit = static_audit(source)
            checks = {
                "directory_contains_only_main_py": entries == ["main.py"],
                "hash_matches_frozen_candidate": _sha256(source) == metadata["sha256"],
                "under_5_mib": source.stat().st_size < 5 * 1024 * 1024,
                "isolated_import": imported == {"callable_agent": True, "isolated": True},
                "standard_library_contract": audit["pass"],
                "both_seats_official_engine": all(game["pass"] for game in games),
            }
            variants[name] = {
                "candidate_id": metadata["candidate_id"],
                "path": str(source),
                "bytes": source.stat().st_size,
                "sha256": _sha256(source),
                "directory_entries": entries,
                "static_audit": audit,
                "isolated_import": imported,
                "official_engine_games": games,
                "checks": checks,
                "pass": all(checks.values()),
            }
    finally:
        s1.RUNNER.opponent_path = original_opponent_path

    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "e2_boatlee_submission_variants_verification",
        "technical_seed": TECHNICAL_SEED,
        "technical_seed_role": "correctness_only",
        "opponent": {
            "lane": "v27_current_meta",
            "path": str(OPPONENT),
            "sha256": _sha256(OPPONENT),
        },
        "engine_fingerprint": engine,
        "build": build_result,
        "variants": variants,
        "formal_fresh_seeds_executed": False,
        "kaggle_submission_executed": False,
        "pass": all(row["pass"] for row in variants.values()),
    }
    payload["verification_sha256"] = payload_hash(payload)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return payload


def main() -> None:
    print(json.dumps(verify(), sort_keys=True))


if __name__ == "__main__":
    main()
