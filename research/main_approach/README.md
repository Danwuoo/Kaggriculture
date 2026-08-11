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
| `v27_current_meta` | Fixed public-route baseline | HIRE4-derived v27 action tape with actor-local weed repair and market SELL-slot ranking | Moved unchanged from `scripts/other appoach/original/main.py` |
| `v27_current_meta_safety_guarded` | Safety-guarded fixed public route | Adds a same-turn seed ledger and fresh-crop watering protection to the v27 route | Moved unchanged from `scripts/other appoach/main.py` |
| `boatlee_v16_rc2_market_relay` | Market-relay livestock route | Boatlee V16-RC2 high-output route with livestock conversion, wool control, and a guarded three-turn FERTILIZER relay | Imported from the uploaded `submission.tar.gz` |

## Working rules

- Treat the three agents as independently tuned strategy lines; do not collapse
  their constants or tapes into a shared implementation without a comparative
  experiment.
- Keep each `main.py` runnable as a standalone Kaggle entrypoint exposing
  `agent(obs)`.
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
