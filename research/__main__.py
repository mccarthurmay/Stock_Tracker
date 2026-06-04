"""CLI for the M1 data spine.

    python -m research smoke                 # end-to-end tiny demo + checks
    python -m research universe SPY --exp-lte 2026-06-30
    python -m research underlying SPY --days 5 --timeframe 1Min
    python -m research options SPY260619C00500000 --days 5
    python -m research align --option SPY260619C00500000
    python -m research check
    python -m research counts
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone, date

import json

import pandas as pd

from .client import AlpacaResearch
from .storage import ResearchStore
from . import (ingest, universe, integrity, greeks, hypotheses, features, registry,
               signals, metrics as metrics_mod, backtester, validation, stats, run,
               historical, scan, equity)
from .costs import CostModel
# Importing indicators registers them as a side effect.
from . import indicators  # noqa: F401


def _window(days: float) -> tuple[datetime, datetime]:
    # End 20 min ago to stay clear of the free tier's ~15-min delay.
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    return end - timedelta(days=days), end


def _print_checks(store) -> bool:
    results = integrity.run_all_checks(store)
    print("\nIntegrity checks:")
    for c in results:
        print("  " + str(c))
    ok = integrity.all_passed(results)
    print(f"  => {'ALL PASSED' if ok else 'FAILURES PRESENT'}")
    return ok


def cmd_counts(args, store):
    for t, n in store.table_counts().items():
        print(f"  {t:18s} {n:>10,}")


def cmd_universe(args, store):
    client = AlpacaResearch()
    df = universe.snapshot_universe(
        client, store, args.symbol.upper(),
        expiration_gte=args.exp_gte, expiration_lte=args.exp_lte,
        strike_gte=args.strike_gte, strike_lte=args.strike_lte,
    )
    print(f"Snapshotted {len(df)} contracts for {args.symbol.upper()} "
          f"(as_of {date.today()}).")


def cmd_underlying(args, store):
    client = AlpacaResearch()
    start, end = _window(args.days)
    n = ingest.ingest_underlying(client, store, args.symbol.upper(), start, end, args.timeframe)
    print(f"Stored {n} {args.timeframe} underlying bars for {args.symbol.upper()}.")


def cmd_options(args, store):
    client = AlpacaResearch()
    start, end = _window(args.days)
    syms = [s.upper() for s in args.symbols]
    n = ingest.ingest_options(client, store, syms, start, end, args.timeframe)
    print(f"Stored {n} {args.timeframe} option bars across {len(syms)} contract(s).")


def cmd_align(args, store):
    df = ingest.align(store, args.option.upper(), args.timeframe)
    if df.empty:
        print("No aligned rows (ingest underlying + this option for the same window/timeframe first).")
        return
    print(f"{len(df)} aligned rows for {args.option.upper()}. Head:")
    cols = ["ts", "knowable_at", "opt_close", "under_close", "strike", "opt_type", "feed"]
    print(df[cols].head(8).to_string(index=False))


def cmd_check(args, store):
    _print_checks(store)


_GREEK_VIEW = ["ts", "under_price", "opt_price", "tte_years", "model", "iv",
               "iv_converged", "delta", "gamma", "vega_pct", "theta_day"]


def cmd_greeks(args, store):
    sym = args.option.upper()
    r = greeks.compute_for(store, sym, args.timeframe, div_yield=args.q,
                           bs_max_dte=args.bs_max_dte, crr_steps=args.crr_steps,
                           price_source=args.price)
    print(f"{sym}: {r['rows']} rows, {r['converged']}/{r['total']} IV converged, "
          f"models={r['models']}")
    df = store.read_option_greeks(sym, args.timeframe)
    if not df.empty:
        print(df[_GREEK_VIEW].head(8).to_string(index=False))


def cmd_greeks_all(args, store):
    und = args.underlying.upper()
    r = greeks.compute_underlying(store, und, args.timeframe, div_yield=args.q,
                                  bs_max_dte=args.bs_max_dte, crr_steps=args.crr_steps,
                                  price_source=args.price)
    print(f"{und}: {r['contracts']} contracts, {r['rows']} rows, "
          f"{r['converged']}/{r['total']} IV converged, rate_src={r['rate_source']}")


def cmd_greeks_sanity(args, store):
    client = AlpacaResearch()
    rows = greeks.live_sanity(client, [s.upper() for s in args.symbols],
                              div_yield=args.q, bs_max_dte=args.bs_max_dte)
    print(pd.DataFrame(rows).to_string(index=False))


def cmd_indicators(args, store):
    specs = registry.by_layer(args.layer) if args.layer else registry.all_specs()
    print(f"{len(specs)} indicators"
          + (f" in layer '{args.layer}'" if args.layer else "") + ":")
    for s in specs:
        rng = f" sweep={s.param_ranges}" if s.param_ranges else ""
        print(f"  [{s.phase}] {s.name:16s} {s.layer:11s} params={s.params}{rng}")
        print(f"       {s.description}")


def cmd_hypotheses(args, store):
    hyps = hypotheses.load()
    summ = hypotheses.summarize(hyps)
    print(f"{summ['hypotheses']} hypotheses validated  "
          f"(phase A={summ['phase_A']}, phase B={summ['phase_B']})  "
          f"-> {summ['total_configs']} total configs\n")
    for h in hyps:
        print(f"  [{h.phase}] {h.id}  ({h.expected_direction}, {len(h.configs())} configs)")
        print(f"       uses: {', '.join(u.name for u in h.indicators)}")


def cmd_features(args, store):
    sym = args.option.upper()
    df = features.feature_frame(store, sym, args.timeframe)
    if df.empty:
        print(f"No data for {sym} (ingest bars + compute greeks first).")
        return
    if args.hypothesis:
        hyps = {h.id: h for h in hypotheses.load()}
        if args.hypothesis not in hyps:
            print(f"Unknown hypothesis {args.hypothesis!r}; known: {sorted(hyps)}")
            return
        h = hyps[args.hypothesis]
        config = h.configs()[0]  # first concrete config for the preview
        df = features.compute_for_config(df, config)
        cols = ["ts"] + list(config.keys())
        chash = hypotheses.config_hash(h.id, config)
        if args.record:
            n = store.record_config_run(chash, h.id, h.phase,
                                        json.dumps(config, default=str),
                                        dataset=sym, split="dev")
            print(f"recorded config {chash} for {h.id} (run_count={n}, phase={h.phase})")
        print(f"\n{h.id} [{h.phase}] config {chash}: {config}")
    else:
        names = args.indicators or ["rsi", "price_vs_sma", "realized_vol"]
        df = features.compute(df, names)
        cols = ["ts"] + names
    print(df[cols].tail(args.tail).to_string(index=False))


def cmd_config_count(args, store):
    total = store.distinct_config_count()
    a = store.distinct_config_count("A")
    b = store.distinct_config_count("B")
    print(f"Distinct configurations executed (feeds multiple-testing correction):")
    print(f"  total={total}  phase A={a}  phase B={b}")


def cmd_backtest(args, store):
    hyps = {h.id: h for h in hypotheses.load()}
    if args.hypothesis not in hyps:
        print(f"Unknown hypothesis {args.hypothesis!r}; known: {sorted(hyps)}")
        return
    h = hyps[args.hypothesis]
    config = h.configs()[args.config_idx]
    chash = hypotheses.config_hash(h.id, config)
    sym = args.option.upper()

    frame, sig = signals.signal_for_hypothesis(store, h, config, sym, args.timeframe)
    if frame.empty:
        print(f"No data for {sym} (ingest bars + compute greeks first).")
        return
    n_sig = int(sig.sum())
    print(f"Hypothesis {h.id} [{h.phase}] config {chash}  dataset={sym}")
    print(f"  config={config}")
    print(f"  entry signals: {n_sig} of {len(sig)} bars\n")

    bt_cfg = backtester.BacktestConfig(
        contracts=args.contracts, stop_loss_frac=args.stop,
        take_profit_frac=(None if args.take_profit < 0 else args.take_profit),
        max_hold_bars=args.max_hold)

    # Record the executed configuration ONCE (distinct-config ledger, §6.5),
    # then sweep the modeled spread (§5). Each sweep level is its own run row.
    store.record_config_run(chash, h.id, h.phase,
                            __import__("json").dumps(config, default=str),
                            dataset=sym, split=args.split)

    sweep = args.spread_sweep or [0.5, 1.0, 1.5, 2.0]
    print(f"{'spreadx':>7} {'trades':>7} {'effN':>6} {'win%':>6} {'expect':>9} "
          f"{'PF':>6} {'maxDD':>7} {'skew':>6} {'pass':>5}")
    for mult in sweep:
        cm = CostModel(spread_mult=mult)
        res = backtester.run_backtest(frame, sig, cost_model=cm, config=bt_cfg)
        m = metrics_mod.compute_metrics(res["trade_log"], res["equity_curve"])
        verdict = metrics_mod.passes_objective(m)
        store.record_backtest_run(
            config_hash=chash, hypothesis=h.id, phase=h.phase, dataset=sym,
            split=args.split, spread_mult=mult, metrics=m, passed=verdict.passed,
            reasons=" | ".join(verdict.reasons))
        print(f"{mult:7.2f} {m.n_trades:7d} {m.effective_n:6.1f} "
              f"{m.win_rate*100:6.1f} {m.expectancy:9.3f} {m.profit_factor:6.2f} "
              f"{m.max_drawdown*100:6.1f}% {m.return_skew:6.2f} "
              f"{'YES' if verdict.passed else 'no':>5}")

    print(f"\nObjective is expectancy + risk constraints, never win rate alone.")
    print(f"On the free indicative feed a positive result is NOT believable "
          f"(Phase-A; ROADMAP sec 2d). Worst-case spread is the honest read.")


def cmd_backtest_runs(args, store):
    df = store.read_backtest_runs(args.hypothesis)
    if df.empty:
        print("No backtest runs recorded yet.")
        return
    cols = ["run_ts", "hypothesis", "phase", "dataset", "spread_mult", "n_trades",
            "effective_n", "expectancy", "max_drawdown", "passed"]
    print(df[cols].to_string(index=False))


def cmd_deep_ingest(args, store):
    """Deep historical ingest via PIT front-week ATM contract construction."""
    client = AlpacaResearch()
    start = _date(args.start) if args.start else date(2024, 2, 5)
    end = _date(args.end) if args.end else None
    print(f"Deep-ingesting front-week ATM {args.underlying.upper()} from {start} "
          f"at {args.timeframe} (PIT contract construction)...")
    r = historical.deep_ingest(client, store, underlying=args.underlying.upper(),
                               start_date=start, end_date=end, timeframe=args.timeframe)
    print(f"  weeks={r['weeks']} contracts={r['contracts']} "
          f"option_bars={r['option_bars']} underlying_bars={r['underlying_bars']} "
          f"skipped_weeks={r['skipped_weeks']}")
    print("Now run: greeks-all, then run-all.")


def cmd_scan_ingest(args, store):
    """Deep-ingest a whole ticker-list file (front-week ATM call+put, recent window)."""
    client = AlpacaResearch()
    tickers = historical.read_ticker_list(args.file)
    end = _date(args.end) if args.end else None
    if args.start:
        start = _date(args.start)
    else:
        # recent window: default ~3 months back from end (or today)
        ref = end or date.today()
        start = ref - timedelta(days=args.lookback_days)
    print(f"Scan-ingesting {len(tickers)} tickers from {start} at {args.timeframe} "
          f"(PIT front-week ATM call+put)...")
    out = historical.scan_ingest(client, store, tickers, start, end, args.timeframe)
    print(f"\nDone: {out['with_data']}/{out['tickers']} tickers returned option data.")
    print("Now run: greeks-all per ticker (or scan-greeks), then scan-run.")


def cmd_equity_smoke(args, store):
    """Smoke-test the long-horizon factor backtest on real prices.

    Uses 12-1 MOMENTUM (computable lookahead-free from prices alone) to prove
    the plumbing: rebalance loop -> period returns -> DSR + monthly objective +
    train/holdout. The FF quality-value composite is the real target but needs
    filing-lagged fundamentals + a survivorship-free universe + deep history
    (see equity.py TODOs) — not available on the free tier.
    """
    client = AlpacaResearch()
    tickers = historical.read_ticker_list(args.file) if args.file else \
        ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "JPM", "XOM", "JNJ",
         "PG", "HD", "BAC", "KO", "PFE", "CVX", "WMT", "DIS", "CSCO", "INTC", "T"]
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else (end - timedelta(days=args.years * 365 + 400))
    print(f"Equity smoke: 12-1 momentum over {len(tickers)} names, "
          f"{start}..{end}, monthly rebalance (SIP feed, total-return adjusted).\n")
    print("NOTE: today's ticker list has SURVIVORSHIP BIAS (no delisted names) — "
          "this proves the engine and the DSR/holdout wiring; it is NOT a\n"
          "trustworthy factor result until the universe is point-in-time (ROADMAP §12).\n")

    prices = equity.monthly_total_return_panel(client, tickers, start, end)
    if prices.empty or prices.shape[0] < 6:
        print("Not enough monthly price history pulled.")
        return
    print(f"Price panel: {prices.shape[1]} names x {prices.shape[0]} month-ends "
          f"({prices.index[0].date()}..{prices.index[-1].date()})\n")

    # Honest trial counting: every (config) we evaluate is a trial for DSR.
    configs = [("long_only", equity.EquityConfig(quantile=0.3, long_short=False)),
               ("long_short", equity.EquityConfig(quantile=0.3, long_short=True))]
    n_trials = len(configs)

    print(f"{'config':>12} {'periods':>7} {'annRet':>8} {'annSR':>7} {'maxDD':>7} "
          f"{'skew':>6} {'DSR':>6} {'obj':>4} {'surv':>5}")
    results = {}
    for name, cfg in configs:
        bt = equity.run_equity_backtest(prices, equity.momentum_factor, cfg)
        if bt.empty:
            print(f"{name:>12}  (no periods)"); continue
        ev = equity.evaluate(bt, n_trials)
        results[name] = (bt, ev)
        print(f"{name:>12} {ev['n_periods']:7d} {ev['ann_return']*100:7.1f}% "
              f"{ev['sharpe_annual']:7.2f} {ev['max_drawdown']*100:6.1f}% "
              f"{ev['skew']:6.2f} {ev['dsr']:6.2f} "
              f"{'Y' if ev['objective_pass'] else 'n':>4} "
              f"{'YES' if ev['survives'] else 'no':>5}")

    # train/holdout split on the best config's return series (open holdout once)
    if results:
        best = max(results, key=lambda k: results[k][1]["sharpe_annual"])
        bt, _ = results[best]
        sp = validation.chronological_splits(bt["date"], train=0.7, val=0.0)
        tr = bt[sp["train"].mask(bt["date"])]
        ho = bt[sp["holdout"].mask(bt["date"])]
        print(f"\nHoldout check on best config ({best}), opened once:")
        for label, seg in [("train", tr), ("HOLDOUT", ho)]:
            if seg.empty:
                continue
            ev = equity.evaluate(seg, n_trials)
            print(f"  {label:>8}: periods={ev['n_periods']} annRet={ev['ann_return']*100:.1f}% "
                  f"annSR={ev['sharpe_annual']:.2f} maxDD={ev['max_drawdown']*100:.1f}%")

    print("\nSame apparatus as the options work: Sharpe deflated by trial count, "
          "monthly-re-frozen objective, holdout opened once. The deep SIP history "
          "(2016+) gives a real sample; the binding limit now is survivorship-free "
          "PIT membership + filing-lagged fundamentals (the equity.py TODOs).")


def cmd_equity_ff(args, store):
    """The REAL Fama-French quality-value strategy: z(BM)+z(OP)-z(INV), monthly
    rebalanced, with FILING-LAGGED fundamentals (no lookahead) over 2016+ SIP."""
    from . import factors_pit
    client = AlpacaResearch()
    tickers = historical.read_ticker_list(args.file) if args.file else \
        ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "JPM", "XOM", "JNJ",
         "PG", "HD", "BAC", "KO", "PFE", "CVX", "WMT", "DIS", "CSCO", "INTC", "T",
         "VZ", "MRK", "ABBV", "PEP", "ORCL", "COST", "MCD", "NKE", "TXN", "UNH"]
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    print(f"FF quality-value: z(BM)+z(OP)-z(INV), {len(tickers)} names, {start}..{end},")
    print("monthly rebalance, filing-lagged EDGAR fundamentals (no lookahead), SIP prices.\n")
    print("CAVEAT: filing-lag IS enforced; SURVIVORSHIP is NOT (today's large caps).")
    print("So this is the real strategy on real PIT fundamentals, but the universe")
    print("is still biased — treat a 'pass' as provisional (ROADMAP §12).\n")

    prices = equity.monthly_total_return_panel(client, tickers, start, end)
    if prices.empty or prices.shape[0] < 12:
        print("Not enough price history."); return
    print(f"Price panel: {prices.shape[1]} names x {prices.shape[0]} month-ends.")
    print("Fetching filing-lagged EDGAR fundamentals (streaming, ~0.12s/CIK)...", flush=True)
    pit = factors_pit.PITFundamentals(cache_facts=False)  # flat memory over 1000s of names
    panel = factors_pit.build_factor_panel(prices, list(prices.index), pit)
    if panel.empty:
        print("No PIT fundamentals assembled (EDGAR coverage?)."); return
    print(f"Factor panel: {len(panel)} (date,ticker) rows, "
          f"{panel['ticker'].nunique()} names with EDGAR data.\n")

    factor_fn = equity.ff_composite_factor_fn(panel)
    configs = [("long_only", equity.EquityConfig(quantile=0.3, long_short=False)),
               ("long_short", equity.EquityConfig(quantile=0.3, long_short=True))]
    n_trials = len(configs)
    print(f"{'config':>12} {'periods':>7} {'annRet':>8} {'annSR':>7} {'maxDD':>7} "
          f"{'skew':>6} {'DSR':>6} {'obj':>4} {'surv':>5}")
    results = {}
    for name, cfg in configs:
        bt = equity.run_equity_backtest(prices, factor_fn, cfg)
        if bt.empty:
            print(f"{name:>12}  (no periods)"); continue
        ev = equity.evaluate(bt, n_trials)
        results[name] = (bt, ev)
        print(f"{name:>12} {ev['n_periods']:7d} {ev['ann_return']*100:7.1f}% "
              f"{ev['sharpe_annual']:7.2f} {ev['max_drawdown']*100:6.1f}% "
              f"{ev['skew']:6.2f} {ev['dsr']:6.2f} "
              f"{'Y' if ev['objective_pass'] else 'n':>4} "
              f"{'YES' if ev['survives'] else 'no':>5}")

    if results:
        best = max(results, key=lambda k: results[k][1]["sharpe_annual"])
        bt, _ = results[best]
        sp = validation.chronological_splits(bt["date"], train=0.7, val=0.0)
        print(f"\nHoldout check on best config ({best}), opened once:")
        for label, seg in [("train", bt[sp["train"].mask(bt["date"])]),
                           ("HOLDOUT", bt[sp["holdout"].mask(bt["date"])])]:
            if seg.empty:
                continue
            ev = equity.evaluate(seg, n_trials)
            print(f"  {label:>8}: periods={ev['n_periods']} annRet={ev['ann_return']*100:.1f}% "
                  f"annSR={ev['sharpe_annual']:.2f} maxDD={ev['max_drawdown']*100:.1f}%")
    n_surv = sum(1 for _, (_, ev) in results.items() if ev["survives"])
    print(f"\n{'='*66}")
    if n_surv == 0:
        print("No config survives DSR. Even the real quality-value strategy on")
        print("filing-lagged data doesn't clear the data-mining-adjusted bar here")
        print("(and the universe is still survivorship-biased in its FAVOR).")
    else:
        print(f"{n_surv} config(s) survive DSR — provisional only: the universe is")
        print("still survivorship-biased. Next gate is a PIT delisted-aware universe.")
    print('='*66)


def cmd_equity_ci(args, store):
    """Backtest the screener's CI mean-reversion signal (backend/analysis.py) as
    a cross-sectional strategy, sweeping the lookback window + an MA-combo, with
    every variant counted as a DSR trial (the overfitting guard for 'which window
    works'). CI = buy names trading below their own mean-n*std band."""
    client = AlpacaResearch()
    tickers = historical.read_ticker_list(args.file) if args.file else \
        ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "JPM", "XOM", "JNJ",
         "PG", "HD", "BAC", "KO", "PFE", "CVX", "WMT", "DIS", "CSCO", "INTC", "T",
         "VZ", "MRK", "ABBV", "PEP", "ORCL", "COST", "MCD", "NKE", "TXN", "UNH"]
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    print(f"CI mean-reversion backtest, {len(tickers)} names, {start}..{end}, monthly rebalance.")
    print("Signal = buy names below their (mean - n*std) price band; rank by how far below.")
    print("CAVEAT: prices only (no fundamentals), but universe is still NOT survivorship-free.\n")

    daily = equity.daily_price_panel(client, tickers, start, end)
    if daily.empty or daily.shape[0] < 250:
        print("Not enough daily history."); return
    prices = equity.month_end(daily)
    print(f"Daily panel: {daily.shape[1]} names x {daily.shape[0]} days "
          f"-> {prices.shape[0]} month-ends.\n")

    # Avenue 1: sweep lookback windows. Avenue 2: CI+MA combo. long-only & L/S.
    # EVERY entry below is one DSR trial.
    ls = args.long_short
    variants = []
    for lb in args.windows:
        variants.append((f"CI{lb}", equity.ci_factor_fn(daily, lookback_days=lb)))
    for lb in args.windows:
        variants.append((f"CI{lb}+MA{args.ma}", equity.ci_ma_factor_fn(daily, ci_lookback=lb, ma_window=args.ma)))
    n_trials = len(variants) * (2 if ls else 1)

    cfg_lo = equity.EquityConfig(quantile=args.quantile, long_short=False)
    cfg_ls = equity.EquityConfig(quantile=args.quantile, long_short=True)
    print(f"Sweeping {len(variants)} signal variants x {'2 (long-only+L/S)' if ls else '1 (long-only)'} "
          f"= {n_trials} trials (each deflates the DSR).\n")
    print(f"{'variant':>14} {'side':>10} {'periods':>7} {'annRet':>8} {'annSR':>7} "
          f"{'maxDD':>7} {'DSR':>6} {'obj':>4} {'surv':>5}")
    results = {}
    for name, fn in variants:
        for side_name, cfg in ([("long_only", cfg_lo), ("long_short", cfg_ls)] if ls
                               else [("long_only", cfg_lo)]):
            bt = equity.run_equity_backtest(prices, fn, cfg)
            if bt.empty:
                print(f"{name:>14} {side_name:>10}  (no periods)"); continue
            ev = equity.evaluate(bt, n_trials)
            results[(name, side_name)] = (bt, ev)
            print(f"{name:>14} {side_name:>10} {ev['n_periods']:7d} {ev['ann_return']*100:7.1f}% "
                  f"{ev['sharpe_annual']:7.2f} {ev['max_drawdown']*100:6.1f}% {ev['dsr']:6.2f} "
                  f"{'Y' if ev['objective_pass'] else 'n':>4} {'YES' if ev['survives'] else 'no':>5}")

    if results:
        best = max(results, key=lambda k: results[k][1]["sharpe_annual"])
        bt, _ = results[best]
        sp = validation.chronological_splits(bt["date"], train=0.7, val=0.0)
        print(f"\nWhich window 'works' + holdout — best by validation SR was {best}, opened once:")
        for label, seg in [("train", bt[sp["train"].mask(bt["date"])]),
                           ("HOLDOUT", bt[sp["holdout"].mask(bt["date"])])]:
            if seg.empty:
                continue
            ev = equity.evaluate(seg, n_trials)
            print(f"  {label:>8}: periods={ev['n_periods']} annRet={ev['ann_return']*100:.1f}% "
                  f"annSR={ev['sharpe_annual']:.2f} maxDD={ev['max_drawdown']*100:.1f}%")
    n_surv = sum(1 for _, (_, ev) in results.items() if ev["survives"])
    print(f"\n{'='*68}")
    if n_surv == 0:
        print("No CI variant survives DSR. 'Which window works' is the wrong question —")
        print("the best window is the best-of-N fluke, and deflating by all N deletes it.")
    else:
        print(f"{n_surv} variant(s) survive DSR (provisional; universe survivorship-biased).")
    print('='*68)


