# Current task authority — maximum full-tape population search

Updated: 2026-08-23

## 2026-08-23 execution transition

The signed 300M execution is stopped and immutable.  It must not be resumed or
rewritten as the new approximately-two-day contract.  Stop authority and exact
database/artifact hashes are in `max_search_formal_stop_20260823.json`.

The active execution objective is now the independently signed 14-worker
continuation implemented by `max_search/two_day.py`.  It must reconstruct the
196,272 completed T0/T1 game keys (98,304 Gen0 T0, 65,520 Gen0 T1, and 32,448
Gen1 live T0), keep reused and newly executed counters separate, pre-index all
31,384 old candidate semantics, and never execute a completed tuple again.
Its formal quota is derived only after an accepted whole-interval calibration,
uses generation 0 as an evidence-only bootstrap, and retains multiple real
offspring generations across all 32 lane-owned islands.  The old formal
holdout remains frozen and untouched.  See `two_day_runbook_20260823.md`.

This file is the concise authority for new work in this directory. Historical
V1 documents and proposal artifacts remain immutable evidence, but they no
longer define the active optimization target when they conflict with this
summary.

## Current objective

Build and audit a reproducible, restartable, lane-isolated search over complete
719-turn Kaggriculture action tapes. The search must be able to move from
single-action edits through 1–719-turn replacements and non-incumbent roots,
rather than permanently treating either incumbent as the backbone.

The fixed maximum scale is:

| Dimension | Value |
| --- | ---: |
| Resident population | 16,384 |
| Generations | 2,000 |
| Raw unique-candidate budget | 30,000,000 |
| T0/T1 candidate-game budget | 300,000,000 |
| Broad finalists | 100 |
| Independent islands | 32 |

The 32 islands split exactly into 16 v27 and 16 Boatlee islands. Each lane has
four islands for each search mode: local coordinate, large-neighborhood,
non-incumbent-root/de-novo, and novelty. Results, controls, populations,
caches, scores, and promotion decisions remain lane-local.

## Core constraints

- Use the audited official engine commit
  `bded87b0d7879078c726a93a4884d044f79c4eed`, Python SHA-256
  `fb9215c5e21a25243e2d13e75b3d70a79cf7d78fff150a90f1bb5eacf9ba2bcf`,
  and configuration SHA-256
  `7f196f4aaf9b4e482fbd61ba4bf19f5cec4da0f81938ece756954035a65c0bb5`.
- Re-fingerprint both engine files and both incumbent artifacts at every run
  preflight. Never silently accept worktree-engine or control drift.
- Do not edit either incumbent development tree, generated incumbent
  `main.py`, `.vendor/`, `data/`, E1/E2 source, or frozen evidence.
- Search may use own private state offline to execute legal actions, but a
  compiled runtime selector may use only its own private state and public
  opponent state. Opponent identity and opponent-private state are forbidden.
- Preserve all failures and downside. Technical validity, net WDL transition,
  family×seat tails, CVaR/worst margin, and mean margin are separate fields.
  Mean reward or own bank alone cannot select a winner.
- Search/selection contexts and final untouched holdouts must be disjoint.
  Consumed seeds may support development diagnostics but never fresh efficacy.
- No Kaggle submission, remote mutation, incumbent promotion, or automatic
  later tier is authorized.
- The user authorized the 300M-game run on 2026-08-21 with 10–12 workers,
  50–65% search-program CPU, and dynamic receipt deletion. Formal execution
  `max_search_formal_300m_20260821_v1` is now stopped and retained as immutable
  prior-run evidence. This does not
  authorize Kaggle submission, promotion, remote mutation, automatic broad
  launch, or use of the untouched holdout.

## Confirmed decisions

- Full Cartesian enumeration is impossible; the implementation uses a
  population search with deterministic mutation, crossover, beam/Pareto
  survival, large-neighborhood destroy/repair, and multiple roots.
- Population size means resident survivors, not new candidates per generation.
  Generation 0 contains 16,384 roots. Generations 1–1,999 deterministically
  allocate the remaining 29,983,616 candidate births, so the total is exactly
  30,000,000 rather than 32,768,000.
- Every raw candidate receives six T0 games: 180,000,000 games. Exactly
  5,000,000 candidates receive 24 additional T1 games: 120,000,000 games.
  The T0/T1 candidate-game total is exactly 300,000,000. Frozen control-cache
  games and later broad-finalist games are accounted separately and may not be
  hidden inside that number.
- Allowed replacement horizons are 1, 2, 4, 8, 24, 48, 96, 192, and 719 turns.
- The 225 deduplicated retained public tapes may supply donor roots or blocks,
  but replay support is not quality. Lineage and source hashes remain attached.
- Both active incumbents are controls and valid roots, not mandatory permanent
  backbones. Non-incumbent-root islands are required.

## Current evidence and inference

The frozen Boatlee fertilizer selector broad run completed 6,656 paired
contexts (256 seeds × 13 families × 2 seats). It produced paired-margin
5,054/518/1,084 and net actual-win delta +180, but repeated negative tails in
every non-Roman family×seat stratum triggered the promotion falsifier. The
worst paired margin was -9,517. This replaces the earlier two-seed minimum
confirmation as the current Boatlee selector result.

