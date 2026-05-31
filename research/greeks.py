"""Self-computed IV + Greeks per option bar (ROADMAP §2b, M2).

For each aligned option bar we compute time-to-expiry (to 16:00 ET on the
expiry date), look up a point-in-time risk-free rate, route by DTE to the
Black-Scholes (0/1DTE) or American CRR (longer-dated) model, invert IV from
the bar price, and evaluate Greeks at that IV. Results land in option_greeks.

Everything here is approximate and labelled as such: IV is inverted from a
single (indicative, on the free feed) trade/VWAP print. Prints outside
no-arbitrage bounds yield iv=NaN / iv_converged=False — that is expected, not
a bug. IV-derived *features* remain Phase-B-only for belief (ROADMAP §3).

Greek units stored (trader conventions):
  delta (per $1 underlying), gamma (per $1^2), vega_pct (per 1 vol point),
  theta_day (per calendar day, negative for long), rho_pct (per 1% rate).
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import ingest, pricing
from .occ import parse_occ
from .rates import RateProvider

NY = ZoneInfo("America/New_York")
SECONDS_PER_YEAR = pricing.YEAR_DAYS * 24 * 3600


def _expiry_moment_utc(expiry_naive: pd.Series) -> pd.Series:
    """16:00 America/New_York on each expiry date, as UTC timestamps."""
    naive_4pm = pd.to_datetime(expiry_naive) + pd.Timedelta(hours=16)
    return naive_4pm.dt.tz_localize(NY, nonexistent="shift_forward",
                                    ambiguous=True).dt.tz_convert("UTC")


def compute_for(store, option_symbol: str, timeframe: str = "1Min",
                rate_provider: RateProvider | None = None, div_yield: float = 0.0,
                bs_max_dte: int = 2, crr_steps: int = 160,
                price_source: str = "vwap") -> dict:
    """Compute and store IV+Greeks for one option contract's bars."""
    df = ingest.align(store, option_symbol, timeframe)
    if df.empty:
        return {"rows": 0, "converged": 0, "total": 0, "models": {}}
    rp = rate_provider or RateProvider()
    n = len(df)

    # Price to invert: prefer VWAP (less single-print noise) else close.
    vwap = df["opt_vwap"]
    use_vwap = (price_source == "vwap") & vwap.notna() & (vwap > 0)
    price = np.where(use_vwap, vwap, df["opt_close"]).astype(float)
    psource = np.where(use_vwap, "vwap", "close").astype(object)

    S = df["under_close"].to_numpy(float)
    K = df["strike"].to_numpy(float)
    is_call = (df["opt_type"] == "call").to_numpy()
    ts = df["ts"]
    exp_naive = pd.to_datetime(df["expiry"])

    # Time to expiry (years) and DTE (calendar days).
    tte = (_expiry_moment_utc(exp_naive) - ts).dt.total_seconds().to_numpy() / SECONDS_PER_YEAR
    ts_day = ts.dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()
    dte_days = (exp_naive.dt.normalize() - ts_day).dt.days.to_numpy()

    # Point-in-time risk-free rate, one lookup per distinct date.
    dser = ts.dt.tz_convert("UTC").dt.date
    rate_map = {d: rp.rate_for(d) for d in pd.unique(dser)}
    rate = dser.map(rate_map).to_numpy(float)

    q = float(div_yield)
    valid = tte > 0
    model = np.where(dte_days <= bs_max_dte, "bs", "crr").astype(object)
    model = np.where(~valid, "expired", model)

    iv = np.full(n, np.nan)
    conv = np.zeros(n, bool)
    resid = np.full(n, np.nan)
    delta = np.full(n, np.nan)
    gamma = np.full(n, np.nan)
    vega = np.full(n, np.nan)
    theta = np.full(n, np.nan)
    rho = np.full(n, np.nan)

    # Black-Scholes group: fully vectorized.
    bs_idx = np.where(valid & (model == "bs"))[0]
    if bs_idx.size:
        iv_i, conv_i, res_i = pricing.bs_iv(
            price[bs_idx], S[bs_idx], K[bs_idx], tte[bs_idx], rate[bs_idx], q, is_call[bs_idx])
        iv[bs_idx], conv[bs_idx], resid[bs_idx] = iv_i, conv_i, res_i
        fin = np.isfinite(iv[bs_idx])
        if fin.any():
            j = bs_idx[fin]
            g = pricing.bs_greeks(S[j], K[j], tte[j], rate[j], q, iv[j], is_call[j])
            delta[j], gamma[j], vega[j], theta[j], rho[j] = (
                g["delta"], g["gamma"], g["vega"], g["theta"], g["rho"])

    # American CRR group: scalar loop (longer-dated, fewer rows in practice).
    for idx in np.where(valid & (model == "crr"))[0]:
        ivv, ok = pricing.crr_iv(price[idx], S[idx], K[idx], tte[idx], rate[idx], q,
                                 bool(is_call[idx]), steps=crr_steps)
        iv[idx], conv[idx] = ivv, ok
        if ok and np.isfinite(ivv):
            resid[idx] = abs(pricing.crr_price(S[idx], K[idx], tte[idx], rate[idx], q,
                                               ivv, bool(is_call[idx]), crr_steps) - price[idx])
            g = pricing.crr_greeks(S[idx], K[idx], tte[idx], rate[idx], q, ivv,
                                   bool(is_call[idx]), crr_steps)
            delta[idx], gamma[idx], vega[idx], theta[idx], rho[idx] = (
                g["delta"], g["gamma"], g["vega"], g["theta"], g["rho"])

    out = pd.DataFrame({
        "option_symbol": option_symbol,
        "underlying": df["underlying"].to_numpy(),
        "expiry": df["expiry"].to_numpy(),
        "strike": K,
        "opt_type": df["opt_type"].to_numpy(),
        "timeframe": timeframe,
        "ts": ts.to_numpy(),
        "under_price": S,
        "opt_price": price,
        "price_source": psource,
        "dte_days": dte_days.astype("int64"),
        "tte_years": tte,
        "rate": rate,
        "div_yield": q,
        "model": model,
        "iv": iv,
        "iv_converged": conv,
        "iv_residual": resid,
        "delta": delta,
        "gamma": gamma,
        "vega_pct": vega / 100.0,
        "theta_day": theta / pricing.YEAR_DAYS,
        "rho_pct": rho / 100.0,
        "feed": df["feed"].to_numpy(),
        "computed_at": pd.Timestamp.now(tz="UTC"),
    })
    written = store.upsert_option_greeks(out)
    models = pd.Series(model).value_counts().to_dict()
    store.log_ingest("option_greeks", option_symbol, timeframe, ts.min(), ts.max(),
                     str(df["feed"].iloc[0]), written,
                     note=f"rate_src={rp.source} converged={int(conv.sum())}/{n}")
    return {"rows": written, "converged": int(conv.sum()), "total": n, "models": models}


