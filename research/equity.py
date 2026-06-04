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


def daily_price_panel(client, tickers, start, end, feed="sip",
                      progress_every: int = 200) -> pd.DataFrame:
    """Wide DAILY total-return-adjusted close panel (index=daily ts, cols=tickers).

    The CI mean-reversion signal (from backend/analysis.py) needs a ~90-DAY
    rolling mean/std, so monthly bars aren't enough — this keeps daily history.
    Resample to month-end with `month_end()` to get the return panel."""
    series = {}
    s = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    e = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
    for i, t in enumerate(tickers, 1):
        try:
            df = client.stock_bars(t, s, e, "1Day", adjustment="all", feed=feed)
        except Exception:
            df = None
        if df is not None and not df.empty:
            series[t] = df.set_index(pd.to_datetime(df["ts"]))["close"].sort_index()
        if progress_every and i % progress_every == 0:
            print(f"  daily prices {i}/{len(tickers)} ({len(series)} with data)", flush=True)
    return pd.DataFrame(series).sort_index() if series else pd.DataFrame()


def month_end(daily: pd.DataFrame) -> pd.DataFrame:
    """Month-end last observation from a daily panel (for forward returns)."""
    return daily.resample("ME").last()


def ci_factor_fn(daily: pd.DataFrame, lookback_days=90, n_std=2.0):
    """The screener's CI signal as a cross-sectional factor (point-in-time).

    Mirrors backend/analysis.py: lower_bound = mean − n_std·std over the last
    `lookback_days`; a name is a "buy" when its price sits below that band, and
    *more below* = stronger. The cross-sectional score is −z = −(price−mean)/std,
    so the top quantile = the names furthest below their own CI band (the biggest
    dips). Uses only daily data ≤ `date`, so no lookahead. (n_std is kept for a
    thresholded variant; the rank form already favours the most-below names.)"""
    def factor_fn(prices, date, **_):
        win = daily.loc[:date]
        if win.empty:
            return pd.Series(dtype=float)
        win = win.tail(lookback_days)
        if len(win) < int(lookback_days * 0.5):
            return pd.Series(dtype=float)
        mean = win.mean()
        std = win.std().replace(0, np.nan)
        price = win.iloc[-1]
        z = (price - mean) / std
        return (-z).dropna()          # higher = further below band = stronger buy
    return factor_fn


def ci_ma_factor_fn(daily: pd.DataFrame, ci_lookback=90, ma_window=200):
    """Avenue 2: buy the dip ONLY in an uptrend. Among names whose price is above
    their `ma_window`-day moving average (MA bullish), rank by how far below the
    CI band they are (−z). Non-uptrend names are excluded. Point-in-time."""
    def factor_fn(prices, date, **_):
        win = daily.loc[:date]
        if win.empty:
            return pd.Series(dtype=float)
        w_ci = win.tail(ci_lookback)
        if len(w_ci) < int(ci_lookback * 0.5):
            return pd.Series(dtype=float)
        mean = w_ci.mean()
        std = w_ci.std().replace(0, np.nan)
        price = win.iloc[-1]
        z = (price - mean) / std
        ma = win.tail(ma_window).mean()
        score = (-z).where(price > ma)   # eligible only if in uptrend
        return score.dropna()
    return factor_fn


def rsi_frame(px: pd.DataFrame, window=14) -> pd.DataFrame:
    """RSI matching backend/analysis.py exactly: 14-period SIMPLE rolling mean
    of up/down moves (not Wilder's EMA): 100*mean_up/(mean_up+mean_down)."""
    change = px.diff()
    up = change.clip(lower=0)
    down = (-change.clip(upper=0))
    mean_up = up.rolling(window).mean()
    mean_down = down.rolling(window).mean()
    denom = (mean_up + mean_down).replace(0, np.nan)
    return 100 * mean_up / denom


