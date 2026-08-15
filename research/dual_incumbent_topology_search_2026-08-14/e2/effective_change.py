"""Economic effective-change classification for paired E2 evidence."""

from __future__ import annotations

import json
from typing import Any

from authority import source_run


NOOP_ID = "ac_bad79e4d71965c86b6b351a1"
BOATLEE_ID = "ac_3aa759d7d7fc4a409c409326"
V27_PROBE_ID = "ac_46448f767f398cc4ce8047d3"


def classify_result(candidate_id: str, result: dict[str, Any]) -> dict[str, Any]:
    candidate = result["evidence"]
    control = result["control"]["evidence"]
    terminal_changed = any(
        float(result[key]) != float(result["control"][key])
        for key in ("own_reward", "opponent_reward", "own_bank", "opponent_bank")
    )
    changes = {
        "action": candidate.get("action_digest") != control.get("action_digest"),
        "receipt": candidate.get("receipt_digest") != control.get("receipt_digest"),
        "public_economic_state": candidate.get("state_digest") != control.get("state_digest"),
        "terminal_bank_or_reward": terminal_changed,
        "economic_diagnostics": candidate.get("economic_diagnostics") != control.get("economic_diagnostics"),
    }
    effective = any(changes[key] for key in changes if key != "action")
    return {
        "candidate_id": candidate_id, "changes": changes, "effective": effective,
        "action_only_noop": changes["action"] and not effective,
        "efficacy_eligible": effective and candidate_id != NOOP_ID,
        "executed_edit_observed": changes["receipt"] or changes["public_economic_state"] or terminal_changed,
    }


def frozen_e1c_records() -> list[dict[str, Any]]:
    run = source_run()
    cache = json.loads((run / "candidate_context_cache.json").read_text(encoding="utf-8"))["contexts"]
    retained = {NOOP_ID, BOATLEE_ID, V27_PROBE_ID}
    rows: list[dict[str, Any]] = []
    for entry in cache.values():
        candidate_id = entry["candidate_id"]
        if candidate_id not in retained:
            continue
        shard = run / "formal" / "candidates" / "shards" / f"{entry['job_id']}.json"
        payload = json.loads(shard.read_text(encoding="utf-8"))
        record = classify_result(candidate_id, payload["result"])
        record["context"] = entry["context"]
        record["job_id"] = entry["job_id"]
        rows.append(record)
    return sorted(rows, key=lambda row: (row["candidate_id"], json.dumps(row["context"], sort_keys=True)))


def effective_change_audit() -> dict[str, Any]:
    rows = frozen_e1c_records()
    grouped = {
        candidate_id: [row for row in rows if row["candidate_id"] == candidate_id]
        for candidate_id in (BOATLEE_ID, V27_PROBE_ID, NOOP_ID)
    }
    frontiers = {
        "robust": [BOATLEE_ID],
        "diagnostic_high_upside": [V27_PROBE_ID],
        "selector_labels": [],
        "excluded": [NOOP_ID],
    }
    checks = {
        "boatlee_effective_all_contexts": len(grouped[BOATLEE_ID]) == 8 and all(row["effective"] for row in grouped[BOATLEE_ID]),
        "v27_probe_effective_all_contexts": len(grouped[V27_PROBE_ID]) == 8 and all(row["effective"] for row in grouped[V27_PROBE_ID]),
        "noop_action_only_all_contexts": len(grouped[NOOP_ID]) == 8 and all(row["action_only_noop"] for row in grouped[NOOP_ID]),
        "noop_in_no_efficacy_frontier": all(NOOP_ID not in values for key, values in frontiers.items() if key != "excluded"),
    }
    return {"pass": all(checks.values()), "checks": checks, "records": rows, "frontiers": frontiers}
