# Kaggriculture Top-50 Public Replays (2026-08-09)

This dataset contains one high-reward public Kaggriculture replay for each of
the top 50 teams in a fixed public-leaderboard snapshot.

## Snapshot

- Competition: `kaggriculture`
- Leaderboard captured: `2026-08-08T16:10:15.675637Z`
  (`2026-08-09 00:10:15` Asia/Taipei)
- Included leaderboard ranks: 1-50
- Replay count: 50 unique episodes
- Uncompressed size: 1,391,681,379 bytes (1.296 GiB)
- Replay schema version: 1
- Engine module versions: 47 on `1.32.6`, 2 on `1.32.5`, and 1 on `1.32.4`

## Files

The compact metadata files remain in this directory. The 50 raw payloads were
moved during the 2026-08-10 workspace cleanup to:

`C:\Users\wurre\Desktop\Kaggriculture-archive\2026-08-10\data\public_replays\top50-2026-08-09\replays`

- `leaderboard_snapshot.json`: the fixed leaderboard snapshot used for
  selection. It retains ranks 1-55 so the collection can be audited and would
  have allowed bounded backfilling if a top-50 team had no accessible replay.
- `manifest.json`: selection metadata, teams, submissions, opponents, rewards,
  seeds, file sizes, SHA-256 checksums, engine versions, and replay paths.
- `failures.json`: collection failures. It is an empty list for this snapshot.
- `replays/episode-<id>-replay.json`: paths recorded by the frozen manifest;
  resolve these below the external archive dataset root above.

## Selection rule

For each leaderboard team, the collector:

1. Finds the active submission whose public score exactly matches the fixed
   leaderboard score.
2. Lists that submission's completed public episodes.
3. Selects the episode with the highest reward earned by that team.
4. Enforces unique episode IDs in leaderboard order, using the next-highest
   reward only if an earlier team already selected the same episode.
5. Breaks equal-reward ties by lower episode ID.

All 50 entries in this snapshot use their team's number-one reward episode;
no duplicate fallback was necessary. Selected target-team rewards range from
134,868 to 183,163. These are unusually strong individual games and should not
be interpreted as expected or median performance.

## Validation

Every replay was parsed and checked for:

- the expected episode ID;
- exactly 720 recorded steps;
- terminal statuses `DONE`, `DONE`;
- agreement between replay and episode-list target reward;
- a recorded SHA-256 checksum and byte size.

`manifest.json` is the authoritative index. To collect a fresh snapshot into a
different output directory, run:

```powershell
python scripts\collect_top_public_replays.py `
  --count 50 `
  --candidate-limit 55 `
  --workers 2 `
  --output data\public_replays\top50-YYYY-MM-DD
```

The live leaderboard and episode population change over time, so a fresh run is
not expected to reproduce the same teams or episode IDs. The stored files are
reproducible by their episode IDs and checksums.

## Information-boundary warning

A replay contains each player's own private observation. Combining both agent
records offline exposes private inventories for both sides, even though neither
agent had that combined view during play. Use private fields only to audit the
same player. Cross-player strategy comparisons and any runtime opponent model
must use public farms, actions, market data, town data, and final rewards only.
