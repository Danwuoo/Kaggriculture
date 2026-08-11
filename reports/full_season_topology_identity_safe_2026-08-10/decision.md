# Identity-safe full-season topology experiment — decision

Date: 2026-08-10

Decision: **retain as a complete, executable negative experiment; do not
promote or package the candidate.**  The model produced a valid whole-season
selector candidate, but it failed the predeclared fresh paired efficacy gate.
Production `submission/` and `dist/` were not changed.

## A. Executable whole-season candidate

Yes.  `build_topology_model.py` selected `zero_to_top_meta` from the four
statically extracted exact notebook `main.py` controls.  `candidate_agent.py`
loads the frozen model and delegates every meaningful step 0--718 to that exact
controller.  There is no maintenance fallback, short takeover, random-split
state-to-action classifier, or branch without a complete continuation.

This is a new executable **model-selected backbone candidate**, not a claim of
new controller behavior: its runtime behavior is the selected exact
`zero_to_top_meta` notebook controller.  Its value is that the selector was
constrained by complete-season topology and executable safety evidence.

The model compares the complete 719 aligned unit tapes and market tapes
separately, including full-sequence Hamming distance, prefix/suffix structure,
and 30 phase blocks.  Its lexicographic selection order was:

1. retained exact-panel safety and determinism;
2. minimum mean margin over executable opponent families;
3. overall mean margin;
4. complete-season topology proximity.

All four notebook sources were recovered statically from
`data/high scores notebook/`; the extracted artifact manifest contains source,
notebook, code, and embedded-tape hashes.  No notebook payload was executed
during extraction.

## B. Fresh paired increment over an exact backbone

The direct exact baseline was `adaptive_farming`.  Evaluation used previously
unused seeds `826081` and `826087`, both seats, and live executable Kaito v21,
Saiteja 3000, and Roman LB950 families.  This produced 12 paired margin deltas:

| Family | Positive / pairs | Mean paired margin delta |
| --- | ---: | ---: |
| Kaito v21 | 2 / 4 | +3,591.50 |
| Saiteja 3000 | 0 / 4 | -3,489.00 |
| Roman LB950 | 2 / 4 | +14,481.75 |
| **Overall** | **4 / 12** | **+4,861.42** |

The positive overall mean is driven by two large Roman results and is not a
promotion signal.  The candidate failed both required efficacy conditions:
only 4/12 deltas were positive (gate: at least 8/12), and the Saiteja family
mean was negative (gate: every family mean positive).

The separate 24-game one-seed exact-control screen retained every result:

| Exact control | Safe games | W-D-L | Mean margin |
| --- | ---: | ---: | ---: |
| `adaptive_farming` | 6 / 6 | 6-0-0 | +37,261.67 |
| `preempt_h6` | 6 / 6 | 6-0-0 | +37,257.00 |
| `zero_to_top_meta` | 6 / 6 | 6-0-0 | +44,489.67 |
| `v25_meta_reset` | 0 / 6 | 6-0-0 | +45,809.33 |

`v25_meta_reset` escaped one animal in every screen game and had seed
overcommit in two games, demonstrating why raw score cannot override safety.

## C. Safety, determinism, efficacy, and latency

The selected candidate passed the full safety and determinism gates across all
12 paired games:

- all games ended `DONE`/`DONE` with 720 recorded states and 719 candidate
  calls;
- zero animal escapes, fresh-crop deaths, observed shed-overcapacity states,
  malformed actions, market-list overflow, seed overcommit, exceptions, and
  timeout calls;
- maximum observed shed load was 96/100;
- the two determinism games had the same action digest
  `69844fe3f11aa93ff35a692654d50c2f2b33a54264e61bf42c4a355f4ed1337b`
  and identical rewards 81,199 versus 72,994;
- across the 8,628 timed paired calls, worst per-game p95 was 0.9245 ms,
  worst per-game p99 was 1.1998 ms, and global maximum was 2.2681 ms.

Safety gate: **PASS**.  Determinism gate: **PASS**.  Efficacy/promotion gate:
**FAIL**.  Therefore the candidate is not submission-ready and was not copied
into production.

## D. Complete trajectories and provenance

The new fixed-snapshot corpus contains 50 snapshot-valid records.  Every
record has:

- 720 target-player observation/state labels;
- 719 canonical full actions, with separate unit and market tapes kept in
  season alignment;
- snapshot, team, score, submission, episode, target seat, engine version,
  raw replay SHA-256, and record SHA-256 provenance;
- only that player's private shed/seeds/inventories; the opponent contributes
  public farm, market, town, and reward fields only.

The authoritative fixed snapshot ID is
`sha256:cef04aa8897ffb20ea27c32d4b7eb9863a80cdc3f42e13986486bddada6470da`,
captured at `2026-08-08T16:10:15.675637Z`.  All 50 source replay hashes and
720-state `DONE`/`DONE` contracts were rechecked.  Engine versions are 47 on
1.32.6, two on 1.32.5, and one on 1.32.4.

The old scale-up cache is retained only as 246 **temporal-pooled** complete
719-action prototypes.  It has only 30 daily state labels, no valid single
snapshot coverage claim, and invalid mutable-rank provenance.  Identity-safe
deduplication yields 227 support representatives and excludes 19 duplicates.
Those rows are never counted as new 720-label trajectories.

Thus the experiment used 296 complete action trajectories in total, of which
277 were support-eligible; only the 50 fixed-snapshot records meet the new
720-state-label provenance contract.  Fixed-snapshot checkpoint keys are
`snapshot_id + team_id + score + submission_id + episode_id`, never rank.

## Engine and configuration

The experiment patched the read-only local package in memory to upstream
commit `bded87b0d7879078c726a93a4884d044f79c4eed` and used explicit current
configuration.  The verified hashes were:

- normalized Python SHA-256:
  `FB9215C5E21A25243E2D13E75B3D70A79CF7D78FFF150A90F1BB5EACF9BA2BCF`;
- JSON SHA-256:
  `7F196F4AAF9B4E482FBD61BA4BF19F5CEC4DA0F81938ECE756954035A65C0BB5`.

Functional checks confirmed a 24-turn town-center interval, a hired hand on
locked `(5,4)`, and legal center-shed pickup while that tile is locked.

## E. Checkpoint and resumption

No process is currently running.  All planned stages are complete: 24 control
games, 24 paired arm games (12 pairs), and two determinism games.  The durable
checkpoint is:

`research/cache/full_season_topology_identity_safe_2026-08-10/evaluation/games.jsonl`

Re-running a stage skips existing game keys and safely continues any missing
items.  The current result can be regenerated without playing a game:

```powershell
python research\full_season_topology_identity_safe_2026-08-10\run_experiment.py --stage summarize
```

Corpus construction is also resumable per replay through `checkpoint.json` and
the identity-keyed manifest; `--max-records 10` bounds a resumed batch.

## Artifacts

- `research/full_season_topology_identity_safe_2026-08-10/`: source, tests,
  exact controls, and executable candidate;
- `research/cache/full_season_topology_identity_safe_2026-08-10/`: corpus and
  game checkpoints;
- `reports/full_season_topology_identity_safe_2026-08-10/model.json`: frozen
  topology and selection evidence;
- `reports/full_season_topology_identity_safe_2026-08-10/evaluation.json`: all
  50 game rows and aggregate gates;
- `reports/full_season_topology_identity_safe_2026-08-10/engine_fingerprint.json`:
  source/config hashes and functional semantics checks.

The existing production archive remained SHA-256
`C84664D77EB9D32CE7001D31EE15634AE144B9403BA98D43B1D69226A588AAB2`.

