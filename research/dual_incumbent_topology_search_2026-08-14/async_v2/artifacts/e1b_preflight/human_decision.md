# Async E1b technical development decision

**READY_FOR_E1B_PREFLIGHT**

This is a technical-only preflight result. It does not launch E1b,
re-execute retained E1 seeds, authorize E2, or claim strategy efficacy.

## Evidence

- Retained E1 audit: 4096 jobs, 235 unique lane-genomes, 36 no-op, 199 behavior-changing.
- Static/technical topology capacity: {'v27_current_meta': 1500, 'boatlee_v16_rc2_market_relay': 1500} unique behavior-changing phenotypes per lane.
- Windows spawn scheduler/cache/checkpoint/failure audit: pass=true.
- Technical smoke: seed 811407 only, 64 complete jobs; all finalists both-seat parity=true.
- 15-worker process-tree CPU: mean=37.732%, median=42.478%, p95=59.200%, peak=62.389%; overall throughput=0.604081 candidate-context jobs/s.
- Formal/fresh seeds executed=false; retained E1 seeds re-executed=false; E2 games executed=false.

## Boundary

The progressive E1b protocol remains non-executable. A new explicit
authorization is required before the consumed E1 small screen or any
later stage is run.
