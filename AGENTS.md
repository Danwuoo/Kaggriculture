# Kaggriculture Workspace Guide

This file governs work under `C:\Users\wurre\Desktop\Kaggriculture` unless a
more deeply nested `AGENTS.md` overrides it.

## Mission

Maintain and improve a reliable, competitive, multi-file Kaggriculture agent.
The current production design and canonical experimental control are:

> Efficient mixed livestock baseline + closed-loop task scheduling + exact
> market control + safe degradation.

This control is reliable but not close to the demonstrated public frontier.
Treat its route, scheduler, objective, and economic theory as hypotheses, not as
the definition of the problem. Before optimizing an existing mechanism, compare
materially different explanations, seek falsifying evidence, and prefer the
cheapest experiment that reduces uncertainty. Do not promote a change from a
single favorable seed, raw score, or winning margin.

Prefer a complete, tested, submission-ready change over a plan or an abstract
framework. Continue autonomously through implementation, tests, official-engine
games, performance checks, and packaging unless a decision cannot be recovered
from this workspace or an authoritative source.

Do not submit to Kaggle, create a remote repository, push commits, or otherwise
change external state unless the user explicitly asks in the current chat.

## Authority and Required Reading

Before changing strategy or engine-facing behavior, read:

1. `strategy.md`
2. `data/kaggriculture/AGENTS.md`
3. `data/kaggriculture/README.md`
4. The relevant material in `docs/competition/`
5. The current official engine source

When sources disagree, the current competition engine is authoritative:

- <https://github.com/Kaggle/kaggle-environments/tree/master/kaggle_environments/envs/kaggriculture>
- The local pinned checkout `.vendor/kaggle-environments` currently resolves to
  `a4dce5ae6e2ffe3c1afea8ec4b24b562df74cc07`.
- The latest retained experiment audit was verified against commit
  `bded87b0d7879078c726a93a4884d044f79c4eed` on 2026-08-08; that newer engine
  is not the current local pinned checkout.

Re-check upstream before relying on that commit in a later session. Do not edit
`.vendor`, `data`, or `docs` as part of normal agent development.

## Documentation Navigation

Use the narrowest authoritative document for the task:

| Need | Start here |
| --- | --- |
| Intended production strategy | `strategy.md` |
| Manually tuned standalone main approaches | `research/main_approach/README.md` |
| Packaged competition data and local rules | `data/kaggriculture/AGENTS.md`, `data/kaggriculture/README.md` |
| Saved competition page | `docs/competition/Kaggriculture _ Kaggle.html` |
| Initial implementation and validation | `reports/strategy_round1_2026-08-06.md` |
| Restoration of the canonical Round 2 control | `reports/round2_restoration_2026-08-08.md` |
| Latest arena and public-league evidence | `reports/arena_results.json`, `reports/public_league_results.json` |
| Retired family and one-factor decisions | `reports/experiments/README.md` |
| Top-50 replay metadata and external payload location | `data/public_replays/top50-2026-08-09/README.md` |
| Replay-clone analysis and archived full matrix | `reports/replay_clone_study/analysis.md`, `reports/replay_clone_study/full_matrix_report.md` |
| H1-H8 hypothesis cycle and redevelopment decision | `reports/hypothesis_cycle_2026-08-10.md` |
| Original replay-reproduction notes | `report_v1.md` |
| Downloaded public agents | `research/public_agents/README.md` |
| External artifact and retired-code map | `ARCHIVE.md` |

`report_v1.md` and the frozen replay-clone matrix are historical evidence with a
known mixed-engine configuration: newer Python semantics were patched into an
older package while its JSON still used a 12-turn town-center interval. Read the
2026-08-10 hypothesis report before drawing current-engine conclusions from
those results.

## Hand-Tuned Main Approaches

`research/main_approach/` is the canonical home for the project owner's
manually tuned, standalone strategy lines. It currently contains:

- `v27_current_meta/`: the original v27 fixed public route with actor-local
  weed repair and market SELL-slot ranking.
