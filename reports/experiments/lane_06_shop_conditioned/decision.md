# Lane 06 — shop-conditioned crop portfolio

Status: stopped after the required small smoke; not a promotion candidate.

## Change

- Copied the canonical archive-root candidate into `candidate/`; no canonical
  submission file was changed.
- Corrected town demand to the current engine semantics: a list entry is one
  shop instance, duplicates consume independently every four turns, and the
  town centre consumes one of each non-fertilizer product once every 24 turns.
- Added a deterministic two-to-four-slot WHEAT/CARROT/TOMATO/STRAWBERRY
  portfolio.  It scores feasible crops with live future town drain, public
  24-turn opponent exposure, current/predicted marginal sale prices, seed
  cost, and an action-cost charge.  It has a two-day cooldown, a 90-point
  switch margin, and two slots maximum per crop.  MELON is not in this model.
- The lane-local `engine_bded/` mirror applies the audited `bded87…` town and
  shed-access deltas without modifying `.vendor`.

## Focused checks

`compileall` passed.  The seven targeted tests passed, including direct
engine-mirror transitions for duplicate Farmers Markets, duplicate Yarn
Stores, no relevant crop shop, draw-with-replacement, portfolio cooldown, and
seed-need consistency.

## Paired smoke — upstream semantic mirror, `bded87b0d7879078c726a93a4884d044f79c4eed`

Two seeds were run from both seats against the isolated canonical control and
the built-in starter (eight complete 720-step games).  Candidate versus
canonical control was 0 wins / 4 losses:

| Seed | Seat 0 | Seat 1 | Paired sum |
|---:|---:|---:|---:|
| 11 | -9,772 | -9,708 | -19,480 |
| 37 | -11,603 | -11,615 | -23,218 |

Mean candidate-control difference was **-10,674.5**.  The candidate beat
starter in all four games (mean +68,479.25), which is only a plumbing signal
and does not offset the matched control losses.

Safety was clean across all eight games: both players `DONE`; 0 timeouts,
malformed actions, market lists above 10, seed overcommits, animal escapes,
fresh-crop deaths, and shed-overflow states.  Candidate latency was p50
1.038 ms, p95 1.900 ms, p99 3.405 ms, max 59.425 ms.

The live draws were materially different: seed 11 opened BRUNCH_SPOT and
repeated it three times; seed 37 opened FARMERS_MARKET and later drew it
twice, with Yarn Store instances as unrelated controls.  The policy did use
the duplicate-instance signal (2 -> 3 -> 4 marginal slots), but its live
product mix did not materially separate the Brunch and Farmers-Market paths;
both converged to WHEAT/CARROT/TOMATO/STRAWBERRY = 3/1/1/6 once four relevant
instances were present.  The controlled transition test does distinguish two
Yarn Stores (inert, two slots) from two Farmers Markets (three slots).

## Decision

There is no positive matched signal.  Preserve `smoke_results.json` as the
loss record and do not expand this lane into a larger ablation or promote it to
`submission/`.
