# research/ — Options Day-Trading Research System

Methodology and the full plan live in [ROADMAP.md](ROADMAP.md). **Read the
prior first**: the default expected outcome is "no robust edge," and Phase A
on Alpaca's free *indicative* feed can only falsify a signal, never confirm
one (ROADMAP §2d).

This module is **M1 — the data spine**: rate-limited Alpaca pulls of aligned
underlying + option bars into DuckDB, a point-in-time contract universe, and
point-in-time integrity checks.

## Setup

```bash
pip install -r research/requirements.txt        # alpaca-py, duckdb, pandas, python-dotenv
```

Credentials are read from the environment, then `research/.env`, then
`backend/config.py` (where this project keeps its Alpaca keys). They are never
hard-coded in this module. To use env / `.env`, set:

```
ALPACA_KEY=...
ALPACA_SECRET=...
# optional overrides:
# ALPACA_OPTIONS_FEED=indicative   # free tier; recorded on every option bar
# ALPACA_STOCK_FEED=iex            # free tier
# ALPACA_ADJUSTMENT=split          # underlying price adjustment
# ALPACA_MAX_RPM=180               # stay under the ~200/min free-tier ceiling
```

> `backend/config.py` holds live keys in plaintext (gitignored, but in git
> history) — consider rotating them. This module's `settings.py` sources that
> file only to read the keys into the environment; it never imports the Flask app.
> (`config.py` is a gitignored name repo-wide, which is why this module's
> settings live in `settings.py`.)

## Use

Run from the repo root:

```bash
python -m research smoke          # end-to-end demo: universe -> bars -> align -> checks
python -m research universe SPY --exp-lte 2026-06-30
python -m research underlying SPY --days 5 --timeframe 1Min
python -m research options SPY260619C00500000 --days 5 --timeframe 1Min
python -m research align --option SPY260619C00500000
python -m research check          # point-in-time integrity checks
python -m research counts
# M2 — self-computed IV + Greeks:
python -m research greeks --option SPY260619C00500000   # one contract -> option_greeks
python -m research greeks-all --underlying SPY          # every option in option_bars
python -m research greeks-sanity SPY260619C00500000     # live self-consistency check
# M3 — indicators + hypothesis registry:
python -m research indicators [--layer momentum]        # list registered indicators
python -m research hypotheses                           # validate + list hypotheses.yaml
python -m research features --option SPY260619C00500000 --indicators rsi roc
python -m research features --option SPY260619C00500000 --hypothesis gamma_scalp_zone --record
python -m research config-count                         # distinct executed configs (§6 correction)
# M4 — backtester + cost model + objective:
python -m research backtest --hypothesis oversold_mean_reversion --option SPY260619C00500000
python -m research backtest-runs --hypothesis oversold_mean_reversion
# M5 — validation harness (where edges die):
python -m research validate --hypothesis oversold_mean_reversion --option SPY260619C00500000
python -m research walk-forward --hypothesis oversold_mean_reversion --option SPY260619C00500000 --folds 4
python -m research sensitivity --hypothesis oversold_mean_reversion --option SPY260619C00500000
python -m research reality-check --hypothesis oversold_mean_reversion --option SPY260619C00500000
python -m research holdout --hypothesis oversold_mean_reversion --option SPY260619C00500000  # ONCE
```

## What's stored (DuckDB at `research/data/research.duckdb`)

| table | grain | notes |
|---|---|---|
| `underlying_bars` | (symbol, timeframe, ts) | OHLCV; ts = bar start, UTC |
| `option_bars` | (option_symbol, timeframe, ts) | OHLCV + parsed contract fields + **`feed`** |
| `contract_universe` | (option_symbol, as_of_date) | point-in-time snapshot; daily-snapshot OI |
| `option_greeks` | (option_symbol, timeframe, ts) | self-computed IV + Greeks per bar (M2); labelled approximate |
| `config_runs` | (config_hash) | executed-configuration ledger (M3); distinct count feeds ROADMAP §6.5 |
| `backtest_runs` | one row / run | per spread-sweep-level metrics + objective verdict (M4) |
| `holdout_log` | (hypothesis, dataset) | open-exactly-once guard (M5); a 2nd open is refused |
| `ingest_log` | one row / pull | audit trail feeding ROADMAP §6.6 |

