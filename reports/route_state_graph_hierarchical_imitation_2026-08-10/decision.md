# Route-state graph / hierarchical imitation: minimal decision

Date: 2026-08-10  
Decision: **REJECT_DO_NOT_SCALE_TO_1500**.  Production `submission/` and
`dist/` were not edited.

## Predeclared mechanism

The hypothesis was not a state-to-next-action classifier, route-memory restart,
linear clone, or a fixed tape.  It was that a compact graph could identify a
supported route node, require public-state compatibility plus a 24–72-turn
maintenance feasibility bound, and then execute a deterministic multi-actor
maintenance option without losing inherited dense assets.  Only after that
safety gate passed would a fresh, paired efficacy test be allowed.

The implementation is isolated in
`research/route_state_graph_hierarchical_imitation_2026-08-10/`:

1. `src/route_graph.py` extracts macro family, day node, and 24-turn option
   digest.  A node contains land, worker count, crop/animal counts and yields,
   weed count, and structure count.  The option is an aggregate operation
   chunk, never an action tape.
2. `src/controller.py` selects a node only when its same-day public distance
   and a three-day own-feed/labor bound pass.  Its executor contains only P0/P1
   maintenance and capacity-safe logistics; it does not PLANT, BUY_LAND, or
   follow a replay action sequence.
3. `extract_v25.py` safely recovers the public v25 notebook artifact used
   only to construct inherited live states.  It found no dangerous imports or
   calls.  The recovered logical LF source SHA-256 is
   `2a66e22940e96c867622b89a1251b49edf1b819b26970f6b0ee21f2b13b00473`.

## Engine and configuration fingerprint

- Upstream `git ls-remote` resolved `master` to
  `bded87b0d7879078c726a93a4884d044f79c4eed`.
- Direct upstream UTF-8 normalized source hashes: Python
  `FB9215C5E21A25243E2D13E75B3D70A79CF7D78FFF150A90F1BB5EACF9BA2BCF`, JSON
  `7F196F4AAF9B4E482FBD61BA4BF19F5CEC4DA0F81938ECE756954035A65C0BB5`.
- The local pinned JSON remains a 12-turn default and was **not** used as the
  experiment configuration.  The harness applied the audited current patch
  through `scripts.replay_engine_versions.patch_registered_engine_current` and
  explicitly supplied `townCenterSellInterval=24`.
- A direct transition check observed configuration 24, a hand spawning at the
  locked NE shed tile `(5,4)`, and successful `PICKUP WHEAT` from that locked
  tile (inventory changed 0→1; shed 1→0).  Thus the actual test has the current
  locked-shed semantics rather than the old pinned behavior.
- The machine-readable result is `engine_fingerprint.json` in this report
  directory.

## Dataset, graph, and leakage controls

The graph used only the existing fixed Top-50 snapshot.  It rebuilt six macro
families: `F01` has 45/50 target-team episodes; the other five families each
have one.  It produced 180 day nodes and 322 24-turn options.

Private observation is used only for the same target player's feed/shed/seed
feasibility audit.  Cross-player clustering, family labels, and runtime
opponent handling use only public farm, market, town, and action information.
The stored split protocol forbids random transition splitting and declares
team holdout ranks divisible by five, singleton-family holdouts, and days
20–29 temporal holdout.  Those splits are descriptive support checks, not
efficacy evidence.

The selected replay for each team is its best available episode.  Therefore
the data cannot estimate family expected reward or win rate.  It also spans
engine versions 1.32.4–1.32.6, and a public notebook artifact is not proof that
it created a particular Top-50 replay or team submission.

## Maintenance gate

The first run is retained at `maintenance_gate_attempt1_invalid.json`.  It
exposed two prototype defects: an over-conservative one-worker-per-five-assets
bound and a `DROP→PICKUP` loop that discarded staged wheat before FEED.  It is
invalid implementation evidence, not a mechanism result.

After correcting only those defects, the predeclared current-engine block at
steps 240, 360, and 480 (days 10, 15, 20), horizons 72, 72, and 48, and both
seats passed:

