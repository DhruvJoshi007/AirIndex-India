"""Turn clean fares into a CPI-ready airfare price index.

Method (follows the ILO CPI Manual, 2004):

* Elementary aggregate = one route x one booking window (economy, one-way).
  Holding the booking window fixed is what keeps the comparison like-for-like:
  a fare bought 1 day out is never compared with one bought 60 days out.
* Elementary price on a day = geometric mean of every clean fare observed in
  that cell that day (all airlines, all portals).
* Elementary index = Jevons: geometric-mean price today / geometric-mean price
  in the base period x 100. Jevons is the formula most statistical offices use
  for web-scraped prices because it is not pulled up by a few extreme fares.
* Route index = booking-window-weighted average of its cells.
* Headline index = traffic-weighted average of route indices (fixed-basket,
  Laspeyres-type, as in CPI).
* Monthly CPI feed = average of daily headline values in the month.
Missing cells are carried forward from the last observed value (standard CPI
imputation for temporarily missing prices).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BASE_END, BASE_START, ROUTES, WINDOW_WEIGHTS

ROUTE_W = {r.code: r.weight for r in ROUTES}


def cell_prices(clean: pd.DataFrame) -> pd.DataFrame:
    """Daily geometric-mean fare per (route, window)."""
    g = (clean.assign(lf=np.log(clean["total"]))
              .groupby(["scrape_date", "route", "window"])
              .agg(lf=("lf", "mean"), n=("lf", "size"),
                   lo=("total", "min"), hi=("total", "max")))
    g["price"] = np.exp(g["lf"])
    return g.drop(columns="lf").reset_index()


def compute(clean: pd.DataFrame) -> dict[str, pd.DataFrame]:
    cp = cell_prices(clean)
    cp = cp[cp["window"].isin(WINDOW_WEIGHTS)]

    wide = cp.pivot_table(index="scrape_date", columns=["route", "window"], values="price")
    wide = wide.asfreq("D").ffill()                       # carry forward gaps

    base_mask = (wide.index >= pd.Timestamp(BASE_START)) & (wide.index <= pd.Timestamp(BASE_END))
    base = np.exp(np.log(wide[base_mask]).mean())
    cell_idx = 100 * wide / base

    route_idx = pd.DataFrame(index=cell_idx.index)
    for r in ROUTE_W:
        route_idx[r] = sum(cell_idx[(r, w)] * wt for w, wt in WINDOW_WEIGHTS.items())

    # rebase so every route averages exactly 100 over the base period
    route_idx = 100 * route_idx / route_idx[base_mask].mean()

    window_idx = pd.DataFrame(index=cell_idx.index)
    for w in WINDOW_WEIGHTS:
        window_idx[w] = sum(cell_idx[(r, w)] * ROUTE_W[r] for r in ROUTE_W)
    window_idx = 100 * window_idx / window_idx[base_mask].mean()

    headline = (route_idx * pd.Series(ROUTE_W)).sum(axis=1).rename("index")

    daily = pd.DataFrame({"index": headline})
    daily["ma7"] = daily["index"].rolling(7, min_periods=1).mean()

    monthly = headline.groupby(headline.index.to_period("M")).mean().to_frame("index")
    monthly["mom_pct"] = monthly["index"].pct_change() * 100
    monthly["days"] = headline.groupby(headline.index.to_period("M")).size()

    # Dynamic-pricing spread: highest / lowest fare seen per route on a day
    spread = (cp.groupby(["scrape_date", "route"])
                .agg(lo=("lo", "min"), hi=("hi", "max"))
                .assign(ratio=lambda d: d["hi"] / d["lo"]))

    return dict(cells=cp, cell_index=cell_idx, route_index=route_idx,
                window_index=window_idx, daily=daily, monthly=monthly,
                spread=spread, base_prices=base)
