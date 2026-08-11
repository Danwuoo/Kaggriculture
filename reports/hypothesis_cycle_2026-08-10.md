# Hypothesis and redevelopment cycle — 2026-08-10

Status: diagnostic cycle complete; redevelopment candidate rejected; canonical
workspace unchanged.

## Protocol

The investigation used a coordinator plus isolated projectless task lanes.  All
worker tasks used `gpt-5.6-terra` with `xhigh` reasoning in standard mode.  Each
lane treated `C:\Users\wurre\Desktop\Kaggriculture` as read-only, wrote only to
its own directory, and used short predeclared experiment blocks rather than a
new broad league.

Current-semantics experiments used official engine commit
`bded87b0d7879078c726a93a4884d044f79c4eed` with an explicit
`townCenterSellInterval=24`.  This is important because the earlier replay-clone
matrix patched current Python behavior into the old local package while still
inheriting the old JSON default of 12.

After the cycle, all 13 files in `submission/` matched an isolated Round 2
control snapshot by SHA-256.  `dist/submission.tar.gz` remained unchanged at:

`C84664D77EB9D32CE7001D31EE15634AE144B9403BA98D43B1D69226A588AAB2`

## Hypothesis decisions

| ID | Mechanism | Decision | Discriminating evidence |
| --- | --- | --- | --- |
| H1 | Canonical is stuck chiefly because its intended production scale is too small. | Rejected as the primary cause. | Exact v25 reached a much larger turn-240 farm, but handing that state to unchanged canonical produced 91,427 versus 99,084 for all-canonical.  It preserved the herd but lost 20 inherited strawberries and accumulated 18 weeds. |
| H2 | The missing abstraction is season-scale multi-worker trajectory commitment. | Plausible, but efficacy not established by the tested one-day proxy. | Observationally, high routes used less travel and more productive work after load normalization.  A day-local commitment patch first won 4/4 on already-used seeds, but the frozen fresh holdout was only 3/1 with paired means +52 and +516; the earlier +13,178 mean did not reproduce. |
| H3 | A different opening capital basin is the main advantage. | Rejected as a sufficient explanation. | Exact v25 scored 200,213 versus canonical 99,084 on one controlled seed, but v25-to-canonical handoffs at steps 24, 72, and 240 scored only 56,738, 92,351, and 91,427.  Continued execution, not entry state alone, carried the value. |
| H4 | Shared-market relative timing is frontier alpha. | Supported, but only as a small edge. | On a fixed verified Preempt-H6 field route, SELL ranking beat the no-ranking near-clone 4/0 over two fresh seeds and both seats, with mean margin about +153.  Preemption generalized against a non-clone only by tens of coins and did not alter W/L. |
| H5 | The apparent limit is partly an engine/configuration measurement artifact. | Supported. | The frozen clone study combined current-like patched behavior with the old `townCenterSellInterval=12`; current official semantics use a flat 24-turn interval.  Current locked center-shed operations also differ from the local pinned engine. |
| H6 | Clone evaluation substantially mismeasured exact public artifacts. | Moderately supported, with an identity boundary. | Exact Kaito v21 and Saiteja 3000 notebook payloads beat canonical in both seats on the current-semantics micro-panel, while Roman lost both.  No notebook full tape matched a Top-50 player tape, and two replay-conditioned checks diverged after 96 and 324 matching actions.  Notebook payload identity is not submission/team identity. |
| H7 | The project is optimizing terminal bank when it should optimize family-stratified paired wins. | Not supported by the direct bounded test. | The raw-bank-selected P1R1 market variant and paired-win-selected P0R1 variant both went 4/0 against exact Kaito v21.1.  P1R1 retained +23.5 mean own bank and +89 mean margin; no objective-ranking divergence appeared. |
| H8 | The Top-50 modal field route is itself the correct imitation target. | Rejected as a sufficient problem formulation. | Among the 50 selected targets, 33 share the exact 719-step field/unit tape and 45 share the macro route, yet all 50 complete action tapes, market tapes, and market-order shapes are distinct.  Route prevalence alone does not identify the winning residual. |

## Main experiment blocks

### Measurement and exact-artifact panel

- The engine/configuration mismatch was reproduced and fingerprinted.
- On seed `20260810`, paired seats under current semantics:
  - `kaito_v21_top30`: margins +76,295 and +74,396 versus canonical.
  - `saiteja_mega_ensemble_3000`: +41,292 and +42,542.
  - `roman_lb950`: -6,582 and -7,124.
- These results establish notebook-payload behavior only.  They do not prove
  that a notebook snapshot generated a particular historical replay.

### Prefix and scale separation

- All-exact v25: 200,213; all-canonical: 99,084.
- v25 prefix then canonical at 24/72/240: 56,738 / 92,351 / 91,427.
- The cut-24 composite lost all five inherited animals.  The cut-240 composite
  kept the inherited herd but could not sustain the inherited crop density.