def undervalued_mask_from_panel(daily: pd.DataFrame, factor_panel: pd.DataFrame,
                                quantile=0.3) -> pd.DataFrame:
    """Daily boolean 'is this name fundamentally undervalued right now?' mask.

    `factor_panel` is the filing-lagged MONTHLY FF panel (date,ticker,BM,OP,INV)
    from factors_pit.build_factor_panel. At each panel date we cross-sectionally
    score z(BM)+z(OP)-z(INV) and flag the top `quantile` as undervalued, then
    FORWARD-FILL that monthly flag onto daily dates (point-in-time: a name's
    undervalued status only changes when the monthly screen refreshes — using
    only filings knowable then). Returns a daily bool frame aligned to `daily`."""
    flags = {}
    for d, g in factor_panel.groupby("date"):
        if len(g) < 3:
            continue
        z = lambda c: (g[c] - g[c].mean()) / g[c].std(ddof=0)
        score = (z("BM") + z("OP") - z("INV"))
        n = max(1, int(len(score) * quantile))
        top = set(g.iloc[score.values.argsort()[::-1][:n]]["ticker"])
        flags[d] = {t: (t in top) for t in g["ticker"]}
    if not flags:
        return pd.DataFrame(False, index=daily.index, columns=daily.columns)
    monthly = pd.DataFrame(flags).T.reindex(columns=daily.columns).astype("boolean")
    monthly.index = pd.to_datetime(monthly.index)
    # reindex onto daily dates, forward-fill the monthly flag (PIT carry), and
    # treat pre-first-screen dates as not-undervalued. Nullable boolean avoids
    # the object-dtype downcast warning.
    daily_mask = monthly.reindex(daily.index, method="ffill")
    return daily_mask.fillna(False).astype(bool)


def ci_value_timing_backtest(daily: pd.DataFrame, undervalued: pd.DataFrame,
                             ci_lookback=90, buy_sigma=2.0, sell_sigma=1.0,
                             cost_bps=5.0, hold_forever=False):
    """The user's combined strategy, daily event-driven, point-in-time.

      BUY  when price < mean - buy_sigma*std  AND  fundamentally undervalued
           (top-quantile FF value score; the `undervalued` daily mask).
      SELL when price recovers to mean - sell_sigma*std (partial reversion;
           e.g. exit at -1sigma after buying at -2sigma -> capture the bounce).
      Re-buy is allowed whenever both buy conditions re-trigger.

      hold_forever=True -> NO SELL: once a name is bought on the signal it is
      held to the end. This isolates the ENTRY signal's value (does buying cheap
      dips and holding beat always-in?) without the sell rule sacrificing beta.

    The value mask is the value-trap FILTER the prior pure-CI tests lacked:
    only buy dips in cheap names, not every falling knife. mean/std are rolling
    (causal); a close-t decision acts on t+1 (shift) -> no lookahead. Returns the
    daily strat return + buy-and-hold benchmark on the same names."""
    px = daily.sort_index()
    rets = px.pct_change(fill_method=None)
    mean = px.rolling(ci_lookback, min_periods=int(ci_lookback*0.6)).mean()
    std = px.rolling(ci_lookback, min_periods=int(ci_lookback*0.6)).std()
    uv = undervalued.reindex_like(px).fillna(False)

    buy = (px < (mean - buy_sigma * std)) & uv          # dip AND undervalued

    sig = pd.DataFrame(np.nan, index=px.index, columns=px.columns)
    if hold_forever:
        # buy-and-hold-the-signal: latch to 1 on first buy, never reset to 0
        sig = sig.mask(buy, 1.0)
    else:
        sell = px > (mean - sell_sigma * std)            # recovered to -1sigma
        sig = sig.mask(buy, 1.0).mask(sell, 0.0)
    held_eff = sig.ffill().fillna(0.0).shift(1).fillna(0.0)

    held_mask = held_eff > 0
    n_held = held_mask.sum(axis=1)
    strat_ret = (rets.where(held_mask)).mean(axis=1).fillna(0.0)
    flips = held_eff.diff().abs().sum(axis=1)
    cost = (cost_bps / 1e4) * (flips / n_held.replace(0, np.nan)).fillna(0.0)
    strat_ret = strat_ret - cost
    bh_ret = rets.mean(axis=1).fillna(0.0)

    out = pd.DataFrame({"date": px.index, "ret": strat_ret.values,
                        "bh_ret": bh_ret.values, "n_held": n_held.values})
    valid_from = mean.dropna(how="all").index.min()
    return out[out["date"] >= valid_from].reset_index(drop=True)


# ---------------------------------------------------------------- drawdown overlays
# Each returns a daily exposure series in [0,1] (1 = fully invested), causal:
# the value at t uses only data <= t. The caller shifts t->t+1 for the fill.
# Combine overlays by MULTIPLYING their exposures (stay fully in only if all agree).

