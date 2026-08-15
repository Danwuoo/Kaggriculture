# High-score route refresh decision — 2026-08-13

## Decision

**Stop the direct route-transplant lane. Retain the shared 8-cow/4-sheep
backbone as evidence for a narrower public-state market-exposure mechanism.**

Neither `v27_current_meta` nor `boatlee_v16_rc2_market_relay` is changed. No
candidate passes the predeclared expansion gate, so this lane does not expand
to more seeds or opponents and produces no submission artifact.

## Live snapshot and new route families

The Kaggle leaderboard was captured at `2026-08-13T13:56:56Z`. The selected
cohort contains one public replay for each of the current ranks 1–40; the live
leader had reached 3240.2. Only four teams overlap the frozen 2026-08-09 Top-50
cohort, and none of the 40 correctly aligned unit tapes exactly matches a unit
tape in the archived Top-50 audit.

The current cohort contains 40 full tapes, 40 market tapes, 32 exact unit tapes,
and 14 macro route families. Its strongest repeated structure is an exact unit
tape shared by seven teams at ranks 3, 5, 7, 9, 13, 23, and 27. Those teams use
seven different market tapes. A broader macro profile appears in 32/40 selected
replays: eight cows, four sheep, roughly 35–36 strawberries, 12 melons, and land
unlocks near days 7 and 11.

Two distinct leading profiles are also new:

| Selected route | Peak assets | Land unlocks | Source terminal bank |
| --- | --- | --- | ---: |
| Rank 1 | 10 cows, 4 sheep, 35 wheat, 4 carrots, 34 strawberries, 20 melons | 7, 12 | 149,998 |
| Rank 2 | 9 cows, 3 sheep, 47 wheat, 42 strawberries, 18 melons | 7, 10 | 145,008 |
| Shared rank-3-family tape | 8 cows, 4 sheep, 56 wheat, 36 strawberries, 12 melons | 7, 11 | 150,896 |

The selected replay reward is descriptive, not a rating estimate or promotion
claim.

## Evidence correctness

The retained streaming collector had an action-alignment defect: it previously
used replay rows 0–718, even though row 0 is the initial placeholder and the 719
meaningful agent calls are rows 1–719. The collector now enforces rows 1–719,
has schema version 2, and has a regression test. The first unaligned refresh
cache and results are retained with `_unaligned` names and excluded from all
efficacy conclusions.

The current engine was re-fingerprinted before the experiments:

- Python blob: `4b78842d0f2d4abf6e318a8248b6306454f5c714`
- Configuration blob: `0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8`
- Audited engine commit: `bded87b0d7879078c726a93a4884d044f79c4eed`

Ranks 1 and 3 were then replayed through every official-engine transition.
Both passed all 719/719 transition checks. Raw successful replay JSON was
deleted after audit. Private observations were used only to validate that same
player's transition and were neither retained nor used across players. The
rank-3 source tape contains three atomic seed-overcommit turns; fresh guarded
experiments cancel every same-crop `PLANT` request in such a turn, matching the
engine's atomic cancellation semantics.

## Matched transplant screen

The smallest screen used fresh seed `83171301`, both seats, the other active
incumbent and Kaito v21 as opponent families, and separate control strata for
the two incumbents.

| Candidate | Incumbent stratum | Paired W/D/L | Mean margin delta | Mean own-bank delta | Technical |
| --- | --- | ---: | ---: | ---: | --- |
| Rank-1 10c4s full tape | v27 | 2/0/2 | -2,742.25 | +22,742.50 | pass |
| Rank-1 10c4s full tape | Boatlee | 2/0/2 | -2,982.25 | +22,622.50 | pass |
| Shared 8c4s full tape | v27 | 2/0/2 | +4,765.50 | +44,418.50 | fail: source seed overcommit |
| Shared 8c4s full tape | Boatlee | 2/0/2 | +4,525.50 | +44,298.50 | fail: source seed overcommit |

The high own-bank deltas make the new production route economically
interesting, but the 2/0/2 split is opponent-dependent rather than robust.

## Exact shared-backbone market ablation

Seven guarded candidates held the exact shared 8c4s unit tape and weed/seed
guards fixed, varying only the seven observed public market tapes. This is 56
candidate games: seven tapes, two incumbent strata, two opponent families, and
both seats.

All 56 games finished `DONE`/`DONE` with zero exceptions, timeouts, malformed
actions, overage exhaustion, or market lists above ten. Worst observed p95
latency was about 0.17 ms and maximum latency was 2.39 ms. There were no animal
escapes. Each fresh game had three fresh-crop deaths, an additional
state-compatibility warning absent from the selected source replay; one market
variant also produced six shed-overflow units across the screen.

Every market tape has the same interaction sign:

- Against the other incumbent: both seats positive, with mean paired-margin
  delta between +20,254 and +22,053 depending on tape and incumbent stratum.
- Against Kaito v21: both seats negative, with mean paired-margin delta between
  -9,521.5 and -10,762.
- Across the four contexts: 2/0/2 for every tape. The best overall tape (rank
  7) is +6,007.25 in the v27 stratum and +5,767.25 in the Boatlee stratum, but
  still averages -10,038.5 against Kaito.

Thus market-tape selection alone does not repair the failure. The shared route
raises its own bank by roughly 38k–41k, but exposes enough public market value
that Kaito gains more. No tape passes the gate requiring positive paired margin
in both seats against both opponent families, separately for each incumbent.

## What to retain

The reusable signal is not “clone the new leaderboard route.” It is:

1. The high-output 8c4s unit backbone is a real new production regime.
2. Its value is conditional on public market exposure and opponent response.
3. The next discriminating experiment should isolate a bounded,
   public-state-compatible early production motif plus a market-exposure
   suppressor, with an explicit return to each incumbent.
4. That mechanism must not branch on opponent identity. It should use public
   demand, price, inventory, timing, and capacity state, and must earn value
   separately on v27 and Boatlee.
5. The fresh-crop deaths and seed feasibility difference show that a full tape
   is not a state-compatible residual; any next candidate needs a local
   feasibility and rejoin contract rather than longer tape playback.

## Machine-readable evidence

- `research/highscore_route_refresh_2026-08-13/artifacts/analysis.json`
- `research/highscore_route_refresh_2026-08-13/artifacts/selected_transition_audit.json`
- `research/highscore_route_refresh_2026-08-13/artifacts/selected_source_public_routes.json`
- `research/highscore_route_refresh_2026-08-13/artifacts/route_transplant_ablation.json`
- `research/highscore_route_refresh_2026-08-13/artifacts/shared_market_screen.json`
- `research/highscore_route_refresh_2026-08-13/artifacts/candidate_manifest.json`

The corrected compressed cache is
`research/cache/highscore_route_refresh_2026-08-13`. The unaligned cache and
results are retained only as provenance and must not be compared as action-tape
evidence.
