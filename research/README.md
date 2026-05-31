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
```

## What's stored (DuckDB at `research/data/research.duckdb`)

| table | grain | notes |
|---|---|---|
| `underlying_bars` | (symbol, timeframe, ts) | OHLCV; ts = bar start, UTC |
| `option_bars` | (option_symbol, timeframe, ts) | OHLCV + parsed contract fields + **`feed`** |
| `contract_universe` | (option_symbol, as_of_date) | point-in-time snapshot; daily-snapshot OI |
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

## Next: M2

Self-computed IV + Greeks per bar (Black-Scholes for 0DTE; American for
longer-dated), sanity-checked against `client.option_snapshots()` live values.
IV-derived features are Phase-B-only for *belief* (ROADMAP §3).
