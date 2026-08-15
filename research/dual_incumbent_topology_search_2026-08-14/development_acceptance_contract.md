# Development acceptance contract

The D0--D4 implementation is ready for formal S1 only when all conditions are
machine-verifiably true.

## Independence

- Every genome compiles separately for v27 and Boatlee.
- Candidate IDs, outputs, controls, caches, shards, summaries, and decisions
  include the incumbent identity.
- A lane may reject or pass without affecting the other lane.
- No summary pools raw rewards or paired margins across incumbents.

## Compiler

- All local windows are between 8 and 48 turns.
- Every displaced action is `retained`, `reassigned`, or `reclaimed`.
- BUY/BUILD/PLACE, actor choice, travel, resources, lifecycle, market timing,
  fallback, and rejoin are explicitly represented.
- Missing a same-step incumbent cow action or matching actor is never a valid
  rejection reason.
- Static rejection codes are non-circular and name the failed path, resource,
  precondition, market, lifecycle, actor-continuity, or rejoin constraint.

## Runtime and engine

- Final schema/hand/market/atomic-seed projection is the last boundary before
  return.
- Missing or unreadable own-private resource state degrades to the incumbent.
- Opponent features use public state only and contain no opponent identity.
- Every retained technical game ends `DONE/DONE` with zero exception, timeout,
  malformed action, hand drift, market overflow, or overage exhaustion.
- Same seed/seat/opponent reproduces rewards and both action digests.
- p95 latency is below 150 ms and max below 750 ms.

## Evaluator and scheduler

- Fast and materialized standalone candidates are exact in both seats.
- Worker count 1 and worker count >1 produce the same canonical merge.
- Resume rejects a mismatched manifest/hash and detects corrupt shards.
- Engine/import/worker failures yield infrastructure records with no efficacy
  fields and cannot unlock a seed tier.
- Status performs no writes.

## Artifacts

- Research standalones are self-contained, standard-library-only, import in an
  isolated directory, and perform no runtime file/network/subprocess/process
  operations.
- Both incumbent builders and `--check` pass, as does the shared development
  source contract.
- Exact engine/config hashes match the frozen protocol.
- `formal_fresh_seeds_executed` is `false` throughout D4.