def cmd_equity_selltriggers(args, store):
    """Compare 7 drawdown-DETECTION triggers on identical staggered-avg-down buy
    mechanics: CI-band, vol-spike, MA-cross (the 3 already tried) + trailing
    drawdown, market breadth, cross-asset (bonds>stocks), Donchian low (4 new).
    Each arms the same crash-dodge; run on SPY/QQQ/UPRO vs buy-and-hold."""
    import numpy as np
    client = AlpacaResearch()
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    s = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    e = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
    syms = [x.upper() for x in args.symbols]

    def pull(sym):
        df = client.stock_bars(sym, s, e, "1Day", adjustment="all", feed="sip")
        return df.set_index(pd.to_datetime(df["ts"]))["close"].sort_index() if not df.empty else None

    # market-wide signals computed once (on SPY / TLT / the S&P breadth panel)
    spx = pull("SPY")
    tlt = pull("TLT")
    print("Building market breadth (S&P 500 % above 50d MA)...", flush=True)
    sp500 = historical.read_ticker_list("backend/storage/ticker_lists/smp500.txt")
    panel = equity.daily_price_panel(client, sp500, start, end, progress_every=250)
    breadth = equity.breadth_series(panel, 50)
    # cross-asset risk-off: bonds outperform stocks over trailing 20d
    xa = None
    if tlt is not None and spx is not None:
        common = spx.index.intersection(tlt.index)
        bond_minus_stock = (tlt.reindex(common).pct_change(20) - spx.reindex(common).pct_change(20))
        xa = (bond_minus_stock > 0)        # bonds winning -> risk-off

    def arms_for(px):
        """Return {name: boolean arm series} for one symbol's price."""
        mean = px.rolling(90, min_periods=54).mean(); std = px.rolling(90, min_periods=54).std()
        ma50 = px.rolling(50, min_periods=30).mean()
        logr = np.log(px / px.shift(1)); rv = logr.rolling(20, min_periods=12).std()*np.sqrt(252)
        rvmed = rv.rolling(252, min_periods=120).median()
        peak = px.cummax(); ddown = px/peak - 1.0
        donch = px.rolling(60, min_periods=30).min()
        a = {
            "ci_band":      px < mean - 2.0*std,                  # already tried
            "vol_spike":    rv > rvmed*1.5,                       # already tried
            "ma_cross":     px < ma50,                            # already tried
            "trail_dd10":   ddown <= -0.10,                       # NEW: down >=10% from peak
            "breadth<40":   breadth.reindex(px.index).ffill() < 0.40,   # NEW: internals
            "donchian60":   px <= donch.shift(1),                 # NEW: new 60d low
        }
        if xa is not None:
            a["bonds>stocks"] = xa.reindex(px.index).fillna(False)   # NEW: cross-asset
        return a

    order = ["ci_band", "vol_spike", "ma_cross", "trail_dd10", "breadth<40", "donchian60", "bonds>stocks"]
    print(f"\n7 sell triggers x identical staggered avg-down buy, {syms}, {start}..{end}.\n")
    for sym in syms:
        px = pull(sym)
        if px is None or len(px) < 400:
            print(f"{sym}: insufficient history"); continue
        bh_bt = equity.overlay_backtest(px, pd.Series(1.0, index=px.index))
        bh = equity.evaluate(bh_bt.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                             1, periods_per_year=252, min_periods=120)
        print(f"=== {sym} ===  BUY&HOLD annRet {bh['ann_return']*100:.1f}%  SR {bh['sharpe_annual']:.2f}  maxDD {bh['max_drawdown']*100:.0f}%")
        print(f"  {'sell trigger':>14} {'new?':>4} {'%inv':>5} {'annRet':>7} {'SR':>5} {'Calmar':>7} {'maxDD':>6} {'vsB&H':>7} {'ddSav':>7}")
        arms = arms_for(px)
        for name in order:
            if name not in arms:
                continue
            exp = pd.Series(equity.staggered_overlay_exposure(px, arms[name], n_increments=args.increments,
                            decline_mode="cliff_sell", reentry_mode="avg_down"), index=px.index)
            bt = equity.overlay_backtest(px, exp)
            ev = equity.evaluate(bt, 1, periods_per_year=252, min_periods=120)
            is_new = "new" if name in ("trail_dd10", "breadth<40", "donchian60", "bonds>stocks") else "-"
            print(f"  {name:>14} {is_new:>4} {bt['n_held'].mean()*100:4.0f}% {ev['ann_return']*100:6.1f}% "
                  f"{ev['sharpe_annual']:5.2f} {ev['calmar']:7.2f} {ev['max_drawdown']*100:5.0f}% "
                  f"{(ev['ann_return']-bh['ann_return'])*100:+6.1f}% {(bh['max_drawdown']-ev['max_drawdown'])*100:+6.1f}%")
        print()
    print('='*96)
    print("All share the staggered avg-down BUY; only the de-risk TRIGGER differs. breadth &")
    print("bonds>stocks are market-wide (computed on S&P/TLT), the rest on each symbol's price.")
    print("Risk control, not alpha: these are MANY-variant methods, the best is data-mined.")
    print('='*96)


