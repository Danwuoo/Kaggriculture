# Staged full-tape topology scale-up

Date: 2026-08-10  
Status: **PROCEED_STAGED_TO_1500 — partial API coverage, no production promotion.**

The user explicitly authorized read-only Kaggle/API collection and an isolated
research cache. Nothing under `submission/`, `dist/`, `.vendor/`, `data/`, or
`docs/` was changed; no Kaggle submission, remote repository, or remote write
was made.

## Formulation retained

Exact notebook backbones remain atomic. This program does not train a
state-to-next-action classifier or create generic maintenance continuation. It
uses canonical full 719-action tapes, separate unit and market tapes,
common-prefix/branch topology, and same-family residual statistics. Runtime
candidates must be a complete tape/backbone, a verified complete-tape branch,
or a bounded residual over such a backbone.

## Stage A — exact v25 → zero-to-top branch

`prefix_branch_ablation.json` tests v25 through step 160, shadow-verifies the
zero-to-top emitted action on every prefix step, then invokes zero-to-top's
original controller/tape from step 161. It never calls a maintenance planner.

- all 12 fresh blocks had 161/161 runtime prefix equality and matching
  same-player step-161 state labels versus direct zero reference;
- zero escapes/fresh crop deaths/overflow/schema/timeout, deterministic, p95
  0.9822 ms;
- efficacy failed: 4/12 positive paired deltas. Kaito mean −3,991.50;
  Saiteja +780.50; Roman +249.00.

This is a valid complete-tape branch negative result, not evidence against the
complete-backbone formulation generally.

## Stage B — streaming corpus and coverage

Cache root (absolute):
`C:\Users\wurre\Desktop\Kaggriculture\research\cache\full_tape_topology_scaleup_2026-08-10`.
The collector pages a 1,700-row live leaderboard snapshot (API page maximum
200), resolves team/submission/episode metadata, downloads only one temporary
raw replay at a time, and immediately writes compressed canonical feature/tape
records. A successful raw file is removed only after the feature is durable;
invalid raw files would be retained separately. No successful raw replay is
retained.

Actual checkpointed coverage, not a claimed 1,500:

| Measure | Actual |
| --- | ---: |
| Live leaderboard rows cached | 1,700 |
| Successful team metadata | 277 (ranks 1–290, non-contiguous) |
| Team/submission-deduplicated selected episodes | 227 |
| Replays streamed | 246 |
| Analysis representatives | 227 |
| Duplicate team/submission records retained but excluded from support | 19 |
| Raw bytes processed | 6,968,260,166 |
| Successful raw bytes retained | 0 |
| Compressed feature + tape bytes | 3,313,238 |
| Replay module versions | 244 on 1.32.6; 2 on 1.32.5 |

The initial broad metadata pass triggered HTTP 429. It was stopped after
checkpointing; later 25/50/100-rank controlled batches resumed successfully
until the current partial boundary. `coverage_report.json` and
`metadata_failures.jsonl` record coverage/failure state. This is an API
rate-limit/metadata-availability blocker, not a claim that 1,500 is complete.
Resume with `--metadata-batch` after backoff.

## Corpus structure and trie

After team/submission dedupe, the corpus has 225 exact full-tape families, 99
unit-tape families, 225 market-tape families, and 55 public route families.
The largest unit family has support 53 while all 53 market tapes differ: a
direct demonstration that unit topology and market continuation must remain
separate. Its terminal market shapes show repeated but non-universal SELL
patterns, retained in `full_action_trie.json` as family-specific residual
evidence rather than a universal action rule.

`full_action_prefix_trie.sqlite` and `full_action_trie.json` contain 102,803
disk-backed full-action prefix nodes for 227 representative tapes. The first
action is shared by all 227; later branches include a two-child boundary after
78 common actions with aggregate support 98. This is the intended
common-prefix/branch corpus representation, not a random transition split.

## Stage C/D — corpus-supported candidate gate

Ranks 82 and 96 are distinct teams and submissions but share one exact complete
full/unit/market tape. That two-team 719-step support was selected before eval
as the smallest executable corpus candidate. The candidate returned that tape
verbatim except for current hand-count padding/truncation; it contained no
planner, state classifier, market invention, or maintenance continuation.

On fresh seeds 732041/732059, both seats, and Kaito/Saiteja/Roman live
families, it was deterministic and p95 0.1597 ms but failed decisively:

- 0/12 positive paired-margin deltas;
- family means −60,941.75 / −49,706.25 / −54,678.50;
- 12 animal escapes in every candidate game, despite zero malformed actions,
  seed overcommit, market overflow, and timeout.

This rejects direct raw-tape replay execution even with independent full-tape
support. It reinforces that a corpus tape needs a verified executable backbone
or state-compatible branch/rejoin; it does not reject the streaming corpus.

## Decision and next stage

Continue **PROCEED_STAGED_TO_1500** from the retained cache checkpoint. The
next priority is rate-limited metadata collection followed by streaming only
new selected episodes. Do not launch more unconditioned raw-tape candidates:
the first one is decisive negative evidence. Use additional corpus support to
identify a branch attached to an exact executable backbone or a family-specific
SELL/terminal/WEED residual with a measured compatibility condition, then use
new seeds, both seats, live family-stratified opponents, safety, determinism,
latency, and paired-win gates.

All splits remain by team/submission/episode/family/time; random transition
splits are forbidden. Selected-best-episode bias, engine-version drift,
notebook-team identity ambiguity, repeated submissions, and no cross-player
private leakage are explicit audit boundaries.

## Reproduction

```powershell
$env:PYTHONPATH=(Resolve-Path '.vendor\kaggle-environments').Path
$env:TF_CPP_MIN_LOG_LEVEL='3'
python -m compileall -q research\full_tape_topology_scaleup_2026-08-10
python -m unittest discover -s research\full_tape_topology_scaleup_2026-08-10\tests -v
python research\full_tape_topology_scaleup_2026-08-10\streaming_corpus.py --stage coverage --requested-count 1500 --candidate-limit 1700 --workers 2 --metadata-batch 25
python research\full_tape_topology_scaleup_2026-08-10\streaming_corpus.py --stage checkpoint --requested-count 1500 --candidate-limit 1700
python research\full_tape_topology_scaleup_2026-08-10\streaming_corpus.py --stage collect --requested-count 1500 --candidate-limit 1700
python research\full_tape_topology_scaleup_2026-08-10\build_tape_trie.py --output reports\full_tape_topology_scaleup_2026-08-10\full_action_trie.json
python research\full_tape_topology_scaleup_2026-08-10\run_prefix_branch.py --output reports\full_tape_topology_scaleup_2026-08-10\prefix_branch_ablation.json
python research\full_tape_topology_scaleup_2026-08-10\run_corpus_tape_ablation.py --output reports\full_tape_topology_scaleup_2026-08-10\corpus_tape_ablation.json
```
