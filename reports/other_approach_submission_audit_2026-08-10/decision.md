# Other Approach standalone submission audit — 2026-08-10

## Decision

The isolated standalone candidate passed the current-engine submission gate after two narrow safety projections and was submitted to Kaggle as submission **55410356**. The first server-side status check was `PENDING`.

This is a submission experiment, not a promotion decision. The one-seed public-agent comparison was mixed relative to exact adaptive and is not evidence that this route should replace the adaptive research incumbent or production control.

Production `submission/`, `dist/`, `.vendor/`, `data/`, and `docs/` were not modified.

## What the file actually is

The original `scripts/other appoach/main.py` is a standalone compressed 719-action tape controller with a small runtime overlay:

- Original source SHA-256: `403561FC61DBDC22262D2C6508A2816E08B49371397FDF4BCF88A439BC028757`.
- Final audited source SHA-256: `0138B516F265250B55EFC84C7849C36E7B54045D171A54B8D81022F6322C43E7`.
- Embedded tape SHA-256 remained `9080682756f5b9fc0f2cae25efdffa69474d40883f693b49f58be2c1893ae5d2`.
- The tape is not adaptive farming, Preempt-H6, zero-to-top, or v25. It opens with four HIRE orders, one cow, four sheep, five wheat seeds, five melon seeds, and five wheat products.
- `_REBALANCE_ACTIONS` is the same object as `_LEGACY_ACTIONS`; there is no separate 24-turn route tape. The current-engine branch changes SELL scoring/ranking, not the underlying route.
- SELL ranking preserves non-SELL market slots and only permutes existing SELL slots. It does not preempt, add terminal liquidation, skip price-floor sales, or alter quantities.
- Static imports are standard-library only: `base64`, `copy`, `json`, `math`, and `zlib`. There are no `open`, dynamic import, subprocess, network, or runtime file-write calls.
- The raw tape contains 168 SELL orders on 100 turns and never exceeds the engine's 10-order market cap.

This is therefore a whole-route candidate with a current-market SELL-order overlay, not a market-only one-factor variant of adaptive.

## Pre-guard rejection and fixes

The first complete audit was rejected and preserved as `results_pre_guard_invalid.json`:

- One fresh strawberry died at day refresh. A hand planted at step 284, then remained on the crop and emitted PASS through step 287; the crop became a weed at step 288.
- Three aggregate seed-overcommit units were emitted. Reproducible examples occurred at step 190 with zero strawberry seeds and at step 272 with zero melon seeds.

Two narrow final-boundary projections were added to the standalone file:

1. If aggregate PLANT requests for a crop exceed available seeds, all PLANT requests for that crop become PASS. This matches the engine's existing atomic cancellation result.
2. On the last turn of a day, a unit standing on a fresh unwatered crop emits WATER, and a same-turn PLANT request is suppressed because it cannot be watered before refresh.

The embedded tape, non-safety market logic, and production files were unchanged.

## Current-engine validation

Engine fingerprint:

- Commit: `bded87b0d7879078c726a93a4884d044f79c4eed`
- Normalized Python SHA-256: `FB9215C5E21A25243E2D13E75B3D70A79CF7D78FFF150A90F1BB5EACF9BA2BCF`
- JSON SHA-256: `7F196F4AAF9B4E482FBD61BA4BF19F5CEC4DA0F81938ECE756954035A65C0BB5`
- Explicit configuration: 720 episode steps, 24 turns/day, `townCenterSellInterval=24`, shop interval 4, shed capacity 100, and market-order cap 10.

The final matrix covered 21 candidate games and 15,099 candidate calls:

- One complete self-play game.
- Starter and random: three seeds, both seats, 12 games total.
- Exact live Kaito v21, Saiteja 3000, and Roman: one fresh seed, both seats, six games total.
- Two repeated exact Kaito games for determinism.
- Six additional exact adaptive reference games on the same public-agent seed and seats.

