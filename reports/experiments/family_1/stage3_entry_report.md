# Family 1 Stage 3 entry audit

Decision: **DO_NOT_ENTER_STAGE3**

- `PROTOCOL_COMPLETE`: True
- `EFFICACY_GATE_PASS`: False
- Stage 3: **PENDING** (not started and not complete)
- Stage 3 holdout used: **No**

## Remediation decision block

| Treatment | W-T-L | paired win delta | seed-cluster 95% CI | paired terminal delta |
|---|---:|---:|---:|---:|
| `canonical_control` | 1-0-639 | n/a | n/a | n/a |
| `scheduler_fixes` | 5-0-635 | 0.006250 | [-0.001563, 0.015625] | 1713.634 |
| `selector_only` | 5-0-635 | 0.006250 | [-0.001563, 0.015625] | 1724.000 |
| `single_route` | 1-0-639 | 0.000000 | [-0.004687, 0.004687] | -4693.786 |
| `full_repaired` | 1-0-639 | 0.000000 | [-0.004687, 0.004687] | -188.233 |

The full candidate retained 639 losses; all flip and regression cases, opponent strata, the competitive pool, and the separate `saiteja_2600` stress pool are in `stage3_entry_remediation_comparison.json`.

## Proven

- The current upstream is `bbcdd460accc16fdb1d1074b8c5b1d30ea92da4a`; the matched-matrix checkout is byte-identical for Kaggriculture source.
- ERR-025 requested-quantity contamination is removed across 743 episode files / 1486 valid routes with 0 money mismatches. Repaired artifact `9930d169aeb23c744daa8df25e2489fec2b599c7f73d2b11d02b6f74581e6a2a`; runtime module `8828753ed8a75d934ba93444e3cc7b01d7097caa606a0442ce0c3fd8ac8c0930`; independent rebuild: True.
- EOD auto-drop is frozen as a correctness/safety fix: fresh-crop deaths 9 -> 0, paired win delta 0.000000, paired terminal delta 14044.000.
- State-machine and sustained rejoin are separate; every post-rejoin record carries 1/3/6-day route health and terminal outcome.

## Not proven

- Maintenance marginal-action value is not frozen: fresh-crop deaths 9 -> 30 despite terminal delta 4366.683.
- Animal finite-season NPV is not frozen: paired win delta 0.000000 and terminal delta 24.933 do not establish efficacy.
- Alternate market sequencing is not frozen: paired win delta 0.000000 and terminal delta -74.467.
- Absolute route reward is not competitive evidence; entry depends on the matched win result above.

## Safety / correctness failures retained

- `diagnostic/canonical_control`: `{"semantic_noops": 1134}`
- `diagnostic/scheduler_fixes`: `{"cap_waste_units": 7}`
- `diagnostic/selector_only`: `{"cap_waste_units": 7}`
- `diagnostic/single_route`: `{"cap_waste_units": 60, "fresh_crop_deaths": 3}`
- `diagnostic/full_repaired`: `{"cap_waste_units": 271, "fresh_crop_deaths": 3}`
- `remediation/canonical_control`: `{"semantic_noops": 1106}`
- `remediation/single_route`: `{"cap_waste_units": 67, "fresh_crop_deaths": 1}`
- `remediation/full_repaired`: `{"cap_waste_units": 179, "fresh_crop_deaths": 3}`
- `daily_logistics/full_repaired`: `{"cap_waste_units": 33}`
- `recovery_faults/full_repaired`: `{"animal_escapes": 18}`

## Rejected evidence and exact blockers

- Historical `experiments/family_1_route_memory/artifacts/stage2_route_bank.json` (`cb0dc09c9bf677f6cd8d8046e3a1a03d7d08eb68292af0074a87e28616e526e5`): rejected for ERR-025 requested-quantity contamination.
- `all_correctness_and_safety_zero`: evidence `reports/experiments/family_1/stage3_entry_validation.json`, `reports/experiments/family_1/stage3_entry_diagnostic_full_repaired.json`, `reports/experiments/family_1/stage3_entry_remediation_full_repaired.json`, `reports/experiments/family_1/stage3_entry_daily_logistics.json`, `reports/experiments/family_1/stage3_entry_recovery_faults.json`; next: Replay every failing seed from its day-level log; constrain expansion/workload before purchase and rerun the identical block.
- `positive_paired_win_delta`: evidence `reports/experiments/family_1/stage3_entry_remediation_comparison.json`; next: Use matched flip/regression seeds to isolate route-target harm; change no threshold until a one-factor paired ablation predicts the sign.
- `normal_non_roman_multi_seed_wins`: evidence `reports/experiments/family_1/stage3_entry_remediation_full_repaired.json`, `reports/experiments/family_1/stage3_entry_remediation_comparison.json`; next: Target the weakest normal-opponent stratum with opponent-conditioned route evidence, then verify on a fresh non-holdout block.
- `sustained_rejoin_multi_seed`: evidence `reports/experiments/family_1/stage3_entry_recovery_faults.json`; next: Repair route-health feasibility or recovery transitions and rerun the same six official fault classes across fresh development seeds.
- `abandonment_materially_reduced`: evidence `reports/experiments/family_1/stage2_nearest_robust_official_640.json`, `reports/experiments/family_1/stage3_entry_remediation_full_repaired.json`, `reports/experiments/family_1/stage3_entry_validation.json`; next: Ablate distance/capital/workload components using recorded 1/3/6-day horizons; retain the gate unchanged.
- `abandonment_reduction_statistically_supported`: evidence `reports/experiments/family_1/stage2_nearest_robust_official_640.json`, `reports/experiments/family_1/stage3_entry_remediation_full_repaired.json`, `reports/experiments/family_1/stage3_entry_validation.json`; next: Demonstrate an abandonment-rate reduction whose conservative 95% difference interval excludes zero; do not weaken the 10-point materiality gate.