def cmd_equity_volcrash(args, store):
    """The combined BEST strategy: SELL on a volatility spike (the winning exit),
    BUY back STAGGERED via average-down on new lows (the winning re-entry). Run on
    each symbol vs buy-and-hold AND vs the original CI-triggered staggered overlay,
    so we see whether swapping the trigger to vol helps."""
    client = AlpacaResearch()
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    syms = [s.upper() for s in args.symbols]
    print(f"Vol-spike SELL + staggered avg-down BUY, {syms}, {start}..{end}.")
    print("Sell when realized vol > rolling median x{:.1f}; average back in on new lows;".format(args.vol_mult))
    print("reset when vol calms. vs buy-and-hold AND the CI-triggered version.\n")
    for sym in syms:
        try:
            df = client.stock_bars(sym, datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
                                   datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
                                   "1Day", adjustment="all", feed="sip")
        except Exception as e:
            print(f"{sym}: ERROR {type(e).__name__}"); continue
        if df.empty or len(df) < 400:
            print(f"{sym}: insufficient history"); continue
        px = df.set_index(pd.to_datetime(df["ts"]))["close"].sort_index()
        bh_bt = equity.overlay_backtest(px, pd.Series(1.0, index=px.index))
        bh = equity.evaluate(bh_bt.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                             1, periods_per_year=252, min_periods=120)
        print(f"=== {sym} ({px.index[0].date()}..{px.index[-1].date()}) ===")
        print(f"  BUY & HOLD:  annRet {bh['ann_return']*100:5.1f}%  SR {bh['sharpe_annual']:.2f}  "
              f"Calmar {bh['calmar']:.2f}  maxDD {bh['max_drawdown']*100:.0f}%")
        print(f"  {'strategy':>34} {'%inv':>5} {'annRet':>7} {'SR':>5} {'Calmar':>7} {'maxDD':>6} {'vsB&H':>7}")
        # CI-triggered staggered (the prior best crash overlay) for reference
        ci_exp = pd.Series(equity._crash_exposure_path(px, 90, 2.0, args.increments,
                           "cliff_sell", "avg_down"), index=px.index)
        ci_bt = equity.overlay_backtest(px, ci_exp)
        ci = equity.evaluate(ci_bt, 1, periods_per_year=252, min_periods=120)
        print(f"  {'CI-trigger + avg-down (prior best)':>34} {ci_bt['n_held'].mean()*100:4.0f}% "
              f"{ci['ann_return']*100:6.1f}% {ci['sharpe_annual']:5.2f} {ci['calmar']:7.2f} "
              f"{ci['max_drawdown']*100:5.0f}% {(ci['ann_return']-bh['ann_return'])*100:+6.1f}%")
        # vol-triggered staggered, sweep increments and decline mode
        for dm in ["cliff_sell", "ramp_sell"]:
            for inc in args.increments_sweep:
                exp = pd.Series(equity.volcrash_exposure_path(px, n_increments=inc,
                                vol_mult=args.vol_mult, decline_mode=dm, reentry_mode="avg_down"),
                                index=px.index)
                bt = equity.overlay_backtest(px, exp)
                ev = equity.evaluate(bt, 1, periods_per_year=252, min_periods=120)
                lbl = f"VOL-trigger {dm.split('_')[0]} + avg-down (inc={inc})"
                print(f"  {lbl:>34} {bt['n_held'].mean()*100:4.0f}% "
                      f"{ev['ann_return']*100:6.1f}% {ev['sharpe_annual']:5.2f} {ev['calmar']:7.2f} "
                      f"{ev['max_drawdown']*100:5.0f}% {(ev['ann_return']-bh['ann_return'])*100:+6.1f}%")
        print()
    print('='*94)
    print("Combines the two winners: vol-spike SELL (best exit) + staggered avg-down BUY")
    print("(best re-entry). vsB&H = annual return gap. Watch whether the vol trigger keeps")
    print("you invested more (less return drag) than the CI-band trigger while still dodging DD.")
    print('='*94)


def cmd_equity_buysell(args, store):
    """ACTIVE buy/sell timing on indices: pair a BUY rule with the new SELL
    indicators (MA cross, vol spike, RSI, CI bands) and see what it does to
    PROFIT vs buy-and-hold. Tests 'ci_dip' vs 'always' entry to isolate how much
    the CI-dip entry costs in missed upside."""
    client = AlpacaResearch()
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    syms = [s.upper() for s in args.symbols]
    # (buy_rule, sell_rules-tuple, label)
    strategies = [
        ("ci_dip", ("ci_recover",), "ci_dip -> ci_recover(-1sig)"),
        ("ci_dip", ("ci_upper",), "ci_dip -> ci_upper(+1sig)"),
        ("ci_dip", ("ma_cross",), "ci_dip -> MA cross"),
        ("ci_dip", ("vol_spike",), "ci_dip -> vol spike"),
        ("ci_dip", ("rsi",), "ci_dip -> RSI>=70"),
        ("ci_dip", ("ma_cross", "vol_spike"), "ci_dip -> MA or vol"),
        ("always", ("ma_cross",), "ALWAYS-in -> MA cross"),
        ("always", ("vol_spike",), "ALWAYS-in -> vol spike"),
        ("always", ("ma_cross", "vol_spike"), "ALWAYS-in -> MA or vol"),
    ]
    print(f"Active buy/sell timing on {syms}, {start}..{end}. vs buy-and-hold of each.")
    print("'ci_dip' enters only on a -2sig dip; 'always' enters whenever flat (isolates")
    print("the entry cost). Question: what does active timing do to PROFIT?\n")
    for sym in syms:
        try:
            df = client.stock_bars(sym, datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
                                   datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
                                   "1Day", adjustment="all", feed="sip")
        except Exception as e:
            print(f"{sym}: ERROR {type(e).__name__}"); continue
        if df.empty or len(df) < 400:
            print(f"{sym}: insufficient history"); continue
        px = df.set_index(pd.to_datetime(df["ts"]))["close"].sort_index()
        bh_bt = equity.index_buysell_backtest(px, buy_rule="always", sell_rules=())
        bh = equity.evaluate(bh_bt.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                             1, periods_per_year=252, min_periods=120)
        print(f"=== {sym} ({px.index[0].date()}..{px.index[-1].date()}) ===")
        print(f"  BUY & HOLD: annRet {bh['ann_return']*100:5.1f}%  SR {bh['sharpe_annual']:.2f}  maxDD {bh['max_drawdown']*100:.0f}%")
        print(f"  {'strategy':>28} {'%inv':>5} {'annRet':>7} {'SR':>5} {'maxDD':>6} {'vs B&H ret':>11}")
        for buy, sells, label in strategies:
            bt = equity.index_buysell_backtest(px, buy_rule=buy, sell_rules=sells,
                                               ci_lookback=args.ci_lookback, buy_sigma=args.buy_sigma,
                                               sell_sigma=args.sell_sigma, ma_window=args.ma)
            ev = equity.evaluate(bt, 1, periods_per_year=252, min_periods=120)
            dret = (ev['ann_return'] - bh['ann_return']) * 100
            print(f"  {label:>28} {bt['n_held'].mean()*100:4.0f}% {ev['ann_return']*100:6.1f}% "
                  f"{ev['sharpe_annual']:5.2f} {ev['max_drawdown']*100:5.0f}% {dret:+10.1f}%")
        print()
    print('='*86)
    print("vs B&H ret = annual return gap vs just holding. The CI-dip ENTRY sits in cash")
    print("waiting for -2sig dips that rarely come -> low %inv -> usually big return drag.")
    print("Active timing here trades PROFIT for lower drawdown; it doesn't add profit.")
    print('='*86)


def cmd_equity_overlays(args, store):
    """Compare drawdown-reduction overlays + combinations on each symbol.

    Methods (each -> daily exposure 0..1, combined by MULTIPLYING):
      crash  : CI crash-dodge (cliff_sell+avg_down)
      ma200  : Faber trend filter (in when price > 200d MA)
      voltgt : volatility targeting (exposure = 15% / realized vol)
      tsmom  : time-series momentum (in when trailing 12m return > 0)
    Each symbol vs buy-and-hold of itself. The question: which overlay (or combo)
    gives the best risk-adjusted / drawdown profile -- this is RISK CONTROL, the
    one place timing showed merit, not an alpha hunt."""
    client = AlpacaResearch()
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    syms = [s.upper() for s in args.symbols]

    def methods(px):
        return {
            "crash": equity.crash_exposure_series(px),
            "ma200": equity.ma_filter_exposure(px, 200),
            "voltgt": equity.vol_target_exposure(px, args.target_vol, 20),
            "tsmom": equity.ts_momentum_exposure(px, 252),
        }
    # singles + the intuitive combinations (multiply exposures)
    combos = [("crash",), ("ma200",), ("voltgt",), ("tsmom",),
              ("crash", "ma200"), ("ma200", "voltgt"), ("crash", "voltgt"),
              ("ma200", "tsmom"), ("crash", "ma200", "voltgt")]

    print(f"Drawdown overlays on {syms}, {start}..{end}, daily. vol target={args.target_vol:.0%}.")
    print("Each overlay -> exposure 0..1; combos MULTIPLY (fully invested only if all agree).\n")
    for sym in syms:
        try:
            df = client.stock_bars(sym, datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
                                   datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
                                   "1Day", adjustment="all", feed="sip")
        except Exception as e:
            print(f"{sym}: ERROR {type(e).__name__}"); continue
        if df.empty or len(df) < 400:
            print(f"{sym}: insufficient history"); continue
        px = df.set_index(pd.to_datetime(df["ts"]))["close"].sort_index()
        m = methods(px)
        bh_bt = equity.overlay_backtest(px, pd.Series(1.0, index=px.index))
        bh = equity.evaluate(bh_bt.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                             1, periods_per_year=252, min_periods=120)
        print(f"=== {sym} ({px.index[0].date()}..{px.index[-1].date()}) ===")
        print(f"  buy&hold: annRet {bh['ann_return']*100:5.1f}%  SR {bh['sharpe_annual']:.2f}  "
              f"Calmar {bh['calmar']:.2f}  maxDD {bh['max_drawdown']*100:.0f}%")
        print(f"  {'overlay':>22} {'%inv':>5} {'annRet':>7} {'SR':>5} {'Calmar':>7} {'maxDD':>6} "
              f"{'dSR':>6} {'ddSaved':>8}")
        rows = []
        for combo in combos:
            exp = m[combo[0]].copy()
            for extra in combo[1:]:
                exp = exp * m[extra]
            bt = equity.overlay_backtest(px, exp)
            ev = equity.evaluate(bt, 1, periods_per_year=252, min_periods=120)
            rows.append((combo, ev))
            print(f"  {'+'.join(combo):>22} {bt['n_held'].mean()*100:4.0f}% "
                  f"{ev['ann_return']*100:6.1f}% {ev['sharpe_annual']:5.2f} {ev['calmar']:7.2f} "
                  f"{ev['max_drawdown']*100:5.0f}% {ev['sharpe_annual']-bh['sharpe_annual']:+6.2f} "
                  f"{(bh['max_drawdown']-ev['max_drawdown'])*100:+7.1f}%")
        # best by Calmar (return per unit drawdown -- the risk-control objective)
        best = max(rows, key=lambda r: r[1]["calmar"])
        print(f"  -> best Calmar: {'+'.join(best[0])} ({best[1]['calmar']:.2f} vs B&H {bh['calmar']:.2f})\n")
    print('='*88)
    print("Risk-control view (Calmar/maxDD), NOT an alpha test. These overlays each have")
    print("MANY published variants; treating the best as significant would be data-mining.")
    print("voltgt+ma200 is the standard institutional risk overlay; crash adds little beyond it.")
    print('='*88)


