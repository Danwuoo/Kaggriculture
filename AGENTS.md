# Kaggriculture Main-Approach Guide

This file governs work under `C:\Users\wurre\Downloads\Kaggriculture` unless a
more deeply nested `AGENTS.md` overrides it.

## Current Focus

The active development center is `research/main_approach/`, with two independent
incumbent strategy lines:

| Incumbent | Core mechanism | Editable source |
| --- | --- | --- |
| `v27_current_meta` | HIRE4-derived fixed route, actor-local weed repair, and market SELL-slot ranking | `research/main_approach/v27_current_meta/development/` |
| `boatlee_v16_rc2_market_relay` | Boatlee V16-RC2 livestock route, wool control, and guarded three-turn FERTILIZER relay | `research/main_approach/boatlee_v16_rc2_market_relay/development/` |

Treat both as first-class incumbents. Do not silently make one the universal
baseline, transplant a result from one to the other, or report an aggregate
gain that hides a regression on either line. They may share hypotheses, test
harnesses, and offline analysis, but their runtime modules, routes, generated
artifacts, controls, and evidence must remain independently attributable.

### Current topology-search state: E1c complete, E2 development next

The Async V3 E1c retained-seed search completed on 2026-08-15. Do not restart
or broaden E1 merely because its population code remains available. Its search
surface saturated: the useful Boatlee result appeared in generation 0 and the
v27 high-upside result in generation 1, with no late-generation improvement.

The next authorized work is contract-scoped E2 development under
`research/dual_incumbent_topology_search_2026-08-14/e2/`. It has two independent
lane roles:

- Boatlee fixed finalist `ac_3aa759d7d7fc4a409c409326`, a one-block market
  route over steps 237--245;
- v27 diagnostic probe `ac_46448f767f398cc4ce8047d3`, used only as a branch
  for a public-state selector, never as an always-on promoted candidate.

The v27 E1c representative `ac_bad79e4d71965c86b6b351a1` is an economic no-op
counterexample. An action-digest difference alone is no longer sufficient for
behavior-change, efficacy, frontier, or finalist eligibility. Require an
executed receipt, public/economic state, terminal bank/reward, or attributed
economic-diagnostic difference relative to the lane control.

E1c used only previously consumed seeds `81426017` and `81426029`.
`formal_fresh_seeds_executed=false` for E1c, and no E2 fresh seed has been
selected or executed. E2 development does not authorize E2 S1 launch.

`v27_current_meta_safety_guarded/` is retained as a useful reference variant,
not a third active development line. The multi-file `submission/` tree is the
restored Round 2 reliability control; it is no longer the default optimization
target and must not displace the two main approaches in experiments unless the
hypothesis specifically requires it.

### Primary Research Objective: Strategy Tuning and Route Topology

The **first and highest-priority objective** is strategy-level micro-tuning and
route-topology exploration on both incumbents. Optimize decision boundaries,
short action motifs, divergence and legal rejoin points, worker allocation,
production timing, and public-market exposure before considering another broad
runtime, planner, model, or software-architecture redesign. Prefer bounded
8- to 48-turn interventions and paired time-shifted counterfactuals over full
tape replacement or a new universal framework.

Large architectural changes are not an active optimization target. Make one
only when a discriminating experiment shows that the current architecture
cannot express, observe, safely rejoin from, or measure a strategy intervention
that already has evidence of value. Architecture may otherwise supply only the
minimum state tracking, legality projection, timing guard, and incumbent rejoin
support required by the strategy experiment. Do not treat model complexity,
graph structure, or a shared abstraction as progress without a separately
measured strategy gain on both incumbents.

The leading concrete lane is a dual-incumbent temporal residual over an 8- to
48-turn horizon, informed by the high-output 8-cow/4-sheep topology but not by
full route cloning. It should let feed, water, harvest, shipping, shed capacity,
sale timing, deliberate asset abandonment, and time-shifted market preemption
compete through explicit opportunity cost. Its first discriminating target is
the public-market externality exposed by the 2026-08-13 high-score refresh:
retain locally valuable production motifs while suppressing sales or production
timing that creates more value for the opponent. The decision must use public
state rather than opponent identity.

Asset survival has no special status in that comparison: losing an animal or
crop can be the rational choice when its remaining value is below the work,
timing, capacity, or capital it consumes. A graph model is one ablation, not the
assumed solution: compare it with a flat model and a simple greedy/value rule.
A shared residual must condition on incumbent identity and state, rejoin the
relevant incumbent legally, and earn its value separately on both strategy
families.

