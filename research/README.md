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

### Multi-ticker scan (2026-06-03): "scan until one works" — answered with data

[scan.py](scan.py) + `scan-ingest`/`scan-run` run the **CALL** hypotheses
across a whole ticker universe, counting **every (ticker × config) as a
trial**, then deflating the Deflated Sharpe by the *total* trial count and
opening the holdout once on the apparent best. Ingested the **S&P 500 list**
(`backend/storage/ticker_lists/smp500.txt`) front-week ATM, recent ~3 months,
5-min: **279/507 tickers had liquid weekly options** (2,423 call contracts).

```bash
python -m research scan-ingest --file backend/storage/ticker_lists/smp500.txt --lookback-days 95 --timeframe 5Min
python -m research scan-run    --file backend/storage/ticker_lists/smp500.txt --timeframe 5Min
```

Result over **3,614 trials across 278 tickers**:

- **In-sample "winners" (positive validation expectancy): 1** — `AMZN`
  volatility-squeeze, +21.3 expectancy, SR/trade 0.06. The single thing a naive
  ticker-scan would have found and traded.
- **DSR deflated by 3,614 trials → 0.00.** The lone winner's tiny Sharpe is
  statistically nothing once you account for how many trials produced it.
- **Holdout (opened once on that best result) → −34.4 expectancy, Sharpe
  −5.47, FAILS.** It looked good on the data it was selected on and **lost money
  on data it had never seen** — the textbook overfit signature.

This is the direct, data answer to *"why can't I scan tickers until one
works — even if overfit, maybe it isn't?"* You *can* scan; the framework found
your candidate; and tested honestly it was overfit, caught on **two independent
grounds** (holdout reversal + DSR). The protocol is exactly what separates
"overfit" from "real," and the only way to know is the out-of-sample test —
which here was decisive. (Telling, too: only **1 of 3,614** trials cleared even
positive in-sample expectancy — for retail intraday calls, costs dominate so
thoroughly that the search space barely produces *apparent* winners.)

## Long-horizon equity factor backtest (2026-06-03)

The same noise apparatus — Deflated Sharpe, walk-forward, the frozen objective —
ports directly to **long-term, monthly-rebalanced stock-picking** (the
Fama-French quality-value direction the screener in `backend/` is built around).
[equity.py](equity.py) adds a cross-sectional rebalance engine:

- A **factor source** maps (ticker, date) → a score using only data knowable at
  `date`. Two are provided: `momentum_factor` (12-1 month return, computable
  lookahead-free from prices alone) and `ff_composite_factor`
  (`z(BM)+z(OP)−z(INV)` from SEC fundamentals — the real target).
- Monthly: rank the universe, long the top quantile (optionally short the
  bottom), equal-weight, hold to next rebalance, charge turnover cost.
- Output is a **period-return series** → fed straight into `stats` (DSR) and a
  monthly-**re-frozen** objective (`evaluate()`): ≥24 periods, positive mean,
  drawdown ≤35%, and DSR>0.95 deflated by the distinct-config count.

```bash
python -m research equity-smoke --years 2          # 12-1 momentum, 20 large caps
```

**Smoke result (20 mega-caps, 112 monthly periods over 2016-2026, 12-1
momentum):** long-only showed annualized Sharpe **1.11**, +22%/yr, and *passed*
the monthly objective — but **DSR ≈ 0.01 → does not survive**, and that refusal
is correct:

- **Survivorship bias dominates** — these are names that are *still* mega-caps
  in 2026, so momentum among known winners is almost guaranteed to look good.
  `smp500.txt` is a *current*-membership list (no delisted names); a real study
  needs a point-in-time, survivorship-free universe (`equity.py` TODO).
- **Deep sample, still unproven** — with 112 monthly returns spanning the 2018,
  2020 and 2022 stress regimes, the DSR verdict is now *well-powered*: the
  refusal is no longer "too few points" but "this Sharpe is what survivorship +
  data-mining would produce." A naive backtester would have said "Sharpe 1.1,
  ship it"; the apparatus says "unproven." (More data made DSR *more* confident
  in rejecting, not less.)

