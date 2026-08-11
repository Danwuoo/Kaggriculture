# Counterfactual market residual — decision

Date: 2026-08-10  
Status: **REJECT_ALL_SCREEN_ARMS; STOP_WITHOUT_HOLDOUT; no production promotion.**

## Decision

No market-only treatment passed the predeclared screen. The exact adaptive
3->2->1 controller remains the research incumbent. Do not prepare a candidate
archive from this lane, do not run the 40-comparison holdout, and do not add a
terminal-only residual: the screen produced no ordinary winner and no
terminal-specific efficacy signal.

All treatments were safe and genuinely one-factor, so this is an efficacy
rejection rather than an implementation failure. The evidence supports the
earlier conclusion that exact adaptive preemption is a small family-specific
edge, but neither a longer fixed horizon nor C68 online horizon inference
improves paired match wins.

## Current engine/configuration

Upstream `master` was rechecked immediately before games and still resolved to
`bded87b0d7879078c726a93a4884d044f79c4eed`.

| Surface | Verified value |
| --- | --- |
| Official Python normalized SHA-256 | `FB9215C5E21A25243E2D13E75B3D70A79CF7D78FFF150A90F1BB5EACF9BA2BCF` |
| Official JSON SHA-256 | `7F196F4AAF9B4E482FBD61BA4BF19F5CEC4DA0F81938ECE756954035A65C0BB5` |
| `townCenterSellInterval` | `24`, flat one-unit demand for the whole season |
| Market queue | ordered, per-unit lockstep, first 10 entries only |
| Price floor | a `$1` sale consumes shed inventory but does not add market inventory |
| Unit/market order | unit actions precede market; same-turn `DROP` makes stock available to `SELL` |
| Locked shed | `PICKUP`, `DROP`, and shed-directed `PLACE` work at locked center access tiles |

The lane patched the immutable local `a4dce5a…` package in memory with the
audited current semantic changes. The functional fingerprint directly tested
locked `(5,4)` pickup and same-turn drop availability; every source/hash probe
passed. See `engine_fingerprint.json`.

## One-factor boundary

The incumbent source was the statically extracted exact adaptive artifact,
SHA-256 `997E6BFC…710F1B6`. Preempt-H6 was `BE5B3713…4DE4D397`; C68 was
`E5CBB6ED…7FFBC248`. All four effective variants used the exact same adaptive
719-action embedded route digest:

`04354aa03513bfc1dcfbbeaf25a4a2074317681bd3c839a9550db21fa3e0d406`

- `adaptive_native`: unmodified exact adaptive ranking, 3->2->1 preemption,
  due-turn repayment, and terminal liquidation.
- `no_preemption`: only `_PREEMPT_ENABLED=False`; ranking and terminal behavior
  remained active.
- `preempt_h6`: its 6->1 market layer ran over a deep copy of the exact adaptive
  tape.
- `c68_overlay`: C68 public-market observation, adaptive horizon, and independent
  debts ran only after its own field tape was replaced by the exact adaptive
  tape.

Across all 36 treatment/control screen pairs, farmer/hands digests and all
non-SELL market-order digests were exactly equal. Thus HIRE, BUY, LAND, SEED,
ANIMAL, field route, production scale, and weed repair did not vary. The full
route and emitted SELL event logs retain market inventory, prices, town shops,
demand, public opponent distance, ranking changes, floor skips, shift creation,
and due-turn repayment.

## Screen result

Screen block: Kaito v21, Saiteja 3000, Roman LB950; fresh seeds `937181` and
`937193`; both seats. Each treatment has 12 same-opponent/same-seed/same-seat
paired deltas versus exact adaptive. Required gate: zero invalid/safety faults,
at least 8/12 positive deltas, and positive mean delta in every family.

| Treatment | Positive-zero-negative | Mean paired margin delta | Match-win increment | Gate |
| --- | ---: | ---: | ---: | --- |
| no preemption | 0-8-4 | -79.50 | 0 | Fail |
| Preempt-H6 | 1-7-4 | +30.83 | 0 | Fail |
| C68 overlay | 1-7-4 | +28.00 | 0 | Fail |

Every arm, including the incumbent, won all 12 raw matches. That is not a
residual win improvement: treatment and incumbent were both 12-0, so all three
paired match-win increments are zero. Positive raw mean for H6/C68 is driven by
one +428 Saiteja seat result and cannot rescue a 1/12 positive-delta count.

### Family-stratified paired deltas

