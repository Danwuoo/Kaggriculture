# Family 2 Stage 1 completion report

Status: **COMPLETE**. The isolated Search Hybrid substrate passed the Stage 1 correctness gate; it is not a promotion candidate.

## Outcome

Frozen source `60270e2f3206cf3bbbd7bbd01666b1db8d0bce2cb4ca7d47960cbf19c2c29cf7` completed **320** current-official-engine games (32 seeds × 2 seats × 5 opponents). Result: **0-0-320**, Wilson 95% [0.0000%, 1.1862%]. Paired result: **0-0-160** over 160 opponent/seed pairs, Wilson 95% [0.0000%, 2.3446%], seed-cluster bootstrap [0.0000%, 0.0000%].

Safety and schema take priority over the 0% win rate. All games ended with both players `DONE`; candidate malformed actions, timeouts, runtime exceptions, animal escapes, fresh-crop deaths, shed overflow states, semantic silent no-ops, seed overcommit, market-list overflow, overflow discard, and audit errors were all zero.

## Implementation

- `candidate/search_planner.py`: 64-option deterministic broad macro generator/ranker over livestock mix, all crop cohorts, topology, hands, land, cash/feed/shed reserves, shipment timing/fraction, and public opponent pressure. Former ceilings appear only in priors; safety realization is resource-dependent.
- `candidate/daily_model.py`: compressed day-boundary transition with per-unit market pricing, ordered finance, atomic seeds, feed/care, production, shed capacity, overflow, and conservation ledger.
- `candidate/market.py`: exact price curve, P0 lifetime feed reservation, dynamically wheat-supported expansion, ordered shipment and capital decisions.
- `candidate/strategy.py`: broad four-quadrant animal/crop topology. The inherited P0–P5 scheduler, Level 0/1/2 degradation, and final legality projector remain authoritative.
- Offline runner/tests cover differential conservation, current locked-shed semantics, full replay safety, semantic no-op audit, Wilson and seed-cluster bootstrap statistics, determinism, latency, packaging, and control isolation.

## Competitive evidence

| Opponent | Seat 0 W-T-L | Seat 1 W-T-L | Overall W-T-L | Wilson 95% | Seed bootstrap 95% | Candidate reward median [min,max] | Opponent reward median [min,max] | Diff median / p10 [min,max] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| kaito_v20 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 12764 [5108,16784] | 150092 [56699,176903] | -136237 / -161207.2 [-166957,-49950] |
| kaito_v21 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 6695 [238,16055] | 141934 [44388,186964] | -134546 / -167534.0 [-178673,-36504] |
| roman_lb950 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 3222 [182,8148] | 93614 [69830,119172] | -91268 / -106017.9 [-117171,-66793] |
| saiteja_2600 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 9569 [5773,20051] | 157264 [68605,188253] | -144184 / -166815.1 [-180503,-57800] |
| saiteja_3000 | 0-0-32 | 0-0-32 | 0-0-64 | [0.00%, 5.66%] | [0.00%, 0.00%] | 12674 [3953,18832] | 141215 [85454,160222] | -127038 / -140100.7 [-155365,-78055] |

Overall difference distribution: mean -122027.6, median -124908.0, lower decile -160900.3, range [-180503, -36504]. Every development seed and all 320 losses are retained in the official JSON.

## Fidelity, failures, and regressions

The engine differential used 600 component cases. Market and crop boundaries were exact; 34 aggregate animal compression mismatches are retained. Three official rollout games produced 87 day comparisons; money MAE was 683.494. These errors make the model an unproven one-day ranker, not an engine substitute.

The first 80-game smoke (`4314434f07085479dbcdacd9110788183d13e9d0dfc3ea0a14e0f8e1f6d83a1c`) exposed 280 animal escapes and 8 caught runtime exceptions. The first 320-game frozen attempt (`b87a59d32c264030fe2b36aa05b149a47b787f80ccdb8100b835140f15e468cc`) retained 25 terminal animal escapes. Root causes were reserve-blocked P0 feed, non-orderable score ties, expansion without sustainable wheat, and terminal feed depletion. Regression seeds 0, 23, 100007, and 100029 were added. A later upstream town rebalance changed the center interval and shop sampling before delivery; the complete `bbcdd460` snapshot was retained and the 80/320 matrices, fidelity, determinism, tests, and package gate were rerun on `bded87b0d7879078c726a93a4884d044f79c4eed` with zero candidate failures.

## Reproducibility and isolation

Latency over 230080 calls: p50 1.917 ms, p95 9.686 ms, p99 40.305 ms, max 159.159 ms. Same-seed self-play reproduced reward and per-seat action digests exactly.

Family archive: `experiments/family_2_search/artifacts/family_2_stage_1_candidate.tar.gz`, 24412 bytes, SHA-256 `f46ff6bb9301c136df0ac4ef4799355bf9241b6b60a5e869a3f7a256cadff391`. It has archive-root `main.py`, imports after extraction, and completed the extracted seed-424242 game with statuses ['DONE', 'DONE']. Runtime uses no networking, subprocesses, multiprocessing, heavy ML runtime, or file writes.

Validation passed compilation, 18 control tests, 10 Family 2 tests, current-engine games, and before/after hash isolation. `submission/` and canonical `dist/submission.tar.gz` match their recorded baselines.

## Provenance, decision, and remaining uncertainty

Current upstream engine commit `bded87b0d7879078c726a93a4884d044f79c4eed` (Apache-2.0) is authoritative; its engine SHA-256 is recorded in evidence. Five public notebook agents are evaluation-only; exact notebook/extracted hashes are in `research/public_agents/extraction_manifest.json`. Their kernel metadata declares no explicit content license, so none of their code is packaged or copied into this candidate.

**Stage 2 entry decision: DO_NOT_ENTER_STAGE2.** Stage 1 is complete under no-early-kill, but 0–0–320 provides no efficacy signal. Still unproven: competitive value, a multi-day optimizer, accurate low-money rollout value, Stage 2 validation, Stage 3 holdout, final selection, and promotion.

Reproduction commands and evidence paths are in `experiments/family_2_search/README.md`. Stage 3 holdout seeds 300000–300127 were not read or used.