- `v27_current_meta_safety_guarded/`: the v27 route plus a same-turn seed
  ledger and fresh-crop watering protection.
- `boatlee_v16_rc2_market_relay/`: the Boatlee V16-RC2 livestock route with
  wool control and a guarded three-turn FERTILIZER market relay.

Each line retains a self-contained `main.py`. They are classified research
approaches, not production controls, and their presence here is not promotion
evidence. Compare them under an explicit engine/configuration fingerprint and
the standard paired safety/efficacy gates before reusing or packaging one. The
former `scripts/other appoach/` location was removed after its two v27 agents
were moved here; retained audit reports may still cite the old paths as
provenance.

## Evidence Retention and Deleted Material

The temporary route-memory, search, and learned-family program was retired on
2026-08-08 after none of its frozen candidates established competitive efficacy.
Only its narrative final reports and decisions remain under
`reports/experiments/`. The former `experiments/` tree, candidate source,
runners, raw matrices, logs, caches, and superseded snapshots were intentionally
deleted. Paths to them inside retained reports are provenance, not live
navigation or reproducibility promises.

Do not treat any reported family as a promotion candidate or restart the old
staged program without a new, explicitly authorized protocol.

On 2026-08-10 the workspace was compacted into an active source tree and an
external archive at
`C:\Users\wurre\Desktop\Kaggriculture-archive\2026-08-10`. The replay-clone
implementation, large raw matrix files, raw replay payloads, and completed or
rejected 2026-08-10 research implementations are retained there. Compact
decisions, analyses, manifests, and checksums remain in this workspace. Paths
inside historical reports that now point to archived files are provenance, not
live navigation. Read `ARCHIVE.md` before attempting to reproduce or resume an
archived lane.

The full-tape topology scale-up is not archived: its source and resumable cache
remain active under `research/full_tape_topology_scaleup_2026-08-10/` and
`research/cache/full_tape_topology_scaleup_2026-08-10/`. `.vendor/` and
`research/other_approach_submission_audit_2026-08-10/` were explicitly
excluded from the cleanup and must remain untouched unless the user separately
authorizes a change.

## Workspace Map

- `reports/experiments/`: narrative final reports and decisions from retired
  family and one-factor programs; raw per-game evidence is not retained.
- `reports/hypothesis_cycle_2026-08-10.md`: consolidated H1-H8 evidence,
  measurement audit, and final redevelopment rejection.
- `reports/replay_clone_study/`: retained replay-clone summaries and compact
  fidelity/specification evidence. Large raw matrix outputs are in the external
  archive; apply the mixed-engine caveat above.
- `submission/main.py`: Kaggle entrypoint exposing `agent(obs)`.
- `submission/controller.py`: episode lifecycle, timing budget, orchestration,
  caching, and fallback levels.
- `submission/state.py`: defensive observation normalization and derived state.
- `submission/rules.py`: legality, schema, resource consistency, and final
  action projection.
- `submission/scheduler.py`: P0-P5 job generation, assignment, logistics, and
  weed recovery.
- `submission/pathfinding.py`: cached all-pairs BFS for the 10x10 board.
- `submission/market.py`: exact price curve, per-unit projection, ordered sales,
  purchases, hiring, and land decisions.
- `submission/economy.py`: crop, animal, land, fertilizer, and terminal value.
- `submission/opponent.py`: public-information-only cohort forecasts.
- `submission/simulator.py`: compressed daily macro scenario selection.
- `submission/strategy.py`: stable spatial roles and desired farm topology.
- `submission/constants.py`: engine-matched constants.
- `submission/parameters.py`: small offline-tunable policy parameters.
- `tests/test_agent.py`: unit and official-engine rule tests.
- `scripts/run_arena.py`: official 720-step multi-seed/paired-seat arena and
  latency/safety report.
- `scripts/run_public_league.py`: scalable paired-seat league against safely
  extracted public research agents.
- `scripts/extract_public_agents.py`: static, non-executing notebook payload
  extractor and source audit.
