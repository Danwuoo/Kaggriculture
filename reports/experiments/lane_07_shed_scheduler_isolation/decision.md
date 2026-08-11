# Lane 07 — current-engine all-four center-shed scheduler ablation

Decision: Pilot failed its continuation gate; the experiment stopped as predeclared.

## Scope and provenance

This is a one-factor scheduler experiment. Both variants retain the current-engine town demand, duplicate-shop accounting, locked-center shed legality, and engine provenance fixes. The treatment is the canonical source copy; the control preserves those fixes while restoring only the old unlocked-only shed-target selection.

Upstream master was rechecked on 2026-08-08 as `bded87b0d7879078c726a93a4884d044f79c4eed` via `git ls-remote`. The retained raw-byte manifest records `kaggriculture.py` `FB9215C5E21A25243E2D13E75B3D70A79CF7D78FFF150A90F1BB5EACF9BA2BCF` and `kaggriculture.json` `7F196F4AAF9B4E482FBD61BA4BF19F5CEC4DA0F81938ECE756954035A65C0BB5`.

## Seed audit and precommitment

The pre-game audit scanned 72 retained Markdown/JSON evidence files (excluding engine snapshots and this new lane). It found none of the selected seeds before this lane: `{'51011': False, '51031': False, '51047': False, '51059': False, '51071': False}`. The historical confirmation seeds 1009, 2029, 3049, and 4099 were found only in the retained confirmation evidence.

Predeclared protocol: Stage 0 smoke seed `51071`; Stage 1 pilot seed `51011`; reserved Stage 2 seeds `[51031, 51047, 51059]`; opponents `['roman_lb950', 'kaito_v20']`; both seats; variants control and treatment. No new opponent or seed was added after any result.

## Mechanical isolation

Treatment source SHA-256: `a3d5822e03f3283b6ff4d0dd4ffadab676a7627e45c56f619bf422ffa02b38e1`; canonical source SHA-256: `a3d5822e03f3283b6ff4d0dd4ffadab676a7627e45c56f619bf422ffa02b38e1`; control source SHA-256: `02579e544bed897b67e0a49ba5e8c584c6fb011b3cdce5a30fef503ea01207ef`. Treatment was byte-identical to canonical: `True`. Control matched canonical in every non-scheduler file: `True`. The only differing file was `['scheduler.py']`.

```diff
--- control/scheduler.py
+++ treatment/scheduler.py
@@ -77,7 +77,7 @@
         crop_layout = desired_crops(state, macro)
         # Current engine resolves shed logistics before rejecting a LOCKED
         # center tile, so each of the four inner access tiles is usable.
-        usable_shed = tuple(pos for pos in shed_tiles(state.size) if state.tile(pos) != "LOCKED")
+        usable_shed = tuple(shed_tiles(state.size))
 
         # Existing assets always generate maintenance jobs, independent of the
         # current economic target. This is the safety backbone of closed loop.
```

Each game ran in a fresh Python child process, which imported exactly one archive-root variant. The process-isolated probes imported both variants, returned schema-valid actions, and verified the control target `[(4,4)]` versus the treatment target `[(4,4),(5,4),(4,5),(5,5)]`.

## Stage 0 correctness and isolation

Stage 0 pass: `True`. Both variants completed two identical 720-step deterministic replays against `starter`; all completed states were `DONE`. Stage-0 safety violations: `[]`.

The paired unit probes covered current upstream semantics: a flat town-center tick once per 24 turns, duplicate shop instances consuming independently, and locked-center `PICKUP`/`DROP`/shed-directed `PLACE` while locked field mutation remains a no-op.

## Executed matched block

Executed stage: `stage_1_pilot`. Evaluation games: `8`; matched pairs: `4`. Evaluation safety passed: `True`. Violations: `[]`.

| Variant | Games | Wins | Mean margin | Moves | Productive | Moves/productive | PICKUP total/mean | DROP total/mean | p95 mean / max call ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| control | 4 | 0 | -38,297.500 | 18872 | 7306 | 2.583 | 2420/1.678 | 9826/8.081 | 2.809/113.059 |
| treatment | 4 | 0 | -40,252.750 | 18930 | 7282 | 2.600 | 2378/1.658 | 10108/8.326 | 2.774/79.186 |

### Raw matched pairs

| Opponent | Seed | Seat | Control reward | Treatment reward | Control margin | Treatment margin | Terminal Δ | Margin Δ | Higher margin |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| kaito_v20 | 51011 | 0 | 43,349.000 | 42,136.000 | -69,888.000 | -74,659.000 | -1,213.000 | -4,771.000 | control |
| kaito_v20 | 51011 | 1 | 43,632.000 | 42,174.000 | -70,802.000 | -72,641.000 | -1,458.000 | -1,839.000 | control |
| roman_lb950 | 51011 | 0 | 65,481.000 | 65,497.000 | -6,059.000 | -7,379.000 | 16.000 | -1,320.000 | control |
| roman_lb950 | 51011 | 1 | 65,369.000 | 65,516.000 | -6,441.000 | -6,332.000 | 147.000 | 109.000 | treatment |

### Paired, opponent, and seed summaries

| Group | Pairs | Treatment higher | Control higher | Ties | Mean terminal Δ | Median terminal Δ | Mean margin Δ | Median margin Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Overall | 4 | 1 | 3 | 0 | -627.000 | -598.500 | -1,955.250 | -1,579.500 |
| Opponent: kaito_v20 | 2 | 0 | 2 | 0 | -1,335.500 | -1,335.500 | -3,305.000 | -3,305.000 |
| Opponent: roman_lb950 | 2 | 1 | 1 | 0 | 81.500 | 81.500 | -605.500 | -605.500 |
| Seed: 51011 | 4 | 1 | 3 | 0 | -627.000 | -598.500 | -1,955.250 | -1,579.500 |

## Stage decision

Pilot safety gates passed: `True`. Treatment had higher match margin in `1/4` pairs; mean paired margin delta was `-1,955.250`. Moves/productive changed from `2.583` to `2.600` (-0.638%). Signal A: `False`. Signal B: `False`. Continue to Stage 2: `False`.

Recommendation: Keep the canonical current-engine scheduler untouched; do not promote or revert it on this small pilot.

## Reproduction commands

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m compileall -q experiments\lane_07_shed_scheduler_isolation\control experiments\lane_07_shed_scheduler_isolation\treatment experiments\lane_07_shed_scheduler_isolation\tests
python -m unittest discover -s experiments\lane_07_shed_scheduler_isolation\tests -v
python experiments\lane_07_shed_scheduler_isolation\run_ablation.py --stage smoke --output reports\experiments\lane_07_shed_scheduler_isolation\stage0_smoke.json
python experiments\lane_07_shed_scheduler_isolation\run_ablation.py --stage pilot --stage0 reports\experiments\lane_07_shed_scheduler_isolation\stage0_smoke.json --output reports\experiments\lane_07_shed_scheduler_isolation\evidence.json
python experiments\lane_07_shed_scheduler_isolation\render_report.py --evidence reports\experiments\lane_07_shed_scheduler_isolation\evidence.json --output reports\experiments\lane_07_shed_scheduler_isolation\decision.md
```

No canonical submission file, archive, vendor/data/docs file, or Kaggle submission was changed by this lane.
