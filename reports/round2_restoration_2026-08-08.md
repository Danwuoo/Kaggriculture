# Round 2 canonical restoration — 2026-08-08

Status: restored, validated, and packaged locally.  No Kaggle submission was
made by this operation.

## Source restoration

The 13 files in `submission/` were restored to the retained Round 2 control.
Before the experiment source was removed, every runtime Python file matched the
control by SHA-256.  The behavioral rollback restored:

- town-center demand estimate `1/12`;
- locked center tiles rejected by the legality projector;
- shed logistics routed only through currently unlocked center access tiles;
- Round 2 engine provenance (`a4dce5ae6e2ffe3c1afea8ec4b24b562df74cc07`).

## Validation

- Compile: passed for `submission`, `tests`, and `scripts`.
- Unit tests: 18/18 passed on the pinned engine.
- Official arena: all 13 evaluated games ended with both players `DONE`.
- Starter: 6/6 wins; random: 6/6 wins, three seeds and both seats.
- Determinism: repeated seed-777 self-play produced identical rewards and
  action digest.
- Safety: zero malformed actions, timeout calls/statuses, animal escapes,
  fresh-crop deaths, shed overflow states, seed overcommitments, and market
  lists above ten entries.
- Full 719-call episode latency: p50 0.7774 ms, p95 1.04767 ms,
  p99 2.00739 ms, maximum 10.4343 ms.
- Extracted archive game: 720 states, both players `DONE`, seed 4242 versus
  starter, reward 93,405–3,514.

Exact arena records remain in `reports/arena_results.json`.

## Package

`dist/submission.tar.gz` contains 13 Python files with `main.py` at archive
root.  Size: 17,340 bytes.  SHA-256:

`C84664D77EB9D32CE7001D31EE15634AE144B9403BA98D43B1D69226A588AAB2`

This exactly matches the previously recorded Round 2 artifact hash.

## Experiment cleanup

The stopped family and lane experiment trees (2,998,337,652 bytes before
cleanup) were moved to the Windows Recycle Bin.  Raw experiment JSON,
current-engine-only runners, and current-engine-only tests were deleted.  The
retained narrative decisions are indexed by `reports/experiments/README.md`.
