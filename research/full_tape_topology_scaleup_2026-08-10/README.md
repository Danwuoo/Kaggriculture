# Full-tape topology staged scale-up

Offline-only corpus/research lane. `streaming_corpus.py` is resumable and
keeps its raw one-file temporary cache below `research/cache/`, never `data/`.
It records public action topology and same-player-only private compatibility
labels. See the matching decision at
`reports/full_tape_topology_scaleup_2026-08-10/decision.md`.

- `branch_v25_to_zero_agent.py`: verified 161-turn exact-backbone branch.
- `streaming_corpus.py`: live API coverage, streaming extraction, and audit.
- `build_tape_trie.py`: SQLite full-action trie and market-residual summary.
- `corpus_supported_tape_agent.py`: retained failed corpus candidate.
