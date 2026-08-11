# Public Kaggriculture research agents

These notebooks were downloaded from public Kaggle sources on 2026-08-06 for
offline opponent evaluation.  Their title metrics are author claims, not local
or leaderboard verification.

- `saiteja_mega_ensemble_3000`: `saitejabandaruin/kaggriculture-ultimate-mega-ensemble-3000`
- `saiteja_pure_architecture_2600`: `saitejabandaruin/kaggriculture-pure-architecture-2600-elo-v3`
- `kaito_v21_top30`: `kaitofukami/177-180-fresh-top-30-v21-1-conditional-memory`
- `kaito_v20_weed_recovery`: `kaitofukami/159-160-vs-frontier-v20-weed-slip-recovery`
- `roman_lb950`: `romanrozen/strong-statr-baseline-agent-lb-950`

Run `python scripts/extract_public_agents.py` to statically extract embedded
Python payloads.  The extractor parses notebook literals and never executes a
notebook cell.  Extracted code remains offline research material and is not
included in `submission/` or `dist/submission.tar.gz`.