## Point-in-time guarantees (enforced by `integrity.py`)

- No bar is timestamped in the future; no NULL timestamps.
- Every option bar records its `feed` (indicative on free).
- No option bar is dated after the contract's expiry.
- ≥90% of option bars align to a same-timestamp underlying bar.
- Stored contract fields match the parsed OCC symbol.

A bar labelled `t` covers `[t, t+timeframe)` and is only *knowable* at
`t + timeframe`. `ingest.align()` attaches `knowable_at` so the backtester
(M4) can enforce **signal-on-close-`t` → fill no earlier than `t+1` open**
(ROADMAP §5). M1 does not trade; it just makes that invariant expressible.

## Caveats baked in (see ROADMAP §2, §12)

- Free option bars are **indicative-feed** aggregates, not true OPRA prints.
- Historical option **quotes/spreads do not exist** here — not pulled, not faked.
- History begins ~Feb 2024; underlying adjustment uses today's factors (mild
  lookahead, documented).

## M2 — self-computed IV + Greeks (done)

[pricing.py](pricing.py) prices and inverts IV; [greeks.py](greeks.py) routes
each bar by DTE and writes `option_greeks`; [rates.py](rates.py) supplies a
point-in-time risk-free rate from FRED (`DGS1MO`, with a constant fallback).

- **Model by DTE bucket** (ROADMAP §2b): Black-Scholes for 0/1DTE (vectorized,
  essentially exact there); American CRR binomial for longer-dated.
- **IV inversion**: vectorized Newton with a Brent fallback. Prints outside
  no-arbitrage bounds give `iv=NaN`, `iv_converged=False` — expected, not a bug.
- **TTE** is measured to 16:00 America/New_York on the expiry date.
- **Price used** is the bar VWAP (less single-print noise), falling back to close.
- **Greek units stored**: `delta`, `gamma`, `vega_pct` (per 1 vol point),
  `theta_day` (per calendar day), `rho_pct` (per 1% rate).

Validated by: textbook BS values, exact put-call parity, exact IV round-trip
(incl. 0DTE); on real stored bars IV round-trips to the input price with
delta/gamma matching an independent recompute; and the CRR tree's
delta/gamma/theta match Black-Scholes to <0.2% for short-dated contracts.

> **On the feed and the live snapshot:** the free indicative feed *does* carry
> latest IV/Greeks/trades for liquid contracts (a full SPY chain returned
> ~12.3k of ~14.6k contracts with IV+Greeks). But those snapshot values are
> *latest-only* (no history) and on the indicative feed are approximations, so
> `greeks-sanity` is a coarse live cross-check, not ground truth — and during
> closed markets its IV/delta fields are stale/asymmetric. A trustworthy
> IV/Greeks comparison is a **Phase-B** activity on vendor data (ORATS/Polygon).
> Self-computing per-bar Greeks remains mandatory because **no historical**
> IV/Greeks series exists on Alpaca (ROADMAP §2a).

Everything here is approximate and IV-derived features remain **Phase-B-only
for belief** (ROADMAP §3).

## M3 — indicator library + hypothesis registry (done)

The anti-data-mining core (ROADMAP §3, §4).

- [registry.py](registry.py): `@register` decorator + `IndicatorSpec`. Each
  indicator declares inputs, default params, sweep ranges, layer, and **data
  phase** ('A' = believable on Alpaca data; 'B' = IV-derived, Phase-B-only).
- [indicators.py](indicators.py): 19 pure, **causal** indicators across trend /
  momentum / volatility / volume / greek / pricing / iv layers. No spread/flow
  indicators — no historical quotes exist on Alpaca.