All 21 candidate games recorded 720 states, 719 calls, and `DONE/DONE`. Totals were zero for malformed actions, market lists above 10, seed overcommit, animal escapes, fresh-crop deaths, observed shed overflow, candidate-attributed DROP/EOD discarded overflow, and timeouts. The repeated game had identical rewards and action digest.

Latency across all 15,099 calls was p50 **0.1679 ms**, p95 **0.3552 ms**, p99 **0.6661 ms**, maximum **1.1746 ms**. The designated full episode was p50 **0.1672 ms**, p95 **0.3004 ms**, p99 **0.6383 ms**, maximum **0.9070 ms**.

An additional 20-run random-agent stress block also passed with zero safety, schema, seed-ledger, overflow, and timeout findings. Candidate rewards ranged from 91,826 to 171,675, illustrating that this fixed route remains sensitive to market/opponent variation even when safe.

## Competitive signal

Against starter the candidate won 6/6 with mean margin +162,916.3. Against random it won 6/6 with mean margin +150,701.3.

On the single fresh public-agent seed, both the candidate and exact adaptive won all six direct games. Candidate-minus-adaptive margin deltas were:

| Family | Candidate margins | Adaptive margins | Paired mean delta |
| --- | ---: | ---: | ---: |
| Kaito v21 | +13,587 / +13,587 | +6,215 / +6,215 | **+7,372.0** |
| Saiteja 3000 | +30,363 / +30,413 | +30,740 / +30,802 | **-383.0** |
| Roman | +73,645 / +78,630 | +101,424 / +102,216 | **-25,682.5** |

This is a mixed margin result with no paired-win improvement: Kaito is favorable, Saiteja is approximately flat/slightly negative, and Roman is materially worse. With one seed and all games already wins, it does not support competitive promotion or preparation as the main candidate archive.

## Package and submission

The isolated deterministic archive is `research/other_approach_submission_audit_2026-08-10/artifacts/other_approach_submission.tar.gz`:

- Size: 12,211 bytes.
- SHA-256: `8594ABF803D0658AF85DB6C2708113287EC08E19C046F272454B29B202EDB274`.
- Sole archive member: root-level `main.py`.
- Extracted `main.py` matched the source SHA exactly.
- A full current-engine game loaded from the extracted archive completed 720 states with `DONE/DONE`, rewards 157,753 versus 3,516.

Kaggle submission:

- Reference: **55410356**
- Filename: `other_approach_submission.tar.gz`
- Description: `Other approach tape + current-market rebalance; safety-gated`
- Submitted at: `2026-08-10 15:17:22.830000` (Kaggle CLI output)
- First observed status: `SubmissionStatus.PENDING`

## Evidence files

- `results.json`: final complete matrix and exact per-game evidence.
- `results_pre_guard_invalid.json`: preserved failed pre-guard matrix.
- `random_stress.json`: 20-run post-guard random-agent stress evidence.
- `package_smoke.json`: archive membership, hashes, and extracted-package full-game smoke.
- `run_audit.py`: isolated reproducible runner.

## Follow-up original-file submission

At the user's explicit request, `scripts/other appoach/original/main.py` was subsequently packaged and submitted without adding the safety guards described above.

- Original-file source SHA-256: `F48C21166EAC68D1B05A401F04F94A2EB6154E65415AF64893672365FF33C7B8`.
- Archive: `research/other_approach_submission_audit_2026-08-10/artifacts/other_approach_original_submission.tar.gz`.
- Archive size: 12,052 bytes.
- Archive SHA-256: `10B5D23AEA7B6A396212918C9340EE9710C78D30DA1EA4842EE4CBB1765146DE`.
- Archive member: root-level `main.py`; extracted bytes matched the requested source.
- Current-engine extracted-package smoke: 720 states, `DONE/DONE`, rewards 137,701 versus 3,514.
- Kaggle reference: **55410495**.
- Description: `Original other approach; unmodified unguarded baseline`.
- First observed status: `SubmissionStatus.PENDING`.

This follow-up submission is intentionally the unguarded baseline. The earlier safety findings remain applicable; its successful smoke game does not supersede the retained invalid matrix.
