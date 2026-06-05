"""Monte-Carlo stress test of the CI crash-dodge on SYNTHETIC crash paths.

WHY THIS EXISTS
  Every real backtest in this project lives in ONE benign decade (2016-2026) plus
  ONE hand-constructed dot-com splice. That is a single draw from the distribution
  of possible futures, and the crash-dodge is the weakest-tested, non-DSR-significant
  piece of the whole plan. The honest way to ask "does the dodge survive crashes I
  haven't seen?" is to generate THOUSANDS of crashes with known, varied shapes and
  watch the dodge in each.

WHAT IT DOES
  1. Generate N synthetic S&P daily-return paths, EACH guaranteed to contain a crash,
     drawn from 5 heuristic crash ARCHETYPES with randomized parameters:
        vcrash   - clean V (COVID-like): one fast deep drop, sharp recovery
        flash    - flash crash: very fast shallow drop, near-immediate snap-back
        waterfall- 2008-like: steep multi-month decline w/ violent counter-rallies
        choppy   - dot-com-like: long saw-tooth grind-down (down-leg, bear rally, repeat)
        grind    - stagnation: long low-drift chop w/ an embedded drop (vol-decay killer)
  2. Map each index path to a SYNTHETIC 3x DAILY-RESET fund (UPRO). Volatility decay
     and the amplified drawdown fall out automatically from compounding 3x of the
     daily simple return (this IS the mechanism the broker warning is about).
  3. Run the plan's EXACT crash-dodge (equity._crash_exposure_path, 90d / 2.0 sigma /
     8 steps, cliff_sell + avg_down) vs plain buy-and-hold of the same synthetic fund.
  4. Report, OVERALL and BY ARCHETYPE: win rate, median out/under-performance,
     drawdown reduction, and LEFT-TAIL (ruin) protection -- the metrics that decide
     whether the dodge is real protection or just whipsaw.

NOT A PREDICTION. The archetypes are heuristics, not a fitted model of the market;
the leverage drag is a parameter. The value is RELATIVE and CONDITIONAL: across many
crash shapes, WHEN does the dodge help and when does it bleed, and by how much.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .equity import _crash_exposure_path

TRADING_DAYS = 252

# Daily simple-return clamps. Index circuit breakers halt at -20%; cap a touch wider
# so the synthetic never produces a single-day move that would mathematically wipe a
# 3x fund (3 * -0.22 = -0.66, survivable; a -0.34 day would not be).
IDX_RET_FLOOR, IDX_RET_CEIL = -0.22, 0.18

ARCHETYPES = ("vcrash", "flash", "waterfall", "choppy", "grind")
DEFAULT_WEIGHTS = {"vcrash": 0.25, "flash": 0.15, "waterfall": 0.20,
                   "choppy": 0.25, "grind": 0.15}


# ------------------------------------------------------------------ path pieces
def _t_noise(rng, n, scale, nu=5.0):
    """Student-t innovations (fat tails, real markets have kurtosis), rescaled to
    unit variance then to `scale` (a daily std). nu=5 -> finite variance, fat-ish."""
    z = rng.standard_t(nu, size=n)
    z /= np.sqrt(nu / (nu - 2.0))          # unit variance
    return z * scale


def _calm_segment(rng, n, mu_annual, vol_annual, nu=6.0):
    """A 'normal market' stretch as daily LOG returns: small drift + fat-tail noise."""
    if n <= 0:
        return np.empty(0)
    mu_d = mu_annual / TRADING_DAYS
    vol_d = vol_annual / np.sqrt(TRADING_DAYS)
    return mu_d + _t_noise(rng, n, vol_d, nu)


def _drop_phase(rng, total_drop, n_days, vol_annual, nu=5.0):
    """A declining stretch: daily LOG returns that sum (in expectation) to
    ln(1-total_drop) over n_days, with daily noise of `vol_annual`."""
    n_days = max(1, int(n_days))
    target = np.log(max(1e-6, 1.0 - total_drop))
    mu_d = target / n_days
    vol_d = vol_annual / np.sqrt(TRADING_DAYS)
    return mu_d + _t_noise(rng, n_days, vol_d, nu)


def _rise_phase(rng, total_gain, n_days, vol_annual, nu=5.0):
    """A recovering stretch: daily LOG returns summing (in expectation) to
    ln(1+total_gain) over n_days, with noise."""
    n_days = max(1, int(n_days))
    target = np.log(max(1e-6, 1.0 + total_gain))
    mu_d = target / n_days
    vol_d = vol_annual / np.sqrt(TRADING_DAYS)
    return mu_d + _t_noise(rng, n_days, vol_d, nu)


# ------------------------------------------------------------------ crash archetypes
# Each returns an array of daily LOG returns describing ONLY the crash (+ its own
# recovery where applicable). The caller wraps it with a calm pre-segment and a
# calm post-segment so every path is: bull -> CRASH -> continuation.

def _crash_vcrash(rng):
    """Clean V (COVID-like): one fast deep drop then a sharp recovery."""
    D = rng.uniform(0.28, 0.40)
    t_down = rng.integers(15, 36)
    vol = rng.uniform(0.40, 0.70)
    rec = rng.uniform(0.75, 1.05)               # fraction of the drop regained
    t_up = rng.integers(50, 160)
    down = _drop_phase(rng, D, t_down, vol)
    gain = (1.0 / (1.0 - D)) - 1.0              # gain needed to fully retrace
    up = _rise_phase(rng, gain * rec, t_up, vol * 0.7)
    return np.concatenate([down, up])


def _crash_flash(rng):
    """Flash crash: very fast shallow drop, near-immediate snap-back."""
    D = rng.uniform(0.10, 0.20)
    t_down = rng.integers(3, 12)
    vol = rng.uniform(0.45, 0.85)
    t_up = rng.integers(10, 45)
    down = _drop_phase(rng, D, t_down, vol)
    gain = (1.0 / (1.0 - D)) - 1.0
    up = _rise_phase(rng, gain * rng.uniform(0.90, 1.05), t_up, vol * 0.6)
    return np.concatenate([down, up])


def _crash_waterfall(rng):
    """2008-like: steep multi-month decline punctuated by violent counter-rallies,
    then a slow partial recovery."""
    D = rng.uniform(0.45, 0.57)
    t_down = int(rng.integers(160, 300))
    vol = rng.uniform(0.45, 0.70)
    # break the decline into 3-4 legs separated by sharp bear rallies
    n_legs = int(rng.integers(3, 5))
    pieces = []
    remaining = D
    for k in range(n_legs):
        leg_drop = remaining * rng.uniform(0.35, 0.6) if k < n_legs - 1 else remaining
        remaining -= leg_drop
        seg_len = max(8, int(t_down / n_legs))
        pieces.append(_drop_phase(rng, leg_drop, seg_len, vol))
        if k < n_legs - 1:                      # a violent bear-market rally
            pieces.append(_rise_phase(rng, rng.uniform(0.08, 0.22),
                                      int(rng.integers(8, 25)), vol))
    # slow partial recovery
    cum = float(np.exp(np.sum(np.concatenate(pieces))))   # ending level vs 1.0
    full = 1.0 / cum - 1.0
    pieces.append(_rise_phase(rng, full * rng.uniform(0.5, 0.9),
                              int(rng.integers(180, 420)), vol * 0.7))
    return np.concatenate(pieces)


def _crash_choppy(rng):
    """Dot-com-like: a long saw-tooth grind-down -- down-leg, partial bear rally,
    repeat -- ending well below the start. The classic whipsaw machine."""
    D = rng.uniform(0.40, 0.55)
    n_cycles = int(rng.integers(5, 10))
    vol = rng.uniform(0.32, 0.52)
    pieces = []
    remaining = D
    for k in range(n_cycles):
        leg = remaining * rng.uniform(0.3, 0.55) if k < n_cycles - 1 else remaining
        remaining = max(0.0, remaining - leg)
        pieces.append(_drop_phase(rng, leg, int(rng.integers(25, 60)), vol))
        # a bear-market rally that retraces part of THIS leg (the whipsaw bait)
        if k < n_cycles - 1:
            rally = (1.0 / (1.0 - leg) - 1.0) * rng.uniform(0.35, 0.75)
            pieces.append(_rise_phase(rng, rally, int(rng.integers(20, 50)), vol * 0.85))
    return np.concatenate(pieces)


def _crash_grind(rng):
    """Stagnation/vol-decay killer: a long low-drift, choppy market with an embedded
    moderate drop and only weak recovery. Net mildly down, lots of churn -- the
    regime where 3x daily-reset funds bleed the most even though the index goes ~nowhere."""
    D = rng.uniform(0.20, 0.38)
    t = int(rng.integers(250, 500))
    vol = rng.uniform(0.22, 0.34)
    # embed the drop in the FIRST ~40-60% of the window, then sideways chop
    t_drop = int(t * rng.uniform(0.4, 0.6))
    down = _drop_phase(rng, D, t_drop, vol)
    side = _rise_phase(rng, D * rng.uniform(0.1, 0.4), t - t_drop, vol)   # weak partial recovery
    return np.concatenate([down, side])


_CRASH_FN = {"vcrash": _crash_vcrash, "flash": _crash_flash,
             "waterfall": _crash_waterfall, "choppy": _crash_choppy,
             "grind": _crash_grind}


# ------------------------------------------------------------------ full path
@dataclass
class MCConfig:
    n_paths: int = 3000
    n_days: int = 1260                 # ~5 trading years -> room for long bears + recovery
    leverage: float = 3.0              # UPRO
    lev_expense_annual: float = 0.0092 # UPRO expense ratio
    lev_financing_annual: float = 0.03 # cost of the 2x borrowed notional (rate*~(L-1))
    cash_yield_annual: float = 0.0     # yield on the dodged-to-cash sleeve (0 = conservative)
    ci_lookback: int = 90
    crash_sigma: float = 2.0
    n_increments: int = 8
    cost_bps: float = 5.0
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    seed: int = 12345

    @property
    def lev_drag_daily(self) -> float:
        # expense + financing on the borrowed (leverage-1) notional, per day
        ann = self.lev_expense_annual + self.lev_financing_annual * (self.leverage - 1.0)
        return ann / TRADING_DAYS


def _make_index_path(rng, cfg: MCConfig, archetype: str) -> np.ndarray:
    """One full index price path (starts at 1.0) guaranteed to contain `archetype`'s
    crash, framed by a calm bull pre-segment and a calm continuation post-segment."""
    crash = _CRASH_FN[archetype](rng)
    Lc = len(crash)
    # pre needs >= ci_lookback for warmup; leave >= 60d of post so recovery can register
    max_pre = cfg.n_days - Lc - 60
    lo_pre = max(cfg.ci_lookback + 20, 120)
    if max_pre <= lo_pre:                       # very long crash -> shrink pre to fit
        pre_n = max(cfg.ci_lookback + 10, min(max_pre, lo_pre))
        pre_n = max(pre_n, cfg.ci_lookback + 5)
    else:
        pre_n = int(rng.integers(lo_pre, max_pre))
    pre = _calm_segment(rng, pre_n, rng.uniform(0.06, 0.16), rng.uniform(0.11, 0.16))
    post_n = max(0, cfg.n_days - pre_n - Lc)
    post = _calm_segment(rng, post_n, rng.uniform(0.05, 0.14), rng.uniform(0.11, 0.17))

    logret = np.concatenate([pre, crash, post])
    # convert to simple, clamp daily moves, rebuild a clean price
    simple = np.expm1(logret)
    simple = np.clip(simple, IDX_RET_FLOOR, IDX_RET_CEIL)
    px = np.empty(len(simple) + 1)
    px[0] = 1.0
    px[1:] = np.cumprod(1.0 + simple)
    return px


def _synth_leveraged(idx_px: np.ndarray, cfg: MCConfig) -> np.ndarray:
    """Map an index price path to a synthetic L-x DAILY-RESET fund. The fund earns
    L * (daily index simple return) minus a daily drag, compounded -- so volatility
    decay and amplified drawdown emerge from the compounding, not an assumption."""
    idx_ret = idx_px[1:] / idx_px[:-1] - 1.0
    lev_ret = cfg.leverage * idx_ret - cfg.lev_drag_daily
    lev_ret = np.maximum(lev_ret, -0.95)        # a fund can't lose >100% in a day
    px = np.empty(len(lev_ret) + 1)
    px[0] = 1.0
    px[1:] = np.cumprod(1.0 + lev_ret)
    return px


def _max_drawdown(px: np.ndarray) -> float:
    peak = np.maximum.accumulate(px)
    return float(np.max((peak - px) / peak))


def _dodge_vs_hold(lev_px: np.ndarray, cfg: MCConfig, ci_lookback: int | None = None) -> dict:
    """Run the plan's exact crash-dodge on a synthetic leveraged price path vs
    buy-and-hold of the same path. Returns terminal wealth + drawdown for each.
    `ci_lookback` overrides cfg.ci_lookback (for the lookback sweep)."""
    lb = cfg.ci_lookback if ci_lookback is None else ci_lookback
    s = pd.Series(lev_px)
    exp = _crash_exposure_path(s, lb, cfg.crash_sigma,
                               cfg.n_increments, "cliff_sell", "avg_down")
    exp_eff = np.empty_like(exp)
    exp_eff[0] = 1.0
    exp_eff[1:] = exp[:-1]                       # decision at close t acts on t+1
    lev_ret = lev_px[1:] / lev_px[:-1] - 1.0
    cash_ret = cfg.cash_yield_annual / TRADING_DAYS
    e = exp_eff[1:]                              # exposure earning today's return
    turnover = np.abs(np.diff(exp_eff))
    strat_ret = e * lev_ret + (1.0 - e) * cash_ret - (cfg.cost_bps / 1e4) * turnover
    dodge_px = np.empty(len(strat_ret) + 1)
    dodge_px[0] = 1.0
    dodge_px[1:] = np.cumprod(1.0 + strat_ret)
    return {
        "hold_final": float(lev_px[-1]),
        "dodge_final": float(dodge_px[-1]),
        "hold_maxdd": _max_drawdown(lev_px),
        "dodge_maxdd": _max_drawdown(dodge_px),
        "pct_invested": float(np.mean(exp_eff)),
    }


# ------------------------------------------------------------------ driver
def run_mc(cfg: MCConfig, progress_every: int = 500) -> pd.DataFrame:
    """Simulate cfg.n_paths crash paths; return one row per path."""
    rng = np.random.default_rng(cfg.seed)
    arche = list(cfg.weights.keys())
    probs = np.array([cfg.weights[a] for a in arche], float)
    probs /= probs.sum()

    rows = []
    for i in range(cfg.n_paths):
        a = arche[rng.choice(len(arche), p=probs)]
        idx_px = _make_index_path(rng, cfg, a)
        lev_px = _synth_leveraged(idx_px, cfg)
        r = _dodge_vs_hold(lev_px, cfg)
        r["archetype"] = a
        r["idx_final"] = float(idx_px[-1])
        r["idx_maxdd"] = _max_drawdown(idx_px)
        rows.append(r)
        if progress_every and (i + 1) % progress_every == 0:
            print(f"  {i + 1}/{cfg.n_paths} paths simulated", flush=True)
    df = pd.DataFrame(rows)
    df["dodge_minus_hold"] = df["dodge_final"] / df["hold_final"] - 1.0
    df["dd_reduction"] = df["hold_maxdd"] - df["dodge_maxdd"]
    df["dodge_wins"] = df["dodge_final"] > df["hold_final"]
    return df


def _block(df: pd.DataFrame) -> dict:
    """Summary stats for a slice of paths."""
    n = len(df)
    return {
        "n": n,
        "win_rate": float(df["dodge_wins"].mean()),
        "med_rel": float(df["dodge_minus_hold"].median()),
        "mean_rel": float(df["dodge_minus_hold"].mean()),
        "dd_help_rate": float((df["dd_reduction"] > 0).mean()),
        "med_dd_red": float(df["dd_reduction"].median()),
        "hold_med": float(df["hold_final"].median()),
        "dodge_med": float(df["dodge_final"].median()),
        "hold_p05": float(df["hold_final"].quantile(0.05)),
        "dodge_p05": float(df["dodge_final"].quantile(0.05)),
        "hold_ddmed": float(df["hold_maxdd"].median()),
        "dodge_ddmed": float(df["dodge_maxdd"].median()),
        "pct_inv": float(df["pct_invested"].mean()),
    }


def summarize(df: pd.DataFrame, cfg: MCConfig) -> None:
    yrs = cfg.n_days / TRADING_DAYS
    print(f"\n{'='*100}")
    print(f"MONTE-CARLO CRASH STRESS TEST  -  {len(df):,} paths x {cfg.n_days}d (~{yrs:.1f}y), "
          f"each with a guaranteed crash")
    print(f"Synthetic {cfg.leverage:.0f}x daily-reset fund (drag {cfg.lev_drag_daily*TRADING_DAYS*100:.2f}%/yr), "
          f"dodge = {cfg.ci_lookback}d / {cfg.crash_sigma}sigma / {cfg.n_increments} steps, "
          f"cash yield {cfg.cash_yield_annual*100:.1f}%/yr")
    print('='*100)

    # ---- per-archetype table (the conditional answer: WHEN does the dodge help?)
    print("\nBY CRASH ARCHETYPE  (terminal wealth of $1; 'rel' = dodge/hold - 1):")
    print(f"  {'archetype':>10} {'n':>5} {'%inv':>5} | {'dodge wins':>10} {'med rel':>8} "
          f"| {'holdMedDD':>9} {'dodgeMedDD':>10} {'ddHelp%':>8} "
          f"| {'hold p05$':>9} {'dodge p05$':>10}")
    label = {"vcrash": "vcrash(V)", "flash": "flash", "waterfall": "waterfall",
             "choppy": "choppy", "grind": "grind"}
    for a in ARCHETYPES:
        sub = df[df["archetype"] == a]
        if sub.empty:
            continue
        b = _block(sub)
        print(f"  {label[a]:>10} {b['n']:5d} {b['pct_inv']*100:4.0f}% | "
              f"{b['win_rate']*100:9.0f}% {b['med_rel']*100:+7.1f}% | "
              f"{b['hold_ddmed']*100:8.0f}% {b['dodge_ddmed']*100:9.0f}% {b['dd_help_rate']*100:7.0f}% | "
              f"{b['hold_p05']:9.2f} {b['dodge_p05']:10.2f}")

    # ---- overall
    o = _block(df)
    print(f"\nOVERALL  (weighted mix; per-archetype above is the unbiased read):")
    print(f"  dodge beats hold in {o['win_rate']*100:.0f}% of crash paths; "
          f"median dodge/hold = {o['med_rel']*100:+.1f}%")
    print(f"  median max-drawdown:  hold {o['hold_ddmed']*100:.0f}%  ->  dodge {o['dodge_ddmed']*100:.0f}%  "
          f"(dodge cut the drawdown in {o['dd_help_rate']*100:.0f}% of paths)")
    print(f"  median terminal $1:   hold ${o['hold_med']:.2f}   dodge ${o['dodge_med']:.2f}")
    print(f"  LEFT-TAIL 5th-pctile: hold ${o['hold_p05']:.2f}   dodge ${o['dodge_p05']:.2f}   "
          f"<- the 'did it save the bad case' number")

    # ---- ruin protection: of the paths where HOLD is a disaster, how often is the dodge better?
    disaster = df[df["hold_final"] < 0.50]       # buy-and-hold lost >= half
    if len(disaster):
        saved = (disaster["dodge_final"] > disaster["hold_final"]).mean()
        big = (disaster["dodge_final"] > 2 * disaster["hold_final"]).mean()
        print(f"\nRUIN CASES (hold lost >=50%): {len(disaster):,} paths "
              f"({len(disaster)/len(df)*100:.0f}% of all).")
        print(f"  dodge ended ABOVE hold in {saved*100:.0f}% of them; "
              f"ended >2x hold in {big*100:.0f}%.")
        print(f"  median terminal in ruin cases: hold ${disaster['hold_final'].median():.2f}  "
              f"-> dodge ${disaster['dodge_final'].median():.2f}")

    # ---- the whipsaw cost: where the dodge HURTS
    hurt = df[df["dodge_minus_hold"] < -0.05]
    if len(hurt):
        worst_arch = hurt["archetype"].value_counts(normalize=True)
        top = ", ".join(f"{k} {v*100:.0f}%" for k, v in worst_arch.head(3).items())
        print(f"\nWHIPSAW COST: dodge lagged hold by >5% in {len(hurt)/len(df)*100:.0f}% of paths; "
              f"those are mostly: {top}")
    print('='*100)


# ------------------------------------------------------------------ lookback sweep
def run_mc_sweep(cfg: MCConfig, lookbacks: list[int], progress_every: int = 500) -> pd.DataFrame:
    """Same as run_mc, but evaluate the dodge at EVERY lookback on the SAME path
    (same RNG draw) -- so differences are purely the lookback, not path luck. One
    row per (path, lookback). Buy-and-hold is identical across lookbacks."""
    rng = np.random.default_rng(cfg.seed)
    arche = list(cfg.weights.keys())
    probs = np.array([cfg.weights[a] for a in arche], float)
    probs /= probs.sum()

    rows = []
    for i in range(cfg.n_paths):
        a = arche[rng.choice(len(arche), p=probs)]
        idx_px = _make_index_path(rng, cfg, a)
        lev_px = _synth_leveraged(idx_px, cfg)
        for lb in lookbacks:
            r = _dodge_vs_hold(lev_px, cfg, ci_lookback=lb)
            r["archetype"] = a
            r["lookback"] = lb
            rows.append(r)
        if progress_every and (i + 1) % progress_every == 0:
            print(f"  {i + 1}/{cfg.n_paths} paths x {len(lookbacks)} lookbacks", flush=True)
    df = pd.DataFrame(rows)
    df["dodge_minus_hold"] = df["dodge_final"] / df["hold_final"] - 1.0
    df["dd_reduction"] = df["hold_maxdd"] - df["dodge_maxdd"]
    df["dodge_wins"] = df["dodge_final"] > df["hold_final"]
    return df


def summarize_sweep(df: pd.DataFrame, cfg: MCConfig, lookbacks: list[int]) -> None:
    yrs = cfg.n_days / TRADING_DAYS
    n_paths = len(df) // len(lookbacks)
    print(f"\n{'='*100}")
    print(f"CI LOOKBACK SWEEP  -  {n_paths:,} crash paths x {cfg.n_days}d (~{yrs:.1f}y), "
          f"every lookback on the SAME paths")
    print(f"Synthetic {cfg.leverage:.0f}x daily-reset fund, dodge = LB / {cfg.crash_sigma}sigma / "
          f"{cfg.n_increments} steps")
    print('='*100)

    # ---- overall, per lookback (the robustness read)
    print("\nOVERALL, per lookback (terminal wealth of $1; 'rel' = dodge/hold - 1):")
    print(f"  {'lookback':>8} {'%inv':>5} {'dodge wins':>10} {'med rel':>8} {'mean rel':>8} "
          f"{'dodgeMedDD':>10} {'ddHelp%':>8} {'dodge p05$':>10} {'whipsaw>5%':>10}")
    overall = {}
    for lb in lookbacks:
        sub = df[df["lookback"] == lb]
        b = _block(sub)
        whip = float((sub["dodge_minus_hold"] < -0.05).mean())
        overall[lb] = (b, whip)
        print(f"  {lb:8d} {b['pct_inv']*100:4.0f}% {b['win_rate']*100:9.0f}% "
              f"{b['med_rel']*100:+7.1f}% {b['mean_rel']*100:+7.1f}% "
              f"{b['dodge_ddmed']*100:9.0f}% {b['dd_help_rate']*100:7.0f}% "
              f"{b['dodge_p05']:10.2f} {whip*100:9.0f}%")
    hold_b = _block(df[df["lookback"] == lookbacks[0]])   # hold identical across LBs
    print(f"  (buy-and-hold reference: medDD {hold_b['hold_ddmed']*100:.0f}%, "
          f"p05 ${hold_b['hold_p05']:.2f}, median ${hold_b['hold_med']:.2f})")

    # ---- median rel by archetype x lookback (does the regime want a different LB?)
    print("\nMEDIAN dodge/hold - 1, by ARCHETYPE x LOOKBACK  (best lookback per row marked *):")
    header = "  " + f"{'archetype':>10} " + " ".join(f"{('LB'+str(lb)):>8}" for lb in lookbacks)
    print(header)
    for a in ARCHETYPES:
        sa = df[df["archetype"] == a]
        if sa.empty:
            continue
        vals = {lb: float(sa[sa["lookback"] == lb]["dodge_minus_hold"].median()) for lb in lookbacks}
        best = max(vals, key=vals.get)
        cells = " ".join(f"{(('%+.1f' % (vals[lb]*100)) + ('*' if lb == best else ' ')):>8}" for lb in lookbacks)
        print(f"  {a:>10} {cells}")

    # ---- drawdown reduction by archetype x lookback
    print("\nMEDIAN drawdown REDUCTION (hold maxDD - dodge maxDD), by ARCHETYPE x LOOKBACK:")
    print(header)
    for a in ARCHETYPES:
        sa = df[df["archetype"] == a]
        if sa.empty:
            continue
        vals = {lb: float(sa[sa["lookback"] == lb]["dd_reduction"].median()) for lb in lookbacks}
        best = max(vals, key=vals.get)
        cells = " ".join(f"{(('%+.1f' % (vals[lb]*100)) + ('*' if lb == best else ' ')):>8}" for lb in lookbacks)
        print(f"  {a:>10} {cells}")

    # ---- pick the most robust: best worst-case (max-min across archetypes) on median rel
    print("\nROBUSTNESS (which lookback is least bad in its WORST archetype):")
    for lb in lookbacks:
        per_arch = [float(df[(df["lookback"] == lb) & (df["archetype"] == a)]["dodge_minus_hold"].median())
                    for a in ARCHETYPES if (df["archetype"] == a).any()]
        print(f"  LB{lb:>3}: worst-archetype median rel = {min(per_arch)*100:+.1f}%, "
              f"avg-archetype = {np.mean(per_arch)*100:+.1f}%")
    print('='*100)
