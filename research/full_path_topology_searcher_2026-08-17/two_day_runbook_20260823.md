# Approximately-two-day full-tape continuation runbook — 2026-08-23

## Authority and boundary

This lane is a new formal execution.  It does not mutate, resume, reinterpret,
or replace the signed manifest for
`max_search_formal_300m_20260821_v1`.  The old run remains the authoritative
source for completed evidence and is accessed only by copying its SQLite main,
WAL, and SHM files into a temporary directory.  Hashes of the source files are
checked before and after every import.  The separately signed
`max_search_formal_stop_database_identity_20260823.json` binds the complete
store and candidate-index main/WAL/SHM byte set, both `quick_check=ok` results,
the original stop artifact, and the stopped execution manifest.

No incumbent production source, `.vendor`, `data`, frozen E1/E2 evidence,
Kaggle submission, promotion, broad evaluation, or remote state is in scope.
The 24 holdout contexts remain signed and untouched.

## Exact reuse boundary

The continuation first writes a signed, compressed completed-game ledger:

- Gen0 T0: 16,384 signed initial candidates × 6 frozen T0 contexts = 98,304.
- Gen0 T1: 2,730 persisted promotions × 24 frozen T1 contexts = 65,520.
- Gen1 live T0: 5,408 complete candidate blocks × 6 frozen T0 contexts = 32,448.
- Total reusable completed keys: 196,272.

Each key binds candidate semantics, lane, tier, context, and a compatibility
digest covering engine Python/configuration, lane-local control, route, root
registry, opponents, context registry, and the unchanged legacy 14-file game
implementation.  It also binds the official evaluator dependency closure:
`engine_runner.py`, `protocol.py`, `harness.py`, and
`artifacts/prechange_manifest.json`; startup and every generation boundary
recheck their bytes.  Reused counters never increment newly executed counters.

All 31,384 old candidate semantics are inserted into the new exact candidate
index before proposal.  This prevents the new mutation stream from emitting a
candidate that was already present in either old generation, including an old
candidate whose favorable raw receipt was pruned after signed retention.

## Seed and evolution design

The new resident population is 2,048 (64 per island).  Where Gen1 has complete
T0 evidence, a resident island receives 48 candidates from the completed Gen0
survivor frontier and 16 from Gen1, selected with the existing technical gate,
negative-tail-first ordering, objective extremes, and novelty.  The stopped
receipt stream covers only the first 12 v27 islands; no Gen1 score is imputed
into Boatlee or an uncovered island.  Those islands receive 64 Gen0 frontier
seeds.  The signed seed artifact records this asymmetry.

Generation 0 is an evidence-only bootstrap and executes zero games.  Sixteen
offspring generations then run across all 32 islands.  Each generation proposes
an exact equal birth quota per island, evaluates T0, promotes an exact equal T1
quota per island, selects lane/island-local survivors from parents plus births,
writes signed birth/completion/checkpoint artifacts, retains every adverse or
technical receipt, and dynamically prunes raw receipts.  This is genuine
multi-round survivor feedback, not a truncation of the old first two generations.

## Calibration and quota closure

`physical_workers` is fixed at 14.  If 14 simultaneous games violate the 50–65%
whole-interval CPU band, `active_in_flight` is reduced as an explicit signed
throttle while the configured process-pool capacity remains 14.  It is never
silently reported as a lower worker configuration.

An accepted calibration requires at least `max(128, 14×8)` official games,
zero technical failures, the CPU band, and at least 50 GiB free.  Its signed
artifact binds eight newly allocated technical-only contexts: both seats for
two Kaito seeds and two other-incumbent seeds, matching the formal T1 50:50
opponent mix.  These seeds had no prior workspace evidence when allocated and
are disjoint from T0, T1, and holdout; calibration retries may reuse them, and
they are never efficacy evidence.  The artifact also requires exactly balanced
candidate batches across both incumbent lanes.
The formal
quota chooser searches exact per-island birth/promotion integers at the
measured games/s.  It maximizes safe new work within 45.5 search hours, prefers
44–45.5 hours and 400k–500k total reused-plus-new completed keys, and reserves
2.5 hours of the two-day window for checkpointing, finalization, and operational
variance.  The resulting signed contract is created only after calibration.

## Launch gates

Before background launch, all of the following must be green:

1. Old stop hashes, internal signatures, SQLite `quick_check`, and copied-state
   ledger reconstruction.
2. Exact compatibility for engine, configuration, controls, routes, roots,
   opponents, contexts, and legacy game implementation.
3. Seed topology, lane ownership, source coverage, candidate pre-index, and
   zero newly executed games at prepare.
4. Unit/integration tests, main-approach source contracts, builders, and
   `git diff --check`.
5. A fresh context-clean Sol/High read-only audit returning `ship`.
6. Accepted signed 14-worker calibration and storage reserve.
7. Signed contract, context reference, preflight, manifest, checkpoint, and an
   empty stderr path before launch.

If any gate fails, do not start.  Leave the failed artifact, stdout/stderr, exact
command, and current hashes in place so the attempt is recoverable and auditable.