- [hypotheses.py](hypotheses.py) + [hypotheses.yaml](hypotheses.yaml): the
  registry. Every hypothesis MUST declare a written economic rationale, an
  expected direction, and its indicators. Validation is **strict and
  fail-closed** — no rationale / bad direction / unknown indicator is rejected.
  A hypothesis using any phase-'B' indicator is itself phase 'B'.
- [features.py](features.py): compute registered indicators onto an option's
  aligned bars + Greeks.
- `config_runs` table: every distinct backtested configuration is recorded;
  the **distinct** count (idempotent on `config_hash`) is the N fed to the
  multiple-testing correction (ROADMAP §6.5). Counting registered hypotheses
  instead would be anti-conservative — this captures the garden of forking
  paths (universe, params, split, …).

Validated: known indicator values; a **no-lookahead** test (each rolling
indicator's value at t is unchanged when future rows are truncated); strict
hypothesis rejection of bad input; deterministic config hashing; and the
ledger's distinct-vs-repeat counting (re-running a config bumps `run_count`
but not the distinct count).

> **Discipline reminder (ROADMAP §0, §4):** keep `hypotheses.yaml` small and
> reasoned (tens, not thousands). Adding a sweep value multiplies the executed
> config count and raises the bar the result must clear. The seed set is tiny
> and includes a deliberately over-mined baseline (`oversold_mean_reversion`)
> the apparatus should be able to reject.

## M4 — backtester + cost model + objective (done)

ROADMAP §1 (frozen objective) and §5 (event-driven backtest with realistic costs).

- [metrics.py](metrics.py): expectancy, profit factor, Sharpe/Sortino/Calmar,
  max drawdown, skew, **effective sample size** (deflated for autocorrelation +
  overlap), and `passes_objective` — the frozen gate. The objective is
  **expectancy + risk constraints, never win rate alone**; it returns the
  reasons each constraint passed/failed so a result is never silently accepted.
- [costs.py](costs.py): always-on cost model. Fills cross the **worse side** of
  a *modeled* spread (no historical quotes exist); `spread_mult` is a first-
  class **swept** parameter; stops add **fat-tailed** slippage. `CostModel.zero()`
  exists for tests only — production runs never disable costs.
- [backtester.py](backtester.py): event-driven, **one uniform no-lookahead
  rule** — everything observed at the close of bar *t* (entry signal, stop,
  take-profit, max-hold, flat-exit) executes at the **open of bar t+1**. Outputs
  a trade log (with signal/entry/exit timestamps so the invariant is auditable)
  and an equity curve.
- [signals.py](signals.py): maps each hypothesis config to a transparent,
  causal +1/0 entry rule (the engine is the point, not the signal).

The `backtest` command sweeps the spread and records every level in
`backtest_runs` (and the config once in `config_runs`). **Costs always on; the
worst-case spread is the honest read.**

Validated: the timing invariant (entry fixed when future bars truncated); a
zero-cost round-trip nets exactly 0 while costs strictly reduce P&L; wider
spread is monotonically worse; metrics math on a known log; the objective gate
rejects tiny-N and negative-skew "win-small/blow-up" profiles. A same-bar-fill
lookahead bug was found by the timing test and fixed (uniform t→t+1 rule).

> **What the apparatus is supposed to do:** on stored SPY data the over-mined
> `oversold_mean_reversion` baseline **fails the objective at every spread
> level** (negative expectancy + negative skew), worsening as the spread
> widens. That rejection is success, not failure (ROADMAP prior). And on the
> free indicative feed even a *passing* result would not be believable — that's
> Phase B.

## M5 — validation harness (done)

ROADMAP §6, "where most edges should die."

