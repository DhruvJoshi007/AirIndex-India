"""Clean and normalise raw portal rows into comparable total fares."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .config import MAD_FLOOR, MAD_Z_LIMIT, MAX_VALID_FARE, MIN_VALID_FARE

_NUM = re.compile(r"[\d,]+(?:\.\d+)?")


def parse_price(text) -> float | None:
    """'₹5,432' / 'INR 5432.00' / '5432' -> 5432.0 ; 'Sold out' / None -> None"""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return None
    m = _NUM.search(str(text))
    if not m:
        return None
    return float(m.group(0).replace(",", ""))


def clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return (clean fares, quality report).

    Steps
    1. parse price text
    2. de-duplicate identical cards from the same page load
    3. rebuild total fare where a portal shows only the base fare
       (ratio learnt from portals that show both, same route/window/cycle)
    4. drop impossible values (sold out, promo glitches, paise slips)
    5. robust outlier filter: median / MAD on log fare within each
       route x booking-window x scrape-day cell
    """
    report = {"raw_rows": int(len(raw))}
    df = raw.copy()
    df["scraped_at"] = pd.to_datetime(df["scraped_at"])
    df["departure"] = pd.to_datetime(df["departure"])
    df["scrape_date"] = df["scraped_at"].dt.normalize()
    df["window"] = (df["departure"] - df["scrape_date"]).dt.days

    df["base"] = df["base_fare_text"].map(parse_price)
    df["taxes"] = df["taxes_text"].map(parse_price)
    df["total"] = df["total_text"].map(parse_price)

    # 2. duplicates
    before = len(df)
    df = df.drop_duplicates(["scraped_at", "source", "route", "departure", "flight_no"])
    report["duplicates"] = before - len(df)

    # 3. base-only portals -> estimate total with learnt tax ratio
    both = df.dropna(subset=["base", "total"])
    both = both[(both["total"] > MIN_VALID_FARE) & (both["total"] < MAX_VALID_FARE)]
    ratio = (both.assign(r=both["total"] / both["base"])
                 .groupby(["scraped_at", "route", "window"])["r"].median()
                 .rename("tax_ratio"))
    df = df.join(ratio, on=["scraped_at", "route", "window"])
    need = df["total"].isna() & df["base"].notna()
    df["imputed_total"] = need
    df.loc[need, "total"] = df.loc[need, "base"] * df.loc[need, "tax_ratio"]
    report["taxes_imputed"] = int(need.sum())

    # 4. hard validity bounds
    missing = df["total"].isna()
    report["unpriced_sold_out"] = int(missing.sum())
    df = df[~missing]
    bad = (df["total"] < MIN_VALID_FARE) | (df["total"] > MAX_VALID_FARE)
    report["out_of_bounds"] = int(bad.sum())
    df = df[~bad]

    # 5. robust outlier filter
    df = df.assign(lf=np.log(df["total"]))
    g = df.groupby(["scrape_date", "route", "window"])["lf"]
    med = g.transform("median")
    # MAD floor: fares within one cell cluster tightly by flight, so a raw MAD
    # can be tiny and would wrongly flag the dearest airline as an outlier.
    mad = g.transform(lambda s: (s - s.median()).abs().median()).clip(lower=MAD_FLOOR)
    z = 0.6745 * (df["lf"] - med) / mad
    outlier = z.abs() > MAD_Z_LIMIT
    report["statistical_outliers"] = int(outlier.sum())
    df = df[~outlier]

    report["clean_rows"] = int(len(df))
    report["pass_rate"] = round(report["clean_rows"] / max(report["raw_rows"], 1), 4)

    cols = ["scraped_at", "scrape_date", "source", "route", "departure", "window",
            "airline", "flight_no", "total", "imputed_total"]
    out = df[cols].copy()
    out["total"] = out["total"].round(0)
    return out.reset_index(drop=True), report
