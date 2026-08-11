# Lane 05 — crop-scale treatment

## Scope

This lane copied the canonical archive-root candidate into `candidate/` and
changed only crop-scale policy. Livestock targets, market-order sequencing, and
the public-information opponent selector are unchanged. The treatment keeps the
opening eight melons and expands only the strawberry production band from seven
to fourteen slots: ten SW slots plus four NW cells not used by the opening melon
cohort.

The scale gate requires SW (and NE for the four-slot extension), individual
terminal finishability, a daily cap of two plants, same-day PLANT+WATER action
capacity, a three-day crop/husbandry/harvest/shipping workload estimate, shed
headroom below 80, and a low held-strawberry reserve. A six-seed pre-buffer
accounts for the engine fact that same-turn market planning observes pre-unit
seed inventory. Only a crop cohort that passes all gates is raised to P2; P0/P1
survival remains ahead of it and all generic planting remains P5.

## Engine and checks

The live upstream master was confirmed as
`bded87b0d7879078c726a93a4884d044f79c4eed`. The lane-only runtime copied the
pinned package and applied the authoritative `a4dce..bded87` diff; the tested
`kaggriculture.py` and `.json` blobs exactly match upstream `4b78842d...` and
`0fcdf2c...`, respectively. No `.vendor`, data, docs, dist, canonical
submission, or shared report was changed.

`python -m compileall -q candidate tests run_smoke.py` passed.

`python -m unittest discover -s tests -v` passed: 3/3 focused tests cover the
14-slot NW/SW topology, land/shed/labor/terminal gates, the seed reserve, daily
cap, and same-day-water feasibility.

## Final minimal matched smoke

Four full official episodes on `bded87b`: seeds 101 and 307, both seats, final
candidate versus the untouched canonical control. This is development evidence,
not a promotion evaluation.

| Seed | Candidate seat | Candidate | Control | Difference | Max live strawberries |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 0 | 16,538 | 17,891 | -1,353 | 14 |
| 101 | 1 | 16,321 | 24,142 | -7,821 | 14 |
| 307 | 0 | 24,014 | 26,917 | -2,903 | 14 |
| 307 | 1 | 27,189 | 33,816 | -6,627 | 14 |

Result: 0 wins, 0 ties, 4 losses; mean difference **-4,676**. Both players
ended `DONE` in all games. The production change genuinely executed: every game
confirmed 14 strawberry cohorts, with 196/196/218/217 WATER actions,
32/32/44/44 strawberry units harvested and sold, respectively. Worker load
peaked at 11 (mean about 9.58); shed peaks were 66, 66, 69, and 69, with only
0–7 non-sale terminal items remaining. Final unlocked empty-tile counts were
43, 46, 41, and 46.

Safety audit: 0 malformed actions, timeouts, animal escapes, fresh-crop deaths,
shed-overflow states, seed overcommitments, or market lists above 10. Candidate
latency was p95 at most 1.636 ms and maximum 17.892 ms.

The machine-readable per-game diagnostics are in
`artifacts/smoke_bded87b.json`; retained failed implementation/effectiveness
attempts are in `artifacts/failed_smoke_attempts.json`.

## Decision

Do **not** advance this crop-scale treatment to a larger matched ablation or
promote it to `submission/`. It safely reaches the intended 14-cell scale but
has no positive paired-win signal and loses all four bounded control games.
