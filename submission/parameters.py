"""Small, offline-tunable policy parameters."""

SOFT_SIMULATION_SECONDS = 0.45
MACRO_REUSE_SECONDS = 0.60
HARD_OUTPUT_SECONDS = 0.70
MAX_MARKET_ORDERS = 10
SHED_CAPACITY = 100
SHED_SOFT_LIMIT = 68
SHED_HARD_LIMIT = 86
PLANT_CUTOFF_HOUR = 20
RECOVERY_TURNS = 7
FEED_DAYS_IN_SHED = 3
MIN_CASH_RESERVE = 160
MAX_STRAWBERRY_PLANTS_PER_DAY = 2
OPENING_MELONS = 8

# A sale may wait below these fractions of base price unless capacity, terminal,
# or opponent exposure makes delay more dangerous than price impact.
RESERVE_FRACTIONS = {
    "WHEAT": .72,
    "CARROT": .68,
    "TOMATO": .62,
    "STRAWBERRY": .55,
    "MELON": .56,
    "EGG": .68,
    "MILK": .56,
    "WOOL": .55,
    "FERTILIZER": .62,
}

NORMAL_BATCH = {
    "WHEAT": 16,
    "CARROT": 10,
    "TOMATO": 8,
    "STRAWBERRY": 5,
    "MELON": 8,
    "EGG": 12,
    "MILK": 6,
    "WOOL": 5,
    "FERTILIZER": 10,
}