def cmd_equity_crash_multi(args, store):
    """Crash-dodge overlay across MANY indices/ETFs, esp. leveraged (UPRO/TQQQ).

    Each symbol is timed on ITS OWN CI band and compared to buy-and-hold of
    ITSELF. One fixed mode-pair (default the index winner: cliff_sell + avg_down)
    and one sigma/increment, so each symbol = a clean head-to-head, not a sweep.

    Why leveraged ETFs are the interesting case: a 3x DAILY-rebalanced fund has
    volatility decay -- a deep drawdown compounds far worse than 3x and choppy
    markets bleed it -- so DODGING drawdowns is worth much more here than on SPY.
    Caveat: that also maximally amplifies the 'dodged COVID once' overfit, and
    leveraged ETFs have short/varied histories (UPRO/TQQQ ~2010, AVUV ~2019)."""
    client = AlpacaResearch()
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2010, 1, 1)
    syms = [s.upper() for s in args.symbols]
    dm, rm, sig, inc = args.decline_mode, args.reentry_mode, args.crash_sigma, args.increment
    print(f"Crash-dodge across {len(syms)} symbols, {start}..{end}, daily.")
    print(f"Mode: {dm}+{rm}, sigma={sig}, increments={inc}. Each vs buy-and-hold of itself.\n")
    print(f"{'symbol':>7} {'span':>11} {'%inv':>5} | {'STRAT annRet':>12} {'SR':>5} {'maxDD':>6} "
          f"| {'B&H annRet':>11} {'SR':>5} {'maxDD':>6} | {'dSR':>6} {'ddSaved':>8}")
    for sym in syms:
        try:
            df = client.stock_bars(sym, datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
                                   datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
                                   "1Day", adjustment="all", feed="sip")
        except Exception as e:
            print(f"{sym:>7}  ERROR {type(e).__name__}"); continue
        if df.empty or len(df) < 300:
            print(f"{sym:>7}  (insufficient history: {len(df)} bars)"); continue
        px = df.set_index(pd.to_datetime(df["ts"]))["close"].sort_index()
        bt = equity.spy_crash_overlay_backtest(px, ci_lookback=args.ci_lookback,
                                               crash_sigma=sig, n_increments=inc,
                                               decline_mode=dm, reentry_mode=rm)
        if bt.empty:
            print(f"{sym:>7}  (no overlay data)"); continue
        e = equity.evaluate(bt, 1, periods_per_year=252, min_periods=120)
        eb = equity.evaluate(bt.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                             1, periods_per_year=252, min_periods=120)
        span = f"{px.index[0].date():%y/%m}-{px.index[-1].date():%y/%m}"
        print(f"{sym:>7} {span:>11} {bt['n_held'].mean()*100:4.0f}% | "
              f"{e['ann_return']*100:11.1f}% {e['sharpe_annual']:5.2f} {e['max_drawdown']*100:5.0f}% | "
              f"{eb['ann_return']*100:10.1f}% {eb['sharpe_annual']:5.2f} {eb['max_drawdown']*100:5.0f}% | "
              f"{e['sharpe_annual']-eb['sharpe_annual']:+6.2f} {(eb['max_drawdown']-e['max_drawdown'])*100:+7.1f}%")
    print(f"\n{'='*92}")
    print("dSR = strat annSR - its own buy&hold annSR.  ddSaved = drawdown reduction.")
    print("Leveraged ETFs: vol-decay makes dodging drawdowns worth more -- but the edge")
    print("still rests on the SAME ~3-5 crashes (esp. COVID), so it's the SAME few-events")
    print("illusion, just amplified. Different symbols are NOT independent confirmations:")
    print("UPRO/SPXL are SPY, TQQQ/SOXL crash in the same events. Not DSR-significant.")
    print('='*92)


def cmd_equity_crash(args, store):
    """Single-asset crash-dodge overlay on SPY (the user's idea): sell all when
    SPY breaks below its CI band (black-swan), average back in incrementally as
    it keeps falling, stop on the turn, reset on recovery. vs buy-and-hold SPY."""
    client = AlpacaResearch()
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    print(f"SPY crash-dodge overlay, {start}..{end}, daily.")
    print("Sell all when SPY < mean-Nsig (black swan); average in as it falls;")
    print("reset to fully invested when it recovers above the CI mid. vs buy&hold SPY.\n")
    df = client.stock_bars("SPY", datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
                           datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
                           "1Day", adjustment="all", feed="sip")
    if df.empty or len(df) < 300:
        print("Not enough SPY history."); return
    spy = df.set_index(pd.to_datetime(df["ts"]))["close"].sort_index()
    print(f"SPY: {len(spy)} daily bars {spy.index[0].date()}..{spy.index[-1].date()}\n")

    # The 2x2 the user asked for: decline phase {cliff_sell, ramp_sell} x
    # re-entry phase {avg_down, ramp_up, cliff_up}. Each (mode-pair x sigma x incr)
    # is one DSR trial. cliff_sell+avg_down == the original crash overlay.
    declines = args.decline_modes
    reentries = args.reentry_modes
    combos = [(dm, rm, s, n) for dm in declines for rm in reentries
              for s in args.crash_sigmas for n in args.increments]
    n_trials = len(combos)
    base = equity.spy_crash_overlay_backtest(spy, ci_lookback=args.ci_lookback,
                                             crash_sigma=args.crash_sigmas[0], n_increments=args.increments[0])
    bh = equity.evaluate(base.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                         1, periods_per_year=252, min_periods=252)
    print(f"Buy-and-hold SPY: annRet {bh['ann_return']*100:.1f}%  annSR {bh['sharpe_annual']:.2f}  "
          f"Calmar {bh['calmar']:.2f}  maxDD {bh['max_drawdown']*100:.1f}%\n")
    print(f"decline=cliff_sell(dump)|ramp_sell(trend: cut into weakness)  "
          f"reentry=avg_down(mean-rev)|ramp_up(trend: add into strength)|cliff_up(snap back)")
    print(f"Sweeping {len(declines)}x{len(reentries)} modes x {len(args.crash_sigmas)} sig "
          f"x {len(args.increments)} incr = {n_trials} trials.\n")
    print(f"{'decline':>11} {'reentry':>9} {'sig':>4} {'inc':>4} {'%inv':>5} {'annRet':>7} "
          f"{'annSR':>6} {'Calmar':>7} {'maxDD':>6} {'DSR':>5} {'vsBH':>6} {'ddSav':>6}")
    results = {}
    # aggregate best per mode-pair for the summary
    for dm, rm, s, n in combos:
        bt = equity.spy_crash_overlay_backtest(spy, ci_lookback=args.ci_lookback,
                                               crash_sigma=s, n_increments=n,
                                               decline_mode=dm, reentry_mode=rm)
        if bt.empty:
            continue
        ev = equity.evaluate(bt, n_trials, periods_per_year=252, min_periods=252)
        results[(dm, rm, s, n)] = (bt, ev)
        dd_saved = bh["max_drawdown"] - ev["max_drawdown"]
        print(f"{dm:>11} {rm:>9} {s:4.1f} {n:4d} {bt['n_held'].mean()*100:4.0f}% "
              f"{ev['ann_return']*100:6.1f}% {ev['sharpe_annual']:6.2f} {ev['calmar']:7.2f} "
              f"{ev['max_drawdown']*100:5.0f}% {ev['dsr']:5.2f} "
              f"{ev['sharpe_annual']-bh['sharpe_annual']:+6.2f} {dd_saved*100:+6.1f}%")

    # per-mode-pair summary: avg Sharpe across its sigma/incr variants
    print(f"\nPer-mode-pair avg annSR (across sigma/incr) -- which PHILOSOPHY wins:")
    pairs = {}
    for (dm, rm, s, n), (_, ev) in results.items():
        pairs.setdefault((dm, rm), []).append(ev["sharpe_annual"])
    avg = lambda xs: sum(xs) / len(xs)
    for (dm, rm), srs in sorted(pairs.items(), key=lambda kv: -avg(kv[1])):
        tag = ("trend/trend" if (dm == "ramp_sell" and rm == "ramp_up") else
               "dump/mean-rev (orig)" if (dm == "cliff_sell" and rm == "avg_down") else
               f"{dm.split('_')[0]}/{rm.split('_')[0]}")
        print(f"  {dm:>11} + {rm:>9}  avgSR {avg(srs):.2f}  ({tag})")

    if results:
        best = max(results, key=lambda k: results[k][1]["sharpe_annual"])
        bt = results[best][0]
        sp = validation.chronological_splits(bt["date"], train=0.7, val=0.0)
        print(f"\nHoldout on best ({best[0]}+{best[1]}, sig={best[2]}, inc={best[3]}), opened once:")
        for label, seg in [("train", bt[sp["train"].mask(bt["date"])]),
                           ("HOLDOUT", bt[sp["holdout"].mask(bt["date"])])]:
            if seg.empty:
                continue
            e = equity.evaluate(seg, n_trials, periods_per_year=252, min_periods=60)
            eb = equity.evaluate(seg.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                                 1, periods_per_year=252, min_periods=60)
            print(f"  {label:>8}: strat annSR {e['sharpe_annual']:.2f} vs B&H {eb['sharpe_annual']:.2f} "
                  f"| strat maxDD {e['max_drawdown']*100:.0f}% vs B&H {eb['max_drawdown']*100:.0f}%")
    n_beat = sum(1 for _, (_, ev) in results.items() if ev["sharpe_annual"] > bh["sharpe_annual"])
    print(f"\n{'='*72}")
    print(f"Combos beating B&H on Sharpe: {n_beat}/{len(results)}.  DSR survivors: "
          f"{sum(1 for _,(_,ev) in results.items() if ev['survives'])}/{len(results)}.")
    print("HONEST CAVEAT: market timing -> P&L comes from a HANDFUL of crash events")
    print("(~3-5 in 2016-2026: 2018x2, COVID 2020, 2022, maybe 2024). Even a 'win' is")
    print("near-unfalsifiable on so few events -- the 'I dodged COVID once' trap. DSR")
    print("and the holdout are the honest read; ddSaved shows the risk-control angle.")
    print('='*72)


