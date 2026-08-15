# E2 topology validation authority

Status: `CONTRACT_ONLY_AWAITING_E2_DEVELOPMENT`

E2 is a new versioned development and validation lane. It consumes the frozen
E1c decision but does not resume the E1c evolutionary population or widen its
search surface. Its purpose is to turn the two lane-specific E1c findings into
the smallest discriminating fresh-holdout experiment:

- Boatlee: validate one fixed, attributable market-route finalist;
- v27: develop and validate a public-state selector around a high-upside,
  high-downside market topology.

No E2 fresh seed has been selected or executed. This directory does not
authorize formal E2 execution.

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
9. `runbook.md` and `protocol_template.json`.

## Fixed candidate roles

The two lanes remain independent and may not share controls, scores, caches,
compiled candidates, or promotion decisions.

- `boatlee_v16_rc2_market_relay`:
  `ac_3aa759d7d7fc4a409c409326` is the fixed E2 finalist.
- `v27_current_meta`:
  `ac_46448f767f398cc4ce8047d3` is a diagnostic probe and selector branch, not an
  always-on finalist.
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
