"""SQLite fare store.

The demo uses SQLite so it runs with zero setup. The schema maps one-to-one
onto PostgreSQL + TimescaleDB (make `clean_fares.scraped_at` a hypertable
time column); set AIRINDEX_DB_URL and swap the connection helper to move over.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

import pandas as pd

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_fares (
    scraped_at TEXT, source TEXT, route TEXT, departure TEXT, airline TEXT,
    flight_no TEXT, base_fare_text TEXT, taxes_text TEXT, total_text TEXT);
CREATE TABLE IF NOT EXISTS clean_fares (
    scraped_at TEXT, scrape_date TEXT, source TEXT, route TEXT, departure TEXT,
    window INTEGER, airline TEXT, flight_no TEXT, total REAL, imputed_total INTEGER);
CREATE INDEX IF NOT EXISTS ix_clean_date ON clean_fares(scrape_date, route, window);
CREATE TABLE IF NOT EXISTS scrape_runs (
    scraped_at TEXT, source TEXT, route TEXT, status TEXT, attempts INTEGER, rows INTEGER);
CREATE TABLE IF NOT EXISTS quality_log (scrape_date TEXT PRIMARY KEY, report TEXT);
"""


@contextmanager
def connect():
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def _stringify(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%S")
        elif out[c].dtype == object:
            out[c] = out[c].map(lambda v: v.isoformat() if hasattr(v, "isoformat") else v)
    return out


def save(con, table: str, df: pd.DataFrame):
    if len(df):
        _stringify(df).to_sql(table, con, if_exists="append", index=False)


def save_quality(con, scrape_date: str, report: dict):
    con.execute("INSERT OR REPLACE INTO quality_log VALUES (?, ?)",
                (scrape_date, json.dumps(report)))


def load_clean(con) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM clean_fares", con)
    df["scraped_at"] = pd.to_datetime(df["scraped_at"])
    df["scrape_date"] = pd.to_datetime(df["scrape_date"])
    df["departure"] = pd.to_datetime(df["departure"])
    return df


def load_runs(con) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM scrape_runs", con)
    df["scraped_at"] = pd.to_datetime(df["scraped_at"])
    return df


def load_quality(con) -> pd.DataFrame:
    rows = con.execute("SELECT scrape_date, report FROM quality_log ORDER BY scrape_date").fetchall()
    return pd.DataFrame([{"scrape_date": d, **json.loads(r)} for d, r in rows])
