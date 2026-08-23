# Full Path Topology Searcher — development lane

> **V1 historical boundary.** The active optimization task is now the maximum
> full-tape population search in `CURRENT_TASK.md`; its closed scale contract is
> `max_search_contract.json` and implementation is under `max_search/`. This
> README remains authoritative only for the retained bounded-branch V1
> regression substrate. Statements below about the next proposal or efficacy
> action are superseded when they conflict with `CURRENT_TASK.md`.

This isolated V1 is a **branch-experimentation substrate**, not the complete
Outcome-Conditioned Executable DAG described by `topology_path.md`. It
materializes one bounded branch against a retained incumbent spine; it does
not yet route among multiple calibrated outgoing branches or materialize
`BEST_POLICY_TOPOLOGY`. The executable unit is:

`incumbent spine -> public-state trigger -> 1..48 turn motif -> causal continuation -> explicit rejoin or incumbent fallback -> WDL value`

The two incumbent lanes remain independently owned and evaluated. Atlas edges
cannot cross lanes, opponent identity and opponent-private state are forbidden
runtime inputs, and evidence levels remain explicit. The old full-tape Python
modules are not imported; this lane reads only the frozen JSON, SQLite, and
compressed target-player action cache.

Atlas population is selected in two stages: one representative per team and
submission lineage, then one representative per canonical 719-action digest.
The retained population is 225 unique tapes from 227 source-level rows; two
exact duplicates are excluded from support and entropy statistics.

## Status boundary

Current status is `REPRODUCIBLE_BRANCH_EXPERIMENTATION_SUBSTRATE_ONLY`. It cannot authorize fresh seeds,
formal efficacy, promotion, submission packaging, or Kaggle submission. The
frozen Boatlee E2 selector is evidence about rejection logic only; its consumed
contexts and zero actual win delta remain non-efficacy evidence. v27 E2 remains
stopped.

The 2026-08-20 consumed counterfactual search retained one distinct v27
fresh-falsification candidate at step 264 and one narrow Boatlee diagnostic at
step 361. The guarded v27 result is 6 positive, 2 fallback-neutral, 0 negative,
including two L-to-W rows; Boatlee is 2 positive, 6 fallback-neutral, 0 negative
with no WDL transition. Both selectors were derived from consumed contexts and
remain non-efficacy evidence. See
`proposals/2026-08-20_counterfactual_search/counterfactual_decision.md`.

## Commands

Run from this directory with the workspace Python:

```powershell
python cli.py validate
python cli.py build-atlas --output ..\cache\full_path_topology_searcher_2026-08-17\atlas.json
python cli.py propose --lane v27_current_meta --output ..\cache\full_path_topology_searcher_2026-08-17\v27_proposals.json
python cli.py forensics --control control_trace.json --candidate candidate_trace.json --output divergence.json
python cli.py compile --spec branch.json --output artifacts\candidate\main.py
python cli.py technical-evaluate --candidate artifacts\candidate\main.py
python cli.py report --output ..\cache\full_path_topology_searcher_2026-08-17\development_verification.json
python cli.py write-summary
python compiled_counterfactual_screen.py --manifest proposals\2026-08-20_counterfactual_search\guarded_screen_manifest.json --output proposals\2026-08-20_counterfactual_search\guarded_consumed_screen.json
```

`write-summary` executes the lane, Async V3, and incumbent source-contract
suites plus registry validation before publishing. Zero-test or reduced-test
runs fail closed. Its source digest covers Git-tracked inputs only, so ignored
candidate artifacts cannot make the committed summary checkout-dependent.

`propose` derives replay mutability from the 225-tape atlas, own-loss match from
registered consumed forensic windows, and frontier relevance from hash-frozen
public-agent sources with audited semantic symbols. It deduplicates submission
lineages and requires at least two independent lineages; source drift or absent
matches fails closed. Manual scalar priorities are not accepted. A ranked motif
identifies only a development locus: the consumed own-loss rows describe a
known-harmful direction and cannot label a positive branch. `technical-evaluate`
performs static and isolated-import checks and runs zero formal games.

Compiled counterfactual screens must freeze the current incumbent control hash.
The retained no-op equivalence artifact catches wrapper/action-schema drift
before strategy results are admitted. Consumed discovery games are recorded
separately from formal games and never set `efficacy_signal=true`.

## Candidate contract

A `BranchSpec` names one incumbent lane, public trigger, displaced actions,
ordered motif patches, continuation mode, explicit compatibility fields and
tolerances for natural rejoin, maximum horizon, incumbent fallback, parent
atlas node, and evidence IDs. V1 accepts schema version 1 only, uses a closed
trigger/motif/patch schema, and permits at most one patch for each step; fields
that would be ignored by their selected market mode are rejected. The compiler
also rejects any resolved output below incumbent or E1/E2 roots. It supports action sequences, ordered
market replace/append/insert/remove edits, state rejoin, and terminal handoff. A final
schema/market-cap/atomic-PLANT projection occurs immediately before return.

Efficacy is WDL-primary and fail-closed: evidence must declare one incumbent's
exact engine and control/candidate hashes, predeclared seed/context registry,
unique matched rows with reward-derived outcomes and both seats per context,
authoritative non-consumed freshness, strict technical validity, an executed
public/economic/terminal change, and strictly positive net WDL movement.
The supplied protocol must exactly equal a registry entry, and its immutable
lane-local candidate file is independently byte-counted and re-hashed. V1 has
no registered fresh paired protocol, so an arbitrary caller-provided digest is
never sufficient. Runtime step/player and private counts/coordinates accept
exact non-Boolean integers only.
Margin, own bank, receipts, action digests,
or proposal priority cannot substitute. W→L is high risk; repeatable family/seat
worsening is a stop. Economics may break ties only when transition profiles are
identical. In this V1 registry, `formal_efficacy_authorized` is false and the
statistical efficacy contract is explicitly `not_approved`. Toggling the
authorization flag alone cannot make evidence eligible.

## Known evidence gaps

The c27 positive anchor and fixed-horizon-25 distribution-failure anchor remain
uncalibrated because their raw parent-relative paired rows are not present.
Only the Boatlee E2 margin-only false-positive anchor can currently be rejected
from retained machine evidence. These gaps are blockers, not proposal signals.
