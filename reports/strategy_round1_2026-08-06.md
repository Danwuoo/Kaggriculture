# Kaggriculture strategy round 1 — 2026-08-06

## Scope and authority

- Submission `55283999` was inspected but not resubmitted.
- Live Kaggle submission status at analysis time: `COMPLETE`, submission API
  public score `646.2`. The leaderboard snapshot downloaded at 01:27:58 UTC
  listed Daniel Wu at rank 1,056 with rating 682.4; the two endpoints update on
  different schedules.
- All ten available replays (validation plus nine public games) were downloaded to
  `reports/public_replays/` and summarized in `public_replay_analysis.json`.
- The current upstream `Kaggle/kaggle-environments` master and the pinned local
  engine were both commit `a4dce5ae6e2ffe3c1afea8ec4b24b562df74cc07`.
- Opponent comparisons use only public farms, actions, market state, and rewards.
  Each player's private replay observation is used only to audit that same player.

## Replay findings

The baseline's public record was five wins and four losses after the latest two
episodes arrived. The four losses were:

| Episode | Opponent | Ours | Opponent | Verified strategic gap |
|---:|---|---:|---:|---|
| 90302036 | Garigariyong | 66,120 | 87,718 | Opponent reached 6 cows + 3 sheep while sustaining roughly 9–14 melons and 12 strawberries; our mature farm held 14 animals but only 2–3 strawberries. Opponent unlocked NE/SW at steps 169/218 versus our 242/290. |
| 90303546 | Fernando GH H | 73,885 | 101,974 | Opponent allocated early capital to 10 melons + 5 strawberries with only 1 cow + 1 sheep, then reached 7 cows + 5 sheep, about 14 melons and 20 strawberries. Our opening was 5 melons and mature crops remained 2 strawberries. |
| 90304270 | Solve Langseth | 47,752 | 60,654 | Opponent used only 6 cows, one extra quadrant, and a large rotating melon/wheat/carrot field (up to 26 melons). Its milk sales also depressed the shared milk price; our 8-cow target concentrated more capital in the contested product. |
| 90305779 | Team Name Pending | 83,126 | 97,294 | Opponent delayed livestock, opened with 13 melons, then operated 5 cows + 7 sheep and up to 32 strawberries. Our early cash lead was overtaken after its large crop cohorts matured. |

Across the validation and public games, the baseline used about 6,880 unit-action
slots. Only 22–24% were field/logistics operations, while roughly 4,300 actions
were movement (2.7–2.9 moves per productive action). Strong winning opponents
were generally around 1.7–1.9 moves per productive action. The planned SW crop
area was visibly empty for most of the season and the intended 6–7 strawberry
target usually materialized as only 2–3 plants.

The baseline already handled two areas well:

- It sold the five-melon opening at steps 253–260 and usually front-ran the
  opponents' first large melon sale. The main deficit was production scale, not
  the first-sale trigger.
- Terminal shed/carried product was normally zero or one unit, so terminal
  liquidation was not the cause of the losses.

## Root cause and changes

The scheduler routed `PICKUP` and `DROP` jobs to all four center shed-access
tiles. The engine rejects every tile operation on a `LOCKED` tile, including a
center access tile. Before NE/SW unlocks, the scheduler's shadow inventory could
therefore record wheat or fertilizer as picked up while the final legality layer
correctly projected the action to `PASS`. That starved real feed/placement work,
increased movement churn, and prevented P5 crop construction from receiving
capacity.

Changes retained:

1. Shed logistics now target only currently unlocked center access tiles.
2. The opening melon cohort was raised from 5 to 8, still alongside the required
   3-cow + 1-sheep opening and four wheat plots. Eight fits the existing 12 NW
   crop slots without changing spatial roles.
3. Added regression tests for locked shed access and the replay-informed opening
   cohort.
4. Added `scripts/analyze_public_replays.py` for reproducible replay summaries.

A broader sticky-assignment experiment was rejected because it introduced two
animal escapes in the first arena run. It is not present in the final candidate.

## Old-versus-new paired evidence

The exact old archive was preserved as
`reports/baseline_submission_55283999.tar.gz` (SHA-256
`C90ED03D87D6B4C3FA7C4AC0E49CA9152D8BA966EED1C2DB432A67C11C3ABDFD`).
The final candidate played it at seeds 0, 11, 23, 37, 101, and 777 from both
seats under the official engine:

- 12 wins, 0 losses.
- Average candidate reward: 63,433.17.
- Average old-baseline reward: 51,771.17.
- Average paired terminal difference: +11,662.00.
- All games ended with both players `DONE`.

Exact games are in `candidate_vs_baseline_round2.json`. This comparison is
zero-sum strategically but not in raw coin totals: the larger, earlier candidate
melon cohort also changes the shared market price faced by the old baseline.
That is intentional because ladder rating rewards match wins.

## Final acceptance gates

- Unit tests: 18/18 passed.
- Official arena: 13/13 games ended with both players `DONE`.
- Starter: 6/6 wins; random: 6/6 wins, three seeds and both seats.
- Malformed actions: 0.
- Animal escapes: 0.
- Fresh-crop water deaths: 0.
- Shed overflow states: 0.
- Determinism: identical seed-777 rewards and action digest on repeat.
- Full 719 effective calls: p50 0.7387 ms, p95 1.07972 ms,
  p99 1.50608 ms, maximum 9.1504 ms.
- Archive: 17,340 bytes, 13 Python files, root `main.py` present.
- Archive SHA-256:
  `C84664D77EB9D32CE7001D31EE15634AE144B9403BA98D43B1D69226A588AAB2`.
- Extracted-package official game at seed 4242: 93,405–3,514 against starter,
  both players `DONE`, 720 recorded states.

## Remaining risk

The candidate is still livestock-heavy relative to the strongest public agents,
and the replay set is small. The next experiment should preserve the new shed
fix and 8-melon opening while comparing 6–7 cows / 4–5 sheep against the current
8/6 mature target, then expand the strawberry target only if paired win rate
improves without feed safety regressions.
