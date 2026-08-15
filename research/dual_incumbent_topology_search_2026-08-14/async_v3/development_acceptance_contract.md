# Async V3 / E1c Development Acceptance Contract

All requirements are conjunctive.  A repair changes the candidate or code
version and reruns the same gate; it does not weaken the gate.

## Frozen-evidence gate

- The fixture schema validates.
- Raw file hashes and embedded canonical hashes match the committed E1b files.
- Each referenced generation hash and candidate payload is present.
- Async v2 source and artifacts remain byte-identical throughout development.
- Both incumbent controls and exact engine/configuration identities are frozen.

## Genome and mutation gate

- Canonical equality is independent of input ordering and lineage metadata.
- Candidate IDs are lane-specific even for equal semantic edits.
- Ordered-market edits cover all declared opcodes, quantities, queue positions,
  guards, removal, and deliberate retention.
- An ordinary mutation changes exactly one causal atom.
- Dependency-bundle crossover cannot silently drop required actions.
- Refill terminates deterministically and records saturation.
- Every lane-local island produces distinct compiled phenotypes in a fixed
  capacity probe; inactive constants are reported instead of counted as
  diversity.

## Compiler/runtime gate

- The four E1b anchors reconstruct the fixture's effective patches exactly.
- Every displaced action has one of the three required dispositions.
- Market queues never exceed ten entries and preserve declared order.
- Public guards use no opponent identity or private-opponent information.
- Missing private/current observation state preserves the incumbent action.
- The atomic seed guard retains incumbent behavior on missing/unreadable
  private seed data and cancels same-crop overcommit atomically when readable.
- Final legality projection is the final operation before return.
- Runtime remains self-contained, standard-library-only, and performs no file,
  network, subprocess, multiprocessing, or verbose-log operation.

## Regression-ranking gate

- Boatlee fixture `ac_5f4a369973330bf53370f3f8` is classified robust.
- Boatlee `ac_25fbbfe7484fa2d6846b27c6` remains separately attributable; within the
  fixture's 1-coin mean-margin near-tie band, the one-block candidate is the
  preferred causal representative.
- v27 fixtures `ac_b59943fc80ea1fa0ff69ce89` and
  `ac_421ad5f206c01e62204a11e3` are preserved on the high-upside frontier and
  excluded from the robust frontier because their worst paired margins are
  negative.
- High-upside evidence is never discarded merely because it fails the robust
  gate, and it is never reported as robust.
- Ranking and Pareto selection are performed independently per lane.

## Exact-evaluation gate

- Technical seed `811407` is used only for correctness and parity; its reward is
  absent from efficacy fields.
- Unchanged controls reproduce exact rewards, all-action digests, termination,
  and diagnostics from both seats.
- Fast and finalist standalone execution are exactly equal from both seats.
- All completed games end `DONE`/`DONE`, with zero exceptions, malformed
  actions, timeouts, and market overflow.
- Full-episode latency p95 is below 150 ms and maximum below 750 ms.

## Scheduler gate

- Worker counts 1 and 4 produce canonical equality in development.
- The configured maximum of 15 is enforced.
- Kill/restart, corrupt shard, import, engine, and worker failures are tested.
- Resume rejects changed manifest, engine, control, fixture, registry, or job
  hashes before evaluation.
- Infrastructure failure produces no efficacy score.
- Status is read-only and does not create a missing run root.

## Repository and artifact gate

- Both incumbent builders pass `--check` and the shared source contract passes.
- Existing Async v2 tests remain green.
- New unit, property, integration, parity, and failure tests pass.
- `git diff --check` has no new source/document whitespace errors.  Frozen
  evidence is not rewritten merely to change formatting.
- `development_verification.json` is machine-readable and contains command,
  version, hash, seed, seat, latency, parity, failure-injection, and frozen-file
  evidence.
- `development_decision.md` says exactly one of
  `READY_FOR_E1C_CONSUMED_SEED_RUN` or
  `E1C_DEVELOPMENT_REMEDIATION_REQUIRED`.
- No E1c efficacy run, E2 run, fresh seed, submission, commit, push, or remote
  mutation is performed by the development task.
