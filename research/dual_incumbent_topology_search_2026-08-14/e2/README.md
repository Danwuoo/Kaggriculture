# E2 topology validation authority

Status: `READY_FOR_E2_S2_FRESH_CONFIRMATION` (fresh confirmation is not authorized)

Start with `research_summary.md` for the consolidated development, S1, S2,
remediation, seed-consumption, and technical-package outcome. The documents
below remain the gate-specific authority.

## Current formal and remediation state

E2 S1 and the Boatlee-only S2 tail tier completed on 2026-08-15. S1 stopped
the v27 selector for no efficacy. S2 rejected always-on Boatlee
`ac_3aa759d7d7fc4a409c409326` because its positive mean depended on one Roman
outlier and retained a repeatable Roman/seat-sensitive downside.

The user then authorized remediation development. Atomic consumed-seed
diagnostics rejected the step-240 component and retained the step-241
fertilizer branch behind one frozen public-state selector,
`e2boatlee_7f591d609cf14d89e6aa1599`. Exact diagnostic validation is 36 positive,
12 incumbent fallbacks, and zero negative contexts. See
`remediation_candidate_registry.json`, `remediation_verification.json`, and
`remediation_decision.md`.

S1/S2 formal fresh seeds have been executed and are now consumed. Remediation
selected and executed no new fresh seed. A separate user authorization is
required before selecting or executing fresh confirmation seeds. No later
fresh tier has been executed.

The user separately authorized technical packaging of the frozen public
selector and the step-241-only diagnostic comparator. They are retained at
`submission/e2_boatlee_public_selector/main.py` and
`submission/e2_boatlee_step_241_only/main.py`. Both passed isolated import,
both-seat correctness, and user-authorized Kaggle server-runtime smoke checks.
The initial packages exposed `agent` but lacked Kaggle's required
`_kaggle_submission_entrypoint`; the deterministic builder now preserves the
frozen strategy bytes and appends only that adapter. The repaired validation
episodes finished `DONE/DONE` with 690 non-pass actions per seat. Packaging and
server execution are not promotion evidence. The step-241-only artifact
retains the known Roman tail and is diagnostic-only. See
`submission_server_verification.json` for submission and replay hashes.

## User-authorized remediation amendment

After the first development verification proved that the exact v27 probe must
commit at an invariant step-0 public state, the user authorized a delayed
public-state intervention. The exact registered probe remains a diagnostic
comparator and is not mutated. The E2 S1 selector candidate is instead the new
lane-local candidate in `development_candidate_registry.json`.

The delayed selector makes one decision at step 494, may remove only the
incumbent `BUY_PRODUCT WHEAT 2` order, and rejoins at step 495. It uses only
public wheat price/inventory and public observation completeness. Its technical
thresholds exercise both branches on correctness seed `811407`; those rewards
are not efficacy evidence. E2 S1 is required to acquire fresh labels for this
new intervention. This amendment does not authorize fresh-seed selection or an
S1 launch.

E2 is a new versioned development and validation lane. It consumes the frozen
E1c decision but does not resume the E1c evolutionary population or widen its
search surface. Its purpose is to turn the two lane-specific E1c findings into
the smallest discriminating fresh-holdout experiment:

- Boatlee: validate one fixed, attributable market-route finalist;
- v27: develop and validate a public-state selector around a high-upside,
  high-downside market topology.

The historical S1/S2 fresh seeds are retained only in their frozen formal run
roots. Current remediation work may use them for diagnostics, never for a new
efficacy claim.

## Required reading

Read in this order before E2 work:

1. repository-root `AGENTS.md` and its Required Reading;
2. `research/main_approach/README.md`;
3. both active incumbents' `development/README.md` files and relevant modules;
4. `../async_v3/README.md`, `../async_v3/e1c_decision.md`, and the committed E1c
   machine summary;
5. this file;
6. `candidate_registry.json`;
7. `implementation_plan.md`;
8. `development_acceptance_contract.md`;
9. `runbook.md` and `protocol_template.json`;
10. `research_summary.md` and the decision record for the stage being
    extended or challenged.

## Fixed candidate roles

The two lanes remain independent and may not share controls, scores, caches,
compiled candidates, or promotion decisions.

- `boatlee_v16_rc2_market_relay`:
  `ac_3aa759d7d7fc4a409c409326` is the fixed E2 finalist.
- `v27_current_meta`:
  `ac_46448f767f398cc4ce8047d3` is a diagnostic probe and selector branch, not an
  always-on finalist.
- After the user-authorized amendment, the exact probe remains diagnostic and
  the delayed candidate `e2v27_8b3ebcb128a4f4709ea94ce3` is the sole frozen
  v27 E2 S1 selector candidate. It carries no pre-S1 efficacy claim.
- `ac_bad79e4d71965c86b6b351a1` is a required no-op regression counterexample
  and must never enter an efficacy frontier.

## Development boundary

E2 development may use technical seed `811407` for correctness, effective
change classification, receipts, state/action digests, and standalone parity.
Technical rewards must not enter efficacy scoring. Existing consumed E1 seeds
may be read from frozen artifacts for feature and label analysis but must not
be rerun unless a later contract explicitly authorizes it.

Development ends with exactly one decision:

- `READY_FOR_E2_S1`; or
- `E2_DEVELOPMENT_REMEDIATION_REQUIRED`.

Neither decision launches E2. A later explicit user instruction must authorize
the fresh-seed preflight and launch.
