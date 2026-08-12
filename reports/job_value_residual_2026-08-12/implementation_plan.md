# Dual-Incumbent Job-Value Residual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and falsify a bounded 24/48-turn job-value residual that can alter one worker for four to eight turns, rejoin either active incumbent legally, and earn a real paired game-outcome improvement separately on v27 and Boatlee.

**Architecture:** A shared offline lane freezes controls, captures exact-engine traces, mines event-anchored one-worker windows, forces one window per paired full game, and labels it from terminal outcomes. Only a passing discovery gate generates independently owned `job_windows.py` and `job_value.py` modules for each incumbent; runtime uses a conservative local ledger and abstains outside exact preconditions.

**Tech Stack:** Python 3 standard library for runtime and offline orchestration, `unittest`, the audited Kaggriculture interpreter loaded from the local Git object database, deterministic JSON/JSONL/GZip artifacts, and the existing standalone builders.

## Global Constraints

- Treat `v27_current_meta` and `boatlee_v16_rc2_market_relay` as separate first-class incumbents. Never pool their promotion evidence.
- Editable runtime source lives only under each incumbent's `development/` directory. Never hand-edit generated `main.py`.
- Do not edit `.vendor/`, `data/`, or `docs/`. Keep the user's untracked `data/replay/` read-only and outside every commit.
- Do not submit to Kaggle, push, open a PR, or change any remote state.
- Re-fingerprint both official files before every engine experiment. Required commit: `bded87b0d7879078c726a93a4884d044f79c4eed`; Python blob: `4b78842d0f2d4abf6e318a8248b6306454f5c714`; configuration blob: `0fcdf2c14c47d3bdc821c02e26263956cf0fd3d8`; Python SHA-256: `fb9215c5e21a25243e2d13e75b3d70a79cf7d78fff150a90f1bb5eacf9ba2bcf`; configuration SHA-256: `7f196f4aaf9b4e482fbd61ba4bf19f5cec4da0f81938ece756954035a65c0bb5`.
- Unit actions execute before market actions; SELL uses shed inventory only; same-turn DROP may fund a same-turn SELL; market lists are ordered and capped at ten.
- Runtime opponent features use public observations only. Never access or infer from an opponent's private inventory, identity, account, or team.
- Runtime code is standard-library-only and performs no networking, subprocesses, multiprocessing, file writes, or verbose logging.
- Keep the final legality projection immediately before returning an action.
- A residual controls one actor for four to eight turns, has one declared rejoin step, and never extends itself to repair a failed intervention.
- Asset loss is an economic result, not an automatic failure. Record and attribute it.
- Discovery must contain at least four positive and four negative labels for each incumbent across at least two job families before runtime work begins.
- The first efficacy gate requires an actual `L→D/W` or `D→W` transition. Bank or margin gain alone cannot unlock confirmation.
- Use `apply_patch` for source edits. Stage explicit paths only and make a reviewable commit after every task.

---

## File and Responsibility Map

### Shared offline lane

- Create `research/job_value_residual_2026-08-12/protocol.py`: immutable paths, engine hashes, opponents, seed pools, and stage matrix.
- Create `research/job_value_residual_2026-08-12/freeze_protocol.py`: freeze the two generated controls and write their hash manifest.
- Create `research/job_value_residual_2026-08-12/engine_runner.py`: exact-engine execution, complete candidate trace, action digests, economic events, and optional policy wrapping.
- Create `research/job_value_residual_2026-08-12/schema.py`: typed candidate-window, requirement, market directive, ledger, and paired-label records.
- Create `research/job_value_residual_2026-08-12/window_search.py`: event anchors, deterministic grid routing, candidate construction, and static validation.
- Create `research/job_value_residual_2026-08-12/forced_policy.py`: one-window policy wrapper with fail-closed preconditions and rejoin accounting.
- Create `research/job_value_residual_2026-08-12/ledger.py`: mutually exclusive 24/48-turn value components and public opponent shipment tracker.
- Create `research/job_value_residual_2026-08-12/analysis.py`: labels, sign metrics, outcome transitions, stage gates, and stratified summaries.
- Create `research/job_value_residual_2026-08-12/run_discovery.py`: 16 shared controls plus at most 48 forced-candidate games.
- Create `research/job_value_residual_2026-08-12/freeze_windows.py`: deterministically render separately owned runtime window tables from passing discovery evidence.
- Create `research/job_value_residual_2026-08-12/run_efficacy.py`: frozen screen and confirmation matrices.
- Create `research/job_value_residual_2026-08-12/validate_candidate_representations.py`: generated-versus-development exact equivalence and determinism.
- Create `research/job_value_residual_2026-08-12/verify_artifact.py`: isolated archive import, official game, imports, size, and package checks.
- Create `research/job_value_residual_2026-08-12/test_support.py`: deterministic offline observations, windows, policies, and synthetic gate rows used only by tests.
- Create focused `test_*.py` files beside those modules; run them with `unittest discover` because the dated directory is not an importable package name.

### v27-owned runtime

- Create `research/main_approach/v27_current_meta/development/job_windows.py`: generated immutable v27-only candidate table and threshold.
- Create `research/main_approach/v27_current_meta/development/job_value.py`: v27-only runtime state, public tracker, ledger score, selector, override, and fallback.
- Modify `research/main_approach/v27_current_meta/development/agent.py:8-31`: insert the job residual after existing incumbent behavior and before final SELL ranking/projection.
- Modify `research/main_approach/v27_current_meta/development/build_standalone.py:15`: include both new modules before `agent.py`.
- Rebuild `research/main_approach/v27_current_meta/main.py`; never edit it directly.

### Boatlee-owned runtime

- Create `research/main_approach/boatlee_v16_rc2_market_relay/development/job_windows.py`: generated immutable Boatlee-only candidate table and threshold.
- Create `research/main_approach/boatlee_v16_rc2_market_relay/development/job_value.py`: Boatlee-only runtime state, tracker, score, selector, override, and fallback.
- Modify `research/main_approach/boatlee_v16_rc2_market_relay/development/agent.py:11-45`: abstain during weed/yarn/relay activity, otherwise apply the residual before the final projection.
- Modify `research/main_approach/boatlee_v16_rc2_market_relay/development/build_standalone.py:15`: include both new modules before `agent.py`.
- Rebuild `research/main_approach/boatlee_v16_rc2_market_relay/main.py`; never edit it directly.

### Cross-incumbent tests and reports

- Create `research/main_approach/job_value_test_support.py`: shared synthetic observation/configuration helpers; it is test-only and never imported by either runtime.
- Create `research/main_approach/test_job_value_residual_v27.py`: v27 runtime contract.
- Create `research/main_approach/test_job_value_residual_boatlee.py`: Boatlee runtime contract.
- Create `reports/job_value_residual_2026-08-12/protocol.md`: frozen hypotheses, matrices, and stop rules.
- Generate `reports/job_value_residual_2026-08-12/decision_discovery.md`, `decision_screen.md`, and `decision.md` only as their stages finish.

---

### Task 1: Freeze Protocol, Controls, Opponents, and Fresh Seeds

**Files:**
- Create: `research/job_value_residual_2026-08-12/protocol.py`
- Create: `research/job_value_residual_2026-08-12/freeze_protocol.py`
- Create: `research/job_value_residual_2026-08-12/test_protocol.py`
- Create: `reports/job_value_residual_2026-08-12/protocol.md`
- Generate: `research/job_value_residual_2026-08-12/controls/v27_current_meta/main.py`
- Generate: `research/job_value_residual_2026-08-12/controls/boatlee_v16_rc2_market_relay/main.py`
- Generate: `research/job_value_residual_2026-08-12/artifacts/prechange_manifest.json`

**Interfaces:**
- Produces: `INCUMBENTS: tuple[str, ...]`, `DISCOVERY_SEEDS`, `SCREEN_SEEDS`, `CONFIRMATION_SEEDS`, `candidate_path(name)`, `control_path(name)`, `opponent_path(incumbent, family)`, `readable_route(incumbent)`, and `stage_contexts(stage)`.
- Produces: an immutable manifest consumed by every later runner.

- [ ] **Step 1: Write the failing protocol tests**

