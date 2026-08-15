# Runbook

Run every command from `C:\Users\wurre\Downloads\Kaggriculture`.

## D0-D4 development commands

```powershell
python research\dual_incumbent_topology_search_2026-08-14\cli.py preflight --output research\dual_incumbent_topology_search_2026-08-14\artifacts\preflight.json
python research\dual_incumbent_topology_search_2026-08-14\cli.py enumerate --frontier --output research\dual_incumbent_topology_search_2026-08-14\artifacts\development_population.json
python research\dual_incumbent_topology_search_2026-08-14\cli.py audit-technical --output research\dual_incumbent_topology_search_2026-08-14\artifacts\technical_audit.json
python research\dual_incumbent_topology_search_2026-08-14\d0_verify.py --output research\dual_incumbent_topology_search_2026-08-14\artifacts\d0_verification.json
python research\dual_incumbent_topology_search_2026-08-14\d4_verify.py --output research\dual_incumbent_topology_search_2026-08-14\artifacts\development_verification.json --transcript research\dual_incumbent_topology_search_2026-08-14\artifacts\command_transcript.txt
```

These commands accept only the previously consumed technical seed `811407`.
They do not authorize or execute formal fresh seeds.

## Scheduler and resume

Create an immutable development manifest by selecting lane-qualified IDs from
`technical_audit.json` or `development_population.json`:

```powershell
python research\dual_incumbent_topology_search_2026-08-14\cli.py make-dev-manifest --registry research\dual_incumbent_topology_search_2026-08-14\artifacts\technical_audit.json --candidate-id <lane-qualified-id> --opponent other_incumbent --run-id <run-id> --stage D3 --output <manifest.json>
python research\dual_incumbent_topology_search_2026-08-14\cli.py run --manifest <manifest.json> --run-root <run-root> --workers 1
python research\dual_incumbent_topology_search_2026-08-14\cli.py run --manifest <manifest.json> --run-root <run-root> --workers 4 --resume
python research\dual_incumbent_topology_search_2026-08-14\cli.py status --manifest <manifest.json> --run-root <run-root>
python research\dual_incumbent_topology_search_2026-08-14\cli.py merge --manifest <manifest.json> --run-root <run-root> --output <merge.json>
```

`status` is read-only. Every job owns one shard. A corrupt shard is preserved
with a `.corrupt-<hash>.json` suffix before resume replaces its canonical path.
Infrastructure-failed shards contain no efficacy field and cannot merge.

## Formal S1 boundary

Do not run these commands under the current authorization. After the user says
`開始 E1`, first rescan all seed usage, populate and freeze `S1` in
`protocol_seed_registry.json`, and freeze the selected lane-qualified jobs.
Then the exact preflight/materialization commands are:

```powershell
python research\dual_incumbent_topology_search_2026-08-14\cli.py make-formal-manifest --authorization START_E1 --tier S1 --seed-registry research\dual_incumbent_topology_search_2026-08-14\protocol_seed_registry.json --registry research\dual_incumbent_topology_search_2026-08-14\artifacts\development_population.json --candidate-id <v27-id> --candidate-id <boatlee-id> --opponent <family> --run-id <frozen-run-id> --output research\dual_incumbent_topology_search_2026-08-14\artifacts\formal\s1_manifest.json
python research\dual_incumbent_topology_search_2026-08-14\cli.py formal-preflight --authorization START_E1 --tier S1 --registry research\dual_incumbent_topology_search_2026-08-14\protocol_seed_registry.json --manifest research\dual_incumbent_topology_search_2026-08-14\artifacts\formal\s1_manifest.json
python research\dual_incumbent_topology_search_2026-08-14\cli.py launch-formal --authorization START_E1 --tier S1 --registry research\dual_incumbent_topology_search_2026-08-14\protocol_seed_registry.json --manifest research\dual_incumbent_topology_search_2026-08-14\artifacts\formal\s1_manifest.json --run-root research\dual_incumbent_topology_search_2026-08-14\artifacts\formal\s1_run --workers <N> --stdout research\dual_incumbent_topology_search_2026-08-14\artifacts\formal\s1_stdout.log --stderr research\dual_incumbent_topology_search_2026-08-14\artifacts\formal\s1_stderr.log --launch-record research\dual_incumbent_topology_search_2026-08-14\artifacts\formal\s1_launch.json
```

`launch-formal` starts a hidden spawn-isolated process, redirects both streams,
records PID/run ID/manifest and registry hashes/expected shard paths, and
returns immediately without polling, tailing, sleeping, or waiting.