def ma_filter_exposure(px: pd.Series, window=200) -> pd.Series:
    """Faber trend filter: exposure 1 when price > its `window`-day MA, else 0.
    The single most-studied timing rule. Binary on/off."""
    ma = px.rolling(window, min_periods=int(window * 0.6)).mean()
    return (px > ma).astype(float)


def vol_target_exposure(px: pd.Series, target_vol=0.15, window=20,
                        cap=1.0) -> pd.Series:
    """Volatility targeting: exposure = target_vol / realized_vol, capped at `cap`.
    Realized vol = annualized rolling std of daily log returns. Vol spikes during
    crashes -> exposure auto-shrinks. Continuous (not binary); the institutional
    standard risk overlay. Uses YESTERDAY's vol (shifted) so it's causal."""
    r = np.log(px / px.shift(1))
    rv = r.rolling(window, min_periods=int(window * 0.6)).std() * np.sqrt(252)
    rv = rv.shift(1)                       # only knowable at the prior close
    exp = (target_vol / rv).clip(upper=cap)
    return exp.fillna(cap).clip(0.0, cap)


def ts_momentum_exposure(px: pd.Series, lookback=252) -> pd.Series:
    """Time-series momentum (dual-momentum's defensive half): exposure 1 if the
    trailing `lookback`-day total return is positive, else 0. Binary."""
    trailing = px / px.shift(lookback) - 1.0
    return (trailing > 0).astype(float)


def overlay_backtest(px: pd.Series, exposure: pd.Series, cost_bps=5.0):
    """Backtest a single price series under a given daily exposure path (0..1).
    Decision at close t acts on t+1 (shift, no lookahead). Returns strat + B&H."""
    px = px.sort_index()
    ret = px.pct_change(fill_method=None).fillna(0.0)
    exp_eff = exposure.reindex(px.index).shift(1).fillna(1.0).clip(0.0, 1.0)
    strat = exp_eff * ret - (cost_bps / 1e4) * exp_eff.diff().abs().fillna(0.0)
    out = pd.DataFrame({"date": px.index, "ret": strat.values, "bh_ret": ret.values,
                        "n_held": exp_eff.values})
    # drop the longest warmup so all overlays compare on the same window
    return out.iloc[252:].reset_index(drop=True)


def index_buysell_backtest(px: pd.Series, buy_rule="ci_dip", sell_rules=("ci_recover",),
                           ci_lookback=90, buy_sigma=2.0, sell_sigma=1.0,
                           ma_window=50, rsi_sell=70.0, rsi_window=14, cost_bps=5.0):
    """Single-asset ACTIVE buy/sell timing (binary held/flat) on one index.

    BUY (enter when flat):
      'ci_dip'  : price < mean - buy_sigma*std  (the screener's CI dip)
      'always'  : enter the moment you're flat (so the only timing is the SELL --
                  this isolates how much the CI-dip ENTRY costs in missed upside)
    SELL (exit when held) -- fires if ANY listed rule triggers:
      'ci_recover' : price > mean - sell_sigma*std  (partial reversion exit)
      'ci_upper'   : price > mean + sell_sigma*std  (overextended)
      'ma_cross'   : price < its `ma_window`-day MA (trend break)
      'vol_spike'  : realized vol (20d, annualized) jumps above its 1y median*1.5
      'rsi'        : 14d RSI >= rsi_sell
    Causal (rolling), decision at close t acts on t+1. vs buy-and-hold of itself."""
    px = px.sort_index()
    ret = px.pct_change(fill_method=None).fillna(0.0)
    mean = px.rolling(ci_lookback, min_periods=int(ci_lookback*0.6)).mean()
    std = px.rolling(ci_lookback, min_periods=int(ci_lookback*0.6)).std()
    ma = px.rolling(ma_window, min_periods=int(ma_window*0.6)).mean()
    rsi = rsi_frame(px.to_frame("p"), rsi_window)["p"]
    logr = np.log(px / px.shift(1))
    rv = logr.rolling(20, min_periods=12).std() * np.sqrt(252)
    rv_med = rv.rolling(252, min_periods=120).median()

    buy = (px < mean - buy_sigma*std) if buy_rule == "ci_dip" else pd.Series(True, index=px.index)
    sell = pd.Series(False, index=px.index)
    if "ci_recover" in sell_rules:
        sell = sell | (px > mean - sell_sigma*std)
    if "ci_upper" in sell_rules:
        sell = sell | (px > mean + sell_sigma*std)
    if "ma_cross" in sell_rules:
        sell = sell | (px < ma)
    if "vol_spike" in sell_rules:
        sell = sell | (rv > rv_med * 1.5)
    if "rsi" in sell_rules:
        sell = sell | (rsi >= rsi_sell)

    # binary held-state: 1 on buy, 0 on sell, ffill; act next bar
    sig = pd.Series(np.nan, index=px.index)
    sig = sig.mask(buy.fillna(False), 1.0).mask(sell.fillna(False), 0.0)
    held = sig.ffill().fillna(0.0).shift(1).fillna(0.0)

    strat = held * ret - (cost_bps/1e4) * held.diff().abs().fillna(0.0)
    out = pd.DataFrame({"date": px.index, "ret": strat.values, "bh_ret": ret.values,
                        "n_held": held.values})
    return out.iloc[ci_lookback:].reset_index(drop=True)