| Treatment | Kaito v21 | Saiteja 3000 | Roman LB950 |
| --- | ---: | ---: | ---: |
| no preemption | 0/4 positive, mean -238.50 | 0/4, mean 0 | 0/4, mean 0 |
| Preempt-H6 | 0/4, mean -14.50 | 1/4, mean +107.00 | 0/4, mean 0 |
| C68 overlay | 0/4, mean -23.00 | 1/4, mean +107.00 | 0/4, mean 0 |

Native adaptive therefore retained a reproducible small advantage over no
preemption against Kaito, with no W/L change. Longer/C68 timing damaged that
Kaito residual and changed only one of four Saiteja comparisons. Roman exposed
no preemption opportunity, so every treatment was exactly neutral there.

## SELL debt and market trace audit

The screen logged 2,088 route-planned SELL orders per arm and every emitted
market-layer result. Quantity debt was conserved exactly in all games:

| Variant | Shift units by horizon | Shifted items | Repaid items | Conserved |
| --- | --- | --- | --- | --- |
| adaptive native | h3: 88; h2: 4 | milk 52; strawberry 40 | milk 52; strawberry 40 | Yes |
| no preemption | none | none | none | Yes |
| Preempt-H6 | h6: 60; h4: 8; h3: 24; h2: 4 | milk 52; strawberry 44 | milk 52; strawberry 44 | Yes |
| C68 overlay | h4: 8; h2: 60 | milk 52; strawberry 16 | milk 52; strawberry 16 | Yes |

There was no unresolved debt, beyond-six-turn advance, market list over 10,
seed overcommit, or non-SELL mutation. Floor-skip candidates and SELL-slot
ranking changes are retained per event in the checkpoint; the summary records
their aggregate counts. Terminal liquidation stayed identical to the source
layer, and no terminal-only treatment was justified.

## Safety, determinism, latency, and tests

Active evidence contains 60 official current-engine games: eight development,
48 screen, and four deterministic duplicates. Every game has 720 recorded
states, 719 candidate calls, and `DONE/DONE`.

Across the 48 screen games, every arm had zero animal escapes, fresh-crop
deaths, mid-day DROP overflow units, EOD overflow units, observed over-capacity
shed states, malformed actions, exceptions, timeouts, market-cap violations,
and seed overcommit. Candidate-only overflow was measured at the engine deposit
boundary, not inferred from an over-capacity observation.

Deterministic duplicates exactly reproduced candidate/opponent rewards and the
719-call action digest:

| Variant | p50 ms | p95 ms | p99 ms | max ms | Deterministic |
| --- | ---: | ---: | ---: | ---: | --- |
| adaptive native | 0.1516 | 0.2573 | 0.4733 | 0.8616 | Yes |
| no preemption | 0.0883 | 0.1725 | 0.2890 | 0.6202 | Yes |
| Preempt-H6 | 0.1519 | 0.2763 | 0.4267 | 0.9757 | Yes |
| C68 overlay | 0.2445 | 0.6156 | 0.8906 | 2.6126 | Yes |

All are far below the 150 ms p95 and 750 ms maximum gates. Compilation passed;
the production suite passed 18/18 and lane contract tests passed 4/4.

The first overflow probe revision attributed both players' discarded units to
the candidate. Its eight development and eight partial-screen rows remain in
`cache/games.jsonl` as 16 superseded instrumentation runs. All were rerun under
the candidate-private-state-only probe; no old row contributes to decisions.

## Stopping decision and production integrity

`frozen_winners.json` records a complete screen and an empty winner list.
Consequently the predeclared 40-comparison holdout was correctly not entered.
This is a completed stopping-rule outcome, not unfinished evaluation.

No file under `submission/`, `dist/`, `.vendor/`, `data/`, or `docs/` was
changed. `dist/submission.tar.gz` remains SHA-256
`C84664D77EB9D32CE7001D31EE15634AE144B9403BA98D43B1D69226A588AAB2`.
Nothing was packaged, submitted, pushed, or changed remotely.

## Artifacts

- `research/counterfactual_market_residual_2026-08-10/`: frozen protocol
  implementation, overlays, engine fingerprint, tests, and resumable cache.
- `reports/counterfactual_market_residual_2026-08-10/protocol.md`: predeclared
  mechanism, seeds, gates, and stopping rule.
- `reports/counterfactual_market_residual_2026-08-10/engine_fingerprint.json`:
  current source/config and functional semantic checks.
- `reports/counterfactual_market_residual_2026-08-10/summary.json`: all active
  aggregates, paired details, digests, event/debt statistics, latency, and
  determinism.
- `reports/counterfactual_market_residual_2026-08-10/frozen_winners.json`: empty
  screen-winner freeze and holdout boundary.