- [stats.py](stats.py): the multiple-testing core. Probabilistic Sharpe Ratio,
  expected-max-Sharpe of N trials, the **Deflated Sharpe Ratio** (PSR against
  that data-mined benchmark), and **White's Reality Check** (stationary
  block-bootstrap p-value for the best of N). The N is the **distinct-config
  count from `config_runs`** (ROADMAP §4) — not the hypothesis count.
- [validation.py](validation.py): chronological **train/validation/holdout**
  splits (no shuffle, no leakage; holdout is the most-recent slice), rolling/
  anchored **walk-forward** windows, and **parameter sensitivity** (a real edge
  is a broad plateau, not a spike — curve-fit detector).
- `holdout_log` + `holdout` command: the holdout is **opened exactly once**; a
  second open is refused at the storage layer (ROADMAP §6.1).
- Commands: `validate` (train/val + DSR, holdout locked), `walk-forward`,
  `sensitivity`, `reality-check`, `holdout`.

Validated: PSR ≈ 0.5 at its own SR and monotone in the benchmark; E[max SR]
grows with N; a **noise** strategy among 200 trials gets **DSR ≈ 0** while a
genuine strong edge with few trials clears DSR > 0.95; Reality Check gives a
large p under the null and a small p when one real winner is planted; splits
are disjoint/ordered/holdout-newest; the open-once guard refuses a re-open. A
PSR `sqrt`-of-negative bug (→ `nan` for strongly negative SR) was found on the
live run and fixed (falls back to Gaussian SR variance → DSR ≈ 0).

> **What the apparatus does on real data:** the over-mined
> `oversold_mean_reversion` baseline is rejected through **every** lens — train,
> validation, DSR (deflated by the distinct-config N), sensitivity, reality
> check, and finally the one-shot holdout (failing all four objective
> constraints). Rejection is the success case (ROADMAP prior).

> **Shallow-history caveat (real, observed):** the stored demo bars span ~one
> day, so train/val/holdout collapse onto the same date and walk-forward folds
> are same-regime. This exercises the machinery but is **not** a real
> out-of-regime test — that is Phase B on deep vendor history (ROADMAP §6.1, §6.4).

## M6 — run the reasoned hypothesis set (done; result: no edge)

[run.py](run.py) + the `run-all` command run EVERY hypothesis × config × the
option universe through the M4/M5 pipeline: features computed causally per
contract, validation-window trades pooled across contracts, then judged on the
frozen objective, the **Deflated Sharpe Ratio** (deflated by the true
distinct-config count), and **White's Reality Check** across all configs.

```bash
python -m research run-all --underlying SPY            # over all stored SPY options
python -m research run-all --symbols SPY...C... SPY...P...   # explicit basket
```

### First run (2026-06-01), 42 SPY contracts × 7 trading days (2026-05-20→05-29)

| hypothesis | phase | trades | effN | expectancy | SR/trade | DSR | survives |
|---|---|---|---|---|---|---|---|
| oversold_mean_reversion (w=7) | A | 294 | 28.9 | −27.21 | −1.10 | 0.00 | no |
| oversold_mean_reversion (w=14) | A | 88 | 11.6 | −32.13 | −1.05 | 0.00 | no |
| trend_pullback_continuation (w=20) | A | 65 | 23.5 | −24.06 | −1.27 | 0.00 | no |
| trend_pullback_continuation (w=50) | A | 126 | 25.5 | −23.40 | −1.12 | 0.00 | no |
| volatility_squeeze_breakout (w=10) | A | 152 | 25.5 | −19.82 | −0.98 | 0.00 | no |
| volatility_squeeze_breakout (w=20) | A | 109 | 17.4 | −21.60 | −0.95 | 0.00 | no |
| gamma_scalp_zone | A | 0 | 0.0 | — | — | 0.00 | no |
| iv_overpriced_fade (w=30) | B | 274 | 36.4 | −19.83 | −1.04 | 0.00 | no |
| iv_overpriced_fade (w=60) | B | 153 | 25.0 | −17.45 | −0.91 | 0.00 | no |