Prefer a complete, tested, standalone, submission-ready change over a plan or
an abstract framework. Continue through implementation, official-engine games,
performance checks, and artifact verification unless a decision cannot be
recovered from this workspace or an authoritative source.

Do not submit to Kaggle, create or change a remote repository, push commits, or
otherwise change external state unless the user explicitly asks in the current
chat.

## Authority and Required Reading

Before changing either main approach or engine-facing experiment behavior,
read in this order:

1. This file.
2. `research/main_approach/README.md`.
3. The selected approach's `development/README.md` and relevant split modules.
4. `data/kaggriculture/AGENTS.md` and `data/kaggriculture/README.md`.
5. The exact official engine Python and configuration JSON used by the run.
6. For topology-search or E2 work, the Async V3 README, E1c decision, E2
   README, candidate registry, implementation plan, acceptance contract, and
   runbook in their declared order.
7. The decision record for the mechanism being extended or challenged.

Read `strategy.md` and the relevant `submission/` modules only when changing or
using the legacy production control. Read archived reports narrowly for the
question at hand; they are evidence, not active implementation instructions.

When sources disagree, the exact engine used by the experiment is authoritative:

- Official source: <https://github.com/Kaggle/kaggle-environments/tree/master/kaggle_environments/envs/kaggriculture>
- Local pinned checkout `.vendor/kaggle-environments` resolves to
  `a4dce5ae6e2ffe3c1afea8ec4b24b562df74cc07` and is older than the latest
  retained current-engine audit.
- The 2026-08-11 graph-relay audit used Python blob
  `4b78842d0f2d4abf6e318a8248b6306454f5c714` and configuration blob
  `0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8`, associated with audited engine
  commit `bded87b0d7879078c726a93a4884d044f79c4eed`.

Re-fingerprint both Python and configuration before every new official-engine
experiment. Never call a result current-engine-matched merely because its
Python code matches while its JSON configuration differs. Do not edit
`.vendor/`, `data/`, or `docs/` during normal strategy development.

## Active Source and Artifact Contract

For each active incumbent, `development/` is the editable source of truth. The
sibling `main.py` is a deterministic, compressed, generated Kaggle artifact.

### v27 current meta

- `route_actions.json`: independently owned readable 719-turn route.
- `constants.py`, `runtime.py`: constants and episode/runtime state.
- `weed_repair.py`, `market.py`: runtime overlays.
- `agent.py`: development composition and entrypoint.
- `development_main.py`: local uncompressed entrypoint.
- `development/build_standalone.py`: deterministic single-file builder.
- `main.py`: generated artifact; never edit it by hand.

### Boatlee V16-RC2 market relay

- `route_actions.json`: independently owned readable 719-turn route.
- `constants.py`, `runtime.py`: constants and episode/runtime state.
- `weed_repair.py`, `market.py`: shared concerns within this approach only.
- `livestock.py`, `wool.py`: livestock conversion and wool control.
- `base_agent.py`, `relay.py`, `agent.py`: base route, relay residual, and
  development composition.
- `development_main.py`: local uncompressed entrypoint.
- `development/build_standalone.py`: deterministic single-file builder.
- `main.py`: generated artifact; never edit it by hand.

Do not deduplicate route JSON, constants, or Python modules across the two
approaches. Similarity is provenance, not permission to couple their editable
sources. If a reusable offline harness is needed, keep it outside both runtime
trees and ensure neither generated artifact imports it.

Every generated `main.py` must:

- expose `agent(obs)` from archive root;
- be self-contained and standard-library-only;
- have no runtime filesystem, network, subprocess, or local checkout
  assumptions;
- preserve seat-isolated episode state and reset on step zero or rewind;
- remain below the competition package and runtime limits.

`v27_current_meta_safety_guarded/main.py` remains authoritative for that
reference variant until a separately validated decompression is performed.

## Main-Approach Development Workflow

### 1. Establish the control

Before editing:

1. Run `git status -sb` and preserve unrelated or user-owned changes.
2. Name the incumbent being changed. For a dual-incumbent mechanism, name both.
3. Fingerprint engine Python and configuration JSON.
4. Freeze or checksum each pre-change generated `main.py` used as a control.
5. Predeclare the mechanism, smallest discriminating game block, fresh
   holdouts, stopping rule, and falsifying result.
6. Decide whether the work is behavior-preserving or intentionally behavioral;
   the validation protocol is different.

Use `apply_patch` for source edits. Keep the final action projection or
equivalent legality boundary immediately before returning the action.

### 2. Edit decompressed source only

