# Live high-score route refresh (2026-08-13)

This lane compares a fresh public-leaderboard replay snapshot with the frozen
2026-08-09 Top-50 snapshot and the retained 2026-08-10 streaming corpus.  It
uses target-player public actions and public farm state for route analysis.
No private replay field from either player is read or stored.

The raw replay collector is the retained streaming collector at
`research/full_tape_topology_scaleup_2026-08-10/streaming_corpus.py`.  Its
cache for this refresh is `research/cache/highscore_route_refresh_2026-08-13`;
successful raw replay JSON is deleted immediately after compressed features
and the target action tape are durable.

Reproduce the compact analysis and the two research-only standalone tape
artifacts with:

```powershell
py -3.12 research\highscore_route_refresh_2026-08-13\analyze_refresh.py
py -3.12 research\highscore_route_refresh_2026-08-13\extract_selected_public_routes.py
py -3.12 research\highscore_route_refresh_2026-08-13\audit_selected_transitions.py
py -3.12 research\highscore_route_refresh_2026-08-13\build_candidates.py
py -3.12 research\highscore_route_refresh_2026-08-13\build_candidates.py --check
py -3.12 research\highscore_route_refresh_2026-08-13\run_route_transplant_ablation.py
py -3.12 research\highscore_route_refresh_2026-08-13\run_shared_market_screen.py
```

The candidates are deliberately narrow route-transplant ablations.  They are
not claimed to be state-compatible backbones or promotion candidates.

The completed decision is recorded in
`reports/highscore_route_refresh_2026-08-13/decision.md`. Direct transplant was
stopped after the smallest matched screen: the new shared 8-cow/4-sheep route
raised own-bank output but produced an opponent-dependent market externality,
and none of seven observed market tapes passed both incumbent strata.

## Replay action alignment correction

The retained 2026-08-10 streaming collector originally selected replay rows
0..718. Kaggle replay row 0 is the initial placeholder; the 719 meaningful
agent calls are rows 1..719. The collector and a regression test now enforce
that mapping. The first refresh cache and transplant results are retained with
the `_unaligned` suffix and are excluded from efficacy conclusions. Historical
exact-unit comparisons use the correctly aligned archived Top-50 transition
audit, not old streaming-cache tape digests.