White's Reality Check over 8 configs: **p = 1.000** — the best-of-N is
indistinguishable from luck.

**SURVIVORS: none.** This is the expected, correct outcome (ROADMAP §0): no
robust edge in the reasoned set under realistic costs + multiple-testing
correction. The over-mined baselines all have negative expectancy net of costs
and negative per-trade Sharpe; the effective-N column (12–36 vs 65–294 raw)
shows the heavy serial correlation the deflator is built to catch.

Notes: `gamma_scalp_zone` produced **0 trades** — its conjunction (high gamma
AND |moneyness|<0.01 AND DTE≤2) is too tight for this basket; that's a
signal-definition observation, not an edge. And even a survivor here would be
**Phase-A-only** on indicative data — not believable until Phase B.

### Deep run (2026-06-01), 234 SPY contracts × 565 trading days × 5-min (Feb 2024 → May 2026)

Built via [historical.py](historical.py) `deep-ingest`: point-in-time
front-week ATM contract construction (each week's call+put picked from the
*then* spot — survivorship-safe, no peeking). 85k+ option bars over ~2.3 years
and multiple regimes, at 5-min to cut intraday trade overlap. Added 4 structural
indicators and 3 **structural** hypotheses (opening-range breakout, power-hour
momentum, gap-fade) — the productive direction after generic indicators failed.

```bash
python -m research deep-ingest --underlying SPY --timeframe 5Min
python -m research greeks-all  --underlying SPY --timeframe 5Min --bs-max-dte 5
python -m research run-all     --underlying SPY --timeframe 5Min
```

| hypothesis | phase | trades | effN | expectancy | SR/trade | DSR | surv |
|---|---|---|---|---|---|---|---|
| oversold_mean_reversion (w=7) | A | 939 | 512.9 | −31.27 | −0.38 | 0.00 | no |
| oversold_mean_reversion (w=14) | A | 446 | 247.7 | −27.16 | −0.30 | 0.00 | no |
| trend_pullback_continuation (w=20) | A | 207 | 118.4 | −31.69 | −0.82 | 0.00 | no |
| trend_pullback_continuation (w=50) | A | 379 | 217.0 | −28.62 | −0.63 | 0.00 | no |
| volatility_squeeze_breakout (w=10) | A | 518 | 280.4 | −29.06 | −0.40 | 0.00 | no |
| volatility_squeeze_breakout (w=20) | A | 355 | 197.8 | −30.47 | −0.28 | 0.00 | no |
| gamma_scalp_zone | A | 516 | 273.1 | −19.12 | −0.15 | 0.00 | no |
| iv_overpriced_fade (w=30) | B | 1412 | 977.8 | −29.40 | −0.69 | 0.00 | no |
| iv_overpriced_fade (w=60) | B | 1244 | 893.0 | −31.45 | −0.59 | 0.00 | no |
| **opening_range_breakout (15)** | A | 527 | 274.2 | −25.34 | −0.57 | 0.00 | no |
| **opening_range_breakout (30)** | A | 497 | 257.6 | −24.43 | −0.61 | 0.00 | no |
| **power_hour_momentum** | A | 249 | 136.0 | −36.25 | −0.67 | 0.00 | no |
| **gap_fade_reversion** | A | 77 | 39.0 | −34.15 | −0.03 | 0.00 | no |

White's Reality Check over 13 configs: best = `gap_fade_reversion`, **p = 1.000**.

**SURVIVORS: none — and now the verdict is trustworthy.** Unlike the 7-day run,
effective-N is 39–977 (real samples, not a small-sample fluke), and the data
spans ~2.3 years / multiple regimes. Every config loses money net of costs. The
**structural hypotheses fared no better** than the textbook ones — the prior
that intraday structure (open/close/gap effects) would help was tested and
**rejected by the data**. The cost drag (theta + modeled spread on long
premium) is the dominant term, exactly as the §1 cost-hurdle pre-check warned.
`gamma_scalp_zone` now trades 516× (deep data fixed the empty filter) and still
loses. The least-bad gross is `gap_fade_reversion` (SR/trade −0.03) but it is
negative after costs and indistinguishable from luck.

