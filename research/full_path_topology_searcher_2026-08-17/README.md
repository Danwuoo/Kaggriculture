# Full Path Topology Searcher — development lane

This isolated V1 turns retained route topology into bounded, executable branch
proposals. It does **not** search an unconstrained 719-turn replacement tape.
The executable graph is:

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

V1 may produce `READY_FOR_PROPOSAL_ONLY`. It cannot authorize fresh seeds,
formal efficacy, promotion, submission packaging, or Kaggle submission. The
frozen Boatlee E2 selector is evidence about rejection logic only; its consumed
contexts and zero actual win delta remain non-efficacy evidence. v27 E2 remains
stopped.

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
```

`propose` ranks test budget by `mutability × frontier relevance × own-loss
match`; it never ranks efficacy. `technical-evaluate` performs static and
isolated-import checks and runs zero formal games.

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
identical. In this V1 registry, `formal_efficacy_authorized` is false, so even a
fully passing hypothetical raw-row gate remains non-eligible until a separate
authorization updates the program boundary.
