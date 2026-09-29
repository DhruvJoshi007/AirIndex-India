"""Static configuration for the AirIndex India demo.

Route weights are illustrative traffic shares for the pilot basket. In the real
system they would come from DGCA monthly domestic passenger data and be
revised once a year, the same way CPI item weights are revised.
"""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "airindex.db"


@dataclass(frozen=True)
class Route:
    code: str          # e.g. "DEL-BOM"
    origin: str
    dest: str
    km: int            # great-circle distance, approx
    weight: float      # share of basket (sums to 1.0)


# Pilot basket: top 10 domestic routes (weights illustrative, sum = 1.0)
ROUTES = [
    Route("DEL-BOM", "Delhi", "Mumbai", 1140, 0.18),
    Route("DEL-BLR", "Delhi", "Bengaluru", 1740, 0.14),
    Route("BOM-BLR", "Mumbai", "Bengaluru", 840, 0.12),
    Route("DEL-HYD", "Delhi", "Hyderabad", 1260, 0.10),
    Route("DEL-CCU", "Delhi", "Kolkata", 1305, 0.09),
    Route("BOM-GOI", "Mumbai", "Goa", 430, 0.08),
    Route("DEL-MAA", "Delhi", "Chennai", 1760, 0.08),
    Route("BLR-MAA", "Bengaluru", "Chennai", 290, 0.07),
    Route("BOM-CCU", "Mumbai", "Kolkata", 1660, 0.07),
    Route("BLR-HYD", "Bengaluru", "Hyderabad", 500, 0.07),
]
ROUTE_BY_CODE = {r.code: r for r in ROUTES}

# Booking windows = days between the scrape and departure.
# The index prices the same window every day, so a fare bought 1 day out is
# only ever compared with other fares bought 1 day out (like-for-like).
BOOKING_WINDOWS = [1, 7, 14, 30, 60]
# How travellers actually spread their purchases across windows (illustrative)
WINDOW_WEIGHTS = {1: 0.12, 7: 0.23, 14: 0.25, 30: 0.25, 60: 0.15}

AIRLINES = ["IndiGo", "Air India", "Akasa Air", "SpiceJet", "Air India Express"]

# Portals the scraper fleet visits (simulated in this demo)
SOURCES = [
    "Airline direct",
    "MakeMyTrip",
    "Yatra",
    "EaseMyTrip",
    "Cleartrip",
    "Ixigo",
]

# Base period for the index (= 100)
BASE_START = date(2026, 4, 1)
BASE_END = date(2026, 4, 30)

# Demo history range
HISTORY_START = date(2026, 4, 1)
HISTORY_END = date(2026, 9, 28)

# Data-quality thresholds
MIN_VALID_FARE = 900        # INR; anything cheaper is a parsing glitch
MAX_VALID_FARE = 60_000     # INR; economy one-way ceiling
MAD_Z_LIMIT = 3.5           # robust z-score cut-off for outliers
MAD_FLOOR = 0.10            # minimum spread (log units, about 10%) used in that z-score