def cmd_equity_crash_stocks(args, store):
    """PER-STOCK crash timing: EACH name runs its own crash-dodge on its own CI
    band (sell that name when it crashes, re-buy on its own recovery). Pool
    equal-weight across held names. vs equal-weight buy-and-hold of the universe.
    Sweeps decline x reentry modes x sigma x increments (each a DSR trial)."""
    client = AlpacaResearch()
    tickers = historical.read_ticker_list(args.file) if args.file else \
        ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "JPM", "XOM", "JNJ",
         "PG", "HD", "BAC", "KO", "PFE", "CVX", "WMT", "DIS", "CSCO", "INTC", "T"]
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    print(f"PER-STOCK crash timing, {len(tickers)} names, {start}..{end}, daily.")
    print("Each stock runs its OWN crash-dodge on its OWN CI band; pool equal-weight")
    print("over held names. vs equal-weight buy-and-hold of the universe. PIT, costs on.\n")
    daily = equity.daily_price_panel(client, tickers, start, end)
    if daily.empty or daily.shape[0] < 300:
        print("Not enough daily history."); return
    print(f"Daily panel: {daily.shape[1]} names x {daily.shape[0]} days.\n")

    declines, reentries = args.decline_modes, args.reentry_modes
    combos = [(dm, rm, s, n) for dm in declines for rm in reentries
              for s in args.crash_sigmas for n in args.increments]
    n_trials = len(combos)
    base = equity.per_stock_crash_backtest(daily, ci_lookback=args.ci_lookback,
                                           crash_sigma=args.crash_sigmas[0], n_increments=args.increments[0])
    bh = equity.evaluate(base.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                         1, periods_per_year=252, min_periods=252)
    print(f"Equal-weight buy-and-hold: annRet {bh['ann_return']*100:.1f}%  annSR {bh['sharpe_annual']:.2f}  "
          f"Calmar {bh['calmar']:.2f}  maxDD {bh['max_drawdown']*100:.1f}%\n")
    print(f"Sweeping {len(declines)}x{len(reentries)} modes x {len(args.crash_sigmas)} sig "
          f"x {len(args.increments)} incr = {n_trials} trials.\n")
    print(f"{'decline':>11} {'reentry':>9} {'sig':>4} {'inc':>4} {'%inv':>5} {'annRet':>7} "
          f"{'annSR':>6} {'Calmar':>7} {'maxDD':>6} {'DSR':>5} {'vsBH':>6} {'ddSav':>6}")
    results = {}
    n_names = daily.shape[1]
    for dm, rm, s, n in combos:
        bt = equity.per_stock_crash_backtest(daily, ci_lookback=args.ci_lookback,
                                             crash_sigma=s, n_increments=n,
                                             decline_mode=dm, reentry_mode=rm)
        if bt.empty:
            continue
        ev = equity.evaluate(bt, n_trials, periods_per_year=252, min_periods=252)
        results[(dm, rm, s, n)] = (bt, ev)
        dd_saved = bh["max_drawdown"] - ev["max_drawdown"]
        # avg fraction of universe held (n_held is a count here)
        pct_inv = bt["n_held"].mean() / max(1, n_names) * 100
        print(f"{dm:>11} {rm:>9} {s:4.1f} {n:4d} {pct_inv:4.0f}% "
              f"{ev['ann_return']*100:6.1f}% {ev['sharpe_annual']:6.2f} {ev['calmar']:7.2f} "
              f"{ev['max_drawdown']*100:5.0f}% {ev['dsr']:5.2f} "
              f"{ev['sharpe_annual']-bh['sharpe_annual']:+6.2f} {dd_saved*100:+6.1f}%")

    print(f"\nPer-mode-pair avg annSR (which PHILOSOPHY wins per-stock):")
    pairs = {}
    for (dm, rm, s, n), (_, ev) in results.items():
        pairs.setdefault((dm, rm), []).append(ev["sharpe_annual"])
    avg = lambda xs: sum(xs) / len(xs)
    for (dm, rm), srs in sorted(pairs.items(), key=lambda kv: -avg(kv[1])):
        print(f"  {dm:>11} + {rm:>9}  avgSR {avg(srs):.2f}")
    if results:
        best = max(results, key=lambda k: results[k][1]["sharpe_annual"])
        bt = results[best][0]
        sp = validation.chronological_splits(bt["date"], train=0.7, val=0.0)
        print(f"\nHoldout on best ({best[0]}+{best[1]}, sig={best[2]}, inc={best[3]}), opened once:")
        for label, seg in [("train", bt[sp["train"].mask(bt["date"])]),
                           ("HOLDOUT", bt[sp["holdout"].mask(bt["date"])])]:
            if seg.empty:
                continue
            e = equity.evaluate(seg, n_trials, periods_per_year=252, min_periods=60)
            eb = equity.evaluate(seg.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                                 1, periods_per_year=252, min_periods=60)
            print(f"  {label:>8}: strat annSR {e['sharpe_annual']:.2f} vs B&H {eb['sharpe_annual']:.2f} "
                  f"| strat maxDD {e['max_drawdown']*100:.0f}% vs B&H {eb['max_drawdown']*100:.0f}%")
    n_beat = sum(1 for _, (_, ev) in results.items() if ev["sharpe_annual"] > bh["sharpe_annual"])
    print(f"\n{'='*72}")
    print(f"Combos beating B&H on Sharpe: {n_beat}/{len(results)}.  DSR survivors: "
          f"{sum(1 for _,(_,ev) in results.items() if ev['survives'])}/{len(results)}.")
    print("Per-stock means each name times its OWN crashes -- but most 'crashes' in a")
    print("single stock are idiosyncratic dips, not the ~5 market-wide events. Watch")
    print("whether per-stock timing helps or just churns vs holding the basket.")
    print('='*72)


def cmd_equity_civalue(args, store):
    """The user's combined strategy: BUY when price < mean-2sig AND fundamentally
    undervalued (filing-lagged FF value screen); SELL when price recovers to
    mean-1sig. The value screen is the value-trap filter the pure-CI tests
    lacked. Sweeps CI window x value quantile (each a DSR trial) vs buy-and-hold."""
    from . import factors_pit
    client = AlpacaResearch()
    tickers = historical.read_ticker_list(args.file) if args.file else \
        ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "JPM", "XOM", "JNJ",
         "PG", "HD", "BAC", "KO", "PFE", "CVX", "WMT", "DIS", "CSCO", "INTC", "T",
         "VZ", "MRK", "ABBV", "PEP", "ORCL", "COST", "MCD", "NKE", "TXN", "UNH"]
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    print(f"CI + VALUE combined strategy, {len(tickers)} names, {start}..{end}, DAILY event-driven.")
    print("BUY: price < mean-2sig AND fundamentally undervalued (filing-lagged FF screen).")
    print("SELL: price recovers to mean-1sig. Re-buy when both conditions re-fire.")
    print("vs buy-and-hold. Costs on. PIT (signal t -> act t+1). NOT survivorship-free.\n")

    daily = equity.daily_price_panel(client, tickers, start, end)
    if daily.empty or daily.shape[0] < 300:
        print("Not enough daily history."); return
    monthly = equity.month_end(daily)
    print(f"Daily panel: {daily.shape[1]} names x {daily.shape[0]} days. "
          f"Fetching filing-lagged EDGAR (streaming)...", flush=True)
    pit = factors_pit.PITFundamentals(cache_facts=False)
    panel = factors_pit.build_factor_panel(monthly, list(monthly.index), pit)
    if panel.empty:
        print("No PIT fundamentals assembled."); return
    print(f"Factor panel: {len(panel)} (date,ticker) rows, {panel['ticker'].nunique()} names.\n")

    hold = args.hold_forever
    mode = ("BUY-AND-HOLD the signal (no sell; once bought, held to the end)"
            if hold else f"buy@-{args.buy_sigma}sig, sell@-{args.sell_sigma}sig")
    # baseline buy-and-hold once
    base = equity.ci_value_timing_backtest(
        daily, equity.undervalued_mask_from_panel(daily, panel, 0.3),
        ci_lookback=args.windows[0], buy_sigma=args.buy_sigma, sell_sigma=args.sell_sigma,
        hold_forever=hold)
    bh_ev = equity.evaluate(base.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                            1, periods_per_year=252, min_periods=252)
    print(f"Buy-and-hold (always-in): annRet {bh_ev['ann_return']*100:.1f}%  "
          f"annSR {bh_ev['sharpe_annual']:.2f}  Calmar {bh_ev['calmar']:.2f}  "
          f"maxDD {bh_ev['max_drawdown']*100:.1f}%\n")

    combos = [(w, q) for w in args.windows for q in args.quantiles]
    n_trials = len(combos)
    print(f"Mode: {mode}.")
    print(f"Sweeping {len(args.windows)} CI-window x {len(args.quantiles)} value-quantile "
          f"= {n_trials} trials (each a DSR trial).\n")
    print(f"{'CIwin':>6} {'valQ':>5} {'avgHeld':>8} {'annRet':>8} {'annSR':>7} {'Calmar':>7} "
          f"{'maxDD':>7} {'DSR':>6} {'dSR vsBH':>9} {'surv':>5}")
    results = {}
    for w, q in combos:
        uv = equity.undervalued_mask_from_panel(daily, panel, q)
        bt = equity.ci_value_timing_backtest(daily, uv, ci_lookback=w,
                                             buy_sigma=args.buy_sigma, sell_sigma=args.sell_sigma,
                                             hold_forever=hold)
        if bt.empty:
            print(f"{w:6d} {q:5.2f}  (no data)"); continue
        ev = equity.evaluate(bt, n_trials, periods_per_year=252, min_periods=252)
        results[(w, q)] = (bt, ev)
        print(f"{w:6d} {q:5.2f} {bt['n_held'].mean():8.1f} {ev['ann_return']*100:7.1f}% "
              f"{ev['sharpe_annual']:7.2f} {ev['calmar']:7.2f} {ev['max_drawdown']*100:6.1f}% "
              f"{ev['dsr']:6.2f} {ev['sharpe_annual']-bh_ev['sharpe_annual']:+9.2f} "
              f"{'YES' if ev['survives'] else 'no':>5}")

    if results:
        best = max(results, key=lambda k: results[k][1]["sharpe_annual"])
        bt = results[best][0]
        sp = validation.chronological_splits(bt["date"], train=0.7, val=0.0)
        print(f"\nHoldout on best-Sharpe combo (CIwin={best[0]}, valQ={best[1]}), opened once:")
        for label, seg in [("train", bt[sp["train"].mask(bt["date"])]),
                           ("HOLDOUT", bt[sp["holdout"].mask(bt["date"])])]:
            if seg.empty:
                continue
            e = equity.evaluate(seg, n_trials, periods_per_year=252, min_periods=60)
            eb = equity.evaluate(seg.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                                 1, periods_per_year=252, min_periods=60)
            print(f"  {label:>8}: strat annSR {e['sharpe_annual']:.2f} vs B&H {eb['sharpe_annual']:.2f} "
                  f"| strat annRet {e['ann_return']*100:.1f}% vs B&H {eb['ann_return']*100:.1f}%")
    n_surv = sum(1 for _, (_, ev) in results.items() if ev["survives"])
    n_beat = sum(1 for _, (_, ev) in results.items() if ev["sharpe_annual"] > bh_ev["sharpe_annual"])
    print(f"\n{'='*72}")
    print(f"DSR survivors: {n_surv}/{len(results)}.  Beating B&H on Sharpe: {n_beat}/{len(results)}.")
    print("This adds the VALUE filter the pure-CI tests lacked (buy dips only in cheap")
    print("names). If the value screen has selection skill, THIS is where it shows -- a")
    print("dSR vsBH > 0 with DSR>0.95 would be the first thing to clear the bar.")
    print('='*72)


def cmd_equity_timing(args, store):
    """Daily event-driven CI timing with a SELL/take-profit rule:
    buy < mean-2sig; EXIT when price > mean+1sig OR the MA is falling. Tests
    whether the sell rule beats buy-and-hold, sweeping sell-sigma + MA window
    (each a DSR trial). Daily series -> 252 periods/yr."""
    client = AlpacaResearch()
    tickers = historical.read_ticker_list(args.file) if args.file else \
        ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "JPM", "XOM", "JNJ",
         "PG", "HD", "BAC", "KO", "PFE", "CVX", "WMT", "DIS", "CSCO", "INTC", "T",
         "VZ", "MRK", "ABBV", "PEP", "ORCL", "COST", "MCD", "NKE", "TXN", "UNH"]
    end = _date(args.end) if args.end else date.today()
    start = _date(args.start) if args.start else date(2016, 1, 1)
    print(f"CI timing + SELL rule, {len(tickers)} names, {start}..{end}, DAILY event-driven.")
    print("Buy: price < mean-2sig.  Sell/take-profit: price > mean+{0}sig OR MA falling."
          .format("S"))
    print("vs buy-and-hold (always-in, equal-weight). Costs on. PIT (signal t -> act t+1).\n")

    daily = equity.daily_price_panel(client, tickers, start, end)
    if daily.empty or daily.shape[0] < 300:
        print("Not enough daily history."); return
    print(f"Daily panel: {daily.shape[1]} names x {daily.shape[0]} days.\n")

    # Sweep COMBINATIONS of sell triggers (the user's question: can ANY mix get a
    # good DSR?). sigma / ma / rsi, alone and unioned. Each combo = one DSR trial.
    combos = [("sigma",), ("ma",), ("rsi",), ("sigma", "ma"),
              ("sigma", "rsi"), ("ma", "rsi"), ("sigma", "ma", "rsi")]
    n_trials = len(combos)

    # buy-and-hold baseline once (any combo's bh_ret is identical)
    base = equity.ci_timing_backtest(daily, ci_lookback=args.ci_lookback,
                                     buy_sigma=args.buy_sigma, sell_sigma=args.sell_sigma,
                                     ma_window=args.ma, rsi_sell=args.rsi_sell,
                                     sell_triggers=("sigma",))
    bh_ev = equity.evaluate(base.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                            1, periods_per_year=252, min_periods=252)
    print(f"Buy-and-hold (always-in): annRet {bh_ev['ann_return']*100:.1f}%  "
          f"annSR {bh_ev['sharpe_annual']:.2f}  Calmar {bh_ev['calmar']:.2f}  "
          f"maxDD {bh_ev['max_drawdown']*100:.1f}%\n")
    print(f"sell_sigma={args.sell_sigma}, ma={args.ma}d, rsi_sell={args.rsi_sell}. "
          f"Sweeping {n_trials} trigger combos (each a DSR trial).\n")
    print(f"{'sell triggers':>20} {'annRet':>8} {'annSR':>7} {'Calmar':>7} {'maxDD':>7} "
          f"{'DSR':>6} {'dSR vsBH':>9} {'ddSaved':>8} {'surv':>5}")
    results = {}
    for combo in combos:
        bt = equity.ci_timing_backtest(daily, ci_lookback=args.ci_lookback,
                                       buy_sigma=args.buy_sigma, sell_sigma=args.sell_sigma,
                                       ma_window=args.ma, rsi_sell=args.rsi_sell,
                                       sell_triggers=combo)
        if bt.empty:
            print(f"{'+'.join(combo):>20}  (no data)"); continue
        ev = equity.evaluate(bt, n_trials, periods_per_year=252, min_periods=252)
        results[combo] = (bt, ev)
        dd_saved = bh_ev["max_drawdown"] - ev["max_drawdown"]   # +ve = less drawdown than B&H
        print(f"{'+'.join(combo):>20} {ev['ann_return']*100:7.1f}% {ev['sharpe_annual']:7.2f} "
              f"{ev['calmar']:7.2f} {ev['max_drawdown']*100:6.1f}% {ev['dsr']:6.2f} "
              f"{ev['sharpe_annual']-bh_ev['sharpe_annual']:+9.2f} {dd_saved*100:+7.1f}% "
              f"{'YES' if ev['survives'] else 'no':>5}")

    # Drawdown-reducer lens: among combos, which gives the best Calmar / cuts the
    # most drawdown while giving up the least return vs buy-and-hold?
    if results:
        by_calmar = max(results, key=lambda k: results[k][1]["calmar"])
        ev = results[by_calmar][1]
        print(f"\nDrawdown-reducer view (the MA-as-risk-control question):")
        print(f"  best Calmar combo = {'+'.join(by_calmar)}: Calmar {ev['calmar']:.2f} "
              f"(B&H {bh_ev['calmar']:.2f}), maxDD {ev['max_drawdown']*100:.1f}% "
              f"(B&H {bh_ev['max_drawdown']*100:.1f}%), annRet {ev['ann_return']*100:.1f}% "
              f"(B&H {bh_ev['ann_return']*100:.1f}%)")
        # holdout on the best Sharpe combo
        best = max(results, key=lambda k: results[k][1]["sharpe_annual"])
        bt = results[best][0]
        sp = validation.chronological_splits(bt["date"], train=0.7, val=0.0)
        print(f"\nHoldout on best-Sharpe combo ({'+'.join(best)}), opened once:")
        for label, seg in [("train", bt[sp["train"].mask(bt["date"])]),
                           ("HOLDOUT", bt[sp["holdout"].mask(bt["date"])])]:
            if seg.empty:
                continue
            e = equity.evaluate(seg, n_trials, periods_per_year=252, min_periods=60)
            eb = equity.evaluate(seg.rename(columns={"ret": "_s", "bh_ret": "ret"}),
                                 1, periods_per_year=252, min_periods=60)
            print(f"  {label:>8}: strat annSR {e['sharpe_annual']:.2f} vs B&H {eb['sharpe_annual']:.2f} "
                  f"| strat Calmar {e['calmar']:.2f} vs B&H {eb['calmar']:.2f}")
    n_surv = sum(1 for _, (_, ev) in results.items() if ev["survives"])
    n_beat = sum(1 for _, (_, ev) in results.items() if ev["sharpe_annual"] > bh_ev["sharpe_annual"])
    print(f"\n{'='*72}")
    print(f"DSR survivors: {n_surv}/{len(results)}.  Combos beating B&H on Sharpe: {n_beat}/{len(results)}.")
    print("dSR vsBH = strat annSR - buy&hold annSR (the alpha test). ddSaved = drawdown")
    print("reduction vs B&H (the risk-control use). A real edge needs dSR>0 AND DSR>0.95.")
    print('='*72)


