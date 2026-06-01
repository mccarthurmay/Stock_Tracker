"""Deep historical ingest via point-in-time contract construction (ROADMAP §2c).

Alpaca's *active* contracts endpoint can't show expired options, but the
historical option-bars endpoint *will* serve an expired contract's bars if you
name it. So to build deep history without survivorship bias we:

  1. walk forward week by week from a start date,
  2. on each Monday, read SPY's price AT THAT TIME (point-in-time spot),
  3. construct the OCC symbol for that week's Friday-expiry ATM call & put at
     the strike nearest the PIT spot (rounded to the listed $1 grid),
  4. pull that contract's bars for the days it was the front-week contract.

This selects contracts using ONLY information available at the time (the spot
and the known expiry calendar) — no peeking at which contracts "worked out."
Strikes are PIT-ATM by construction, which is the regime our hypotheses target.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, date

import pandas as pd

from . import ingest
from .occ import build_occ


def _fridays(start: date, end: date):
    """Yield every Friday in [start, end] (weekly SPY expiries land on Fridays;
    holiday-shifted weeks simply return no bars and are skipped)."""
    d = start + timedelta((4 - start.weekday()) % 7)  # first Friday on/after start
    while d <= end:
        yield d
        d += timedelta(days=7)


def _spot_on(client, when: date) -> float | None:
    """SPY close on/just before `when` (point-in-time spot)."""
    start = datetime(when.year, when.month, when.day, tzinfo=timezone.utc) - timedelta(days=5)
    end = datetime(when.year, when.month, when.day, tzinfo=timezone.utc) + timedelta(days=1)
    df = client.stock_bars("SPY", start, end, "1Day")
    return float(df["close"].iloc[-1]) if not df.empty else None


def deep_ingest(client, store, underlying="SPY", start_date=date(2024, 2, 5),
                end_date: date | None = None, timeframe="5Min",
                strike_round=1.0, window_days=5) -> dict:
    """Ingest deep history of front-week ATM call+put, week by week.

    For each weekly Friday expiry, pick the ATM strike from the PIT spot the
    Monday of that week, then pull that contract's bars for the 5 trading days
    leading into expiry. Underlying bars are ingested per-week alongside.
    """
    end_date = end_date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    syms_ingested, total_opt, total_und, weeks, skipped = [], 0, 0, 0, 0

    for friday in _fridays(start_date, end_date):
        monday = friday - timedelta(days=4)
        spot = _spot_on(client, monday)
        if spot is None:
            skipped += 1
            continue
        strike = round(spot / strike_round) * strike_round

        win_start = datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)
        win_end = datetime(friday.year, friday.month, friday.day, tzinfo=timezone.utc) + timedelta(days=1)

        # underlying for this week (idempotent upsert; dedups across weeks)
        total_und += ingest.ingest_underlying(client, store, underlying,
                                              win_start, win_end, timeframe)

        week_syms = [build_occ(underlying, friday, t, float(strike)) for t in ("call", "put")]
        n = ingest.ingest_options(client, store, week_syms, win_start, win_end, timeframe)
        if n > 0:
            total_opt += n
            syms_ingested.extend(week_syms)
        else:
            skipped += 1
        weeks += 1

    return {"weeks": weeks, "contracts": len(set(syms_ingested)),
            "option_bars": total_opt, "underlying_bars": total_und,
            "skipped_weeks": skipped, "timeframe": timeframe}
