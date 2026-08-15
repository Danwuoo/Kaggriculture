# E2 development and formal boundary runbook

This runbook authorizes development verification only. It deliberately contains
no executable fresh seed and no formal launch command.

## Development preflight

From the repository root:

```powershell
git status -sb
git rev-parse HEAD
python research\main_approach\v27_current_meta\development\build_standalone.py --check
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
python -m unittest research.main_approach.test_development_sources -v
python -m unittest discover -s research\dual_incumbent_topology_search_2026-08-14\async_v2 -p "test_*.py" -v
python -m unittest discover -s research\dual_incumbent_topology_search_2026-08-14\async_v3 -p "test_*.py" -v
```

The E2 implementation must add stable commands for:

- validating `candidate_registry.json` and E1c hashes;
- running the no-op ranking regression;
- reconstructing and materializing both registered candidates;
- running technical-seed parity in both seats;
- comparing worker 1 and worker 4 output;
- injecting scheduler and engine failures;
- producing `development_verification.json` and
  `development_decision.md`.

All development outputs go below a new `e2/artifacts/development/<run-id>/`
directory. Technical seed `811407` is correctness-only; its reward must be
absent from efficacy fields.

## Development final audit

```powershell
python research\main_approach\v27_current_meta\development\build_standalone.py --check
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
python -m unittest research.main_approach.test_development_sources -v
python -m unittest discover -s research\dual_incumbent_topology_search_2026-08-14\async_v2 -p "test_*.py" -v
python -m unittest discover -s research\dual_incumbent_topology_search_2026-08-14\async_v3 -p "test_*.py" -v
python -m json.tool research\dual_incumbent_topology_search_2026-08-14\e2\candidate_registry.json > $null
python -m json.tool research\dual_incumbent_topology_search_2026-08-14\e2\protocol_template.json > $null
git diff --check
git status -sb
```

Stop if the decision is not `READY_FOR_E2_S1`.

## Later formal E2 S1 boundary

Only after a new explicit user instruction to start E2 S1:

1. rescan repository-wide seed usage;
2. select fresh seeds that do not appear in any retained artifact;
3. replace the empty seed list in a copied protocol template and set
   `formal_authorized=true` in that copied run protocol;
4. freeze engine/configuration, controls, candidates, selectors, opponents,
   seats, job list, and every file/canonical hash;
5. run a dry preflight and verify the exact candidate count and seed tier;
6. launch with stdout/stderr redirection and record PID, run ID, manifest hash,
   registry hash, and shard paths;
7. after successful launch, do not poll, tail, sleep, wait, or monitor until the
   user later requests a read-only audit.

The initial S1 opponent block must include Kaito v21, the other active
incumbent, Roman, and Saiteja in both seats. Results remain lane-relative and
must never be pooled. Boatlee evaluates the fixed finalist against its own
control. v27 evaluates each frozen selector against its own control; the
always-on probe is retained only as a diagnostic comparator.

Infrastructure failure produces no efficacy result and unlocks no later tier.
