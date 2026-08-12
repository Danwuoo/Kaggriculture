# Job-value residual frozen protocol

## Hypothesis and scope

The rejected starting mechanism is a market-first residual: retained market
experiments did not demonstrate a matched game-outcome gain, same-turn SELL
splitting does not improve the engine price curve, and the examined premium
output normally becomes sellable only at its scheduled SELL turn. This lane
therefore tests only a coupled local job change: one farmer or hand may take
control for four to eight turns, then rejoin the incumbent at its declared
position and actor index. A coupled HARVEST/transport/DROP/SELL chain is
eligible only when it changes first-sellable time; moving an already-sellable
SELL by itself is rejected.

The two incumbent strata remain separate: `v27_current_meta` and
`boatlee_v16_rc2_market_relay`. Opponents are only the other frozen incumbent
and frozen Kaito v21. Seed, seat, exact engine/configuration, and opponent are
paired between control and intervention.

## Frozen matrices

| Stage | Contexts | Maximum games | Purpose |
| --- | ---: | ---: | --- |
| Discovery | 16 | 64 | One shared control plus no more than three forced one-window candidates per context. |
| Screen | 32 | 64 | Frozen greedy candidate versus control on four fresh seeds. |
| Confirmation | 64 | 128 | Frozen candidate versus control on eight further fresh seeds. |

The reserved seed pools are disjoint: two discovery, four screen, and eight
confirmation seeds. The generated manifest records their exact values, the
audited engine fingerprint, controls, opponents, hashes, and prior-use scan.

## Stop gates

Stop discovery immediately for an invalid action, exception, timeout, market
list above ten, nondeterminism, or failed `DONE/DONE` termination. Stop the
lane if either incumbent has fewer than four positive or four negative labels,
if labels occupy only one job family, if most candidate windows cannot legally
rejoin within eight turns, or if a market candidate merely moves an
already-sellable order.

Do not freeze the greedy rule unless its 24- and 48-turn ledger values have
known, agreeing signs and it separates positive from negative forced labels.
Stop after screen unless each incumbent independently has at least one actual
loss/draw-to-win or draw-to-win outcome transition, more outcome improvements
than regressions, more positive than negative paired-margin deltas with a
positive median, non-negative outcome-transition net against each opponent
family, and improvements across more than one seed and seat. Margin or bank
gain alone cannot pass the screen.

Confirmation retains every game and stops promotion for any correctness or
reproduction failure, a negative opponent-family or seat-specific net, no
actual outcome improvement, a non-positive paired-margin median or sign count,
or an effect isolated to one seat. The lane also stops rather than escalating
if the greedy rule cannot beat always-incumbent, always-intervene, and
maintenance-first baselines, useful windows usually require a second actor or
larger touched-state model, or explaining the result requires approximating the
full farm. Asset deaths, escapes, overflow, and terminal inventory are recorded
economic outcomes; unexplained cascades stop the lane.
