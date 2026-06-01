"""Performance metrics + the frozen objective (ROADMAP §1).

The objective is decided up front and not moved: **positive expectancy net of
realistic costs**, subject to risk constraints. Win rate is NEVER the
objective — optimizing it selects for dangerous negative-skew strategies.

All metrics are computed from a trade log (one row per closed trade, with a
net P&L already inclusive of costs) and an equity curve. `passes_objective`
returns a single bool plus the reasons, so a later run can never quietly relax
the bar.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

# Frozen thresholds (ROADMAP §1). Changing these changes the goalposts —
# do so only deliberately, in version control, with justification.
MAX_DRAWDOWN_CEILING = 0.20      # ≤ 20% on the test equity curve
MIN_EFFECTIVE_TRADES = 200       # effective N, not raw count
MIN_EXPECTANCY = 0.0             # must be strictly positive net of costs
TRADING_PERIODS_PER_YEAR = 252


@dataclass
class Metrics:
    n_trades: int
    effective_n: float
    win_rate: float
    loss_rate: float
    avg_win: float
    avg_loss: float          # reported as a positive magnitude
    expectancy: float        # (win_rate*avg_win) - (loss_rate*avg_loss)
    profit_factor: float
    total_pnl: float
    avg_trade: float
    worst_trade: float
    best_trade: float
    return_skew: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float      # positive fraction (0.20 == 20%)
    worst_day: float

    def to_dict(self) -> dict:
        return asdict(self)


def _effective_n(pnl: pd.Series, entry_ts: pd.Series | None,
                 exit_ts: pd.Series | None) -> float:
    """Effective sample size, deflated for serial correlation / overlap.

    Two deflators, take the smaller (ROADMAP §1, §6.3):
      * autocorrelation: N_eff = N * (1 - rho1) / (1 + rho1), rho1 clipped ≥ 0
      * overlap: if holding windows overlap, count concurrent trades and divide
        N by the average concurrency.
    Falls back to raw N when timestamps are unavailable.
    """
    n = len(pnl)
    if n < 3:
        return float(n)

    # autocorrelation deflator
    x = pnl.to_numpy(float)
    x = x - x.mean()
    denom = np.sum(x * x)
    rho1 = float(np.sum(x[1:] * x[:-1]) / denom) if denom > 0 else 0.0
    rho1 = min(max(rho1, 0.0), 0.999)
    n_ac = n * (1 - rho1) / (1 + rho1)

    # overlap deflator
    n_ov = n
    if entry_ts is not None and exit_ts is not None:
        e = pd.to_datetime(entry_ts).to_numpy()
        x_ = pd.to_datetime(exit_ts).to_numpy()
        order = np.argsort(e)
        e, x_ = e[order], x_[order]
        # average number of trades open when each trade opens
        concurrency = np.array([np.sum((e <= e[i]) & (x_ > e[i])) for i in range(n)])
        avg_conc = concurrency.mean()
        if avg_conc > 1:
            n_ov = n / avg_conc

    return float(min(n_ac, n_ov, n))


def compute_metrics(trade_log: pd.DataFrame, equity_curve: pd.DataFrame | None = None,
                    pnl_col: str = "net_pnl") -> Metrics:
    """Compute all metrics from a trade log (+ optional equity curve)."""
    if trade_log is None or trade_log.empty:
        return Metrics(*([0] * 4 + [0.0] * 14))

    pnl = trade_log[pnl_col].astype(float)
    n = len(pnl)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    win_rate = len(wins) / n
    loss_rate = len(losses) / n
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(-losses.mean()) if len(losses) else 0.0  # positive magnitude
    expectancy = win_rate * avg_win - loss_rate * avg_loss

    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf

    # per-trade return stats
    std = float(pnl.std(ddof=1)) if n > 1 else 0.0
    sharpe = (float(pnl.mean()) / std * np.sqrt(TRADING_PERIODS_PER_YEAR)
              if std > 0 else 0.0)
    downside = pnl[pnl < 0]
    dstd = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else 0.0
    sortino = (float(pnl.mean()) / dstd * np.sqrt(TRADING_PERIODS_PER_YEAR)
               if dstd > 0 else (np.inf if pnl.mean() > 0 else 0.0))

    # drawdown from the equity curve (or the cumulative trade P&L)
    if equity_curve is not None and not equity_curve.empty:
        eq = equity_curve["equity"].astype(float)
    else:
        eq = pnl.cumsum()
    max_dd = _max_drawdown_fraction(eq)
    calmar = (expectancy / max_dd) if max_dd > 0 else (np.inf if expectancy > 0 else 0.0)

    # worst day from equity curve timestamps if present
    worst_day = float(pnl.min())
    if equity_curve is not None and "ts" in equity_curve.columns and not equity_curve.empty:
        daily = equity_curve.assign(
            day=pd.to_datetime(equity_curve["ts"]).dt.tz_convert("UTC").dt.date
        ).groupby("day")["equity"].last().diff().dropna()
        if len(daily):
            worst_day = float(daily.min())

    eff_n = _effective_n(pnl, trade_log.get("entry_ts"), trade_log.get("exit_ts"))

    return Metrics(
        n_trades=n, effective_n=round(eff_n, 1),
        win_rate=round(win_rate, 4), loss_rate=round(loss_rate, 4),
        avg_win=round(avg_win, 4), avg_loss=round(avg_loss, 4),
        expectancy=round(expectancy, 4), profit_factor=round(profit_factor, 3),
        total_pnl=round(float(pnl.sum()), 4), avg_trade=round(float(pnl.mean()), 4),
        worst_trade=round(float(pnl.min()), 4), best_trade=round(float(pnl.max()), 4),
        return_skew=round(float(pnl.skew()) if n > 2 else 0.0, 4),
        sharpe=round(sharpe, 3), sortino=round(sortino, 3), calmar=round(calmar, 3),
        max_drawdown=round(max_dd, 4), worst_day=round(worst_day, 4),
    )


def per_trade_returns(trade_log: pd.DataFrame) -> np.ndarray:
    """Per-trade return = net P&L / capital at risk (entry premium × mult × size).

    For long premium the capital at risk is the premium paid, so this is a
    clean fractional return for Sharpe-based stats (stats.py). Falls back to
    net_pnl if entry fields are missing.
    """
    if trade_log is None or trade_log.empty:
        return np.array([])
    if {"entry_fill", "contracts"}.issubset(trade_log.columns):
        capital = (trade_log["entry_fill"].astype(float)
                   * trade_log["contracts"].astype(float) * 100.0)
        capital = capital.replace(0, np.nan)
        r = (trade_log["net_pnl"].astype(float) / capital)
        return r.to_numpy(float)
    return trade_log["net_pnl"].astype(float).to_numpy()


def _max_drawdown_fraction(equity: pd.Series) -> float:
    """Max peak-to-trough drawdown as a positive fraction of the peak.

    Equity here is cumulative P&L (may start at 0), so normalize by an assumed
    starting capital baseline = the running peak, guarding the 0 case.
    """
    eq = equity.to_numpy(float)
    if eq.size == 0:
        return 0.0
    # shift so the curve represents account value; assume unit starting capital
    # of max(1, |min|) to avoid divide-by-zero when the curve crosses zero.
    base = max(1.0, float(np.abs(eq).max()))
    value = base + eq
    running_max = np.maximum.accumulate(value)
    dd = (running_max - value) / running_max
    return float(np.max(dd)) if dd.size else 0.0


@dataclass
class ObjectiveResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed


def passes_objective(m: Metrics,
                     max_drawdown_ceiling: float = MAX_DRAWDOWN_CEILING,
                     min_effective_trades: int = MIN_EFFECTIVE_TRADES,
                     min_expectancy: float = MIN_EXPECTANCY,
                     require_non_negative_skew: bool = True) -> ObjectiveResult:
    """The frozen objective gate (ROADMAP §1). All constraints must hold.

    Returns a bool-like result carrying the reasons each constraint passed or
    failed, so a result is never silently accepted.
    """
    reasons = []
    ok = True

    if m.expectancy > min_expectancy:
        reasons.append(f"PASS expectancy {m.expectancy:.4f} > {min_expectancy}")
    else:
        ok = False
        reasons.append(f"FAIL expectancy {m.expectancy:.4f} <= {min_expectancy}")

    if m.max_drawdown <= max_drawdown_ceiling:
        reasons.append(f"PASS max_drawdown {m.max_drawdown:.2%} <= {max_drawdown_ceiling:.0%}")
    else:
        ok = False
        reasons.append(f"FAIL max_drawdown {m.max_drawdown:.2%} > {max_drawdown_ceiling:.0%}")

    if m.effective_n >= min_effective_trades:
        reasons.append(f"PASS effective_n {m.effective_n} >= {min_effective_trades}")
    else:
        ok = False
        reasons.append(f"FAIL effective_n {m.effective_n} < {min_effective_trades} "
                       f"(raw n={m.n_trades})")

    # Negative-skew "win small, blow up" check: the strategy must not rely on a
    # heavy negative tail (ROADMAP §1 skew/tail check).
    if require_non_negative_skew:
        if m.return_skew >= 0:
            reasons.append(f"PASS return_skew {m.return_skew:.2f} >= 0")
        else:
            ok = False
            reasons.append(f"FAIL return_skew {m.return_skew:.2f} < 0 "
                           f"(negative-skew profile; worst_trade={m.worst_trade})")

    return ObjectiveResult(passed=ok, reasons=reasons)