- `scripts/analyze_top50_replays.py`: offline structural analysis of the fixed
  Top-50 replay snapshot. It reads compact metadata locally, raw payloads from
  the external archive by default, and writes regenerated large output there.
- `scripts/build_submission.py`: deterministic tarball builder and extracted
  import smoke test.
- `data/high scores notebook/`: downloaded high-scoring notebook sources; read
  them as evidence, never package or import them at runtime.
- `data/public_replays/top50-2026-08-09/`: fixed Top-50 snapshot metadata and
  authoritative manifest. The 50 raw replay payloads are externally archived
  at the location recorded in its `README.md` and in `ARCHIVE.md`.
- `research/main_approach/`: canonical catalog of the project owner's three
  manually tuned standalone agents; see its `README.md` before evaluation.
- `research/public_agents/`: downloaded public notebooks and offline-only
  extracted opponents; never package this directory into a submission.
- `research/full_tape_topology_scaleup_2026-08-10/`: the only retained active
  scale-up research lane; its checkpoint remains under `research/cache/`.
- `research/other_approach_submission_audit_2026-08-10/`: explicitly retained
  standalone submission audit; do not treat it as production.
- `ARCHIVE.md`: exact mapping of externally archived raw evidence, retired
  research implementations, and historical runners.
- `reports/arena_results.json`: latest generated arena evidence.
- `dist/submission.tar.gz`: generated Kaggle artifact; never edit by hand.

All runtime imports must work with the archive extracted directly into
`/kaggle_simulations/agent/`. Keep sibling imports absolute, lightweight, and
free of local filesystem assumptions.

## Engine Invariants

Preserve these rules in every change:

- The episode has 720 recorded states; meaningful agent actions are steps
  0-718. The engine marks both players `DONE` after processing step 718.
- Unit actions run before market actions. A product already carried can be
  `DROP`ped and then `SELL`ed in the same turn.
- Same-turn market purchases cannot fund or supply unit actions that were
  already processed. Earlier `SELL` orders can fund later market orders.
- `SELL` consumes shed inventory only. `HARVEST` writes to that unit's inventory.
- A fresh plant begins with `consecutive_unwatered = 1` and must be watered on
  its planting day or it becomes a weed at refresh.
- Two consecutive missed daily needs kill the asset: plants become weeds and
  animals escape permanently.
- PLANT demand is atomic per crop. If requests exceed seeds, every PLANT request
  for that crop is cancelled. Always use a same-turn shadow seed ledger.
- LOCKED tiles are traversable. In the audited current engine, center-shed
  `PICKUP`, `DROP`, and shed-directed `PLACE` are handled before the locked-tile
  guard and therefore remain legal; field mutations remain blocked. A hired
  hand may spawn on `(5,4)` while NE is locked and must be able to leave.
- The shed holds 100 non-seed items. DROP overflow is discarded before market
  processing; selling later in that turn cannot recover overflow.
- Market queues are ordered and capped at 10 entries. Extra orders are silently
  discarded.
- Market price is recomputed per unit. Splitting one order into several orders
  in the same turn does not improve its price.
- Price-floor sales do not add market inventory. BUY_PRODUCT quotes at post-buy
  inventory.
- At audited commit `bded87b0d7879078c726a93a4884d044f79c4eed`, the town
  center sells on a flat 24-turn interval and shops are sampled as instances
  with replacement, so duplicate shop types are possible, up to a cap of eight.
- The restored production control and local pinned package still encode older
  assumptions in places, including a 12-turn demand estimate and unlocked-only
  shed targeting. Fingerprint both the Python engine and configuration JSON
  before every current-engine experiment; do not call the control
  current-engine-matched without that check.
- State must reset when `step` returns to zero or moves backward and must remain
  isolated by player seat.
- Opponent modeling may use only public money, farm tiles, crops, animals,
  workers, land, town, shops, and market data. Never infer from account, team,
  or hidden private inventory.

## Strategy and Safety Priorities

