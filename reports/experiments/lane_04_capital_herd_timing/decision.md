# Lane 04 — Capital / herd timing (development smoke)

## Scope

- Isolated candidate copied from `submission/`; `control/` is an untouched
  canonical copy.  No `submission/`, `.vendor/`, `data/`, `docs/`, `dist/`, or
  shared report was modified.
- One explicit flag, `CAPITAL_HERD_TIMING_TREATMENT`, enables the treatment.
  It retains the 3C1S opening, limits post-opening buys to one animal per turn,
  targets 7C5S, and waits for an observed melon sale or the configured
  equivalent cash event.
- A post-event purchase requires: four physical wheat days for the next herd
  size; the three-day P0/basic-needs workload check; land/crop opportunity
  cost; cash to bridge animal cost plus feed through first output; and time to
  place, produce, harvest, drop, and sell before step 718.  Scheduler,
  layout, and market-order sequence were otherwise retained.

## Validation

- `python -m compileall -q experiments/lane_04_capital_herd_timing`: pass.
- Focused tests: 3/3 pass (`tests/test_capital_herd_timing.py`).
- Smoke engine: exact upstream `bded87b0d7879078c726a93a4884d044f79c4eed`
  Kaggriculture source and json are loaded from the lane-local checkout into
  the pinned harness; `.vendor` is not changed.
- Smoke matrix: seeds 1301 and 1302, both seats, treatment vs canonical
  control (4 games), treatment vs built-in `starter` (4 games), and one
  treatment-vs-control deterministic repeat (9 full 720-step games total).
  All finished `DONE` for both players.

## Matched control result

| Seed | Candidate seat-0 diff | Candidate seat-1 diff | Two-seat diff | Paired result |
|---:|---:|---:|---:|---|
| 1301 | +1,701 (24,564 vs 22,863) | +3,972 (20,425 vs 16,453) | +5,673 | win |
| 1302 | -4,872 (76,855 vs 81,727) | -6,465 (70,926 vs 77,391) | -11,337 | loss |

The treatment won 1/2 seed-pairs (2/4 seat games), with combined two-seat
difference -5,664.  This is mixed and not a positive paired-win signal; raw
reward is therefore not treated as a promotion result.  It remains a
development-only, delayed-expansion gate and is **not worth a larger matched
ablation or promotion**.

`starter` was 4/4 candidate wins (71,709–91,056 / 3,484–3,506 at seed 1301;
51,654–54,676 / 3,506 at seed 1302), which is plumbing evidence only.

## Required event telemetry

- First executed melon sale: step 264 for both control-seed games; steps
  260–264 against `starter`.  In control games the equivalent-cash event
  opened first, so post-opening buys began at step 242; this is intentional
  under the explicitly configured alternative gate and is retained as a
  design risk.
- NE/SW unlocks: control games step 128 / 218; candidate as starter-seat-0
  unlocked NE at step 121 and SW at 218.
- Purchases: 3C + 1S at step 0, then one-at-a-time C at 242, 243, 250 and S at
  251–253, followed by C/S at 270/271.  Placements and all individual orders
  are retained in `smoke_results.json`.
- Cash trough: 140 against control; 142 against starter.  Minimum observed
  physical feed runway was 0.0 days per placed animal at least once; despite
  this, no animals escaped.  Peak recorded three-day mandatory load was
  77 against a minimum capacity estimate of 42, but it occurred after the
  expansion burst rather than causing an unsafe emitted action.
- Deterministic repeat: identical rewards and both action digests.

## Safety and timing (final smoke)

Across every candidate track: malformed action 0, timeout 0, animal escape 0,
fresh-crop death 0, shed overflow 0, seed overcommit 0, and market list over
10 entries 0.  Candidate p95 agent latency was at most 1.6234 ms; maximum was
31.8160 ms.

## Preserved failure evidence

`smoke_results_invalid_module_collision.json` (SHA-256
`69BE65D23E9398D4CDCBA2BAC6D055F0A8D9D402B2D77717D16BE59E2AEF0B4B`) is an
intentionally retained invalid run.  A lazy economy import was shadowed when
the in-process harness loaded the control copy, forcing candidate fallback and
four animal escapes per game.  The cause was fixed by removing the import
cycle; the final smoke above is the valid evidence.  The invalid run must not
be used to compare strategy quality, but remains regression evidence for
multi-candidate harness imports.
