# Family 1 Stage 2 completion report

Status: **COMPLETE**. Both isolated finalists are retained; this is not a promotion into `submission/`.

## Route-bank provenance

The streaming build consumed the complete **743-episode** daily manifest: 742 JSON files packaged in `kaggle/kaggriculture-episodes-2026-08-05`, plus missing manifest episode `90288213` fetched through the official Kaggle replay API. These produced 1486 valid agent routes, 1485 unique routes, and 12 deterministic macro clusters. The dataset is CC0-1.0; identity, private-state fields, and action tapes are not retained.

## Fixed Stage 2 validation

| Selector | W-T-L | Paired W-T-L | Wilson 95% | Worst opponent wins | Median diff | p95 / max ms | Rejoins / switches / abandons |
|---|---:|---:|---:|---:|---:|---:|---:|
| `adaptive_profit` | 10-0-630 | 3-0-317 | 0.85%-2.85% | 0 | -88906.0 | 14.038 / 389.833 | 523 / 299 / 640 |
| `nearest_robust` | 11-0-629 | 4-0-316 | 0.96%-3.05% | 0 | -88754.5 | 14.698 / 258.595 | 405 / 198 / 640 |

Each finalist ran 64 fixed seeds (200000-200063), both seats, and all five core opponents: **640 official-engine games per finalist, 1,280 total**. All candidate safety, timeout, malformed-action, semantic-no-op, seed, market-cap, and overflow counts are zero.

The lexicographic Stage 3 starting recommendation is `nearest_robust`; both materially different selectors remain frozen and evidenced.

## Implementation and remaining uncertainty

Stage 2 adds a complete-dataset streaming summarizer, deterministic macro clustering, live legal-public-state route selection, bounded repair, route switching/rejoin, two frozen selector packages, and fixed-gate tooling. The defensive scheduler and final legality projector remain authoritative.

Still unproven: Stage 3 holdout performance, the expanded then-current opponent pool, and canonical promotion/package acceptance. No file under `submission/` was changed.

Machine-readable gate: `reports/experiments/family_1/stage2_evidence.json`.
