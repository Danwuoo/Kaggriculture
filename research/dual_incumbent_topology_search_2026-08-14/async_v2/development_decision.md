# Async topology v2 development decision (superseded)

This early technical decision is superseded by
`artifacts/e1b_remediation_v4/human_decision_final.md`.  It does not authorize a formal
run.  The current decision token is `READY_FOR_E1B_PREFLIGHT`.

## Retained early result

The corrected searcher can evolve several route blocks, public-market
policies, and lane-owned constants in one genome.  It does not pool v27
and Boatlee evidence.

### Verification

- Motif library: 554 v27 and 554 Boatlee lane-qualified blocks.
- Compile smoke: {'v27_current_meta': 8, 'boatlee_v16_rc2_market_relay': 8} candidates/lane; {'v27_current_meta': 4, 'boatlee_v16_rc2_market_relay': 4} multi-gene candidates/lane.
- Exact technical search: 64 jobs, 2 generations, seed `811407` only.
- Scheduler audit: worker 1/>1 equality=true, corrupt resume=true, failure injection=true.
- Fast/standalone both-seat parity=true.
- Formal v2 fresh seeds executed=false.

### Efficacy boundary

The small technical search selected the unchanged control in both lanes.
This verifies the search machinery and preservation of negative evidence;
it is not evidence that a stronger strategy has already been found.
The superseded ninth-cow S1 does not unlock S2.

### Known limitations

- Only one consumed technical seed and a 4x2 development population were evaluated.
- Unit-block compatibility is certified against a lane control trace; a
  different public entry position causes bounded incumbent fallback.
- Engine market physics remain exact and immutable.  Search mutates only
  policy thresholds, model weights, order quantities, and timing.
- A new seed scan, protocol, and explicit authorization are required before
  any async-v2 formal search.
