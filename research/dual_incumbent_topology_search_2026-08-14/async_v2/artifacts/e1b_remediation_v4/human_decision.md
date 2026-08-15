# Async E1b technical development decision

**READY_FOR_E1B_PREFLIGHT**

This is a technical-only preflight result. It does not launch E1b,
re-execute retained E1 seeds, authorize E2, or claim strategy efficacy.

## Evidence

- Retained E1 audit: 4096 jobs, 235 unique lane-genomes, 36 no-op, 199 behavior-changing.
- Static/technical topology capacity: {'v27_current_meta': 1500, 'boatlee_v16_rc2_market_relay': 1500} compile-distinct nonempty semantic phenotypes per lane; this is not an exact action-change claim.
- Exact technical observed action-change: {'v27_current_meta': {'evaluated_compile_nonempty_semantic_phenotypes': 8, 'observed_behavior_changing_phenotypes': 7, 'observed_action_no_op_phenotypes': 1, 'observed_behavior_changing_rate': 0.875, 'observed_action_no_op_candidate_ids': ['ac_bf69712345be6ebcf0a80f89'], 'behavior_flag_consistent': True}, 'boatlee_v16_rc2_market_relay': {'evaluated_compile_nonempty_semantic_phenotypes': 8, 'observed_behavior_changing_phenotypes': 8, 'observed_action_no_op_phenotypes': 0, 'observed_behavior_changing_rate': 1.0, 'observed_action_no_op_candidate_ids': [], 'behavior_flag_consistent': True}}.
- Windows spawn scheduler/cache/checkpoint/failure audit: pass=true.
- Technical smoke: seed 811407 only, 64 complete jobs; all finalists both-seat parity=true.
- Formal launcher plumbing: registry_run_id=async-e1b-20260815-consumed-small-screen, retained seeds=[81426017, 81426029], fresh_evaluation_seeds=[]; authority hashes validated=true, execution_started=false.
- Failed preflight negative evidence preserved: manifest_sha256=f1433c44f1fd83446173234ac8b9136215a6549d188a3a9c687e87924901cf0c; launch/PID evidence present=false.
- 15-worker process-tree CPU: mean=49.329%, median=56.506%, p95=80.116%, peak=81.557%; overall throughput=0.721484 candidate-context jobs/s.
- Formal/fresh seeds executed=false; retained E1 seeds re-executed=false; E2 games executed=false.

## Boundary

The progressive E1b protocol remains non-executable. A new explicit
authorization is required before the consumed E1 small screen or any
later stage is run.
