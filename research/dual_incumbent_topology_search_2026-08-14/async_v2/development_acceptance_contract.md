# Development acceptance contract

- A genome can retain up to eight event-linked 8--48 turn windows and multiple
  route, market, and constant genes together.
- Search uses mutation/crossover and bounded populations, never a Cartesian
  enumeration of every knob combination.
- Every route gene spans 8--48 turns.  Unit genes have public actor-position
  entry checks and exact actor-position rejoin on the reference trace.
- Every displaced unit or market action is recorded as retained, reassigned,
  or reclaimed.
- Missing public entry state, missing private state needed by a structural
  action, actor drift, hand-count drift, or a failed rejoin preserves the
  incumbent action.
- Market selectors use public price/inventory and own route orders only.  They
  never receive opponent identity or private-opponent state.
- Engine physics are immutable.  Tunable "market constants" are policy-model
  weights, thresholds, release quantities, and ordering decisions only.
- Both lane populations have distinct candidates, artifacts, caches, scores,
  checkpoints, and Pareto archives.  No raw score or margin is pooled.
- Route, market, constants, and coupled islands remain lane-local; crossover is
  same-lane, and a novelty archive prevents repeated Cartesian expansion.
- Semantic no-ops and duplicate phenotypes are rejected before efficacy work.
  Cross-generation candidate/context cache entries are validated atomically;
  action-digest vectors deduplicate behavior before Pareto selection.
- Static capacity is compile-distinct nonempty semantic capacity, never an
  exact action-change count.  Observed behavior-changing rates require an
  exact lane-control action-digest comparison and retain observed action no-ops.
- Near-tie ranking considers opponent consistency, paired wins and losses,
  worst downside, own bank, and topology complexity in that order after
  technical validity.
- Fast and standalone candidates are exact from both seats; every retained
  technical game is `DONE/DONE`, deterministic, schema-valid, and within the
  latency gates.
- Process workers use Windows `spawn`; shards are single-writer; checkpoints
  are atomic; status is read-only; resume validates every frozen hash.  Worker
  default and cap are 15, and no process is launched with `DETACHED_PROCESS`.
- Development uses seed `811407` only and cannot unlock or launch formal
  fresh-seed tiers.
- The E1b progressive protocol is non-executable in development and explicitly
  forbids E2.  Retained E1 seeds are artifact inputs only, never rerun here.
- Formal authorization and seed freshness are independent.  Manifests classify
  technical, retained/consumed E1, fresh, and unclassified seeds separately.
- Formal schema-v2 protocols must explicitly partition every evaluation seed,
  match the frozen registry classification, and bind both file hashes into the
  launch authority.  Retained stages pass no fresh seeds; unknown seeds fail.
- The exact validated registry path/run-id/hash flows through preflight,
  execute, manifest, resume, summary, and status.  Default-registry fallback is
  forbidden for a formal protocol selecting a non-default registry.
- Configured seed categories are not execution evidence.  Preflight and its
  manifest keep execution-started/completed and all executed flags false.
