"""Option pricing, Greeks, and IV inversion (ROADMAP §2b).

Two models, routed by DTE in greeks.py:
  * Black-Scholes (European) — vectorized; the default for 0DTE/1DTE where
    early exercise is worthless, so BS is essentially exact and cheap.
  * Cox-Ross-Rubinstein binomial (American) — scalar; for longer-dated /
    higher-dividend contracts where early exercise can matter.

Conventions (raw analytic units; greeks.py converts to trader units):
  * sigma, r, q are annualized decimals; T is in years.
  * vega = dPrice/dSigma per 1.00 of vol; theta = dPrice/dT per *year*
    (negative for long options); rho = dPrice/dr per 1.00 of rate.

Everything self-computed here is approximate — IV inverted from a single
(indicative, on the free feed) trade print is noisy. Non-invertible prints
(outside no-arbitrage bounds) return NaN with converged=False, by design.
"""
from __future__ import annotations

import numpy as np
from scipy.special import ndtr  # vectorized standard-normal CDF
from scipy.optimize import brentq

_SQRT_2PI = np.sqrt(2.0 * np.pi)
YEAR_DAYS = 365.0
IV_LO, IV_HI = 1e-4, 10.0  # 0.01% .. 1000% vol search bracket


def _npdf(x):
    return np.exp(-0.5 * x * x) / _SQRT_2PI


# ---------------------------------------------------------------- Black-Scholes
def _d1_d2(S, K, T, r, q, sigma):
    vol = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol
    return d1, d1 - vol


def bs_price(S, K, T, r, q, sigma, is_call):
    """Black-Scholes price (vectorized). is_call: bool/array."""
    S, K, T, r, q, sigma = map(np.asarray, (S, K, T, r, q, sigma))
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    dq, dr = np.exp(-q * T), np.exp(-r * T)
    call = S * dq * ndtr(d1) - K * dr * ndtr(d2)
    put = K * dr * ndtr(-d2) - S * dq * ndtr(-d1)
    return np.where(is_call, call, put)


def bs_greeks(S, K, T, r, q, sigma, is_call):
    """Return dict of vectorized Greeks in raw analytic units."""
    S, K, T, r, q, sigma = map(lambda x: np.asarray(x, float), (S, K, T, r, q, sigma))
    is_call = np.asarray(is_call)
    sqrtT = np.sqrt(T)
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    pdf = _npdf(d1)
    dq, dr = np.exp(-q * T), np.exp(-r * T)

    delta = np.where(is_call, dq * ndtr(d1), dq * (ndtr(d1) - 1.0))
    gamma = dq * pdf / (S * sigma * sqrtT)
    vega = S * dq * pdf * sqrtT
    term = -(S * dq * pdf * sigma) / (2.0 * sqrtT)
    theta = np.where(
        is_call,
        term - r * K * dr * ndtr(d2) + q * S * dq * ndtr(d1),
        term + r * K * dr * ndtr(-d2) - q * S * dq * ndtr(-d1),
    )
    rho = np.where(is_call, K * T * dr * ndtr(d2), -K * T * dr * ndtr(-d2))
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho}


def no_arb_bounds(S, K, T, r, q, is_call):
    """(lower, upper) European price bounds; IV exists only strictly inside."""
    dq, dr = np.exp(-q * T), np.exp(-r * T)
    fwd = S * dq
    lower = np.where(is_call, np.maximum(0.0, fwd - K * dr), np.maximum(0.0, K * dr - fwd))
    upper = np.where(is_call, fwd, K * dr)
    return lower, upper