def crash_exposure_series(px: pd.Series, ci_lookback=90, crash_sigma=2.0,
                          n_increments=5, decline_mode="cliff_sell",
                          reentry_mode="avg_down") -> pd.Series:
    """The CI crash-dodge exposure path as a Series (wraps _crash_exposure_path)."""
    arr = _crash_exposure_path(px.sort_index(), ci_lookback, crash_sigma,
                               n_increments, decline_mode, reentry_mode)
    return pd.Series(arr, index=px.sort_index().index)


def _crash_exposure_path(px: pd.Series, ci_lookback, crash_sigma, n_increments,
                         decline_mode, reentry_mode) -> np.ndarray:
    """Daily exposure (0..1) for ONE price series under the crash state machine.

      decline_mode: 'cliff_sell' (dump to 0 on trigger) | 'ramp_sell' (sell a
                    step per new low -- trend: cut into weakness).
      reentry_mode: 'avg_down' (add a step per new low -- mean-reversion) |
                    'ramp_up' (add a step as it rises off the low -- trend) |
                    'cliff_up' (snap back only once recovered above the CI mid).
    Recovery above the CI mid (mean) resets to fully invested. Causal: the value
    at position i is the exposure that was chosen by the prior bar (the caller
    shifts for the t->t+1 fill)."""
    mean = px.rolling(ci_lookback, min_periods=int(ci_lookback*0.6)).mean()
    std = px.rolling(ci_lookback, min_periods=int(ci_lookback*0.6)).std()
    lower = mean - crash_sigma * std
    exposure = np.ones(len(px))
    state, exp = "normal", 1.0
    crash_low, prev_p = np.inf, np.inf
    step = 1.0 / max(1, n_increments)
    pv, mv, lv = px.to_numpy(), mean.to_numpy(), lower.to_numpy()

    for i in range(len(px)):
        p, m, lo = pv[i], mv[i], lv[i]
        exposure[i] = exp
        if not np.isfinite(m):
            prev_p = p
            continue
        if state == "normal":
            if np.isfinite(lo) and p < lo:
                state, crash_low = "crash", p
                exp = 0.0 if decline_mode == "cliff_sell" else max(0.0, exp - step)
        else:
            if p < crash_low:
                crash_low = p
                if decline_mode == "ramp_sell":
                    exp = max(0.0, exp - step)
                if reentry_mode == "avg_down":
                    exp = min(1.0, exp + step)
            elif p > prev_p and reentry_mode == "ramp_up":
                exp = min(1.0, exp + step)
            if p > m:
                exp, state, crash_low = 1.0, "normal", np.inf
        prev_p = p
    return exposure


