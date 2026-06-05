"""Compute registered indicators onto a feature frame (ROADMAP §3).

Loads an option contract's aligned bars + self-computed Greeks from storage,
then evaluates named indicators (pure, causal) into columns. This is the bridge
from the data spine to the hypothesis layer; it does not trade or signal.
"""
from __future__ import annotations

import pandas as pd

from . import ingest, registry


def feature_frame(store, option_symbol: str, timeframe: str = "1Min") -> pd.DataFrame:
    """Aligned option/underlying bars joined with self-computed Greeks/IV.

    Returns one row per bar with the columns indicators expect. Greek/IV columns
    are present only if option_greeks has been computed (M2); indicators that
    need them will raise a clear KeyError otherwise.
    """
    bars = ingest.align(store, option_symbol, timeframe)
    if bars.empty:
        return bars
    g = store.read_option_greeks(option_symbol, timeframe)
    if not g.empty:
        gcols = ["ts", "iv", "iv_converged", "delta", "gamma", "vega_pct",
                 "theta_day", "dte_days", "tte_years"]
        bars = bars.merge(g[gcols], on="ts", how="left")
    return bars.sort_values("ts").reset_index(drop=True)


def compute(df: pd.DataFrame, names: list[str],
            overrides: dict | None = None) -> pd.DataFrame:
    """Add one column per requested indicator. overrides: {name: {param: val}}."""
    overrides = overrides or {}
    out = df.copy()
    for name in names:
        spec = registry.get(name)
        out[name] = spec.compute(df, **overrides.get(name, {}))
    return out


def compute_for_config(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Add columns for a hypothesis config: {indicator_name: params}."""
    out = df.copy()
    for name, params in config.items():
        out[name] = registry.get(name).compute(df, **params)
    return out
