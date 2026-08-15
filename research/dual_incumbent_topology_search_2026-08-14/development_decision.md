# Development decision: READY_FOR_FORMAL_S1

Date: 2026-08-14

## Outcome

D0-D4 are complete and the development decision is
`READY_FOR_FORMAL_S1`. Formal fresh seeds were not executed. Technical seed
`811407` was used only for correctness, lineage, parity, scheduler, and failure
testing; its score deltas are not promotion evidence.

## Evidence

- Both incumbent controls were frozen before D0. The independent atomic seed
  guards preserve the incumbent when private/seeds data is absent or unreadable
  and cancel every same-crop PLANT only when readable demand exceeds stock.
- Both regenerated standalones, both builder checks, the shared 3-test source
  contract, and the official-engine generated/development/frozen-control audit
  pass from both seats.
- The exact local trace verifies cow ordinal 9, purchase step 361, build/place
  steps 517/518, and tile `(7,3)`.
- The shared semantic frontier compiles independently to 41 candidates and 14
  concrete rejections per lane. Equal genomes have lane-specific IDs; the two
  compiled ID sets have zero collisions.
- Control, ninth-cow removal (fixed8 reconstruction), true `-24`, and true
  `+24` compile and achieve exact fast/standalone parity from both seats on
  both incumbents.
- One-worker and two-worker runs have the same canonical merge digest.
  Corruption/resume, simulated kill/restart, worker failure, engine-import
  failure, read-only status, and no-efficacy-on-infrastructure-failure tests
  pass.
- Every audited research standalone imports from an isolated directory, is
  standard-library-only at runtime, and remains below 5 MiB. Maximum observed
  p95 call latency is below 1 ms and maximum call latency is below 3 ms, well
  inside the 150/750 ms gates.

The authoritative machine result is
`artifacts/development_verification.json`; the exact command transcript is
`artifacts/command_transcript.txt`. The first failed D4 attempt and its missing
`requests` traceback are retained under `artifacts/remediation/`; the repaired
audit uses the installed Python 3.12 environment required by the legacy audit
runner without changing any gate.

## Formal boundary and limitations

No Phase 1, Phase 2A, fixed8 selector-v2, or prior plus/minus-24 implementation
artifact exists in this checkout, so those remain prompt memory rather than
authority. The D1 route synthesizer is deliberately bounded and deterministic;
it rejects with a concrete resource/path/precondition/rejoin reason rather than
improvising when exact trace support is absent.

Before S1, rescan seed usage, freeze the S1 seed registry and job manifest, and
retain both lane strata independently. Do not pool rewards or paired margins.