This is the honest endpoint of the free-data project: a well-powered Phase-A
test says **no robust intraday long-premium edge** for a retail account, across
generic and structural signals, under realistic costs. Believing otherwise
would require vendor data (Phase B) and a mechanism these signals don't capture.

### Short premium (2026-06-01): the engine generalized to selling

The backtester was generalized to **short premium** (`position: short_premium`
on a hypothesis → engine `side = -1`: entry sells below mid, exit buys back
above mid, P&L = `side·(exit−entry)`, and stop/TP key off the *signed* position
P&L so a short is "stopped" when the option price **rises**). Three short-vol
hypotheses were added with written rationale: `short_high_iv`,
`short_theta_midday`, `short_low_rvol_calm`. (16 unit tests pin the P&L signs,
stop/TP direction, and fill sides; long behaviour is unchanged.)

| hypothesis | phase | trades | effN | expectancy | SR/t | DSR | surv |
|---|---|---|---|---|---|---|---|
| short_high_iv (w=30) | B | 1599 | 1079.6 | −27.02 | −0.47 | 0.00 | no |
| short_high_iv (w=60) | B | 1366 | 949.1 | −27.61 | −0.45 | 0.00 | no |
| short_theta_midday | A | 518 | 264.1 | −36.69 | −0.33 | 0.00 | no |
| short_low_rvol_calm (w=10) | A | 586 | 320.3 | −37.68 | −0.42 | 0.00 | no |
| short_low_rvol_calm (w=20) | A | 436 | 237.3 | −33.93 | −0.40 | 0.00 | no |

**SURVIVORS: still none** (full set: 11 hypotheses, 18 configs, Reality Check
p = 1.000). But the *reason* short premium failed overturned the prior — and is
the interesting result:

- I expected the classic theta profile (high win rate, positive expectancy,
  rejected by the **negative-skew tail check**). Instead these have a **~21%
  win rate and negative expectancy** — they fail the *first* gate.
- Cost is only ~$1.30/trade (vs the $27 loss); short premium is **not** a cost
  story. Gross expectancy is already ≈ −26.
- Mechanism (diagnosed from the trade distribution): intraday short ATM premium
  is **short-gamma with negligible theta capture**. Over 5-minute holds a
  multi-day option's decay is tiny but its gamma exposure to the underlying's
  moves is large — so you're short realized vol with almost no decay offset and
  lose on the moves. A take-profit at 50% of credit barely fires (the IV signal
  flips flat first) and doesn't help.
- The "win small / blow up" negative-skew profile the objective guards against
  **requires holding to harvest theta over days**, which intraday 5-min trading
  on near-ATM weeklies structurally cannot do. The skew check *did* also fire
  (skew −0.85 to −0.99, worst trade −$438, drawdown 100%), but it wasn't even
  needed — expectancy alone killed it.

Net: across **long and short** premium, generic, structural, and vol-based
signals — 11 hypotheses, 18 configs, effective-N up to ~1,080 — **no robust
intraday-options edge survives realistic costs and multiple-testing
correction**. That is the project's honest verdict on free data.

## Next: M7–M9 (not core engineering)

- **M7** — re-validate any survivor on **vendor** IV/Greeks/quotes (ORATS /
  Polygon / CBOE); this is the real experiment (needs a paid source).
- **M8** — paper/forward test on an Alpaca paper account; compare realized vs
  modeled spread.
- **M9** — conditional small live deploy with hard risk controls.

With no Phase-A survivor, there is nothing to carry into M7 from this run — the
honest stopping point. Expanding `hypotheses.yaml` requires a written economic
story per the §4 discipline (and raises the multiple-testing bar).