def volcrash_exposure_path(px: pd.Series, vol_window=20, vol_med_window=252,
                           vol_mult=1.5, n_increments=5, decline_mode="cliff_sell",
                           reentry_mode="avg_down") -> np.ndarray:
    """Combined BEST pieces: SELL trigger = volatility spike (the winning exit),
    BUY-back = STAGGERED average-down on new lows (the winning re-entry).

    State machine (causal; caller shifts t->t+1):
      NORMAL (exposure 1): when realized vol spikes above its rolling median *
        vol_mult -> a 'risk-off' event -> de-risk (cliff_sell: dump to 0;
        ramp_sell: shed a step per new low).
      RISK-OFF: average back IN incrementally as price makes NEW LOWS (avg_down,
        the staggered buy), OR add as it rises off the low (ramp_up). RESET to
        fully invested once VOL CALMS back below the spike threshold (the
        vol-trigger analog of 'recovered above the CI mid')."""
    px = px.sort_index()
    logr = np.log(px / px.shift(1))
    rv = logr.rolling(vol_window, min_periods=int(vol_window*0.6)).std() * np.sqrt(252)
    rv_med = rv.rolling(vol_med_window, min_periods=120).median()
    thresh = rv_med * vol_mult

    exposure = np.ones(len(px))
    state, exp = "normal", 1.0
    low_since, prev_p = np.inf, np.inf
    step = 1.0 / max(1, n_increments)
    pv, rvv, tv = px.to_numpy(), rv.to_numpy(), thresh.to_numpy()

    for i in range(len(px)):
        p, v, th = pv[i], rvv[i], tv[i]
        exposure[i] = exp
        if not np.isfinite(th):
            prev_p = p
            continue
        spiking = np.isfinite(v) and v > th
        if state == "normal":
            if spiking:                                  # vol-spike SELL trigger
                state, low_since = "riskoff", p
                exp = 0.0 if decline_mode == "cliff_sell" else max(0.0, exp - step)
        else:
            if p < low_since:                            # new low -> stagger in
                low_since = p
                if decline_mode == "ramp_sell":
                    exp = max(0.0, exp - step)
                if reentry_mode == "avg_down":
                    exp = min(1.0, exp + step)
            elif p > prev_p and reentry_mode == "ramp_up":
                exp = min(1.0, exp + step)
            if not spiking:                              # vol calmed -> reset
                exp, state, low_since = 1.0, "normal", np.inf
        prev_p = p
    return exposure


def staggered_overlay_exposure(px: pd.Series, arm: pd.Series, n_increments=5,
                               decline_mode="cliff_sell", reentry_mode="avg_down") -> np.ndarray:
    """Generic staggered crash-dodge driven by an explicit boolean ARM series.

    This separates WHAT detects the drawdown (the `arm` series, True = risk-off)
    from HOW it's traded (always the same staggered avg-down buy-back). Lets every
    sell trigger -- CI band, vol spike, MA cross, trailing drawdown, breadth,
    cross-asset, Donchian -- be compared on identical buy mechanics.

      NORMAL (exp 1): when arm flips True -> de-risk (cliff_sell: dump to 0;
        ramp_sell: shed a step per new low since arming).
      RISK-OFF: average back IN a step per NEW LOW (avg_down) or as price rises off
        the low (ramp_up). RESET to fully invested when arm flips back False.
    Causal: value at i is set by the prior bar; caller shifts t->t+1."""
    px = px.sort_index()
    arm = arm.reindex(px.index).fillna(False).to_numpy().astype(bool)
    pv = px.to_numpy()
    exposure = np.ones(len(px))
    state, exp = "normal", 1.0
    low_since, prev_p = np.inf, np.inf
    step = 1.0 / max(1, n_increments)
    for i in range(len(px)):
        p = pv[i]
        exposure[i] = exp
        if state == "normal":
            if arm[i]:
                state, low_since = "riskoff", p
                exp = 0.0 if decline_mode == "cliff_sell" else max(0.0, exp - step)
        else:
            if p < low_since:
                low_since = p
                if decline_mode == "ramp_sell":
                    exp = max(0.0, exp - step)
                if reentry_mode == "avg_down":
                    exp = min(1.0, exp + step)
            elif p > prev_p and reentry_mode == "ramp_up":
                exp = min(1.0, exp + step)
            if not arm[i]:
                exp, state, low_since = 1.0, "normal", np.inf
        prev_p = p
    return exposure


def breadth_series(panel: pd.DataFrame, ma_window=50) -> pd.Series:
    """Market breadth = fraction of names trading above their `ma_window`-day MA,
    per day. A LEADING risk signal: internals weaken before the index does."""
    ma = panel.rolling(ma_window, min_periods=int(ma_window*0.6)).mean()
    above = (panel > ma)
    return above.sum(axis=1) / panel.notna().sum(axis=1).replace(0, np.nan)


