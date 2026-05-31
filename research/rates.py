"""Risk-free rate provider, point-in-time by date (ROADMAP §2b).

Pulls a short-tenor Treasury series from FRED (default DGS1MO, the 1-month
yield — the right tenor for 0DTE/weekly options) and returns, for any date,
the most recent yield published on or before it. Falls back to a constant if
FRED is unavailable, so the rest of the pipeline never blocks on it.

FRED yields are annualized bond-equivalent percentages; we use value/100 as a
continuously-compounded approximation. The error is negligible at short rates
and trivial for 0DTE (where r barely moves the price at all).
"""
from __future__ import annotations

import os
from bisect import bisect_right
from datetime import date, datetime

import requests

from . import settings

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


class RateProvider:
    def __init__(self, series_id: str = "DGS1MO", default_rate: float | None = None):
        self.series_id = series_id
        self.default_rate = (
            float(os.getenv("RISK_FREE_DEFAULT", "0.05"))
            if default_rate is None else default_rate
        )
        self._dates: list[date] | None = None
        self._rates: list[float] | None = None
        self.source: str | None = None

    def _fred_key(self) -> str | None:
        key = os.getenv("FRED_SECRET") or os.getenv("FRED_KEY")
        if not key:
            settings.source_backend_env()
            key = os.getenv("FRED_SECRET") or os.getenv("FRED_KEY")
        return key

    def _load(self) -> None:
        if self._dates is not None:
            return
        self._dates, self._rates = [], []
        key = self._fred_key()
        if not key:
            self.source = f"constant:{self.default_rate}"
            return
        try:
            resp = requests.get(
                FRED_URL,
                params={"series_id": self.series_id, "api_key": key, "file_type": "json"},
                timeout=15,
            )
            resp.raise_for_status()
            pairs = []
            for o in resp.json().get("observations", []):
                v = o.get("value")
                if v in (None, "", "."):
                    continue
                try:
                    pairs.append((datetime.strptime(o["date"], "%Y-%m-%d").date(),
                                  float(v) / 100.0))
                except ValueError:
                    continue
            pairs.sort()
            self._dates = [d for d, _ in pairs]
            self._rates = [r for _, r in pairs]
            self.source = (f"FRED:{self.series_id}" if self._dates
                           else f"constant:{self.default_rate}")
        except Exception:
            self.source = f"constant:{self.default_rate}"

    def rate_for(self, when) -> float:
        """Most recent yield on or before `when` (date/datetime/Timestamp)."""
        self._load()
        if not self._dates:
            return self.default_rate
        d = when.date() if hasattr(when, "date") else when
        i = bisect_right(self._dates, d)
        return self._rates[i - 1] if i > 0 else self._rates[0]
