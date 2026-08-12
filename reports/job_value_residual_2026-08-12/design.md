# Dual-incumbent 24–48-turn job-value residual design

Date: 2026-08-12
Status: approved design; implementation has not started
Active incumbents: `v27_current_meta`, `boatlee_v16_rc2_market_relay`

## Objective

Build the smallest bounded residual that can improve actual matched game
outcomes on either active incumbent by comparing local jobs through explicit
24- and 48-turn opportunity cost. The residual may alter one worker for four to
eight turns and, when directly coupled to that worker's logistics chain, one
SELL order. It must rejoin the relevant incumbent without taking control of the
rest of the route.

The first efficacy gate is an improvement in paired game outcomes, not merely
more bank or a better terminal margin. Results remain separately attributable
to v27 and Boatlee. A gain on one incumbent cannot hide a regression on the
other.

## Established evidence and rejected starting point

### Runtime acceleration is not the observed regression mechanism

The 2026-08-11 runtime optimization was intentionally behavior-preserving. Its
frozen controls, regenerated artifacts, and development entrypoints produced
the same actions, rewards, opponent traces, and full-episode digests while
reducing runtime substantially. Both incumbents were already far below the
one-second action timeout before optimization.

The supplied `data/replay/v27.json` and `data/replay/boatlee.json` each contain
720 states, end `DONE/DONE`, and keep both seats' `remainingOverageTime` at 60
for the full episode. No timeout or overage consumption can explain their
results. Acceleration therefore changed speed, not strategy behavior, in the
verified runs.

Leaderboard score compression and visible-route homogeneity are separately
supported by the retained leaderboard snapshots and replay-clone study. They
are compatible with the rating decline, but the available evidence does not
identify either as a sole causal explanation.

### Market-first residual is rejected

The proposed Market Residual V2 would repeat retained experiments:

- The counterfactual market residual already tested no preemption, fixed H6
  preemption, and C68 adaptive horizon inference with exact SELL debt
  conservation and unchanged unit actions.
- C68 infers opponent supply from market-inventory changes, subtracts own sales
  and deterministic town drain, conditions on public farm similarity, and
  shifts a future scheduled premium SELL. It did not establish a matched game
  outcome improvement.
- Same-turn split orders cannot improve own price under the authoritative
  engine. They matter only through order interleaving or finance dependencies.
- In the two supplied replays, both incumbents and both seats make 316 premium
  SELL orders totaling 3,092 units. For WOOL, MILK, MELON, and STRAWBERRY, the
  shed has zero sellable units one, two, and three turns before every one of
  those orders. The route normally sells premium output as soon as it first
  becomes sellable.
- The replays show no shed overflow and finish with an empty shed; terminal
  liquidation and standalone capacity selling have no discriminating surface
  in those games.

FERTILIZER and WHEAT sometimes exist in the shed before their scheduled sales,
but their sale timing is coupled to purchases and capital sequencing. Retained
market ranking and relay experiments produced small margin changes without the
required game-outcome signal.

Market timing remains eligible only as part of a coupled
HARVEST/transport/DROP/SELL job. Moving an existing SELL alone is outside the
new lane.

### Other lanes not to repeat

- Short sticky-zone and one-day commitment work did not reliably convert
  travel or reversal reductions into efficacy.
- The former one-day global ranker had material transition error and no
  competitive win signal.
- The fertilizer graph-relay dataset lacked negative examples. Neither the GCN
  nor the flat model earned promotion, and the static always-force rule changed
  no match outcomes.

Consequently, travel reduction is a cost feature rather than an objective; the
new residual uses full-game paired counterfactual labels and requires positive
and negative examples before considering a learned selector.

## Scope and non-goals

The first implementation may:

- modify one farmer or hand for four to eight turns;
- swap the order of two jobs performed by that actor;
- replace PASS, reversal, or low-value work with a productive detour and rejoin;
- skip maintenance and deliberately accept crop death or animal escape;
- treat HARVEST, transport, DROP, and one coupled SELL as one intervention;
- relieve shed capacity or liquidate terminal value when the local chain makes
  the product newly sellable.

It may not:

