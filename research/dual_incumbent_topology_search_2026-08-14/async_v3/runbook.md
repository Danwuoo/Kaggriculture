# Historical Async V3 / E1c development runbook

This runbook is retained as the development and technical-verification record.
The later retained-seed E1c run completed; see `e1c_decision.md`. For current
work use `../e2/runbook.md`. Nothing in this historical runbook authorizes E2
or a fresh seed.

## Preflight

From the repository root:

```powershell
git status -sb
git rev-parse HEAD
python research\main_approach\v27_current_meta\development\build_standalone.py --check
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
python -m unittest research.main_approach.test_development_sources -v
python -m unittest discover -s research\dual_incumbent_topology_search_2026-08-14\async_v2 -p "test_*.py" -v
```

The implementation must add one v3 command that validates
`fixtures/e1b_regression_fixtures.json` against the frozen source artifacts
without writing them.

## Required development commands

The final implementation must make these stable entrypoints available:

```powershell
python -m unittest discover -s research\dual_incumbent_topology_search_2026-08-14\async_v3 -p "test_*.py" -v
python research\dual_incumbent_topology_search_2026-08-14\async_v3\cli.py verify-fixtures
python research\dual_incumbent_topology_search_2026-08-14\async_v3\cli.py compile-smoke --technical-seed 811407
python research\dual_incumbent_topology_search_2026-08-14\async_v3\verify.py --technical-seed 811407 --workers 1
python research\dual_incumbent_topology_search_2026-08-14\async_v3\verify.py --technical-seed 811407 --workers 4 --compare-workers 1
```

Exact option spelling may be extended, but these commands must remain valid.
All output goes below `async_v3/artifacts/development/` using atomic writes.

## Formal-pipeline dry/mock proof

This exercises the exact same frozen manifest, control-cache, spawned-worker,
score, frontier, checkpoint, and summary plumbing without calling the engine
for an E1c seed.  It is the only formal command permitted during development.

```powershell
python research\dual_incumbent_topology_search_2026-08-14\async_v3\cli.py preflight --output-root research\dual_incumbent_topology_search_2026-08-14\async_v3\artifacts\development\formal_cli_dry_mock_current --proposal-seed 271828 --population 6 --generations 2 --workers 4
python research\dual_incumbent_topology_search_2026-08-14\async_v3\cli.py status --output-root research\dual_incumbent_topology_search_2026-08-14\async_v3\artifacts\development\formal_cli_dry_mock_current
python research\dual_incumbent_topology_search_2026-08-14\async_v3\cli.py run --output-root research\dual_incumbent_topology_search_2026-08-14\async_v3\artifacts\development\formal_cli_dry_mock_current --workers 4 --dry-run
```

`run` without `--dry-run` refuses execution unless a separately authorized
operator supplies the retained-seed execution flag.  This runbook does not
show that flag or any executable E1c seed launch command.

## Final audit

```powershell
python research\main_approach\v27_current_meta\development\build_standalone.py --check
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
python -m unittest research.main_approach.test_development_sources -v
python -m unittest discover -s research\dual_incumbent_topology_search_2026-08-14\async_v2 -p "test_*.py" -v
python -m unittest discover -s research\dual_incumbent_topology_search_2026-08-14\async_v3 -p "test_*.py" -v
git diff --check
git status -sb
```

The development task stops after writing `development_verification.json` and
`development_decision.md`.  It must print no launch command containing an
unregistered seed and must not execute seeds `81426017`, `81426029`, or any E2
seed.

## Historical later E1c boundary

The separately authorized E1c launch subsequently rescanned seed usage, created
a consumed-seed registry, froze controls/engine/configuration/job list, and ran
with 15 workers. It used no fresh seed. The exact completed evidence is frozen
under `artifacts/formal/async_e1c_20260815_expanded_v1/`.