Make runtime and route changes under the selected approach's `development/`
tree. Never prototype by editing generated `main.py`. Do not change both
incumbents in one lane unless the experiment explicitly tests a shared
dual-incumbent residual; even then, retain separate parameterization and
per-incumbent results.

For a temporal or time-difference intervention, record:

- the public trigger and decision step;
- the intended action shift and maximum horizon;
- the resource, maintenance, capacity, or market opportunity displaced;
- the exact condition that returns control to the incumbent;
- the unshifted paired counterfactual.

### 3. Rebuild generated artifacts

From workspace root:

```powershell
python research\main_approach\v27_current_meta\development\build_standalone.py
python research\main_approach\v27_current_meta\development\build_standalone.py --check
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
python -m unittest research.main_approach.test_development_sources -v
```

Run only the relevant builder when one approach changed, but always run the
shared source contract. A stale generated artifact is a failed check, not a
minor packaging issue.

### 4. Validate according to change type

For a behavior-preserving split, builder, or refactor change, run:

```powershell
python research\main_approach\validate_development.py
```

It must establish exact current-engine equivalence among the frozen pre-change
standalone control, regenerated `main.py`, and `development_main.py`, from both
seats. Compare rewards, all 719 returned actions or their full digest,
  termination, action-schema findings, economic-event diagnostics, and opponent
  behavior.

For an intentional strategy change, equality to the old control is neither
expected nor sufficient. Use the frozen pre-change artifact as the matched
control, evaluate the candidate from both seats on identical seed/opponent
blocks, and keep every loss, invalid run, and adverse event. Confirm separately
that the regenerated `main.py` and `development_main.py` are exactly equivalent
to each other.

### 5. Evaluate against both incumbents

A single-incumbent change must be judged relative to its own incumbent. A
shared overlay, selector, job model, or temporal residual must report two
separate strata:

- candidate-on-v27 versus unmodified v27;
- candidate-on-Boatlee versus unmodified Boatlee.

Do not pool raw terminal rewards across these strata. Report paired win/draw/
loss first, then paired terminal-margin delta, own-bank delta, downside, and
mechanism-specific diagnostics. Include the other incumbent as an opponent
when it is useful, but do not confuse opponent choice with the control being
ablated.

Use both seats and fresh, previously unused holdout seeds before expanding a
lane. Opponent blocks should be family-stratified and chosen for interaction,
not merely public rating. The retained Kaito v21, Saiteja Mega Ensemble, Roman,
guarded-v27, and the other active incumbent are available references; add an
opponent only when it exercises a distinct maintenance, capacity, livestock,
fertilizer, or market-timing interaction.

### 6. Record and hand off

Retain exact engine/config hashes, controls, source hashes, seeds, seats,
opponents, per-game results, action digests, latency, and economic events. A
summary report is not passing unless its current machine-readable
artifact supports it. Do not overwrite or discard unfavorable runs.

## Experiment and Promotion Gates

Use the cheapest experiment that can falsify the mechanism. One favorable seed,
raw score, margin, or head-to-head win is not promotion evidence.

A candidate may expand only after:

- both players finish `DONE` in every retained game;
- there are zero exceptions, timeouts, malformed action structures, and
  overage exhaustion;
- same seed, seats, strategies, engine, and configuration reproduce identical
  rewards and action digests;
- market action lists never exceed ten entries;
- latency is measured across a full episode, with p95 below 150 ms and maximum
  below 750 ms on the development machine;
- fresh paired holdouts show a positive win signal in the relevant incumbent
  stratum, with no unexplained strategy-wide collapse;
- a dual-incumbent candidate has non-negative credible evidence on each
  incumbent separately rather than relying on a pooled gain.

Animal escapes, crop deaths, fresh-crop deaths, shed overflow, seed
overcommit, deliberate abandonment, and terminal inventory are economic
outcomes, never independent promotion gates. They may increase, even sharply,
when paired win and value evidence shows that the released labor, timing,
capacity, or capital is worth more. Record and attribute them so intentional
abandonment can be distinguished from an uncontrolled cascade. Reject them only
when the total economic outcome or downside is unreasonable, not because an
asset failed to survive.

Before packaging any approach for submission, also verify that the archive:

- is under 5 MiB;
- contains `main.py` at archive root;
- excludes development modules, tests, reports, replay data, caches, virtual
  environments, and local paths;
- imports after extraction into an isolated directory;
- completes at least one official-engine game from the extracted copy.

Packaging or promotion does not authorize a Kaggle submission.

## Engine Invariants

Preserve and test these rules in every engine-facing change:

- An episode has 720 recorded states. Meaningful agent actions are steps 0-718;
  both players become `DONE` after processing step 718.
