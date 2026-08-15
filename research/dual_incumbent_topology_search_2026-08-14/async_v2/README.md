# Dual-incumbent asynchronous topology search v2

This version replaces the narrow ninth-cow root screen with a coupled,
population-based search over each incumbent's complete readable route and
runtime policy surface.

The search genome may contain up to eight non-overlapping 8--48 turn route-block
genes, several public-market policy genes, and several lane-owned runtime
constant genes at once.  Route blocks are mined from the corrected local
high-score tape corpus, but they execute only when their public entry and
actor-path/rejoin contracts match the active incumbent.  Full donor tapes are
never replayed as candidates.

The two populations are independent:

- `v27_current_meta` owns its route blocks, candidate IDs, policy constants,
  evaluations, archive, checkpoints, and decisions.
- `boatlee_v16_rc2_market_relay` owns a separate copy of all of those objects,
  including its livestock, wool, and relay genes.

Only the donor hypothesis language and offline implementation are shared.
Scores and rewards are never pooled across lanes.

The completed 2026-08-14 S1 ninth-cow screen is retained as negative evidence
that an eight-root, one-factor surface was too narrow.  It is not an input
population and does not authorize another fresh-seed run.

## Development boundary

All v2 development and smoke search use the already-consumed technical seed
`811407`.  A fresh formal manifest requires a new explicit authorization after
the v2 development verification is complete.

The E1b extension uses four lane-local islands (`route`, `market`, `constants`,
and `coupled`) with same-lane crossover and a novelty archive.  Semantic
phenotypes are rejected before efficacy work when they are semantic no-ops or duplicates;
returned-action digest vectors provide the later behavioral deduplication and
cross-generation candidate/context cache key.  Ranking resolves near ties by
opponent consistency, paired wins and losses, worst downside, own bank, and
finally topology complexity.  Every Pareto finalist must pass fast/standalone
parity from both seats.

Static topology capacity counts only compile-distinct, nonempty semantic
phenotypes.  It is not an exact behavior-changing count: exact change requires
comparison with the lane-relative control action digest in an evaluated
technical context.  Reports therefore publish the static capacity and the
observed technical action-change rate as separate fields, including observed
action no-ops as negative evidence.

The worker default and cap are both 15.  Windows processes use `spawn` without
`DETACHED_PROCESS`; atomic checkpoints, corrupt-artifact preservation, resume,
failure recovery, and read-only status are acceptance requirements.  The E1b
progressive protocol in `formal/e1b_progressive_protocol.json` is a frozen
non-executable design.  This development does not launch any E1b or E2 game.
Formal authorization, technical seeds, retained/consumed E1 seeds, and fresh
seeds are recorded independently from the frozen seed registry; authorization
alone never sets `formal_fresh_seeds_executed`.
The formal launcher accepts fresh seeds only when schema-v2 protocol and frozen
registry classifications agree and their hashes are part of the validated
authority.  A retained-consumed stage passes an empty `fresh_evaluation_seeds`
tuple; unknown seeds are rejected rather than inferred fresh.
The validated non-default registry path and loaded registry identity are passed
unchanged through preflight, execute, manifest construction, resume, summary,
and status.  A registry hash/run-id change invalidates resume before evaluation.
Preflight records seeds as configured with `execution_started=false` and
`execution_completed=false`; executed flags belong only to a started run.