- optimize the full season or replace the fixed route;
- coordinate two workers in the first version;
- identify an opponent account, team, or hidden inventory;
- preempt solely from a fixed SELL horizon or clone identity;
- optimize same-turn order splitting as though it changed the price curve;
- modify HIRE, BUY_LAND, BUILD, or seed-dependent windows in the first version;
- automatically escalate from a failed greedy rule to a flat or graph model.

## Candidate-window generation

Candidates are anchored to events on an incumbent's actual control trajectory,
not produced by an unrestricted action search. Eligible anchors are:

- an imminent feed, water, crop-death, or animal-escape deadline;
- harvestable output or a fertilized production window;
- carried cargo approaching a DROP opportunity;
- projected shed occupancy of at least 85 with additional inbound cargo;
- a SELL collision only when changing the product's first sellable time requires
  a coupled harvest or logistics intervention;
- the last 48 meaningful turns of the episode;
- a reversal or detour adjacent to a feasible higher-value job.

Each candidate records:

- incumbent identity, trigger step, actor index, and event family;
- four to eight candidate actions and the displaced incumbent actions;
- touched tiles, products, money, shed quantity, and maintenance state;
- the public trigger and the intended time shift;
- the exact expected rejoin step and fingerprint;
- an unshifted paired counterfactual.

At most three different job-family candidates are retained in a discovery
context. Candidate generation must not manufacture three parameter variants of
the same mechanism and count them as distinct families.

## Rejoin and bounded-control contract

At the declared rejoin step:

- the actor is at the position expected by the incumbent;
- the hand count and actor indexing match the route;
- there is no outstanding SELL quantity debt;
- the next incumbent action passes the final legality projection;
- the residual relinquishes control even when resources differ because a crop
  was harvested or an asset was deliberately abandoned.

A candidate is discarded if it cannot rejoin legally within eight turns. The
residual must not extend its window to repair an intervention. If an observation
is missing, a precondition changes, the actor count differs, a dependency
escapes the touched set, or runtime budget is threatened, the current turn
returns the complete incumbent action.

## Counterfactual labels

Every discovery candidate is evaluated by two complete games using identical
engine, configuration, seed, seat, and opponent:

- control: the frozen incumbent;
- intervention: the same incumbent with exactly one forced candidate window.

The authoritative label is lexicographic:

1. `L→D/W` and `D→W` are positive; reverse transitions are negative.
2. When the game outcome is unchanged, paired terminal-margin delta determines
   positive or negative.
3. Exactly zero terminal-margin delta is neutral.

Own-bank delta, opponent-bank delta, downside, asset losses, overflow,
inventory, action digests, and economic events remain diagnostics rather than
replacing the label.

Snapshots at trigger+24 and trigger+48 record cash, liquidatable inventory,
carried cargo, shed headroom, maintenance debt, remaining production, worker
position, market changes, and the incumbent job displaced. These snapshots
explain the terminal label; they are not substituted for the full-game result.

Before a selector is built, each incumbent must independently provide at least
four positive and four negative examples spanning more than one job family.

## Local counterfactual ledger

The runtime rule compares the candidate and incumbent only over the touched
actor, tiles, products, shed quantities, market orders, and deliberately
affected asset. Untouched state cancels rather than being approximately
simulated.

For horizons `h ∈ {24, 48}`, or the remaining episode when shorter:

```text
delta_value_h =
    delta_cash_h
  + delta_liquidatable_h
  + delta_asset_h
  + delta_capacity_h
  + delta_market_h
```

- `delta_cash` contains certain revenue and input expenditure.
- `delta_liquidatable` values products that reach the shed or market within the
  horizon at a conservative post-impact price.
- `delta_asset` values realizable remaining output minus feed, water, care,
  harvest, and transport work. Asset survival receives no categorical bonus.
- `delta_capacity` values avoided discard, shed headroom, and any cargo delayed
  by the intervention.
- `delta_market` is nonzero only when the candidate changes first-sellable time
  and a legal public signal supports a different market position.

The five components are mutually exclusive at the horizon boundary. Output
already sold contributes to cash but not liquidatable inventory; harvested but
unsold output contributes to liquidatable inventory but not remaining asset
value; and `delta_asset` contains only output still embodied in a surviving
crop or animal. `delta_market` contains only the timing-dependent price
difference beyond the ordinary liquidation value. This prevents revenue,
inventory, and future production from being counted twice.

