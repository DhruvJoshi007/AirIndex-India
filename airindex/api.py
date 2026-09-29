"""REST API + dashboard server.

Run:  uvicorn airindex.api:app --reload
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import threading
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import pipeline, snapshot, storage
from .config import ROOT, ROUTE_BY_CODE

app = FastAPI(
    title="AirIndex India API",
    version="0.1.0",
    description="Real-time airfare price index for CPI augmentation (SIH 2026, PS 26056, team ERROR502). "
                "Demo build: fares come from simulated portals.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_cache: dict = {}
_lock = threading.Lock()


def snap(refresh: bool = False) -> dict:
    with _lock:
        if refresh or "s" not in _cache:
            _cache["s"] = snapshot.build()
        return _cache["s"]


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(ROOT / "dashboard" / "index.html")


@app.get("/api/snapshot", tags=["dashboard"])
def get_snapshot():
    """Everything the dashboard renders, in one payload."""
    return snap()


@app.get("/api/index/daily", tags=["index"])
def daily(route: str | None = Query(None, description="e.g. DEL-BOM; omit for headline"),
          days: int = Query(90, ge=1, le=3650)):
    s = snap()
    if route is None:
        h = s["headline"]
        return [dict(date=d, index=v, ma7=m) for d, v, m in
                zip(h["dates"][-days:], h["index"][-days:], h["ma7"][-days:])]
    r = next((x for x in s["routes"] if x["code"] == route.upper()), None)
    if r is None:
        raise HTTPException(404, f"Unknown route {route}. Try one of {list(ROUTE_BY_CODE)}")
    dates = s["headline"]["dates"][-len(r["series"]):]
    return [dict(date=d, index=v) for d, v in list(zip(dates, r["series"]))[-days:]]


@app.get("/api/index/monthly", tags=["index"])
def monthly():
    """Monthly airfare sub-index, ready to slot into CPI (Transport & Communication)."""
    return snap()["cpi_feed"]


@app.get("/api/cpi-feed", tags=["index"])
def cpi_feed():
    """MoSPI hand-over format: one record per month with metadata."""
    s = snap()
    return dict(
        series="AirIndex India, domestic economy airfare",
        cpi_group="Transport and communication",
        base_period=s["meta"]["base_period"],
        base_value=100,
        method="Jevons elementary indices by route x booking window, fixed traffic weights",
        observations=s["cpi_feed"],
    )


@app.get("/api/routes", tags=["index"])
def routes():
    return [{k: v for k, v in r.items() if k != "series"} for r in snap()["routes"]]


@app.get("/api/fares/latest", tags=["fares"])
def latest_fares(route: str | None = None, window: int | None = None):
    rows = snap()["latest_fares"]
    if route:
        rows = [r for r in rows if r["route"] == route.upper()]
    if window is not None:
        rows = [r for r in rows if r["window"] == window]
    return rows


@app.get("/api/quality", tags=["pipeline"])
def quality():
    s = snap()
    return dict(quality=s["quality"], scraper_health=s["health"])


@app.post("/api/cycle", tags=["pipeline"])
def run_cycle(day: date | None = None):
    """Run one scrape + clean cycle for a day (default: the day after the latest data),
    then recompute the index."""
    s = snap()
    day = day or date.fromisoformat(s["meta"]["last_date"]) + timedelta(days=1)
    with storage.connect() as con:
        report = pipeline.run_day(con, day)
    new = snap(refresh=True)
    return dict(day=day.isoformat(), report=report, index=new["kpi"]["index"])