The result is strong evidence that Boatlee's fixed continuation is not locally
optimal, while also showing that a single near-always-on public threshold is
not robust enough. It supports searching the full tape and measuring gain as
edit distance/replacement horizon grows. It does not establish the same
bottleneck for v27 and does not promote the failed selector.

## Superseded or historical-only material

- V1's `1..48 turn bounded branch against incumbent spine` is retained as a
  compiler and regression substrate, not the active optimization ceiling.
- The 2026-08-20 v27 step-264 and Boatlee step-361 proposals remain consumed
  diagnostic hypotheses only. They are not seeds for automatic promotion.
- The Boatlee two-seed minimum confirmation is superseded by the completed
  broad robustness result for current decision-making.
- The old statement that the next efficacy action is broad validation of the
  frozen Boatlee selector is obsolete; that broad validation has completed and
  failed its promotion contract.
- E1/E2 development code, earlier proposal ranking, and negative controls stay
  available for regression and provenance. They are not active search-policy
  instructions.

## Current progress

- Maximum scale and lane split are fixed.
- Broad selector evidence and the incumbent-bottleneck inference are recorded.
- Required incumbent, engine, Async V3, E2, and V1 authorities have been read.
- The working tree already contains user-owned V1 and E2 changes; they must be
  preserved.
- V2 development substrate is implemented: closed scale validation, canonical
  sparse full-tape genomes, deterministic 32-island generation, exact birth
  quotas, mutation/crossover, lane-local Pareto/tail scoring, signed atomic
  checkpoint state, official-engine policy projection, and read-only status.
- A development preflight created all 16,384 generation-0 residents; a bounded
  generation-1 shard exercised the persistent uniqueness index and idempotent
  artifact path.
- Official-engine no-op and effective one-action mutation smokes passed for
  both lanes and both seats.
- Repository regression checks are green. Four fresh Sol/High read-only audits
  produced fix-first findings that were remediated; a fifth independent
  cumulative audit returned `ship`. Development audit is complete.
- The long-running execution layer is complete: signed context registries and
  execution manifests, a persistent spawned process pool, bounded in-flight
  work, exact control/T0/T1 receipt caching, deterministic T1 quotas,
  multi-objective survivor feedback, birth journals, SQLite idempotence, signed
  checkpoints, and generation-boundary pause/resume are implemented.
- A three-generation deterministic mock run completed 192 candidates and 288
  candidate-games. A two-generation official-engine run paused after
  generation 0, resumed to completion, and closed at 128 candidates, 128 T0,
  and 64 T1 games with 18 distinct worker processes. Re-running the completed
  execution performed zero generations and changed no counters.
- Dynamic generation retention is implemented and recovery-tested. Each
  generation hashes every receipt, writes a signed gzip ledger containing all
  negative-margin rows, technical failures, and worsened economic diagnostics,
  then deletes raw receipt payloads after the generation journal is prepared.
  Logical counters remain cumulative while SQLite pages are reused.
- The accepted 11-process official calibration ran 128 candidate-games at
  57.48% whole-interval CPU and 1.3439 games/s. A steady-state process-tree
  sample measured 50.19%. The rejected 12-worker calibration measured 69.17%.
- Formal contexts are frozen at 6 T0, 24 additional T1, and 24 untouched
  holdout contexts under registry
  `caacd2101412edd7578cbabeba8b17d2796cbadbc0acac812149b36a128e584b`.
- Formal execution started at 2026-08-21 20:15:50 +08:00. The original PID
  3912 was accidentally terminated; SQLite, checkpoint, frozen inputs, and
  32,256 cached T0 receipts passed recovery checks. The same run resumed on
  2026-08-22 00:53:25 +08:00 as PID 20656 with no orphan workers or duplicate
  run. It expanded to 11 workers plus one resource tracker, persisted all 60
  controls and its first 192 T0 receipts, and had zero stderr bytes at launch
  verification. Searcher tests pass 104/104; main-approach contracts pass 3/3;
  both incumbent builders are current.
- Formal execution has started but no efficacy is claimed. The generation
  checkpoint remains at generation 0 until the entire generation commits.

## Historical 300M execution constraints

- Keep at least 50 GiB free. The runner checks this reserve at startup and
  before every generation; a low-storage condition stops safely at the current
  recoverable boundary.
- At 1.3439 games/s, the full budget still projects to roughly 2,584 days. This
  is an estimate, not a completion promise; actual per-generation throughput
  must be recorded.
- Do not inspect or execute the 24 frozen holdout contexts during T0/T1 search.
- Do not edit `max_search/*.py`, the contract, engine, controls, routes,
  opponent artifacts, formal registry, calibration, or preflight while the run
  is active; drift makes restart fail closed.
- Establish whether engine/agent prefix checkpointing can be made byte-exact;
  until proven, full replay from step 0 is authoritative.

## Superseded 300M monitoring plan

1. Monitor PID 20656, resume stderr, process-tree CPU, free space, persisted receipt
   counts, and generation journals without changing frozen inputs.
2. Audit generation 0 completion, its signed adverse ledger, logical
   98,304-game T0 count, exact T1 quota, survivor population, and raw-receipt
   deletion before treating later generations as healthy.
3. Continue generation-boundary recovery and storage checks throughout the
   run. A process stop is recoverable; restart only from the same signed run
   root and inputs.
4. Do not automatically execute the holdout, broad tier, promotion, packaging,
   submission, or any remote action.
