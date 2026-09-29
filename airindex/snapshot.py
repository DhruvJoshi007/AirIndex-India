"""Bundle everything the dashboard and API need into one JSON-ready dict."""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from . import index_engine, storage
from .config import (BASE_END, BASE_START, BOOKING_WINDOWS, ROUTE_BY_CODE, ROUTES,
                     SOURCES, WINDOW_WEIGHTS)


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def build(con=None) -> dict:
    own = con is None
    if own:
        ctx = storage.connect()
        con = ctx.__enter__()
    try:
        clean = storage.load_clean(con)
        runs = storage.load_runs(con)
        quality = storage.load_quality(con)
    finally:
        if own:
            ctx.__exit__(None, None, None)

    res = index_engine.compute(clean)
    daily, monthly, route_idx = res["daily"], res["monthly"], res["route_index"]
    last = daily.index.max()
    d30 = last - pd.Timedelta(days=30)

    def at(series, ts):
        s = series[series.index <= ts]
        return float(s.iloc[-1]) if len(s) else np.nan

    headline = dict(
        dates=[d.strftime("%Y-%m-%d") for d in daily.index],
        index=[_r(v) for v in daily["index"]],
        ma7=[_r(v) for v in daily["ma7"]],
    )

    cells = res["cells"]
    recent = cells[cells["scrape_date"] > last - pd.Timedelta(days=7)]
    spread = res["spread"].reset_index()
    spread_recent = spread[spread["scrape_date"] > last - pd.Timedelta(days=7)]

    routes = []
    for r in ROUTES:
        s = route_idx[r.code]
        rc = recent[recent["route"] == r.code]
        curve = (rc.assign(lp=np.log(rc["price"])).groupby("window")["lp"].mean()
                   .pipe(np.exp).reindex(BOOKING_WINDOWS))
        routes.append(dict(
            code=r.code, origin=r.origin, dest=r.dest, km=r.km, weight=r.weight,
            latest=_r(s.iloc[-1], 1),
            chg30=_r((s.iloc[-1] / at(s, d30) - 1) * 100, 1),
            series=[_r(v, 1) for v in s.iloc[-90:]],
            window_fares={str(w): _r(v, 0) for w, v in curve.items()},
            spread=_r(spread_recent[spread_recent["route"] == r.code]["ratio"].mean(), 2),
        ))

    # CPI feed
    feed = [dict(month=str(p), index=_r(row["index"]), mom_pct=_r(row["mom_pct"]),
                 days=int(row["days"])) for p, row in monthly.iterrows()]

    # Quality + scraper health (last 30 days)
    q = quality.copy()
    q["scrape_date"] = pd.to_datetime(q["scrape_date"])
    q30 = q[q["scrape_date"] > d30]
    reasons = {k: int(q30[k].sum()) for k in
               ["duplicates", "taxes_imputed", "unpriced_sold_out",
                "out_of_bounds", "statistical_outliers"]}
    runs30 = runs[runs["scraped_at"] > d30]
    health = []
    for src in SOURCES:
        g = runs30[runs30["source"] == src]
        n = max(len(g), 1)
        health.append(dict(
            source=src,
            ok=_r((g["status"] == "ok").sum() / n * 100, 1),
            recovered=_r((g["status"] == "recovered").sum() / n * 100, 1),
            blocked=_r((g["status"] == "blocked").sum() / n * 100, 1),
            rows=int(g["rows"].sum()),
        ))

    # Latest observations for the live-fare table
    last_cycle = clean["scraped_at"].max()
    lf = clean[clean["scraped_at"] == last_cycle]
    latest_fares = [dict(route=x.route, window=int(x.window), source=x.source,
                         airline=x.airline, flight=x.flight_no, total=int(x.total),
                         imputed=bool(x.imputed_total))
                    for x in lf.itertuples()]

    wi = res["window_index"]
    return dict(
        meta=dict(
            generated_at=datetime.now().isoformat(timespec="seconds"),
            last_date=last.strftime("%Y-%m-%d"),
            last_cycle=last_cycle.strftime("%Y-%m-%d %H:%M"),
            base_period=f"{BASE_START:%d %b %Y} to {BASE_END:%d %b %Y}",
            windows=BOOKING_WINDOWS, window_weights=WINDOW_WEIGHTS,
            sources=SOURCES, simulated=True,
        ),
        kpi=dict(
            index=_r(daily["index"].iloc[-1]),
            chg30=_r((daily["index"].iloc[-1] / at(daily["index"], d30) - 1) * 100),
            latest_month=feed[-1]["month"], latest_month_index=feed[-1]["index"],
            latest_mom=feed[-1]["mom_pct"],
            fares_24h=int((clean["scrape_date"] == last).sum()),
            fares_total=int(len(clean)),
            pass_rate=_r(q30["clean_rows"].sum() / q30["raw_rows"].sum() * 100, 1),
            spread=_r(spread_recent["ratio"].mean(), 2),
        ),
        headline=headline,
        window_index={str(w): _r(wi[w].iloc[-1], 1) for w in wi.columns},
        routes=routes,
        cpi_feed=feed,
        quality=dict(
            reasons=reasons,
            raw_30d=int(q30["raw_rows"].sum()), clean_30d=int(q30["clean_rows"].sum()),
            daily_pass=[dict(date=d.strftime("%Y-%m-%d"), pass_rate=_r(p * 100, 2))
                        for d, p in zip(q["scrape_date"], q["pass_rate"])],
        ),
        health=health,
        latest_fares=latest_fares,
    )


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "data/snapshot.json"
    snap = build()
    with open(out, "w") as f:
        json.dump(snap, f, separators=(",", ":"))
    print(f"wrote {out}  index={snap['kpi']['index']}  fares={snap['kpi']['fares_total']:,}")
