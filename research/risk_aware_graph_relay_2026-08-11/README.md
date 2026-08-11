# Risk-aware graph relay experiment (2026-08-11)

This lane tests one deliberately narrow hypothesis: a learned topology-aware
selector can improve the timing of Boatlee V16-RC2's three-turn fertilizer
market relay without replacing its unit route.

The experiment compares:

1. Boatlee V16-RC2 control;
2. a parameter-matched flat MLP residual;
3. a two-layer graph-convolution residual over product, demand, crop-input,
   animal-feed, and global-state relations.

All variants preserve Boatlee's farmer/hand actions.  A residual may only force
or suppress an existing fertilizer relay opportunity, and it rejoins the
original policy three turns later by reducing the scheduled fertilizer sale by
the same quantity.

## Decision rules

Hard technical failures are exceptions, malformed actions, official timeout or
overage exhaustion, and use of opponent-private state.  Animal escapes, crop
deaths, seed overcommit, shed overflow, and terminal inventory are **soft
economic diagnostics**.  They are reported and priced through paired terminal
margin and downside risk; none is an independent zero-tolerance promotion gate.

Promotion requires positive held-out paired evidence against the control, no
technical failures, and a graph advantage over the flat ablation.  Mean margin
alone is insufficient: the report also includes win count, weakest opponent
family, worst margin, and lower-tail CVaR.

## Reproduction

Run from repository root after installing the current Kaggriculture environment:

```bash
python research/risk_aware_graph_relay_2026-08-11/run_experiment.py
```

The local development checkout may instead provide the exact current official
interpreter under `.research_runtime`; that directory is test support and is not
part of the research deliverable.
