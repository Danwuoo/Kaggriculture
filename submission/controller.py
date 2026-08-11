"""Time-budgeted integration of strategy, scheduling, market, and fallback."""

from time import perf_counter

from economy import fertilizer_incremental_value
from market import MarketController
from opponent import OpponentModel
from parameters import HARD_OUTPUT_SECONDS, MACRO_REUSE_SECONDS, SOFT_SIMULATION_SECONDS
from pathfinding import DistanceCache
from rules import validate_and_project
from scheduler import Scheduler
from simulator import MacroPlanner
from state import GameState, generic_safe_action


class Controller:
    def __init__(self, player):
        self.player = int(player)
        self.last_step = -1
        self.paths = DistanceCache(10)
        self.scheduler = Scheduler(self.paths)
        self.macro = MacroPlanner()
        self.opponent = OpponentModel()
        self.market = MarketController()
        self.cached_forecast = {"windows": {}, "exposure": {}, "cohorts": []}
        self.degrade_counts = [0, 0, 0]

    def reset(self, size=10):
        self.last_step = -1
        self.paths = DistanceCache(size)
        self.scheduler = Scheduler(self.paths)
        self.macro = MacroPlanner()
        self.opponent = OpponentModel()
        self.market = MarketController()
        self.cached_forecast = {"windows": {}, "exposure": {}, "cohorts": []}

    def act(self, obs):
        started = perf_counter()
        try:
            state = GameState(obs)
            if state.player != self.player:
                self.player = state.player
                self.reset(state.size)
            if state.step <= self.last_step or self.paths.size != state.size:
                self.reset(state.size)
            self.last_step = state.step

            elapsed = perf_counter() - started
            if elapsed >= HARD_OUTPUT_SECONDS:
                self.degrade_counts[2] += 1
                return self._fallback(state)

            level = 0
            if elapsed < SOFT_SIMULATION_SECONDS:
                self.cached_forecast = self.opponent.forecast(state)
            else:
                level = 1
            macro = self.macro.update(state, self.cached_forecast, force=(state.hour == 0 and elapsed < SOFT_SIMULATION_SECONDS))
            farm_action = self.scheduler.assign(state, macro)
            legal_farm, projected_shed = validate_and_project(state, farm_action)

            elapsed = perf_counter() - started
            if elapsed < MACRO_REUSE_SECONDS:
                fertilizer_reserve = sum(
                    1 for _, tile in state.iter_tiles()
                    if fertilizer_incremental_value(state, tile) > 0
                )
                farm_action["market"] = self.market.plan(state, macro, self.cached_forecast, projected_shed, min(2, fertilizer_reserve))
            else:
                level = max(level, 1)
                farm_action["market"] = self.market.plan(state, macro, self.cached_forecast, projected_shed, 0)[:4]
            result, _ = validate_and_project(state, farm_action)
            if perf_counter() - started >= HARD_OUTPUT_SECONDS:
                level = 2
                result = self._fallback(state)
            self.degrade_counts[level] += 1
            return result
        except Exception:
            self.degrade_counts[2] += 1
            try:
                return self._fallback(GameState(obs))
            except Exception:
                return generic_safe_action(obs)

    def _fallback(self, state):
        action = self.scheduler.safe_schedule(state)
        # Terminal shed liquidation is safe and keeps Level 2 useful.
        if state.step >= 696:
            action["market"] = [["SELL", item, count] for item, count in state.shed.items() if item in state.market_inventory and count > 0][:10]
        return validate_and_project(state, action)[0]

