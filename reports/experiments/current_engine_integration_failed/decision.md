# Current-engine canonical integration — 2026-08-08

Status: correctness acceptance and starter/random plumbing passed. The bounded public block completed safely, but it did not establish a competitive benefit from the four-way shed route.

## Provenance and scope

The pre-integration canonical `submission/` was byte-identical, file by file, with [lane_04 control](/C:/Users/wurre/Desktop/Kaggriculture/experiments/lane_04_capital_herd_timing/control): 13 Python files matched and the aggregate source SHA-256 was `75567280fa51f6f6af54f857fd92bf8bc21375c952a9ca65c0d2c9211ae1b9d6`. That fixed copy is the public-confirmation control. The integrated treatment source SHA-256 is `a3d5822e03f3283b6ff4d0dd4ffadab676a7627e45c56f619bf422ffa02b38e1`.

All validation uses Lane 1's raw-byte verified current-engine snapshot, without changing `.vendor`: commit `bded87b0d7879078c726a93a4884d044f79c4eed`; `kaggriculture.py` SHA-256 `FB9215C5E21A25243E2D13E75B3D70A79CF7D78FFF150A90F1BB5EACF9BA2BCF`; `kaggriculture.json` SHA-256 `7F196F4AAF9B4E482FBD61BA4BF19F5CEC4DA0F81938ECE756954035A65C0BB5`. The manifest SHA-256 is `BFAF24011341FFE36958FC7E1B52154EA6B03259FBDCFE95C77438A28490727A`; it is authoritative over any CRLF/text-mode representation.

Only these canonical behavioral changes were integrated:

- [constants.py](/C:/Users/wurre/Desktop/Kaggriculture/submission/constants.py): current-engine provenance.
- [market.py](/C:/Users/wurre/Desktop/Kaggriculture/submission/market.py): flat town-center rate `1/24`, retaining per-instance duplicate shop accounting.
- [rules.py](/C:/Users/wurre/Desktop/Kaggriculture/submission/rules.py): locked inner-center tiles admit only shed `PICKUP`, `DROP`, and shed-directed `PLACE`.
- [scheduler.py](/C:/Users/wurre/Desktop/Kaggriculture/submission/scheduler.py): all four shed-access tiles are logistics targets.

Macro targets, order policy, market thresholds, and scheduler P0–P5 priorities were not changed. `.vendor`, `data`, `docs`, and retired lane evidence were not edited.

The `PLACE` proof is explicit: the locked-tile exception first requires an actual shed-access coordinate. The animal-placement branch still requires a matching structure dictionary, impossible for `"LOCKED"`; only its later shed-transfer branch can run, and it debits the projected unit inventory before crediting the shadow shed. Canonical tests cover locked-center shed transfer, locked non-center rejection, animal `PLACE` returning to shed rather than placing an animal, and `PLANT` projecting to `PASS`.

## Acceptance results

| Gate | Result |
| --- | --- |
| `compileall` and canonical unit tests | Passed; 23/23 tests on bded87b |
| Current-engine self-play | Both `DONE` |
| `starter`, three seeds × both seats | 6/6 wins; both `DONE` |
| `random`, three seeds × both seats | 6/6 wins; both `DONE` |
| Determinism, seed 777 | Equal rewards `[31546.0, 29670.0]`; digest `f5cdf93a…e20424cbc` |
| Safety | All zero: malformed, timeout calls/statuses, escapes, fresh-crop deaths, shed overflow, seed overcommit, and >10 market orders |
| Full episode latency | p50 1.4683 ms; p95 2.12163 ms; p99 2.57583 ms; max 12.17030 ms |
| Build / import smoke | Passed; 13 root Python files |
| Extracted archive, current-engine 720-step game | Both `DONE`, seed 5051 vs starter, 84,731–3,512; zero malformed |

The exact game records, action digests, and all arena safety counters are in [arena_results.json](/C:/Users/wurre/Desktop/Kaggriculture/reports/arena_results.json). The extracted-package replay result is in [extracted_current_engine_smoke.json](/C:/Users/wurre/Desktop/Kaggriculture/reports/extracted_current_engine_smoke.json).

## Bounded public confirmation

The retained block is exactly 32 games: four fresh seeds (`1009`, `2029`, `3049`, `4099`) × two seats × `roman_lb950` and `kaito_v20` × control/treatment. All 32 finished `DONE`; there were no runner failures and all candidate safety counters were zero.

| Variant | Games | Wins | Mean margin | Moves | Productive | Moves/productive | PICKUP distance | DROP distance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Control | 16 | 2 | -36,791.81 | 75,420 | 29,227 | 2.58049 | 1.77651 | 8.03162 |
| Treatment | 16 | 2 | -37,083.00 | 75,067 | 29,896 | 2.51094 | 1.58160 | 8.19784 |

Of 16 matched `(opponent, seed, seat)` pairs, treatment had the higher match margin in 5, control in 11, with no ties. Mean treatment-minus-control terminal delta was +138.50 coins, but mean match-margin delta was -291.19. Per-seed clusters and every retained game are in [current_engine_confirmation.json](/C:/Users/wurre/Desktop/Kaggriculture/reports/current_engine_confirmation.json). This is a correctness integration, so the negative small-sample signal does not justify a rollback; it does mean four-way routing must not be described as a proven performance improvement.

## Packaging

[submission.tar.gz](/C:/Users/wurre/Desktop/Kaggriculture/dist/submission.tar.gz) is 17,550 bytes (under 5 MiB), has `main.py` at archive root, excludes tests/replays/cache/venv, and has SHA-256 `36A7E734B6C47BF157CD37D4084B749F98ED19CF032E978AE5EA78BBD89C2A82`.

## Reproduction commands

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m compileall -q submission tests scripts; python -m unittest discover -s tests -v
$env:PYTHONDONTWRITEBYTECODE='1'; $env:TF_CPP_MIN_LOG_LEVEL='3'; python scripts/run_arena.py
$env:PYTHONDONTWRITEBYTECODE='1'; $env:TF_CPP_MIN_LOG_LEVEL='3'; python scripts/run_current_engine_confirmation.py
$env:PYTHONDONTWRITEBYTECODE='1'; python scripts/build_submission.py
$env:PYTHONDONTWRITEBYTECODE='1'; python scripts/run_extracted_current_engine_smoke.py
```

The initial Lane 1 raw-byte transfer once passed through a PowerShell text pipe and changed line endings; this is why all canonical runners now invoke the retained manifest verifier before loading the engine. During this integration, the first duplicate-shop unit-test assertion incorrectly expected an absolute wool inventory after prior town ticks; it was repaired to verify the engine's four-wool duplicate-shop tick delta. An initial streamed confirmation command was stopped after roughly 80 seconds without saved per-game output; profiling then measured Roman alone at 3.46 seconds, control-versus-Roman at 4.94 seconds, and the exact runner path at 4.69 seconds. The one retained 32-game run completed with no runner failure.

Remaining risks: the public block is intentionally small and does not prove a routing performance gain; `.vendor` intentionally remains old, so all engine comparisons must keep using the verified loader; and upstream should be rechecked before treating bded87b as current in a future session. The optional `pyspiel` warning is unrelated to Kaggriculture.
