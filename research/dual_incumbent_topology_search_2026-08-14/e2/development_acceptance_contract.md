# E2 development acceptance contract

All gates are conjunctive. A repair creates a new code or candidate version and
reruns the same gate; it never weakens the gate.

## Frozen authority gate

- `candidate_registry.json` validates and all committed file and payload hashes
  match.
- The E1b fixtures, E1c compact evidence, both active controls, opponents,
  routes, engine Python, and configuration remain independently attributable.
- No E1c artifact is overwritten or reused as a writable cache.
- Seed usage is rescanned; no E2 fresh seed is selected or executed during
  development.

## Effective-change gate

- Candidate-versus-control comparison records action, receipt, state, terminal
  bank/reward, and economic-diagnostic changes separately.
- An action digest difference alone never makes a context behavior-changing or
  efficacy-eligible.
- At least one receipt, public/economic state, bank/reward, or attributed
  economic diagnostic must differ in an effective context.
- `ac_bad79e4d71965c86b6b351a1` is classified as an economic no-op and excluded
  from robust, high-upside, selector-label, finalist, and promotion sets.
- Cancelled, truncated, unaffordable, or guard-failed orders are recorded and
  are not counted as executed edits.

## Boatlee gate

- `ac_3aa759d7d7fc4a409c409326` reconstructs the registered genome, compiled
  payload, effective patches, candidate ID, and standalone hash exactly.
- E2 S1 contains the fixed candidate and its frozen Boatlee control only; no
  hidden route, quantity, constant, or guard mutation is introduced.
- Fast and standalone execution are exactly equal in both seats on the
  technical probe.

## v27 selector gate

- `ac_46448f767f398cc4ce8047d3` reconstructs exactly as the probe branch.
- The other branch is the frozen unmodified v27 control.
- Every selector input is enumerated and public; opponent identity and private
  opponent information are absent by construction and by test.
- Missing features, malformed observations, time pressure, or failed probe
  preconditions preserve the incumbent.
- Technical fixtures exercise both selector branches and the fallback.
- At most two selector versions are frozen for E2 S1, with distinct IDs and
  exact standalone parity.

## Engine/runtime gate

- Both players end `DONE` in every retained technical game.
- There are zero candidate exceptions, timeouts, malformed structures, market
  queues over ten, or overage exhaustion.
- Atomic PLANT accounting retains the incumbent on missing/unreadable seed data
  and cancels same-crop overcommit atomically when the ledger is readable.
- Final legality projection remains the final operation before return.
- Runtime remains deterministic, self-contained, standard-library-only, and
  uses no filesystem, network, subprocess, multiprocessing, or verbose logs.
- Full-episode p95 latency is below 150 ms and maximum below 750 ms.

## Scheduler and artifact gate

- Workers 1 and 4 produce canonical equality in development; the hard maximum
  remains 15.
- Resume validates protocol, registry, engine, controls, candidates, opponents,
  and job hashes.
- Kill/restart, corrupt shard, import, engine, and worker failure injections do
  not produce efficacy scores or unlock a seed tier.
- Status is read-only.
- Finalist artifacts import and run from isolated directories.

## Repository gate

- Both incumbent builders pass `--check` and the shared source contract passes.
- Async V2, Async V3, and E2 tests pass.
- `git diff --check` has no new errors.
- Machine verification and the command transcript record exact hashes,
  commands, seeds, seats, parity, latency, and failure evidence.
- The human decision says exactly `READY_FOR_E2_S1` or
  `E2_DEVELOPMENT_REMEDIATION_REQUIRED`.
- Development performs no E2 game, fresh-seed execution, submission, commit,
  push, or remote mutation unless separately authorized by the user.
