import copy
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBMISSION = ROOT / "submission"
VENDOR = ROOT / ".vendor" / "kaggle-environments"
if str(SUBMISSION) not in sys.path:
    sys.path.insert(0, str(SUBMISSION))
if str(VENDOR) not in sys.path:
    sys.path.insert(1, str(VENDOR))

import main
from constants import ALL_SHED_ITEMS, ANIMALS, CROPS, MARKET_PARAMS, PRODUCTS
from controller import Controller
from economy import fertilizer_incremental_value
from market import market_price, projected_sale
from opponent import OpponentModel
from pathfinding import DistanceCache
from rules import animal_will_escape, is_action_schema, plant_will_die, validate_and_project
from scheduler import Scheduler
from simulator import MacroPlanner
from state import GameState, generic_safe_action


def blank_tiles():
    return [[None if x < 5 and y < 5 else "LOCKED" for x in range(10)] for y in range(10)]


def blank_farm(hands=None):
    return {
        "money": 3000,
        "tiles": blank_tiles(),
        "farmer": [4, 4],
        "hands": hands or [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }


def blank_obs(player=0, step=0, hands=None):
    farms = [blank_farm(hands if player == 0 else None), blank_farm(hands if player == 1 else None)]
    return {
        "player": player,
        "step": step,
        "day": step // 24,
        "hour": step % 24,
        "farms": farms,
        "private": {
            "shed": {item: 0 for item in ALL_SHED_ITEMS},
            "seeds": {crop: 0 for crop in CROPS},
            "inventories": [{} for _ in range(1 + len(hands or []))],
        },
        "market": {
            "inventory": {item: 10000 for item in PRODUCTS},
            "prices": {item: MARKET_PARAMS[item]["base"] for item in PRODUCTS},
        },
        "town": {"unlocked_shops": []},
    }


class StateAndSafetyTests(unittest.TestCase):
    def test_observation_parsing_and_validation(self):
        obs = blank_obs(hands=[[99, -2]])
        obs["private"]["seeds"]["WHEAT"] = -5
        obs["private"]["shed"]["MILK"] = "3"
        obs["farms"][0]["tiles"][0][0] = {"kind": "PLANT", "crop": "NOPE"}
        state = GameState(obs)
        self.assertEqual(state.seeds["WHEAT"], 0)
        self.assertEqual(state.shed["MILK"], 3)
        self.assertEqual(state.me["hands"][0], (0, 0))
        self.assertEqual(state.tile((0, 0)), "LOCKED")
        self.assertTrue(state.errors)

    def test_new_episode_reset_and_seat_isolation(self):
        main._controllers.clear()
        main.agent(blank_obs(0, 0))
        main.agent(blank_obs(1, 0))
        self.assertIsNot(main._controllers[0], main._controllers[1])
        main._controllers[0].macro.plan["sentinel"] = 1
        main.agent(blank_obs(0, 0))
        self.assertNotIn("sentinel", main._controllers[0].macro.plan)
        self.assertNotIn("sentinel", main._controllers[1].macro.plan)

    def test_fresh_crop_is_watered(self):
        obs = blank_obs(step=10)
        obs["farms"][0]["tiles"][4][4] = {
            "kind": "PLANT", "crop": "MELON", "planted_day": 0,
            "watered_today": False, "consecutive_unwatered": 1,
            "yield_units": 1, "max_lifespan_step": 312, "fertilized_until_day": -1,
        }
        action = Controller(0).act(obs)
        self.assertEqual(action["farmer"], ["WATER"])

    def test_death_predicates(self):
        plant = {"kind": "PLANT", "watered_today": False, "consecutive_unwatered": 1}
        cow = {"animal": "COW", "fed_today": False, "consecutive_unfed": 1}
        self.assertTrue(plant_will_die(plant))
        self.assertTrue(animal_will_escape(cow))
        plant["watered_today"] = True
        cow["fed_today"] = True
        self.assertFalse(plant_will_die(plant))
        self.assertFalse(animal_will_escape(cow))

    def test_locked_path_is_traversable(self):
        paths = DistanceCache(10)
        self.assertEqual(paths.distance((5, 4), (4, 4)), 1)
        self.assertEqual(paths.next_action((5, 4), (4, 4)), ["WEST"])

    def test_weed_recovery_dig_then_retry(self):
        obs = blank_obs(step=5)
        obs["farms"][0]["tiles"][4][4] = {"kind": "WEED"}
        obs["private"]["seeds"]["MELON"] = 1
        state = GameState(obs)
        scheduler = Scheduler(DistanceCache(10))
        scheduler.intents[0] = {"pos": (4, 4), "action": ("PLANT", "MELON"), "expires": 12}
        action = scheduler.assign(state, {"cows": 0, "sheep": 0, "melons": 0, "wheat": 0})
        self.assertEqual(action["farmer"], ["DIG"])
        obs2 = copy.deepcopy(obs)
        obs2["step"], obs2["hour"] = 6, 6
        obs2["farms"][0]["tiles"][4][4] = None
        action2 = scheduler.assign(GameState(obs2), {"cows": 0, "sheep": 0, "melons": 0, "wheat": 0})
        self.assertEqual(action2["farmer"], ["PLANT", "MELON"])

    def test_fallback_schema(self):
        for obs in (None, {}, {"player": "bad", "farms": "bad"}, blank_obs(hands=[[5, 4], [4, 5]])):
            action = generic_safe_action(obs)
            self.assertTrue(is_action_schema(action))
            self.assertLessEqual(len(action["market"]), 10)


class MarketAndSchedulingTests(unittest.TestCase):
    def test_locked_shed_access_tiles_are_excluded_for_pickup(self):
        obs = blank_obs(step=25, hands=[[5, 4], [4, 4]])
        obs["private"]["shed"]["WHEAT"] = 12
        obs["farms"][0]["tiles"][0][0] = {
            "kind": "PASTURE", "animal": "COW", "placed_day": 0,
            "yield_units": 0, "fed_today": False, "consecutive_unfed": 1,
            "cared_today": False, "fertilizer_available": False,
            "pending_care_bonus": 0,
        }
        state = GameState(obs)
        jobs = Scheduler(DistanceCache(10)).build_jobs(
            state, {"cows": 1, "sheep": 0, "melons": 0, "wheat": 0}
        )
        pickup_positions = [job.positions for job in jobs if job.action[:2] == ["PICKUP", "WHEAT"]]
        self.assertIn(((4, 4),), pickup_positions)
        self.assertNotIn(state.shed_access, pickup_positions)

    def test_opening_plan_uses_replay_informed_melon_cohort(self):
        plan = MacroPlanner().update(GameState(blank_obs(step=0)), {})
        self.assertEqual(plan["melons"], 8)
        self.assertEqual(plan["seed_needs"]["MELON"], 8)

    def test_market_price_and_unit_revenue(self):
        try:
            from kaggle_environments.envs.kaggriculture import kaggriculture as engine
        except ImportError as exc:
            self.skipTest(str(exc))
        for item in PRODUCTS:
            for inventory in (9500, 9900, 9999, 10000, 10001, 10100, 11000):
                self.assertEqual(market_price(item, inventory, MARKET_PARAMS), engine.market_price(item, inventory))
        revenue, end = projected_sale("MELON", 20, 10000, MARKET_PARAMS)
        expected = 0
        inv = 10000
        for _ in range(20):
            price = market_price("MELON", inv, MARKET_PARAMS)
            expected += price
            if price > 1:
                inv += 1
        self.assertEqual((revenue, end), (expected, inv))

    def test_seed_consistency_and_order_cap(self):
        obs = blank_obs(step=2, hands=[[0, 0], [1, 0]])
        obs["farms"][0]["farmer"] = [2, 0]
        obs["private"]["seeds"]["MELON"] = 1
        state = GameState(obs)
        scheduler = Scheduler(DistanceCache(10))
        action = scheduler.assign(state, {"cows": 0, "sheep": 0, "melons": 5, "wheat": 0})
        plants = [x for x in [action["farmer"]] + action["hands"] if x[:1] == ["PLANT"] and x[1] == "MELON"]
        self.assertLessEqual(len(plants), 1)
        action["market"] = [["HIRE"] for _ in range(20)]
        legal, _ = validate_and_project(state, action)
        self.assertLessEqual(len(legal["market"]), 10)

    def test_fertilizer_opportunity_cost(self):
        obs = blank_obs(step=300)
        state = GameState(obs)
        wheat = {"kind": "PLANT", "crop": "WHEAT", "planted_day": 12, "fertilized_until_day": -1}
        strawberry = {"kind": "PLANT", "crop": "STRAWBERRY", "planted_day": 12, "fertilized_until_day": -1}
        self.assertLess(fertilizer_incremental_value(state, wheat), 0)
        self.assertGreater(fertilizer_incremental_value(state, strawberry), 0)

    def test_opponent_public_forecast_windows(self):
        obs = blank_obs(step=240)
        obs["farms"][1]["tiles"][0][0] = {
            "kind": "PLANT", "crop": "MELON", "planted_day": 0,
            "watered_today": True, "consecutive_unwatered": 0, "yield_units": 6,
            "max_lifespan_step": 312, "fertilized_until_day": -1,
        }
        forecast = OpponentModel().forecast(GameState(obs))
        self.assertEqual(tuple(forecast["windows"]), (1, 3, 6, 12, 24))
        self.assertGreater(forecast["exposure"]["MELON"], 0)

    def test_terminal_717_to_719(self):
        for step in (717, 718, 719):
            obs = blank_obs(step=step)
            obs["private"]["shed"]["MILK"] = 3
            obs["private"]["inventories"][0]["WOOL"] = 2
            action = Controller(0).act(obs)
            self.assertTrue(is_action_schema(action, 0))
            self.assertLessEqual(len(action["market"]), 10)
            self.assertTrue(any(order[:2] == ["SELL", "MILK"] for order in action["market"]))
            if step <= 718:
                self.assertEqual(action["farmer"], ["DROP"])


class OfficialEngineFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from kaggle_environments.envs.kaggriculture import kaggriculture
        except ImportError as exc:
            raise unittest.SkipTest(str(exc))
        cls.engine = kaggriculture

    def test_care_bonus_and_product_cap(self):
        e = self.engine
        farm, private = e._new_farm(10, 3000), e._new_private()
        farm["tiles"][4][4] = e._new_animal("COW", 0)
        private["inventories"][0]["WHEAT"] = 20
        for day in range(8):
            e._apply_unit_action(farm, private, 0, ["FEED"], 10, day, 24)
            e._apply_unit_action(farm, private, 0, ["CARE"], 10, day, 24)
            e._daily_refresh_animals(farm, day)
        cow = farm["tiles"][4][4]
        self.assertEqual(cow["yield_units"], ANIMALS["COW"]["max_held"])
        self.assertEqual(cow["pending_care_bonus"], 1)

    def test_fertilizer_collect_apply_drop_sell(self):
        e = self.engine
        farm, private = e._new_farm(10, 3000), e._new_private()
        farm["tiles"][4][4] = e._new_animal("COW", 0)
        e._daily_refresh_animals(farm, 0)
        e._apply_unit_action(farm, private, 0, ["COLLECT_FERTILIZER"], 10, 1, 24)
        self.assertEqual(private["inventories"][0].get("FERTILIZER"), 1)
        farm["tiles"][4][4] = e._new_plant("STRAWBERRY", 1, 24)
        e._apply_unit_action(farm, private, 0, ["FERTILIZE"], 10, 1, 24)
        self.assertEqual(farm["tiles"][4][4]["fertilized_until_day"], 3)
        private["shed"]["FERTILIZER"] = 1
        market = e._new_market()
        before = farm["money"]
        self.assertTrue(e._commit_unit("SELL", "FERTILIZER", 100, farm, private, market))
        self.assertEqual(farm["money"], before + 100)

    def test_harvest_inventory_drop_shed_sell(self):
        e = self.engine
        farm, private, market = e._new_farm(10, 3000), e._new_private(), e._new_market()
        plant = e._new_plant("WHEAT", 0, 24)
        plant["yield_units"] = 4
        farm["tiles"][4][4] = plant
        e._apply_unit_action(farm, private, 0, ["HARVEST"], 10, 4, 24)
        self.assertEqual(private["inventories"][0]["WHEAT"], 4)
        e._apply_unit_action(farm, private, 0, ["DROP"], 10, 4, 24)
        self.assertEqual(private["shed"]["WHEAT"], 4)
        for _ in range(4):
            price = e.market_price("WHEAT", market["inventory"]["WHEAT"])
            self.assertTrue(e._commit_unit("SELL", "WHEAT", price, farm, private, market))
        self.assertEqual(private["shed"]["WHEAT"], 0)

    def test_shed_overflow_discards_excess(self):
        e = self.engine
        farm, private = e._new_farm(10, 3000), e._new_private()
        private["shed"]["FERTILIZER"] = 95
        private["inventories"][0]["WHEAT"] = 10
        e._apply_unit_action(farm, private, 0, ["DROP"], 10, 0, 24, 100)
        self.assertEqual(sum(private["shed"].values()), 100)
        self.assertEqual(private["shed"]["WHEAT"], 5)
        self.assertEqual(private["inventories"][0], {})


if __name__ == "__main__":
    unittest.main()