- Unit actions run before market actions. A product already carried may be
  `DROP`ped and then `SELL`ed in the same turn.
- Same-turn purchases cannot fund or supply unit actions already processed.
  Earlier `SELL` orders may fund later market orders.
- `SELL` consumes shed inventory only. `HARVEST` writes to unit inventory.
- A fresh plant starts with `consecutive_unwatered = 1` and must be watered on
  planting day or it becomes a weed at refresh.
- Two consecutive missed daily needs destroy the asset: plants become weeds
  and animals escape permanently.
- PLANT demand is atomic per crop. If requests exceed available seeds, every
  PLANT request for that crop is cancelled. Use a same-turn shadow seed ledger
  whenever an overlay can add or redirect planting.
- LOCKED tiles are traversable. In the audited current engine, center-shed
  `PICKUP`, `DROP`, and shed-directed `PLACE` occur before the locked-tile guard;
  field mutations remain blocked. A hand spawned at `(5,4)` while NE is locked
  must be able to leave.
- The shed holds 100 non-seed items. DROP overflow is discarded before market
  processing and cannot be recovered by selling later that turn.
- Market queues are ordered and capped at ten entries. Extra orders are
  silently discarded.
- Market price is recomputed per unit. Splitting an order in the same turn does
  not improve price.
- Price-floor sales do not add market inventory. BUY_PRODUCT quotes use
  post-buy inventory.
- At audited commit `bded87b0d7879078c726a93a4884d044f79c4eed`, town-center
  demand uses a flat 24-turn interval and shop instances are sampled with
  replacement, permitting duplicate types up to the eight-shop cap.
- State resets when step returns to zero or moves backward and remains isolated
  by player seat.
- Runtime opponent modeling may use only public money, farms, tiles, crops,
  animals, workers, land, town, shops, market data, and public actions. Never
  infer from account, team, or hidden private inventory.

## Job Value and Opportunity Cost

For the current temporal-residual direction, compare work by marginal value over
the active horizon rather than inherited urgency labels. The model or rule must
put all of these on the same opportunity-cost surface:

- preventing an imminent crop death or animal escape;
- accepting that death or escape and reallocating the worker;
- relieving capacity or decay pressure;
- harvesting, shipping, or exploiting a fertilized production window;
- moving a sale to preempt public demand or delaying it for a better bundle;
- ordinary feed, water, care, pickup, and staging;
- planting, building, digging, expansion, hiring, and investment.

None receives a categorical priority merely because it preserves an asset. The
point of a job-level residual is to expose the competition between remaining
asset value, travel, labor, timing, capacity, capital, and opponent interaction.
Preserve the incumbent action when the residual lacks support, and bound every
override in time and scope so a local trade does not accidentally become a
strategy-wide collapse.

For a planned PLANT or BUILD target that becomes a weed, DIG, revalidate on the
next turn, retry locally for a bounded number of turns, and cancel when terminal
or economic feasibility is gone. Any retry must still obey planting-day water
requirements and cutoffs.

## Runtime Constraints

The official action timeout is one second. Keep normal turns far below 150 ms
and measure with `time.perf_counter()`.

Runtime code and generated artifacts must not use networking, subprocesses,
multiprocessing, pandas, sklearn, heavy models, file writes, or verbose logging.
Offline experiment scripts may use files and subprocesses. Keep learned models
small, deterministic, embedded, and cheap enough that model inference is not a
meaningful share of the action budget.

Use bounded technical degradation for any new residual:

- if observations or features are missing, return to the incumbent;
- if the time budget is threatened, skip the residual and preserve legal
  incumbent behavior;
- if an override becomes illegal or its preconditions change, rejoin rather
  than improvising an unvalidated action chain.

This fallback rule protects runtime validity, not biological assets. A valid
residual may intentionally skip maintenance or abandon an asset when that is
the higher-value action.

## Retained Decision Memory

The details belong in their reports; the following constraints remain active:

- `research/risk_aware_graph_relay_2026-08-11/decision.md`: do not promote the
  GCN or flat MLP. Across 80 held-out games, a static always-force fertilizer
  residual beat both learned selectors but improved mean paired margin by only
  6.5 coins and changed no win/loss. The intervention surface lacked negative
  labels. Reuse this as falsifying evidence, not as a model candidate.
- `reports/highscore_route_refresh_2026-08-13/decision.md`: direct full-route
  transplant is stopped. The new shared 8-cow/4-sheep topology raised own-bank
  output and beat the other incumbent on the smallest matched screen, but all
  seven observed market tapes lost both seats to Kaito v21 and created fresh
  state-compatibility failures. Retain the production topology only as source
  material for bounded motifs and public-state market-exposure suppression.
