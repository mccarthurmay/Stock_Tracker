# Options Day-Trading Research System — Build Roadmap (rev. 2026-05-31)

> **Purpose of this document.** This is a build spec to hand to a coding/agent AI. It describes a research and backtesting framework whose goal is to *honestly determine whether any combination of indicators produces a positive-expectancy intraday options strategy* — and, if one survives, to forward-test it before risking real money. The broker/data source is **Alpaca (free tier)**, which has specific limitations documented below that the build must work around.

> **Read this first — the prior that governs the whole project.** The base rate is that intraday options traders lose, and most apparent "edges" found by searching many indicator combinations are statistical artifacts. The entire validation apparatus in this spec exists to avoid fooling ourselves. **The correct default outcome of this project is "no robust edge found," and that is a success, not a failure.** Any result that survives must clear a deliberately high bar. Do not relax the guardrails to manufacture a positive result.

> This is research methodology and engineering, not financial advice.

---

## Revision notes (what changed in this rev, and why)

This revision folds in a feasibility + methodology review (2026-05-31) that verified the data claims against Alpaca's live docs/SDK and tightened the statistics. The original spec was already methodologically strong; the changes below close the holes that survive its existing guardrails. Substantive edits are tagged **[rev]** inline.

1. **Phase A is reframed as pipeline-validation-only.** Alpaca's free options data comes from the *indicative feed*, which Alpaca itself says is "not generally to be used... to test the efficacy of one's strategy." **Phase A can falsify but never confirm an edge; Phase B vendor data is the actual experiment, not a bonus.** (§2a, §2d, §6)
2. **Free historical bars are indicative-sourced.** The risk is data *quality* (indicative vs OPRA), not delay. The trade price you invert for IV is itself an approximation before single-print noise. (§2a, §2b)
3. **Multiple-testing N = distinct executed configurations, not registered hypotheses.** The garden of forking paths (universe, DTE bucket, timing, stops, sizing, spread model, split point) inflates true multiplicity. Wire the run-log into the deflation. (§4, §6, §9)
4. **Trade "independence" is defined and enforced.** Overlapping/clustered intraday trades are serially correlated; report *effective* N and use purged+embargoed CV / block bootstrap. (§1, §6)
5. **The modeled spread is promoted to a first-class swept parameter** with a mandatory pessimism sweep; any edge that only survives the optimistic end is dead. (§5)
6. **IV-derived features are tagged Phase-B-only**, with IV-mean-reversion flagged as especially suspect (errors-in-variables manufactures spurious reversion). (§3)
7. **Off-by-one-bar lookahead** is now an explicit engine invariant, and the **contract universe must be point-in-time.** (§5, §11)
8. **Black-Scholes is the default for 0DTE**; match the pricing model to the DTE bucket rather than mandating American everywhere. (§2b)

---

## 0. Scope and non-goals

- **In scope:** data pipeline, self-computed Greeks/IV, indicator library, a hypothesis registry, an event-driven backtester with realistic costs, a rigorous validation protocol, and a paper/forward-test harness.
- **Out of scope (for v1):** live capital deployment at size, multi-leg optimization, ML model zoos. Get a clean, honest single-signal pipeline working first.
- **Explicit anti-goal:** brute-forcing every indicator combination to find anything above a 50% win rate. That approach is the primary failure mode (see §4 and §6). Win rate is not the objective (see §1).
- **[rev] Code location:** lives in a separate top-level `research/` directory in the Stock_Tracker repo. It reuses the existing `AlpacaDataManager`/`RateLimiter` *pattern* from `backend/data/analysis.py` but keeps its own data layer (DuckDB/Parquet) and dependencies. It does not import the Flask app.

---

## 1. Objective function (decide and freeze BEFORE touching data)

Define the success metric up front and do not move the goalposts later.

- **Primary metric:** positive **expectancy** net of realistic costs.
  `expectancy = (win_rate * avg_win) − (loss_rate * avg_loss)`
- **Required constraints (all must hold):**
  - Maximum drawdown below a pre-set ceiling (e.g. ≤ 20% on the test equity curve).
  - A skew/tail check: the strategy must not be a "win small, blow up" negative-skew profile masquerading as steady. Report return skewness and worst single-day/worst-trade loss.
  - **[rev] Minimum *effective* trade count, not raw count.** Aim for ≥ 200 trades, but the number that feeds any statistic is the **effective sample size** after accounting for serial correlation and overlap (see §6.3). 200 clustered 0DTE entries on 40 trading days is *not* 200 independent draws. Define a trade as independent only if its holding window does not overlap another's and entries are separated by a stated minimum gap; otherwise down-weight via block bootstrap.
