# Exact-backbone / tape-topology correction lane

Date: 2026-08-10  
Status: **DEFER_1500; no production promotion.** No production, distribution,
vendor, data, or documentation path was changed; no external state changed.

## Scope correction

The prior 0/12 result replaces exact v25 after step 239 with a
maintenance-only executor. It therefore rejects only that executor. This lane
requires a complete notebook route for all 719 calls: a graph may select a
complete family, exact prefix/branch/rejoin, or narrow residual, but may not
generate a generic maintenance continuation.

## Engine and exact artifacts

All games used current commit `bded87b0d7879078c726a93a4884d044f79c4eed`,
Python SHA `FB9215C5E21A25243E2D13E75B3D70A79CF7D78FFF150A90F1BB5EACF9BA2BCF`,
JSON SHA `7F196F4AAF9B4E482FBD61BA4BF19F5CEC4DA0F81938ECE756954035A65C0BB5`,
and explicit `townCenterSellInterval=24`. `engine_fingerprint.json` also
confirms the current locked-shed pickup behavior at `(5,4)`. The local engine
base stayed immutable and was patched only in memory.

`extract_exact_artifacts.py` treats notebooks as data, never executes cells,
and accepts only direct `%%writefile`, v25 printed source, or bounded literal
base64/base85+zlib recovery before AST audit. Byte hashes, tape digests, and
overlay composition are retained in `artifacts/artifact_manifest.json`.

| Artifact | Source SHA | 12-game live panel | Safety |
| --- | --- | --- | --- |
| v25 meta reset | `2a66e229…b00473` | 12-0-0, margin +35,771.08 | Fail: one escape each game; one seed-overcommit |
| adaptive farming | `997e6bfc…10f1b6` | 12-0-0, +29,038.08 | Pass |
| zero-to-top meta | `e5cbb6ed…bc248` | 12-0-0, +33,007.67 | Pass |
| preempt H6 | `be5b3713…e4d397` | 12-0-0, +29,052.42 | Pass |

The panel in `exact_artifact_panel.json` is 48 full official-engine games:
Kaito v21, Saiteja 3000, Roman LB950; fresh seeds `731981`, `731983`; both
seats. Each artifact has a deterministic duplicate. No frozen replay is an
opponent. P95 artifact latencies are 0.3843, 0.5230, 0.6647, and 0.5325 ms.

This supports complete notebook backbones as an efficacy mechanism class. It
does not make unsafe v25 promotion-ready or identify a notebook with a Top-50
team.

## Topology and residuals

`tape_topology.json` only uses target-player actions and public target-player
observations. It reconfirms F01 support 45/50 and a 33/50 exact unit tape, but
every Top-50 full and market tape is singleton. Adaptive and preempt H6 have
the same full 719-turn tape; they are not independent samples. V25 and
zero-to-top have an exact 161-turn full-action prefix (162 unit turns), then
branch. This is an untested complete-tape topology candidate already exposed
by existing artifacts.

`residual_ablation.json` evaluates fresh seeds `731987` and `731991`, both
seats, and all three live executable opponent families against exact same-seed
same-seat v25. Required gate: zero safety/validity faults, deterministic,
>=8/12 positive deltas, and positive mean delta per family.

| Residual | Scope | Result |
| --- | --- | --- |
| adaptive terminal | only steps 716-718 on v25 action; no adaptive tape | 7/12 positive, mean +17.58; fails inherited safety and 8/12 |
| local P0 feed | at most adjacent move then FEED; no planner/PLANT/BUY_LAND/market | 0/12 positive, mean -124,111.58; Roman still escapes |

Both were deterministic (p95 0.3706 and 0.4679 ms). `v25_escape_audit.json`
records the P0 trigger at step 551: a cow at `(7,4)` had
`consecutive_unfed=1`, while its hand issued `CARE` without wheat. The repair
removes the old escape against Kaito/Saiteja but destroys value through actor
cursor incompatibility. It rejects that residual, not all complete tape branch
or rejoin mechanisms.

## Decision

**A. Backbone effect:** supported: three safe full artifacts and one
unsafe-but-high-margin v25 backbone won all live panel games. V25 itself fails
the lexicographic safety gate.

**B. Residual increment:** rejected: terminal liquidation is insufficient;
local P0 feed has severe compatibility failure.

**C. 1,500 replays:** **defer; do not download now.** The old 0/12 cannot
support a broad no-scale claim. The current 50 and four exact artifacts already
give a cheaper untested 161-turn branch and falsify two residuals. Scale only
after a predeclared complete-tape branch/rejoin passes safety and a fresh
paired-win gate, or a support calculation shows Top-50 cannot answer it.

**D. Maintenance-only conclusion:** retain: its step-240 takeover fails
full-context safety/efficacy and bounded safety is not productive continuation.
Withdraw: any interpretation that it rejects exact backbones, complete-tape
topology, or future scaling for this corrected formulation.

## Reproduction

```powershell
$env:PYTHONPATH=(Resolve-Path '.vendor\kaggle-environments').Path
$env:TF_CPP_MIN_LOG_LEVEL='3'
python -m compileall -q research\exact_backbone_correction_2026-08-10
python -m unittest discover -s research\exact_backbone_correction_2026-08-10\tests -v
python research\exact_backbone_correction_2026-08-10\extract_exact_artifacts.py
python research\exact_backbone_correction_2026-08-10\fingerprint_engine.py --output reports\exact_backbone_correction_2026-08-10\engine_fingerprint.json
python research\exact_backbone_correction_2026-08-10\analyze_tape_topology.py --output reports\exact_backbone_correction_2026-08-10\tape_topology.json
python research\exact_backbone_correction_2026-08-10\run_exact_artifact_panel.py --output reports\exact_backbone_correction_2026-08-10\exact_artifact_panel.json
python research\exact_backbone_correction_2026-08-10\run_residual_ablation.py --output reports\exact_backbone_correction_2026-08-10\residual_ablation.json
```

All losing residual, escape-audit, and prior maintenance-only evidence remains
retained. Nothing in this lane is packaged for production.

## User-authorized staged scale-up addendum (2026-08-10)

The prior **DEFER_1500** wording is superseded by the user's explicit
authorization: **PROCEED_STAGED_TO_1500**. This is authorization to build the
isolated, streaming full-tape topology corpus; it is not production promotion
or permission to submit to Kaggle. The active record is
`reports/full_tape_topology_scaleup_2026-08-10/decision.md`.

The first staged results retain the correction lane's safety/effect gates:
v25-to-zero's verified 161-turn full-tape branch was compatible and safe but
failed fresh efficacy; a two-independent-team complete raw-tape candidate also
failed safety and efficacy. These failures reject those candidates, not corpus
growth. The corpus has already exposed broad common-prefix/branch support and
family-specific market variation that the former Top-50 snapshot could not
measure. Resume collection from the recorded API checkpoint after its
rate-limit backoff; do not claim 1,500 until the manifest has 1,500 eligible
team/submission representatives.
