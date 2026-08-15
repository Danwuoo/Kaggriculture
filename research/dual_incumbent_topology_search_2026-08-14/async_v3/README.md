# Async V3 / E1c Contract Authority

Status: `E1C_COMPLETE_E2_HANDOFF`

This directory is the implemented versioned lane for the E1c expansion of the
dual-incumbent asynchronous topology searcher. The retained-seed E1c run
`async_e1c_20260815_expanded_v1` completed on 2026-08-15. It used only the
already-consumed seeds `81426017` and `81426029`; therefore
`formal_fresh_seeds_executed=false`. `async_v2/`, all E1b artifacts, and the E1c
run are frozen evidence and must not be edited, regenerated, normalized, or
reused as writable cache.

Read `e1c_decision.md` for the human decision and `../e2/README.md` for the next
development boundary. This directory does not authorize an E2 game or any
fresh seed.

Read before implementation, in this order:

1. the repository-root `AGENTS.md` and its Required Reading;
2. this file;
3. `implementation_plan.md`;
4. `development_acceptance_contract.md`;
5. `fixtures/e1b_regression_fixtures.json`;
6. `runbook.md`;
7. `e1c_decision.md`;
8. `../e2/README.md` when performing E2 work;
9. the relevant Async v2 source modules, strictly as committed provenance.

## Objective

E1c must search coherent combinations of route topology, ordered market
actions, quantities, public guards, and lane-owned runtime constants.  It must
not merely run more generations over the Async v2 proposal distribution.

The new searchable surface must directly express combinations such as:

- `HIRE`, `BUY_LAND`, `BUY_ANIMAL`, `BUY_SEED`, `BUY_PRODUCT`, and `SELL`;
- market-order insertion, removal, replacement, quantity change, and queue
  movement at an event-linked step;
- a public price/inventory guard on a sale or purchase motif;
- a lane-owned runtime constant perturbation that is proven to reach a live
  runtime decision;
- a bounded 8--48 turn route block coupled to those market and constant edits.

The two incumbents remain independent compiler and evaluation strata:

- `v27_current_meta`
- `boatlee_v16_rc2_market_relay`

No editable genome, compiled candidate, cache, score, decision, or artifact may
cross lanes.  Shared schema and offline algorithms are allowed; IDs and outputs
must remain lane-specific.

## E1c roots

The initial population must include lane-local control and the reconstructable
E1b anchors in the regression fixture.  Mutations then expand outward by one
causal edit at a time.

- Boatlee root: the steps 237--244 market window whose effective orders occur
  at steps 240 and 241.
- v27 root: the step-0 ordered market sequence with `BUY_PRODUCT WHEAT 11`.
- Boatlee steps 266--273 and v27 steps 491--498 are removable ablations, not
  mandatory parts of either root.

## Historical E1c seed boundary

Development used technical seed `811407` only for correctness, observed
behavior, receipts, digest, and parity checks. Its rewards did not enter
efficacy ranking. The later authorized E1c run used only the already-consumed
seeds `81426017` and `81426029`. The E2 boundary is now authoritative in
`../e2/README.md`; no E2 or fresh seed is authorized here.

## Completed deliverable state

The development verification and human development decision recorded
`READY_FOR_E1C_CONSUMED_SEED_RUN`; the separately authorized retained-seed run
then completed. The resulting decision is
`E1C_COMPLETE_PROCEED_TO_E2_DEVELOPMENT`. This authorizes only contract-scoped
E2 development. It does not authorize fresh-seed execution.
