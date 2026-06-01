"""Always-on cost model (ROADMAP §5, §11).

Costs are MANDATORY and never disabled to improve a result. Three components:

  1. Commission — per contract per side (default $0.65).
  2. Spread — fills happen at the WORSE side of a *modeled* spread, never the
     mid. With no historical quotes (ROADMAP §2a) the spread must be modeled
     from moneyness/DTE/price; `spread_mult` is a first-class swept parameter,
     and any edge that survives only the optimistic end of the sweep is dead.
  3. Slippage on stops — a triggered stop becomes a MARKET order with a poor,
     fat-tailed fill in thin options (extra spread fractions beyond the model).

`spread_fraction` returns the modeled full bid-ask spread as a fraction of
option price; half of it is paid on each side. The model widens for low price,
low DTE, and far-from-money contracts — all empirically wider markets.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CostModel:
    commission_per_contract: float = 0.65
    base_spread_frac: float = 0.04     # 4% of price for a liquid ATM weekly
    min_spread_dollars: float = 0.02   # at least 2 cents wide
    spread_mult: float = 1.0           # SWEEP THIS (pessimism multiplier)
    stop_slippage_extra_frac: float = 0.5  # mean extra half-spreads on a stop
    stop_slippage_tail_frac: float = 1.0   # fat-tail add (×|N(0,1)| clipped)
    contract_multiplier: int = 100

    def spread_fraction(self, price, dte_days, moneyness_abs):
        """Modeled full spread as a fraction of option price (vectorized-safe).

        Built as base_spread_frac × a dimensionless widening factor (≥1) for
        cheap / low-DTE / far-OTM contracts, all × spread_mult. So base=0 gives
        a zero spread (the frictionless model), and widening is relative.
        """
        price = np.asarray(price, float)
        dte = np.asarray(dte_days, float)
        mny = np.asarray(moneyness_abs, float)
        cheap = np.clip(1.0 / np.maximum(price, 0.05), 0.0, 8.0) * 0.75
        dte_w = np.where(dte <= 0, 1.0, 0.75 / np.sqrt(np.maximum(dte, 1.0)))
        otm_w = np.minimum(mny, 0.2) * 12.5
        widen = 1.0 + cheap + dte_w + otm_w
        frac = self.base_spread_frac * widen * self.spread_mult
        return np.clip(frac, 0.0, 1.5)

    def half_spread_dollars(self, price, dte_days, moneyness_abs):
        """Dollar cost of crossing half the spread (per contract, 1 unit)."""
        price = np.asarray(price, float)
        frac = self.spread_fraction(price, dte_days, moneyness_abs)
        dollars = 0.5 * frac * price
        return np.maximum(dollars, 0.5 * self.min_spread_dollars)

    def entry_fill(self, mid_price, dte_days, moneyness_abs, side):
        """Fill price entering: pay half-spread on the worse side.

        side: +1 long (buy, fill above mid), -1 short (sell, fill below mid).
        """
        hs = self.half_spread_dollars(mid_price, dte_days, moneyness_abs)
        return np.asarray(mid_price, float) + side * hs

    def exit_fill(self, mid_price, dte_days, moneyness_abs, side, is_stop=False, rng=None):
        """Fill price exiting a position of direction `side`.

        Exiting a long means selling (fill below mid); exiting a short means
        buying (fill above mid). A stop adds fat-tailed extra slippage.
        """
        hs = self.half_spread_dollars(mid_price, dte_days, moneyness_abs)
        slip = np.zeros_like(np.asarray(mid_price, float))
        if is_stop:
            tail = 0.0
            if rng is not None:
                tail = self.stop_slippage_tail_frac * abs(float(rng.standard_normal()))
            slip = hs * (self.stop_slippage_extra_frac + tail)
        # exiting reverses side: a long sells (-), a short buys (+)
        return np.asarray(mid_price, float) - side * (hs + slip)

    def commission(self, contracts: int) -> float:
        return self.commission_per_contract * abs(contracts)

    @classmethod
    def zero(cls) -> "CostModel":
        """A frictionless model — for tests/invariant checks ONLY, never a run.

        Production runs must keep costs on (ROADMAP §11); this exists so a test
        can isolate the engine's mechanics from the cost arithmetic.
        """
        return cls(commission_per_contract=0.0, base_spread_frac=0.0,
                   min_spread_dollars=0.0, stop_slippage_extra_frac=0.0,
                   stop_slippage_tail_frac=0.0)
