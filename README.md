# AirIndex India (demo)

**SIH 2026 · PS 26056 · Theme: Travel & Tourism · Team ERROR502**

A working prototype of a real-time airfare price index for India. Fares are collected from airline and online travel aggregator (OTA) portals, cleaned, turned into a CPI-style index and served through a dashboard and a REST API that MoSPI could plug into the Consumer Price Index.

> **Demo data.** The scrapers in this build are *simulated portals* (`airindex/sources/simulated.py`). They reproduce dynamic pricing, seasonality, portal quirks and anti-bot blocks so the full pipeline can be shown offline and reproduced exactly. No real website is contacted. A Playwright adapter template for live portals is included.

**Walkthrough video:** [`media/AirIndex_India_demo.mp4`](media/AirIndex_India_demo.mp4) (1:42)

## Quick start

```bash
pip install -r requirements.txt
python -m airindex.pipeline backfill        # builds 1 Apr to 28 Sep 2026 of history (~1 min, ~540k clean fares)
uvicorn airindex.api:app --reload           # dashboard: http://localhost:8000   API docs: /docs
```

No FastAPI available? `python -m airindex.devserver` serves the same dashboard and core endpoints with only the standard library.

Offline single file for judges: `python scripts/build_static.py` writes `dist/airindex_dashboard.html` with the data baked in.

Docker: `docker compose up --build` (the image runs the backfill during build).

Tests: `pytest -q`

## What the demo shows

| Pitch-deck claim | Where it lives in the code |
|---|---|
| Bots scrape airline sites & OTAs | `sources/simulated.py` (demo), `sources/playwright_adapter.py` (live template) |
| Self-healing scrapers | `SelectorSet` fallback selectors; retry with a rotated browser profile in `pipeline.scrape_cycle` |
| Anomaly filtering | `cleaning.py`: price-text parsing, de-duplication, tax rebuilding, hard bounds, robust MAD z-score |
| Capture total fare incl. taxes | portals that show only the base fare get taxes rebuilt from the ratio seen on other portals for the same route, window and cycle |
| Booking-window-aware, route-weighted index | `index_engine.py` |
| Captures 200–400% day-to-day pricing | "Dynamic pricing spread" tile and booking-window curve (dearest ÷ cheapest ≈ 3.6×) |
| Live dashboard + open API for MoSPI | `dashboard/index.html`, `api.py` (`/api/cpi-feed`) |
| Hourly scrape scheduling (Airflow) | `dags/airindex_dag.py` with a data-quality gate |
| PostgreSQL + TimescaleDB store | `storage.py` uses SQLite for zero setup; same schema, swap the connection |

## Index method

Follows the ILO *Consumer Price Index Manual* (2004).

1. **Elementary aggregate** = one route × one booking window (D-1, D-7, D-14, D-30, D-60), economy, one-way. A fare bought one day before departure is only ever compared with other fares bought one day before departure.
2. **Elementary price** for a day = geometric mean of every clean fare in that cell (all airlines, all portals).
3. **Elementary index** = Jevons: today's geometric mean ÷ base-period geometric mean × 100. Base period is April 2026.
4. **Route index** = booking-window-weighted average of its five cells.
5. **Headline index** = traffic-weighted average of the ten route indices (fixed basket, Laspeyres-type).
6. **Monthly CPI value** = mean of the daily headline values in the month.
7. Missing cells are carried forward from their last observed value.

The test `test_jevons_ignores_booking_window_mix` checks the key property: if travellers buy more last-minute tickets but prices do not change, the index stays at 100.

Weights in `config.py` are illustrative. In production, route weights come from DGCA monthly domestic traffic and booking-window weights from OTA booking-lead-time data, revised yearly.

## API

| Method | Path | Returns |
|---|---|---|
| GET | `/api/cpi-feed` | Monthly sub-index with base period and method metadata (MoSPI hand-over) |
| GET | `/api/index/monthly` | Monthly index and month-on-month change |
| GET | `/api/index/daily?route=DEL-BOM&days=90` | Daily headline or route index |
| GET | `/api/routes` | Basket, weights, booking curves, price spread |
| GET | `/api/fares/latest?route=DEL-BOM&window=1` | Clean fares from the last cycle |
| GET | `/api/quality` | Cleaning log and scraper health |
| POST | `/api/cycle?day=2026-09-29` | Run one scrape and clean cycle, then recompute |
| GET | `/api/snapshot` | Everything the dashboard renders |

## Project layout

```
airindex/
  config.py            routes, weights, windows, thresholds
  sources/
    base.py            RawFare record + FareSource interface
    simulated.py       offline portal simulator (demo data)
    playwright_adapter.py  live adapter template: fallback selectors, polite crawling
  cleaning.py          parse, dedupe, rebuild taxes, bounds, MAD outlier filter
  storage.py           SQLite store (Timescale-ready schema)
  index_engine.py      Jevons elementary indices, weighting, monthly feed
  pipeline.py          scrape cycle + backfill CLI
  snapshot.py          one JSON bundle for dashboard/API
  api.py               FastAPI app
  devserver.py         stdlib fallback server
dashboard/index.html   the dashboard (vanilla JS + SVG, no build step)
dags/airindex_dag.py   Airflow hourly DAG
scripts/build_static.py   bake data into a single offline HTML file
scripts/record_demo.js    Playwright script that records the walkthrough video
tests/test_pipeline.py
```

## Going live

Write one `PortalSpec` per portal in `playwright_adapter.py` (URL pattern + candidate selectors), check its robots.txt and terms, keep the polite delay, and pass `PlaywrightPortal(spec)` objects into `pipeline.scrape_cycle(..., sources=[...])`. Everything downstream stays the same. A formal data-sharing arrangement with airlines and OTAs through MoSPI is the cleaner long-term route.