def cmd_scan_run(args, store):
    """Run the call-option hypotheses across a ticker-list universe; show the
    in-sample winners, the DSR deflation, and the holdout on the apparent best."""
    tickers = historical.read_ticker_list(args.file) if args.file else \
        sorted({s[:-15] for s in store.option_symbols() if len(s) > 15})
    bt_cfg = backtester.BacktestConfig(max_hold_bars=args.max_hold,
                                       take_profit_frac=(None if args.take_profit < 0 else args.take_profit),
                                       stop_loss_frac=args.stop)
    print(f"Scan: CALL-option hypotheses across {len(tickers)} tickers, spread x{args.spread} ...\n")
    out = scan.run_scan(store, tickers, timeframe=args.timeframe, spread_mult=args.spread,
                        bt_cfg=bt_cfg, dsr_threshold=args.dsr_threshold)
    rep = out["report"]
    if rep.empty:
        print("No trials produced (no call-option data for these tickers/timeframe).")
        return

    n_trials = out["n_trials"]
    winners = out["in_sample_winners"]
    print(f"Trials evaluated (ticker x config): {n_trials} across "
          f"{out['n_tickers']} tickers with data.")
    print(f"In-sample 'winners' (positive validation expectancy): {len(winners)} "
          f"({len(winners)/n_trials*100:.1f}% of trials)\n")

    if not winners.empty:
        print("Top 10 in-sample winners (what a naive scan would trade), with DSR:")
        print(f"{'ticker':>8} {'hypothesis':>26} {'trades':>7} {'expect':>9} {'SR/t':>6} {'DSR':>6} {'surv':>5}")
        for _, r in winners.head(10).iterrows():
            print(f"{r['ticker']:>8} {r['hypothesis']:>26} {int(r['n_trades']):7d} "
                  f"{r['expectancy']:9.3f} {r['sharpe_per_trade']:6.2f} {r['dsr']:6.2f} "
                  f"{'YES' if r['survives_dsr'] else 'no':>5}")

    print(f"\nSurvivors after DSR deflation (N_trials={n_trials}): {len(out['survivors'])}")

    ho = out["holdout"]
    if ho:
        print(f"\nHoldout opened ONCE on the best validation result "
              f"({ho['ticker']} / {ho['hypothesis']}):")
        print(f"  validation: expectancy={ho['val_expectancy']:.3f} SR/t={ho['val_sharpe']:.2f} DSR={ho['val_dsr']:.3f}")
        print(f"  HOLDOUT:    trades={ho['holdout_trades']} expectancy={ho['holdout_expectancy']:.3f} "
              f"sharpe={ho['holdout_sharpe']:.2f} -> {'PASSES' if ho['holdout_passes'] else 'FAILS'}")

    print(f"\n{'='*68}")
    if len(out["survivors"]) == 0:
        print("VERDICT: scanning produced in-sample 'winners' (max of noisy trials),")
        print("but NONE survive the data-mining-adjusted bar. This is the answer to")
        print("'scan until one works': the winners are the multiple-testing artifact,")
        print("and the correction (DSR, deflated by every trial) deletes them.")
    else:
        print(f"VERDICT: {len(out['survivors'])} config(s) cleared DSR. Check the holdout")
        print("above and then forward-paper-test before believing it (ROADMAP §6.6, §7).")
    print('='*68)


def cmd_run_all(args, store):
    """M6: run the full reasoned hypothesis set and report survivors honestly."""
    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    else:
        symbols = store.option_symbols(args.underlying.upper() if args.underlying else None)
    if not symbols:
        print("No option symbols in store. Ingest bars (and greeks) first.")
        return
    bt_cfg = backtester.BacktestConfig(max_hold_bars=args.max_hold,
                                       take_profit_frac=(None if args.take_profit < 0 else args.take_profit),
                                       stop_loss_frac=args.stop)
    print(f"M6: running reasoned hypothesis set over {len(symbols)} contract(s), "
          f"spread×{args.spread} ...\n")
    out = run.run_all(store, symbols, timeframe=args.timeframe, spread_mult=args.spread,
                      bt_cfg=bt_cfg, dsr_threshold=args.dsr_threshold)
    rep = out["report"]
    if rep.empty:
        print("No configs produced results (insufficient data).")
        return

    print(f"{out['n_hypotheses']} hypotheses, {out['n_configs']} configs, "
          f"N_trials(distinct)={out['n_trials']}\n")
    print(f"{'hypothesis':>28} {'phase':>5} {'cfg':>10} {'trades':>7} {'effN':>6} "
          f"{'expect':>9} {'SR/t':>7} {'DSR':>6} {'obj':>4} {'surv':>5}")
    for _, r in rep.iterrows():
        print(f"{r['hypothesis']:>28} {r['phase']:>5} {r['config_hash'][:8]:>10} "
              f"{int(r['n_trades']):7d} {r['effective_n']:6.1f} {r['expectancy']:9.3f} "
              f"{r['sharpe_per_trade']:7.2f} {r.get('dsr', 0):6.2f} "
              f"{'Y' if r['objective_pass'] else 'n':>4} "
              f"{'YES' if r.get('survives') else 'no':>5}")

    rc = out["reality_check"]
    print(f"\nWhite's Reality Check over {rc['n_strategies']} configs: "
          f"best={rc['best']}  p={rc['p_value']:.3f}  "
          f"({'no strategy beats luck at 5%' if rc['p_value'] > 0.05 else 'best beats luck at 5%'})")

    n_surv = len(out["survivors"])
    print(f"\n{'='*64}")
    if n_surv == 0:
        print("SURVIVORS: none. This is the expected, correct outcome (ROADMAP §0).")
        print("No robust edge found in the reasoned set under realistic costs +")
        print("multiple-testing correction. That is a success, not a failure.")
    else:
        print(f"SURVIVORS: {n_surv} config(s) cleared objective + DSR>{args.dsr_threshold}.")
        print("Treat with SUSPICION: this is Phase-A indicative data. A survivor is")
        print("only a CANDIDATE for the one-shot holdout, then Phase-B vendor data")
        print("and forward testing (ROADMAP §6.6, §7). Do NOT believe it yet.")
        for _, r in out["survivors"].iterrows():
            print(f"  - {r['hypothesis']} {r['config_hash'][:8]}: "
                  f"expectancy={r['expectancy']:.3f} DSR={r['dsr']:.3f} {r['config']}")
    print('='*64)


def _resolve_hyp(args):
    hyps = {h.id: h for h in hypotheses.load()}
    if args.hypothesis not in hyps:
        print(f"Unknown hypothesis {args.hypothesis!r}; known: {sorted(hyps)}")
        return None
    return hyps[args.hypothesis]


def cmd_validate(args, store):
    """Evaluate on train + validation (NOT holdout), report DSR vs distinct-N."""
    h = _resolve_hyp(args)
    if h is None:
        return
    config = h.configs()[args.config_idx]
    sym = args.option.upper()
    frame, _ = signals.signal_for_hypothesis(store, h, config, sym, args.timeframe)
    if frame.empty:
        print(f"No data for {sym}.")
        return
    splits = validation.chronological_splits(frame["ts"])
    bt_cfg = backtester.BacktestConfig(max_hold_bars=args.max_hold,
                                       take_profit_frac=(None if args.take_profit < 0 else args.take_profit),
                                       stop_loss_frac=args.stop)
    print(f"{h.id} [{h.phase}] config {hypotheses.config_hash(h.id, config)} on {sym}")
    print(f"  splits: train {splits['train'].start.date()}..{splits['train'].end.date()} | "
          f"val ..{splits['validation'].end.date()} | HOLDOUT LOCKED ..{splits['holdout'].end.date()}\n")
    print(f"{'split':>11} {'trades':>7} {'effN':>6} {'expect':>9} {'sharpe':>7} {'maxDD':>7} {'pass':>5}")
    last_m = None
    for name in ("train", "validation"):
        m = validation.evaluate_split(store, h, config, sym, splits[name],
                                      args.timeframe, args.spread, bt_cfg)
        v = metrics_mod.passes_objective(m)
        print(f"{name:>11} {m.n_trades:7d} {m.effective_n:6.1f} {m.expectancy:9.3f} "
              f"{m.sharpe:7.2f} {m.max_drawdown*100:6.1f}% {'YES' if v.passed else 'no':>5}")
        last_m = m

    # Deflated Sharpe on validation, deflated by the distinct-config count.
    res = backtester.run_backtest(
        frame[splits['validation'].mask(frame['ts'])].reset_index(drop=True),
        signals.signal_for_hypothesis(store, h, config, sym, args.timeframe)[1][
            splits['validation'].mask(frame['ts'])].reset_index(drop=True),
        cost_model=CostModel(spread_mult=args.spread), config=bt_cfg)
    r = metrics_mod.per_trade_returns(res["trade_log"])
    n_trials = max(store.distinct_config_count(), 1)
    sr, _, _ = stats.sharpe_stats(r)
    dsr = stats.deflated_sharpe_ratio(sr, r, n_trials)
    print(f"\nDeflated Sharpe (validation), N_trials={n_trials} distinct configs:")
    print(f"  per-trade SR={sr:.3f}  must beat E[max]={dsr['benchmark_sr']:.3f}  "
          f"-> DSR={dsr['dsr']:.3f}  (n_obs={dsr['n_obs']})")
    print(f"  {'SURVIVES' if (dsr['dsr'] or 0) > 0.95 else 'does NOT survive'} the "
          f"data-mining-adjusted bar (DSR>0.95).")
    print(f"\nReminder: holdout NOT opened here. On the indicative free feed a "
          f"pass is still Phase-A only (ROADMAP sec 2d).")


def cmd_walk_forward(args, store):
    h = _resolve_hyp(args)
    if h is None:
        return
    config = h.configs()[args.config_idx]
    sym = args.option.upper()
    frame, _ = signals.signal_for_hypothesis(store, h, config, sym, args.timeframe)
    if frame.empty:
        print(f"No data for {sym}.")
        return
    folds = validation.walk_forward_windows(frame["ts"], n_folds=args.folds,
                                            anchored=args.anchored)
    bt_cfg = backtester.BacktestConfig(max_hold_bars=args.max_hold,
                                       take_profit_frac=(None if args.take_profit < 0 else args.take_profit),
                                       stop_loss_frac=args.stop)
    print(f"{h.id} walk-forward, {len(folds)} folds ({'anchored' if args.anchored else 'rolling'}) on {sym}")
    print(f"  NOTE: ~one regime in Alpaca history -> few, same-regime folds; "
          f"interpret cautiously (ROADMAP sec 6.4)\n")
    print(f"{'fold':>5} {'test window':>23} {'trades':>7} {'expect':>9} {'sharpe':>7} {'pass':>5}")
    for k, fold in enumerate(folds):
        m = validation.evaluate_split(store, h, config, sym, fold["test"],
                                      args.timeframe, args.spread, bt_cfg)
        v = metrics_mod.passes_objective(m)
        win = f"{fold['test'].start.date()}..{fold['test'].end.date()}"
        print(f"{k:5d} {win:>23} {m.n_trades:7d} {m.expectancy:9.3f} "
              f"{m.sharpe:7.2f} {'YES' if v.passed else 'no':>5}")