```python
class ProtocolTests(unittest.TestCase):
    def test_seed_pools_are_disjoint_and_have_exact_sizes(self):
        pools = [DISCOVERY_SEEDS, SCREEN_SEEDS, CONFIRMATION_SEEDS]
        self.assertEqual([2, 4, 8], [len(pool) for pool in pools])
        self.assertEqual(14, len(set().union(*map(set, pools))))

    def test_stage_context_counts(self):
        self.assertEqual(16, len(stage_contexts("discovery")))
        self.assertEqual(32, len(stage_contexts("screen")))
        self.assertEqual(64, len(stage_contexts("confirmation")))

    def test_opponents_are_frozen_other_incumbent_or_kaito(self):
        for incumbent in INCUMBENTS:
            self.assertTrue(opponent_path(incumbent, "other_incumbent").is_file())
            self.assertTrue(opponent_path(incumbent, "kaito_v21").is_file())
```

- [ ] **Step 2: Run the test and verify the protocol module is absent**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p test_protocol.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'protocol'`.

- [ ] **Step 3: Add the exact protocol constants and context constructor**

```python
INCUMBENTS = ("v27_current_meta", "boatlee_v16_rc2_market_relay")
DISCOVERY_SEEDS = (93687444, 65365230)
SCREEN_SEEDS = (76238482, 47896298, 37504575, 22465322)
CONFIRMATION_SEEDS = (
    22831087, 27715185, 39010211, 44100301,
    89716831, 79417473, 15516570, 28880297,
)
OPPONENT_FAMILIES = ("other_incumbent", "kaito_v21")

def stage_contexts(stage):
    seeds = {
        "discovery": DISCOVERY_SEEDS,
        "screen": SCREEN_SEEDS,
        "confirmation": CONFIRMATION_SEEDS,
    }[stage]
    return tuple(
        (incumbent, family, seed, seat)
        for incumbent in INCUMBENTS
        for family in OPPONENT_FAMILIES
        for seed in seeds
        for seat in (0, 1)
    )
