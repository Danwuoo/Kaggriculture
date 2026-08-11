# Lane 01 report — current-engine parity

## Scope and provenance

This lane copied the canonical submission into `candidate/` and made only
engine-semantics corrections.  It did not change macro targets, scheduler
priorities, crop/livestock economics, or market-order policy.  No canonical
source, `.vendor`, `data`, `docs`, `dist`, or shared report was changed.

Upstream `master` was checked on 2026-08-08 and resolves to
`bded87b0d7879078c726a93a4884d044f79c4eed`.  The lane runs the source snapshot
through the bundled framework without changing `.vendor`:

| File | SHA-256 of authoritative GitHub raw bytes |
| --- | --- |
| `kaggriculture.py` | `FB9215C5E21A25243E2D13E75B3D70A79CF7D78FFF150A90F1BB5EACF9BA2BCF` |
| `kaggriculture.json` | `7F196F4AAF9B4E482FBD61BA4BF19F5CEC4DA0F81938ECE756954035A65C0BB5` |

`python scripts\\fetch_bded_engine.py --remote --check-master` verifies both
the remote master ref and these bytes.  `engine_runtime.py` then re-registers
that interpreter for test and smoke processes.

## Parity matrix

| Surface | a4dce5a behavior | bded87b behavior | Lane result |
| --- | --- | --- | --- |
| Locked shed access | The LOCKED guard rejected `PICKUP`, `DROP`, and shed-directed `PLACE` on three center tiles. | Those shed operations run before the LOCKED guard; field mutations remain blocked. | `candidate/rules.py` allows exactly those three operations; `scheduler.py` targets all four shed-access tiles. Direct engine and projector probes pass. |
| Town center | Default every 12 turns; demand scaled 1x/2x/4x by season day. | Default every 24 turns, exactly one of each non-fertilizer product, flat all season. | `market.demand_rate` changes its base from `1/12` to `1/24`; transition probe confirms turns 0 and 24 consume, turn 12 does not. |
| Shop unlock and demand | Draw without replacement from remaining shop kinds. | Draw with replacement, each list entry consumes independently, and total entries cap at 8. | `GameState` already retained duplicate entries and `demand_rate` already iterated them; probes verify two yarn shops consume 4 wool per tick, repeated forced draws retain duplicates, and an 8-instance town does not grow. |
| Observation/schema | Earlier descriptions implied unique shops and the old center default/ramp. | No new top-level observation field; `town.unlocked_shops` may contain duplicates and JSON defaults describe current town timing. | Candidate normalization preserves duplicates; manifest test checks JSON default `townCenterSellInterval == 24`. |

## Validation

- Compile: `python -m compileall -q candidate scripts tests engine_runtime.py` — passed.
- Semantics tests: 6/6 passed against the bded interpreter.  Covered snapshot
  hash/defaults, locked `PICKUP`/`DROP`/`PLACE`, scheduler target selection,
  flat town-center timing, replacement shop instances/cap, and duplicate-shop
  observation preservation.
- Development smoke: 8 complete 720-step games, seeds 11 and 23, both seats,
  against `starter` and `random`.  All players finished `DONE`; candidate won
  all 8.  Exact per-game outcomes are retained in `smoke_results.json`.
- Determinism: two self-play runs at seed 777 had the same rewards
  `[31546.0, 29670.0]` and action digest
  `f5cdf93a56e2d5498b98f56c95716fc19bb37e18d6c8b4d79622342e20424cbc`.
- Safety audit across the 8 opponent games: malformed actions 0, timeouts 0,
  animal escapes 0, fresh-crop deaths 0, shed-overflow states 0, seed
  overcommit 0, and market lists above 10 entries 0.
- Latency across those games: p50 1.00045 ms, p95 3.06054 ms, p99 7.36413 ms,
  max 54.45610 ms.

## Failures and decision

The first local `git archive` transfer passed binary data through a PowerShell
text pipeline, producing CRLF-transformed snapshot bytes.  The lane now uses
the remote raw-byte verifier/writer; the verified `engine_bded/` snapshot is
the only one used by tests or smoke.  No candidate semantic or safety test
failed after that correction.  The unrelated optional `pyspiel` warning from
the bundled framework appeared as expected.

This is a correctness/harness baseline, not an economic-policy candidate, so
it should **not** enter a standalone larger matched ablation.  Future strategy
lanes should use this bded loader and probes before interpreting any paired
win result.