def spy_crash_overlay_backtest(spy: pd.Series, ci_lookback=90, crash_sigma=2.0,
                               n_increments=5, cost_bps=5.0,
                               decline_mode="cliff_sell", reentry_mode="avg_down"):
    """Single-asset market-timing overlay on SPY (one price series). See
    _crash_exposure_path for the two-phase state machine. Exposure (0..1)
    multiplies SPY's next-day return; changes pay turnover cost."""
    px = spy.sort_index()
    ret = px.pct_change(fill_method=None).fillna(0.0)
    idx = px.index
    exposure = _crash_exposure_path(px, ci_lookback, crash_sigma, n_increments,
                                    decline_mode, reentry_mode)

    # decision at close t affects t+1 (no lookahead)
    exp_eff = pd.Series(exposure, index=idx).shift(1).fillna(1.0)
    strat = exp_eff * ret
    turnover = exp_eff.diff().abs().fillna(0.0)
    strat = strat - (cost_bps / 1e4) * turnover

    out = pd.DataFrame({"date": idx, "ret": strat.values, "bh_ret": ret.values,
                        "n_held": exp_eff.values})
    warmup = int(ci_lookback * 0.6)
    return out.iloc[warmup:].reset_index(drop=True)


def per_stock_crash_backtest(daily: pd.DataFrame, ci_lookback=90, crash_sigma=2.0,
                             n_increments=5, cost_bps=5.0,
                             decline_mode="cliff_sell", reentry_mode="avg_down"):
    """Per-stock crash timing: EACH name runs its OWN crash-dodge on its OWN CI
    band (sell that name when IT crashes, re-buy it on its own recovery). The
    portfolio return each day is the equal-weight mean over names that are
    currently HELD (exposure>0), weighted by each name's own 0..1 exposure.

    Differs from spy_crash_overlay_backtest (one index-level dial) and from
    ci_value (which also picks on value): here every stock is timed individually.
    Benchmarked vs equal-weight buy-and-hold of the same names. PIT: each name's
    exposure decision at close t acts on t+1 (shift)."""
    px = daily.sort_index()
    rets = px.pct_change(fill_method=None)
    # per-name exposure path, then shift each column by 1 (t -> t+1, no lookahead)
    exp = pd.DataFrame(
        {c: _crash_exposure_path(px[c], ci_lookback, crash_sigma, n_increments,
                                 decline_mode, reentry_mode) for c in px.columns},
        index=px.index)
    exp_eff = exp.shift(1)
    # a name only contributes once it has price history (avoid warmup garbage)
    have = px.notna()
    exp_eff = exp_eff.where(have, np.nan)

    held = exp_eff > 0
    n_held = held.sum(axis=1)
    # exposure-weighted equal-weight return across held names
    contrib = (exp_eff * rets).where(held)
    strat_ret = contrib.mean(axis=1).fillna(0.0)
    # turnover cost: avg absolute exposure change across names currently in play
    turnover = exp_eff.diff().abs().mean(axis=1).fillna(0.0)
    strat_ret = strat_ret - (cost_bps / 1e4) * turnover
    bh_ret = rets.mean(axis=1).fillna(0.0)   # equal-weight buy-and-hold of the same names

    out = pd.DataFrame({"date": px.index, "ret": strat_ret.values,
                        "bh_ret": bh_ret.values, "n_held": n_held.values})
    warmup = int(ci_lookback * 0.6)
    return out.iloc[warmup:].reset_index(drop=True)


