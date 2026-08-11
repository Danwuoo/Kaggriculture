# Main-approach performance optimization decision

Date: 2026-08-11
Decision: **retain layers 1-5 independently on both incumbents; reject and
fully revert layer 6.** Strategy actions are unchanged.

## Scope and frozen controls

This lane is behavior-preserving performance work on two independent runtime
trees:

- `v27_current_meta`
- `boatlee_v16_rc2_market_relay`

The pre-change working-tree standalones were frozen under
`controls/layer_00_baseline/`, not reconstructed from HEAD:

| Incumbent | Frozen SHA-256 | Bytes |
| --- | --- | ---: |
| v27 | `917fda167d98bbdea95307d61ff3954f56493404baa64ef8467407ad21571fb9` | 21,973 |
| Boatlee | `02d9e7442a5efc425b767aae942d35a1acd41327b53a8038c694f7065b9e1379` | 31,897 |

The official engine was read directly from the local pinned Git object store
and executed from a temporary extraction. The exact source is commit
`bded87b0d7879078c726a93a4884d044f79c4eed`, Python blob
`4b78842d0f2d4abf6e318a8248b6306454f5c714`, and configuration blob
`0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8`. SHA-256 values are
`fb9215c5e21a25243e2d13e75b3d70a79cf7d78fff150a90f1bb5eacf9ba2bcf`
and `7f196f4aaf9b4e482fbd61ba4bf19f5cec4da0f81938ece756954035a65c0bb5`.

Every layer used a frozen immediate predecessor, both seats, one fresh
seed/opponent block, generated and development representations, and repeated
same-observation replay timing. Any action/reward/diagnostic mismatch was a
hard rejection. Small timing effects required an alternating 31-repeat
confirmation. Layer speedups below use each layer's own matched trace and are
therefore not multiplicative.

## Layer decisions

| Layer | v27 result | Boatlee result | Decision |
| --- | ---: | ---: | --- |
| 1. Action-schema copy | 122.84 → 45.49 ms, 2.70× | 184.92 → 57.45 ms, 3.22× | Retain both. `copy.deepcopy` was replaced by a two-level schema copy. |
| 2. Read-only template + COW | 50.44 → 32.22 ms, 1.57× | 58.65 → 33.19 ms, 1.77× | Retain both. Static aligned turns return the route template; dynamic turns materialize. |
| 3. Precomputed metadata | 21.38 → 20.40 ms, 1.05× | 25.26 → 21.44 ms, 1.18× | Retain both. A 31-repeat alternating confirmation improved both seats: median 1.18× v27 and 1.13× Boatlee. |
| 4. One-materialization pipeline | 15.29 → 13.61 ms, 1.12× | 17.01 → 13.87 ms, 1.23× | Retain both. Seat/reset context is computed once and every overlay mutates one dynamic action before final projection. |
| 5. Base64 codec | decode 1.981 → 1.296 ms | decode 2.880 → 1.811 ms | Retain both. In 31 alternating imports Base64 also reduced cold median by 0.58/0.74 ms. Each artifact grew 489 bytes. |
| 6. Guarded micro-optimizations | confirmation 0.985× | confirmation 0.959× | Reject both and revert. Neither improved both seats in the 31-repeat alternating confirmation. |

All retained layer files report `behavior_equal=true`. Layer 6's initially
mixed result and the confirming adverse repetitions remain in
`layers/layer_06_guarded_hot_path*.json`; the final generated SHA-256 values
match the frozen layer-5 artifacts byte for byte.

## Final same-trace performance

The canonical cumulative comparison is `final_vs_baseline.json`: fresh seed
873089, Kaito v21, both seats, and 31 repeats per representation.

| Metric | v27 baseline → final | Boatlee baseline → final |
| --- | ---: | ---: |
| Season agent time, median across seats | 73.781 → 14.314 ms (**5.15×**) | 142.098 → 16.240 ms (**8.75×**) |
| Conservative per-turn p50 (worse seat) | 0.0901 → 0.0164 ms | 0.1861 → 0.0125 ms |
| Conservative per-turn p95 | 0.2824 → 0.0762 ms | 0.5539 → 0.0744 ms |
| Conservative per-turn p99 | 0.3639 → 0.1291 ms | 0.7985 → 0.1646 ms |
| Conservative observed max | 0.5683 → 0.2391 ms | 1.0778 → 0.2786 ms |
| Traced peak bytes (worse seat) | 76,096 → 69,728 | 77,016 → 70,632 |
| GC collections during replay | 0 → 0 | 0 → 0 |
| Static/dynamic returns, seat 0 | 0/719 → 665/54 | 0/719 → 665/54 |
| Static/dynamic returns, seat 1 | 0/719 → 676/43 | 0/719 → 676/43 |
| Cold import median | 18.953 → 19.155 ms | 19.406 → 13.891 ms |
| Artifact bytes | 21,973 → 28,142 | 31,897 → 37,741 |