So the plumbing is validated and the engine refuses to bless a survivorship-
inflated result even with a decade of data. A trustworthy FF factor study needs
**(1)** a PIT delisted-aware universe and **(2)** **filing-lagged** fundamentals
(use a 10-K only after its `filed` date — `fundamentals.py` tracks it but
`get_fundamentals` returns latest). History depth is *not* the blocker: free
Alpaca **stock** bars via the **SIP** feed go back to **2016** (~9 yrs, verified
— the IEX feed only reaches ~mid-2020, and the Feb-2024 limit is *options*
only). Ken French's library + Stooq/Tiingo remain useful for going beyond 2016.
Long-horizon
strategies are *easier* to overfit and *harder* to validate (few independent
bets), which is exactly why the t-stat hurdle in the factor literature rose
from ~2.0 to ~3.0 once trial-counting was applied.

### The real Fama-French quality-value strategy, filing-lagged (2026-06-03)

[factors_pit.py](factors_pit.py) closes the #2 prerequisite — **filing-lag**.
It reads SEC EDGAR `companyfacts` and, for any rebalance date, uses only 10-K
values whose `filed` date ≤ that date (the live `FundamentalsManager` returns
*latest* values, which is lookahead). Verified: AAPL's as-of BM falls 0.56
(2018) → 0.03 (2021) → 0.02 (2024) as different filings become knowable — no
peeking. [equity.py](equity.py) `ff_composite_factor_fn` then scores each date
cross-sectionally as **z(BM) + z(OP) − z(INV)** (cheaper + more profitable +
more conservative — the academically-signed factors the `backend/` screener
uses).

```bash
python -m research equity-ff --start 2016-01-01 --end 2026-06-01
```

**Result (30 large caps, 28 with EDGAR data, 124 monthly periods, 2016-2026):**

| config | periods | annRet | annSR | maxDD | DSR | obj | survives |
|---|---|---|---|---|---|---|---|
| long-only (top 30%) | 124 | +23.4% | **1.28** | 18.3% | 0.06 | pass | **no** |
| long-short (top−bottom 30%) | 124 | +1.4% | 0.17 | 33.0% | 0.00 | pass | no |

Long-only quality-value looks *genuinely attractive* — Sharpe 1.28 over a
decade including 2018/2020/2022, and it even **strengthens on the holdout**
(Sharpe 1.51). A naive quant would ship it. **DSR = 0.06 → does not survive**,
and the reason is specific and correct: the universe is **survivorship-biased
in the strategy's favour** — 28 names that all survived to 2026 — so a Sharpe
~1.3 from a couple of configs on hand-picked survivors is within what selection
+ luck produce. This is *not* "no edge"; it's **"promising, not yet proven, and
here is exactly what proving it requires."** The long-short being flat is itself
a tell: most of the long-only return is market beta, not factor alpha.

### Broad-universe run (~4,100 names with EDGAR data, 125 periods, 2016-2026)

To shrink the *which-names* selection bias, the same strategy was re-run over a
**6,808-ticker** universe ([complete_list_api_valid.txt](../backend/storage/ticker_lists/complete_list_api_valid.txt)
— every symbol in `complete_list.txt` with Alpaca SIP history; ~4,100 had usable
filing-lagged EDGAR fundamentals → **~270k point-in-time factor rows**). Memory
held flat via a streaming per-ticker EDGAR fetch (no unbounded cache).

| config | periods | annRet | annSR | maxDD | skew | DSR | survives |
|---|---|---|---|---|---|---|---|
| long-only (top 30%) | 124 | +19.2% | 0.86 | 31.6% | +1.59 | 0.00 | no |
| long-short (top−bottom 30%) | 124 | **−21.6%** | **−0.45** | **93.0%** | −1.30 | 0.00 | no |

This is the **most informative equity result in the project**, and it sharpens
the 30-name finding two ways:

1. **The apparent edge shrank with breadth.** Long-only fell from Sharpe 1.28
   (30 cherry-picked mega-caps) to **0.86** on thousands of names — exactly what
   you'd expect as survivorship/selection bias washes out. Still DSR 0.00.
