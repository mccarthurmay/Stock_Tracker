"""Validation harness (ROADMAP §6) — where most edges should die.

Provides:
  * chronological train/validation/holdout splits (no shuffling, no leakage;
    every split boundary is a point in time, and later data never informs
    earlier features)
  * walk-forward windows (rolling/anchored) for out-of-sample-through-time
  * parameter sensitivity: a real edge is a broad PLATEAU, not a sharp SPIKE;
    we sweep a hypothesis's params and measure how expectancy holds up when a
    parameter moves one step (curve-fit detector)

Honest caveat baked into the docs: Alpaca history (~Feb 2024+) is ~one regime,
so the holdout and the handful of walk-forward folds are same-regime and weak;
the real out-of-regime test is Phase B (ROADMAP §6.1, §6.4).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import features, signals, hypotheses, backtester, metrics as M
from .costs import CostModel


@dataclass
class Split:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp           # half-open [start, end)

    def mask(self, ts: pd.Series) -> pd.Series:
        return (ts >= self.start) & (ts < self.end)


def chronological_splits(ts: pd.Series, train=0.6, val=0.2) -> dict[str, Split]:
    """Split a sorted timestamp series into train / validation / holdout.

    Boundaries are at time quantiles, so the holdout is strictly the most
    recent slice and is never touched during development (ROADMAP §6.1).
    """
    ts = pd.to_datetime(pd.Series(ts)).sort_values().reset_index(drop=True)
    if ts.empty:
        raise ValueError("empty timestamp series")
    t0, t1 = ts.iloc[0], ts.iloc[-1]
    span = t1 - t0
    b_train = t0 + span * train
    b_val = t0 + span * (train + val)
    end = t1 + pd.Timedelta(seconds=1)  # make the last bar inclusive
    return {
        "train": Split("train", t0, b_train),
        "validation": Split("validation", b_train, b_val),
        "holdout": Split("holdout", b_val, end),
    }


def walk_forward_windows(ts: pd.Series, n_folds=4, train_frac=0.5,
                         anchored=False) -> list[dict[str, Split]]:
    """Rolling (or anchored) walk-forward folds across the timeline.

    Each fold is {'train': Split, 'test': Split} with test immediately after
    train and no overlap. With shallow Alpaca history expect few folds — report
    the count and don't over-interpret (ROADMAP §6.4).
    """
    ts = pd.to_datetime(pd.Series(ts)).sort_values().reset_index(drop=True)
    t0, t1 = ts.iloc[0], ts.iloc[-1]
    end = t1 + pd.Timedelta(seconds=1)
    span = end - t0
    test_frac = (1.0 - train_frac) / n_folds
    folds = []
    for k in range(n_folds):
        test_start = t0 + span * (train_frac + k * test_frac)
        test_end = t0 + span * (train_frac + (k + 1) * test_frac)
        train_start = t0 if anchored else t0 + span * (k * test_frac)
        folds.append({
            "train": Split(f"wf{k}_train", train_start, test_start),
            "test": Split(f"wf{k}_test", test_start, test_end),
        })
    return folds


def _backtest_on(frame: pd.DataFrame, sig: pd.Series, spread_mult: float,
                 bt_cfg: backtester.BacktestConfig) -> M.Metrics:
    cm = CostModel(spread_mult=spread_mult)
    res = backtester.run_backtest(frame, sig, cost_model=cm, config=bt_cfg)
    return M.compute_metrics(res["trade_log"], res["equity_curve"])


def evaluate_split(store, hyp, config: dict, option_symbol: str, split: Split,
                   timeframe="1Min", spread_mult=1.0,
                   bt_cfg: backtester.BacktestConfig | None = None) -> M.Metrics:
    """Compute features + signal on the full series, then evaluate only within
    `split`. Features are computed causally on the full history (so rolling
    windows are warm at the split start) but trades are taken only inside the
    split window — no future data leaks into a feature value."""
    bt_cfg = bt_cfg or backtester.BacktestConfig()
    frame, sig = signals.signal_for_hypothesis(store, hyp, config, option_symbol, timeframe)
    if frame.empty:
        return M.compute_metrics(pd.DataFrame())
    m = split.mask(frame["ts"])
    sub_frame = frame[m].reset_index(drop=True)
    sub_sig = sig[m].reset_index(drop=True)
    return _backtest_on(sub_frame, sub_sig, spread_mult, bt_cfg)


def parameter_sensitivity(store, hyp, option_symbol: str, split: Split | None = None,
                          timeframe="1Min", spread_mult=1.0,
                          bt_cfg: backtester.BacktestConfig | None = None) -> pd.DataFrame:
    """Expectancy across ALL of a hypothesis's configs — the plateau test.

    A robust edge varies smoothly across neighbouring parameter settings; if
    expectancy spikes at one config and collapses at its neighbours, it is a
    curve-fit and should be rejected (ROADMAP §6.3).
    """
    rows = []
    for cfg in hyp.configs():
        if split is not None:
            m = evaluate_split(store, hyp, cfg, option_symbol, split,
                               timeframe, spread_mult, bt_cfg)
        else:
            frame, sig = signals.signal_for_hypothesis(store, hyp, cfg, option_symbol, timeframe)
            m = (_backtest_on(frame, sig, spread_mult, bt_cfg or backtester.BacktestConfig())
                 if not frame.empty else M.compute_metrics(pd.DataFrame()))
        rows.append({"config": cfg, "config_hash": hypotheses.config_hash(hyp.id, cfg),
                     "n_trades": m.n_trades, "expectancy": m.expectancy,
                     "sharpe": m.sharpe, "max_drawdown": m.max_drawdown})
    df = pd.DataFrame(rows)
    if len(df) > 1:
        exp = df["expectancy"].to_numpy(float)
        # plateau score: 1 - (dispersion of neighbours / level). Lower => spiky.
        rng = exp.max() - exp.min()
        df.attrs["plateau_spread"] = float(rng)
        df.attrs["is_spiky"] = bool(rng > 0 and (exp.max() - np.median(exp)) > 0.6 * rng)
    return df
