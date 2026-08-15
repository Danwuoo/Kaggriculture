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

The user-authorized remediation additionally requires validation of
`development_candidate_registry.json` and exact parity for delayed selector
`e2v27_8b3ebcb128a4f4709ea94ce3`. The exact E1c v27 probe remains a diagnostic
artifact. Technical seed `811407` may demonstrate public-feature branch
coverage but supplies no efficacy score.

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

## User-authorized E2 S2 boundary

S1 completed and the attributed decision advances only unchanged Boatlee
`ac_3aa759d7d7fc4a409c409326` to an S2 public-market tail-characterization
tier. The v27 selector stopped for no efficacy and receives no S2 jobs.

Before launch, S2 must:

1. select exactly four new formal-fresh seeds and scan the worktree, retained
   source checkout, and archive for prior occurrences;
2. freeze the S1 decision, summary, checkpoint, engine/configuration, both
   controls, the unchanged Boatlee artifact, opponent packages, both seats,
   and all 64 jobs;
3. verify direct and Windows-spawn imports, including the complete Saiteja
   package;
4. keep one Boatlee-only control cache and emit no v27 candidate or control
   game;
5. require all 32 controls to finish before launching the 32 candidates;
6. record sign counts, mean and worst paired margin, lower-quartile mean,
   per-opponent means, and every negative context;
7. write an attributed S2 decision before any later tier. Completion never
   launches another tier automatically.

The frozen launcher is `formal_s2.py`. Preflight and launch require separate
commands so fresh games cannot occur during validation. Once the detached run
is launched, retain its PID, manifests, logs, shards, and canonical hashes and
do not monitor it until the user requests a read-only audit.

## Boatlee S2 remediation boundary

The S2 decision is `E2_S2_REMEDIATION_REQUIRED`. The user-authorized
remediation is complete and freezes one selector,
`e2boatlee_7f591d609cf14d89e6aa1599`, for possible fresh confirmation.

- `boatlee_remediation.py` reconstructs step-240-only and step-241-only
  attributable variants and runs consumed-seed diagnostics only.
- `boatlee_selector.py` owns the public fertilizer-surplus rule and standalone
  builder.
- `boatlee_selector_validation.py` checks exact predicted behavior, worker
  equality, technical-seed fast/standalone parity, failure injection, and
  latency.
- `remediation_verification.json` is the machine authority. A readiness value
  is not an efficacy claim.

Do not reuse S1/S2 seeds as fresh confirmation. Before a new formal run,
obtain explicit user authorization, scan and select a new seed tier, freeze a
new root, and evaluate the selector against the unchanged Boatlee control in
both seats and all four opponent families. The selector's public threshold
perfectly separates Roman from the other retained families, so fresh evidence
must explicitly test proxy overfit. Do not launch a later tier or package for
submission automatically.