Use lexicographic priorities that ordinary economic scores cannot override:

- P0: second missed water/feed would destroy an asset.
- P1: decay, full held yield, shed pressure, forced terminal return/drop/sale.
- P2: melon or fertilized production windows and bounded weed recovery.
- P3: normal feed, care, harvest, and logistics.
- P4: fertilizer collection and feed staging.
- P5: planting, building, digging, expansion, and optional investment.

The canonical control remains adaptive. Do not replace it merely because a
route is common in strong replays: the trajectory-primary redevelopment failed
both safety and efficacy gates. Its intended route is approximately 3 cows + 1
sheep in the opening, a small melon capital event, conditional NE then SW
unlocks, and a mature target near 8 cows, 5-6 sheep, 6-7 staggered strawberries,
and 10-12 hands when workload warrants it. SE must pass a remaining-time,
4,000-coin, labor, and commute marginal-return test. A materially different
route is allowed, but must earn promotion through fresh paired evidence and the
same safety gates.

For a planned PLANT or BUILD target that becomes a weed: DIG, revalidate next
turn, retry locally for a bounded number of turns, and cancel if terminal or
economic feasibility is gone. A recovery retry must still obey the planting
cutoff so it cannot create an unwatered crop late in the day.

## Runtime Constraints

The official action timeout is one second. Keep normal turns far below 150 ms.
Use `time.perf_counter()` and preserve the controller's levels:

- Level 0: full macro plan, opponent forecast, jobs, and market control.
- Level 1: reuse macro state and update jobs/market only.
- Level 2: survival, harvest, return/drop, legal liquidation, and schema safety.

Runtime code must not use networking, subprocesses, multiprocessing, pandas,
sklearn, heavy models, file writes, or verbose logging. Offline scripts may use
files and subprocesses for validation/building.

## Development Workflow

1. Inspect the workspace and, if present, `git status -sb`. Preserve unrelated
   and user-owned changes.
2. Read the relevant modules and official engine code before editing.
3. Use `apply_patch` for source edits.
4. Keep the legality projector as the final boundary before returning an action.
5. Compile and run unit tests.
6. Run the official arena for behavioral, paired-seat, determinism, and latency
   evidence.
7. Rebuild the tarball only after all validation passes.
8. Extract and import-smoke-test the tarball; for material changes, also run one
   complete game using the extracted package.
9. Report exact results and remaining risks. Do not describe a generated report
   as passing unless its current contents support that claim.

PowerShell validation commands from the workspace root:

```powershell
python -m compileall -q submission tests scripts
$env:PYTHONPATH=(Resolve-Path '.vendor\kaggle-environments').Path
$env:TF_CPP_MIN_LOG_LEVEL='3'
python -m unittest discover -s tests -v
python scripts\run_arena.py
python scripts\build_submission.py
```

The source checkout may print `Loading environment open_spiel_env failed: No
module named 'pyspiel'`; this is unrelated to Kaggriculture when the
Kaggriculture environment loads and runs successfully.

## Acceptance Gates

A submission candidate is ready only when:

- All unit tests pass.
- Self-play ends with both players `DONE`.
- Multi-seed games against `starter` and `random` run from both seats.
- Same seed + same strategies reproduce identical rewards and action digest.
- There are zero timeouts and malformed actions.
- Replay auditing finds zero animal escapes, zero fresh-crop water deaths, and
  zero shed states above capacity.
- Market lists never exceed 10 entries and emitted PLANT requests never exceed
  available seeds.
- A full official episode records p50, p95, p99, and maximum agent latency; p95
  must stay under 150 ms and maximum under 750 ms.
- `dist/submission.tar.gz` is under 5 MiB, contains `main.py` at archive root,
  excludes tests/replays/cache/venv, and imports after extraction.

## Experiment Results and Decisions

These summaries are decision memory, not permission to reuse deleted candidates.
Consult the linked reports for protocols, seed sets, and caveats.

### Production controls and public league

