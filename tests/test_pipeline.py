from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from airindex.cleaning import clean, parse_price
from airindex.index_engine import compute
from airindex.pipeline import scrape_cycle


@pytest.mark.parametrize("text,expected", [
    ("₹5,432", 5432.0), ("INR 5432.00", 5432.0), ("5432", 5432.0),
    ("Sold out", None), (None, None),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_scrape_is_reproducible():
    t = datetime(2026, 6, 1, 6)
    a, _ = scrape_cycle(t)
    b, _ = scrape_cycle(t)
    pd.testing.assert_frame_equal(a, b)


def test_cleaning_removes_bad_rows():
    raw, _ = scrape_cycle(datetime(2026, 6, 1, 6))
    fares, rep = clean(raw)
    assert rep["clean_rows"] == len(fares)
    assert fares["total"].between(900, 60_000).all()
    assert not fares.duplicated(["scraped_at", "source", "route", "departure", "flight_no"]).any()
    # base-only portal rows get a total rebuilt from the tax ratio
    assert fares.loc[fares["source"] == "Yatra", "imputed_total"].all()


def _synthetic(prices_by_day):
    rows = []
    for day, price in prices_by_day.items():
        for route in ["DEL-BOM", "DEL-BLR", "BOM-BLR", "DEL-HYD", "DEL-CCU",
                      "BOM-GOI", "DEL-MAA", "BLR-MAA", "BOM-CCU", "BLR-HYD"]:
            for w in [1, 7, 14, 30, 60]:
                rows.append(dict(scrape_date=pd.Timestamp(day), route=route, window=w,
                                 total=price * (1 + w / 100)))
    return pd.DataFrame(rows)


def test_index_is_100_in_base_and_tracks_uniform_change():
    days = pd.date_range("2026-04-01", "2026-05-31")
    prices = {d: (5000 if d.month == 4 else 5500) for d in days}
    res = compute(_synthetic(prices))
    daily = res["daily"]["index"]
    assert daily["2026-04"].mean() == pytest.approx(100, abs=1e-6)
    assert daily["2026-05-15"] == pytest.approx(110, abs=1e-6)   # +10% everywhere -> 110


def test_jevons_ignores_booking_window_mix():
    """If the share of last-minute fares rises but prices don't, the index must not move."""
    days = pd.date_range("2026-04-01", "2026-05-10")
    df = _synthetic({d: 5000 for d in days})
    extra = df[(df["window"] == 1) & (df["scrape_date"] >= "2026-05-01")]
    res = compute(pd.concat([df] + [extra] * 5))
    assert np.allclose(res["daily"]["index"], 100)
