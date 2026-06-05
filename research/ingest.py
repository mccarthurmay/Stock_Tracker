"""Ingest orchestration: pull -> store -> log, plus underlying/option alignment.

Alignment joins option bars to the underlying bar at the *same* bar-start
timestamp and timeframe (ROADMAP §2c). It also attaches ``knowable_at`` =
ts + timeframe, the earliest moment a bar's close is known — the hook the
backtester's signal->fill invariant (ROADMAP §5) will hang off of.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from . import settings as config
from .client import parse_timeframe


def _timeframe_delta(timeframe: str) -> pd.Timedelta:
    tf = parse_timeframe(timeframe)
    unit = str(tf.unit_value).lower() if hasattr(tf, "unit_value") else ""
    amount = getattr(tf, "amount_value", None) or getattr(tf, "amount", 1)
    # str(TimeFrame) looks like '1Min' / '1Hour' / '1Day'; map the unit word.
    s = str(tf).lower()
    if "min" in s:
        return pd.Timedelta(minutes=amount)
    if "hour" in s:
        return pd.Timedelta(hours=amount)
    if "day" in s:
        return pd.Timedelta(days=amount)
    if "week" in s:
        return pd.Timedelta(weeks=amount)
    raise ValueError(f"cannot derive interval for timeframe {timeframe!r}")


def ingest_underlying(client, store, symbol: str, start: datetime, end: datetime,
                      timeframe: str) -> int:
    df = client.stock_bars(symbol, start, end, timeframe)
    n = store.upsert_underlying_bars(df)
    store.log_ingest("underlying_bars", symbol, timeframe, start, end,
                     config.STOCK_FEED, n)
    return n


def ingest_options(client, store, symbols: list[str], start: datetime, end: datetime,
                   timeframe: str) -> int:
    df = client.option_bars(symbols, start, end, timeframe)
    n = store.upsert_option_bars(df)
    note = ",".join(symbols)
    store.log_ingest("option_bars", note[:240], timeframe, start, end,
                     client.options_feed, n)
    return n


def align(store, option_symbol: str, timeframe: str) -> pd.DataFrame:
    """Return option bars joined to the underlying close at the same ts."""
    q = """
        SELECT o.ts,
               o.option_symbol, o.underlying, o.expiry, o.strike, o.opt_type,
               o.open  AS opt_open,  o.high AS opt_high, o.low AS opt_low,
               o.close AS opt_close, o.volume AS opt_volume, o.vwap AS opt_vwap,
               o.feed,
               u.close AS under_close, u.vwap AS under_vwap
        FROM option_bars o
        JOIN underlying_bars u
          ON u.symbol = o.underlying AND u.timeframe = o.timeframe AND u.ts = o.ts
        WHERE o.option_symbol = ? AND o.timeframe = ?
        ORDER BY o.ts
    """
    df = store.con.execute(q, [option_symbol, timeframe]).df()
    if not df.empty:
        df["knowable_at"] = df["ts"] + _timeframe_delta(timeframe)
    return df