Movement has no arbitrary negative reward. Its cost is the incumbent work that
the occupied action slot can no longer complete.

The first version rejects a candidate if it:

- overlaps HIRE, BUY_LAND, BUILD, or an atomic seed dependency;
- changes money in a way that can alter an incumbent purchase or hire;
- overlaps active weed repair, Boatlee livestock/wool conversion, or RC2
  fertilizer relay;
- requires a second worker;
- cannot determine DROP, capacity, or market-order legality exactly.

This is a delta model, not a compressed full-farm or one-day engine substitute.

## Greedy runtime selector

The runtime enumerates only predeclared, incumbent-specific candidate templates
whose triggers match the current state. It does not search arbitrary routes.

For every eligible candidate:

1. compute `delta_value_24` and `delta_value_48`;
2. abstain if either value is unknown, their signs disagree, or either fails the
   incumbent-specific frozen threshold;
3. choose the candidate maximizing
   `min(delta_value_24, delta_value_48)`;
4. preserve the incumbent on an exact tie;
5. allow no overlapping residual until the active window has rejoined.

The rule and thresholds are frozen after discovery. v27 and Boatlee have
independent window tables, parameters, and results. Failure of the simple rule
ends the lane; it does not justify learning a more flexible model from the same
failed evidence.

## Feature surface

Own-state inputs may include step, day, hour, actor position, candidate and
incumbent path, rejoin distance, touched tile type and yield, water/feed/care
state, maintenance deadline, carried inventory, seeds, shed contents and
occupancy, money, market inventory and prices, expected own price impact,
first-sellable step, and remaining 24/48-turn workload.

Opponent-aware inputs use public information only:

- public yield decreases that conservatively indicate a harvest;
- public worker movement and distance to shed access;
- a lower bound on inferred inbound product, quantity, and earliest arrival;
- public farm composition and economic type;
- market-inventory changes after accounting for own orders and deterministic
  town drain.

The selector neither identifies a player nor assumes the opponent follows the
incumbent's future tape. Inferred opponent cargo is cleared when its public
transition becomes ambiguous, the day resets, or the bound can no longer be
maintained.

## Runtime integration and ownership

Shared offline experiment code may live under
`research/job_value_residual_2026-08-12/`, but neither runtime tree imports it.

Each incumbent independently owns:

- `development/job_value.py`: ledger, trigger, selector, and seat-isolated
  episode state;
- `development/job_windows.py`: route-specific candidate windows, thresholds,
  and rejoin fingerprints;
- its own builder output, tests, hashes, and result stratum.

The action pipeline is:

1. construct the normal incumbent action;
2. apply the existing weed, livestock, wool, market-relay, and other incumbent
   overlays;
3. abstain in the first version if one of those behavior-changing overlays is
   active;
4. otherwise apply an already-selected job window;
5. rerun SELL-slot ranking if the window changed market actions;
6. run the final legality projection immediately before returning.

State is isolated by seat and reset on step zero or rewind. The generated
artifact remains standard-library-only and performs no network, subprocess,
file-write, or verbose logging operation. The residual has a two-millisecond
soft budget and abstains when it is exceeded; official promotion limits remain
p95 below 150 ms and maximum below 750 ms over a full episode.

## Experiment protocol

### Pre-experiment freeze

Before editing runtime source:

- record `git status -sb` and preserve unrelated or user-owned changes;
- re-fingerprint both official engine Python and configuration JSON;
- freeze the SHA-256 of both incumbent `main.py` controls;
- record source, opponent, seed, seat, and generated-artifact hashes;
- reserve disjoint discovery, screen, and confirmation seeds that do not occur
  in retained evidence;
- predeclare candidate families and all stop rules.

The supplied `data/replay/` remains read-only and outside commits.

### Discovery block: at most 64 official games

The block contains two incumbents, two opponent families, two fresh seeds, and
both seats. The opponent families are the other active incumbent and a distinct
strong public strategy such as Kaito v21.

There are 16 incumbent/opponent/seed/seat contexts. Each context runs one shared
control plus at most three single-window forced candidates, for at most 16
control and 48 intervention games.

Discovery tests intervention surface, exact rejoin, positive/negative label
availability, and whether the ledger separates signs. It is not promotion
evidence.

