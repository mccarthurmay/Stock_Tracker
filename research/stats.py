"""Multiple-testing statistics (ROADMAP §6.5).

The whole point of this module: a Sharpe ratio that looks good is meaningless
until it is deflated by *how many configurations were tried to find it*. The N
that drives the deflation is the distinct-config count from the `config_runs`
ledger (ROADMAP §4) — NOT the number of registered hypotheses, which would be
anti-conservative (the garden of forking paths).

Implements:
  * probabilistic_sharpe_ratio (PSR) — Bailey & López de Prado
  * expected_max_sharpe — E[max Sharpe] of N independent zero-skill trials
  * deflated_sharpe_ratio (DSR) — PSR against that data-mined benchmark
  * whites_reality_check — stationary block-bootstrap p-value for "best of N"

These reduce, but do not eliminate, false-discovery risk under clustered,
non-stationary intraday returns (ROADMAP §6.5 caveat). Treat them as a high
bar, not a proof.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm

EULER_MASCHERONI = 0.5772156649015329


def sharpe_stats(returns: np.ndarray) -> tuple[float, float, float]:
    """Return (sharpe, skew, excess_kurtosis) of a per-trade/return series."""
    r = np.asarray(returns, float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < 2:
        return 0.0, 0.0, 0.0
    mu = r.mean()
    sd = r.std(ddof=1)
    if sd == 0:
        return 0.0, 0.0, 0.0
    sr = mu / sd
    m3 = np.mean(((r - mu) / sd) ** 3)
    m4 = np.mean(((r - mu) / sd) ** 4)
    return float(sr), float(m3), float(m4 - 3.0)


def probabilistic_sharpe_ratio(observed_sr: float, n: int, skew: float,
                               excess_kurtosis: float,
                               benchmark_sr: float = 0.0) -> float:
    """PSR: P(true SR > benchmark) given a non-normal return sample.

    Bailey & López de Prado (2012). `observed_sr` and `benchmark_sr` are in the
    SAME (per-period) units; n is the number of observations.
    """
    if n < 2:
        return 0.5
    var_term = 1.0 - skew * observed_sr + (excess_kurtosis - 1.0) / 4.0 * observed_sr ** 2
    if var_term <= 0 or not np.isfinite(var_term):
        # Non-normality estimate degenerate (typically tiny n with extreme
        # skew/kurtosis): fall back to the Gaussian SR variance, 1.
        var_term = 1.0
    z = (observed_sr - benchmark_sr) * np.sqrt(n - 1) / np.sqrt(var_term)
    return float(norm.cdf(z))


def expected_max_sharpe(n_trials: int, sr_std: float = 1.0) -> float:
    """E[max] of N independent N(0, sr_std^2) Sharpe estimates.

    Approximation (Bailey & López de Prado): sr_std * [ (1-γ)·Z⁻¹(1-1/N)
    + γ·Z⁻¹(1 - 1/(N·e)) ], γ = Euler-Mascheroni. This is the benchmark a
    data-mined "best" Sharpe must beat just by chance.
    """
    n = max(int(n_trials), 1)
    if n == 1:
        return 0.0
    g = EULER_MASCHERONI
    z1 = norm.ppf(1.0 - 1.0 / n)
    z2 = norm.ppf(1.0 - 1.0 / (n * np.e))
    return float(sr_std * ((1.0 - g) * z1 + g * z2))


def deflated_sharpe_ratio(observed_sr: float, returns: np.ndarray, n_trials: int,
                          sr_variance_across_trials: float | None = None) -> dict:
    """Deflated Sharpe Ratio: PSR against the expected-max-Sharpe benchmark.

    `observed_sr` is per-period (same units as sharpe_stats). `n_trials` is the
    distinct-config count (ROADMAP §4). If the variance of Sharpe across the
    trials isn't known, assume sr_std=1 (a standard conservative default).
    Returns the DSR (a probability) plus the benchmark it had to beat.
    """
    r = np.asarray(returns, float)
    r = r[np.isfinite(r)]
    n_obs = r.size
    _, skew, exk = sharpe_stats(r)
    sr_std = (np.sqrt(sr_variance_across_trials)
              if sr_variance_across_trials else 1.0)
    benchmark = expected_max_sharpe(n_trials, sr_std)
    dsr = probabilistic_sharpe_ratio(observed_sr, n_obs, skew, exk, benchmark)
    return {"dsr": dsr, "benchmark_sr": benchmark, "n_trials": n_trials,
            "n_obs": n_obs, "skew": skew, "excess_kurtosis": exk}


def _stationary_bootstrap_indices(n: int, avg_block: float,
                                  rng: np.random.Generator) -> np.ndarray:
    """Politis-Romano stationary bootstrap index sample of length n."""
    p = 1.0 / max(avg_block, 1.0)
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    for t in range(1, n):
        if rng.random() < p:
            idx[t] = rng.integers(n)
        else:
            idx[t] = (idx[t - 1] + 1) % n
    return idx


def whites_reality_check(candidate_returns: dict[str, np.ndarray],
                         n_boot: int = 2000, avg_block: float = 10.0,
                         seed: int = 0) -> dict:
    """White's Reality Check (Hansen-style) p-value for the best of N strategies.

    Null: no strategy beats a zero benchmark. Statistic: max over strategies of
    sqrt(T)·mean(return). Uses a stationary block bootstrap on the (recentred)
    returns to respect serial dependence. Returns the best strategy, its mean,
    and the bootstrap p-value (low => the best survivor is unlikely under H0).
    """
    names = list(candidate_returns)
    if not names:
        return {"best": None, "p_value": 1.0, "n_strategies": 0}
    series = [np.asarray(candidate_returns[k], float) for k in names]
    T = min(len(s) for s in series)
    if T < 2:
        return {"best": names[0], "p_value": 1.0, "n_strategies": len(names)}
    series = [s[-T:] for s in series]
    means = np.array([s.mean() for s in series])
    stats_obs = np.sqrt(T) * means
    v_obs = stats_obs.max()
    best = names[int(stats_obs.argmax())]

    rng = np.random.default_rng(seed)
    centred = [s - s.mean() for s in series]  # impose the null
    count = 0
    for _ in range(n_boot):
        idx = _stationary_bootstrap_indices(T, avg_block, rng)
        v_b = max(np.sqrt(T) * c[idx].mean() for c in centred)
        if v_b >= v_obs:
            count += 1
    p = (count + 1) / (n_boot + 1)
    return {"best": best, "best_mean": float(means[int(stats_obs.argmax())]),
            "v_obs": float(v_obs), "p_value": float(p),
            "n_strategies": len(names), "n_obs": T, "n_boot": n_boot}
