# Main approaches

This directory is the canonical catalog for the project owner's manually tuned,
standalone Kaggriculture agents. Each approach keeps a self-contained
`main.py` that can be packaged at archive root for isolated evaluation.

These files are research candidates, not the production control. The verified
production implementation remains under `submission/`, and moving an approach
here does not establish safety, efficacy, or promotion readiness.

## Classification

| Approach | Category | Distinguishing mechanism | Provenance |
| --- | --- | --- | --- |
| `v27_current_meta` | Active incumbent | HIRE4-derived v27 action tape with actor-local weed repair and market SELL-slot ranking | Moved unchanged from `scripts/other appoach/original/main.py` |
| `boatlee_v16_rc2_market_relay` | Active incumbent | Boatlee V16-RC2 high-output route with livestock conversion, wool control, and a guarded three-turn FERTILIZER relay | Imported from the uploaded `submission.tar.gz` |
| `v27_current_meta_safety_guarded` | Retained reference | Adds a same-turn seed ledger and fresh-crop watering protection to the v27 route | Moved unchanged from `scripts/other appoach/main.py` |

## Current E2 topology result

The 2026-08-15 E2 program evaluated the two active incumbents separately. The
v27 public selector stopped at S1 because its fresh interventions changed
receipts/public state but produced zero terminal paired-margin and own-bank
change. The unchanged always-on Boatlee E1c block advanced through S1 but was
rejected at S2 because its positive mean depended on one Roman outlier and it
retained a repeatable Roman/seat-sensitive public-market downside.

Boatlee remediation froze one new public-state selector,
`e2boatlee_7f591d609cf14d89e6aa1599`. It observes only public fertilizer price
and inventory at step 240, conditionally applies the exact step-241 fertilizer
branch, and rejoins at step 242. Its consumed-context diagnostics are 36/12/0,
but it has no post-remediation fresh efficacy evidence and is not promoted.

Two user-authorized technical artifacts are retained independently:

| Artifact | Role | Promotion status |
| --- | --- | --- |
| `submission/e2_boatlee_public_selector/main.py` | Frozen candidate for a separately authorized fresh confirmation | Not promoted |
| `submission/e2_boatlee_step_241_only/main.py` | Atomic risk comparator retaining the Roman tail | Diagnostic only |

Both artifacts include the Kaggle server adapter
`_kaggle_submission_entrypoint`. Their repaired, user-authorized server smoke
replays completed `DONE/DONE` with active actions, confirming packaging/runtime
only. They do not supply fresh efficacy or promotion evidence.

See
`research/dual_incumbent_topology_search_2026-08-14/e2/research_summary.md`
for the full stage history, seeds, hashes, evidence map, and next gate.

## Working rules

- Treat v27 and Boatlee as two independently tuned active strategy lines. Keep
  the safety-guarded v27 variant as a reference rather than a third active
  incumbent. Do not collapse their constants or tapes into a shared
  implementation without a comparative experiment.
- Keep each generated `main.py` runnable through local `agent(obs)`. Any file
  packaged for Kaggle must also expose `_kaggle_submission_entrypoint` and be
  verified through that exact adapter.
- Record engine/configuration fingerprints and paired-seat evidence before
  comparing scores or promoting a candidate.
- Preserve the existing audit history in
  `reports/other_approach_submission_audit_2026-08-10/`; its original paths
  are provenance for the two v27 variants.
- Do not package any approach as the production submission unless it separately
  passes the workspace acceptance gates.

## Development sources

The two active high-score lines keep their editable implementation under a
`development/` package. Their 719-turn routes are readable
`route_actions.json` files and their runtime overlays are split by concern.
The sibling `main.py` is generated only as the single-file Kaggle artifact;
edit the development package, then run its `build_standalone.py` and
`--check`. `development_main.py` exposes the same agent directly from the
uncompressed modules for local experiments.

Run the shared source contracts and full current-engine equivalence check with:

```powershell
python -m unittest research.main_approach.test_development_sources -v
python research\main_approach\validate_development.py
```

The full-game validator requires exact equality of rewards, action digests,
schema findings, and safety diagnostics from both seats. Keep the two
development trees independent even when their route data currently matches.