- **Risk-adjusted reporting (always):** Sharpe, Sortino, Calmar, profit factor, max drawdown, average and worst trade. **[rev]** Report Sharpe with its standard error and the **Deflated Sharpe Ratio** alongside it (see §6.5).
- **[rev] Cost-hurdle pre-check:** before any search, compute the break-even *gross* edge at your typical contract premium (see §5). At $0.65/contract/side plus a modeled spread on a $0.20–$0.50 contract, round-trip friction is 10–30%+ of premium. State the gross edge required just to break even — this grounds the "default = no edge" prior in arithmetic.
- **NOT the objective:** win rate alone. Optimizing win rate selects *for* dangerous negatively-skewed strategies.

Deliverable: a `metrics.py` that computes all of the above from a trade log, plus a single boolean `passes_objective(results) -> bool`. **[rev]** Every call to `passes_objective` is logged with the config that produced it (see §6.6) — the boolean is only trustworthy if you can count how many times you queried it.

---

## 2. Data layer

### 2a. What Alpaca's free tier actually provides

> **[rev] Verified against Alpaca docs/SDK on 2026-05-31.** See Sources at the end.

| Data | Availability on free (Basic) plan | Notes |
|---|---|---|
| Underlying (stock) bars, OHLCV to 1-min | ✅ | Free feed is IEX for equities |
| Option bars, OHLCV per contract | ✅ | `get_option_bars`, no explicit time cap, since Feb 2024 |
| Option latest quote / latest trade / snapshot / chain | ✅ | Includes **IV and Greeks** — but **latest only** |
| Historical option **trades** | ⚠️ capped at **last 7 days** | `get_option_trades`: "up to 7 days ago" |
| Historical option **quotes** (bid/ask time series) | ❌ **not available** | No `get_option_quotes`; only `get_option_latest_quote` |
| Historical IV / Greeks time series | ❌ **not available** | Snapshot/chain are latest-only |
| History depth | ~**Feb 2024 → present** | No 2018/2020/2022 stress regime exists in Alpaca options |

> **[rev] Feed-quality caveat (the real one).** The free Basic plan serves options data from the **indicative feed**, which Alpaca describes as *calculated derivatives of OPRA* — "the quotes are not actual OPRA quotes... indicative derivatives," and the feed is positioned "to debug one's code and not generally to be used for live trading or to test the efficacy of one's strategy." **This means your historical option *bars* on the free plan are aggregated from indicative (approximated) prints, not true OPRA trades.** The problem is *data quality*, not the 15-minute delay (delay is irrelevant for backtesting). Record the `feed` value used for every pull; on the free plan it can only be `indicative`. This is the central reason Phase A cannot confirm an edge (see §2d, §6).

### 2b. What must be built because Alpaca won't give it historically

- **Self-computed IV and Greeks.** For each historical option bar, compute IV and Greeks from:
  - the option bar price (note: this is a *trade* price — and **[rev]** on the free feed an *indicative* trade price — not a bid/ask mid; see caveat),
  - the underlying price at the **same timestamp** (requires careful time alignment),
  - time-to-expiry, a risk-free rate (short Treasury / SOFR via FRED), and the underlying's dividend yield.
  - **[rev] Match the pricing model to the DTE bucket.** For **0DTE/1DTE** (most of "intraday options"), early-exercise value ≈ 0 and intraday dividend exposure ≈ 0, so **Black-Scholes is essentially exact and far cheaper to invert** — use it. Reserve an **American model** (binomial CRR or Barone-Adesi-Whaley, e.g. via QuantLib) for longer-dated or high-dividend contracts where early exercise matters. Document the model used per bucket.
  - Solve IV by numerically inverting the pricing model (Newton-Raphson with bisection fallback). Use the bar VWAP rather than the single close print where available, to dampen single-print noise.
  - **Caveat to record in the output:** IV computed from a single trade print is noisier than vendor IV and inherits bid-ask noise; **[rev]** on the free feed it inherits *indicative-feed approximation error on top of that* — two layers, not one. Treat self-computed IV/Greeks as approximate, and see §3 for why IV-derived signals are Phase-B-only.