- No controller reset, malformed action, or timeout explained the result.

### Trajectory and commitment tests

- In eight matched public-state cohorts, high replay actions minus canonical per
  100 worker-turns were approximately -16.44 travel and +17.95 field-productive
  actions.  Immediate reversals were 5.45 versus 16.69 per 100 move pairs.
- The direct day-local commitment patch changed only `scheduler.py`.  Its first
  two-seed screen was 4/0 with mean +13,178, but those seeds were already known.
- On two new holdout seeds it was 3/1 with paired means +52 and +516.  Travel,
  reversals, logistics, and productive-action metrics still improved, so those
  diagnostics are not reliable substitutes for paired competitive efficacy.
- The patch was not promoted.

### Fixed-route market tests

- Preempt-H6 supplied a verified separable route/ranking/preemption boundary.
- SELL ranking changed order at 23 steps and increased sale revenue while
  executing the same number of sale units.
- Ranking was a stable small near-clone edge.  Preemption survived against the
  non-clone Kaito family only as a small bank/margin effect, not a win-rate
  difference.

### Formulation and identity audit

- Exact field identities formed 15 families; the largest contained 33/50.
- The coarser macro fingerprint formed six families; the largest contained
  45/50 and had an effective family count of about 1.23.
- Within the largest field family, every market trace was distinct.
- Selected own bank predicted the selected replay's W/L but had essentially no
  pooled relationship with leaderboard rating.  Because the dataset keeps each
  team's highest-reward available replay, it cannot estimate family win rate or
  expected reward.
- Replay-conditioned Kaito and Saiteja checks did not reproduce all 719 actions;
  partial prefixes cannot establish code, package, or team identity.

## Redevelopment decision

One fresh redevelopment lane built a materially different trajectory-primary
agent around the public Preempt-H6 route.  It embedded the 719-step field tape
and added a compatibility guard, P0/P1 survival shell, fresh-plant protection,
bounded weed repair, seed/shed legality, SELL ordering, terminal liquidation,
and a survival/logistics fallback.

The candidate failed its predeclared gate:

- versus canonical: 0/4;
- versus exact public v25: 0/2;
- animal escapes: 32;
- schema, timeout, fresh-crop, overflow, market-cap, and seed-overcommit counts:
  zero.

The developer corrected an overly eager fallback guard after consuming the
eight-game cap.  A separate validation-only lane then tested the frozen archive
without modification.  Against canonical on fresh seed `618273`, the candidate
lost both seats (117-759 and 117-670) and still lost four animals in each game.
The independent decision was `REJECT`.  Two v25 validation records were invalid
because the validation harness reset an internal v25 table; they were retained
and not rerun, but the canonical safety failure already decided rejection.

Do not promote or package this trajectory-primary candidate.  It exists only as
negative architecture evidence.

## Detailed task-lane artifacts

The compact conclusions above are authoritative inside this workspace.  The
larger task-lane artifacts remain outside the project and may not survive a
workspace move:

- Round 1 measurement:
  `C:\Users\wurre\Documents\Codex\2026-08-10\kaggriculture-cycle-r1-measurement\RESULT.md`
- Round 1 prefix handoff:
  `C:\Users\wurre\Documents\Codex\2026-08-10\kaggriculture-cycle-r1-prefix\RESULT.md`
- Round 1 trajectory analysis:
  `C:\Users\wurre\Documents\Codex\2026-08-10\kaggriculture-cycle-r1-trajectory\RESULT.md`
- Round 2 commitment, market, and formulation:
  `C:\Users\wurre\Documents\Codex\2026-08-10\kaggriculture-cycle-r2-*\outputs\RESULT.md`
- Round 3 replication, objective, and identity:
  `C:\Users\wurre\Documents\Codex\2026-08-10\kaggriculture-cycle-r3-*\outputs\RESULT.md`
- Redevelopment and independent validation:
  `C:\Users\wurre\Documents\Codex\2026-08-10\kaggriculture-cycle-r4-*\outputs\RESULT.md`

## Implications for future work

1. Do not enlarge canonical asset targets merely to resemble a replay.
2. Do not promote route memory, a one-day commitment layer, or a fixed tape on
   trajectory diagnostics alone; require fresh, unused, paired-seat wins.
3. Treat SELL ordering as a late-stage marginal improvement, not a solution to
   the production/execution gap.
4. Every current-engine experiment must explicitly load and fingerprint the
   current Python source and JSON defaults.  A version label alone is not enough.
5. The next useful abstraction experiment must isolate route-state compatibility
   and maintenance feasibility before investing in another full trajectory
   agent.  Animal survival and fresh-crop safety remain lexicographic gates.
