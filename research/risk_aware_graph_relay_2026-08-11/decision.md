# Risk-aware graph relay decision

Date: 2026-08-11  
Decision: **do not promote the GCN or MLP; retain Boatlee V16-RC2 as the main
approach and keep the lane as falsifying evidence.**

## Question

Can a small topology-aware model decide when to force or suppress Boatlee
V16-RC2's three-turn fertilizer relay more effectively than both the current
hard route lock and a parameter-matched flat model?

The experiment deliberately preserves every farmer and hand action.  It only
moves a scheduled fertilizer sale three turns earlier and reduces the later
sale by the same quantity, so each intervention naturally rejoins Boatlee.

## Engine and protocol

- Current official Kaggriculture Python blob:
  `4b78842d0f2d4abf6e318a8248b6306454f5c714`.
- Current official configuration blob:
  `0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8`.
- Official limits: 720 recorded states, `actTimeout=1`, and 60 seconds of
  remaining overage time.
- Counterfactual dataset: 72 paired force-vs-block examples (144 full games),
  split into 48 training and 24 validation examples. Each pair reused seed,
  seat, opponent, and relay step.
- Held-out evaluation: seeds 404 and 505, both seats, and five opponent
  families (`v27_current_meta`, guarded v27, Kaito v21, Roman LB950, and
  Saiteja Mega Ensemble). Four policies produced 80 full games.
- Total retained protocol: 224 full current-engine games.

The graph uses ten nodes: nine products plus global farm state. Edges represent
town co-demand, fertilizer-to-crop inputs, wheat-to-animal-product feed, and
global coupling. The GCN has 449 learned parameters. The flat MLP has 409.

## Results

All figures below are paired terminal-margin deltas versus unmodified Boatlee.

| Residual | Positive / zero / negative pairs | Mean | Median | CVaR20 | Worst |
| --- | ---: | ---: | ---: | ---: | ---: |
| Always force | 10 / 10 / 0 | +6.5 | +2.5 | 0.0 | 0.0 |
| Flat MLP | 10 / 10 / 0 | +5.5 | +0.5 | 0.0 | 0.0 |
| GCN | 10 / 10 / 0 | +4.3 | +2.5 | 0.0 | 0.0 |

| Opponent family | Always force | Flat MLP | GCN |
| --- | ---: | ---: | ---: |
| v27 current | 0.0 | 0.0 | 0.0 |
| v27 guarded | 0.0 | 0.0 | 0.0 |
| Kaito v21 | +8.0 | +8.0 | +8.0 |
| Roman LB950 | +2.5 | +0.5 | +2.5 |
| Saiteja Mega Ensemble | +22.0 | +19.0 | +11.0 |

The MLP validation MAE was 1.62 versus 5.03 for the GCN. Both had validation
sign accuracy of 0.417 because 14/24 validation labels were exactly zero. The
training and validation label distributions had no negative examples.

All candidates had zero exceptions, malformed actions, timeout calls, or
overage exhaustion. The GCN's worst per-game p95 was 0.547 ms and observed max
was 18.0 ms, comfortably below the project limits on this machine. Animal
escapes, crop deaths, fresh-crop deaths, seed overcommit, overflow, and terminal
inventory all had aggregate delta zero versus control. These are soft economic
diagnostics, not hard pass conditions.

## Interpretation

The graph hypothesis is falsified for this intervention surface. A static
always-force residual beats both learned selectors, so the learned models do
not explain the positive margin. The useful mechanism is simply that RC2's
existing route-distance lock is slightly too restrictive against Kaito, Roman,
and Saiteja. The effect is only 6.5 terminal coins on average and does not alter
any held-out win/loss, far too small to justify a new main approach or runtime
model.

This does **not** show that GNNs are generally unsuitable. It shows that a
binary, reversible fertilizer timing choice has too little target variance and
no observed downside for topology learning to earn its complexity.

## Limits and next experiment

- Only two held-out seeds were used. Results are deterministic and paired but
  are not a leaderboard-rating estimate.
- The harness calls the current official interpreter directly through a small
  framework adapter. It does not reproduce Kaggle service jitter.
- The graph topology encodes known mechanics; topology itself was not learned.
- Public opponents are behaviorally varied, but none supplied negative
  single-relay labels in the sampled windows.

The next worthwhile learning surface is job-level residual value over a 24- to
48-turn horizon: feed/water, harvest/ship, capacity relief, market timing, and
intentional asset abandonment as competing jobs. Labels must include both
positive and negative counterfactuals and compare graph message passing with a
flat ablation and a simple greedy value rule. Add another public agent only if
it contributes a novel fertilizer, capacity, or maintenance interaction; raw
public score alone is not sufficient.

## Reproduction artifacts

- `artifacts/counterfactuals.jsonl`: all 72 retained counterfactual pairs.
- `artifacts/held_out_evaluation.csv`: all 80 held-out games.
- `artifacts/analysis.json`: exact summaries and promotion gates.
- `artifacts/gcn_model.json` and `artifacts/flat_mlp_model.json`: fitted weights.
- `run_experiment.py`: full generation, training, evaluation, and analysis.

The official source used for the fingerprint is the
[Kaggriculture environment in Kaggle's repository](https://github.com/Kaggle/kaggle-environments/tree/master/kaggle_environments/envs/kaggriculture).