- Round 1 established the safe multi-file baseline; Round 2 added regional
  scheduling and shipping ETA and is the restored canonical control.
- The initial 10-replay audit found only about 22-24% field/logistics actions,
  2.7-2.9 moves per productive action versus roughly 1.7-1.9 for strong winning
  opponents, and a planned 6-7 strawberry target usually realized as only 2-3.
  Under the then-pinned engine, unlocked-only shed routing plus an eight-melon
  opening addressed a real logistics/capital defect; this historical locked-
  shed conclusion must not be projected onto the newer audited semantics.
- An intermediate old-versus-new candidate matrix was 10 wins and 2 losses with
  mean paired terminal difference +2,403.42. The retained final Round 2
  candidate then went 12-0 against the exact old archive across six seeds and
  both seats, averaging +11,662.00. See
  `reports/candidate_vs_baseline_round1.json` and
  `reports/candidate_vs_baseline_round2.json`.
- A broader sticky-assignment variant was rejected immediately after causing
  two animal escapes; it is not in production.
- The 80-game public-agent league was 4 wins and 76 losses. Against the four
  strongest extracted public routes, the control was 0/64 despite zero safety
  failures. Reliability therefore does not establish competitive efficacy.

### Retired three-family program

Results below use wins-draws-losses as recorded in
`reports/experiments/README.md`:

| Family | Result | Decision |
| --- | --- | --- |
| Route memory, Stage 1 | 4-0-316; paired 2-0-158 | Failed efficacy gate. |
| Route memory, Stage 2 | `adaptive_profit` 10-0-630; `nearest_robust` 11-0-629 | Both selector variants failed. |
| Route memory, Stage 3 entry | `full_repaired` 1-0-639 | `DO_NOT_ENTER_STAGE3`. |
| One-day search hybrid | 0-0-320 | `DO_NOT_ENTER_STAGE2`. |
| Linear learned hybrid | 0-0-320 | `DO_NOT_ENTER_STAGE2`. |

The common lesson is that route selection, one-day ranking, and linear behavior
cloning did not overcome the shared execution core. The underlying candidates
and runners no longer exist in this workspace.

### One-factor lanes and failed current-engine integration

| Lane | Evidence | Decision |
| --- | --- | --- |
| 01, current-engine parity | Reproduced audited current semantics and served as a correctness control. | Baseline only; no efficacy claim. |
| 02, four-way shed | Higher starter margin in 3/4 pairs, mean +1,493; public-opponent run hit its time cap. | Insufficient for promotion. |
| 03, short zone scheduler | Positive in 1/4 pairs; mean -1,791.25. | Stop. |
| 04, capital/herd timing | Positive in 1/2 seed-pairs (2/4 seats); combined -5,664. | Stop. |
| 05, 14-strawberry scale | 0/4; mean -4,676. | Stop. |
| 06, shop-conditioned portfolio | 0/4; mean -10,674.5. | Stop. |
| 07, four-way shed isolation | Higher current-engine margin in 1/4; mean paired delta -1,955.25. | Stop. |

A later current-engine integration passed its correctness gates, including
23/23 tests, but improved public-match margin in only 5/16 bounded comparisons
with mean delta -291.19 and then received a lower live leaderboard result. It
was restored away. Its decision report is retained at
`reports/experiments/current_engine_integration_failed/decision.md`; several raw
artifact links inside that report point to intentionally deleted files.

### Replay-clone study

The Top-50 snapshot showed a highly concentrated visible route but not a shared
complete policy: 45/50 replays had the same macro fingerprint and 33/50 the
exact unit-action sequence, while every complete action tape, market tape, and
market-order shape was distinct.

Three closed-loop reference clones were safe but competitively ineffective:

| Clone | Matrix result | Average margin |
| --- | --- | --- |
| Rank-1 full-map 10-cow/11-sheep | 0-0-96; paired 0-0-48 | -97,629.0 |
| Cow-heavy 12-cow/2-sheep | 0-0-96 | -102,141.6 |
| Dominant 8-cow/6-sheep | 0-0-96 | -107,700.2 |

