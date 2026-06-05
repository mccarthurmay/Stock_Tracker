"""Multi-ticker scan — the "scan until one works" experiment (answers the
   data-mining question directly).

Runs the long-premium (CALL) hypotheses across a whole universe of tickers and
counts EVERY (ticker × hypothesis × config) as a separate trial. The point is
to show, on real data, the two-step truth about ticker-shopping:

  1. With enough tickers, SOME (ticker, config) will look great on the
     train/validation window purely by chance — the max of many noisy results
     is positive. These are the "winners" a naive scan would trade.
  2. The Deflated Sharpe Ratio, deflated by the TOTAL trial count (all
     tickers × configs), removes them; and the apparent best is then checked on
     a holdout window it never saw. A real edge survives both; noise does not.

CALL options only (long premium on calls), per the request. Each ticker's bars
are split train/validation/holdout chronologically; the scan ranks on
validation, and the single best validation result has its holdout opened once.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from . import hypotheses, signals, backtester, validation, stats, metrics as M
from .costs import CostModel


def _call_symbols(store, ticker: str, timeframe: str) -> list[str]:
    """Stored option symbols for `ticker` that are CALLS (OCC ...C########)."""
    out = []
    for sym in store.option_symbols(ticker):
        # OCC: <root><yymmdd><C|P><strike8>; the type char is 9 from the end
        if len(sym) >= 9 and sym[-9] == "C":
            if not store.read_option_bars(sym, timeframe).empty:
                out.append(sym)
    return out


def _pooled(store, hyp, config, symbols, timeframe, split_name, spread_mult, bt_cfg):
    """Pool a config's trades over `symbols` within one split; return returns."""
    cfg = dataclasses.replace(bt_cfg, side=hyp.side)
    logs = []
    for sym in symbols:
        try:
            frame, sig = signals.signal_for_hypothesis(store, hyp, config, sym, timeframe)
        except KeyError:
            # config needs a column this symbol lacks (e.g. greeks not computed);
            # skip rather than crash the whole scan.
            continue
        if frame.empty:
            continue
        sp = validation.chronological_splits(frame["ts"])[split_name]
        m = sp.mask(frame["ts"])
        sf, ss = frame[m].reset_index(drop=True), sig[m].reset_index(drop=True)
        if sf.empty:
            continue
        res = backtester.run_backtest(sf, ss, cost_model=CostModel(spread_mult=spread_mult),
                                      config=cfg)
        if not res["trade_log"].empty:
            logs.append(res["trade_log"])
    if not logs:
        return pd.DataFrame(), np.array([])
    pooled = pd.concat(logs, ignore_index=True)
    return pooled, M.per_trade_returns(pooled)


def run_scan(store, tickers, timeframe="5Min", spread_mult=1.0,
             bt_cfg: backtester.BacktestConfig | None = None,
             dsr_threshold=0.95, only_calls=True, min_trades=20) -> dict:
    """Scan all (ticker × call-hypothesis × config) trials on validation, then
    deflate and open the holdout on the apparent best."""
    bt_cfg = bt_cfg or backtester.BacktestConfig(max_hold_bars=30,
                                                 take_profit_frac=None, stop_loss_frac=0.5)
    # call-option strategies only -> long-premium hypotheses (side=+1)
    hyps = [h for h in hypotheses.load() if h.side == +1]
    rows = []
    val_returns = {}

    for t in tickers:
        syms = _call_symbols(store, t, timeframe) if only_calls else store.option_symbols(t)
        if not syms:
            continue
        for h in hyps:
            for cfg in h.configs():
                chash = hypotheses.config_hash(h.id, cfg)
                key = f"{t}:{h.id}:{chash}"
                pooled, rets = _pooled(store, h, cfg, syms, timeframe, "validation",
                                       spread_mult, bt_cfg)
                m = M.compute_metrics(pooled)
                sr, _, _ = stats.sharpe_stats(rets)
                rows.append({"ticker": t, "hypothesis": h.id, "config_hash": chash,
                             "config": cfg, "n_trades": m.n_trades,
                             "effective_n": m.effective_n, "expectancy": m.expectancy,
                             "sharpe_per_trade": round(sr, 3),
                             "return_skew": m.return_skew, "max_drawdown": m.max_drawdown,
                             "objective_pass": M.passes_objective(m).passed})
                if rets.size >= min_trades:
                    val_returns[key] = rets

    report = pd.DataFrame(rows)
    if report.empty:
        return {"report": report, "n_trials": 0, "in_sample_winners": report,
                "survivors": report, "best": None, "holdout": None}

    # TOTAL trial count = every (ticker × config) evaluated (ROADMAP §4/§6.5)
    n_trials = len(report)

    # "In-sample winners": positive expectancy on validation (what a naive scan
    # would trade). Count them — this is the false-positive harvest.
    winners = report[(report["expectancy"] > 0) & (report["n_trades"] >= min_trades)] \
        .sort_values("sharpe_per_trade", ascending=False)

    # Deflated Sharpe on each winner, deflated by the full trial count.
    surv = []
    for _, r in winners.iterrows():
        key = f"{r['ticker']}:{r['hypothesis']}:{r['config_hash']}"
        rets = val_returns.get(key)
        if rets is None or rets.size < 2:
            surv.append(0.0)
            continue
        sr, _, _ = stats.sharpe_stats(rets)
        d = stats.deflated_sharpe_ratio(sr, rets, n_trials)
        surv.append(round(d["dsr"] if d["dsr"] is not None and np.isfinite(d["dsr"]) else 0.0, 4))
    winners = winners.copy()
    winners["dsr"] = surv
    winners["survives_dsr"] = [s > dsr_threshold for s in surv]
    survivors = winners[winners["survives_dsr"]]

    # Open the holdout ONCE on the single best validation result (highest SR).
    holdout = None
    if not winners.empty:
        best = winners.iloc[0]
        h = next(hh for hh in hyps if hh.id == best["hypothesis"])
        cfg = next(c for c in h.configs()
                   if hypotheses.config_hash(h.id, c) == best["config_hash"])
        syms = _call_symbols(store, best["ticker"], timeframe)
        pooled, _ = _pooled(store, h, cfg, syms, timeframe, "holdout", spread_mult, bt_cfg)
        mh = M.compute_metrics(pooled)
        vh = M.passes_objective(mh)
        holdout = {"ticker": best["ticker"], "hypothesis": best["hypothesis"],
                   "config_hash": best["config_hash"],
                   "val_expectancy": float(best["expectancy"]),
                   "val_sharpe": float(best["sharpe_per_trade"]),
                   "val_dsr": float(best["dsr"]),
                   "holdout_trades": mh.n_trades, "holdout_expectancy": mh.expectancy,
                   "holdout_sharpe": mh.sharpe, "holdout_passes": vh.passed}

    return {"report": report, "n_trials": n_trials, "in_sample_winners": winners,
            "survivors": survivors, "best": (winners.iloc[0].to_dict() if not winners.empty else None),
            "holdout": holdout, "n_tickers": report["ticker"].nunique(),
            "dsr_threshold": dsr_threshold}