- 6/6 accepted route nodes; zero escapes, fresh-crop deaths, shed-overflow
  states, malformed actions, timeouts, seed overcommit, and market-order cap
  violations.
- Same-seed 24-turn repeat was deterministic.
- 432 controller calls: p50 0.1281 ms, p95 0.4991 ms, p99 0.7177 ms,
  maximum 0.9159 ms.

The full-season diagnostic at fresh seed `202608105`, v25 prefix through step
239 then graph maintenance against a live v25 opponent, also completed
`DONE/DONE` with zero recorded survival violations.  Its bank was only 3,075
against 122,857: safety feasibility did not imply economic continuation.

## Fresh paired efficacy gate

Because the short maintenance gate passed, the required fresh paired test ran.
The fresh-seed check found no prior occurrence of `916731` or `916733` outside
this experiment under `research/`, `reports/`, and `scripts/`.

For each of Kaito v21, Saiteja 3000, and Roman LB950, two seeds and both seats
were tested (12 paired blocks).  Each block compared the same live executable
opponent and same v25 prefix: baseline continues v25, candidate switches to
the graph controller at step 240.  No frozen replay was an opponent.  The
promotion criterion was zero candidate safety failures, at least 8/12 positive
paired terminal-margin deltas, and a positive mean delta in every opponent
family.

| Executable family | Positive / 4 | Mean paired-margin delta |
| --- | ---: | ---: |
| Kaito v21 | 0 | -138,522.50 |
| Saiteja 3000 | 0 | -172,088.50 |
| Roman LB950 | 0 | -153,171.75 |

All 12 deltas were negative.  Candidate safety also failed under live public
competition: 18 animal escapes total (6 in one Saiteja seat and 12 in one
Roman seat), despite zero malformed actions, timeouts, seed overcommit, and
shed-overflow states.  Candidate-controller latency remained safe over 5,748
calls: p50 0.1181 ms, p95 0.2662 ms, p99 0.4608 ms, max 1.0209 ms.  A complete
duplicate Kaito game reproduced action digest and both rewards.

Hence this mechanism fails both the fresh efficacy gate and the full-context
safety gate.  It must not be promoted, packaged, or expanded to 1,500 replays.

## Smallest viable architecture and remaining risks

The smallest technically viable architecture is a **route-node compatibility
gate + deterministic 24-turn P0/P1 maintenance option**.  It is enough to
preserve dense inherited states for bounded horizons at negligible latency, but
it lacks a productive continuation option: asset replacement, harvest/shipping
cadence, capital, topology repair, and market control.  Its full-season bank
collapse and fresh losses show that maintenance feasibility is necessary but
far from sufficient.

The main identification risks remaining are selected-best-episode bias, the
45/50 family concentration, sparse singleton family holdouts, replay engine
version drift, and notebook/team identity ambiguity.  The unanimous fresh
paired loss is nevertheless decisive for this prototype; downloading 1,500
more replays would not reduce the mechanism uncertainty that caused rejection.

## Correction addendum: scope of this decision (2026-08-10)

The preceding `REJECT_DO_NOT_SCALE_TO_1500` label is **not** a rejection of
complete exact notebook backbones, full-tape/family topology learning, or a
route branch/rejoin that retains a complete tape. It is corrected to mean
only: **reject the route-node gate plus maintenance-only executor tested in
this report**. The 0/12 block changed the v25 policy at step 240 into a
controller that deliberately did not PLANT, BUY_LAND, or continue its complete
logistics/market route. It can establish that bounded maintenance feasibility
does not make a productive continuation; it cannot test or falsify the value
of the original v25 719-action backbone.

The full correction lane is isolated at
`research/exact_backbone_correction_2026-08-10/`, with its decision record at
`reports/exact_backbone_correction_2026-08-10/decision.md`. It statically
recovers all four high-score notebook `main.py` artifacts, evaluates them as
complete policies on the current engine, and tests only exact-v25-preserving
narrow residuals. That lane, not this maintenance-only result, governs any
future decision about a 1,500-replay expansion of complete-tape topology.
