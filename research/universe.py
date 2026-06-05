"""Point-in-time contract-universe snapshots.

Alpaca's contracts endpoint reports the universe *as of now*. We can only
build point-in-time history going forward, so each snapshot is stamped with
``as_of_date`` and stored as its own row. Open interest is a daily snapshot
(ROADMAP §2c) — do not treat it as intraday.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd


def _enum(v):
    return v.value if hasattr(v, "value") else (str(v) if v is not None else None)


def _to_float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def contracts_to_df(contracts, as_of: date) -> pd.DataFrame:
    rows = [
        {
            "option_symbol": c.symbol,
            "underlying": c.underlying_symbol,
            "expiry": c.expiration_date,
            "strike": _to_float(c.strike_price),
            "opt_type": _enum(c.type),
            "style": _enum(c.style),
            "status": _enum(c.status),
            "tradable": bool(c.tradable),
            "size": str(c.size) if c.size is not None else None,
            "open_interest": _to_int(c.open_interest),
            "open_interest_date": c.open_interest_date,
            "close_price": _to_float(c.close_price),
            "close_price_date": c.close_price_date,
            "as_of_date": as_of,
        }
        for c in contracts
    ]
    return pd.DataFrame(rows)


def snapshot_universe(client, store, underlying: str, expiration_gte: Optional[date] = None,
                      expiration_lte: Optional[date] = None, strike_gte=None,
                      strike_lte=None, as_of: Optional[date] = None) -> pd.DataFrame:
    as_of = as_of or date.today()
    contracts = client.list_contracts(
        underlying, expiration_gte=expiration_gte, expiration_lte=expiration_lte,
        strike_gte=strike_gte, strike_lte=strike_lte,
    )
    df = contracts_to_df(contracts, as_of)
    n = store.upsert_universe(df)
    store.log_ingest("universe", underlying, None, None, None, None, n,
                     note=f"as_of={as_of} contracts={n}")
    return df
