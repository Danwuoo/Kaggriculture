# Family 3 Stage 1 completion report

Status: **COMPLETE**. The isolated Learned Hybrid passed the Stage 1 correctness and reproducibility gate; it is not a Stage 2 candidate.

## Outcome

Frozen source `748971420d87e386aabfaddf81ac4d99ee093ea26e27771de9615e8d980bfd38` completed **320** current-official-engine games (32 seeds x 2 seats x 5 opponents). Result: **0-0-320**, Wilson 95% [0.0000%, 1.1862%]. Paired result: **0-0-160** over 160 opponent/seed pairs, Wilson 95% [0.0000%, 2.3446%], seed-cluster bootstrap [0.0000%, 0.0000%].

All games ended with both players `DONE`; candidate malformed actions, timeouts, runtime exceptions, animal escapes, fresh-crop deaths, shed overflow states, semantic silent no-ops, seed overcommit, market-list overflow, overflow discard, and audit errors were all zero.

## Dataset, representation, and teacher

The official Kaggle daily dataset `kaggle/kaggriculture-episodes-2026-08-07` (dataset ID 11551024, updated 2026-08-08T00:08:38.150000, CC0-1.0) was streamed from a 433,589,878-byte ZIP with SHA-256 `40C9C9C31A5EAB6EC3024E098BD2C2D499A194B1B7D099B3330746F339A5399A`. All 675 episode JSON files (21,445,647,958 uncompressed bytes) and 675 manifest rows produced 40,500 samples over 1350 agent routes.

Episode/route connected-component splitting produced 377 components: 609 train episodes / 875 train routes and 66 validation episodes / 122 validation routes, with zero episode and route overlap. Artifact SHA-256 is `8264d5df55a519a8f2fe8227b68b9c213b5d7d4ec50d138ab6eaacc818ddb25b`; split SHA-256 is `484d0d8916d9654764285e33de9363c7519fe55d579963c3307045f9a7021158`.

The 32-feature pipeline explicitly permits only own private state, shared market/town state, and public opponent farm state. Poison tests prove opponent private shed/seeds/inventories plus identity/account/team fields cannot affect features. Runtime candidate source has no network, subprocess, multiprocessing, heavy ML import, or file-write call.

The offline NumPy linear behavior-cloning teacher used seed 20260807, 240 epochs, learning rate 0.12, and L2 0.001. Validation accuracy was 96.4141%, macro-F1 0.3431, and log loss 0.1304; the training-majority non-neural baseline was 96.2121% (delta +0.2020%). Rebuild hashes match exactly for both model artifact `000b7873373c55ca0fa1788027f86ce42abc7a6cc2c60970218bb2cafcb28953` and generated runtime source `0bfa95dd737de54996b1c249a03b39b14ee9361000a94a717a8cf272eeb75c62`.

The teacher only ranks at most 64 feasible Search Hybrid macro candidates. The inherited P0-P5 scheduler, Level 0/1/2 degradation, deterministic fallback, and legality projector remain final authorities; no model path emits raw actions.

## Competitive evidence

| Opponent | Seat 0 W-T-L | Seat 1 W-T-L | Overall W-T-L | Wilson 95% | Seed bootstrap 95% | Candidate reward median [min,max] | Opponent reward median [min,max] | Diff median / p10 [min,max] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| kaito_v20 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 22240 [8200,33794] | 127576 [53979,166427] | -107957 / -135721.0 [-146152,-41442] |
| kaito_v21 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 15870 [1093,32982] | 140512 [71925,187791] | -126522 / -156932.0 [-184450,-54669] |
| roman_lb950 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 20294 [4282,29701] | 81775 [53177,100560] | -62931 / -77925.6 [-83961,-24113] |
| saiteja_2600 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 21074 [4271,34069] | 136338 [67762,175968] | -111260 / -143117.6 [-163191,-54370] |
| saiteja_3000 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 21018 [10719,31682] | 125544 [53227,153176] | -100706 / -121496.3 [-128855,-39945] |

Overall difference distribution: mean -100234.2, median -104357.5, lower decile -135494.0, range [-184450, -24113]. All 320 losses and all 32 development seeds are retained in `reports/experiments/family_3/stage1_official_320.json`.

## Failures and regression evidence

The first route-component split was rejected and retained: 2 components forced 1 train episode versus 682 validation episodes. The first runner probe retained 14 overflow-discard units. The first formal 320 run retained 3 animal escapes caused by repeated feed pickup; after that repair, a full smoke exposed 3 late-feed escapes caused by cash reserve outranking lifetime feed liability. After the 2026-08-07 data refresh, another complete formal matrix retained 1 fresh-crop death at kaito_v20 seed 100030 seat 0: a carried-animal tie penalty displaced the local P0 water task. Finally, upstream town semantics changed before delivery; the first current-engine smoke retained 4 escapes at kaito_v20 seed 777 seat 0 because six cows had only five wheat and 35 coins near season end. A dynamic physical-feed runway gate fixed optional herd expansion. Both two-seat regressions and the subsequent complete smoke/formal gates have zero candidate events. Regression seeds 100003, 100027, 101, 100030, and 777 are retained, together with the complete 2026-08-06 and `bbcdd460` snapshots.

## Safety, determinism, latency, and package

Latency over 230,080 official candidate calls: p50 1.978 ms, p95 6.798 ms, p99 34.106 ms, max 163.032 ms. Same-seed self-play reproduced rewards and both per-seat action digests exactly.

Family archive: `experiments/family_3_learned/artifacts/family_3_stage_1_candidate.tar.gz`, 29,007 bytes, SHA-256 `5df203d9f41923873456edd8ba233c9c65c81872730be4ed484baeb9b9d37858`. It contains archive-root `main.py`, imports after extraction, and completed the extracted seed-424242 game with statuses ['DONE', 'DONE']. Compilation, 18 control tests, 23 Family 3 tests, source isolation, and canonical archive isolation all passed.

## Decision and remaining uncertainty

**Stage 2 entry decision: DO_NOT_ENTER_STAGE2.** Stage 1 is complete under no-early-kill, but the final match matrix supplies no established competitive efficacy signal. Minority-class validation remains weak (mixed_expansion F1 0.0000; conservative F1 0.3902), the causal value of learned ranking over the search-only parent is unproven, and generalization beyond this daily dataset—published before the final town rebalance—has not been established. Stage 2, Stage 3 holdout, promotion, and final cross-family selection were not performed.

Exact commands, hashes, provenance, and license notes are in `experiments/family_3_learned/README.md` and `PROVENANCE.md`. Holdout seeds 300000-300127 were not read or used.
