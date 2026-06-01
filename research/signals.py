"""Turn a hypothesis config into a +1/0 entry signal (ROADMAP §3 -> §5).

This v1 maps each seed hypothesis to a simple, transparent entry rule over the
computed indicator columns. The rule is intentionally plain: the point of M4 is
an honest backtest engine, not a clever signal. A signal is a Series on the
frame index: 1 = "want to be long premium given this bar's close" (the engine
acts on the NEXT bar's open), 0 = flat.

Every rule is causal — it reads only indicator columns, which are themselves
causal — so no lookahead is introduced here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import features


def _entry_rule(hyp_id: str, df: pd.DataFrame) -> pd.Series:
    z = pd.Series(0, index=df.index, dtype=int)
    if hyp_id == "oversold_mean_reversion":
        rsi_col = next((c for c in df.columns if c.startswith("rsi")), "rsi")
        return (df[rsi_col] < 30).astype(int)
    if hyp_id == "trend_pullback_continuation":
        pvs = next((c for c in df.columns if c.startswith("price_vs_sma")), "price_vs_sma")
        return ((df[pvs] > 0) & (df["rsi"] < 45)).astype(int)
    if hyp_id == "volatility_squeeze_breakout":
        bw = next((c for c in df.columns if c.startswith("bollinger_bw")), "bollinger_bw")
        # squeeze = bandwidth in the bottom quintile of its own history (causal rank)
        rank = df[bw].rolling(60, min_periods=20).apply(
            lambda w: (w.iloc[-1] <= w).mean(), raw=False)
        return (rank < 0.2).astype(int)
    if hyp_id == "gamma_scalp_zone":
        return ((df["gamma"] > df["gamma"].median()) & (df["moneyness"].abs() < 0.01)
                & (df["dte"] <= 2)).astype(int)
    if hyp_id == "iv_overpriced_fade":
        ivr = next((c for c in df.columns if c.startswith("iv_rank")), "iv_rank")
        return (df[ivr] > 0.8).astype(int)
    return z


def signal_for_hypothesis(store, hyp, config: dict, option_symbol: str,
                          timeframe: str = "1Min") -> tuple[pd.DataFrame, pd.Series]:
    """Compute the feature frame for a config and derive its entry signal."""
    frame = features.feature_frame(store, option_symbol, timeframe)
    if frame.empty:
        return frame, pd.Series(dtype=int)
    frame = features.compute_for_config(frame, config)
    sig = _entry_rule(hyp.id, frame).fillna(0).astype(int)
    return frame, sig