```

Also include the exact engine commit/blob/SHA constants from Global Constraints and absolute paths derived from `Path(__file__).resolve().parents[2]`. `opponent_path(name, "other_incumbent")` must point to the other frozen control, never to a mutable working candidate.

- [ ] **Step 4: Implement the freeze script and protocol report**

`freeze_protocol.py` must import the verified performance harness by inserting `research/main_approach/performance_optimization_2026_08_11` on `sys.path`, call `engine_fingerprint()`, copy both current generated artifacts into `controls/`, hash controls and opponents, scan `reports/` and `research/` outside this new lane for all 14 seeds, and refuse to overwrite a differing frozen control.

```python
def freeze_file(source, target):
    raw = source.read_bytes()
    if target.exists() and target.read_bytes() != raw:
        raise RuntimeError(f"frozen control differs: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(raw)
    return {"path": str(target), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
```

The report must name the rejected market-first mechanism, the one-worker/four-to-eight-turn intervention, the 64/64/128 maximum matrices, and every stop gate from the approved design.

- [ ] **Step 5: Run freeze and verify the tests and manifest**

Run:

```powershell
python research\job_value_residual_2026-08-12\freeze_protocol.py
python -m unittest discover -s research\job_value_residual_2026-08-12 -p test_protocol.py -v
git diff --check
```

Expected: protocol tests PASS; the manifest reports both audited engine hashes, two frozen controls, two opponent families, zero prior seed hits, and disjoint seed pools.

- [ ] **Step 6: Commit only Task 1 files**

```powershell
git add -- reports/job_value_residual_2026-08-12/protocol.md research/job_value_residual_2026-08-12/protocol.py research/job_value_residual_2026-08-12/freeze_protocol.py research/job_value_residual_2026-08-12/test_protocol.py research/job_value_residual_2026-08-12/controls research/job_value_residual_2026-08-12/artifacts/prechange_manifest.json
git commit -m "Freeze job-value residual protocol"
```

### Task 2: Build an Exact-Engine Trace Runner

**Files:**
- Create: `research/job_value_residual_2026-08-12/engine_runner.py`
- Create: `research/job_value_residual_2026-08-12/test_engine_runner.py`

**Interfaces:**
- Consumes: Task 1 paths, seeds, frozen controls, and engine manifest.
- Produces: `TraceFrame`, `GameRun`, `PolicyFactory`, `assert_engine_current()`, `run_game(...)`, `behavior_view(...)`, and `write_trace_gzip(...)`.

Use these exact record fields:

```python
@dataclass(frozen=True)
class TraceFrame:
    step: int
    observation: dict[str, Any]
    action: dict[str, Any]
    latency_ms: float

@dataclass
class GameRun:
    incumbent: str
    opponent_family: str
    seed: int
    seat: int
    summary: dict[str, Any]
    trace: list[TraceFrame]
    policy_metadata: dict[str, Any]
```

- [ ] **Step 1: Write failing runner tests**

```python
class EngineRunnerTests(unittest.TestCase):
    def test_full_game_has_719_calls_and_stable_digest(self):
        path = control_path("v27_current_meta")
        first = run_game("v27_current_meta", path, "kaito_v21", 93687444, 0, capture_trace=True)
        second = run_game("v27_current_meta", path, "kaito_v21", 93687444, 0, capture_trace=False)
        self.assertEqual(["DONE", "DONE"], first.summary["statuses"])
        self.assertEqual(719, len(first.trace))
        self.assertEqual(719, first.summary["calls"])
        self.assertEqual(first.summary["action_digest"], second.summary["action_digest"])
        self.assertEqual(first.summary["rewards"], second.summary["rewards"])

    def test_trace_contains_only_own_private_view(self):
        run = run_game("v27_current_meta", control_path("v27_current_meta"), "kaito_v21", 93687444, 1, capture_trace=True)
        self.assertIn("private", run.trace[0].observation)
        self.assertNotIn("opponent_private", run.trace[0].observation)
```

- [ ] **Step 2: Run the tests and verify the runner is absent**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p test_engine_runner.py -v
```

Expected: FAIL importing `engine_runner`.

- [ ] **Step 3: Implement the runner around the verified harness loader**

Import `harness.load_engine`, `harness.configuration`, `harness.load_agent`, `harness.invoke`, `harness.structify`, and `harness.plain`. Reuse those functions without modifying the historical performance lane. Add a policy-factory hook after loading the candidate:

```python
PolicyFactory = Callable[[Any, Callable[..., dict], int], Callable[..., dict]]

def run_game(incumbent, candidate_path, opponent_family, seed, seat, *, policy_factory=None, capture_trace=False):
    module, policy, import_ms = harness.load_agent(candidate_path, f"job_{incumbent}_{seed}_{seat}")
    metadata = {}
    if policy_factory is not None:
        policy = policy_factory(module, policy, seat)
        metadata = getattr(policy, "metadata", metadata)
```

`assert_engine_current()` must call `harness.engine_fingerprint()` afresh and compare the complete returned commit, blobs, and both SHA-256 values with Task 1's immutable manifest. Call it once at the start of every discovery, representation, screen, confirmation, and artifact-verification process before launching a game.

The game loop must record the pre-action observation and returned action for the candidate, both players' action digests, 719 call counts, rewards, money, statuses, exceptions, hand alignment, seed overcommit, market overflow, actual overflow discard, crop deaths, fresh-crop deaths, animal escapes, terminal inventory, remaining overage, and p50/p95/max latency. Do not read opponent-private state while constructing candidate trace features.

Use these exact `summary` keys throughout later tasks: `statuses`, `calls`, `rewards`, `money`, `action_digest`, `opponent_action_digest`, `action_issues`, `max_market_orders`, `diagnostics`, `terminal_inventory`, `exception`, `opponent_exception`, `timeout_calls`, `overage_exhausted`, `latency_ms`, and `engine_fingerprint`. `rewards` and `money` are two-element lists in seat order; derive a candidate margin by subtracting the opponent element from the candidate-seat element.

- [ ] **Step 4: Add deterministic trace serialization**

```python
def write_trace_gzip(path, run):
    payload = {
        "summary": run.summary,
        "trace": [asdict(frame) for frame in run.trace],
        "policy_metadata": run.policy_metadata,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
```

- [ ] **Step 5: Run runner tests and inspect validity**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p test_engine_runner.py -v
```

Expected: all tests PASS; both games end `DONE/DONE`, have identical candidate digests/rewards, 719 calls, no exceptions, no malformed actions, and no timeout.

- [ ] **Step 6: Commit the runner**

```powershell
git add -- research/job_value_residual_2026-08-12/engine_runner.py research/job_value_residual_2026-08-12/test_engine_runner.py
git commit -m "Add exact job-window trace runner"
```

### Task 3: Define and Mine Event-Anchored Candidate Windows

**Files:**
- Create: `research/job_value_residual_2026-08-12/schema.py`
- Create: `research/job_value_residual_2026-08-12/window_search.py`
- Create: `research/job_value_residual_2026-08-12/test_support.py`
- Create: `research/job_value_residual_2026-08-12/test_window_search.py`

**Interfaces:**
- Consumes: `TraceFrame` sequences and each incumbent's readable route.
- Produces: `Requirement`, `SellDirective`, `MarketShift`, `HorizonEffect`, `CandidateWindow`, `shortest_actions(...)`, `mine_candidates(...)`, and `validate_window(...)`.

Define the schema with immutable tuples so serialization and ordering are deterministic:

```python
@dataclass(frozen=True)
class Requirement:
    field: str
    key: tuple[Any, ...]
    operator: str
    value: Any

@dataclass(frozen=True)
class SellDirective:
    offset: int
    product: str
    quantity: int

@dataclass(frozen=True)
class MarketShift:
    product: str
    quantity: int
    control_offset: int
    candidate_offset: int
    provenance: str

@dataclass(frozen=True)
class HorizonEffect:
    horizon: int
    cash_coins: float
    liquidatable: tuple[tuple[str, int, str], ...]
    asset: tuple[tuple[str, int, str], ...]
    capacity: tuple[tuple[str, int, str], ...]
    market: tuple[MarketShift, ...]

@dataclass(frozen=True)
class CandidateWindow:
    candidate_id: str
    incumbent: str
    family: str
    trigger_step: int
    actor: int
    rejoin_step: int
    actions: tuple[tuple[str, ...], ...]
    expected_positions: tuple[tuple[int, int], ...]
    requirements: tuple[Requirement, ...]
    sell_directives: tuple[SellDirective, ...]
    displaced_actions: tuple[tuple[str, ...], ...]
    touched_tiles: tuple[tuple[int, int], ...]
    effects: tuple[HorizonEffect, ...] = ()
```

Actor index zero is the farmer; hand `n` is actor index `n + 1`.
Allowed requirement operators are `eq`, `ge`, and `le`. Allowed fields are `hands`, `actor_position`, `tile_kind`, `tile_product`, `tile_yield`, `actor_inventory`, `shed`, and `money`. Keys are empty for hands/money, `(actor,)` for actor position, `(x, y)` for tile checks, and `(actor, product)` or `(product,)` for inventory and shed checks. Any other field/operator is a static validation error.

- [ ] **Step 1: Add deterministic test fixtures**

`test_support.py` must define `observation_fixture`, `candidate_fixture`, `base_policy`, `passing_discovery_summary`, and `matched_rows`. Use a 10×10 public farm with the farmer plus a configurable number of hands, own private shed/inventories, market prices/inventory for every sellable product, and no opponent-private field. `candidate_fixture` returns a four-turn actor-1 productive detour with five expected positions, one touched tile, no market directive, and rejoin at trigger+4. `base_policy` returns PASS for every actor and no market orders. The two summary helpers must return new dictionaries/lists on every call so tests cannot share mutations.

```python
def base_policy(obs, configuration=None):
    farm = obs["farms"][int(obs.get("player", 0))]
    return {
        "farmer": ["PASS"],
        "hands": [["PASS"] for _ in farm.get("hands", [])],
        "market": [],
    }
```

`passing_discovery_summary()` returns keys for both incumbent names; each value has `positive=4`, `negative=4`, `families=["maintenance_trade", "productive_detour"]`, `legal_rejoin_rate=1.0`, `technical_failures=0`, `score_accuracy=0.75`, and all three baseline accuracies equal to `0.5`. `matched_rows(...)` expands its outcome pairs into rows with `control_outcome`, `candidate_outcome`, `margin_delta`, `opponent_family`, `seat`, and `seed`, cycling supplied family/seat/seed values without inventing a player identity.

- [ ] **Step 2: Write failing path and static-contract tests**

```python
class WindowSearchTests(unittest.TestCase):
    def test_shortest_path_is_deterministic(self):
        self.assertEqual(("EAST", "EAST", "SOUTH"), shortest_actions((0, 0), (2, 1)))

    def test_window_is_one_actor_four_to_eight_turns_and_rejoins(self):
        window = candidate_fixture()
        errors = validate_window(window)
        self.assertEqual([], errors)
        self.assertGreaterEqual(len(window.actions), 4)
        self.assertLessEqual(len(window.actions), 8)
        self.assertEqual(window.rejoin_step, window.trigger_step + len(window.actions))
        self.assertEqual(len(window.expected_positions), len(window.actions) + 1)

    def test_market_only_shift_is_rejected(self):
        window = replace(candidate_fixture(), family="logistics_market", actions=(("PASS",),) * 4, sell_directives=(SellDirective(0, "MILK", 6),))
        self.assertIn("market_without_delivery", validate_window(window))
```

- [ ] **Step 3: Run the tests and verify the modules are absent**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p test_window_search.py -v
```

Expected: FAIL importing `schema` or `window_search`.

- [ ] **Step 4: Implement deterministic movement and actor trace helpers**

Use fixed neighbor order `EAST, SOUTH, WEST, NORTH`; clamp coordinates to the 10×10 farm; treat LOCKED tiles as traversable. Reconstruct the baseline actor's position before each decision from trace observations rather than assuming a movement succeeded.

```python
DELTAS = {"EAST": (1, 0), "SOUTH": (0, 1), "WEST": (-1, 0), "NORTH": (0, -1)}
OPPOSITE = {"EAST": "WEST", "WEST": "EAST", "NORTH": "SOUTH", "SOUTH": "NORTH"}

def shortest_actions(start, target):
    x, y = start
    tx, ty = target
    result = []
    result.extend(["EAST" if tx > x else "WEST"] * abs(tx - x))
    result.extend(["SOUTH" if ty > y else "NORTH"] * abs(ty - y))
    return tuple(result)
```

- [ ] **Step 5: Implement the three candidate families**

Create anchors for maintenance deadlines, harvestable/fertilized output, carried cargo, projected shed occupancy at least 85, SELL collisions with a coupled delivery, the final 48 meaningful turns, PASS, and immediate opposite moves. Do not create a candidate merely because a SELL exists or because a move can be deleted.

For every trace frame, create anchors only for:

1. `maintenance_trade`: the baseline window contains WATER, FEED, or CARE; the candidate reaches one harvest/logistics target and returns while the maintenance job is displaced.
2. `productive_detour`: the baseline contains PASS or an immediate opposite move pair; the candidate reaches one currently legal HARVEST, WATER, FEED, CARE, DROP, or DIG target and returns. When the same actor already visits two legal job targets inside a four-to-eight-turn baseline window, also enumerate the reversed job order and retain it only when it reaches the same rejoin position without adding a second actor.
3. `logistics_market`: the actor already carries a sellable product or harvests it inside the window, reaches shed access, DROPs it, optionally appends one SELL for no more than the delivered quantity, and returns. Capacity anchors require projected occupancy at least 85; terminal anchors require trigger step at least 671 and use the remaining episode instead of a full 48-turn horizon.

Enumerate window lengths from four through eight. A candidate path is `start → target → job → rejoin_position`, padded only with baseline actions that preserve the candidate position. Reject HIRE, BUY_LAND, BUILD, PLANT, seed changes, a second actor, more than one SELL directive, or overlap with a control action that differs from the readable route because an incumbent overlay was active.

Sort candidates by `(family, trigger_step, actor, len(actions), candidate_id)` and retain at most one candidate per family in each incumbent/opponent/seed/seat context. The structural tie-break is shortest window, then larger public yield/cargo, then lexicographic ID; never use terminal outcome to choose the discovery candidate.

Construct `candidate_id` only from incumbent, trigger step, actor, family, action sequence, requirements, and SELL directive. Do not include seed, seat, opponent, reward, or terminal label; the same structural window must therefore aggregate across discovery contexts.

- [ ] **Step 6: Implement static validation and schema round-trip**

`validate_window` must return named errors for `wrong_incumbent`, `unknown_family`, `window_length`, `rejoin_step`, `position_count`, `forbidden_opcode`, `multiple_actors`, `market_without_delivery`, `sell_quantity`, and `more_than_one_sell`. Add `to_json`/`from_json` helpers that preserve exact tuple order and candidate ID.

- [ ] **Step 7: Run all offline unit tests**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p "test_*.py" -v
```

Expected: protocol, engine-runner, path, schema, and candidate-contract tests PASS.

- [ ] **Step 8: Commit the candidate miner**

```powershell
git add -- research/job_value_residual_2026-08-12/schema.py research/job_value_residual_2026-08-12/window_search.py research/job_value_residual_2026-08-12/test_support.py research/job_value_residual_2026-08-12/test_window_search.py
git commit -m "Add bounded job-window discovery"
```

### Task 4: Force One Window and Compute a Non-Duplicating Ledger

**Files:**
- Create: `research/job_value_residual_2026-08-12/forced_policy.py`
- Create: `research/job_value_residual_2026-08-12/ledger.py`
- Create: `research/job_value_residual_2026-08-12/test_forced_policy.py`
- Create: `research/job_value_residual_2026-08-12/test_ledger.py`

**Interfaces:**
- Consumes: `CandidateWindow`, an incumbent module/policy, and trace observations.
- Produces: `make_forced_factory(window)`, `requirements_hold(...)`, `apply_actor_action(...)`, `LedgerBreakdown`, `value_effect(...)`, `derive_horizon_effects(...)`, `estimate_window(...)`, and `update_public_inbound(...)`.

- [ ] **Step 1: Write failing forced-window tests**

```python
class ForcedPolicyTests(unittest.TestCase):
    def test_only_declared_actor_changes(self):
        window = candidate_fixture(trigger_step=10, actor=2)
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        obs = observation_fixture(step=10, hands=3, actor_positions=window.expected_positions[:1])
        base = base_policy(obs)
        changed = wrapped(obs)
        self.assertEqual(base["farmer"], changed["farmer"])
        self.assertEqual(base["hands"][0], changed["hands"][0])
        self.assertEqual(list(window.actions[0]), changed["hands"][1])
        self.assertEqual(base["hands"][2], changed["hands"][2])

    def test_failed_midwindow_precondition_aborts_without_extension(self):
        window = candidate_fixture(trigger_step=10, actor=1)
        wrapped = make_forced_factory(window)(object(), base_policy, 0)
        wrapped(observation_fixture(step=10, hands=2, actor_positions=window.expected_positions[:1]))
        result = wrapped(observation_fixture(step=11, hands=1, actor_positions=((9, 9),)))
        self.assertEqual(base_policy(observation_fixture(step=11, hands=1, actor_positions=((9, 9),))), result)
        self.assertEqual("aborted", wrapped.metadata["status"])
        self.assertEqual(11, wrapped.metadata["abort_step"])
```

- [ ] **Step 2: Write failing ledger and public-data tests**

```python
class LedgerTests(unittest.TestCase):
    def test_components_do_not_double_count_product_units(self):
        effect = HorizonEffect(
            horizon=24,
            cash_coins=100.0,
            liquidatable=(("MILK", 3, "cargo-a"),),
            asset=(("WOOL", -4, "asset-b"),),
            capacity=(("STRAWBERRY", 2, "inflight-c"),),
            market=(MarketShift("MILK", 1, 4, 1, "sale-d"),),
        )
        result = value_effect(
            effect,
            {"MILK": 20, "WOOL": 10, "STRAWBERRY": 30},
            {"sale-d": 7.0},
        )
        self.assertEqual(100.0, result.cash)
        self.assertEqual(60.0, result.liquidatable)
        self.assertEqual(-40.0, result.asset)
        self.assertEqual(60.0, result.capacity)
        self.assertEqual(7.0, result.market)
        self.assertEqual(187.0, result.total)

    def test_opponent_private_field_cannot_change_inbound_tracker(self):
        state_a = update_public_inbound({}, observation_fixture(step=100), 0)
        obs = observation_fixture(step=100)
        obs["opponent_private"] = {"shed": {"MILK": 999999}}
        state_b = update_public_inbound({}, obs, 0)
        self.assertEqual(state_a, state_b)
```

- [ ] **Step 3: Run tests and verify both modules are absent**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p "test_forced_policy.py" -v
python -m unittest discover -s research\job_value_residual_2026-08-12 -p "test_ledger.py" -v
```

Expected: both commands FAIL importing their target modules.

- [ ] **Step 4: Implement fail-closed forced execution**

The wrapper calls the incumbent policy first on every turn. Before trigger it returns the incumbent action unchanged. On offsets zero through `len(actions)-1`, it verifies actor count, declared actor position, and every requirement, copies the full incumbent action, replaces exactly one actor action, appends at most one legal SELL directive, and records the applied action. On mismatch it clears the active state and returns that turn's complete incumbent action. At `rejoin_step` it verifies the final expected position, records `rejoined` or `failed_rejoin`, and never overrides another turn.

For SELL legality, start with own pre-action shed quantity, add only the declared actor's carried quantity when that actor's same-turn override is DROP at shed access, then subtract earlier incumbent SELL orders for the same product. Cap the directive at that remaining quantity and reject rather than split when the exact declared quantity is unavailable.

```python
def apply_actor_action(action, actor, order):
    changed = {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(item or ["PASS"]) for item in action.get("hands", [])],
        "market": [list(item) for item in action.get("market", [])],
    }
    if actor == 0:
        changed["farmer"] = list(order)
    else:
        changed["hands"][actor - 1] = list(order)
    return changed
```

- [ ] **Step 5: Implement the mutually exclusive value ledger**

Reject an effect if the provenance key in any `liquidatable`, `asset`, or `capacity` row appears in another of those buckets. `cash_coins` excludes timing premium from shifted product sales. Each `MarketShift` stores product, quantity, control/candidate offsets, and provenance rather than discovery-time coin value. `value_effect` receives a per-provenance timing adjustment equal to `quantity × (shifted_quote - reference_quote)`. Products sold within the horizon contribute through cash; harvested unsold products through liquidatable; unharvested output through asset; and units still in flight solely because of capacity through capacity.

```python
@dataclass(frozen=True)
class LedgerBreakdown:
    cash: float
    liquidatable: float
    asset: float
    capacity: float
    market: float

    @property
    def total(self):
        return self.cash + self.liquidatable + self.asset + self.capacity + self.market
```

Compute both horizons, use conservative post-own-impact prices, and return unknown rather than inventing a value when a requirement or product quote is missing.

- [ ] **Step 6: Derive frozen effects from paired traces**

`derive_horizon_effects(control_trace, candidate_trace, window)` takes snapshots at `min(trigger+24, 718)` and `min(trigger+48, 718)`. For each touched product, partition the paired state delta into exactly one unsold bucket: carried/shed inventory becomes `liquidatable`, public yield still on a touched crop/animal becomes `asset`, and a runner-recorded unit still in flight solely because shed capacity delayed it becomes `capacity`. Split shifted-sale money so `cash_coins` is the paired money delta minus the realized timing adjustment; store the conserved product, quantity, and two offsets as `MarketShift`, while retaining the observed timing coins only in discovery diagnostics. Refuse the effect when a provenance key occurs in two unsold buckets or when shifted-sale quantity cannot be conserved.

When the same structural `candidate_id` occurs in multiple discovery contexts, aggregate every numeric field by median only if bucket assignment and sign agree in at least two independent contexts. Otherwise mark that candidate `unstable_effect` and exclude it from runtime freezing while retaining all raw rows.

- [ ] **Step 7: Implement legal public shipment inference**

Track only consecutive opponent farm snapshots. Infer cargo when a public tile's `yield_units` decreases while an identifiable public actor occupies that tile; map plants to their crop and COW/SHEEP to MILK/WOOL. Carry a conservative lower bound by actor index and public position, compute Manhattan distance to shed access, and clear the bound on day reset, hand-count change, ambiguous multi-actor harvest, or unexplained market supply. Never read any field outside public farms, market, town, money, day, hour, and step.

- [ ] **Step 8: Run the full offline test suite**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p "test_*.py" -v
```

Expected: all tests PASS, including forced abort/rejoin, no double counting, and opponent-private invariance.

- [ ] **Step 9: Commit forced execution and ledger**

```powershell
git add -- research/job_value_residual_2026-08-12/forced_policy.py research/job_value_residual_2026-08-12/ledger.py research/job_value_residual_2026-08-12/test_forced_policy.py research/job_value_residual_2026-08-12/test_ledger.py
git commit -m "Add forced job-window counterfactuals"
```

### Task 5: Run the 64-Game Discovery and Enforce the Stop Gate

**Files:**
- Create: `research/job_value_residual_2026-08-12/analysis.py`
- Create: `research/job_value_residual_2026-08-12/run_discovery.py`
- Create: `research/job_value_residual_2026-08-12/freeze_windows.py`
- Create: `research/job_value_residual_2026-08-12/test_analysis.py`
- Create: `research/main_approach/job_value_test_support.py`
- Generate: `research/job_value_residual_2026-08-12/artifacts/control_traces/*.json.gz`
- Generate: `research/job_value_residual_2026-08-12/artifacts/discovery_games.jsonl`
- Generate: `research/job_value_residual_2026-08-12/artifacts/discovery_windows.json`
- Generate: `research/job_value_residual_2026-08-12/artifacts/discovery_summary.json`
- Generate: `reports/job_value_residual_2026-08-12/decision_discovery.md`

**Interfaces:**
- Consumes: Tasks 1–4 and the 16 discovery contexts.
- Produces: `outcome(margin)`, `label_pair(control, candidate)`, `summarize_discovery(rows)`, `discovery_gate(summary)`, and complete machine evidence.

- [ ] **Step 1: Write failing label and gate tests**

```python
class AnalysisTests(unittest.TestCase):
    def test_outcome_transition_precedes_margin(self):
        label = label_pair({"margin": -1.0}, {"margin": 0.0})
        self.assertEqual("positive", label.sign)
        self.assertEqual("L_TO_D", label.outcome_transition)

    def test_unchanged_outcome_uses_terminal_margin_delta(self):
        label = label_pair({"margin": 10.0}, {"margin": 15.0})
        self.assertEqual("positive", label.sign)
        self.assertEqual("W_TO_W", label.outcome_transition)
        self.assertEqual(5.0, label.margin_delta)

    def test_gate_requires_both_signs_and_two_families_per_incumbent(self):
        summary = passing_discovery_summary()
        self.assertTrue(discovery_gate(summary)["pass"])
        summary["v27_current_meta"]["negative"] = 3
        self.assertFalse(discovery_gate(summary)["pass"])
```

- [ ] **Step 2: Run the test and verify analysis is absent**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p test_analysis.py -v
```

Expected: FAIL importing `analysis`.

- [ ] **Step 3: Implement labels, stratification, and exact gate rules**

For non-neutral candidates, compute score sign from `min(delta_value_24, delta_value_48)` after each incumbent's threshold. Compare its sign accuracy with three baselines: always intervene, maintenance-first, and always incumbent. A discovery stratum passes only if:

- technical failures are zero;
- positive labels are at least four;
- negative labels are at least four;
- labeled examples span at least two job families;
- legal rejoin rate is greater than 0.5;
- score-sign accuracy strictly exceeds every baseline's accuracy;
- no retained `logistics_market` candidate lacks HARVEST or DROP before SELL.

Select the threshold independently per incumbent from `(0.0, 25.0, 50.0, 100.0, 200.0)`. Maximize sign accuracy; then coverage; then choose the larger threshold. Store every candidate score at both horizons and do not remove losing candidates.

- [ ] **Step 4: Implement the two-phase discovery runner**

Phase A runs each of the 16 controls once with trace capture, writes a deterministic GZip trace, mines candidates, and retains no more than one per job family. Phase B runs one full official game per retained candidate by passing `make_forced_factory(window)` into `engine_runner.run_game`. Stop before launching another game if any completed row has an exception, malformed action, timeout, overage exhaustion, market overflow, or failed determinism repeat.

```python
for incumbent, opponent_family, seed, seat in stage_contexts("discovery"):
    control = run_game(incumbent, control_path(incumbent), opponent_family, seed, seat, capture_trace=True)
    windows = mine_candidates(control.trace, incumbent, readable_route(incumbent))[:3]
    for window in windows:
        candidate = run_game(
            incumbent,
            control_path(incumbent),
            opponent_family,
            seed,
            seat,
            policy_factory=make_forced_factory(window),
            capture_trace=True,
        )
        effects = derive_horizon_effects(control.trace, candidate.trace, window)
        append_discovery_row(control, candidate, replace(window, effects=effects))
```

Reuse the shared control within a context; this yields at most 16 controls plus 48 candidate games.

`freeze_windows.py` must verify the discovery and prechange-manifest hashes, require each structural candidate to have a stable aggregated effect from at least two independent contexts, insert the separately selected incumbent threshold, sort by trigger step and candidate ID, and render standalone Python literals with `pprint.pformat(sort_dicts=True)`. Unit-test that rendering the same frozen policy twice produces identical bytes.

Also add the runtime-only test helper now, outside both incumbent trees. It defines `load_runtime(strategy)`, `runtime_path(strategy)`, `observation_fixture`, `official_configuration`, and `window_dict`; no production module imports it.

- [ ] **Step 5: Run all unit tests before spending the game block**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p "test_*.py" -v
```

Expected: all tests PASS with zero failures.

- [ ] **Step 6: Run discovery and reproduce every retained game**

Run:

```powershell
python research\job_value_residual_2026-08-12\run_discovery.py --output research\job_value_residual_2026-08-12\artifacts
python research\job_value_residual_2026-08-12\run_discovery.py --verify-existing research\job_value_residual_2026-08-12\artifacts\discovery_games.jsonl
```

Expected: no more than 64 official games; every retained row reproduces statuses, rewards, action digests, label, and rejoin metadata.

- [ ] **Step 7: Apply the hard checkpoint**

If either incumbent fails discovery, write `decision_discovery.md` with `STOP_BEFORE_RUNTIME`, list the exact failed gates and all adverse results, commit the evidence, and do not execute Tasks 6–10. If both pass, write `PASS_TO_GREEDY_RUNTIME` with separately selected thresholds and continue. If only one passes, the approved dual-incumbent discovery requirement has failed; stop rather than silently converting this first lane into a pooled or single-line experiment.

- [ ] **Step 8: Commit discovery code and immutable evidence**

```powershell
git add -- research/job_value_residual_2026-08-12/analysis.py research/job_value_residual_2026-08-12/run_discovery.py research/job_value_residual_2026-08-12/freeze_windows.py research/job_value_residual_2026-08-12/test_analysis.py research/main_approach/job_value_test_support.py research/job_value_residual_2026-08-12/artifacts reports/job_value_residual_2026-08-12/decision_discovery.md
git commit -m "Run job-value residual discovery"
```

### Task 6: Generate and Integrate the v27 Runtime Residual

**Prerequisite:** Task 5 status is `PASS_TO_GREEDY_RUNTIME` for both incumbents.

**Files:**
- Create: `research/main_approach/v27_current_meta/development/job_windows.py`
- Create: `research/main_approach/v27_current_meta/development/job_value.py`
- Modify: `research/main_approach/v27_current_meta/development/agent.py:8-31`
- Modify: `research/main_approach/v27_current_meta/development/build_standalone.py:15`
- Consume: `research/main_approach/job_value_test_support.py`
- Create: `research/main_approach/test_job_value_residual_v27.py`
- Generate: `research/main_approach/v27_current_meta/main.py`

**Interfaces:**
- Produces v27-owned `_JOB_WINDOWS`, `_JOB_THRESHOLD`, `_job_reset(seat)`, `_job_tick(obs, configuration, step, seat, blocked=False)`, and `_job_apply(action, directive)`.
- `directive` is either `None` or a dict with `actor`, `action`, `market`, and `changed_market`.

- [ ] **Step 1: Write failing v27 tests using the Task 5 helper**

Use the already committed `job_value_test_support.py`, which defines `load_runtime(strategy)`, `runtime_path(strategy)`, `observation_fixture`, `official_configuration`, and `window_dict`. It loads modules through their full package name so relative imports work and clears that development package from `sys.modules` between tests. `window_dict` returns a four-turn, actor-1 window whose two horizon effects and requirements can be replaced by keyword arguments.

```python
class V27JobValueTests(unittest.TestCase):
    def test_tie_preserves_incumbent(self):
        module = load_runtime("v27_current_meta")
        module._JOB_WINDOWS = {100: (window_dict(score24=50.0, score48=50.0), window_dict(score24=50.0, score48=50.0))}
        module._job_reset(0)
        self.assertIsNone(module._job_tick(observation_fixture(step=100), official_configuration(), 100, 0))

    def test_rewind_and_seats_are_isolated(self):
        module = load_runtime("v27_current_meta")
        left = module._job_reset(0)
        right = module._job_reset(1)
        left["active"] = "left-only"
        module._job_tick(observation_fixture(step=0, player=1), official_configuration(), 0, 1)
        self.assertEqual("left-only", module._JOB_STATE[0]["active"])
        self.assertIsNone(module._JOB_STATE[1]["active"])

    def test_blocked_overlay_aborts_active_window(self):
        module = load_runtime("v27_current_meta")
        state = module._job_reset(0)
        state["active"] = "candidate-a"
        self.assertIsNone(module._job_tick(observation_fixture(step=101), official_configuration(), 101, 0, blocked=True))
        self.assertIsNone(state["active"])

    def test_soft_budget_abstains_and_clears_active_state(self):
        module = load_runtime("v27_current_meta")
        state = module._job_reset(0)
        state["active"] = "candidate-a"
        directive = {"actor": 1, "action": ["PASS"], "market": (), "changed_market": False}
        with mock.patch.object(module, "_continue_or_select", return_value=directive):
            with mock.patch.object(module.time, "perf_counter", side_effect=(0.0, 0.003)):
                self.assertIsNone(module._job_tick(observation_fixture(step=102), official_configuration(), 102, 0))
        self.assertIsNone(state["active"])
        self.assertEqual("budget", state["abstain_reason"])
```

- [ ] **Step 2: Run the focused tests and verify the modules are absent**

Run:

```powershell
python -m unittest research.main_approach.test_job_value_residual_v27 -v
```

Expected: FAIL because `development.job_value` does not exist.

- [ ] **Step 3: Implement deterministic window-table generation**

The Task 5 `freeze_windows.py` reads passing `discovery_summary.json` and `discovery_windows.json`, checks their prechange-manifest hash, filters only statically valid windows, inserts the separately selected v27 threshold and both horizon effects, sorts by step and candidate ID, and renders Python literals with `pprint.pformat(sort_dicts=True)`. Running it twice must produce byte-identical output.

```powershell
python research\job_value_residual_2026-08-12\freeze_windows.py --incumbent v27_current_meta --output research\main_approach\v27_current_meta\development\job_windows.py
```

- [ ] **Step 4: Implement the v27-owned runtime selector**

Use a seat-isolated state dictionary containing `last_step`, `active`, `offset`, `previous_opponent`, `inbound`, and `abstain_reason`. `_job_tick` first handles step zero/rewind, updates only public opponent state, aborts when `blocked`, continues an active window only while position and requirements match, and otherwise scores windows at the current step.

```python
_JOB_BUDGET_SECONDS = 0.002
_JOB_STATE = {0: _new_job_state(), 1: _new_job_state()}

def _job_tick(obs, configuration, step, seat, blocked=False):
    started = time.perf_counter()
    state = _JOB_STATE[seat]
    if step == 0 or step < state["last_step"]:
        state = _job_reset(seat)
    state["last_step"] = step
    _update_public_inbound(state, obs, seat, step)
    if blocked:
        state["active"] = None
        state["offset"] = 0
        return None
    directive = _continue_or_select(obs, configuration, step, seat, state)
    if time.perf_counter() - started > _JOB_BUDGET_SECONDS:
        state["active"] = None
        state["offset"] = 0
        state["abstain_reason"] = "budget"
        return None
    return directive
```

`_continue_or_select` requires both 24/48 values above `_JOB_THRESHOLD`, rejects opposite signs or unknown values, chooses the largest minimum score, and returns `None` on an exact tie. Missing observations, a requirement mismatch, hand-count mismatch, market length ten, illegal SELL quantity, or failed rejoin all return the complete incumbent behavior by producing no directive.

For each `MarketShift`, assign zero timing value unless the public inbound tracker has the same product with a conservative ETA between the candidate and control ready offsets. When supported, compute both quotes from current public market inventory after own quantity and the inferred lower-bound opponent quantity, then use only their difference as the market component. Discovery's realized timing coins are diagnostic and must not appear in `job_windows.py`.

`_job_apply` must validate actor range, hand count, order shape, SELL availability, and ten-order capacity before mutating the copied incumbent action. A failed validation returns `False` with the action byte-for-byte unchanged.

- [ ] **Step 5: Integrate v27 without bypassing weed repair or the projector**

In `agent.py`, reset job state alongside weed state. Compute weed state first and pass `blocked=weed`. Include `directive is None` in the static fast-path predicate. Materialize and apply weed repair first, then apply the directive, rerank SELL slots when either the original step has multiple SELLs or the directive changed market actions, and call `_project_action` last.

```python
directive = _job_tick(obs, configuration, step, seat, blocked=weed)
if aligned and not weed and step not in _MULTI_SELL_STEPS and directive is None:
    return template
action = _copy_action(template)
if weed:
    _weed_repair_action(action, actions, step, farm, game)
changed_market = _job_apply(action, directive) if directive is not None else False
if step in _MULTI_SELL_STEPS or changed_market:
    _rank_sell_slots(obs, action, configuration)
return _project_action(action, expected_hands)
```

- [ ] **Step 6: Add the modules to the v27 builder and rebuild**

Set:

```python
MODULES = ('constants.py', 'runtime.py', 'weed_repair.py', 'market.py', 'job_windows.py', 'job_value.py', 'agent.py')
```

Run:

```powershell
python research\main_approach\v27_current_meta\development\build_standalone.py
python research\main_approach\v27_current_meta\development\build_standalone.py --check
python -m unittest research.main_approach.test_job_value_residual_v27 -v
python -m unittest research.main_approach.test_development_sources -v
```

Expected: the new focused tests PASS, the builder check passes, and the shared source contract remains 3/3.

- [ ] **Step 7: Commit the independently owned v27 runtime**

```powershell
git add -- research/main_approach/test_job_value_residual_v27.py research/main_approach/v27_current_meta/development/job_windows.py research/main_approach/v27_current_meta/development/job_value.py research/main_approach/v27_current_meta/development/agent.py research/main_approach/v27_current_meta/development/build_standalone.py research/main_approach/v27_current_meta/main.py
git commit -m "Add v27 job-value residual runtime"
```

### Task 7: Generate and Integrate the Boatlee Runtime Residual

**Prerequisite:** Task 5 status is `PASS_TO_GREEDY_RUNTIME` for both incumbents.

**Files:**
- Create: `research/main_approach/boatlee_v16_rc2_market_relay/development/job_windows.py`
- Create: `research/main_approach/boatlee_v16_rc2_market_relay/development/job_value.py`
- Modify: `research/main_approach/boatlee_v16_rc2_market_relay/development/agent.py:11-45`
- Modify: `research/main_approach/boatlee_v16_rc2_market_relay/development/build_standalone.py:15`
- Create: `research/main_approach/test_job_value_residual_boatlee.py`
- Generate: `research/main_approach/boatlee_v16_rc2_market_relay/main.py`

**Interfaces:**
- Produces Boatlee-owned `_JOB_WINDOWS`, `_JOB_THRESHOLD`, `_job_reset(seat)`, `_job_tick(obs, configuration, step, seat, blocked=False)`, and `_job_apply(action, directive)`.
- No Boatlee runtime file may import the v27 runtime or its window table.

- [ ] **Step 1: Write failing Boatlee runtime and ownership tests**

```python
class BoatleeJobValueTests(unittest.TestCase):
    def test_boatlee_runtime_does_not_import_v27(self):
        source = runtime_path("boatlee_v16_rc2_market_relay").read_text(encoding="utf-8")
        self.assertNotIn("v27_current_meta", source)

    def test_relay_blocks_and_clears_job_window(self):
        module = load_runtime("boatlee_v16_rc2_market_relay")
        state = module._job_reset(0)
        state["active"] = "boatlee-window"
        result = module._job_tick(observation_fixture(step=278), official_configuration(), 278, 0, blocked=True)
        self.assertIsNone(result)
        self.assertIsNone(state["active"])

    def test_missing_public_features_fall_back(self):
        module = load_runtime("boatlee_v16_rc2_market_relay")
        module._job_reset(0)
        self.assertIsNone(module._job_tick({"step": 300, "player": 0}, official_configuration(), 300, 0))
```

- [ ] **Step 2: Run the focused tests and verify Boatlee modules are absent**

Run:

```powershell
python -m unittest research.main_approach.test_job_value_residual_boatlee -v
```

Expected: FAIL because Boatlee `development.job_value` does not exist.

- [ ] **Step 3: Generate a separate Boatlee window table**

Run the frozen renderer against the Boatlee stratum. It must use Boatlee's own threshold, requirements, effects, and IDs and write a complete Python literal rather than importing the v27 table.

```powershell
python research\job_value_residual_2026-08-12\freeze_windows.py --incumbent boatlee_v16_rc2_market_relay --output research\main_approach\boatlee_v16_rc2_market_relay\development\job_windows.py
```

- [ ] **Step 4: Implement the Boatlee-owned runtime selector**

Create an independent standard-library implementation with the same callable contract but Boatlee-specific state and constants. It must reset on step zero/rewind, update only public opponent state, enforce the two-millisecond soft budget, abstain on missing data or ties, and clear any active window when `blocked=True`. Do not import an offline module or any v27 module.

```python
def _job_apply(action, directive):
    if directive is None:
        return False
    actor = int(directive["actor"])
    if actor < 0:
        return False
    order = list(directive["action"])
    additions = [list(item) for item in directive.get("market", ())]
    if additions and len(action.get("market", [])) + len(additions) > 10:
        return False
    if actor > 0 and actor - 1 >= len(action.get("hands", [])):
        return False
    if actor == 0:
        action["farmer"] = order
    else:
        action["hands"][actor - 1] = order
    action.setdefault("market", []).extend(additions)
    return bool(additions)
```

All validation occurs before the first mutation, so an invalid directive leaves the complete incumbent action untouched.

- [ ] **Step 5: Integrate Boatlee after its incumbent overlays**

Reset job state with weed, livestock, wool, and relay state. Compute `blocked = weed or yarn or relay`. Include `directive is None` in the fast-path condition. Build the normal dynamic action, run the existing relay if active, apply a job directive only when unblocked, rerank SELL slots if the directive added market orders, then call `_project_action` last.

```python
directive = _job_tick(obs, configuration, step, seat, blocked=bool(weed or yarn or relay))
if aligned and not yarn and not relay and not weed and step not in _MULTI_SELL_STEPS and directive is None:
    return template
action = _v16_dynamic_action(obs, configuration, template, _REBALANCE_ACTIONS, step, seat, farm, weed_game, weed, yarn)
if relay:
    _rc2_market_relay(obs, action, step, configuration, relay_state)
changed_market = _job_apply(action, directive) if directive is not None else False
if changed_market:
    _rank_sell_slots(obs, action, configuration)
return _project_action(action, expected_hands)
```

- [ ] **Step 6: Add modules to the Boatlee builder and rebuild**

Set:

```python
MODULES = ('constants.py', 'runtime.py', 'weed_repair.py', 'market.py', 'livestock.py', 'wool.py', 'base_agent.py', 'relay.py', 'job_windows.py', 'job_value.py', 'agent.py')
```

Run:

```powershell
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
python -m unittest research.main_approach.test_job_value_residual_boatlee -v
python -m unittest research.main_approach.test_development_sources -v
```

Expected: Boatlee tests PASS, its builder is current, and the shared contract is 3/3.

- [ ] **Step 7: Commit the independently owned Boatlee runtime**

```powershell
git add -- research/main_approach/test_job_value_residual_boatlee.py research/main_approach/boatlee_v16_rc2_market_relay/development/job_windows.py research/main_approach/boatlee_v16_rc2_market_relay/development/job_value.py research/main_approach/boatlee_v16_rc2_market_relay/development/agent.py research/main_approach/boatlee_v16_rc2_market_relay/development/build_standalone.py research/main_approach/boatlee_v16_rc2_market_relay/main.py
git commit -m "Add Boatlee job-value residual runtime"
```

### Task 8: Verify Development/Generated Equivalence, Fallbacks, and Latency

**Files:**
- Create: `research/job_value_residual_2026-08-12/validate_candidate_representations.py`
- Create: `research/job_value_residual_2026-08-12/test_representation_validation.py`
- Generate: `research/job_value_residual_2026-08-12/artifacts/representation_validation.json`

**Interfaces:**
- Consumes: both generated candidates, both development entrypoints, frozen controls, discovery seeds, and both opponent families.
- Produces: exact candidate representation equivalence without requiring equality to the old incumbent.

- [ ] **Step 1: Write a failing representation-comparator test**

```python
class RepresentationValidationTests(unittest.TestCase):
    def test_digest_difference_fails_equivalence(self):
        left = {
            "statuses": ["DONE", "DONE"], "calls": 719,
            "rewards": [1.0, 2.0], "money": [1.0, 2.0],
            "action_digest": "left", "opponent_action_digest": "opponent",
            "action_issues": {}, "diagnostics": {}, "terminal_inventory": {},
            "exception": None, "opponent_exception": None,
            "timeout_calls": 0, "overage_exhausted": False, "max_market_orders": 2,
        }
        right = copy.deepcopy(left)
        self.assertTrue(representation_equal(left, right))
        right["action_digest"] = "right"
        self.assertFalse(representation_equal(left, right))
```

- [ ] **Step 2: Run the focused test and verify the validator is absent**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p test_representation_validation.py -v
```

Expected: FAIL importing `validate_candidate_representations`.

- [ ] **Step 3: Implement the representation validator**

For each incumbent, discovery seed, seat, and opponent family, run generated `main.py` and `development_main.py` on identical games. Compare statuses, 719-call count, both rewards, both money values, candidate and opponent action digests, action issues, economic diagnostics, terminal inventory, exceptions, timeout/overage, and maximum market list length. Record the frozen control in the same row but do not require candidate/control equality.

```python
def representation_equal(left, right):
    keys = (
        "statuses", "calls", "rewards", "money", "action_digest",
        "opponent_action_digest", "action_issues", "diagnostics",
        "terminal_inventory", "exception", "opponent_exception",
        "timeout_calls", "overage_exhausted", "max_market_orders",
    )
    return all(left[key] == right[key] for key in keys)
```

- [ ] **Step 4: Add determinism and performance checks**

Repeat generated candidates twice for both seats on seed `93687444` against Kaito v21. Require identical behavior views. Across every validation episode require p95 below 150 ms, maximum below 750 ms, zero technical failures, and at most ten market orders. Use captured control observations with the existing replay benchmark to report candidate season median, per-turn p95, and the number of dynamic returns.

- [ ] **Step 5: Run builders, all tests, and validation**

Run:

```powershell
python research\main_approach\v27_current_meta\development\build_standalone.py --check
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
python -m unittest research.main_approach.test_development_sources -v
python -m unittest discover -s research\main_approach -p "test_job_value_residual_*.py" -v
python -m unittest discover -s research\job_value_residual_2026-08-12 -p "test_*.py" -v
python research\job_value_residual_2026-08-12\validate_candidate_representations.py --output research\job_value_residual_2026-08-12\artifacts\representation_validation.json
```

Expected: every command exits zero; generated and development representations are exact from both seats; controls remain frozen; all validity and latency gates pass.

- [ ] **Step 6: Commit validation code and evidence**

```powershell
git add -- research/job_value_residual_2026-08-12/validate_candidate_representations.py research/job_value_residual_2026-08-12/test_representation_validation.py research/job_value_residual_2026-08-12/artifacts/representation_validation.json
git commit -m "Validate job-value residual artifacts"
```

### Task 9: Run the 64-Game Frozen Greedy Screen

**Files:**
- Create: `research/job_value_residual_2026-08-12/run_efficacy.py`
- Create: `research/job_value_residual_2026-08-12/test_efficacy.py`
- Generate: `research/job_value_residual_2026-08-12/artifacts/screen_games.jsonl`
- Generate: `research/job_value_residual_2026-08-12/artifacts/screen_summary.json`
- Generate: `reports/job_value_residual_2026-08-12/decision_screen.md`

**Interfaces:**
- Consumes: 32 screen contexts, each incumbent's frozen control and generated candidate.
- Produces: `efficacy_gate(rows)`, matched outcome transition, paired margin delta, bank deltas, stratified W/D/L, gate status, and passing-incumbent list.

- [ ] **Step 1: Write failing efficacy-gate tests**

```python
class EfficacyTests(unittest.TestCase):
    def test_margin_only_gain_fails(self):
        rows = matched_rows(outcomes=(("W", "W"), ("W", "W")), margin_deltas=(10.0, 5.0))
        self.assertFalse(efficacy_gate(rows)["pass"])

    def test_actual_improvement_with_no_family_regression_passes(self):
        rows = matched_rows(
            outcomes=(("L", "D"), ("D", "W"), ("W", "W"), ("W", "W")),
            margin_deltas=(1.0, 2.0, 3.0, -1.0),
            families=("other_incumbent", "kaito_v21", "other_incumbent", "kaito_v21"),
            seats=(0, 1, 1, 0),
            seeds=(76238482, 47896298, 37504575, 22465322),
        )
        self.assertTrue(efficacy_gate(rows)["pass"])
```

- [ ] **Step 2: Run the test and verify the efficacy runner is absent**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p test_efficacy.py -v
```

Expected: FAIL importing `run_efficacy`.

- [ ] **Step 3: Implement matched screen execution and gate**

For every screen context, run the frozen control and generated candidate against the exact same frozen opponent. Store both raw rows. Per incumbent require:

- at least one `L→D/W` or `D→W` transition;
- improved outcome count greater than worsened outcome count;
- positive paired-margin count greater than negative count;
- positive paired-margin median;
- non-negative outcome-transition net in both opponent families;
- improvements across more than one seed and more than one seat;
- zero technical failures and exact determinism.

Never combine v27 and Boatlee raw margins to decide a pass.

- [ ] **Step 4: Run all tests, then the frozen 64-game screen**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p "test_*.py" -v
python research\job_value_residual_2026-08-12\run_efficacy.py --stage screen --games research\job_value_residual_2026-08-12\artifacts\screen_games.jsonl --summary research\job_value_residual_2026-08-12\artifacts\screen_summary.json
python research\job_value_residual_2026-08-12\run_efficacy.py --verify-existing research\job_value_residual_2026-08-12\artifacts\screen_games.jsonl
```

Expected: exactly 64 official games and reproducible rows. The summary reports the gate separately for v27 and Boatlee.

- [ ] **Step 5: Apply the screen checkpoint**

Record the exact Task 6 and Task 7 runtime commit IDs in `screen_summary.json` under `runtime_commits`. Also write `eligible_incumbents` and `rejected_runtime_commits`, with rejected commits ordered newest first for safe reversion. If neither incumbent passes, write `STOP_WITHOUT_CONFIRMATION`. If one passes, mark only it eligible for a 64-game confirmation. If both pass, mark both eligible for the full 128-game confirmation. In every case retain all games and write the exact failing/pass gates before changing runtime source.

- [ ] **Step 6: Commit screen code and evidence**

```powershell
git add -- research/job_value_residual_2026-08-12/run_efficacy.py research/job_value_residual_2026-08-12/test_efficacy.py research/job_value_residual_2026-08-12/artifacts/screen_games.jsonl research/job_value_residual_2026-08-12/artifacts/screen_summary.json reports/job_value_residual_2026-08-12/decision_screen.md
git commit -m "Run frozen job-value residual screen"
```

- [ ] **Step 7: Restore every screen-rejected incumbent**

After the screen evidence commit exists, load `rejected_runtime_commits`, already ordered newest first, from `screen_summary.json` and revert each one:

```powershell
$screen = Get-Content -Raw research\job_value_residual_2026-08-12\artifacts\screen_summary.json | ConvertFrom-Json
$screen.rejected_runtime_commits | ForEach-Object { git revert --no-edit $_ }
```

Task 6 and Task 7 contain disjoint runtime/test paths, so a passing incumbent remains intact. Rerun the restored incumbent's builder `--check` and `python -m unittest research.main_approach.test_development_sources -v`. Verify its generated `main.py` SHA-256 exactly matches the Task 1 frozen control. Keep discovery, representation, and screen evidence even though rejected runtime source is restored. If neither incumbent passed, stop after these restoration commits; otherwise continue with only the eligible incumbent or incumbents.

### Task 10: Confirm Passing Incumbents and Verify Submission-Ready Artifacts

**Prerequisite:** At least one incumbent passed Task 9.

**Files:**
- Create: `research/job_value_residual_2026-08-12/verify_artifact.py`
- Create: `research/job_value_residual_2026-08-12/test_verify_artifact.py`
- Generate: `research/job_value_residual_2026-08-12/artifacts/confirmation_games.jsonl`
- Generate: `research/job_value_residual_2026-08-12/artifacts/confirmation_summary.json`
- Generate: `research/job_value_residual_2026-08-12/artifacts/hash_manifest.json`
- Conditionally generate: `research/job_value_residual_2026-08-12/artifacts/v27_current_meta_submission.tar.gz`
- Conditionally generate: `research/job_value_residual_2026-08-12/artifacts/boatlee_v16_rc2_market_relay_submission.tar.gz`
- Create: `reports/job_value_residual_2026-08-12/decision.md`

**Interfaces:**
- Consumes: Task 9 passing-incumbent list and eight confirmation seeds.
- Produces: 64 confirmation games per eligible incumbent, final per-incumbent decision, archive verification, and immutable hashes.

- [ ] **Step 1: Run confirmation only for screen-passing incumbents**

Run:

```powershell
python research\job_value_residual_2026-08-12\run_efficacy.py --stage confirmation --games research\job_value_residual_2026-08-12\artifacts\confirmation_games.jsonl --summary research\job_value_residual_2026-08-12\artifacts\confirmation_summary.json
python research\job_value_residual_2026-08-12\run_efficacy.py --verify-existing research\job_value_residual_2026-08-12\artifacts\confirmation_games.jsonl
```

Expected: 64 games if one incumbent is eligible, 128 if both are eligible. For each incumbent, improvements exceed regressions with at least one actual improvement; both opponent-family nets are non-negative; paired-margin median and sign count are positive; both seats contribute; validity and determinism gates pass.

- [ ] **Step 2: Write the failing archive-scope test**

```python
class ArtifactVerifierTests(unittest.TestCase):
    def test_archive_must_contain_only_root_main(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good = root / "good.tar.gz"
            bad = root / "bad.tar.gz"
            write_test_archive(good, {"main.py": b"def agent(obs): return {}\n"})
            write_test_archive(bad, {"main.py": b"def agent(obs): return {}\n", "tests.py": b"pass\n"})
            self.assertTrue(valid_members(good))
            self.assertFalse(valid_members(bad))
```

Define `write_test_archive` locally in the test with `tarfile.TarInfo`, `io.BytesIO`, and deterministic member names.

- [ ] **Step 3: Run the focused test and verify the verifier is absent**

Run:

```powershell
python -m unittest discover -s research\job_value_residual_2026-08-12 -p test_verify_artifact.py -v
```

Expected: FAIL importing `verify_artifact`.

- [ ] **Step 4: Implement the artifact verifier before packaging**

The verifier parses generated `main.py`, permits only `base64`, `json`, `zlib`, `math`, and `time`, rejects runtime `open`, `exec`, `eval`, `compile`, `__import__`, networking, and subprocess calls, requires size below five MiB, rebuilds twice into temporary files and compares bytes, creates a tar.gz containing only root `main.py`, extracts to a temporary directory, imports it, and runs one official Kaito v21 game from the extracted copy.

```python
def archive_members(path):
    with tarfile.open(path, "r:gz") as archive:
        return tuple(sorted(member.name for member in archive.getmembers() if member.isfile()))

def valid_members(path):
    return archive_members(path) == ("main.py",)
```

- [ ] **Step 5: Run final source, builder, representation, and archive verification**

Run:

```powershell
python research\main_approach\v27_current_meta\development\build_standalone.py --check
python research\main_approach\boatlee_v16_rc2_market_relay\development\build_standalone.py --check
python -m unittest research.main_approach.test_development_sources -v
python -m unittest discover -s research\main_approach -p "test_job_value_residual_*.py" -v
python -m unittest discover -s research\job_value_residual_2026-08-12 -p "test_*.py" -v
python research\job_value_residual_2026-08-12\validate_candidate_representations.py --output research\job_value_residual_2026-08-12\artifacts\representation_validation.json
python research\job_value_residual_2026-08-12\verify_artifact.py --confirmation research\job_value_residual_2026-08-12\artifacts\confirmation_summary.json --output-dir research\job_value_residual_2026-08-12\artifacts
```

Expected: every command exits zero; every eligible archive contains only root `main.py`, is below five MiB, imports in isolation, and completes an official-engine game `DONE/DONE` with no validity failure.

- [ ] **Step 6: Write the final stratified decision**

For each incumbent, report discovery label counts, selected threshold, screen and confirmation raw outcome transitions, paired margin distribution, own-bank delta, opponent-family/seat strata, downside, asset deaths/escapes, overflow, terminal inventory, latency, determinism, generated/development equivalence, archive hash, and final `PROMOTE_LOCAL_CANDIDATE` or `REJECT`. Explicitly state when only one incumbent passed and that the other remains unchanged. Do not call any result a Kaggle submission.

- [ ] **Step 7: Verify the final diff and commit all retained evidence**

Run:

```powershell
git diff --check
git status -sb
git diff --stat HEAD^
```

Confirm `data/replay/` is still untracked and no `.vendor/`, `data/`, or `docs/` path is staged. Then commit explicit paths:

```powershell
git add -- research/job_value_residual_2026-08-12/verify_artifact.py research/job_value_residual_2026-08-12/test_verify_artifact.py research/job_value_residual_2026-08-12/artifacts reports/job_value_residual_2026-08-12/decision.md
git commit -m "Confirm job-value residual candidates"
```

## Out-of-Scope Follow-Up

A flat selector or graph ablation requires a new approved design and implementation plan. It is eligible only if the greedy residual passes actual outcome gates and the retained dataset contains diverse positive and negative labels for the relevant incumbent. This plan does not authorize either learned model.

The `_DEMAND_ALPHA` sweep, standalone SELL quantity tuning, identity-like clone policy, and pure reversal minimization remain outside this lane. They may be reconsidered only from evidence not already falsified by the retained market and commitment reports.