Interpret these results with the mixed-engine measurement caveat in
Documentation Navigation. They falsify the retained clone implementations, not
the broader claim that strong agents exploit coordinated trajectories.

### H1-H8 uncertainty-reduction cycle, 2026-08-10

The full protocol and evidence are in `reports/hypothesis_cycle_2026-08-10.md`.

| ID | Hypothesis and discriminating result | Decision |
| --- | --- | --- |
| H1 | Small intended scale is the main bottleneck. Exact v25 created a much larger turn-240 farm, but v25-to-canonical scored 91,427 versus all-canonical 99,084 and lost 20 inherited strawberries. | Reject as primary cause. |
| H2 | Season-scale multi-worker trajectory commitment is missing. Strong routes showed less travel and more productive work; a day-local proxy went 4/4 on reused seeds but only 3/1 on fresh holdouts, with paired means +52 and +516 instead of +13,178. | Mechanism plausible; tested proxy not established. |
| H3 | A different opening capital basin is sufficient. Exact v25 scored 200,213 versus 99,084, but handoffs to canonical at 24/72/240 scored 56,738/92,351/91,427. | Reject sufficiency; continued execution carries the value. |
| H4 | Shared-market timing is frontier alpha. SELL ranking won a near-clone comparison 4/0 with about +153 mean margin; cross-family preemption changed only tens of coins and no W/L. | Stable small edge, not main gap. |
| H5 | The apparent limit is partly measurement artifact. The clone study used a 12-turn JSON interval while audited current semantics use 24, and locked center-shed behavior also differs. | Supported. |
| H6 | Clone evaluation mismeasured exact public artifacts. Exact Kaito v21 and Saiteja 3000 beat canonical in both seats; Roman lost both, but none maps to a specific Top-50 team and conditioned tapes later diverged. | Moderately supported, identity unresolved. |
| H7 | Raw terminal bank is the wrong selection objective. Raw-bank P1R1 and paired-win P0R1 market variants both went 4/0 versus Kaito. | Not supported by bounded test. |
| H8 | The Top-50 modal field route is the right imitation target. Route concentration was high, but all 50 full/market tapes were unique. | Reject as sufficient formulation. |

The resulting trajectory-primary Preempt-H6 redevelopment was rejected. Before
its guard fix it went 0/4 versus canonical and 0/2 versus exact v25 with 32
animal escapes. Independent post-fix validation still lost both seats to
canonical on fresh seed `618273` (117-759 and 117-670) and lost four animals in
each game. Do not promote, package, or resume this candidate; use it only as
negative evidence about fixed-tape compatibility and maintenance feasibility.

## Current Verified Baseline

The production tree is the restored Round 2 canonical control, not any
experiment candidate. On 2026-08-10, all 13 files under `submission/` matched an
isolated Round 2 control snapshot by SHA-256, and the archive digest was still
unchanged. Its initial retained 2026-08-06 validation report recorded:

- 18/18 unit tests passing.
- 13 official arena games all ending with both players `DONE`.
- 6/6 wins against `starter` and 6/6 wins against `random`, using three seeds
  and both seats.
- Zero malformed actions, animal escapes, fresh-crop deaths, and overflow states.
- Deterministic repeated self-play at seed 777.
- Full-episode latency: p50 0.7387 ms, p95 1.07972 ms, p99 1.50608 ms,
  max 9.1504 ms.
- Archive size 17,340 bytes with SHA-256
  `C84664D77EB9D32CE7001D31EE15634AE144B9403BA98D43B1D69226A588AAB2`.
- The 80-game public-agent league ended 4 wins and 76 losses. The control was
  0/64 against the four strongest public routes while retaining zero safety
  failures. See `reports/public_league_results.json`.

The 2026-08-08 restoration independently reran compilation, 18/18 tests, all 13
arena games, determinism, safety, and an extracted-package game. All passed; its
719-call latency was p50 0.7774 ms, p95 1.04767 ms, p99 2.00739 ms, and maximum
10.4343 ms. See `reports/round2_restoration_2026-08-08.md`.