- **Historical bid-ask spread is unavailable.** This means spread/liquidity-based signals (a core part of the indicator taxonomy) **cannot be backtested on Alpaca history.** Drop them from v1 (do not try to rescue them); source elsewhere in Phase B (§2d).

### 2c. Storage and hygiene

- Local columnar store: **DuckDB or Parquet** (fast, file-based, free).
- Strict **point-in-time correctness**: every feature value at time *t* must use only data available at or before *t*. No lookahead. **[rev]** See §5 for the explicit signal-to-fill timing invariant.
- Align option bars to underlying bars on a shared minute index.
- Handle corporate actions (splits/dividends) on the underlying.
- Maintain a **point-in-time** contract-universe table (symbol, strike, expiry, type) and an open-interest table (OI is daily-snapshot only, from the contracts endpoint). **[rev]** Build the tradeable-contract set *as it existed at time t* — strikes actually listed and liquid then — never filtered from today's chain, or you select contracts that "worked out" (options survivorship; see §6/§12).

### 2d. Recommended two-phase data strategy

> **[rev] Reframed.** Phase A is not "prove the edge cheaply." It is "prove the *pipeline* is correct." On indicative free data, **a positive Phase-A result is uninterpretable** — by Alpaca's own description the data is unfit for testing strategy efficacy. Phase A can *falsify* (a signal that fails even here is dead) but can *never confirm*. **Phase B is the actual experiment.**

- **Phase A (free, prove the *pipeline*):** Alpaca bars + self-computed Greeks/IV. Accept shallow history, approximate Greeks, and indicative-feed prices. Goal is a working, honest, lookahead-free pipeline whose costs and metrics are wired correctly — **not** a trustworthy edge. Treat every Phase-A "survivor" as a candidate to be re-run on real data, nothing more.
- **Phase B (the experiment — required before believing any result):** re-validate survivors on **vendor-grade historical IV/Greeks and quotes** — ORATS, Polygon options tier, or CBOE DataShop — which provide deep history and proper IV/Greeks/quote time series. A signal that survives Phase A but breaks on Phase B vendor data was an artifact. **No result is believed until it clears Phase B.**

---

## 3. Indicator / feature library

Build each indicator as a **pure, parameterized function** `f(data, params) -> series`, organized by layer:

- **Underlying — trend:** moving averages (SMA/EMA/etc.), MA crossovers, VWAP + bands, anchored VWAP, MACD, ADX/DMI, Ichimoku, Supertrend, linear-regression slope.
- **Underlying — momentum:** RSI (+ divergence/multi-timeframe), Stochastics, Stoch RSI, CCI, Williams %R, ROC/Momentum, MFI.
- **Underlying — volatility:** ATR, Bollinger (+ %B, bandwidth, squeeze), Keltner, Donchian, realized vol windows.
- **Underlying — volume:** raw volume, RVOL, OBV, A/D, Chaikin, Volume/Market Profile (POC, VAH/VAL), cumulative volume delta.
- **Underlying — structure/levels:** pivots (classic/Fib/Camarilla), prior-day H/L/C, opening range, premarket H/L, Fib levels, gaps, round numbers, patterns.
- **Option — Greeks (self-computed):** delta, gamma, theta, vega; higher-order (vanna, charm) optional.
- **Option — IV (self-computed) — [rev] PHASE-B-ONLY for belief:** IV level, IV rank/percentile (needs history), IV-minus-realized spread, skew, term structure. **These may be computed in Phase A for pipeline development, but no IV-derived signal is to be believed on Alpaca data.** Errors-in-variables: a noisy IV that reads "high" today is partly measurement error, which mechanically reverts tomorrow — this *fabricates* a tradeable-looking IV-mean-reversion edge that is pure noise reverting. **Flag IV-mean-reversion signals as especially suspect.**
- **Option — pricing/structure:** moneyness, DTE bucket (0DTE/1DTE/weekly), intrinsic vs extrinsic, distance to strike.
- **Market context:** index trend (SPX/NDX), futures (ES/NQ), breadth (TICK/TRIN/AD), VIX complex, time-of-day, day-of-week/OPEX, economic + earnings calendar.
- **Flow / microstructure — not backtestable on Alpaca history** (no historical quotes/flow); flag as live-only or Phase-B. **[rev]** Do not attempt to reconstruct spread from bars.

Deliverable: an indicator registry where each function declares its inputs, default params, **[rev]** and a `phase` tag (`A`-believable / `B`-only) declaring the lowest data phase at which its output may be trusted.

---

