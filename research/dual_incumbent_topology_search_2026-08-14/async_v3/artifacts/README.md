# Async V3 artifact retention

The source tree commits the compact evidence needed to reconstruct the E1c
decision:

- development verification and its command transcript;
- the completed E1c `search_summary.json`, `protocol.json`, and `launch.json`;
- the two materialized E1c finalist standalones, including the retained v27
  no-op counterexample.

The 5,700-plus per-context shards, generation manifests, caches, checkpoints,
and stdout log occupy roughly 436 MiB and remain preserved in the original
local workspace. They are intentionally ignored rather than deleted or
rewritten. Their frozen hashes are recorded in `../e1c_decision.md` and
`../../e2/candidate_registry.json`.

Do not infer that an ignored raw artifact never existed. Do not regenerate a
historical artifact into the same run directory. A reproduction must use a new
run ID and compare its canonical hashes with the committed compact evidence.
