# Family 1 Stage 1 completion report

Status: **COMPLETE**. This is an isolated experimental candidate, not a promotion decision.

## Outcome

The frozen final source `9812e50b210f6f1fe49b4f57dd048749460d08b731823761ca7f21cc45799606` completed the required 32 seeds × 2 seats × 5 core opponents = **320 official-engine games**. Candidate-side safety, malformed-output, timeout, semantic-no-op, seed-overcommit, market-cap, overflow-discard, and audit-error counts were all zero.

Competitive performance was poor and is retained without pruning: **4 wins, 0 ties, 316 losses** (1.2500%); Wilson 95% CI [0.4871%, 3.1694%]. The seat-paired result was 2-0-158 over 160 pairs, with Wilson 95% CI [0.3435%, 4.4425%]. Stage 1 has no competitive kill threshold: its gate is the executable substrate plus the full no-early-kill evidence matrix.

## Implementation scope

- `candidate/route_memory.py`: identity-free public signatures, three macro prototypes, deterministic selection, checkpoint distance, bounded handoff/rejoin/abandon state, and in-memory telemetry.
- `candidate/controller.py`: route-memory macro overlay before the unchanged safety scheduler and final legality projection.
- `candidate/strategy.py`: prototype-selectable crop targets and animal sequences.
- `candidate/scheduler.py`: same-turn local target claiming to prevent co-located duplicate PLACE actions, and transactional PLANT-to-same-planter WATER recovery.
- `run_stage1.py`: fixed official matrix, both-seat process isolation, Wilson statistics, latency and route telemetry, and official-engine semantic silent-no-op shadow audit.
- `tests/`: the 18 control safety/rule tests plus six route-memory and scheduler regressions.
- `build_candidate.py`, `validate_stage1.py`, and this summarizer: deterministic packaging, extracted import/full-game verification, control isolation, and reproducible evidence generation.

The canonical `submission/` sources and verified `dist/submission.tar.gz` match their baseline hashes. No candidate file was copied into `submission/`.

## Protocol and statistics

| Opponent | W-T-L | Win rate | Wilson 95% | Median diff | Lower-decile diff |
|---|---:|---:|---:|---:|---:|
| kaito_v20 | 0-0-64 | 0.00% | [0.00%, 5.66%] | -96828 | -112474.4 |
| kaito_v21 | 0-0-64 | 0.00% | [0.00%, 5.66%] | -102407 | -122302.1 |
| roman_lb950 | 4-0-60 | 6.25% | [2.46%, 15.00%] | -13310 | -32910.2 |
| saiteja_2600 | 0-0-64 | 0.00% | [0.00%, 5.66%] | -100060 | -114981.6 |
| saiteja_3000 | 0-0-64 | 0.00% | [0.00%, 5.66%] | -78318 | -91804.7 |

Overall terminal difference: mean -79195.4, median -89953.0, lower decile -112762.4, range [-130692, 11447]. All 32 development seeds and all 316 losing cases remain in the official JSON.

Route-style diagnostics:

- `balanced_hybrid`: 0-0-134 over 134 games; mean diff -88852.4; median -101239.0; final modes {'abandoned': 134}.
- `crop_demand`: 3-0-125 over 128 games; mean diff -76412.2; median -89659.0; final modes {'abandoned': 11, 'active': 117}.
- `livestock_frontier`: 1-0-57 over 58 games; mean diff -63026.4; median -80079.5; final modes {'abandoned': 58}.

## Safety, latency, and reproducibility

The final matrix had zero candidate malformed actions, escapes, fresh-crop deaths, shed overflow states, semantic no-ops, seed overcommits, market-list overflows, discarded overflow units, and audit errors. Maximum shed load was 95. The known `saiteja_2600` stress opponent emitted 1344 malformed actions; these are recorded separately and are not attributed to the candidate.

Across 230080 candidate calls under 10-worker offline contention, latency was p50 2.490 ms, p95 9.258 ms, p99 15.157 ms, max 191.896 ms, with 0 calls at or above one second.

Two seed-777 self-play trials reproduced identical statuses, rewards, and per-seat action digests. The deterministic archive is 21386 bytes with SHA-256 `6c68e3e1a036a795cb3ff7ad9d0348d90d9a585547502adbeb9b721aadf8f5da`; two consecutive builds matched byte-for-byte. It contains `main.py` at archive root, imports after extraction, and its extracted candidate completed seed 424242 against `starter` with statuses ['DONE', 'DONE'] and rewards [82078.0, 3510.0].

## Failure analysis and retained evidence

The non-eliminating smoke used all eight fixed smoke seeds, both seats, and all five core opponents: 80 games ending 1-0-79, with zero candidate safety/no-op/audit failures. Its poor result did not eliminate the family; work continued through the required full matrix.

The first semantic probe exposed duplicate PLACE attempts from co-located hands. A local per-turn target-claim ledger removed the collision; the fixed smoke and both full matrices report zero semantic no-ops.

The first 320-game candidate `9a893c100ddaad71bd9d8b02fb9ec24bc9816d342819201a5c51be3d39d22874` ended 9-0-311 but was rejected, not hidden: it had two fresh-crop deaths at seed 100027, candidate seat 0, against `kaito_v21` and `roman_lb950`. Replay audit showed a late WHEAT plant at day 12 hour 20 whose planter was reassigned at hour 21. The scheduler now pins a same-planter WATER tail after recovery planting. The four-game fixed regression (seed 100027, both seats, both affected opponents) had zero safety/no-op/audit failures, after which the entire 320-game matrix was rerun under the final source hash.

The dominant competitive failure is structural rather than variance: only `roman_lb950` was beaten (4/64); every other core opponent was 0/64. Telemetry recorded 203 abandonments, 0 successful rejoins, 13550 critical safety overrides, and 55363 scheduler-handoff steps. Inference: the hand-authored checkpoint targets and selector do not reproduce the public agents' capital/logistics trajectories closely enough, and the route overlay frequently yields to safety work. This is precisely the Stage 2 route-bank, selector, and recovery problem; Stage 1 evidence does not justify promotion.

## Provenance and remaining uncertainty

`PROVENANCE.md` identifies the public notebooks and local extraction manifest. Their metadata declares no explicit content license, so no notebook source, action tape, or learned coefficient was copied. Only independently written route-level concepts and aggregate public trace facts were used. The official engine was pinned to and rechecked upstream at commit `a4dce5ae6e2ffe3c1afea8ec4b24b562df74cc07` on 2026-08-06.

Still unproven: competitive efficacy; a complete official daily top-episode route bank; a strong identity-free selector; successful route rejoin; Stage 2 validation seeds; Stage 3 holdout and promotion gates. Family 1 Stage 2 remains PENDING, and this candidate must not enter `submission/` without the later Stage 3 procedure and explicit authorization.

## Reproduction and evidence

Run the commands in `experiments/family_1_route_memory/README.md`. The machine-readable gate index is `reports/experiments/family_1/stage1_evidence.json`; exact games and retained losses are in `stage1_official_320.json`. The rejected unsafe matrix is preserved as `stage1_official_320_failed_fresh_crop_deaths.json`.
