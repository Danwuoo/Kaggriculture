# Async V3 / E1c Implementation Plan

## 0. Preserve authority

- Assert the committed E1b summary, manifest, generation, engine, configuration,
  control, and fixture hashes before implementing.
- Fail closed if any frozen input differs.
- Write every v3 artifact under `async_v3/artifacts/`; never resume a v2 run or
  write into `async_v2/`.

## 1. Implement the canonical genome

Keep bounded route-block genes and add canonical ordered-market edit genes.
An edit must identify its lane, public event/step anchor, operation
(`insert`, `remove`, `replace`, `move`, or `quantity`), full market order,
queue position, and optional public guard.  Market order opcodes must cover
`HIRE`, `BUY_LAND`, `BUY_ANIMAL`, `BUY_SEED`, `BUY_PRODUCT`, and `SELL`.

Constant genes must come from one lane-owned registry that is also used by the
compiler and runtime.  A constant without a verified live runtime target is not
searchable.  Canonical IDs must include schema version and lane.  Preserve a
parent ID, mutation ID, and causal bundle ID outside the canonical genome so
lineage does not change semantic identity.

## 2. Add causal roots and mutation operators

Seed the exact fixture roots, their controls, and explicit remove-one
ablations.  Add deterministic mutation operators for:

- order insert/remove/replace/move;
- quantity local step and bounded domain jump;
- public price/inventory guard add/remove/perturb;
- lane-owned constant local perturbation;
- route-block add/remove;
- dependency-preserving crossover between compatible parents.

One ordinary child changes one causal atom.  A named bundle may establish an
initial coherent chain, but later mutations must identify the single changed
atom.  Population refill is bounded and emits a saturation record instead of
looping until a nominal quota is filled.

Use separate lane-local islands for route, ordered market, live constants, and
coupled genomes.  Report proposed genomes, compiled phenotypes, technical
behavior digests, rejected proposals, and saturation separately.

## 3. Compile deterministic lane-local patches

Apply ordered-market edits to that lane's incumbent action list in a declared
order.  Reject ambiguous edits with a stable, non-circular reason.  Preserve
all incumbent actions not explicitly edited.  Each displaced action must be
`retained`, `reassigned`, or `reclaimed`.

The compiled contract must enforce:

- no more than ten market orders;
- explicit order sequence and quantity;
- public-only runtime guards;
- concrete resource/path/precondition/rejoin reasons for rejection;
- bounded incumbent fallback;
- final atomic-plant and action projection immediately before return.

Emit planned-versus-executed market receipts, including queue index, money
before/after, public inventory/price before/after where observable, and the
reason an order did not execute.  Do not treat an engine-cancelled order as an
executed topology change.

## 4. Evaluate progressively without seed leakage

The technical probe on seed `811407` may establish validity, action change,
receipts, and fast/standalone parity only.  Keep technical diagnostics out of
the efficacy score schema.

For a later authorized E1c run, freeze lane-relative controls and evaluate only
the consumed E1 seeds from a new registry.  A candidate receives an efficacy
score only after all declared contexts complete.  Infrastructure failures emit
no score and unlock no seed tier.

Materialize canonical compiled payloads during search.  Generate standalone
`main.py` only for shortlisted finalists, not for every generation member.

## 5. Use two explicit frontiers

The robust frontier requires technical pass, observed behavior change, both
opponent-family means non-negative, and worst paired margin non-negative on the
complete declared screen.  The high-upside frontier retains actual win
conversion candidates even when they fail the robust downside condition.

Never let `actual_win_delta` alone promote a high-upside candidate into the
robust frontier.  Within a predeclared near-tie epsilon, prefer lower causal
complexity and fewer effective patches.  Keep both frontiers per lane and never
pool lane rewards or margins.

## 6. Scheduler and artifacts

Retain Windows spawn processes, immutable manifests, per-job canonical shards,
atomic checkpoints, hash-validated resume, deterministic merge, failure
injection, and read-only status.  Support up to 15 workers.  Development smoke
uses 1 and 4 workers; a later launch selects 10--15 only after process-tree CPU
calibration against the user's 30--40 percent target.

Do not create tens of thousands of standalone candidate directories.  Search
shards and context cache remain content-addressed; redundant compiled payloads
reference one canonical object.

## 7. Verify and hand off

Implement the acceptance tests before the corresponding production code.
Finish with the commands and artifacts in `runbook.md`.  Stop after development
verification and report the exact files, hashes, tests, limitations, and
`formal_fresh_seeds_executed=false`.
