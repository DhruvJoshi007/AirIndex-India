"""Common interface every fare source adapter implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import date, datetime


@dataclass
class RawFare:
    """One fare exactly as it was read off a portal page.

    Price fields are kept as text on purpose: portals print "₹5,432",
    "5432.00", "Sold out" and so on, and the cleaning stage owns parsing.
    """
    scraped_at: datetime
    source: str
    route: str
    departure: date
    airline: str
    flight_no: str
    base_fare_text: str | None
    taxes_text: str | None
    total_text: str | None

    def to_dict(self) -> dict:
        return asdict(self)


class BlockedError(RuntimeError):
    """The portal served a CAPTCHA / 403 / empty shell instead of results."""


class FareSource(ABC):
    name: str

    @abstractmethod
    def fetch(self, route: str, departure: date, scraped_at: datetime) -> list[RawFare]:
        """Return every economy fare listed for one route on one departure date."""
