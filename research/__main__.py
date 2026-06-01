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
from . import ingest, universe, integrity, greeks, hypotheses, features, registry
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
