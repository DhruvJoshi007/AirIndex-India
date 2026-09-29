"""Scrape -> clean -> store, for one cycle or a whole backfill."""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta

import pandas as pd

from . import storage
from .cleaning import clean
from .config import BOOKING_WINDOWS, HISTORY_END, HISTORY_START, ROUTES, SOURCES
from .sources import BlockedError, SimulatedPortal

MAX_ATTEMPTS = 3


def scrape_cycle(scraped_at: datetime, sources=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Visit every portal x route x booking window once. Returns (raw rows, run log)."""
    sources = sources or [SimulatedPortal(s) for s in SOURCES]
    rows, runs = [], []
    for src in sources:
        for route in ROUTES:
            got, status, attempts = [], "blocked", 0
            for attempt in range(MAX_ATTEMPTS):
                attempts = attempt + 1
                try:
                    got = []
                    for w in BOOKING_WINDOWS:
                        dep = scraped_at.date() + timedelta(days=w)
                        got += src.fetch(route.code, dep, scraped_at, attempt=attempt)
                    status = "ok" if attempt == 0 else "recovered"
                    break
                except BlockedError:
                    continue            # next attempt uses a rotated browser profile
            rows += [r.to_dict() for r in got]
            runs.append(dict(scraped_at=scraped_at, source=src.name, route=route.code,
                             status=status, attempts=attempts, rows=len(got)))
    return pd.DataFrame(rows), pd.DataFrame(runs)


def run_day(con, day: date, hours=(6, 18)):
    stamps = [datetime.combine(day, time(h)).strftime("%Y-%m-%dT%H:%M:%S") for h in hours]
    for t in ("raw_fares", "clean_fares", "scrape_runs"):   # re-running a cycle replaces it
        con.executemany(f"DELETE FROM {t} WHERE scraped_at = ?", [(s,) for s in stamps])
    raws, runs = [], []
    for h in hours:
        r, l = scrape_cycle(datetime.combine(day, time(h)))
        raws.append(r)
        runs.append(l)
    raw = pd.concat(raws, ignore_index=True)
    runlog = pd.concat(runs, ignore_index=True)
    fares, report = clean(raw)
    report["blocked_runs"] = int((runlog["status"] == "blocked").sum())
    report["recovered_runs"] = int((runlog["status"] == "recovered").sum())
    storage.save(con, "raw_fares", raw)
    storage.save(con, "clean_fares", fares)
    storage.save(con, "scrape_runs", runlog)
    storage.save_quality(con, day.isoformat(), report)
    return report


def backfill(start: date = HISTORY_START, end: date = HISTORY_END, verbose=True):
    storage.DB_PATH.unlink(missing_ok=True)
    with storage.connect() as con:
        d = start
        while d <= end:
            rep = run_day(con, d)
            if verbose and (d.day == 1 or d == end):
                print(f"{d}  raw={rep['raw_rows']:>5}  clean={rep['clean_rows']:>5}  "
                      f"pass={rep['pass_rate']:.1%}  blocked={rep['blocked_runs']}")
            d += timedelta(days=1)


def main():
    ap = argparse.ArgumentParser(description="AirIndex pipeline")
    ap.add_argument("cmd", choices=["backfill", "cycle"])
    ap.add_argument("--date", help="YYYY-MM-DD for a single cycle day")
    a = ap.parse_args()
    if a.cmd == "backfill":
        backfill()
    else:
        day = date.fromisoformat(a.date) if a.date else date.today()
        with storage.connect() as con:
            print(run_day(con, day))


if __name__ == "__main__":
    main()
