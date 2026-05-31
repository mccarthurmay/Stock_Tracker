"""Rate-limited Alpaca data client for the research spine.

Wraps alpaca-py's stock + option historical clients and the trading client's
contracts endpoint, returning DataFrames already shaped for storage.py. A
thread-safe sliding-window rate limiter (same pattern as the legacy backend)
keeps us under the free-tier ~200 req/min ceiling.

Note: get_option_bars takes no feed argument — option bars come from the
account-default feed (indicative on the free tier). We record config.OPTIONS_FEED
on every option row so a later run can never silently mix feeds (ROADMAP §2a).
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime

import pandas as pd

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, OptionBarsRequest, OptionSnapshotRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed, Adjustment, OptionsFeed
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.enums import AssetStatus

from . import settings as config
from .occ import parse_occ

_UNIT = {
    "min": TimeFrameUnit.Minute, "minute": TimeFrameUnit.Minute,
    "hour": TimeFrameUnit.Hour, "h": TimeFrameUnit.Hour,
    "day": TimeFrameUnit.Day, "d": TimeFrameUnit.Day,
    "week": TimeFrameUnit.Week, "w": TimeFrameUnit.Week,
}
_TF_RE = re.compile(r"^\s*(\d+)\s*([a-zA-Z]+)\s*$")


def parse_timeframe(tf: str) -> TimeFrame:
    """'1Min' / '5Min' / '1Hour' / '1Day' -> TimeFrame."""
    m = _TF_RE.match(tf)
    if not m:
        raise ValueError(f"bad timeframe {tf!r} (expected like '1Min', '1Day')")
    amount, unit = int(m.group(1)), m.group(2).lower()
    if unit not in _UNIT:
        raise ValueError(f"unknown timeframe unit {unit!r}")
    return TimeFrame(amount, _UNIT[unit])


class RateLimiter:
    """Thread-safe sliding-window limiter (mirrors backend/data/analysis.py)."""

    def __init__(self, max_per_minute: int):
        self.max = max_per_minute
        self.calls: list[datetime] = []
        self.lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = datetime.now()
                self.calls = [t for t in self.calls if (now - t).total_seconds() < 60]
                if len(self.calls) < self.max:
                    self.calls.append(now)
                    return
                sleep_for = 60 - (now - self.calls[0]).total_seconds()
            if sleep_for > 0:
                time.sleep(sleep_for)


def _bars_to_records(barset, symbol: str) -> list[dict]:
    """Extract Bar rows for one symbol from a BarSet (empty list if none)."""
    data = getattr(barset, "data", {}) or {}
    return [
        {
            "ts": pd.to_datetime(b.timestamp, utc=True),
            "open": b.open, "high": b.high, "low": b.low, "close": b.close,
            "volume": int(b.volume) if b.volume is not None else None,
            "trade_count": int(b.trade_count) if b.trade_count is not None else None,
            "vwap": b.vwap,
        }
        for b in data.get(symbol, [])
    ]


class AlpacaResearch:
    """Rate-limited Alpaca access for the research module."""

    def __init__(self, max_per_minute: int | None = None):
        key, secret = config.get_credentials()
        self.stock = StockHistoricalDataClient(key, secret)
        self.option = OptionHistoricalDataClient(key, secret)
        self.trading = TradingClient(key, secret, paper=True)
        self.rl = RateLimiter(max_per_minute or config.MAX_REQUESTS_PER_MINUTE)
        self.options_feed = config.OPTIONS_FEED
        self._stock_feed = DataFeed(config.STOCK_FEED)
        self._adjustment = Adjustment(config.UNDERLYING_ADJUSTMENT)

    # -- underlying ---------------------------------------------------------
    def stock_bars(self, symbol: str, start: datetime, end: datetime,
                   timeframe: str) -> pd.DataFrame:
        self.rl.acquire()
        req = StockBarsRequest(
            symbol_or_symbols=symbol, start=start, end=end,
            timeframe=parse_timeframe(timeframe),
            adjustment=self._adjustment, feed=self._stock_feed,
        )
        recs = _bars_to_records(self.stock.get_stock_bars(req), symbol)
        df = pd.DataFrame(recs)
        if df.empty:
            return df
        df.insert(0, "symbol", symbol)
        df.insert(1, "timeframe", timeframe)
        return df

    # -- options ------------------------------------------------------------
    def option_bars(self, symbols: list[str], start: datetime, end: datetime,
                    timeframe: str) -> pd.DataFrame:
        self.rl.acquire()
        req = OptionBarsRequest(
            symbol_or_symbols=symbols, start=start, end=end,
            timeframe=parse_timeframe(timeframe),
        )
        barset = self.option.get_option_bars(req)
        frames = []
        for sym in symbols:
            recs = _bars_to_records(barset, sym)
            if not recs:
                continue
            c = parse_occ(sym)
            df = pd.DataFrame(recs)
            df.insert(0, "option_symbol", sym)
            df.insert(1, "underlying", c.underlying)
            df.insert(2, "expiry", c.expiry)
            df.insert(3, "strike", c.strike)
            df.insert(4, "opt_type", c.opt_type)
            df.insert(5, "timeframe", timeframe)
            df["feed"] = self.options_feed
            frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def option_snapshots(self, symbols: list[str]) -> dict:
        """Latest snapshot (incl. live IV + Greeks) — for M2 sanity checks."""
        self.rl.acquire()
        req = OptionSnapshotRequest(
            symbol_or_symbols=symbols, feed=OptionsFeed(self.options_feed)
        )
        return self.option.get_option_snapshot(req)

    # -- contract universe --------------------------------------------------
    def list_contracts(self, underlying: str, expiration_gte=None, expiration_lte=None,
                        strike_gte=None, strike_lte=None, page_limit: int = 10_000) -> list:
        """All ACTIVE contracts for an underlying, following pagination."""
        out, page_token = [], None
        while True:
            self.rl.acquire()
            req = GetOptionContractsRequest(
                underlying_symbols=[underlying],
                status=AssetStatus.ACTIVE,
                expiration_date_gte=expiration_gte,
                expiration_date_lte=expiration_lte,
                strike_price_gte=str(strike_gte) if strike_gte is not None else None,
                strike_price_lte=str(strike_lte) if strike_lte is not None else None,
                limit=page_limit,
                page_token=page_token,
            )
            resp = self.trading.get_option_contracts(req)
            out.extend(resp.option_contracts or [])
            page_token = getattr(resp, "next_page_token", None)
            if not page_token:
                break
        return out