def cmd_sensitivity(args, store):
    h = _resolve_hyp(args)
    if h is None:
        return
    sym = args.option.upper()
    bt_cfg = backtester.BacktestConfig(max_hold_bars=args.max_hold,
                                       take_profit_frac=(None if args.take_profit < 0 else args.take_profit),
                                       stop_loss_frac=args.stop)
    df = validation.parameter_sensitivity(store, h, sym, split=None,
                                          timeframe=args.timeframe,
                                          spread_mult=args.spread, bt_cfg=bt_cfg)
    if df.empty:
        print(f"No data for {sym}.")
        return
    print(f"{h.id} parameter sensitivity on {sym} ({len(df)} configs):")
    print(f"  a real edge is a broad PLATEAU, not a spike (ROADMAP sec 6.3)\n")
    for _, row in df.iterrows():
        print(f"  {row['config_hash']}  expectancy={row['expectancy']:9.3f}  "
              f"sharpe={row['sharpe']:6.2f}  n={int(row['n_trades'])}  {row['config']}")
    if "is_spiky" in df.attrs:
        verdict = "SPIKY (curve-fit risk)" if df.attrs["is_spiky"] else "plateau-like"
        print(f"\n  spread of expectancy across configs={df.attrs['plateau_spread']:.3f} "
              f"-> {verdict}")


def cmd_reality_check(args, store):
    """White's Reality Check across all configs of a hypothesis (best-of-N)."""
    h = _resolve_hyp(args)
    if h is None:
        return
    sym = args.option.upper()
    bt_cfg = backtester.BacktestConfig(max_hold_bars=args.max_hold,
                                       take_profit_frac=(None if args.take_profit < 0 else args.take_profit),
                                       stop_loss_frac=args.stop)
    candidates = {}
    for cfg in h.configs():
        frame, sig = signals.signal_for_hypothesis(store, h, cfg, sym, args.timeframe)
        if frame.empty:
            continue
        res = backtester.run_backtest(frame, sig, cost_model=CostModel(spread_mult=args.spread),
                                      config=bt_cfg)
        r = metrics_mod.per_trade_returns(res["trade_log"])
        if r.size >= 2:
            candidates[hypotheses.config_hash(h.id, cfg)] = r
    if not candidates:
        print(f"No usable configs/trades for {sym}.")
        return
    rc = stats.whites_reality_check(candidates, n_boot=args.n_boot, seed=0)
    print(f"{h.id} White's Reality Check over {rc['n_strategies']} configs on {sym}:")
    print(f"  best config={rc['best']}  best_mean_return={rc.get('best_mean', 0):.4f}")
    print(f"  bootstrap p-value={rc['p_value']:.3f}  (n_boot={rc['n_boot']})")
    print(f"  => best survivor is {'NOT ' if rc['p_value'] > 0.05 else ''}"
          f"distinguishable from luck at 5%.")


def cmd_holdout(args, store):
    """Open the holdout EXACTLY ONCE (ROADMAP sec 6.1). Refuses a second open."""
    h = _resolve_hyp(args)
    if h is None:
        return
    config = h.configs()[args.config_idx]
    chash = hypotheses.config_hash(h.id, config)
    sym = args.option.upper()
    prior = store.holdout_already_opened(h.id, sym)
    if prior is not None and not args.force_show:
        print(f"REFUSED: holdout for ({h.id}, {sym}) was already opened at "
              f"{prior['opened_ts']} (expectancy={prior['expectancy']}, "
              f"passed={prior['passed']}). The holdout is opened EXACTLY ONCE.")
        return
    if prior is not None:
        print(f"(showing prior holdout result; not re-opening)\n  {prior}")
        return
    frame, _ = signals.signal_for_hypothesis(store, h, config, sym, args.timeframe)
    if frame.empty:
        print(f"No data for {sym}.")
        return
    splits = validation.chronological_splits(frame["ts"])
    bt_cfg = backtester.BacktestConfig(max_hold_bars=args.max_hold,
                                       take_profit_frac=(None if args.take_profit < 0 else args.take_profit),
                                       stop_loss_frac=args.stop)
    m = validation.evaluate_split(store, h, config, sym, splits["holdout"],
                                  args.timeframe, args.spread, bt_cfg)
    v = metrics_mod.passes_objective(m)
    store.record_holdout_open(hypothesis=h.id, dataset=sym, config_hash=chash,
                              expectancy=m.expectancy, passed=v.passed,
                              reasons=" | ".join(v.reasons))
    print(f"HOLDOUT OPENED ONCE for {h.id} on {sym} (now locked):")
    print(f"  trades={m.n_trades} effN={m.effective_n} expectancy={m.expectancy:.3f} "
          f"maxDD={m.max_drawdown:.1%} skew={m.return_skew:.2f}")
    for r in v.reasons:
        print(f"    {r}")
    print(f"  => {'CANDIDATE (survives holdout)' if v.passed else 'rejected on holdout - log the lesson, move on'}")


def cmd_smoke(args, store):
    symbol = args.symbol.upper()
    tf = args.timeframe
    today = date.today()
    client = AlpacaResearch()

    print(f"[1/6] Snapshotting {symbol} universe (expiring within {args.exp_days} days)...")
    uni = universe.snapshot_universe(
        client, store, symbol,
        expiration_gte=today, expiration_lte=today + timedelta(days=args.exp_days),
    )
    if uni.empty:
        print("  No contracts returned — aborting smoke test.")
        return
    print(f"  {len(uni)} contracts.")

    print(f"[2/6] Ingesting {symbol} {tf} underlying bars (last {args.days}d)...")
    start, end = _window(args.days)
    n_u = ingest.ingest_underlying(client, store, symbol, start, end, tf)
    print(f"  {n_u} underlying bars.")
    if n_u == 0:
        print("  No underlying bars — aborting.")
        return

    spot = store.read_underlying_bars(symbol, tf)["close"].iloc[-1]
    print(f"  Spot ~ {spot:.2f}")

    print("[3/6] Picking nearest-expiry ATM call + put...")
    expiries = sorted({d for d in uni["expiry"] if d >= today})
    if not expiries:
        print("  No future expiries in window — aborting.")
        return
    near = expiries[0]
    leg = uni[uni["expiry"] == near].copy()
    leg["dist"] = (leg["strike"] - spot).abs()
    chosen = []
    for opt_type in ("call", "put"):
        side = leg[leg["opt_type"] == opt_type].sort_values("dist")
        if not side.empty:
            chosen.append(side.iloc[0]["option_symbol"])
    print(f"  expiry {near}: {chosen}")
    if not chosen:
        print("  No contracts to pull — aborting.")
        return

    print(f"[4/6] Ingesting {tf} option bars for {len(chosen)} contract(s)...")
    n_o = ingest.ingest_options(client, store, chosen, start, end, tf)
    print(f"  {n_o} option bars.")

    print("[5/6] Self-computing IV + Greeks per bar...")
    for sym in chosen:
        g = greeks.compute_for(store, sym, tf)
        print(f"  {sym}: {g['converged']}/{g['total']} IV converged, models={g['models']}")

    print("[6/6] Verifying point-in-time integrity...")
    ok = _print_checks(store)

    print("\nTable counts:")
    cmd_counts(args, store)

    if n_o:
        print(f"\nAligned sample for {chosen[0]}:")
        df = ingest.align(store, chosen[0], tf)
        if not df.empty:
            cols = ["ts", "knowable_at", "opt_close", "under_close", "strike", "opt_type", "feed"]
            print(df[cols].head(6).to_string(index=False))
    print(f"\nSmoke test {'OK' if ok else 'completed with check FAILURES'}.")