def bs_iv(price, S, K, T, r, q, is_call, tol=1e-7, max_iter=64):
    """Invert BS for IV (vectorized Newton, scalar Brent fallback).

    Returns (iv, converged, residual). Prints outside no-arb bounds or with
    T<=0 give iv=NaN, converged=False.
    """
    price, S, K, T, r, q = (np.asarray(x, float) for x in (price, S, K, T, r, q))
    price, S, K, T, r, q, is_call = np.broadcast_arrays(price, S, K, T, r, q, is_call)
    n = price.size
    iv = np.full(n, np.nan)
    conv = np.zeros(n, bool)

    pf, Sf, Kf, Tf, rf, qf = (a.ravel().astype(float) for a in (price, S, K, T, r, q))
    cf = np.asarray(is_call).ravel().astype(bool)

    lower, upper = no_arb_bounds(Sf, Kf, Tf, rf, qf, cf)
    valid = (Tf > 0) & np.isfinite(pf) & (pf > lower + 1e-10) & (pf < upper - 1e-10)

    # Brenner-Subrahmanyam seed, clipped.
    with np.errstate(all="ignore"):
        seed = np.sqrt(_SQRT_2PI / Tf) * (pf / Sf)
    sig = np.clip(np.where(np.isfinite(seed), seed, 0.3), 0.01, 3.0)

    active = valid.copy()
    for _ in range(max_iter):
        if not active.any():
            break
        d1, d2 = _d1_d2(Sf, Kf, Tf, rf, qf, sig)
        dq, dr = np.exp(-qf * Tf), np.exp(-rf * Tf)
        model = np.where(cf, Sf * dq * ndtr(d1) - Kf * dr * ndtr(d2),
                         Kf * dr * ndtr(-d2) - Sf * dq * ndtr(-d1))
        vega = Sf * dq * _npdf(d1) * np.sqrt(Tf)
        diff = model - pf
        done = active & (np.abs(diff) < tol)
        conv |= done
        active &= ~done
        step = np.where(vega > 1e-12, diff / vega, 0.0)
        sig = np.where(active, np.clip(sig - step, IV_LO, IV_HI), sig)

    iv = np.where(valid, sig, np.nan)

    # Brent fallback for valid-but-not-converged (tiny-vega tails).
    leftover = np.where(valid & ~conv)[0]
    for i in leftover:
        try:
            def f(s, i=i):
                return float(bs_price(Sf[i], Kf[i], Tf[i], rf[i], qf[i], s, bool(cf[i]))) - pf[i]
            if f(IV_LO) * f(IV_HI) < 0:
                iv[i] = brentq(f, IV_LO, IV_HI, xtol=tol, maxiter=200)
                conv[i] = True
        except Exception:
            pass

    resid = np.full(n, np.nan)
    ok = np.isfinite(iv)
    if ok.any():
        resid[ok] = np.abs(
            bs_price(Sf[ok], Kf[ok], Tf[ok], rf[ok], qf[ok], iv[ok], cf[ok]) - pf[ok]
        )
    shape = np.asarray(price).shape
    return iv.reshape(shape), conv.reshape(shape), resid.reshape(shape)


# ----------------------------------------------------- American (CRR binomial)
def crr_price(S, K, T, r, q, sigma, is_call, steps=160):
    """American option price via a Cox-Ross-Rubinstein tree (scalar)."""
    if T <= 0 or sigma <= 0:
        intrinsic = (S - K) if is_call else (K - S)
        return max(intrinsic, 0.0)
    dt = T / steps
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    disc = np.exp(-r * dt)
    p = (np.exp((r - q) * dt) - d) / (u - d)
    p = min(max(p, 0.0), 1.0)  # guard against tiny-dt overshoot

    j = np.arange(steps + 1)
    ST = S * u**j * d**(steps - j)
    values = np.maximum((ST - K) if is_call else (K - ST), 0.0)
    for i in range(steps - 1, -1, -1):
        j = np.arange(i + 1)
        ST = S * u**j * d**(i - j)
        cont = disc * (p * values[1:i + 2] + (1.0 - p) * values[0:i + 1])
        ex = np.maximum((ST - K) if is_call else (K - ST), 0.0)
        values = np.maximum(cont, ex)
    return float(values[0])


def crr_greeks(S, K, T, r, q, sigma, is_call, steps=160):
    """American Greeks by bump-and-reprice (scalar), raw analytic units."""
    hS = S * 1e-3
    dv, dr_, hT = 1e-3, 1e-4, min(1.0 / YEAR_DAYS, T * 0.5)

    def P(s=S, sig=sigma, rr=r, t=T):
        return crr_price(s, K, t, rr, q, sig, is_call, steps)

    p0 = P()
    delta = (P(s=S + hS) - P(s=S - hS)) / (2 * hS)
    gamma = (P(s=S + hS) - 2 * p0 + P(s=S - hS)) / (hS * hS)
    vega = (P(sig=sigma + dv) - P(sig=sigma - dv)) / (2 * dv)
    rho = (P(rr=r + dr_) - P(rr=r - dr_)) / (2 * dr_)
    theta = (P(t=T - hT) - p0) / hT * -1.0 if hT > 0 else np.nan  # dPrice/dT per year
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho}


def crr_iv(price, S, K, T, r, q, is_call, steps=160, tol=1e-6):
    """Invert the CRR tree for IV (scalar Brent). NaN if not bracketable."""
    if T <= 0 or not np.isfinite(price):
        return np.nan, False
    intrinsic = max((S - K) if is_call else (K - S), 0.0)
    if price <= intrinsic + 1e-10:
        return np.nan, False

    def f(s):
        return crr_price(S, K, T, r, q, s, is_call, steps) - price

    try:
        if f(IV_LO) * f(IV_HI) >= 0:
            return np.nan, False
        return brentq(f, IV_LO, IV_HI, xtol=tol, maxiter=200), True
    except Exception:
        return np.nan, False