- `research/dual_incumbent_topology_search_2026-08-14/async_v3/e1c_decision.md`:
  stop E1 expansion. Carry the one-block Boatlee candidate into E2 unchanged;
  treat the v27 high-upside topology only as a public-selector branch. Exclude
  the retained v27 economic no-op from all efficacy frontiers. E1c reused
  consumed seeds and is hypothesis/selection evidence, not a fresh promotion
  screen.
- `reports/hypothesis_cycle_2026-08-10.md`: scale-only, opening-only, one-day
  commitment, modal-route imitation, and fixed-tape continuation were not
  sufficient. Do not restart them without a distinct mechanism and protocol.
- `reports/experiments/README.md`: the old route-memory, one-day search, linear
  learned, and one-factor programs failed efficacy gates. Their reported paths
  may be provenance to deleted material.
- `reports/replay_clone_study/`: the Top-50 snapshot showed concentrated visible
  routes but distinct complete action and market tapes. Historical clone
  matrices also used a mixed engine/configuration; read the caveat before
  drawing current-engine conclusions.
- The restored `submission/` control passed its historical reliability gates
  but went 4-76 in the retained public-agent league and 0/64 against the four
  strongest extracted public routes. Reliability is not frontier efficacy.
- `research/full_tape_topology_scaleup_2026-08-10/` and its cache remain active
  files but are not the present priority. Do not resume that lane merely because
  its artifacts remain on disk.

## Evidence, Archive, and Navigation

Use the narrowest source that answers the question:

| Need | Start here |
| --- | --- |
| Two active incumbents and development contract | `research/main_approach/README.md` |
| v27 editable architecture | `research/main_approach/v27_current_meta/development/README.md` |
| Boatlee editable architecture | `research/main_approach/boatlee_v16_rc2_market_relay/development/README.md` |
| Decompression equivalence evidence | `research/main_approach/development_validation.json` |
| Failed graph-relay decision and next abstraction | `research/risk_aware_graph_relay_2026-08-11/decision.md` |
| Competition rules and packaged data | `data/kaggriculture/AGENTS.md`, `data/kaggriculture/README.md` |
| Legacy production intent | `strategy.md` |
| Legacy production validation | `reports/round2_restoration_2026-08-08.md` |
| Historical experiment decisions | `reports/experiments/README.md`, `reports/hypothesis_cycle_2026-08-10.md` |
| Top-50 replay metadata | `data/public_replays/top50-2026-08-09/README.md` |
| Downloaded public opponents | `research/public_agents/README.md` |
| Archived artifact map | `ARCHIVE.md` |
| Async V3 implementation and E1c outcome | `research/dual_incumbent_topology_search_2026-08-14/async_v3/README.md`, `research/dual_incumbent_topology_search_2026-08-14/async_v3/e1c_decision.md` |
| E2 authority, candidates, and formal boundary | `research/dual_incumbent_topology_search_2026-08-14/e2/README.md`, `research/dual_incumbent_topology_search_2026-08-14/e2/candidate_registry.json`, `research/dual_incumbent_topology_search_2026-08-14/e2/runbook.md` |

The external archive is at
`C:\Users\wurre\Desktop\Kaggriculture-archive\2026-08-10`. Read `ARCHIVE.md`
before reproducing an archived lane. Paths in historical reports may be
provenance rather than live navigation.

The fixed Top-50 replay snapshot contains one selected replay for each rank
1-50. Only ranks 1-28 were rated at least 3000; replay rewards are not
leaderboard ratings. Combining both players' replay observations reveals
private information unavailable at runtime. Use private fields only to audit
that same player; all cross-player and runtime comparisons must remain public.

The initial decompression of both active incumbents was verified on 2026-08-11
against audited current-engine commit
`bded87b0d7879078c726a93a4884d044f79c4eed`: 12 full games covering both
approaches, original/generated/development representations, and both seats
ended `DONE`/`DONE` with exact rewards and 719-call action digests. The source
contracts passed 3/3 and the legacy production suite passed 18/18. See
`research/main_approach/development_validation.json`.

## Default Working Principle

Treat strategy micro-tuning and route-topology exploration as the primary goal.
Start from the smallest matched residual on each incumbent that can reveal a
real temporal tradeoff. Preserve incumbent behavior outside the declared
window, require negative as well as positive counterfactual labels before
training a selector, and expand only after fresh paired evidence supports the
mechanism separately for v27 and Boatlee. Do not start a broad architecture
lane unless a strategy experiment first demonstrates a concrete architectural
limitation.