## 4. Hypothesis registry (the anti-data-mining core)

This is the most important non-engineering component.

- **Every candidate signal must be registered before it is tested**, with: a written economic rationale, the expected direction of effect, and pre-specified parameter ranges.
- **[rev] Count *configurations executed*, not just hypotheses registered.** Maintain a global counter of every distinct backtest configuration actually run — not only the named hypotheses. The hidden forks (ticker universe, DTE bucket, entry/exit timing, stop placement, sizing rule, the modeled-spread assumption, IV-solver settings, and the train/val/holdout split point) are each an implicit parameter. The multiple-testing correction in §6 must be driven by this executed-configuration count (wired from the §6.6 run-log), because deflating by only the registered-hypothesis count is anti-conservative — it ignores the garden of forking paths.
- **Do not brute-force the full combinatorial space.** A reasoned candidate set (tens, not tens of thousands) is the goal. If a combination has no economic story for why it should work, it doesn't get tested.
- Store the registry as a versioned file (e.g. `hypotheses.yaml`) so the search space is auditable after the fact.

---

## 5. Backtest engine

- **Event-driven and point-in-time correct.** No vectorized shortcut that peeks at future bars.
- **[rev] Explicit timing invariant (off-by-one-bar lookahead is the classic intraday bug):** a signal computed from the close of bar *t* cannot be known until bar *t* ends, so the **earliest permissible fill is the open of bar *t+1***. Encode this as an engine invariant, not a convention. Never fill on the same bar that generated the signal.
- **Realistic costs are mandatory and always on:**
  - Fill at the **worse** side of the spread, never the mid.
  - **[rev] The modeled spread is a first-class, swept parameter — not a detail.** With no historical quotes, the spread must be *modeled* (from moneyness/DTE/volume heuristics), and for cheap 0DTE contracts the entire expectancy is hostage to it. Sweep the spread assumption across a pessimism range and report expectancy across the whole range. **Any edge that only survives the optimistic end of the spread sweep is treated as dead.** Record the spread model as part of the configuration counted in §4.
  - Subtract commissions (model ~$0.65/contract/side as a default; make it configurable).
  - Apply slippage; model that a triggered stop becomes a **market** order with a poor fill in thin options. **[rev]** A fixed slippage understates the tail — in a thin 0DTE contract a stopped-out market order can fill far worse than the mean assumption. Model slippage with a fat-tailed component, not a constant.
- **Position sizing** per a defined risk rule (fixed fractional risk per trade), with the option's defined-risk nature (long premium = capped loss) handled correctly.
- **Outputs:** a full trade log (entry/exit/price/size/costs/reason, **[rev]** plus the signal-bar and fill-bar timestamps so the timing invariant is auditable) and an equity curve, both consumed by `metrics.py`.

Deliverable: `backtester.py` that takes (signal, data, cost model, sizing rule) and returns (trade_log, equity_curve).

---

## 6. Validation protocol (where most "edges" should die)

1. **Split immediately:** train / validation / **holdout**. Lock the holdout away; it is touched exactly once, at the very end. Prefer a holdout from a regime not studied during development. **[rev] Honest caveat:** Alpaca history is ~Feb-2024→present, almost entirely one regime, so a trailing-N-month holdout is *more of the same regime* — surviving it proves much less than a true out-of-regime holdout would. This is another reason Phase B (deep vendor history) is the real test, not Phase A.
2. **Develop on train, tune lightly on validation.** Tuning is minimal and justified.
3. **[rev] Parameter sensitivity AND trade independence:** a real edge is a broad plateau, not a sharp spike. If performance collapses when a parameter moves by one step, it is a curve-fit — reject it. Separately, **define and enforce trade independence**: intraday signals produce overlapping, serially-correlated trades. Use **purged + embargoed cross-validation** (López de Prado) and/or **block bootstrap**, and report the **effective sample size**, not the raw trade count. Inflated N inflates the t-stat and the DSR.
4. **Walk-forward analysis:** re-fit and test rolling forward through time; report performance separately across bull, chop, and (where data exists) stress regimes. **[rev]** With ~2.25 years you get only ~4–6 folds covering ~1–2 regimes — itself a small sample. Report the fold count and do not over-interpret a handful of folds; this limitation is a key reason for Phase-B vendor data.
5. **Multiple-testing correction:** apply the **Deflated Sharpe Ratio** and **White's Reality Check / Hansen's SPA test**, **[rev] driven by the §4 executed-configuration count (not the registered-hypothesis count)**. The best-of-N result must clear a far higher bar than a single hypothesis would. **[rev] Honest caveat:** under clustered, non-stationary intraday option returns and a fuzzy trial count, DSR/SPA are themselves approximate — they *reduce* false-discovery risk, they do not zero it. State this in the final report.
6. **[rev] Run-logging is part of validation, not just reproducibility.** Every backtest run — including every `passes_objective` query — is logged with its full configuration, so the executed-configuration count in §4/§6.5 is exact and so you can never silently re-run-until-it-passes. If you queried the validation set 50 times, the correction must know that.
7. **Open the holdout once.** If the survivor still holds on data it has never seen, it is a candidate. If not, log the lesson and move on. This is the expected outcome.

