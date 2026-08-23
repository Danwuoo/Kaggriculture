# Boatlee selector fresh-confirmation decision

Decision: `PASS_MINIMUM_FRESH_CONFIRMATION_ADVANCE_TO_BROAD_ROBUSTNESS`

The frozen selector `e2boatlee_7f591d609cf14d89e6aa1599` completed its
smallest formal-fresh confirmation on two new seeds, four opponent families,
and both seats. All 32 official-engine games completed technically. The 16
paired contexts were 12 positive, 4 unchanged, and 0 negative, with mean
paired-margin delta `+150.5625`, worst delta `0`, and no Roman negative tail.

This passes the predeclared minimum falsification gate and supports a larger
Boatlee-local robustness search. It is not a promotion decision: the block had
only two independent seeds, produced no actual win/loss transition, and the
selector abstained in every Roman context. Preserve the exact selector bytes,
use only new seeds, stratify families and seats, and do not pool with v27.

The user explicitly authorized a comprehensive fresh search using roughly
70–85% CPU. That authorization permits the next frozen robustness tier, not an
automatic later tier, Kaggle submission, or promotion.
