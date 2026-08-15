# E2 S2 decision

**E2_S2_REMEDIATION_REQUIRED**

The S2 run is technically complete and trustworthy: all 32 controls and 32
candidate games ended `DONE`/`DONE`, all 64 shard hashes and every retained
canonical artifact hash validate, stderr is empty, market lists stayed within
the ten-entry cap, and the maximum measured candidate/control p95 and call
latencies were `0.467 ms` and `19.756 ms`.

Boatlee `ac_3aa759d7d7fc4a409c409326` is not eligible for a later tier in its
current always-on form. Its 32-context S2 result is 23/0/9 with mean paired
margin `+209.19`, median `+131`, mean own-bank delta `+2217.94`, and no actual
win/loss change. The mean is fragile: the total paired gain is `+6694`, while
one Roman context contributes `+14235`; without that single outlier, the other
31 contexts average `-243.26`. The lower-quartile mean is `-2071.25`.

The failure is concentrated but repeatable. Roman is 3/0/5 in S2, with mean
`-173.75`, median `-2404`, and worst `-4212`. Across S1 plus S2 it is 6/0/6
with mean `-127.33`. Seat 1 also has negative S2 mean `-221.56`. The worst
Roman context improves Boatlee's own bank by `745` but improves Roman by
`4957`, producing the `-4212` margin: this directly confirms the public-market
externality that S2 was designed to detect. Other Roman losses include large
late milk and strawberry receipt reductions. There are no added crop deaths,
fresh-crop deaths, or animal escapes, although shed overflow rises by one or
two units in every context.

The intervention is a coupled market block: step 240 replaces `WOOL 16` plus
`WHEAT 2` sales with `WOOL 18`, and step 241 adds a `FERTILIZER 16` sale and
an additional hire request. Current evidence cannot attribute the tail to one
atom because those changes were never ablated separately. The shards also
retain only decision-state digests, not the public feature snapshots needed to
freeze a safe selector.

The next valid action is an attributable remediation version with step-240-only
and step-241-only diagnostic ablations, followed by a public-state-only guard if
the labels support one. S1/S2 seeds are now consumed and may be used only for
diagnostics or selector construction, never as fresh efficacy evidence. A new
formal-fresh confirmation requires separate authorization. v27 remains stopped,
lanes remain unpooled, and no later tier has been launched.
