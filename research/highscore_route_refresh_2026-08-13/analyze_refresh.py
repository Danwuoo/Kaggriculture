"""Compact, public-information analysis of the 2026-08-13 high-score refresh."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LANE = Path(__file__).resolve().parent
CURRENT_CACHE = ROOT / "research" / "cache" / "highscore_route_refresh_2026-08-13"
OLD_SNAPSHOT = ROOT / "data" / "public_replays" / "top50-2026-08-09" / "leaderboard_snapshot.json"
ARCHIVED_OLD_SUMMARY = Path(r"C:\Users\wurre\Desktop\Kaggriculture-archive\2026-08-10\reports\replay_clone_study\top50_summary.json")
ASSETS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "GOOSE", "COW", "SHEEP")
SHARED_UNIT = "7a200e767030483fb65faeb4060ac4b6bc6580b9ca493180d067c43fdd07ca30"
ENGINE = {
    "commit": "bded87b0d7879078c726a93a4884d044f79c4eed",
    "python_blob": "4b78842d0f2d4abf6e318a8248b6306454f5c714",
    "configuration_blob": "0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8",
    "python_sha256": "fb9215c5e21a25243e2d13e75b3d70a79cf7d78fff150a90f1bb5eacf9ba2bcf",
    "configuration_sha256": "7f196f4aaf9b4e482fbd61ba4bf19f5cec4da0f81938ece756954035a65c0bb5",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def feature(row: dict[str, Any]) -> dict[str, Any]:
    with gzip.open(CURRENT_CACHE / Path(row["feature_path"]), "rt", encoding="utf-8") as stream:
        return json.load(stream)


def actions(row: dict[str, Any]) -> list[dict[str, Any]]:
    path = CURRENT_CACHE / "corpus" / "tapes" / f"{row['full_tape']}.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        result = json.load(stream)["actions"]
    if digest(result) != row["full_tape"]:
        raise ValueError(f"tape digest mismatch for rank {row['rank']}")
    return result


def unit_tape(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"farmer": row["farmer"], "hands": row["hands"]} for row in rows]


def normalized_unit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        hands = [list(action) for action in row["hands"]]
        while hands and hands[-1] == ["PASS"]:
            hands.pop()
        result.append({"farmer": row["farmer"], "hands": hands})
    return result


def historical_unit_sha256(rows: list[dict[str, Any]]) -> str:
    """Match the correctly aligned schema used by the archived Top-50 audit."""
    return digest([[row["farmer"], row["hands"]] for row in rows])


def route_profile(row: dict[str, Any]) -> dict[str, Any]:
    signatures = feature(row)["route"]["daily_public_signatures"]
    peak = {name: max(int(item["assets"][index]) for item in signatures) for index, name in enumerate(ASSETS)}
    unlock_days: list[int] = []
    last_land = int(signatures[0]["land"])
    for item in signatures[1:]:
        land = int(item["land"])
        if land > last_land:
            unlock_days.extend([int(item["day"])] * (land - last_land))
            last_land = land
    return {"peak_assets": peak, "land_unlock_days": unlock_days}


def action_profile(row: dict[str, Any], incumbent_units: list[dict[str, Any]]) -> dict[str, Any]:
    tape = actions(row)
    units = unit_tape(tape)
    ops: Counter[str] = Counter()
    market_orders: Counter[str] = Counter()
    issued_quantities: Counter[str] = Counter()
    for action in tape:
        for unit_action in [action["farmer"], *action["hands"]]:
            ops[str((unit_action or ["PASS"])[0])] += 1
        for order in action["market"]:
            if not order:
                continue
            op = str(order[0])
            item = str(order[1]) if len(order) > 1 else ""
            key = f"{op}:{item}" if item else op
            market_orders[key] += 1
            if len(order) > 2:
                issued_quantities[key] += max(0, int(order[2]))
    exact = sum(left == right for left, right in zip(units, incumbent_units))
    first_difference = next((index for index, (left, right) in enumerate(zip(units, incumbent_units)) if left != right), None)
    return {
        **route_profile(row),
        "unit_operations": dict(sorted(ops.items())),
        "issued_market_order_counts": dict(sorted(market_orders.items())),
        "issued_market_quantities": dict(sorted(issued_quantities.items())),
        "incumbent_exact_unit_turns": exact,
        "incumbent_first_unit_difference": first_difference,
        "normalized_unit_sha256": digest(normalized_unit(tape)),
    }


def profile_key(profile: dict[str, Any]) -> str:
    peaks = profile["peak_assets"]
    return digest({"peaks": [peaks[name] for name in ASSETS], "land": profile["land_unlock_days"]})


def market_variation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tapes = [actions(row) for row in rows]
    equal_steps = []
    for left_index in range(len(tapes)):
        for right_index in range(left_index + 1, len(tapes)):
            equal_steps.append(sum(a["market"] == b["market"] for a, b in zip(tapes[left_index], tapes[right_index])))
    variable_steps = sum(len({canonical(tape[step]["market"]) for tape in tapes}) > 1 for step in range(719))
    return {
        "members": len(rows),
        "unique_market_tapes": len({row["market_tape"] for row in rows}),
        "market_variable_steps": variable_steps,
        "pairwise_equal_market_steps_min": min(equal_steps, default=719),
        "pairwise_equal_market_steps_median": statistics.median(equal_steps) if equal_steps else 719,
        "pairwise_equal_market_steps_max": max(equal_steps, default=719),
    }


def run(output: Path) -> dict[str, Any]:
    rows = sorted(read_jsonl(CURRENT_CACHE / "corpus" / "manifest.jsonl"), key=lambda row: int(row["rank"]))
    old_snapshot = json.loads(OLD_SNAPSHOT.read_text(encoding="utf-8"))["rows"][:50]
    if not ARCHIVED_OLD_SUMMARY.is_file():
        raise FileNotFoundError(f"restore archived Top-50 audit before historical comparison: {ARCHIVED_OLD_SUMMARY}")
    old_summary_bytes = ARCHIVED_OLD_SUMMARY.read_bytes()
    old_summary = json.loads(old_summary_bytes.decode("utf-8"))
    old_unit_hashes = {str(row["unit_action_sha256"]) for row in old_summary["summaries"]}
    old_by_team = {int(row["team_id"]): row for row in old_snapshot}
    incumbent_actions = json.loads((ROOT / "research" / "main_approach" / "v27_current_meta" / "development" / "route_actions.json").read_text(encoding="utf-8"))
    incumbent_units = unit_tape(incumbent_actions)
    other_actions = json.loads((ROOT / "research" / "main_approach" / "boatlee_v16_rc2_market_relay" / "development" / "route_actions.json").read_text(encoding="utf-8"))
    if incumbent_actions != other_actions:
        raise RuntimeError("active incumbent readable routes diverged; analyze them independently")

    historical_hashes = {int(row["rank"]): historical_unit_sha256(actions(row)) for row in rows}
    profile_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    profiles: dict[int, dict[str, Any]] = {}
    for row in rows:
        profile = route_profile(row)
        profiles[int(row["rank"])] = profile
        profile_groups[profile_key(profile)].append(row)
    macro_profiles = []
    for grouped in sorted(profile_groups.values(), key=lambda group: (-len(group), min(int(row["rank"]) for row in group))):
        representative = profiles[int(grouped[0]["rank"])]
        macro_profiles.append({
            "support": len(grouped),
            "ranks": sorted(int(row["rank"]) for row in grouped),
            **representative,
        })

    shared = [row for row in rows if row["unit_tape"] == SHARED_UNIT]
    selected = {
        "rank1_10c4s": rows[0],
        "dominant_8c4s": min(shared, key=lambda row: int(row["rank"])),
    }
    overlap = []
    for row in rows:
        old = old_by_team.get(int(row["team_id"]))
        if old:
            overlap.append({
                "current_rank": int(row["rank"]), "team_name": row["team_name"],
                "old_rank": int(old["rank"]), "old_score": float(old["leaderboard_score"]),
                "current_score": float(row["leaderboard_score"]),
            })

    audit = json.loads((CURRENT_CACHE / "corpus" / "corpus_audit.json").read_text(encoding="utf-8"))
    snapshot = json.loads((CURRENT_CACHE / "coverage" / "leaderboard_snapshot.json").read_text(encoding="utf-8"))
    result = {
        "schema_version": 1,
        "captured_at": snapshot["captured_at"],
        "engine": ENGINE,
        "cohort": {
            "selected_replays": len(rows),
            "ranks": [int(row["rank"]) for row in rows],
            "module_versions": audit["module_versions"],
            "raw_processed_bytes": int(audit["raw_processed_bytes"]),
            "raw_retained_success_bytes": int(audit["raw_retained_success_bytes"]),
            "old_top50_team_overlap": overlap,
            "historical_comparison": {
                "source": str(ARCHIVED_OLD_SUMMARY),
                "source_sha256": hashlib.sha256(old_summary_bytes).hexdigest(),
                "old_top50_correctly_aligned_unit_families": len(old_summary["clusters"]["unit_action"]),
                "current_exact_unit_matches_old_top50": sum(value in old_unit_hashes for value in historical_hashes.values()),
                "current_exact_unit_novel_vs_old_top50": sum(value not in old_unit_hashes for value in historical_hashes.values()),
                "excluded_source": "research/cache/full_tape_topology_scaleup_2026-08-10 tape digests used replay rows 0..718 and are not alignment-comparable",
            },
        },
        "cluster_counts": {
            "full_tape": len(audit["full_tape_clusters"]),
            "unit_tape": len(audit["unit_tape_clusters"]),
            "market_tape": len(audit["market_tape_clusters"]),
            "route_family": len(audit["route_family_clusters"]),
        },
        "macro_profiles": macro_profiles,
        "shared_exact_unit_backbone": {
            "sha256": SHARED_UNIT,
            "support": len(shared),
            "ranks": [int(row["rank"]) for row in shared],
            "teams": [str(row["team_name"]) for row in shared],
            "market_variation": market_variation(shared),
        },
        "incumbent_route": {
            "unit_sha256": digest(incumbent_units),
            "full_sha256": digest(incumbent_actions),
        },
        "candidate_profiles": {
            name: {
                "rank": int(row["rank"]), "team_name": row["team_name"],
                "leaderboard_score": float(row["leaderboard_score"]),
                "selected_episode_reward": float(row["target_reward"]),
                "episode_id": int(row["episode_id"]),
                "full_tape": row["full_tape"], "unit_tape": row["unit_tape"],
                "market_tape": row["market_tape"], "route_family": row["family"],
                "historical_unit_sha256": historical_hashes[int(row["rank"])],
                **action_profile(row, incumbent_units),
            }
            for name, row in selected.items()
        },
        "information_boundary": "Only target-player public actions and public farm signatures are analyzed. No opponent private replay observation is read or stored.",
        "limitations": [
            "one selected high-reward public episode per team",
            "issued market quantities are not treated as executed quantities",
            "leaderboard score is not an episode reward",
            "an exact replay tape is not automatically a state-compatible runtime policy",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=LANE / "artifacts" / "analysis.json")
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({
        "selected_replays": result["cohort"]["selected_replays"],
        "historical_comparison": result["cohort"]["historical_comparison"],
        "cluster_counts": result["cluster_counts"],
        "top_macro_profiles": result["macro_profiles"][:4],
        "shared_exact_unit_backbone": result["shared_exact_unit_backbone"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
