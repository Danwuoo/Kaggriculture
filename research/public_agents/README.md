# Public Kaggriculture research agents

## Primary opponent pool

The primary pool is the top ten unpinned public notebooks shown by Kaggle's
competition Code page under **Public Score**, captured on 2026-08-16. Scores
below are Kaggle's displayed notebook scores at capture time, not title claims
and not the overall competition leaderboard.

| Public rank | Score | Directory | Kernel |
| ---: | ---: | --- | --- |
| 1 | 2913.3 | `lb20260816_01_boatlee_v16_rc5` | `boatlee/v16-rc5-high-score-8c-4s-premium-market-lead` |
| 2 | 2905.7 | `lb20260816_02_kaito_v25` | `kaitofukami/15-16-strict-future-v25-meta-reset` |
| 3 | 2863.4 | `lb20260816_03_deniz_v111` | `denizeryilmaz/v111-8c4s-economic-core-premium-lead` |
| 4 | 2837.0 | `lb20260816_04_rayk_zero_to_top` | `raykkretzschmar/kaggriculture-findings-from-zero-to-top-meta` |
| 5 | 2834.7 | `lb20260816_05_boatlee_v16_rc5_r5a` | `boatlee/v16-rc5-r5a-high-score-8c-4s-recovery` |
| 6 | 2833.9 | `lb20260816_06_boatlee_v14_clone_preemption` | `boatlee/84-84-base-public-holdout-v14-clone-preemption` |
| 7 | 2812.0 | `lb20260816_07_kunal_ttv1` | `kunaldesale2408/kaggriculture-ttv1` |
| 8 | 2772.7 | `lb20260816_08_salem_3094` | `salemali7/3094-score-kaggriculture` |
| 9 | 2754.9 | `lb20260816_09_bruce_high_score_pipeline` | `bruceqdu/my-2026-08-04-high-score-pipeline` |
| 10 | 2733.3 | `lb20260816_10_prvsiyan_soil` | `prvsiyan/kaggriculture-frontier-the-soil-remembers-rain` |

All ten notebook sources and their statically extracted `main.py` files are
retained. `primary_opponents.json` records the capture URL, scores, byte sizes,
SHA-256 hashes, duplicate groups, and static-audit findings. Ranks 1/3 are
byte-identical, as are ranks 7/8, so the ten public slots represent eight
unique artifacts. Report notebook-stratified results, but do not count exact
duplicates twice in a cluster-weighted aggregate.

`scripts/run_public_league.py` now defaults to these ten primary opponents.
All ten also completed one 720-state `DONE`/`DONE` smoke game against `starter`
on the locally pinned engine. See `primary_opponent_smoke.json`; this is runtime
compatibility evidence only, not current-engine or strategy-efficacy evidence.

## Legacy pool

The previous five-notebook pool, downloaded on 2026-08-06, remains available
for historical reproduction but is no longer the default opponent set. Its
title metrics are author claims, not local or leaderboard verification.

- `saiteja_mega_ensemble_3000`: `saitejabandaruin/kaggriculture-ultimate-mega-ensemble-3000`
- `saiteja_pure_architecture_2600`: `saitejabandaruin/kaggriculture-pure-architecture-2600-elo-v3`
- `kaito_v21_top30`: `kaitofukami/177-180-fresh-top-30-v21-1-conditional-memory`
- `kaito_v20_weed_recovery`: `kaitofukami/159-160-vs-frontier-v20-weed-slip-recovery`
- `roman_lb950`: `romanrozen/strong-statr-baseline-agent-lb-950`

Run `python scripts/extract_public_agents.py` to statically extract embedded
Python payloads.  The extractor parses notebook literals and never executes a
notebook cell.  Extracted code remains offline research material and is not
included in `submission/` or `dist/submission.tar.gz`.