The v27 cumulative cold import is effectively flat/slightly slower because the
new metadata and pipeline source offset Base64's faster decoder. Layer 5 itself
did improve cold import against the identical layer-4 runtime. Cold start was
not allowed to override the much larger steady-state result.

The static/dynamic counts are trace-specific. Yarn-store activation, relay
locking, weeds, failed hires, and alignment divergence can legitimately make a
different Boatlee game more dynamic.

## Official-engine validation

The final fresh block used seeds 873001, 873019, and 873037 against Kaito,
Saiteja, and the other frozen incumbent, from both seats. For each of the 12
incumbent games, frozen baseline, final generated, and development entrypoints
had identical 719-action digests, opponent digests, rewards, termination,
schema findings, and economic diagnostics. Each incumbent went 5/0/1 against
its opponents; this is not an efficacy gain because baseline and final actions
are identical.

Additional seed 873059 repeated generated artifacts from both seats, and seed
873077 imported a copy from an isolated directory and completed an official
game. Machine-readable retained outputs cover 154 full games across the layer,
final, isolated, determinism, and shared development validations.

Final gates:

- `DONE/DONE`, 719 calls, and reproducible digests in every retained final game.
- Zero exceptions, timeout calls, overage exhaustion, malformed actions,
  hand-alignment errors, seed overcommit, or market overflow.
- All final market lists were at most ten entries.
- Fresh-game worst p95/max: v27 0.176/2.744 ms; Boatlee 0.108/0.489 ms,
  far below 150/750 ms.
- Zero aggregate animal escapes, crop deaths, fresh-crop deaths, or shed
  overflow in the fresh generated games, matching their controls.
- Deterministic builders; standalone imports are limited to
  `base64`, `json`, `math`, and `zlib`; no runtime file/network/subprocess
  calls; both artifacts are far below 5 MiB.

## Official-hardware extrapolation

This is an estimate, not promotion evidence. Applying the measured same-trace
cumulative factors to the supplied exploratory season figures gives about
11.13 ms/season for v27 (57.36/5.15) and 10.71 ms/season for Boatlee
(93.67/8.75). Applying Boatlee's local per-percentile ratios to the retained
official logs gives an agent-code-only estimate of p50 0.025 ms, p95 0.096 ms,
p99 0.168 ms, and max 0.503 ms. Service serialization and scheduler jitter will
set a higher floor. For cold start, the conservative additive estimate is
roughly 41.7 ms versus the retained 42.753 ms median, based only on the measured
route-decode saving; proportional import extrapolation would be too optimistic.

## Remaining risks

- Static returns expose the same mutable list object to the caller. The audited
  official interpreter does not mutate actions, and all official games passed;
  an out-of-contract caller that mutates returned actions could corrupt the
  template for later turns.
- Performance depends on observation history and the number of dynamic turns.
  Local Python timings do not reproduce Kaggle service jitter.
- Base64 increases source size slightly, and v27's total cold import did not
  improve versus the original smaller artifact.
- No Kaggle submission, archive packaging, remote write, commit, push, or PR was
  performed.

## Reproduction artifacts

- `layers/layer_00_baseline.json` through
  `layers/layer_06_guarded_hot_path.json`: per-layer games and measurements.
- `layers/layer_03_precomputed_metadata_confirmation.json` and
  `layers/layer_06_guarded_hot_path_confirmation.json`: alternating small-effect
  confirmations.
- `layers/layer_05_codec_comparison.json`: raw codec/import measurements.
- `final_vs_baseline.json`: canonical cumulative latency/allocation result.
- `final_validation.json`: fresh games, determinism, isolated import/game, and
  artifact audit.
- `controls/`: byte-exact generated controls at every retained boundary.