def live_sanity(client, symbols: list[str], rate_provider: RateProvider | None = None,
                div_yield: float = 0.0, bs_max_dte: int = 2, crr_steps: int = 160) -> list[dict]:
    """Self-consistency check of our IV/Greeks against a live snapshot.

    NOTE: the free indicative feed returns NO IV/Greeks/trades (only quotes),
    so the alpaca_* columns are null on the free tier and a true vendor
    comparison is a Phase-B activity (ROADMAP §2d). On the free tier this still
    confirms the live path works and the numbers are sane (ATM delta ~ +/-0.5).
    Option price is the latest trade if present, else the quote mid.
    """
    rp = rate_provider or RateProvider()
    snaps = client.option_snapshots(symbols)
    now = datetime.now(timezone.utc)
    spot_cache: dict[str, float | None] = {}
    rows = []
    for sym in symbols:
        snap = snaps.get(sym)
        if snap is None:
            rows.append({"symbol": sym, "note": "no snapshot"})
            continue
        c = parse_occ(sym)
        if c.underlying not in spot_cache:
            spot_cache[c.underlying] = client.stock_latest_trade_price(c.underlying)
        spot = spot_cache[c.underlying]

        # Price: latest trade if available, else quote mid (indicative has no trades).
        opt_price, opt_src = None, None
        if snap.latest_trade and snap.latest_trade.price:
            opt_price, opt_src = float(snap.latest_trade.price), "trade"
        elif snap.latest_quote and snap.latest_quote.bid_price and snap.latest_quote.ask_price:
            b, a = snap.latest_quote.bid_price, snap.latest_quote.ask_price
            if b > 0 and a > 0:
                opt_price, opt_src = (b + a) / 2.0, "quote_mid"
        ag = snap.greeks

        exp_utc = _expiry_moment_utc(pd.Series([pd.Timestamp(c.expiry)])).iloc[0]
        tte = (exp_utc - pd.Timestamp(now)).total_seconds() / SECONDS_PER_YEAR
        dte = (c.expiry - now.date()).days
        rate = rp.rate_for(now.date())
        is_call = c.opt_type == "call"

        our_iv, our_g, model = np.nan, None, None
        if opt_price and spot and tte > 0:
            if dte <= bs_max_dte:
                model = "bs"
                iv, conv, _ = pricing.bs_iv(opt_price, spot, c.strike, tte, rate, div_yield, is_call)
                our_iv = float(iv)
                if np.isfinite(our_iv):
                    our_g = pricing.bs_greeks(spot, c.strike, tte, rate, div_yield, our_iv, is_call)
            else:
                model = "crr"
                iv, conv = pricing.crr_iv(opt_price, spot, c.strike, tte, rate, div_yield, is_call, crr_steps)
                our_iv = float(iv)
                if conv and np.isfinite(our_iv):
                    our_g = pricing.crr_greeks(spot, c.strike, tte, rate, div_yield, our_iv, is_call, crr_steps)

        rows.append({
            "symbol": sym, "dte": dte, "spot": spot,
            "opt_price": round(opt_price, 4) if opt_price else None, "opt_src": opt_src,
            "model": model,
            "alpaca_iv": snap.implied_volatility,
            "our_iv": round(our_iv, 4) if np.isfinite(our_iv) else None,
            "alpaca_delta": getattr(ag, "delta", None),
            "our_delta": round(float(our_g["delta"]), 4) if our_g else None,
            "our_gamma": round(float(our_g["gamma"]), 5) if our_g else None,
            "our_vega_pct": round(float(our_g["vega"]) / 100, 4) if our_g else None,
            "our_theta_day": round(float(our_g["theta"]) / pricing.YEAR_DAYS, 4) if our_g else None,
            "rate_src": rp.source,
        })
    return rows


def compute_underlying(store, underlying: str, timeframe: str = "1Min", **kw) -> dict:
    """Compute IV+Greeks for every option of `underlying` present in option_bars."""
    rp = kw.pop("rate_provider", None) or RateProvider()
    syms = store.option_symbols(underlying)
    agg = {"contracts": 0, "rows": 0, "converged": 0, "total": 0}
    for sym in syms:
        r = compute_for(store, sym, timeframe, rate_provider=rp, **kw)
        agg["contracts"] += 1
        for k in ("rows", "converged", "total"):
            agg[k] += r[k]
    agg["rate_source"] = rp.source
    return agg
