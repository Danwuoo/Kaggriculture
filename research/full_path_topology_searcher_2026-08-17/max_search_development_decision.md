# Maximum full-tape search development decision — 2026-08-21

Decision: **LONG-RUNNING EXECUTION SYSTEM COMPLETE AND TECHNICALLY VERIFIED;
FORMAL EXECUTION REMAINS BLOCKED AND UNAUTHORIZED**.

The requested maximum scale is closed exactly rather than interpreted as
16,384 new births in every generation. Generation 0 has 16,384 residents and
generations 1–1,999 allocate 29,983,616 births, totaling 30,000,000 unique raw
candidates. Six T0 games per candidate produce 180,000,000 candidate-games;
5,000,000 T1 promotions receive 24 additional games for 120,000,000 more. The
T0/T1 total is exactly 300,000,000. Broad-finalist and frozen-control games are
accounted outside that number.

The implemented development substrate represents complete 719-turn tapes with
lane-owned roots and sparse canonical patches. It supports horizons through
719 turns, multiple non-incumbent roots, deterministic lane-compatible
crossover, four search modes across 32 lane-balanced islands, exact persistent
candidate uniqueness, lane-local Pareto/tail ranking, signed atomic
manifest/checkpoint state, and read-only status. Runtime projection preserves
the incumbent as fallback, enforces action schema and market/PLANT constraints,
and forbids pooling the two incumbent lanes.

The first fresh Sol/High audit returned `fix-first` on integrity rather than
search architecture. Remediation now closes every nested contract field,
blocks schema-v2 formal authorization unconditionally, binds dirty/untracked
implementation source bytes into the run manifest, uses lane-encoded full
SHA-256 candidate identities with canonical collision checks, enforces exact
island capacity/uniqueness/lane ownership, binds fitness to lane and incumbent
control, rejects invalid and non-finite survivor scores, and journals the birth
shard before SQLite commit so either side of the crash window is reconcilable.
The second fresh audit then found four residual closure gaps. Scoring rows now
derive immutable provenance from the signed run manifest and the concrete
genome; prepared/final summaries validate a closed schema, requested island
quotas, ordinals, shard bytes/hash, status, and statistics; every index path
requires exactly the allowed generation set; and finalist selection fixes both
50 candidates per lane and the declared margin/bank/complexity/novelty order.
The third audit found that provenance alone did not protect caller-supplied
derived score fields and that recovery needed a coordinator-level lane check.
Scores now recompute margins, bank deltas, outcomes, and WDL transitions from
raw receipts and reject any mismatching derived field. Birth genome, parent,
and mate lanes must match the fixed island in both CLI restoration and the
index add/validate/reconcile APIs. The fourth audit found one remaining direct
API bypass: `score_candidate` accepted an empty opponent-family label even
though `paired_row` rejected it. Scoring now rejects that value itself, and a
regression test closes the bypass.

Development verification created all 16,384 generation-0 candidates, wrote and
re-read a bounded generation-1 birth shard, and completed official-engine no-op
and effective-mutation smokes from both seats on both lanes. All 8 no-op and 8
mutation technical games ended `DONE/DONE`; the mutation changed the action
digest without action-schema findings. Searcher tests passed 90/90, Async V3
passed 23/23, main-approach contracts passed 3/3, both generated artifacts were
current, V1 authority validation passed, and `git diff --check` was clean.

A fifth fresh Sol/High reviewer independently rechecked the cumulative V6
contract, lane isolation, candidate identity, recovery, raw-receipt scoring,
empty-family rejection, manifest binding, and fail-closed execution boundary.
It returned `ship` with no blocking finding. Because its host sandbox was broad
rather than enforced read-only, exact pre/post dirty-state hashes were compared
and matched.

This development audit did not claim that 300 million games had run or that the
search had efficacy. At that audit boundary the formal scheduler was withheld;
the later launch record below supersedes only that execution boundary. No
incumbent promotion, Kaggle submission, or remote state change followed from
the development audit.

The execution extension now adds signed, stage-disjoint context registries;
signed execution manifests and checkpoints; a persistent Windows-spawn process
pool with bounded in-flight games; exact cached controls and idempotent T0/T1
receipts; deterministic per-generation promotion quotas; scalable risk-first
and objective-extreme survival; birth-shard reconciliation; complete next-
population recovery checks; and exact final counter closure. An absolute
generation stop boundary supports planned pauses without changing quotas or
candidate identities. Broad-finalist output is fixed at 50 candidates per lane
and cannot automatically launch another tier, promote, or submit.

A three-generation deterministic integration completed 192 candidates and 288
candidate-games. A two-generation official-engine integration used 18 distinct
worker processes in each generation, paused after generation 0, resumed to 128
T0 and 64 T1 receipts, and returned immediately with no changes when invoked
again after completion. A source-matched 160-game official calibration measured
74.33% CPU, 1.3517 games/s, and 3,123.2 bytes per receipt. Searcher tests now
pass 103/103; Async V3 passes 23/23; main-approach contracts pass 3/3; both
incumbent generated artifacts remain current. After dynamic-retention work,
the full searcher suite passes 104/104.

The preceding pre-launch storage conclusion is superseded by the user's
authorized dynamic-retention design. Every receipt is hash-committed; all
negative margins, technical failures, and worsened economic diagnostics are
retained in a signed per-generation gzip ledger; raw SQLite receipts are then
deleted and their pages reused. A two-generation pause/resume test preserved
logical counts while returning live raw receipts to zero.

On 2026-08-21 a fresh 6-T0/24-T1/24-holdout registry was frozen. An 11-worker
official calibration passed at 57.48% CPU and 1.3439 games/s; 12 workers was
rejected at 69.17%. Formal execution `max_search_formal_300m_20260821_v1`
started in the background as PID 3912. Launch verification observed 11 workers,
60 persisted controls, the first 192 formal T0 receipts, and empty stderr. This
is execution evidence, not efficacy or promotion evidence. The untouched
holdout and every external/later-tier action remain unauthorized.

Machine-readable substrate evidence is in
`max_search_development_verification.json`; execution evidence is in
`max_search_execution_verification.json`; formal launch evidence is in
`max_search_formal_launch_20260821.json`.
