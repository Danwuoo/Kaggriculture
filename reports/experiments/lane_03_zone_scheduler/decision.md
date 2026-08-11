# Lane 03 — safe short-term zone scheduler

Date: 2026-08-08  
Decision: **do not advance to a larger matched ablation.**

## Scope

This lane was cloned from `submission/` into `candidate/`.  The only candidate
behavior change is `candidate/scheduler.py`; macro herd, crop, land, and market
targets are unchanged, and the existing final legality projector remains the
last action boundary.

The scheduler now:

- assigns P0, then P1, before any zone allocation;
- clears every non-safety preference when a P0 appears, a P0/P1 prerequisite is
  unavailable, a day rolls over, or the hand count changes;
- allocates the remaining workers among livestock, NW, SW, and logistics;
- records only 2–4 turn soft zone/target preferences for P2–P5 work;
- recognizes short `PICKUP WHEAT -> FEED` and `HARVEST -> return/DROP` chains;
- records assignment/completion, travel, productive action, deadline slack,
  P0/P1 reservation, retarget, churn, and commitment-clear diagnostics.

This is deliberately not a hard sticky-worker implementation.  A commitment is
only a candidate-score preference and is bypassed if its zone has no feasible
ordinary job.

## Validation

- Compile: passed for `candidate/`, focused test, and smoke harness.
- Focused semantic tests: **4/4 passed** (`test_zone_scheduler.py`).  They cover
  P0 interruption, short chain lifetime, harvest-return routing, day boundary,
  and unavailable P0 feed resources.
- Official engine: current upstream `bded87b0d7879078c726a93a4884d044f79c4eed`.
  The candidate smoke executed its fetched interpreter logic directly; its
  in-memory executable text (with only the JSON file loader replaced by the
  fetched JSON string) had SHA-256
  `19571d207867fa5dfea7d9d2e835a3fd065a04aefe667f9598130db0b755cb7f`.
  No transport fallback was used for that run.
- Development smoke: 2 seeds (`101`, `211`) × both seats versus the official
  deterministic `starter` agent, plus two repeated self-play runs at seed 777.
  Candidate and canonical control both completed all six games as `DONE`.

| Seed | Seat | Candidate | Canonical control | Delta |
|---:|---:|---:|---:|---:|
| 101 | 0 | 58,930 | 64,341 | -5,411 |
| 101 | 1 | 67,947 | 74,765 | -6,818 |
| 211 | 0 | 91,264 | 82,772 | +8,492 |
| 211 | 1 | 79,303 | 82,731 | -3,428 |

The candidate won all four games against `starter`, but the matched comparison
is **1/4 positive pairs**, total delta **-7,165**, mean delta **-1,791.25**.
Repeated seed-777 self-play was deterministic (identical action digest and
rewards).

## Safety and scheduling diagnostics

Across the four matched candidate games and both deterministic self runs:

- malformed actions, agent calls over one second, animal escapes, fresh-crop
  deaths, shed-overflow states, seed overcommitments, and market lists over ten:
  **all zero**;
- worst matched-game p95 latency: **2.604 ms**; worst call: **51.705 ms**;
- candidate moves/productive actions: **19,348 / 7,173 = 2.6973**;
  canonical control: **19,058 / 7,139 = 2.6696**;
- candidate scheduler aggregate: 26,521 assignments, 7,173 at-target
  completions, 19,348 travel actions, 314 P0 reservations, 646 P1
  reservations, 6,587 retargets/churn events, and 1,721 commitment clears.

`p0_unassigned=95` is retained in the raw candidate report.  It counts a P0
`FEED` which lacks carried wheat at assignment time before its P0 pickup route
can complete; it is not an asset-loss count.  The explicit safety audit found
zero escapes, but the diagnostic reinforces that this factor has not reduced
route churn enough to justify expansion.

## Retained failures and stop rationale

1. The first focused test run exposed a defect where a moving `DROP` route
   erased its commitment before reaching the shed.  The implementation now
   clears that commitment only after an at-shed `DROP`; the final 4/4 test run
   passed.
2. The first smoke-harness attempt hit a GitHub raw TLS reset, and a subsequent
   control attempt exposed the absence of lane diagnostics in canonical
   `Scheduler`.  Both were harness-only faults; the final candidate smoke
   fetched the current upstream source directly with no fallback.
3. More importantly, three of four matched seed/seat pairs lost to canonical,
   and moves/productive is slightly worse rather than approaching the stated
   2.2 target.  The safety gate passes, but there is no positive paired signal.

Per-game evidence, including all losses and diagnostics, is retained in
`results/control_smoke.json` and `results/candidate_smoke.json`.  No larger
matrix, submission promotion, archive build, commit, or Kaggle submission was
performed.
