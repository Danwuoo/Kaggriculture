# Job-value residual discovery decision

Date: 2026-08-13
Decision: **STOP_BEFORE_RUNTIME**

## Result

The approved dual-incumbent discovery gate failed.  No Task 6–10 runtime
module, generated artifact, route, or parameter was changed.

The completed block contains exactly 64 current-engine games: 16 matched
controls and 48 one-window counterfactuals (three per context), using the
frozen controls, two opponent families, two reserved discovery seeds, and both
seats.  All 64 games terminated `DONE`/`DONE`; there were zero exceptions,
malformed actions, hand-alignment failures, market overflows, timeout calls,
or overage exhaustion.  A fresh serial reproduction of all 64 games matched
stored statuses, rewards, action digests, labels, and rejoin metadata.

The exact engine and configuration are the frozen prechange-manifest values:
Python blob `4b78842d0f2d4abf6e318a8248b6306454f5c714`, configuration blob
`0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8`, audited commit
`bded87b0d7879078c726a93a4884d044f79c4eed`.  The machine-readable evidence
is [discovery_games.jsonl](../../research/job_value_residual_2026-08-12/artifacts/discovery_games.jsonl),
[discovery_windows.json](../../research/job_value_residual_2026-08-12/artifacts/discovery_windows.json),
and [discovery_summary.json](../../research/job_value_residual_2026-08-12/artifacts/discovery_summary.json).
Every forced-candidate row also retains its canonical committed per-unit receipt
stream (`step`, receipt index, product, price) and a deterministic full
candidate-trace reference. This preserves later committed orders even when an
earlier same-turn SELL is rejected by the official lockstep market.

## Per-incumbent gate evidence

| Incumbent | Forced candidates | Labels (+ / 0 / -) | Families | Legal rejoin | Selected threshold | Score accuracy / baselines | Gate result |
| --- | ---: | ---: | --- | ---: | ---: | --- | --- |
| v27 current meta | 24 | 0 / 0 / 24 | logistics, maintenance, productive | 16/24 | 200 | 0.00 / 0.00, 0.67, 1.00 | Fail |
| Boatlee V16-RC2 | 24 | 0 / 8 / 16 | logistics, maintenance, productive | 16/24 | 25 | 1.00 / 0.00, 0.50, 1.00 | Fail |

The score baselines are, in order, always-intervene, maintenance-first, and
always-incumbent.  Threshold selection remains recorded even though the gate
failed; it is not an authorization to freeze or deploy either threshold.

Exact failed conditions:

- v27: fewer than four positive labels; score did not strictly exceed
  always-intervene, maintenance-first, or always-incumbent; all eight retained
  logistics windows lacked a qualifying HARVEST/DROP-before-SELL chain.
- Boatlee: fewer than four positive labels; score did not strictly exceed
  always-incumbent; all eight retained logistics windows lacked a qualifying
  HARVEST/DROP-before-SELL chain.
- Both: the logistics candidates aborted on their initial precondition in all
  eight contexts, so each stratum's legal-rejoin rate was only 16/24.  This is
  above the numeric `> 0.5` gate but is adverse mechanism evidence, not a
  reason to relax the logistics rule.

## Retained adverse results

Every row below denotes two retained adverse games, one for each seat, whose
terminal margin deltas were identical.  Thus the first table covers all 24
negative v27 candidate games; the second covers all 16 negative Boatlee games.
All 16 neutral-but-invalid/aborted logistics rows are listed separately.

| Incumbent | Candidate / family | Opponent | Seed | Seats | Transition | Margin delta |
| --- | --- | --- | ---: | --- | --- | ---: |
| v27 | `0012c21e45271daf80f082de` maintenance | other incumbent | 93687444 | 0,1 | L→L | -240 |
| v27 | `003b5186d91c1f0d6c7ae72c` productive | other incumbent | 93687444 | 0,1 | L→L | -335 |
| v27 | `0012c21e45271daf80f082de` maintenance | other incumbent | 65365230 | 0,1 | L→L | -276 |
| v27 | `003b5186d91c1f0d6c7ae72c` productive | other incumbent | 65365230 | 0,1 | L→L | -745 |
| v27 | `0012c21e45271daf80f082de` maintenance | Kaito v21 | 93687444 | 0,1 | W→W | -245 |
| v27 | `003b5186d91c1f0d6c7ae72c` productive | Kaito v21 | 93687444 | 0,1 | W→W | -292 |
| v27 | `0012c21e45271daf80f082de` maintenance | Kaito v21 | 65365230 | 0,1 | W→W | -285 |
| v27 | `003b5186d91c1f0d6c7ae72c` productive | Kaito v21 | 65365230 | 0,1 | W→W | -550 |
| v27 | `0007cc4f66a868a617244513` logistics (aborted) | other incumbent | 93687444 | 0,1 | L→L | -377 |
| v27 | `0007cc4f66a868a617244513` logistics (aborted) | other incumbent | 65365230 | 0,1 | L→L | -321 |
| v27 | `0007cc4f66a868a617244513` logistics (aborted) | Kaito v21 | 93687444 | 0,1 | W→W | -569 |
| v27 | `0007cc4f66a868a617244513` logistics (aborted) | Kaito v21 | 65365230 | 0,1 | W→W | -411 |
| Boatlee | `000263fc893b40d79a65d7f8` maintenance | other incumbent | 93687444 | 0,1 | W→L | -2,802 |
| Boatlee | `001a575172c1302e2011cd99` maintenance | other incumbent | 65365230 | 0,1 | W→L | -13,292 |
| Boatlee | `00486fa4e3003dd27c285187` productive | other incumbent | 93687444 | 0,1 | W→W | -40 |
| Boatlee | `00486fa4e3003dd27c285187` productive | other incumbent | 65365230 | 0,1 | W→W | -46 |
| Boatlee | `000263fc893b40d79a65d7f8` maintenance | Kaito v21 | 93687444 | 0,1 | W→W | -1,653 |
| Boatlee | `001a575172c1302e2011cd99` maintenance | Kaito v21 | 65365230 | 0,1 | W→W | -9,393 |
| Boatlee | `00486fa4e3003dd27c285187` productive | Kaito v21 | 93687444 | 0,1 | W→W | -40 |
| Boatlee | `00486fa4e3003dd27c285187` productive | Kaito v21 | 65365230 | 0,1 | W→W | -47 |

The eight Boatlee logistics windows and eight v27 logistics windows each
aborted as `precondition_failed`; Boatlee's resulting margin delta was 0 in
every seat/context and v27's values are the four paired rows listed above.
Their 24/48 effects were respectively `0/0` for Boatlee and unknown for v27;
none is a usable positive counterfactual label.  In addition, the only
non-unknown productive ledger observations on Boatlee had disagreeing signs
(`+50` at 24 turns and `-25` at 48 turns), so the conservative rule correctly
abstains rather than treating a favorable first horizon as support.

## Interpretation

The data falsify this first local job-window surface.  Forced maintenance and
productive detours were consistently harmful, while logistics did not establish
a legal coupled delivery-and-sale intervention.  The result therefore supports
neither the claimed speed advantage nor a replacement market-timing overlay:
within these two incumbent routes, local acceleration mostly removes work that
the incumbent later needs, rather than revealing slack that can be converted
into score.

No pooled or single-incumbent continuation is permitted.  Future work must use
a distinct mechanism and a newly predeclared protocol; rerunning this market or
one-window lane with looser labels, a different threshold, or identity-based
opponent handling would repeat the rejected experiment.