2. **The long-short is catastrophic: −21.6%/yr, 93% drawdown.** The long-short
   leg *isolates the factor from market beta*, and it is strongly negative. So
   the long-only's +19% was **essentially all market beta** (being long stocks
   in a 2016-2026 bull market); the quality-value tilt added **no alpha — it
   detracted**. A naive backtester reporting only the long-only ("+19%, holds up
   on holdout") would entirely miss that there is no factor edge underneath.

**Verdict across both equity runs:** the FF quality-value screen, tested with
filing-lagged fundamentals over a decade, shows **no factor alpha beyond market
beta** on this (still survivorship-biased) universe — and the bias works in the
strategy's *favour*, so the real number is if anything worse. This is now closer
to "no edge" than "unproven."

The one prerequisite still not met is a **point-in-time, delisted-aware
universe**: `complete_list.txt` (and `smp500.txt`) list only *currently* traded
names, so dead companies are absent. (Alpaca SIP itself *does* retain delisted
tickers' bars — verified: FRC/TWTR/WeWork data ends at their death dates — so a
truly survivorship-free run is achievable with a *source* list that includes the
dead names; that historical-constituents list is the hard-to-get free piece.)
Adding the failed names would only lower the result further, reinforcing the
verdict. The framework did its job: it took an attractive-looking screen, showed
the apparent return was beta not alpha, and refused to bless it.

## The screener's own CI signal, backtested (2026-06-03)

The live screener (`backend/analysis.py`) buys names trading **below their
`mean − 2·std` price band** over a ~90-day window (mean reversion). `equity.py`
(`ci_factor_fn`, `ci_ma_factor_fn`) backtests it as a cross-sectional strategy,
point-in-time on daily SIP data, sweeping three things the user asked about —
each counted as a DSR trial:

```bash
python -m research equity-ci --file backend/storage/ticker_lists/smp500.txt \
    --start 2016-01-01 --windows 60 90 120 252 --ma 200 --long-short
```

**Result (S&P 500 names, 125 monthly periods, 2016-2026, 16 trials):**

| variant | long-only annSR | long-short annSR | DSR |
|---|---|---|---|
| CI 60d | 0.82 | −0.14 | 0.00 |
| CI 90d (the screener's default) | 0.74 | −0.34 | 0.00 |
| CI 120d | 0.77 | −0.29 | 0.00 |
| CI 252d | 0.64 | −0.30 | 0.00 |
| **CI 60d + MA200** | **1.04** | −0.01 | 0.00 |
| CI 90d + MA200 | 0.98 | 0.00 | 0.00 |
| CI 120d + MA200 | 0.94 | −0.04 | 0.00 |
| CI 252d + MA200 | 0.86 | −0.37 | 0.00 |

Three findings, mapping to the three avenues:

1. **"Which lookback window works?" is the wrong question.** Long-only Sharpes
   cluster at 0.64–1.04 with no special window; the spread is noise. The best
   (CI60+MA200, SR 1.04) is the **max of 16 trials**, and **DSR = 0.00 on every
   one** — deflating by the trial count deletes the apparent winner. Picking the
   best window *is* the overfit, and the apparatus shows it. (Holdout on the
   best: train SR 1.14 → holdout 0.81 — the usual in-sample flattery fade.)
2. **The CI + moving-average combo genuinely improved the raw signal** — every
   `CI+MA200` variant beat its raw twin (e.g. 60d: 0.82 → 1.04; drawdowns ~27%
   → ~23%). "Buy the dip only in an uptrend" was a sound intuition. But...
3. **...the long-short reveals it's beta, not alpha.** Stripping market beta
   (top minus bottom), every CI variant is ≈ 0%/yr (−0.37 to 0.00 Sharpe). So
   the long-only's ~15%/yr was **market beta** — being long equities in a
   2016-2026 bull market — and the MA filter helped by *timing that beta*
   (staying in uptrends), not by adding selection edge. Same verdict as the FF
   screen: **no alpha beyond beta.**

### Could the CI idea apply to volume? (idea, not tested — per request)

Plausibly, but with a sharper caveat. A CI band on **price** assumes a roughly
stationary mean to revert to; **volume** is different — it's non-stationary
(secular drift, persistent regime shifts around index adds/earnings), heavily
right-skewed, and spikes are clustered. A symmetric `mean ± 2σ` band fits it
badly: "too low" volume isn't obviously a tradeable signal, and "too high"
volume (a 2σ spike) is the more-studied event — usually a *capitulation* or
*breakout* marker, not a mean-reversion one. If pursued, the honest framing
would be **relative volume** (today vs a trailing median, log-scaled) as a
*filter/conditioner* on the price signal — e.g. "a CI dip on elevated volume =
real selling vs. a CI dip on thin volume = noise" — rather than a standalone CI
band on raw volume. That's a conditioning hypothesis worth one registered trial,
not a new factor; and it would face the same beta-vs-alpha test the long-short
applied above.

### Adding a SELL / take-profit rule (2026-06-03)

`equity.ci_timing_backtest` (`equity-timing`) makes the CI signal a **daily,
event-driven** strategy with an explicit exit: **buy when price < mean−2σ; sell
(take profit / de-risk) when price > mean+`S`σ OR the moving average is
falling.** Point-in-time (signal at close t → act t+1), costs on, benchmarked
against **buy-and-hold** (always-in, equal-weight). Sweeps sell-σ × MA window,
each a DSR trial.

```bash
python -m research equity-timing --file backend/storage/ticker_lists/smp500.txt \
    --start 2016-01-01 --sell-sigmas 1.0 1.5 2.0 --ma-windows 50 100 200
```

**Result (S&P 500, daily 2016-2026, 9 trials; buy-and-hold annSR = 0.95):**

| sell σ | MA | annRet | annSR | maxDD | annSR − B&H |
|---|---|---|---|---|---|
| 2.0 | 50 | −1.5% | −0.39 | 19% | **−1.34** |
| 2.0 | 100 | +2.4% | 0.22 | 42% | −0.73 |
| 2.0 | **200** | +16.5% | **0.87** | 33.5% | **−0.08** |

(1.0σ/1.5σ rows track closely; the **MA window dominates**, sell-σ barely moves it.)

The exit rule **does not add value** — **0/9 beat buy-and-hold, DSR = 0.00 on all:**

- **The "MA falling" trigger is the problem, and it's MA-speed-dependent.** A 50-
  or 100-day MA flips negative constantly, so the rule whipsaws you out on every
  wiggle — paying costs, missing recoveries, badly underperforming (SR −0.39 to
  0.22). Only the **slow 200-day MA** flips rarely enough to stay mostly invested,
  and *then* it nearly matches buy-and-hold (0.87 vs 0.95) — but never beats it.
- **At its best it trades a little return for a little less risk** (SR 0.87 vs
  0.95, maxDD 33.5% vs 38.5%) — i.e. "sit in cash sometimes," not edge. The
  holdout agrees (strat 1.21 vs B&H 1.25).
- **Same lesson as the buy side:** selling because price rose (+σ) or a short MA
  ticked down throws away the market beta that was the only thing earning. Exit
  timing on this signal subtracts, it doesn't add. A real take-profit edge would
  have to *beat* the vs-B&H column — none did.

### Composable sell triggers + RSI≥70 + the MA-as-drawdown-reducer test (2026-06-03)

`ci_timing_backtest` was generalized to **composable sell triggers** — `sigma`
(price > mean+σ), `ma` (200d MA falling), and a new **`rsi`** (14d RSI ≥ 70,
matching `backend/analysis.py` *exactly* — verified 0.0 diff) — swept across all
7 unions (each a DSR trial). `evaluate` now also reports **Calmar** and the run
prints **drawdown saved vs buy-and-hold**, to judge the MA exit as risk control
rather than alpha.

```bash
python -m research equity-timing --file backend/storage/ticker_lists/smp500.txt \
    --start 2016-01-01 --sell-sigma 1.0 --ma 200 --rsi-sell 70
```

**Result (S&P 500, daily 2016-2026, 7 combos; buy-and-hold annSR 0.95, Calmar 0.45, maxDD 38.5%):**

| sell triggers | annSR | Calmar | maxDD | DSR | annSR − B&H | ddSaved |
|---|---|---|---|---|---|---|
| sigma | 0.79 | 0.36 | 42.0% | 0.00 | −0.16 | −3.6% |
| **ma** | **0.92** | **0.47** | **33.7%** | 0.00 | −0.03 | **+4.7%** |
| rsi | 0.76 | 0.35 | 42.9% | 0.00 | −0.19 | −4.4% |
| sigma+ma | 0.67 | 0.38 | 33.6% | 0.00 | −0.27 | +4.9% |
| sigma+rsi | 0.74 | 0.34 | 43.1% | 0.00 | −0.20 | −4.6% |
| ma+rsi | 0.72 | 0.41 | 33.7% | 0.00 | −0.22 | +4.8% |
| sigma+ma+rsi | 0.69 | 0.39 | 33.5% | 0.00 | −0.26 | +4.9% |

Three answers:

1. **No combination gets a good DSR or beats buy-and-hold. 0/7 on both.** Every
   `annSR − B&H` is negative; **combining triggers makes it worse** (sigma+ma+rsi
   0.69 < any single trigger) — more exits = more whipsaw, more cost, more missed
   recovery. No mix of CI/σ/MA/RSI conjures alpha that isn't there.
2. **MA-only is a mild, genuine drawdown-reducer** — the one positive. It cuts
   max drawdown 38.5% → 33.7% (**~4.7 pts saved**), nudges Calmar above B&H (0.47
   vs 0.45), and gives up only ~1%/yr (16.0% vs 17.1%). A reasonable risk-control
   choice if you value smoother equity — but **not alpha** (DSR 0.00, doesn't beat
   B&H on Sharpe), and the holdout is unstable (train 0.74 *under* B&H 0.86;
   holdout 1.48 *over* 1.25). That instability is exactly why DSR won't bless it.
3. **RSI≥70 is the weakest exit** — lowest single-trigger Sharpe (0.76) and it
   *raises* drawdown (42.9%, ddSaved −4.4%): selling at RSI 70 exits too early in
   strong uptrends, hurting both return and risk. It dragged down every combo it
   joined.

**Verdict:** across buy, buy-in-uptrend, and now every sell-trigger combination,
nothing clears DSR or beats buy-and-hold. The only defensible use is **MA-only as
a drawdown trimmer** (≈5 pts less drawdown for ≈1%/yr) — risk management, not edge.

### CI dip + VALUE filter (the value-trap fix): buy cheap dips, sell at −1σ (2026-06-03)

The strongest theoretical case the project tested. Every prior CI result was
market beta because pure mean-reversion buys *every* dip — including falling
knives. This combines the screener's two halves: **BUY when price < mean−2σ AND
the name is fundamentally undervalued** (top-quantile filing-lagged `z(BM)+z(OP)
−z(INV)`, no lookahead), **SELL when price recovers to mean−1σ.** The value
screen is meant to filter value-traps from real bargains.
`equity.ci_value_timing_backtest` + `equity-civalue`, daily, PIT, costs on, vs
buy-and-hold; sweeps CI window × value quantile (each a DSR trial).

```bash
python -m research equity-civalue --file backend/storage/ticker_lists/smp500.txt \
    --start 2016-01-01 --windows 60 90 120 --quantiles 0.3 0.5
```

**Result (466 names with EDGAR data, daily 2016-2026, 6 trials; B&H annSR 0.99):**

| CI win | value Q | annSR | Calmar | maxDD | DSR | annSR − B&H |
|---|---|---|---|---|---|---|
| 60 | 0.30 | 0.57 | 0.24 | 44.6% | 0.00 | −0.42 |
| 90 | 0.30 | 0.58 | 0.25 | 46.3% | 0.00 | −0.41 |
| 120 | 0.50 | 0.59 | 0.24 | 47.6% | 0.00 | −0.40 |

**The value filter didn't rescue it — it made things worse. 0/6 clear DSR, 0/6
beat B&H, and the gap (−0.40 to −0.52) is *wider* than pure CI.** The holdout is
decisive: strat annSR **0.60 vs buy-and-hold 1.29** on unseen data. Why this null
is the *most* informative one:

- **The filter worked mechanically but added no skill.** It correctly gated
  holdings to undervalued names (15–26 held of 466) — the screen *is* selecting
  cheap names. They just don't outperform, consistent with the broad-universe FF
  finding that quality-value is **beta, not alpha** here.
- **Waiting for the rare −2σ-dip-AND-undervalued double-trigger means sitting in
  cash most of the time — sacrificing the bull-market beta that was the only
  thing earning.** Every timing/filter variant rediscovers this: the market
  premium is the edge; any rule that sits out the market gives it up.
- This was the **best-motivated combination in the project** (the user's own
  value-trap reasoning, built lookahead-free) and it still failed — that's
  evidence about the market, not a flaw in the idea.

### Isolating the entry signal: same buy, NO sell (`--hold-forever`, 2026-06-03)

To separate "is the buy good?" from "did the sell hurt?", the strategy was re-run
with the **sell rule removed** — buy cheap CI dips, then **hold to the end**
(`equity-civalue --hold-forever`). Same 466 names, 6 trials.

| CI win | value Q | avgHeld | annSR | maxDD | DSR | annSR − B&H |
|---|---|---|---|---|---|---|
| 60 | 0.30 | 263 | 0.89 | 38.7% | 0.00 | −0.09 |
| 120 | 0.50 | 300 | 0.90 | 39.4% | 0.00 | −0.09 |
| — buy-and-hold — | | 466 | **0.99** | 38.5% | — | — |

This is the **most diagnostic result in the project**. Removing the sell:

- **Recovered the lost performance** — Sharpe jumped from ~0.58 (with the sell) to
  ~0.88, and the gap to buy-and-hold collapsed from −0.40+ to **−0.09**. Confirmed:
  **the sell rule was the damaging part, sacrificing market beta.**
- **But the entry signal adds no alpha** — it still slightly *trails* buy-and-hold
  (0.88 vs 0.99, DSR 0.00, holdout 1.19 vs 1.29). And the mechanism is visible in
  `avgHeld`: buying dips and never selling **accumulates 220–337 of 466 names**, so
  the strategy *converges to owning the market* — just later (it waits for dips) and
  slightly incomplete, which is why it trails.
- **Clean verdict:** the buy is **harmless but pointless** (it drifts toward the
  index), the sell was **actively harmful** (it threw away beta). Neither half adds
  selection skill. The honest optimum is the plain index — exactly what every other
  test pointed at.

### SPY crash-dodge overlay — the standout, and why DSR still kills it (2026-06-03)

A different idea entirely: not stock selection but a **single-asset market-timing
overlay on SPY** — sell everything when SPY breaks below its CI band (a "black
swan"), **average back in incrementally as it keeps falling** ("buy as it
decreases"), stop on the turn, reset to fully invested on recovery.
`equity.spy_crash_overlay_backtest` + `equity-crash`, daily, PIT, costs on, vs
buy-and-hold SPY; sweeps crash-σ × number of buy-in increments.

```bash
python -m research equity-crash --start 2016-01-01 --crash-sigmas 1.5 2.0 2.5 --increments 3 5 10
```

**Result (SPY, daily 2016-2026, 9 trials; buy-and-hold SPY annSR 0.91, maxDD 33.8%):**

| crash σ | incr | annRet | annSR | maxDD | DSR | annSR − B&H | ddSaved |
|---|---|---|---|---|---|---|---|
| 1.5 | 5 | +17.7% | 1.09 | 28.4% | 0.00 | +0.18 | +5.4% |
| 1.5 | 10 | +17.4% | 1.21 | **21.2%** | 0.00 | +0.30 | **+12.6%** |
| 2.0 | 5 | +18.2% | 1.14 | 22.9% | 0.00 | +0.23 | +10.8% |

**This is the FIRST and only thing in the project to beat buy-and-hold — all 9/9
combos did**, with higher return *and* much lower drawdown (best cut maxDD nearly
in half: 21% vs 34%). The holdout beat B&H too (Sharpe 1.88 vs 1.48). And **DSR is
still 0.00 on every one** — correctly. Why:

- **The entire P&L comes from ~3-5 crash events** (mainly dodging COVID-2020 and
  the 2022 bear). That's a handful of independent bets, not the hundreds the daily
  Sharpe pretends. DSR 0.00 means: even beating B&H this clearly is statistically
  indistinguishable from getting lucky on a couple of crashes — the **"I dodged
  COVID once" trap.** Any sample containing COVID makes a crash-dodger look brilliant.
- **The sweep pattern is the tell:** Calmar rises monotonically with more increments
  (incr=10 best) — the signature of *fitting the shape of the crashes you happened
  to see*, not a robust mechanism. A fast V-shaped crash (sell the bottom, miss the
  snap-back) could flip the result; COVID's slow decline + sharp recovery flattered it.
- **What it genuinely is:** a **drawdown-reduction / vol-target overlay** (a real,
  documented risk-management technique). The "extra return" is mostly *avoided
  losses*, i.e. risk control, not alpha. Useful if your goal is a smoother ride and
  you accept it may fail the next crash that doesn't look like the last ones — but
  **not a DSR-significant edge**, and honestly can't be on ~5 events.

So even the project's best result reinforces the thesis: it beat the index *only*
by timing rare crashes, which is unfalsifiable on this little data — exactly what
DSR is built to flag.

#### Splitting the overlay into its two phases (the 2×2 matrix)

The overlay has two independent phases, and the *direction* of each is a trading
philosophy. Both were made configurable and swept (54 variants):
**decline** = `cliff_sell` (dump all on the trigger) vs `ramp_sell` (sell a step
per new low — *trend-following: cut risk into weakness*); **re-entry** =
`avg_down` (buy a step per new low — *mean-reversion*), `ramp_up` (buy a step as
it rises off the low — *trend-following: add into strength*), or `cliff_up` (snap
back only once recovered). Per-mode-pair average annualized Sharpe:

| decline | re-entry | avgSR | philosophy |
|---|---|---|---|
| cliff_sell | avg_down | **1.08** | dump + average down (the original) |
| cliff_sell | ramp_up | 1.01 | dump + trend re-entry |
| ramp_sell | avg_down | 0.95 | gradual sell + average down |
| cliff_sell | cliff_up | 0.93 | dump + wait |
| ramp_sell | ramp_up | 0.92 | **pure trend-following** |
| ramp_sell | cliff_up | 0.83 | gradual sell + wait |

Clear, mechanism-consistent ranking:

1. **The decline phase dominates, and decisive beats gradual.** Every `cliff_sell`
   variant outranks its `ramp_sell` twin. A black swan is *fast* — by the time a
   gradual sell has shed a few increments, the crash already happened. **Selling
   incrementally into a drop is too slow to dodge a crash.** (Smoke check: in COVID
   `ramp_sell` only reached ~40% cash while `cliff_sell` hit 0%.)
2. **The re-entry phase barely matters; averaging down slightly beats trend.**
   `avg_down` buys cheaper shares before the snap-back; `ramp_up` waits for the
   uptrend to confirm and re-enters higher. So **buying into the recovery is a hair
   worse than buying into the decline** — you pay up for confirmation.
3. **Pure trend-following (ramp_sell + ramp_up) ranked 5th of 6** — slowest to
   de-risk *and* slowest to re-risk, so it captures the least crash protection.

**But all 54 variants still have DSR = 0.00** (40/54 beat B&H on Sharpe). Slicing
the phases changes *which flavor* of crash-timing is best (decisive exit + average
down) but not the verdict: every variant lives off the same ~3-5 crashes, so none
is statistically real. The matrix tells you the best *shape* of a risk-control
overlay, not that any of them is an edge.

## Final scoreboard (nothing cleared DSR > 0.95)

| Strategy class | best DSR | beats B&H? |
|---|---|---|
| Options long premium (generic + structural) | 0.00 | — |
| Options short premium (short-vol) | 0.00 | — |
| Multi-ticker call scan (3,614 trials) | 0.00 | — |
| FF quality-value, 30 names | 0.06 | no |
| FF quality-value, broad ~4,100 names | 0.00 | no (long-short ≈ 0) |
| CI mean-reversion (window sweep + MA) | 0.00 | no |
| CI sell rule / composable triggers / RSI | 0.00 | no |
| CI dip + value filter | 0.00 | no |
| CI dip + value, no-sell (entry only) | 0.00 | no (≈ B&H) |
| **SPY crash-dodge overlay** | **0.00** | **YES (9/9) — but on ~5 crash events** |

Closest ever: DSR ≈ 0.06. The **only** thing to beat buy-and-hold was the SPY
crash-dodge overlay — and DSR still rejects it because its edge rests on ~3-5
crash events (the "dodged COVID once" trap), exactly the few-bets illusion the
deflation is built to catch. Consistent finding: **apparent returns are market
beta, best-of-N noise, or a handful of lucky macro calls; no robust retail edge
survives honest costs + multiple-testing correction on free data.** The framework
did exactly its job — including rejecting the author's own best ideas, and
refusing to bless even the one strategy that *looked* like a winner.

## Next: M7–M9 (not core engineering)

- **M7** — re-validate any survivor on **vendor** IV/Greeks/quotes (ORATS /
  Polygon / CBOE); this is the real experiment (needs a paid source).
- **M8** — paper/forward test on an Alpaca paper account; compare realized vs
  modeled spread.
- **M9** — conditional small live deploy with hard risk controls.

With no Phase-A survivor, there is nothing to carry into M7 from this run — the
honest stopping point. Expanding `hypotheses.yaml` requires a written economic
story per the §4 discipline (and raises the multiple-testing bar).
