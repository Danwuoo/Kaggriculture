# E2 implementation plan

## 0. Freeze authority

- Validate `candidate_registry.json` and every referenced committed file hash.
- Re-fingerprint both active controls, route sources, opponent artifacts, exact
  engine Python, and configuration JSON.
- Preserve the E1c raw artifact tree as read-only evidence.
- Rescan all repository seed usage, but do not select or execute an E2 seed
  during development.

## 1. Repair effective-change ranking

Replace the Async V3 action-digest-only behavior flag with an explicit
candidate-versus-control effective-change record. A context is effective only
when at least one receipt, public/economic state, terminal bank/reward, or
attributed economic diagnostic changes.

Add regression coverage that:

- excludes `ac_bad79e4d71965c86b6b351a1` from every efficacy frontier;
- retains `ac_3aa759d7d7fc4a409c409326` as a real Boatlee change;
- retains `ac_46448f767f398cc4ce8047d3` only on the v27 high-upside/probe surface;
- never treats an engine-cancelled or queue-truncated order as an executed
  topology change.

## 2. Freeze the Boatlee finalist

Reconstruct the registered one-block candidate exactly and materialize its
standalone deterministically. Do not mutate its route, quantities, constants,
or guards in E2 S1. Confirm exact fast-versus-standalone equality in both seats
on technical seed `811407`.

## 3. Develop the v27 public selector

Materialize the registered high-upside probe. Use only frozen E1c traces to
identify public features that separate favorable and adverse contexts. Allowed
features are bounded functions of public step, money, farms, tiles, crops,
animals, workers, land, town, shops, market price/inventory, and public action
history.

The selector must choose between the unmodified v27 incumbent and the exact
registered probe. It must not identify the opponent, infer private inventory,
or improvise a third route. Keep the model deterministic, small, embedded, and
cheap. Prefer an auditable rule or tiny score over a broad learned model.

Freeze at most two selector versions for E2 S1. Each version receives a new
lane-local candidate ID and includes its exact feature list, thresholds,
fallback, and causal lineage.

## 4. Exact evaluator and scheduler reuse

Reuse the verified Async V3 exact-engine loader, lane-relative controls,
standalone materializer, Windows spawn scheduler, immutable manifests,
per-job shards, checkpoints, deterministic merge, and read-only status. Do not
resume the E1c run directory. Every E2 development and formal run receives a
new output root and registry.

## 5. Development audit

Run the E2 acceptance contract, both incumbent builders, the shared source
contract, Async V2/V3 regression suites, worker 1-versus-4 equality, failure
injection, finalist parity, latency, JSON validation, and `git diff --check`.
Write machine-readable `development_verification.json`, a command transcript,
and `development_decision.md`.

Stop after development verification. Do not choose or execute fresh seeds.