---

## 7. Forward / paper test (no real money yet)

- Run survivors live on an **Alpaca paper account** (and/or micro-size live) for weeks to months.
- This is the only truly out-of-sample test: it catches execution latency, real spreads, fill quality, and operator behavior that backtests cannot.
- Compare realized expectancy and slippage against backtest assumptions. **[rev]** Specifically, compare realized spread against the *modeled* spread sweep from §5 — if live spreads land at or beyond the pessimistic end, the edge is gone. If live materially underperforms the backtest, the cost model was too optimistic — fix it before proceeding.

---

## 8. Live deployment (only if it survives §6 and §7)

- Hard risk controls: per-trade risk limit, daily loss limit / kill-switch, max concurrent exposure, sizing for the tail (a bad day = a bad month, not a wipeout).
- Monitoring and logging of live vs expected performance; periodic re-validation (edges decay and crowd out).
- **Regulatory note for small accounts (verified 2026-05-31):** the FINRA Pattern Day Trader rule was eliminated effective **June 4, 2026** (SEC approved amendments to Rule 4210 on Apr 14, 2026; FINRA Reg Notice 26-10) — the $25,000 minimum and the day-trade-count cap are gone, replaced by a real-time intraday margin framework (brokers may phase in through **Oct 20, 2027**). A sub-$25k account can now day-trade without the old lockout. **However**, small-account economics still dominate: fixed costs and spreads are a large percentage drag on small positions (see §1 cost-hurdle pre-check), and proper per-trade sizing is hard with whole-contract minimums. Treat a small account as education/assay capital, not an income source, and size only what is fully affordable to lose.

---

## 9. Suggested tech stack (all free / open-source)

- **Language:** Python.
- **Broker/data SDK:** `alpaca-py` (`OptionHistoricalDataClient`, `StockHistoricalDataClient`, paper trading client). **[rev]** Note `requirements.txt` currently pins the legacy `alpaca-trade-api`; the research module needs `alpaca-py` instead.
- **Data wrangling:** `pandas` or `polars`; storage in **DuckDB** / Parquet.
- **Greeks/IV:** `py_vollib` / `py_vollib_vectorized` (Black-Scholes — **[rev]** the default for 0DTE) or **QuantLib** (American binomial/BAW — for longer-dated). Numerical IV inversion via `scipy.optimize`.
- **Risk-free rate:** FRED API (the repo already holds a `FRED_SECRET`). **[rev]** Move it and the Alpaca keys out of `backend/config.py` (plaintext, in git history) into env vars / `.env` before this module ships.
- **Backtesting:** custom event-driven engine preferred for correctness; `vectorbt` or `backtrader` acceptable only if the §5 timing invariant is rigorously enforced.
- **Stats / validation:** `numpy`, `scipy`, `statsmodels`; `mlfinlab` or a direct implementation for the **Deflated Sharpe Ratio**, **purged+embargoed combinatorial CV**, and **block bootstrap** (López de Prado tooling).
- **Reproducibility:** seed control, config files, and a logged record of every backtest run **[rev]** that feeds the executed-configuration count in §4/§6.

---

## 10. Build order (milestones)

