"""Indicator library (ROADMAP §3).

Pure, causal indicator functions over a feature frame. Every function uses
only data at or before each row (rolling/ewm/diff/cumulative are all causal),
so the registry's no-lookahead contract holds by construction.

The frame is expected to carry (from ingest.align + greeks):
  ts, under_close, under_vwap, opt_close, opt_vwap, opt_volume, strike, opt_type
  and (after greeks) iv, delta, gamma, vega_pct, theta_day, dte_days, tte_years.

Indicators take the column they act on as a param (default under_close), so the
same RSI works on the underlying or, if asked, on the option price. Spread/flow
indicators are deliberately absent: no historical quotes exist on Alpaca.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .registry import register

# ----------------------------------------------------------------- trend
@register(name="sma", layer="trend", inputs=["under_close"],
          params={"window": 20, "col": "under_close"},
          param_ranges={"window": [10, 20, 50, 100]},
          description="Simple moving average of the price column.")
def sma(df, window=20, col="under_close"):
    return df[col].rolling(window, min_periods=window).mean()


@register(name="ema", layer="trend", inputs=["under_close"],
          params={"window": 20, "col": "under_close"},
          param_ranges={"window": [12, 26, 50]},
          description="Exponential moving average (causal).")
def ema(df, window=20, col="under_close"):
    return df[col].ewm(span=window, adjust=False, min_periods=window).mean()


@register(name="price_vs_sma", layer="trend", inputs=["under_close"],
          params={"window": 20, "col": "under_close"},
          param_ranges={"window": [20, 50, 100]},
          description="(price - SMA) / SMA: fractional distance above/below trend.")
def price_vs_sma(df, window=20, col="under_close"):
    ma = df[col].rolling(window, min_periods=window).mean()
    return (df[col] - ma) / ma


@register(name="macd_hist", layer="trend", inputs=["under_close"],
          params={"fast": 12, "slow": 26, "signal": 9, "col": "under_close"},
          description="MACD histogram = MACD line - signal line.")
def macd_hist(df, fast=12, slow=26, signal=9, col="under_close"):
    p = df[col]
    macd = (p.ewm(span=fast, adjust=False).mean()
            - p.ewm(span=slow, adjust=False).mean())
    return macd - macd.ewm(span=signal, adjust=False).mean()


# ----------------------------------------------------------------- momentum
@register(name="rsi", layer="momentum", inputs=["under_close"],
          params={"window": 14, "col": "under_close"},
          param_ranges={"window": [7, 14, 21]},
          description="Wilder-style RSI (0-100) via causal rolling means.")
def rsi(df, window=14, col="under_close"):
    delta = df[col].diff()
    up = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    roll_up = up.rolling(window, min_periods=window).mean()
    roll_down = down.rolling(window, min_periods=window).mean()
    # No losses in the window -> RS = +inf -> RSI = 100 (Wilder convention).
    # Suppress the benign divide-by-zero; inf propagates to the correct value.
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = roll_up / roll_down
    out = 100 - 100 / (1 + rs)
    # Both means zero (flat window) is undefined; leave as NaN only there.
    return out.where(~((roll_up == 0) & (roll_down == 0)))


@register(name="roc", layer="momentum", inputs=["under_close"],
          params={"window": 10, "col": "under_close"},
          param_ranges={"window": [5, 10, 20, 60]},
          description="Rate of change over `window` bars (fractional).")
def roc(df, window=10, col="under_close"):
    return df[col].pct_change(window)


@register(name="stoch_k", layer="momentum", inputs=["under_close"],
          params={"window": 14, "col": "under_close"},
          description="Stochastic %K on the price column (no separate H/L).")
def stoch_k(df, window=14, col="under_close"):
    p = df[col]
    lo = p.rolling(window, min_periods=window).min()
    hi = p.rolling(window, min_periods=window).max()
    return 100 * (p - lo) / (hi - lo).replace(0, np.nan)


# ----------------------------------------------------------------- volatility
@register(name="realized_vol", layer="volatility", inputs=["under_close"],
          params={"window": 20, "col": "under_close", "annualize": True},
          param_ranges={"window": [10, 20, 60]},
          description="Rolling std of log returns; annualized by sqrt(252) if set.")
def realized_vol(df, window=20, col="under_close", annualize=True):
    r = np.log(df[col] / df[col].shift(1))
    vol = r.rolling(window, min_periods=window).std()
    return vol * np.sqrt(252) if annualize else vol


@register(name="bollinger_pctb", layer="volatility", inputs=["under_close"],
          params={"window": 20, "n_std": 2.0, "col": "under_close"},
          param_ranges={"window": [10, 20], "n_std": [1.5, 2.0, 2.5]},
          description="%B: position within Bollinger bands (0=lower,1=upper).")
def bollinger_pctb(df, window=20, n_std=2.0, col="under_close"):
    p = df[col]
    ma = p.rolling(window, min_periods=window).mean()
    sd = p.rolling(window, min_periods=window).std()
    lower, upper = ma - n_std * sd, ma + n_std * sd
    return (p - lower) / (upper - lower).replace(0, np.nan)


@register(name="bollinger_bw", layer="volatility", inputs=["under_close"],
          params={"window": 20, "n_std": 2.0, "col": "under_close"},
          description="Bollinger bandwidth = (upper-lower)/mid; squeeze detector.")
def bollinger_bw(df, window=20, n_std=2.0, col="under_close"):
    p = df[col]
    ma = p.rolling(window, min_periods=window).mean()
    sd = p.rolling(window, min_periods=window).std()
    return (2 * n_std * sd) / ma


# ----------------------------------------------------------------- volume
@register(name="rvol", layer="volume", inputs=["opt_volume"],
          params={"window": 20, "col": "opt_volume"},
          param_ranges={"window": [10, 20, 50]},
          description="Relative volume = volume / its rolling mean.")
def rvol(df, window=20, col="opt_volume"):
    v = df[col]
    return v / v.rolling(window, min_periods=window).mean().replace(0, np.nan)


# ----------------------------------------------------------------- option / greek (phase A)
@register(name="delta", layer="greek", inputs=["delta"], params={},
          description="Self-computed option delta (pass-through; approximate).")
def delta_passthrough(df):
    return df["delta"]


@register(name="gamma", layer="greek", inputs=["gamma"], params={},
          description="Self-computed option gamma (pass-through; approximate).")
def gamma_passthrough(df):
    return df["gamma"]


@register(name="theta_day", layer="greek", inputs=["theta_day"], params={},
          description="Self-computed theta per calendar day (approximate).")
def theta_passthrough(df):
    return df["theta_day"]


@register(name="moneyness", layer="pricing", inputs=["under_close", "strike"],
          params={},
          description="log(S/K): standardized distance to strike.")
def moneyness(df):
    return np.log(df["under_close"] / df["strike"])


@register(name="dte", layer="pricing", inputs=["dte_days"], params={},
          description="Calendar days to expiry (pass-through).")
def dte_passthrough(df):
    return df["dte_days"].astype(float)


# ----------------------------------------------------------------- IV (phase B for belief)
@register(name="iv_level", layer="iv", inputs=["iv"], params={}, phase="B",
          description="Self-computed IV level. Phase-B-only for belief (noisy on indicative).")
def iv_level(df):
    return df["iv"]


@register(name="iv_change", layer="iv", inputs=["iv"],
          params={"window": 1}, param_ranges={"window": [1, 5, 15]}, phase="B",
          description="Change in IV over `window` bars. Phase-B-only for belief.")
def iv_change(df, window=1):
    return df["iv"].diff(window)


@register(name="iv_rank", layer="iv", inputs=["iv"],
          params={"window": 60}, param_ranges={"window": [30, 60, 120]}, phase="B",
          description="Rolling percentile rank of IV in [0,1] over `window`. "
                      "Phase-B-only; errors-in-variables fabricates mean-reversion.")
def iv_rank(df, window=60):
    return df["iv"].rolling(window, min_periods=window).apply(
        lambda w: (w.iloc[-1] >= w).mean(), raw=False)


# ----------------------------------------------------------------- structure (phase A)
# These read the underlying bar's CLOCK and intraday price path, not textbook
# oscillators. They target intraday-options-specific structural effects.

@register(name="minutes_since_open", layer="structure", inputs=["ts"], params={},
          description="Minutes since the 13:30 UTC (09:30 ET) cash open, per bar.")
def minutes_since_open(df):
    t = pd.to_datetime(df["ts"]).dt.tz_convert("America/New_York")
    mins = (t.dt.hour - 9) * 60 + (t.dt.minute - 30)
    return mins.clip(lower=0).astype(float)


@register(name="time_of_day_bucket", layer="structure", inputs=["ts"], params={},
          description="0=open hr, 1=midday, 2=power hour (last hr to 16:00 ET).")
def time_of_day_bucket(df):
    t = pd.to_datetime(df["ts"]).dt.tz_convert("America/New_York")
    mins = (t.dt.hour - 9) * 60 + (t.dt.minute - 30)
    return pd.cut(mins, bins=[-1, 60, 330, 10_000], labels=[0, 1, 2]).astype(float)


@register(name="opening_range_pos", layer="structure",
          inputs=["ts", "under_close"], params={"or_minutes": 30},
          param_ranges={"or_minutes": [15, 30, 60]},
          description="Position of price vs the day's opening range "
                      "(>1 = broke above OR high, <0 = below OR low).")
def opening_range_pos(df, or_minutes=30):
    t = pd.to_datetime(df["ts"]).dt.tz_convert("America/New_York")
    day = t.dt.date
    mins = (t.dt.hour - 9) * 60 + (t.dt.minute - 30)
    in_or = (mins >= 0) & (mins < or_minutes)
    p = df["under_close"]
    # opening-range high/low per day, using ONLY the first `or_minutes` (causal:
    # once the OR window closes the levels are fixed and known for the rest of day)
    or_hi = p.where(in_or).groupby(day).cummax().groupby(day).ffill()
    or_lo = p.where(in_or).groupby(day).cummin().groupby(day).ffill()
    rng = (or_hi - or_lo).replace(0, np.nan)
    return (p - or_lo) / rng


@register(name="overnight_gap", layer="structure",
          inputs=["ts", "under_close"], params={},
          description="Fractional gap of today's first bar vs prior day's last "
                      "close; constant within the day (a daily structural state).")
def overnight_gap(df):
    t = pd.to_datetime(df["ts"]).dt.tz_convert("America/New_York")
    day = t.dt.date
    first = df.groupby(day)["under_close"].transform("first")
    prev_last = df.groupby(day)["under_close"].transform("last").groupby(day).first()
    # map each day to the PRIOR day's last close (causal: known at today's open)
    daily_last = df.groupby(day)["under_close"].last()
    prior = daily_last.shift(1)
    gap = first / pd.Series(day.values, index=df.index).map(prior) - 1.0
    return gap
