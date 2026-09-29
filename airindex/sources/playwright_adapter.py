"""Template for a live portal adapter using Playwright.

This file shows how a real adapter plugs into the pipeline. It is not wired
to any specific website: every portal needs its own URL pattern and
selectors, written after checking that portal's robots.txt and terms of use
(or, better, a data-sharing agreement arranged through MoSPI).

Two ideas from the pitch are implemented here:

* Self-healing selectors: each field has an ordered list of candidate
  selectors. When the first stops matching after a site redesign, the next
  one is tried, and the adapter records which one worked so the failure shows
  up on the pipeline-health panel before the index is affected.
* Polite crawling: one browser context per portal, fixed delay between
  requests, and a rotated context (fresh user agent / viewport) when a block
  page is detected.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime

from .base import BlockedError, FareSource, RawFare

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36",
]


@dataclass
class SelectorSet:
    """Ordered fallbacks for one field; remembers which candidate last worked."""
    candidates: list[str]
    last_good: int = 0
    misses: dict[str, int] = field(default_factory=dict)

    def query_all(self, page):
        order = [self.last_good] + [i for i in range(len(self.candidates)) if i != self.last_good]
        for i in order:
            sel = self.candidates[i]
            found = page.query_selector_all(sel)
            if found:
                self.last_good = i
                return found
            self.misses[sel] = self.misses.get(sel, 0) + 1
        return []


@dataclass
class PortalSpec:
    name: str
    url_template: str               # e.g. "https://example.com/search?from={o}&to={d}&date={dt}"
    card: SelectorSet               # one result card per flight
    airline: SelectorSet
    flight_no: SelectorSet
    total: SelectorSet
    base: SelectorSet | None = None
    taxes: SelectorSet | None = None
    block_markers: tuple[str, ...] = ("captcha", "access denied", "unusual traffic")
    delay_s: float = 4.0


class PlaywrightPortal(FareSource):
    def __init__(self, spec: PortalSpec, headless: bool = True):
        from playwright.sync_api import sync_playwright   # imported lazily
        self.spec = spec
        self.name = spec.name
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._new_context()

    def _new_context(self):
        self._ctx = self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": random.choice([1280, 1366, 1440]), "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )

    def fetch(self, route: str, departure: date, scraped_at: datetime, attempt: int = 0):
        if attempt:
            self._ctx.close()
            self._new_context()                     # rotate identity on retry
        o, d = route.split("-")
        page = self._ctx.new_page()
        try:
            page.goto(self.spec.url_template.format(o=o, d=d, dt=departure.isoformat()),
                      wait_until="networkidle", timeout=45_000)
            body = (page.text_content("body") or "").lower()
            if any(m in body for m in self.spec.block_markers):
                raise BlockedError(f"{self.name}: block page on {route}")

            rows = []
            for card in self.spec.card.query_all(page):
                def grab(ss):
                    if ss is None:
                        return None
                    el = ss.query_all(card)
                    return el[0].inner_text().strip() if el else None
                rows.append(RawFare(
                    scraped_at, self.name, route, departure,
                    grab(self.spec.airline) or "Unknown",
                    grab(self.spec.flight_no) or "",
                    grab(self.spec.base), grab(self.spec.taxes), grab(self.spec.total),
                ))
            return rows
        finally:
            page.close()
            time.sleep(self.spec.delay_s)            # polite rate limit

    def close(self):
        self._browser.close()
        self._pw.stop()