Immediate discovery stops are:

- any invalid action, exception, timeout, market overflow, or nondeterminism;
- fewer than four positive or four negative labels for either incumbent;
- labels confined to one job family;
- most candidates unable to rejoin within eight turns;
- market candidates that merely move an already-sellable order.

### Frozen greedy screen: 64 official games

After freezing the rule, four new seeds produce:

```text
2 incumbents × 2 opponents × 4 seeds × 2 seats × control/candidate = 64 games
```

Each incumbent must independently show:

- at least one actual `L→D/W` or `D→W` transition;
- more outcome improvements than outcome regressions;
- more positive than negative paired terminal-margin deltas and a positive
  median;
- non-negative outcome-transition net for each opponent family;
- improvements spanning more than one seed and more than one seat.

Bank or margin gain without an actual outcome improvement stops the lane.

### Confirmation block: 128 official games

Only a passing screen unlocks eight new seeds:

```text
2 incumbents × 2 opponents × 8 seeds × 2 seats × control/candidate = 128 games
```

For each incumbent, outcome improvements must exceed regressions with at least
one improvement; both opponent-family nets must be non-negative; paired-margin
median and sign count must be positive; and the effect must not be isolated to
one seat. Every retained game must reproduce rewards and full action digests.

If only one incumbent passes, its result may remain a single-incumbent
candidate. The other incumbent remains unmodified, and the result is not
reported as a shared or dual-incumbent success.

## Correctness, artifact, and safety gates

Every retained game must end `DONE/DONE` with zero exception, timeout, malformed
action, stale state, actor-index drift, illegal rejoin, or market list above ten
orders. Same engine/configuration, strategy, seed, seat, and opponent must
reproduce rewards and full action digests.

For each changed incumbent:

- build its standalone artifact and pass builder `--check`;
- run the shared development-source contract;
- establish exact `development_main.py` versus generated `main.py` equivalence
  from both seats;
- measure full-episode latency;
- verify an archive-root `main.py`, isolated import, size under five MiB, and at
  least one extracted official-engine game before calling it submission-ready.

Animal escape, crop death, shed overflow, deliberate abandonment, and terminal
inventory are economic results rather than categorical failures. They must be
attributed to an intervention, including the labor, timing, capacity, or
capital released. An unexplained cascade is a stop condition.

## Machine-readable evidence

Every candidate record contains incumbent, opponent, seed, seat, trigger step,
actor, control/candidate actions, touched resources, displaced job, rejoin step,
ledger components at 24/48 turns, selector decision, abstention reason, terminal
label, outcome transition, reward and bank deltas, economic events, action
digest, termination status, latency, and exact engine/configuration hashes.

Summaries remain stratified by incumbent, job family, opponent family, and
seat. They include selector confusion matrices, coverage, abstention rate,
legal-rejoin rate, terminal-margin distribution, actual outcome transitions,
and every loss or adverse event. Unfavorable runs are retained and never
overwritten by later winners.

## Final stop and promotion rules

The lane stops rather than escalating when:

- correctness or deterministic reproduction fails;
- discovery lacks diverse positive and negative labels;
- the greedy ledger does not outperform always-intervene, maintenance-first,
  and always-incumbent baselines at sign separation;
- most useful candidates require more than one actor or a larger touched-state
  model;
- the frozen screen has no actual game-outcome improvement;
- confirmation produces a negative opponent-family or seat-specific net;
- the mechanism is explainable only by approximating the full farm.

A flat selector is a later, separately predeclared experiment only after the
greedy rule demonstrates a genuine outcome signal and the dataset contains
negative as well as positive labels. A graph model is an ablation after that,
not the assumed solution.

No design, implementation, packaging, or promotion step authorizes a Kaggle
submission or any other remote-state change.

## Planned deliverables

- this approved design;
- a separately frozen experiment protocol before strategy edits;
- shared offline counterfactual tooling under
  `research/job_value_residual_2026-08-12/`;
- independently owned v27 and Boatlee runtime modules, tests, generated
  artifacts, and evidence;
- immutable JSON/JSONL results, hash manifest, and final decision report;
- a verified standalone archive only for an incumbent that passes its own
  gates.
