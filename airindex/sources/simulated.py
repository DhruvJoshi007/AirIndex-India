"""Simulated portal adapter.

Stands in for real scrapers so the whole pipeline can be demoed offline and
reproduced exactly. It models the behaviour the index has to cope with:

* dynamic pricing (fares climb steeply as departure gets close)
* seasonality by departure date (summer holidays, long weekends, Diwali)
* an underlying inflation trend plus a fuel-surcharge step on 1 Aug 2026
* per-airline and per-portal price differences
* messy page text: "₹5,432", "INR 5432.00", "Sold out", paise-for-rupee slips,
  round-trip prices shown in a one-way slot
* portals that print only the base fare and hide taxes until checkout
* duplicate rows and occasional anti-bot blocks

Every number is generated from a seed, so the same date always yields the same
fares. Nothing here contacts a real website.
"""
from __future__ import annotations

import hashlib
import math
import random
from functools import lru_cache
from datetime import date, datetime, timedelta

from ..config import AIRLINES, ROUTE_BY_CODE
from .base import BlockedError, FareSource, RawFare

WINDOW_MULT = {1: 2.30, 7: 1.45, 14: 1.18, 30: 1.03, 60: 1.00}

# Portal quirks: price offset, how often they block us, how they print prices
SOURCE_PROFILE = {
    "Airline direct": dict(offset=1.000, block=0.02, fmt="rupee"),
    "MakeMyTrip":     dict(offset=1.012, block=0.04, fmt="rupee"),
    "Yatra":          dict(offset=1.008, block=0.05, fmt="base_only"),
    "EaseMyTrip":     dict(offset=0.992, block=0.04, fmt="inr"),
    "Cleartrip":      dict(offset=1.005, block=0.03, fmt="rupee"),
    "Ixigo":          dict(offset=0.997, block=0.08, fmt="plain"),
}
AIRLINE_MULT = {
    "IndiGo": 1.00, "Air India": 1.09, "Akasa Air": 0.96,
    "SpiceJet": 0.94, "Air India Express": 0.91,
}
AIRLINE_CODE = {
    "IndiGo": "6E", "Air India": "AI", "Akasa Air": "QP",
    "SpiceJet": "SG", "Air India Express": "IX",
}


def _seed(*parts) -> int:
    h = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8)
    return int.from_bytes(h.digest(), "big")


def _in(d: date, m1: int, d1: int, m2: int, d2: int) -> bool:
    return date(d.year, m1, d1) <= d <= date(d.year, m2, d2)


def season_factor(route: str, dep: date) -> float:
    f = 1.0
    if _in(dep, 5, 15, 6, 20):          # summer holidays
        f *= 1.22
    if _in(dep, 7, 1, 8, 31):           # monsoon lull
        f *= 0.80 if "GOI" in route else 0.92
    if _in(dep, 8, 13, 8, 17):          # Independence Day long weekend
        f *= 1.15
    if _in(dep, 9, 12, 9, 16) and "BOM" in route:   # Ganesh Chaturthi
        f *= 1.20
    if _in(dep, 11, 4, 11, 11):         # Diwali 2026 (8 Nov)
        f *= 1.38
    if _in(dep, 12, 20, 12, 31):        # year-end holidays
        f *= 1.30
    if dep.weekday() in (4, 6):         # Friday / Sunday departures
        f *= 1.07
    return f


def trend_factor(scraped: date) -> float:
    t = (scraped - date(2026, 4, 1)).days
    f = math.exp(0.055 * t / 365)                  # ~5.5% a year underlying
    if scraped >= date(2026, 8, 1):                # fuel surcharge step
        f *= 1.04
    return f


@lru_cache(maxsize=None)
def route_shock(route: str, scraped: date) -> float:
    """Slow-moving demand shock per route (AR(1) on a weekly clock)."""
    week = (scraped - date(2026, 1, 1)).days // 7
    x = 0.0
    for w in range(week - 12, week + 1):
        x = 0.7 * x + random.Random(_seed("shock", route, w)).gauss(0, 0.035)
    return math.exp(x)


@lru_cache(maxsize=None)
def route_schedule(route: str) -> tuple[tuple[str, str], ...]:
    """Fixed list of (airline, flight number) operating a route."""
    rng = random.Random(_seed("sched", route))
    flights = []
    for airline in AIRLINES:
        for _ in range(rng.choice([1, 1, 2])):
            flights.append((airline, f"{AIRLINE_CODE[airline]} {rng.randint(100, 999)}"))
    return tuple(flights)


def market_fare(route: str, dep: date, window: int, airline: str, scraped: date) -> float:
    r = ROUTE_BY_CODE[route]
    base = 2300 + 3.1 * r.km
    rng = random.Random(_seed("mkt", route, dep, airline, scraped))
    sigma = 0.16 if window <= 1 else 0.09
    return (base * WINDOW_MULT[window] * season_factor(route, dep)
            * trend_factor(scraped) * route_shock(route, scraped)
            * AIRLINE_MULT[airline] * math.exp(rng.gauss(0, sigma)))


def _fmt(x: float, style: str) -> str:
    n = int(round(x))
    if style == "rupee":
        return f"₹{n:,}"
    if style == "inr":
        return f"INR {n}.00"
    return str(n)


class SimulatedPortal(FareSource):
    def __init__(self, name: str):
        self.name = name
        self.profile = SOURCE_PROFILE[name]

    def fetch(self, route: str, departure: date, scraped_at: datetime,
              attempt: int = 0) -> list[RawFare]:
        rng = random.Random(_seed("fetch", self.name, route, departure, scraped_at, attempt))
        block_p = self.profile["block"] * (0.35 if attempt else 1.0)   # rotated profile helps
        if rng.random() < block_p:
            raise BlockedError(f"{self.name}: CAPTCHA wall on {route}")

        window = (departure - scraped_at.date()).days
        out: list[RawFare] = []
        for airline, flt in route_schedule(route):
            if rng.random() < 0.25:             # not every portal lists every flight
                continue
            total = market_fare(route, departure, window, airline, scraped_at.date())
            total *= self.profile["offset"] * math.exp(rng.gauss(0, 0.015))
            taxes = 0.12 * (total - 650) / 1.12 + 650
            base = total - taxes
            style = self.profile["fmt"]

            base_t = _fmt(base, "plain" if style == "base_only" else style)
            tax_t = None if style == "base_only" else _fmt(taxes, style)
            total_t = None if style == "base_only" else _fmt(total, style)

            # --- page-text noise the cleaning stage must survive ---
            u = rng.random()
            if u < 0.004:
                total_t, base_t = "Sold out", None
            elif u < 0.007 and total_t:
                total_t = str(int(round(total * 100)))    # paise read as rupees
            elif u < 0.009 and total_t:
                total_t = "₹99"                           # promo-banner glitch
            elif u < 0.013 and total_t:
                total_t = _fmt(total * 2, style)          # round-trip price in a one-way slot

            row = RawFare(scraped_at, self.name, route, departure, airline, flt,
                          base_t, tax_t, total_t)
            out.append(row)
            if rng.random() < 0.01:                       # duplicate card on page
                out.append(row)
        return out
