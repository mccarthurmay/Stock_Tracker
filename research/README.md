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

## Next: M5

Validation harness: train/validation/holdout split, walk-forward, parameter-
sensitivity (plateau-not-spike), purged+embargoed CV / block bootstrap for
effective N, and the multiple-testing correction (Deflated Sharpe / White's
Reality Check) driven by the `config_runs` distinct-config count — ROADMAP §6.