def ci_timing_backtest(daily: pd.DataFrame, ci_lookback=90, buy_sigma=2.0,
                       sell_sigma=1.0, ma_window=100, rsi_sell=70.0, rsi_window=14,
                       sell_triggers=("sigma", "ma"), cost_bps=5.0):
    """Daily event-driven CI timing with COMPOSABLE sell triggers (point-in-time).

    ENTER (long) when price < mean - buy_sigma*std (the screener's CI buy).
    EXIT when ANY enabled trigger fires (`sell_triggers` is a subset of):
      'sigma' : price > mean + sell_sigma*std        (overextended / take profit)
      'ma'    : the moving average is FALLING          (today's MA < prior MA)
      'rsi'   : RSI >= rsi_sell                         (analysis.py 14d RSI)
    All inputs are rolling/causal; a close-t signal acts on t+1 (shift) -> no
    lookahead. Returns daily strat return (equal-weight over names held) + a
    buy-and-hold benchmark on the same names.
    """
    px = daily.sort_index()
    rets = px.pct_change(fill_method=None)
    mean = px.rolling(ci_lookback, min_periods=int(ci_lookback*0.6)).mean()
    std = px.rolling(ci_lookback, min_periods=int(ci_lookback*0.6)).std()

    buy = px < (mean - buy_sigma * std)

    sell = pd.DataFrame(False, index=px.index, columns=px.columns)
    if "sigma" in sell_triggers:
        sell = sell | (px > (mean + sell_sigma * std))
    if "ma" in sell_triggers:
        ma = px.rolling(ma_window, min_periods=int(ma_window*0.6)).mean()
        sell = sell | (ma < ma.shift(1))
    if "rsi" in sell_triggers:
        sell = sell | (rsi_frame(px, rsi_window) >= rsi_sell)

    # held-state: +1 on buy, 0 on sell, ffill; act on t+1
    sig = pd.DataFrame(np.nan, index=px.index, columns=px.columns)
    sig = sig.mask(buy, 1.0).mask(sell, 0.0)
    held_eff = sig.ffill().fillna(0.0).shift(1).fillna(0.0)

    held_mask = held_eff > 0
    n_held = held_mask.sum(axis=1)
    strat_ret = (rets.where(held_mask)).mean(axis=1).fillna(0.0)
    flips = held_eff.diff().abs().sum(axis=1)
    cost = (cost_bps / 1e4) * (flips / n_held.replace(0, np.nan)).fillna(0.0)
    strat_ret = strat_ret - cost
    bh_ret = rets.mean(axis=1).fillna(0.0)

    out = pd.DataFrame({"date": px.index, "ret": strat_ret.values,
                        "bh_ret": bh_ret.values, "n_held": n_held.values})
    valid_from = mean.dropna(how="all").index.min()
    return out[out["date"] >= valid_from].reset_index(drop=True)


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


def evaluate(period_returns: pd.DataFrame, n_trials: int,
             periods_per_year: int = PERIODS_PER_YEAR, min_periods: int = MONTHLY_MIN_PERIODS) -> dict:
    """Judge a period-return series with the SAME apparatus as the options work:
    Sharpe + Deflated Sharpe (deflated by n_trials distinct configs), plus the
    re-frozen objective. `periods_per_year` lets the same code judge monthly
    (12) or daily (252) return series; Sharpe is annualized for display only."""
    from . import stats
    r = period_returns["ret"].to_numpy(float)
    r = r[np.isfinite(r)]
    n = r.size
    sr_p, skew, exk = stats.sharpe_stats(r)          # per-period Sharpe
    dsr = stats.deflated_sharpe_ratio(sr_p, r, n_trials) if n >= 2 else {"dsr": 0.0, "benchmark_sr": 0.0}

    eq = (1.0 + r).cumprod()
    peak = np.maximum.accumulate(eq)
    max_dd = float(np.max((peak - eq) / peak)) if n else 0.0
    ann_ret = float((1.0 + r).prod() ** (periods_per_year / n) - 1.0) if n else 0.0
    calmar = float(ann_ret / max_dd) if max_dd > 0 else 0.0   # return per unit drawdown

    reasons, passed = [], True
    if n >= min_periods:
        reasons.append(f"PASS n_periods {n} >= {min_periods}")
    else:
        passed = False; reasons.append(f"FAIL n_periods {n} < {min_periods}")
    mean = float(r.mean()) if n else 0.0
    if mean > 0:
        reasons.append(f"PASS mean period return {mean:.5f} > 0")
    else:
        passed = False; reasons.append(f"FAIL mean period return {mean:.5f} <= 0")
    if max_dd <= MONTHLY_MAX_DRAWDOWN:
        reasons.append(f"PASS max_drawdown {max_dd:.1%} <= {MONTHLY_MAX_DRAWDOWN:.0%}")
    else:
        passed = False; reasons.append(f"FAIL max_drawdown {max_dd:.1%} > {MONTHLY_MAX_DRAWDOWN:.0%}")
    dsr_val = dsr["dsr"] if dsr["dsr"] is not None and np.isfinite(dsr["dsr"]) else 0.0
    survives = bool(passed and dsr_val > 0.95)

    return {"n_periods": n, "sharpe_monthly": round(sr_p, 3),
            "sharpe_annual": round(sr_p * np.sqrt(periods_per_year), 3),
            "ann_return": round(ann_ret, 4), "max_drawdown": round(max_dd, 4),
            "calmar": round(calmar, 3),
            "skew": round(skew, 3), "dsr": round(dsr_val, 4),
            "dsr_benchmark_sr": round(dsr["benchmark_sr"], 4), "n_trials": n_trials,
            "objective_pass": passed, "reasons": reasons, "survives": survives}
