"""M6 orchestrator — run the reasoned hypothesis set, report survivors honestly.

Runs EVERY hypothesis × EVERY config × the option universe through the M4/M5
pipeline, pooling trades per config, then judges each against:
  1. the frozen objective (metrics.passes_objective) on validation,
  2. the Deflated Sharpe Ratio, deflated by the TRUE distinct-config count
     across the whole run (ROADMAP §4/§6.5 — the multiple-testing N), and
  3. White's Reality Check across all configs (best-of-N is luck?).

The governing prior (ROADMAP §0): the expected, correct outcome is **no robust
edge**. This function does not relax any bar to manufacture a survivor. On the
free indicative feed even a "survivor" is Phase-A-only and not believable.

The holdout is NOT opened here — that is the separate one-shot `holdout`
command, used only on a candidate that already cleared everything else.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import (hypotheses, signals, backtester, validation, stats,
               metrics as M)
from .costs import CostModel


def _pooled_validation_trades(store, hyp, config, symbols, timeframe,
                              spread_mult, bt_cfg):
    """Pool validation-window trades for one config across all contracts.

    Each contract's features are computed causally on its full history; trades
    are taken only within that contract's validation split, then concatenated.
    Returns (trade_log, per_trade_returns).
    """
    logs = []
    for sym in symbols:
        frame, sig = signals.signal_for_hypothesis(store, hyp, config, sym, timeframe)
        if frame.empty:
            continue
        sp = validation.chronological_splits(frame["ts"])["validation"]
        m = sp.mask(frame["ts"])
        sub_f = frame[m].reset_index(drop=True)
        sub_s = sig[m].reset_index(drop=True)
        if sub_f.empty:
            continue
        res = backtester.run_backtest(sub_f, sub_s,
                                      cost_model=CostModel(spread_mult=spread_mult),
                                      config=bt_cfg)
        if not res["trade_log"].empty:
            logs.append(res["trade_log"])
    if not logs:
        return pd.DataFrame(), np.array([])
    pooled = pd.concat(logs, ignore_index=True)
    return pooled, M.per_trade_returns(pooled)


def run_all(store, symbols, timeframe="1Min", spread_mult=1.0,
            bt_cfg: backtester.BacktestConfig | None = None,
            dsr_threshold=0.95, record=True) -> dict:
    """Run the full reasoned hypothesis set; return an honest survivors report."""
    hyps = hypotheses.load()
    bt_cfg = bt_cfg or backtester.BacktestConfig()
    rows = []

    # Pass 1: evaluate every config, record it in the ledger (so the distinct-N
    # used for deflation reflects what was actually executed in THIS run).
    candidate_returns = {}
    for h in hyps:
        for cfg in h.configs():
            chash = hypotheses.config_hash(h.id, cfg)
            if record:
                import json
                store.record_config_run(chash, h.id, h.phase,
                                        json.dumps(cfg, default=str),
                                        dataset=",".join(symbols)[:200], split="validation")
            pooled, rets = _pooled_validation_trades(
                store, h, cfg, symbols, timeframe, spread_mult, bt_cfg)
            m = M.compute_metrics(pooled)
            verdict = M.passes_objective(m)
            sr, _, _ = stats.sharpe_stats(rets)
            rows.append({
                "hypothesis": h.id, "phase": h.phase, "config_hash": chash,
                "config": cfg, "n_trades": m.n_trades, "effective_n": m.effective_n,
                "expectancy": m.expectancy, "sharpe_per_trade": round(sr, 3),
                "max_drawdown": m.max_drawdown, "return_skew": m.return_skew,
                "objective_pass": verdict.passed,
                "reasons": verdict.reasons,
            })
            if rets.size >= 2:
                candidate_returns[f"{h.id}:{chash}"] = rets

    report = pd.DataFrame(rows)

    # Multiple-testing N: the distinct configs actually executed (ROADMAP §4).
    n_trials = max(store.distinct_config_count(), len(report))

    # Pass 2: DSR for each config that passed the objective, deflated by N.
    dsr_vals, dsr_surv = [], []
    for r in rows:
        key = f"{r['hypothesis']}:{r['config_hash']}"
        rets = candidate_returns.get(key, np.array([]))
        if r["objective_pass"] and rets.size >= 2:
            sr, _, _ = stats.sharpe_stats(rets)
            d = stats.deflated_sharpe_ratio(sr, rets, n_trials)
            dsr = d["dsr"] if d["dsr"] is not None and np.isfinite(d["dsr"]) else 0.0
        else:
            dsr = 0.0
        dsr_vals.append(round(dsr, 4))
        dsr_surv.append(bool(r["objective_pass"] and dsr > dsr_threshold))
    if not report.empty:
        report["dsr"] = dsr_vals
        report["survives"] = dsr_surv

    # Reality Check across all configs that produced trades.
    rc = stats.whites_reality_check(candidate_returns, n_boot=2000, seed=0) \
        if candidate_returns else {"best": None, "p_value": 1.0, "n_strategies": 0}

    survivors = report[report["survives"]] if not report.empty else report
    return {
        "report": report, "survivors": survivors, "n_trials": n_trials,
        "reality_check": rc, "n_hypotheses": len(hyps),
        "n_configs": len(report), "symbols": symbols,
        "dsr_threshold": dsr_threshold,
    }
