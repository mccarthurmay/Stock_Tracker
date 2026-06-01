"""Event-driven, point-in-time backtester for long-premium option trades
(ROADMAP §5).

Hard invariants:
  * NO LOOKAHEAD, ONE UNIFORM RULE. Everything *observed* at the close of bar t
    (the entry signal, and the premium that triggers a stop / take-profit /
    max-hold / flat exit) executes at the OPEN of bar t+1. Nothing is ever
    filled on the same bar that produced the decision, and no intrabar fill is
    assumed. Minimum hold is therefore one bar (open t+1 -> open t+2).
  * COSTS ALWAYS ON. Entry and exit cross the worse side of the modeled spread
    (costs.py); a stop adds fat-tailed slippage. There is no "frictionless" mode.

Scope (v1, ROADMAP §0): single-contract, long-premium (capped-loss) trades on
one option's bar series. A `signal` is a Series aligned to the frame: +1 = be
long this bar's signal (act next open), 0 = flat. Exits: opposite signal, a
stop (fraction of entry premium), a take-profit, or a max-hold in bars.

Output: a trade log (entry/exit/price/size/costs/reason + timestamps) and an
equity curve, both consumed by metrics.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .costs import CostModel


@dataclass
class BacktestConfig:
    contracts: int = 1
    side: int = +1                   # +1 = long premium (buy), -1 = short premium (sell)
    stop_loss_frac: float = 0.5      # exit if position P&L falls -stop_loss_frac of premium
    take_profit_frac: float | None = 1.0  # exit if position P&L gains +take_profit_frac
    max_hold_bars: int | None = 60   # force-exit after N bars
    price_col: str = "opt_close"     # mid proxy to fill against (next-open ideally)
    open_col: str = "opt_open"       # next-bar open used for fills
    seed: int = 0

    def __post_init__(self):
        if self.side not in (+1, -1):
            raise ValueError(f"side must be +1 (long) or -1 (short), got {self.side}")


def _moneyness_abs(row) -> float:
    s = row.get("under_close")
    k = row.get("strike")
    if s and k and s > 0 and k > 0:
        return abs(np.log(s / k))
    return 0.0


def run_backtest(frame: pd.DataFrame, signal: pd.Series,
                 cost_model: CostModel | None = None,
                 config: BacktestConfig | None = None) -> dict:
    """Run the backtest. Returns {trade_log, equity_curve, config}.

    `frame` must be sorted by ts and carry: ts, opt_close, opt_open (fallback to
    opt_close if absent), under_close, strike, dte_days. `signal` is +1/0 on the
    same index. Signals act on the NEXT bar's open (no lookahead).
    """
    cm = cost_model or CostModel()
    cfg = config or BacktestConfig()
    side = cfg.side
    rng = np.random.default_rng(cfg.seed)

    df = frame.reset_index(drop=True)
    sig = pd.Series(signal).reset_index(drop=True).fillna(0).astype(int)
    n = len(df)
    open_col = cfg.open_col if cfg.open_col in df.columns else cfg.price_col

    trades = []
    equity = 0.0
    equity_rows = []
    pos = None  # open position dict; entered = filled, awaiting exit

    def _open(i):
        return float(df.at[i, open_col])

    for i in range(n):
        ts = df.at[i, "ts"]

        # --- decide an exit using info OBSERVED at close[i]; fill at open[i+1].
        # Uniform rule: every decision made on bar i executes on bar i+1's open.
        if pos is not None and i > pos["entry_i"]:
            close_i = float(df.at[i, cfg.price_col])
            entry = pos["entry_price"]
            # Position P&L as a fraction of premium, signed by side: for a long
            # (side=+1) price-down is a loss; for a short (side=-1) price-UP is
            # the loss. Stop/TP key off this signed fraction so they flip
            # correctly. (entry guarded > 0 so the ratio is well-defined.)
            pnl_frac = side * (close_i / entry - 1.0) if entry > 0 else 0.0
            stop_hit = pnl_frac <= -cfg.stop_loss_frac
            tp_hit = (cfg.take_profit_frac is not None
                      and pnl_frac >= cfg.take_profit_frac)
            held = i - pos["entry_i"]
            max_hit = cfg.max_hold_bars is not None and held >= cfg.max_hold_bars
            sig_exit = sig.iat[i] == 0
            no_next = i == n - 1  # cannot fill next open -> close now at this open

            reason = ("stop" if stop_hit else "take_profit" if tp_hit
                      else "max_hold" if max_hit else "signal_flat" if sig_exit
                      else "eod_close" if no_next else None)

            if reason is not None:
                # fill at NEXT open (open[i+1]); if no next bar, fill at open[i].
                fi = i if no_next else i + 1
                fill_mid = _open(fi)
                is_stop = reason == "stop"
                # Exiting reverses direction: cm.exit_fill takes the ENTRY side
                # and internally flips it (a long sells out, a short buys back).
                exit_px = float(cm.exit_fill(fill_mid, df.at[fi, "dte_days"],
                                             _moneyness_abs(df.loc[fi]), side=side,
                                             is_stop=is_stop, rng=rng))
                # P&L signed by side: long earns exit-entry, short earns entry-exit.
                gross = side * (exit_px - pos["entry_fill"]) * cfg.contracts * cm.contract_multiplier
                exit_comm = cm.commission(cfg.contracts)
                net = gross - exit_comm - pos["entry_commission"]
                equity += gross - exit_comm  # entry commission already debited
                trades.append({
                    **pos["record"],
                    "exit_i": fi, "exit_ts": df.at[fi, "ts"], "exit_mid": fill_mid,
                    "exit_fill": round(exit_px, 4), "exit_reason": reason,
                    "exit_commission": round(exit_comm, 4),
                    "gross_pnl": round(gross, 4),
                    "net_pnl": round(net, 4),
                })
                pos = None

        # --- new entry: signal OBSERVED at close[i] fills at open[i+1].
        if pos is None and i < n - 1 and sig.iat[i] == 1:
            j = i + 1
            entry_mid = _open(j)
            entry_px = float(cm.entry_fill(entry_mid, df.at[j, "dte_days"],
                                           _moneyness_abs(df.loc[j]), side=side))
            entry_comm = cm.commission(cfg.contracts)
            equity -= entry_comm
            pos = {
                "entry_i": j, "entry_price": entry_px, "entry_fill": entry_px,
                "entry_commission": entry_comm,
                "record": {
                    "option_symbol": (df.at[j, "option_symbol"]
                                      if "option_symbol" in df.columns else None),
                    "side": "long" if side == +1 else "short", "contracts": cfg.contracts,
                    "signal_i": i, "signal_ts": df.at[i, "ts"],
                    "entry_i": j, "entry_ts": df.at[j, "ts"],
                    "entry_mid": entry_mid, "entry_fill": round(entry_px, 4),
                    "entry_commission": round(entry_comm, 4),
                },
            }

        equity_rows.append({"ts": ts, "equity": equity})

    trade_log = pd.DataFrame(trades)
    equity_curve = pd.DataFrame(equity_rows)
    return {"trade_log": trade_log, "equity_curve": equity_curve, "config": cfg}
