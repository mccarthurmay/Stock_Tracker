"""Long-horizon cross-sectional equity backtest (factor strategies).

This is the bridge that lets the SAME noise apparatus you liked for intraday
options — Deflated Sharpe, walk-forward, the frozen objective — judge a
long-term, monthly-rebalanced stock-picking strategy (e.g. the Fama-French
quality-value composite the screener in backend/analysis.py is built around).

Design (see the discussion that produced this):
  * A FACTOR SOURCE maps (ticker, date) -> a cross-sectional score, using only
    information knowable at `date`. Two are provided:
      - `momentum_factor`  : 12-1 month total return. Computable lookahead-free
        from prices ALONE, so it works on the data we already have -> used for
        the smoke test that proves the plumbing.
      - `ff_composite_factor`: z(BM) + z(OP) - z(INV) from SEC fundamentals.
        This is the REAL target strategy, but it is gated behind two hard
        point-in-time requirements (see the TODOs) and deep history we do not
        have on the free tier, so it is scaffolded, not run.
  * Each rebalance date: rank the universe by score, long the top quantile
    (optionally short the bottom), equal-weight, hold to the next rebalance.
  * Output is a PERIOD-RETURN series -> fed straight into metrics/stats/
    validation, exactly like a trade log.

NON-NEGOTIABLE point-in-time rules (long-horizon failure modes are WORSE than
intraday — see ROADMAP §6, §12):
  1. Survivorship: the universe at date t must include names that later
     delisted. A current index membership file (e.g. smp500.txt) is biased.
  2. Filing lag: accounting data is only knowable at its `filed` date, not the
     fiscal period end. fundamentals.py tracks `filed`; it MUST be enforced.
  3. Total return: use split+dividend-adjusted prices (client adjustment='all').
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


# ----------------------------------------------------------------- prices
def monthly_total_return_panel(client, tickers, start, end, feed="sip",
                               progress_every: int = 200) -> pd.DataFrame:
    """Wide DataFrame of month-end split+div-adjusted closes (index=month-end,
    columns=tickers). One API pull per ticker; total-return proxy via 'all'.
    Uses the SIP feed by default — free-tier historical SIP goes back to 2016
    (IEX only ~mid-2020), the multi-regime depth a factor study needs."""
    series = {}
    s = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    e = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
    for i, t in enumerate(tickers, 1):
        try:
            df = client.stock_bars(t, s, e, "1Day", adjustment="all", feed=feed)
        except Exception:
            df = None
        if df is not None and not df.empty:
            px = df.set_index(pd.to_datetime(df["ts"]))["close"].sort_index()
            series[t] = px.resample("ME").last()   # month-end last observation
        if progress_every and i % progress_every == 0:
            print(f"  prices {i}/{len(tickers)} pulled ({len(series)} with data)", flush=True)
    if not series:
        return pd.DataFrame()
    return pd.DataFrame(series).sort_index()


# ----------------------------------------------------------------- factor sources
def momentum_factor(prices: pd.DataFrame, date, lookback=12, skip=1) -> pd.Series:
    """12-1 momentum: total return from t-lookback to t-skip (skip the most
    recent month to avoid short-term reversal). Uses ONLY prices up to `date`,
    so it is point-in-time correct by construction."""
    idx = prices.index
    pos = idx.get_indexer([date], method="ffill")[0]
    if pos - lookback < 0:
        return pd.Series(dtype=float)
    p_now = prices.iloc[pos - skip]
    p_then = prices.iloc[pos - lookback]
    return (p_now / p_then - 1.0).dropna()


def ff_composite_factor_fn(panel: pd.DataFrame):
    """Build a factor_fn(prices, date) -> score from a PIT factor panel.

    `panel` is the filing-lagged output of factors_pit.build_factor_panel
    (columns date, ticker, BM, OP, INV). At each date we cross-sectionally
    z-score the names available THEN and return:  z(BM) + z(OP) - z(INV)
    (cheaper + more profitable + more conservative). Filing-lag is already
    enforced upstream; survivorship is NOT (universe must be PIT — see TODO).
    """
    by_date = {d: g for d, g in panel.groupby("date")} if not panel.empty else {}

    def factor_fn(prices, date, **_):
        g = by_date.get(date)
        if g is None or len(g) < 3:
            return pd.Series(dtype=float)
        z = lambda col: (g[col] - g[col].mean()) / g[col].std(ddof=0)
        score = (z("BM") + z("OP") - z("INV"))
        return pd.Series(score.values, index=g["ticker"].values).dropna()

    return factor_fn


# ----------------------------------------------------------------- backtest
@dataclass
class EquityConfig:
    quantile: float = 0.2        # top/bottom fraction to trade
    long_short: bool = False     # True -> top minus bottom (market-neutral-ish)
    cost_bps: float = 5.0        # per-rebalance turnover cost, basis points
    min_names: int = 10          # need at least this many scored names to trade


def _turnover_cost(prev_w: dict, new_w: dict, cost_bps: float) -> float:
    names = set(prev_w) | set(new_w)
    turnover = sum(abs(new_w.get(n, 0.0) - prev_w.get(n, 0.0)) for n in names)
    return (cost_bps / 1e4) * turnover


def run_equity_backtest(prices: pd.DataFrame, factor_fn, cfg: EquityConfig | None = None,
                        factor_kwargs: dict | None = None) -> pd.DataFrame:
    """Monthly rebalance loop -> period-return series.

    At each month-end t: score names with factor_fn(prices, t), rank, form the
    top-quantile long book (and bottom-quantile short if long_short), then the
    realized return for the period is the NEXT month's return of that book
    (signal at t, return earned t -> t+1: no lookahead).
    """
    cfg = cfg or EquityConfig()
    fkw = factor_kwargs or {}
    idx = prices.index
    rets = prices.pct_change(fill_method=None)   # month-over-month total return
    prev_w: dict[str, float] = {}
    out = []

    for i in range(len(idx) - 1):        # need t+1 to realize the return
        t, t1 = idx[i], idx[i + 1]
        score = factor_fn(prices, t, **fkw)
        score = score.dropna()
        if len(score) < cfg.min_names:
            continue
        n = max(1, int(len(score) * cfg.quantile))
        longs = score.nlargest(n).index
        fwd = rets.loc[t1]
        long_ret = fwd[longs].mean()
        new_w = {nm: 1.0 / len(longs) for nm in longs}
        if cfg.long_short:
            shorts = score.nsmallest(n).index
            long_ret = long_ret - fwd[shorts].mean()
            for nm in shorts:
                new_w[nm] = new_w.get(nm, 0.0) - 1.0 / len(shorts)
        gross = float(long_ret)
        cost = _turnover_cost(prev_w, new_w, cfg.cost_bps)
        prev_w = new_w
        out.append({"date": t1, "gross_ret": gross, "cost": cost,
                    "ret": gross - cost, "n_long": len(longs)})
    return pd.DataFrame(out)


# ----------------------------------------------------------------- evaluation
# Objective thresholds RE-FROZEN for a monthly horizon (the intraday §1 values
# don't transfer: a monthly strategy has tens of returns, not hundreds, and a
# 20% intra-test drawdown is normal for equity). Decide up front; don't tune.
MONTHLY_MIN_PERIODS = 24         # >= 2 years of monthly returns to say anything
MONTHLY_MAX_DRAWDOWN = 0.35      # equity drawdowns run deeper than option books
PERIODS_PER_YEAR = 12


def evaluate(period_returns: pd.DataFrame, n_trials: int) -> dict:
    """Judge a period-return series with the SAME apparatus as the options work:
    Sharpe + Deflated Sharpe (deflated by n_trials distinct configs), plus the
    monthly-re-frozen objective. Annualizes Sharpe only for display."""
    from . import stats
    r = period_returns["ret"].to_numpy(float)
    r = r[np.isfinite(r)]
    n = r.size
    sr_m, skew, exk = stats.sharpe_stats(r)          # per-month Sharpe
    dsr = stats.deflated_sharpe_ratio(sr_m, r, n_trials) if n >= 2 else {"dsr": 0.0, "benchmark_sr": 0.0}

    eq = (1.0 + r).cumprod()
    peak = np.maximum.accumulate(eq)
    max_dd = float(np.max((peak - eq) / peak)) if n else 0.0
    ann_ret = float((1.0 + r).prod() ** (PERIODS_PER_YEAR / n) - 1.0) if n else 0.0

    reasons, passed = [], True
    if n >= MONTHLY_MIN_PERIODS:
        reasons.append(f"PASS n_periods {n} >= {MONTHLY_MIN_PERIODS}")
    else:
        passed = False; reasons.append(f"FAIL n_periods {n} < {MONTHLY_MIN_PERIODS}")
    mean = float(r.mean()) if n else 0.0
    if mean > 0:
        reasons.append(f"PASS mean monthly return {mean:.4f} > 0")
    else:
        passed = False; reasons.append(f"FAIL mean monthly return {mean:.4f} <= 0")
    if max_dd <= MONTHLY_MAX_DRAWDOWN:
        reasons.append(f"PASS max_drawdown {max_dd:.1%} <= {MONTHLY_MAX_DRAWDOWN:.0%}")
    else:
        passed = False; reasons.append(f"FAIL max_drawdown {max_dd:.1%} > {MONTHLY_MAX_DRAWDOWN:.0%}")
    dsr_val = dsr["dsr"] if dsr["dsr"] is not None and np.isfinite(dsr["dsr"]) else 0.0
    survives = bool(passed and dsr_val > 0.95)

    return {"n_periods": n, "sharpe_monthly": round(sr_m, 3),
            "sharpe_annual": round(sr_m * np.sqrt(PERIODS_PER_YEAR), 3),
            "ann_return": round(ann_ret, 4), "max_drawdown": round(max_dd, 4),
            "skew": round(skew, 3), "dsr": round(dsr_val, 4),
            "dsr_benchmark_sr": round(dsr["benchmark_sr"], 4), "n_trials": n_trials,
            "objective_pass": passed, "reasons": reasons, "survives": survives}