def _date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="research", description="M1 data spine")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("counts", help="row counts per table")
    sp.set_defaults(func=cmd_counts)

    sp = sub.add_parser("universe", help="snapshot the contract universe")
    sp.add_argument("symbol")
    sp.add_argument("--exp-gte", type=_date, dest="exp_gte")
    sp.add_argument("--exp-lte", type=_date, dest="exp_lte")
    sp.add_argument("--strike-gte", type=float, dest="strike_gte")
    sp.add_argument("--strike-lte", type=float, dest="strike_lte")
    sp.set_defaults(func=cmd_universe)

    sp = sub.add_parser("underlying", help="ingest underlying bars")
    sp.add_argument("symbol")
    sp.add_argument("--days", type=float, default=5)
    sp.add_argument("--timeframe", default="1Min")
    sp.set_defaults(func=cmd_underlying)

    sp = sub.add_parser("options", help="ingest option bars")
    sp.add_argument("symbols", nargs="+")
    sp.add_argument("--days", type=float, default=5)
    sp.add_argument("--timeframe", default="1Min")
    sp.set_defaults(func=cmd_options)

    sp = sub.add_parser("align", help="join an option to the underlying")
    sp.add_argument("--option", required=True)
    sp.add_argument("--timeframe", default="1Min")
    sp.set_defaults(func=cmd_align)

    sp = sub.add_parser("check", help="run integrity checks")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("greeks", help="compute IV+Greeks for one option")
    sp.add_argument("--option", required=True)
    sp.add_argument("--timeframe", default="1Min")
    sp.add_argument("--q", type=float, default=0.0, help="continuous dividend yield")
    sp.add_argument("--bs-max-dte", type=int, default=2, dest="bs_max_dte")
    sp.add_argument("--crr-steps", type=int, default=160, dest="crr_steps")
    sp.add_argument("--price", choices=["vwap", "close"], default="vwap")
    sp.set_defaults(func=cmd_greeks)

    sp = sub.add_parser("greeks-all", help="compute IV+Greeks for all options of an underlying")
    sp.add_argument("--underlying", required=True)
    sp.add_argument("--timeframe", default="1Min")
    sp.add_argument("--q", type=float, default=0.0)
    sp.add_argument("--bs-max-dte", type=int, default=2, dest="bs_max_dte")
    sp.add_argument("--crr-steps", type=int, default=160, dest="crr_steps")
    sp.add_argument("--price", choices=["vwap", "close"], default="vwap")
    sp.set_defaults(func=cmd_greeks_all)

    sp = sub.add_parser("greeks-sanity", help="compare our IV/Greeks to Alpaca live snapshot")
    sp.add_argument("symbols", nargs="+")
    sp.add_argument("--q", type=float, default=0.0)
    sp.add_argument("--bs-max-dte", type=int, default=2, dest="bs_max_dte")
    sp.set_defaults(func=cmd_greeks_sanity)

    sp = sub.add_parser("indicators", help="list registered indicators")
    sp.add_argument("--layer", default=None, help="filter by layer")
    sp.set_defaults(func=cmd_indicators)

    sp = sub.add_parser("hypotheses", help="validate + list hypotheses.yaml")
    sp.set_defaults(func=cmd_hypotheses)

    sp = sub.add_parser("features", help="compute indicators onto an option's bars")
    sp.add_argument("--option", required=True)
    sp.add_argument("--timeframe", default="1Min")
    sp.add_argument("--indicators", nargs="*", help="indicator names (default: a few)")
    sp.add_argument("--hypothesis", default=None, help="compute one hypothesis's first config")
    sp.add_argument("--record", action="store_true", help="record the config in the run ledger")
    sp.add_argument("--tail", type=int, default=8)
    sp.set_defaults(func=cmd_features)

    sp = sub.add_parser("config-count", help="distinct executed configs (for §6 correction)")
    sp.set_defaults(func=cmd_config_count)

    sp = sub.add_parser("backtest", help="backtest a hypothesis with the always-on cost model + spread sweep")
    sp.add_argument("--hypothesis", required=True)
    sp.add_argument("--option", required=True)
    sp.add_argument("--timeframe", default="1Min")
    sp.add_argument("--config-idx", type=int, default=0, dest="config_idx",
                    help="which concrete config of the hypothesis to run")
    sp.add_argument("--contracts", type=int, default=1)
    sp.add_argument("--stop", type=float, default=0.5, help="stop-loss fraction of entry premium")
    sp.add_argument("--take-profit", type=float, default=1.0, dest="take_profit",
                    help="take-profit fraction (-1 to disable)")
    sp.add_argument("--max-hold", type=int, default=60, dest="max_hold")
    sp.add_argument("--split", default="dev")
    sp.add_argument("--spread-sweep", type=float, nargs="*", dest="spread_sweep",
                    help="spread multipliers to sweep (default 0.5 1.0 1.5 2.0)")
    sp.set_defaults(func=cmd_backtest)

    sp = sub.add_parser("backtest-runs", help="show recorded backtest runs")
    sp.add_argument("--hypothesis", default=None)
    sp.set_defaults(func=cmd_backtest_runs)

    def _add_eval_args(p, with_idx=True):
        p.add_argument("--hypothesis", required=True)
        p.add_argument("--option", required=True)
        p.add_argument("--timeframe", default="1Min")
        if with_idx:
            p.add_argument("--config-idx", type=int, default=0, dest="config_idx")
        p.add_argument("--spread", type=float, default=1.0)
        p.add_argument("--stop", type=float, default=0.5)
        p.add_argument("--take-profit", type=float, default=1.0, dest="take_profit")
        p.add_argument("--max-hold", type=int, default=60, dest="max_hold")

    sp = sub.add_parser("validate", help="train/val split eval + Deflated Sharpe (holdout LOCKED)")
    _add_eval_args(sp)
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("walk-forward", help="rolling/anchored walk-forward folds")
    _add_eval_args(sp)
    sp.add_argument("--folds", type=int, default=4)
    sp.add_argument("--anchored", action="store_true")
    sp.set_defaults(func=cmd_walk_forward)

    sp = sub.add_parser("sensitivity", help="parameter-sensitivity (plateau-not-spike)")
    _add_eval_args(sp, with_idx=False)
    sp.set_defaults(func=cmd_sensitivity)

    sp = sub.add_parser("reality-check", help="White's Reality Check over a hypothesis's configs")
    _add_eval_args(sp, with_idx=False)
    sp.add_argument("--n-boot", type=int, default=2000, dest="n_boot")
    sp.set_defaults(func=cmd_reality_check)

    sp = sub.add_parser("holdout", help="open the holdout EXACTLY ONCE")
    _add_eval_args(sp)
    sp.add_argument("--force-show", action="store_true", dest="force_show",
                    help="show prior result without attempting to re-open")
    sp.set_defaults(func=cmd_holdout)

    sp = sub.add_parser("deep-ingest", help="deep PIT historical ingest (front-week ATM)")
    sp.add_argument("--underlying", default="SPY")
    sp.add_argument("--start", default=None, help="YYYY-MM-DD (default 2024-02-05)")
    sp.add_argument("--end", default=None, help="YYYY-MM-DD (default yesterday)")
    sp.add_argument("--timeframe", default="5Min")
    sp.set_defaults(func=cmd_deep_ingest)

    sp = sub.add_parser("scan-ingest", help="deep-ingest a ticker-list file (front-week ATM)")
    sp.add_argument("--file", required=True, help="path to a ticker-list file (one symbol/line)")
    sp.add_argument("--start", default=None, help="YYYY-MM-DD (default: end - lookback)")
    sp.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    sp.add_argument("--lookback-days", type=int, default=95, dest="lookback_days")
    sp.add_argument("--timeframe", default="5Min")
    sp.set_defaults(func=cmd_scan_ingest)

    sp = sub.add_parser("equity-smoke", help="long-horizon factor backtest (12-1 momentum) + DSR/holdout")
    sp.add_argument("--file", default=None, help="ticker-list file (default: 20 large caps)")
    sp.add_argument("--start", default=None, help="YYYY-MM-DD")
    sp.add_argument("--end", default=None, help="YYYY-MM-DD")
    sp.add_argument("--years", type=int, default=2, help="approx history depth if --start omitted")
    sp.set_defaults(func=cmd_equity_smoke)

    sp = sub.add_parser("equity-ff", help="real FF quality-value strategy (filing-lagged) + DSR/holdout")
    sp.add_argument("--file", default=None, help="ticker-list file (default: 30 large caps)")
    sp.add_argument("--start", default=None, help="YYYY-MM-DD (default 2016-01-01)")
    sp.add_argument("--end", default=None, help="YYYY-MM-DD (default today)")
    sp.set_defaults(func=cmd_equity_ff)

    sp = sub.add_parser("equity-selltriggers", help="7 drawdown-detection triggers (CI/vol/MA + trailingDD/breadth/crossasset/Donchian) on identical staggered buy")
    sp.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "UPRO"])
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--increments", type=int, default=5, dest="increments")
    sp.set_defaults(func=cmd_equity_selltriggers, no_store=True)

    sp = sub.add_parser("equity-volcrash", help="combined best: vol-spike SELL + staggered avg-down BUY on indices")
    sp.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "UPRO"])
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--vol-mult", type=float, default=1.5, dest="vol_mult",
                    help="sell when realized vol > rolling median x this")
    sp.add_argument("--increments", type=int, default=5, dest="increments",
                    help="increments for the CI-trigger reference")
    sp.add_argument("--increments-sweep", type=int, nargs="+", default=[3, 5, 10], dest="increments_sweep",
                    help="stagger increments to sweep for the vol-trigger version")
    sp.set_defaults(func=cmd_equity_volcrash, no_store=True)

    sp = sub.add_parser("equity-buysell", help="active buy/sell timing on indices (CI dip entry x MA/vol/RSI sell) -- what it does to profit")
    sp.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "UPRO"])
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--ci-lookback", type=int, default=90, dest="ci_lookback")
    sp.add_argument("--buy-sigma", type=float, default=2.0, dest="buy_sigma")
    sp.add_argument("--sell-sigma", type=float, default=1.0, dest="sell_sigma")
    sp.add_argument("--ma", type=int, default=50, dest="ma")
    sp.set_defaults(func=cmd_equity_buysell, no_store=True)

    sp = sub.add_parser("equity-overlays", help="compare drawdown-reduction overlays (crash/MA200/vol-target/TS-mom) + combos per symbol")
    sp.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "UPRO"])
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--target-vol", type=float, default=0.15, dest="target_vol",
                    help="annual vol target for the vol-targeting overlay")
    sp.set_defaults(func=cmd_equity_overlays, no_store=True)

    sp = sub.add_parser("equity-crash-multi", help="crash-dodge across many indices/leveraged ETFs (UPRO/TQQQ/...), each vs its own buy&hold")
    sp.add_argument("--symbols", nargs="+",
                    default=["SPY", "QQQ", "UPRO", "TQQQ", "SPXL", "SOXL", "AVUV", "TNA"],
                    help="tickers to crash-dodge (each timed on its own CI band)")
    sp.add_argument("--start", default=None, help="YYYY-MM-DD (default 2010-01-01)")
    sp.add_argument("--end", default=None)
    sp.add_argument("--ci-lookback", type=int, default=90, dest="ci_lookback")
    sp.add_argument("--crash-sigma", type=float, default=2.0, dest="crash_sigma")
    sp.add_argument("--increment", type=int, default=5, dest="increment")
    sp.add_argument("--decline-mode", default="cliff_sell", dest="decline_mode",
                    choices=["cliff_sell", "ramp_sell"])
    sp.add_argument("--reentry-mode", default="avg_down", dest="reentry_mode",
                    choices=["avg_down", "ramp_up", "cliff_up"])
    sp.set_defaults(func=cmd_equity_crash_multi, no_store=True)

    sp = sub.add_parser("equity-crash", help="SPY crash-dodge overlay: sell on CI black-swan, average in as it falls, vs buy&hold")
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--ci-lookback", type=int, default=90, dest="ci_lookback")
    sp.add_argument("--crash-sigmas", type=float, nargs="+", default=[1.5, 2.0, 2.5], dest="crash_sigmas",
                    help="black-swan trigger: sell when SPY < mean - this*std")
    sp.add_argument("--increments", type=int, nargs="+", default=[3, 5, 10], dest="increments",
                    help="number of incremental steps for ramping exposure")
    sp.add_argument("--decline-modes", nargs="+", default=["cliff_sell", "ramp_sell"],
                    dest="decline_modes", choices=["cliff_sell", "ramp_sell"],
                    help="decline phase: cliff_sell (dump) or ramp_sell (trend: cut into weakness)")
    sp.add_argument("--reentry-modes", nargs="+", default=["avg_down", "ramp_up", "cliff_up"],
                    dest="reentry_modes", choices=["avg_down", "ramp_up", "cliff_up"],
                    help="re-entry: avg_down (mean-rev), ramp_up (trend: add into strength), cliff_up (snap back)")
    sp.set_defaults(func=cmd_equity_crash, no_store=True)

    sp = sub.add_parser("equity-crash-stocks", help="PER-STOCK crash timing: each name dodges its own crashes; vs equal-weight buy&hold")
    sp.add_argument("--file", default=None)
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--ci-lookback", type=int, default=90, dest="ci_lookback")
    sp.add_argument("--crash-sigmas", type=float, nargs="+", default=[1.5, 2.0, 2.5], dest="crash_sigmas")
    sp.add_argument("--increments", type=int, nargs="+", default=[3, 5, 10], dest="increments")
    sp.add_argument("--decline-modes", nargs="+", default=["cliff_sell", "ramp_sell"],
                    dest="decline_modes", choices=["cliff_sell", "ramp_sell"])
    sp.add_argument("--reentry-modes", nargs="+", default=["avg_down", "ramp_up", "cliff_up"],
                    dest="reentry_modes", choices=["avg_down", "ramp_up", "cliff_up"])
    sp.set_defaults(func=cmd_equity_crash_stocks, no_store=True)

    sp = sub.add_parser("equity-civalue", help="combined: buy CI dip AND undervalued; sell at -1sig (filing-lagged value filter)")
    sp.add_argument("--file", default=None)
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--windows", type=int, nargs="+", default=[60, 90, 120], dest="windows",
                    help="CI lookback windows (days) to sweep")
    sp.add_argument("--quantiles", type=float, nargs="+", default=[0.3, 0.5], dest="quantiles",
                    help="value-screen top-quantile thresholds to sweep")
    sp.add_argument("--buy-sigma", type=float, default=2.0, dest="buy_sigma")
    sp.add_argument("--sell-sigma", type=float, default=1.0, dest="sell_sigma")
    sp.add_argument("--hold-forever", action="store_true", dest="hold_forever",
                    help="no sell: buy cheap dips and HOLD to the end (isolate the entry signal)")
    sp.set_defaults(func=cmd_equity_civalue)

    sp = sub.add_parser("equity-timing", help="daily CI buy + composable SELL triggers (sigma/ma/rsi) vs buy-and-hold")
    sp.add_argument("--file", default=None)
    sp.add_argument("--start", default=None)
    sp.add_argument("--end", default=None)
    sp.add_argument("--ci-lookback", type=int, default=90, dest="ci_lookback")
    sp.add_argument("--buy-sigma", type=float, default=2.0, dest="buy_sigma")
    sp.add_argument("--sell-sigma", type=float, default=1.0, dest="sell_sigma",
                    help="take-profit band: sell when price > mean + this*std")
    sp.add_argument("--ma", type=int, default=200, dest="ma",
                    help="MA window (days); 'ma' trigger sells when this MA is falling")
    sp.add_argument("--rsi-sell", type=float, default=70.0, dest="rsi_sell",
                    help="'rsi' trigger sells when 14d RSI (analysis.py) >= this")
    sp.set_defaults(func=cmd_equity_timing)

    sp = sub.add_parser("equity-ci", help="backtest the screener's CI mean-reversion signal (window sweep + MA combo)")
    sp.add_argument("--file", default=None, help="ticker-list file (default: 30 large caps)")
    sp.add_argument("--start", default=None, help="YYYY-MM-DD (default 2016-01-01)")
    sp.add_argument("--end", default=None, help="YYYY-MM-DD (default today)")
    sp.add_argument("--windows", type=int, nargs="+", default=[60, 90, 120, 252],
                    help="CI lookback windows in days to sweep (each = a DSR trial)")
    sp.add_argument("--ma", type=int, default=200, help="MA window (days) for the CI+MA combo")
    sp.add_argument("--quantile", type=float, default=0.2)
    sp.add_argument("--long-short", action="store_true", dest="long_short",
                    help="also test top-minus-bottom (isolates factor from market beta)")
    sp.set_defaults(func=cmd_equity_ci)

    sp = sub.add_parser("scan-run", help="run CALL hypotheses across a ticker universe; DSR-deflate + holdout")
    sp.add_argument("--file", default=None, help="ticker-list file (default: all stored)")
    sp.add_argument("--timeframe", default="5Min")
    sp.add_argument("--spread", type=float, default=1.0)
    sp.add_argument("--stop", type=float, default=0.5)
    sp.add_argument("--take-profit", type=float, default=-1.0, dest="take_profit")
    sp.add_argument("--max-hold", type=int, default=30, dest="max_hold")
    sp.add_argument("--dsr-threshold", type=float, default=0.95, dest="dsr_threshold")
    sp.set_defaults(func=cmd_scan_run)

    sp = sub.add_parser("run-all", help="M6: run the reasoned hypothesis set, report survivors")
    sp.add_argument("--underlying", default=None, help="run over all stored options of this underlying")
    sp.add_argument("--symbols", nargs="*", help="explicit option symbols (overrides --underlying)")
    sp.add_argument("--timeframe", default="1Min")
    sp.add_argument("--spread", type=float, default=1.0)
    sp.add_argument("--stop", type=float, default=0.5)
    sp.add_argument("--take-profit", type=float, default=-1.0, dest="take_profit")
    sp.add_argument("--max-hold", type=int, default=30, dest="max_hold")
    sp.add_argument("--dsr-threshold", type=float, default=0.95, dest="dsr_threshold")
    sp.set_defaults(func=cmd_run_all)

    sp = sub.add_parser("smoke", help="end-to-end tiny demo + checks")
    sp.add_argument("--symbol", default="SPY")
    sp.add_argument("--days", type=float, default=5)
    sp.add_argument("--timeframe", default="1Min")
    sp.add_argument("--exp-days", type=int, default=14, dest="exp_days")
    sp.set_defaults(func=cmd_smoke)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # Commands that only hit external APIs (no DuckDB) skip opening the store, so
    # they can run alongside a backgrounded job holding the write lock.
    if getattr(args, "no_store", False):
        args.func(args, None)
    else:
        with ResearchStore() as store:
            args.func(args, store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
