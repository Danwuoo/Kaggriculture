# Task 0 report: generated-artifact normalization

## Scope

Behavior-preserving normalization only. The two generated standalone artifacts
were rebuilt through their existing builders on Python 3.14.7 / zlib-ng 1.3.1.
No development source, readable route, engine/vendor file, data, or docs file
was changed.

Artifact/evidence commit: `3f30a7541e5f3386df0024d1a26b9a61941413b2`
(`Normalize generated artifacts`).

## RED

Command run before regeneration:

```powershell
python -m unittest research.main_approach.test_development_sources -v
```

Result: exit 1; 3 tests ran with exactly two expected failures:

- `v27_current_meta`: `generated standalone is stale`
- `boatlee_v16_rc2_market_relay`: `generated standalone is stale`

The other two assertions passed: development sources remained decompressed and
both readable routes decoded from the prior generated artifacts.

## GREEN and artifact checks

Builders run from the worktree root:

```powershell
python research\main_approach\v27_current_meta\development\build_standalone.py
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py
```

GREEN command and result:

```powershell
python -m unittest research.main_approach.test_development_sources -v
# Ran 3 tests in 0.238s — OK
```

After exact-engine equivalence, both builder `--check` commands and the shared
source contract were run again:

```powershell
python research\main_approach\v27_current_meta\development\build_standalone.py --check
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
python -m unittest research.main_approach.test_development_sources -v
# Ran 3 tests in 0.185s — OK
git diff --check
# exit 0
```

## Exact-engine equivalence

Harness: `research/main_approach/performance_optimization_2026_08_11/harness.py`.
The pre-normalization controls were loaded directly from commit
`9e90922914d11272b932b9516eadc329d16186a4`; each was compared with the
regenerated artifact using the same seed, opponent, and seat.

Engine fingerprint:

- Commit: `bded87b0d7879078c726a93a4884d044f79c4eed`
- Python blob/SHA-256: `4b78842d0f2d4abf6e318a8248b6306454f5c714` / `fb9215c5e21a25243e2d13e75b3d70a79cf7d78fff150a90f1bb5eacf9ba2bcf` (39,801 bytes)
- Configuration blob/SHA-256: `0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8` / `7f196f4aaf9b4e482fbd61ba4bf19f5cec4da0f81938ece756954035a65c0bb5` (5,877 bytes)

| Incumbent | Seed | Opponent | Seat | Equivalent | Rewards (candidate/opponent) | Candidate action digest |
| --- | ---: | --- | ---: | --- | --- | --- |
| v27_current_meta | 873001 | kaito_v21 | 0 | yes | 71222 / 43905 | f81deed7fa88cfa63f3943812b8ab9931fb1b25b79cb71b92d7a8aaefba2929d |
| v27_current_meta | 873001 | kaito_v21 | 1 | yes | 71222 / 43905 | f81deed7fa88cfa63f3943812b8ab9931fb1b25b79cb71b92d7a8aaefba2929d |
| boatlee_v16_rc2_market_relay | 873001 | kaito_v21 | 0 | yes | 71222 / 43905 | f81deed7fa88cfa63f3943812b8ab9931fb1b25b79cb71b92d7a8aaefba2929d |
| boatlee_v16_rc2_market_relay | 873001 | kaito_v21 | 1 | yes | 71222 / 43905 | f81deed7fa88cfa63f3943812b8ab9931fb1b25b79cb71b92d7a8aaefba2929d |

For every row, the pre-normalization control and regenerated artifact had
exactly equal statuses (`DONE`/`DONE`), 719 calls, candidate/opponent rewards
and monies, both action digests, action issues, maximum market orders,
economic diagnostics, terminal inventory, exception fields, timeout calls, and
overage state. Each had zero malformed actions, hand misalignment, seed
overcommit, market overflow, exceptions, timeout calls, overage exhaustion,
animal escapes, crop deaths, fresh-crop deaths, and shed-overflow events or
units. Maximum market orders was 10; terminal inventory was 0 units / $0.

Machine-readable per-game evidence is retained in
`reports/job_value_residual_2026-08-12/baseline_normalization.json`.

## Files changed

- `research/main_approach/v27_current_meta/main.py` — builder-generated zlib/Base64 route payload only.
- `research/main_approach/boatlee_v16_rc2_market_relay/main.py` — builder-generated zlib/Base64 route payload only.
- `reports/job_value_residual_2026-08-12/baseline_normalization.json` — engine fingerprint and equivalence evidence.
- `.superpowers/sdd/implementation_plan/task-0-report.md` — this verification report.

The regenerated SHA-256 values are respectively
`6f8d070467e311293f6ee919fa405a332ab9f904f3fea77390bb9abb5ff46c64` and
`7117e45755fc4f9b227c82921e19822ce7fcee8c5605a6d0f84957a5a4a8592a`.

## Self-review and concerns

Reviewed the generated-file diff: it changes only the compressed route payload
in both artifacts. The builder checks, source contract, JSON parse, and
exact-engine two-seat comparison all supplied fresh verification evidence.

Concern: Git reported the repository's normal LF-to-CRLF checkout warning for
the three committed files. `git diff --check` was clean; the staged content is
the builder output and no line-ending-only edits were observed. No other
concerns.
