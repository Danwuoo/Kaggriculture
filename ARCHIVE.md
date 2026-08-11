# Kaggriculture External Archive

The active workspace was compacted on 2026-08-10. Large immutable evidence,
retired research implementations, and replay payloads were moved without
renaming their paths below:

`C:\Users\wurre\Desktop\Kaggriculture-archive\2026-08-10`

The archive contains 282 files totaling 1,610,451,462 bytes (1,535.85 MiB),
including its own `README.md`.
Paths under the archive mirror their former paths under the workspace.

| Former workspace path | Retention |
| --- | --- |
| `data/public_replays/top50-2026-08-09/replays/` | All 50 raw replay payloads. Metadata and checksums remain in the active workspace. |
| `reports/public_replays/` | Ten historical Round 1 raw replay payloads. |
| `research/counterfactual_market_residual_2026-08-10/` | Stopped market-residual implementation and durable game cache. |
| `research/exact_backbone_correction_2026-08-10/` | Deferred exact-backbone implementation. |
| `research/full_season_topology_identity_safe_2026-08-10/` | Completed negative experiment implementation. |
| `research/route_state_graph_hierarchical_imitation_2026-08-10/` | Rejected route-state experiment implementation. |
| `research/replay_clones/` | Retired replay-clone implementations. |
| `research/cache/full_season_topology_identity_safe_2026-08-10/` | Completed full-season corpus and game checkpoints. |
| `reports/<retired-lane>/` | Raw result files; compact `decision.md` files remain active. |
| `reports/replay_clone_study/{full_matrix_results.json,top50_summary.json,matrix_games.jsonl,quick_validation.json}` | Large replay-clone evidence; narrative reports remain active. |
| `scripts/{analyze_public_replays.py,build_replay_clones.py,run_replay_clone_fidelity.py,run_replay_clone_study.py}` | Runners that only serve archived programs. |
| `reconstructible_python_cache/` | Recoverable Python bytecode moved out of the workspace; it may be deleted permanently. |

The active full-tape scale-up lane and its resumable cache remain under
`research/full_tape_topology_scaleup_2026-08-10/` and
`research/cache/full_tape_topology_scaleup_2026-08-10/` respectively.
`research/public_agents/` also remains active for public-league validation.

`.vendor/` and `research/other_approach_submission_audit_2026-08-10/` were
explicitly excluded from cleanup and were not moved or edited.

Historical reports may still show their original workspace paths. Those paths
are provenance. To reproduce a retired experiment, restore its mirrored files
from the archive first; do not silently redirect production code to the
archive.
