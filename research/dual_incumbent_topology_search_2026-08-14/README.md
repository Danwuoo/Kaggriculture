# Dual-incumbent event-linked topology search

## 2026-08-14 scope correction

The original S1 surface below is retained as provenance but is superseded for
future search design.  It evaluated only eight ninth-cow structural roots per
lane and did not express the requested coupled search across `_LEGACY_ACTIONS`
blocks and market/runtime constants.  Do not unlock S2 from that run.

The active corrected development surface is [`async_v2/`](async_v2/README.md):
a lane-isolated, population-based search over multiple bounded route blocks,
public-market genes, and v27/Boatlee-owned runtime constants in the same
genome.  See `async_v2/scope_correction.md` for the consumed-seed boundary.

Date: 2026-08-14

This lane develops a resumable, exact-engine searcher for bounded ninth-cow
topology patches on the two active incumbents:

- `v27_current_meta`
- `boatlee_v16_rc2_market_relay`

The two populations are independent. They share only the offline semantic
genome language, causal-lineage extractor, exact-engine adapter, scheduler,
and analysis code. Route sources, runtime modules, controls, compiled IDs,
candidate artifacts, shards, scores, and decisions are lane-qualified and
must never be pooled.

## Search unit

A candidate is an event-linked set of local windows, each 8--48 turns, rather
than a 719-turn tape or a single-actor 4--8-turn detour. The first family links:

`BUY_ANIMAL(COW) -> shed/carry -> BUILD_PASTURE -> PLACE(COW) ->`
`FEED/CARE/COLLECT_FERTILIZER/HARVEST -> carry/drop/shed ->`
`SELL(MILK/FERTILIZER)`.

The structural roots are removal and shifts `-72, -48, -24, 0, +24, +48,
+72`. Enumeration starts from control, ninth-cow removal, and each coupled
shift root. A child adds exactly one causal factor mutation: maintenance,
reclaimed-labor destination, capacity, shipping/sale timing, public market
exposure, or deliberate abandonment. There is no full Cartesian expansion.

Every compiled window declares a public entry condition, private-own resource
preconditions where necessary, displaced-action accounting, a bounded
fallback, and a legal incumbent rejoin. Missing private seed/resource ledgers
cause abstention to the complete incumbent action. Runtime selection may use
public opponent state but never opponent identity or private-opponent data.

## Authority and evidence

`artifacts/evidence_inventory.json` records what this checkout actually
supports, what is only remembered by the delegation prompt, and what is
missing. Historical Phase 1/Phase 2A/fixed8/selector-v2 names were not found in
the current repository and are not treated as authoritative.

The exact engine is commit
`bded87b0d7879078c726a93a4884d044f79c4eed`, Python blob
`4b78842d0f2d4abf6e318a8248b6306454f5c714`, and configuration blob
`0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8`.

## Development-only boundary

This implementation may run only the already-consumed technical seed `811407`
through D4. It must not execute fresh formal S1--S4 seeds. Formal launch is a
separate, explicit user authorization after a new seed-usage scan and frozen
job manifest.

The command surface is documented in `runbook.md`. `status` is read-only.

## D4 status

Development is `READY_FOR_FORMAL_S1`; see `development_decision.md` and
`artifacts/development_verification.json`. The decision covers correctness and
development readiness only. Formal fresh-seed efficacy remains unexecuted and
unauthorized in this task.