1. **M1 — Data spine:** pull and store aligned underlying + option bars in DuckDB; build the **point-in-time** contract universe; verify point-in-time integrity and the signal→fill timing invariant. **[rev]** Record the `feed` (indicative) on every pull.
2. **M2 — Greeks/IV module:** self-compute IV and Greeks per bar (BS for 0DTE, American for longer-dated); sanity-check against a few live snapshot values from Alpaca. Label outputs approximate; tag IV features Phase-B-only.
3. **M3 — Indicator library + registry:** implement layer-1 indicators and the option-derived ones; build the hypothesis registry (§4) **with the phase tag and the executed-configuration counter**.
4. **M4 — Backtester with full cost model:** trade log + equity curve + `metrics.py`; **[rev]** modeled-spread sweep and fat-tailed slippage wired in from the start.
5. **M5 — Validation harness:** splits, walk-forward, parameter-sensitivity, trade-independence / effective-N, run-logging, and multiple-testing correction driven by the executed-configuration count.
6. **M6 — Run the reasoned hypothesis set;** honestly report survivors (expect few or none). Remember: a Phase-A survivor is only a candidate for Phase B.
7. **M7 — Phase-B re-validation** of any survivor on vendor IV/Greeks/quote data. **This is the experiment.**
8. **M8 — Paper/forward test** survivors on Alpaca paper; compare realized vs modeled spread.
9. **M9 — (conditional) small live deployment** with hard risk controls.

---

## 11. Non-negotiable guardrails (checklist for the receiving AI)

- [ ] No lookahead anywhere; all features point-in-time. **[rev]** Signal on close of bar *t* → fill no earlier than open of bar *t+1*; enforced as an engine invariant.
- [ ] **[rev]** The contract universe is built point-in-time (strikes listed/liquid at time *t*), never filtered from today's chain.
- [ ] Costs (worse-side fills, commissions, slippage) are always on, never disabled to improve results. **[rev]** The modeled spread is swept across a pessimism range; edges that survive only the optimistic end are dead. Slippage has a fat tail.
- [ ] The holdout set is opened exactly once, at the end. **[rev]** And it is acknowledged to be same-regime on Alpaca data, so weak.
- [ ] Objective is expectancy + risk constraints, **never win rate alone**.
- [ ] **[rev]** Every *executed configuration* (not just every registered hypothesis) is counted via the run-log and fed into the multiple-testing correction.
- [ ] **[rev]** Trade independence is defined; effective sample size (not raw N) feeds every statistic.
- [ ] Self-computed IV/Greeks are labeled approximate **[rev] (and indicative-feed-sourced on free Alpaca — two layers of error)**; IV-derived signals are tagged Phase-B-only; spread/flow signals are not claimed as backtested on Alpaca history.
- [ ] **[rev]** A positive Phase-A result is treated as uninterpretable until it survives Phase-B vendor data; the default expected conclusion is "no robust edge."

---

## 12. Known limitations to state honestly in any final report

- Shallow Alpaca history (~Feb 2024+) → weak regime coverage; stress-period behavior is untested without Phase-B data; the holdout and walk-forward folds are same-regime and few.
- **[rev]** Free-tier option data is from the **indicative feed** (calculated OPRA derivatives), which Alpaca itself says is unfit for testing strategy efficacy — so Phase-A results are pipeline checks, not edge evidence.
- Self-computed IV/Greeks from (indicative) trade prints are noisier than vendor data; IV-mean-reversion signals are especially prone to errors-in-variables artifacts.
- No historical option quotes → spread/liquidity dynamics not backtestable on Alpaca; the modeled spread dominates intraday-option P&L and is an assumption, not a measurement.
- **[rev]** Multiple-testing corrections (DSR/SPA) are approximate under clustered, non-stationary returns and an uncertain trial count; they reduce but do not eliminate false-discovery risk.
- Survivorship/selection effects in the contract universe must be checked (point-in-time construction).
- Any discovered edge is likely small, regime-dependent, and prone to decay once costs and crowding are accounted for.

---

## Sources (data claims verified 2026-05-31)

- [Historical Option Data — Alpaca Docs](https://docs.alpaca.markets/us/docs/historical-option-data) — history since Feb 2024.
- [OptionHistoricalDataClient — alpaca-py reference](https://alpaca.markets/sdks/python/api_reference/data/option/historical.html) — `get_option_bars`, `get_option_trades` (≤7 days), `get_option_latest_quote`; no historical-quotes method.
- [About Market Data API (Basic plan / indicative feed)](https://docs.alpaca.markets/us/docs/about-market-data-api) — free plan = IEX equities + indicative options feed.
- ["Indicative Pricing Feed for options" — Alpaca forum](https://forum.alpaca.markets/t/what-is-the-indicative-pricing-feed-for-options/14595) — indicative = calculated OPRA derivatives, "not... to test the efficacy of one's strategy."
- [FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10) — PDT rule eliminated effective Jun 4 2026; phase-in to Oct 20 2027.
