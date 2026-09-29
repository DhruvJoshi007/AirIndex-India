"""Zero-dependency server for machines without FastAPI installed.

    python -m airindex.devserver        # http://localhost:8000

Serves the dashboard plus the same /api/snapshot, /api/cpi-feed and
/api/cycle routes as airindex.api, using only the standard library.
Use airindex.api (FastAPI) for the full API with Swagger docs.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import pipeline, snapshot, storage
from .config import ROOT

_cache: dict = {}


def snap(refresh=False):
    if refresh or "s" not in _cache:
        _cache["s"] = snapshot.build()
    return _cache["s"]


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, indent=2).encode(), code=code)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send((ROOT / "dashboard" / "index.html").read_bytes(), "text/html; charset=utf-8")
        s = snap()
        if path == "/api/snapshot":
            return self._json(s)
        if path == "/api/index/monthly":
            return self._json(s["cpi_feed"])
        if path == "/api/cpi-feed":
            return self._json(dict(
                series="AirIndex India, domestic economy airfare",
                cpi_group="Transport and communication",
                base_period=s["meta"]["base_period"], base_value=100,
                method="Jevons elementary indices by route x booking window, fixed traffic weights",
                observations=s["cpi_feed"]))
        if path == "/api/quality":
            return self._json(dict(quality=s["quality"], scraper_health=s["health"]))
        self._json({"detail": "Not Found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/cycle":
            return self._json({"detail": "Not Found"}, 404)
        q = parse_qs(u.query)
        day = (date.fromisoformat(q["day"][0]) if "day" in q
               else date.fromisoformat(snap()["meta"]["last_date"]) + timedelta(days=1))
        with storage.connect() as con:
            report = pipeline.run_day(con, day)
        new = snap(refresh=True)
        self._json(dict(day=day.isoformat(), report=report, index=new["kpi"]["index"]))

    def log_message(self, *a):
        pass


def main(port=8000):
    print(f"AirIndex dashboard on http://localhost:{port}")
    snap()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
