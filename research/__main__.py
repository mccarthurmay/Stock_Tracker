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
               signals, metrics as metrics_mod, backtester, validation, stats, run)
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
    with ResearchStore() as store:
        args.func(args, store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
