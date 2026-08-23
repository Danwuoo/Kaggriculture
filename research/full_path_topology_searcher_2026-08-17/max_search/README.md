# Maximum full-tape search execution system

This package implements the development-safe core for the maximum-scale search
defined by `../CURRENT_TASK.md` and `../max_search_contract.json`.

The stopped 300M run is not the current execution target.  The independently
signed approximately-two-day continuation is in `two_day.py`; its operator
contract and fail-closed sequence are documented in
`../two_day_runbook_20260823.md`.  It reads copies of the old SQLite/WAL state,
never opens the old databases in writable mode, records reused game keys
separately from newly executed games, and binds/rechecks the external official
evaluator dependency closure as well as the local `max_search` implementation.

Two-day commands (run from this directory's parent) are:

```powershell
# Short technical probe; this is not an accepted formal calibration.
python -m max_search.two_day calibrate --active-in-flight 14 --candidate-batches 8 --output <probe.json>

# Accepted calibration binds an eight-context 50:50 Kaito/other-incumbent mix,
# balanced candidate batches across both lanes, at least 128 games, 14
# configured workers, whole-interval CPU in 50-65%, zero technical failures,
# and the disk reserve.
python -m max_search.two_day calibrate --active-in-flight <bounded-limit> --candidate-batches 22 --require-gates --output <calibration.json>

python -m max_search.two_day prepare --calibration <calibration.json> --output-root <new-empty-run-root> --run-id <new-id> --authorization-id <current-chat-id>
python -m max_search.two_day run --run-root <new-run-root>
python -m max_search.two_day status --run-root <new-run-root>
```

The package now contains both the audited V2 search substrate and the
long-running, multi-generation execution layer. The latter uses one persistent
spawned process pool per run, bounded in-flight work, exact receipt caching,
SQLite generation ledgers, atomic signed checkpoints, and deterministic
pause/resume at generation boundaries.

Stable substrate commands, from this directory's parent:

```powershell
python max_search\cli.py validate-contract
python max_search\cli.py plan --output ..\cache\full_path_topology_searcher_2026-08-17\max_search_plan.json
python max_search\cli.py miniature --proposal-seed 271828 --per-island 2 --generations 3
python max_search\cli.py official-smoke --technical-seed 811407
python max_search\cli.py official-mutation-smoke --technical-seed 811407
python max_search\cli.py preflight --run-id max_search_development_v1 --proposal-seed 271828 --output-root ..\cache\full_path_topology_searcher_2026-08-17\max_search_development_v1
python max_search\cli.py dry-generation --output-root ..\cache\full_path_topology_searcher_2026-08-17\max_search_development_v1 --generation 1 --per-island 2
python max_search\cli.py status --output-root ..\cache\full_path_topology_searcher_2026-08-17\max_search_development_v1
```

Execution workflow:

```powershell
# Freeze a development registry. This draft is technical-only, not fresh evidence.
python max_search\cli.py freeze-contexts --draft max_search_context_draft.development.json --output ..\cache\full_path_topology_searcher_2026-08-17\example_context_registry.json

# Prepare a bounded development run against an existing preflight.
python max_search\cli.py prepare-execution --preflight-root ..\cache\full_path_topology_searcher_2026-08-17\max_search_execution_preflight_v5 --context-registry ..\cache\full_path_topology_searcher_2026-08-17\example_context_registry.json --output-root ..\cache\full_path_topology_searcher_2026-08-17\example_execution --run-id example_execution --workers 18 --backend official --generations 2 --residents-per-island 2 --births-per-island 2 --t1-promotions-per-island 1

# Stop after generation 0, inspect, then resume the same signed execution.
python max_search\cli.py run-execution --output-root ..\cache\full_path_topology_searcher_2026-08-17\example_execution --stop-after-generation 0
python max_search\cli.py execution-status --output-root ..\cache\full_path_topology_searcher_2026-08-17\example_execution
python max_search\cli.py run-execution --output-root ..\cache\full_path_topology_searcher_2026-08-17\example_execution

# Calibrate and project the full 300M candidate-game resource requirement.
python max_search\cli.py calibrate-execution --output-root ..\cache\full_path_topology_searcher_2026-08-17\example_execution --output ..\cache\full_path_topology_searcher_2026-08-17\example_calibration.json
python max_search\cli.py resource-estimate --games-per-second 1.3517222918046583 --bytes-per-receipt 3123.2 --workers 18 --output ..\cache\full_path_topology_searcher_2026-08-17\example_resource_estimate.json
```

A formal registry must contain exact, disjoint T0, T1, and untouched-holdout
stages and frozen opponent hashes. Formal preparation additionally requires the
official backend, no development limits, an explicit authorization ID, a
source-matched calibration of at least `max(128, workers * 8)` games, measured
search-program CPU between 50% and 65%, and at least the dynamic-storage
reserve declared by the contract.
The formal command deliberately fails closed if any field is absent or drifts.

Formal run `max_search_formal_300m_20260821_v1` started on 2026-08-21 with 11
workers. Its accepted 128-game official calibration measured 57.48% CPU and
1.3439 games/s; a steady-state process-tree sample measured 50.19%. The
12-worker calibration was rejected at 69.17%.

Storage uses `generation_adverse_compact_prune`. Before raw receipts are
deleted, every receipt contributes to a signed all-receipt digest, while every
negative-margin game, technical failure, and worsened economic diagnostic is
retained row-by-row in a deterministic gzip ledger. Fitness, controls,
promotions, generation summaries, and logical T0/T1 counters remain cumulative.
The runner requires at least 50 GiB free at launch and before each generation.
SQLite deleted pages are reused by later generations.

At launch verification the background parent was PID 3912. After that process
was accidentally terminated, the same signed run passed SQLite, checkpoint,
source, engine, control, route, root, implementation, context, and opponent
drift checks. It resumed as PID 20656 with all 32,256 cached T0 receipts intact;
the first post-resume transaction advanced the ledger to 32,448 receipts.
See `../max_search_formal_launch_20260821.json` and
`../max_search_formal_resume_20260822.json`.

`preflight` is intentionally development-only. It fingerprints the audited
engine commit, freezes current lane-local controls/routes and 225 deduplicated
public donor tapes, creates 16,384 canonical resident genomes across 32
islands, and writes signed manifest/checkpoint state. It runs zero games and
cannot itself authorize the 300M-game search. Formal authority is held by the
separately signed execution manifest and current-chat authorization.

The package keeps semantic genome identity independent of lineage metadata.
Sparse step patches can represent every complete 719-turn tape while avoiding
30 million standalone artifacts. Supported neighborhoods range from one action
through full-tape donor replacement, with deterministic lane-compatible
crossover and bounded destroy/repair.

Development manifests hash every `max_search/*.py` source file as well as the
engine, controls, routes, and roots. Candidate IDs encode the lane and the full
canonical SHA-256; SQLite stores and rechecks the complete canonical semantics.
Generation shards use a prepared-summary journal before the database commit,
so restart reconciles a rolled-back or committed index against the exact shard
instead of silently proposing replacement births.

`runner.py` keeps v27 and Boatlee controls, scores, populations, promotions,
and broad-finalist quotas independently attributable. Every candidate receives
the exact declared T0 block; deterministic per-generation quotas close exactly
at five million T1 promotions in a full run. Completion is accepted only when
candidate-index, receipt-store, fitness, generation-journal, checkpoint, and
next-resident counts all agree. Broad-finalist generation writes exactly 50 per
lane but never launches a later tier, promotes an incumbent, or submits.
