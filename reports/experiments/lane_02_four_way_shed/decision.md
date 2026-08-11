# Lane 02 — four-way shed access

## Scope

Candidate is an isolated copy of the canonical `submission/`, retaining its
archive-root `main.py` import model.  Only these behavioral changes were made:

- `candidate/scheduler.py`: logistics `PICKUP`/`DROP` targets all four centre
  shed access tiles, including the three initially `LOCKED` tiles.
- `candidate/rules.py`: the final projector permits `PICKUP`, `DROP`, and
  shed-directed `PLACE` on a locked centre tile.  All other tile-changing
  operations remain projected to `PASS` there.

No macro target, herd/crop policy, market threshold, path cache, or market code
changed.  The projector remains the final action boundary.

## Engine basis and regressions

Upstream `master` was rechecked as
`bded87b0d7879078c726a93a4884d044f79c4eed`.  Its Kaggriculture engine is
retained in `official_engine/` for this lane only (Git blob
`4b78842d0f2d4abf6e318a8248b6306454f5c714`; SHA-256
`ba86588cbc0e9f3cb11462c8da6c67d8197f0b97d075938dbc713102b9718b7d).

`tests/test_four_way_shed.py` passed 5/5 against that engine:

- locked `(5,4)`, `(4,5)`, and `(5,5)` execute `PICKUP`, `DROP`, and
  shed-directed `PLACE`, respectively;
- `PLANT`, `WATER`, `HARVEST`, `FERTILIZE`, `DIG`, `BUILD_*`, `FEED`,
  `COLLECT_FERTILIZER`, and `CARE` are semantic no-ops on a locked centre
  tile;
- the projector mirrors that split and the scheduler can assign a locked
  centre hand to `PICKUP` using all four access tiles.

`python -m compileall -q experiments\\lane_02_four_way_shed` also passed.

## Development smoke

Protocol: newest retained engine above; seeds `811`, `823`; both seats; official
deterministic `starter`; 4 games each for canonical control and candidate.
This is intentionally a development smoke, not a promotion matrix.  Both
variants completed 4/4 games with 2 repeated seed-977 self-plays producing an
identical action digest and rewards.

| Metric | Control | Four-way shed | Delta |
|---|---:|---:|---:|
| Mean terminal margin vs starter | 70,939.25 | 72,432.25 | +1,493.00 |
| Movement actions | 19,028 | 18,852 | -176 (-0.93%) |
| Productive actions | 7,383 | 7,468 | +85 (+1.15%) |
| Moves / productive action | 2.5773 | 2.5244 | -2.05% |
| PICKUP trip distance (mean) | 2.0992 | 2.0305 | -3.27% |
| DROP trip distance (mean) | 8.8337 | 8.8883 | +0.62% |
| Mean per-game candidate-call p95 (ms) | 3.1750 | 2.9818 | -0.1932 |

Matched candidate-minus-control margins by `(seed, seat)` were `+3553`,
`+3553`, `+13333`, and `-14467`.  The negative `(823, 1)` result is retained;
the candidate had the higher margin in 3/4 pairs.  It won all four starter
games, as did the control.

Safety was zero for both variants: malformed actions, timeout calls/statuses,
animal escapes, fresh-crop deaths, shed-overflow states, seed-overcommit
events, market lists over 10, and semantic no-ops.  Full machine-readable
records are `smoke_control.json` and `smoke_four_way_shed.json`.

## Retained limitation and decision

The planned public-agent extension was attempted first with the default
`roman_lb950` extracted opponent at seed 811, seat 0.  It did not finish its
first full game within the 60-second small-smoke command cap (the process was
terminated after 64.038 seconds, before a replay or partial result existed).
It was not retried or enlarged.  The deterministic self/control smoke above
was used as the permitted lower-cost fallback.

There is a narrow positive signal for a later, larger **matched** ablation:
movement efficiency improved while all safety checks stayed zero, and the mean
starter margin rose in 3/4 matched pairs.  This is insufficient for promotion
or any canonical-submission change; a future expansion should first solve the
public-opponent runtime constraint and retain all paired losses.