Those gates were run against the older local pinned package. Because production
was deliberately restored after the failed current-engine integration, it is
not currently verified as semantically identical to audited commit
`bded87b0d7879078c726a93a4884d044f79c4eed`. Establish an explicit current
engine/configuration fingerprint before using it as a current-engine control.

Kaggle submissions `55283999` (`Hybrid livestock closed-loop scheduler v1`) and
`55287643` (`Round 2 regional scheduler + shipping ETA; safety-gated`) were both
`COMPLETE` when checked on 2026-08-06, with API public scores 668.6 and 783.0.
These values are historical and simulation ratings continue to move: query the
live state with `kaggle competitions submissions kaggriculture --csv` before
reporting it.

The workspace was not a Git repository when this guide was created. Do not
initialize a repository or invent a remote without explicit user direction.

## Top-50 Public Replay Dataset

The workspace contains the metadata for a fixed public-leaderboard replay
snapshot at `data/public_replays/top50-2026-08-09/`; its raw payloads are under
`C:\Users\wurre\Desktop\Kaggriculture-archive\2026-08-10\data\public_replays\top50-2026-08-09\replays`.
It was captured at
`2026-08-08T16:10:15.675637Z` and contains 50 unique official replays, one for
each leaderboard rank 1-50. For every team, the retained episode is the highest
reward completed public episode of the active submission whose public score
matched the leaderboard snapshot. All 50 happened to be distinct, so no
next-best duplicate fallback was needed.

Do not describe all of these as `3000+` leaderboard agents. Only ranks 1-28 in
the snapshot had leaderboard ratings at or above 3000 (`3003.2-3201.1`); ranks
29-50 were rated `2935.1-2997.5`. The selected episode rewards are a different
metric and range from `134,868` to `183,163`. "Top replay" in this dataset means
the highest single-game reward available for that team's matched submission,
not a leaderboard rating above 3000 or an estimate of expected performance.

The 50 externally archived, uncompressed JSON files total 1,391,681,379 bytes
(1.296 GiB). All were
verified as 720-step `DONE`/`DONE` episodes with matching team rewards and
SHA-256 checksums. Engine module versions are 47 replays on `1.32.6`, two on
`1.32.5`, and one on `1.32.4`. Treat `manifest.json` as the authoritative index,
`leaderboard_snapshot.json` as the ranking evidence, and
`scripts/collect_top_public_replays.py` as the reproduction tool.

A replay exposes each player's own private observation. Combining both records
offline therefore reveals information that neither agent possessed during play.
Use private fields only to audit that same player; cross-player comparisons and
runtime opponent modeling must remain limited to public farms, actions, market,
town, and reward data.

## Highest-Value Next Work

Start from matched, one-factor ablations against the canonical control, but do
not assume that more assets, a different opening, or the modal fixed route is
the right formulation. The highest-information next abstraction is
route-state compatibility plus maintenance feasibility: test whether a planner
can accept a dense inherited state, preserve all animals and fresh crops, and
continue productive work before building another full trajectory policy.

For every new program:

1. Fingerprint the exact engine Python and configuration JSON first.
2. Predeclare the mechanism, support and falsification evidence, smallest
   discriminating game block, fresh holdouts, stopping rule, and what a failed
   experiment would still teach.
3. Keep lanes isolated from production and from one another. Preserve every
   loss and invalid run in the decision record.
4. Require zero survival/safety violations and a positive paired-win signal on
   fresh, unused seeds before expanding the program. Diagnostics such as lower
   travel or higher productive-action rate are supporting evidence, not
   promotion criteria.
5. Optimize family-stratified paired match wins first; use own bank and margin
   as secondary diagnostics. Treat SELL ordering as a late-stage marginal edge.

Do not restart scale-only, opening-only, one-day commitment, linear-clone, or
fixed-tape programs without a new mechanism and a protocol that distinguishes
it from the failures recorded above.
