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

from .client import AlpacaResearch
from .storage import ResearchStore
from . import ingest, universe, integrity


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


def cmd_smoke(args, store):
    symbol = args.symbol.upper()
    tf = args.timeframe
    today = date.today()
    client = AlpacaResearch()

    print(f"[1/5] Snapshotting {symbol} universe (expiring within {args.exp_days} days)...")
    uni = universe.snapshot_universe(
        client, store, symbol,
        expiration_gte=today, expiration_lte=today + timedelta(days=args.exp_days),
    )
    if uni.empty:
        print("  No contracts returned — aborting smoke test.")
        return
    print(f"  {len(uni)} contracts.")

    print(f"[2/5] Ingesting {symbol} {tf} underlying bars (last {args.days}d)...")
    start, end = _window(args.days)
    n_u = ingest.ingest_underlying(client, store, symbol, start, end, tf)
    print(f"  {n_u} underlying bars.")
    if n_u == 0:
        print("  No underlying bars — aborting.")
        return

    spot = store.read_underlying_bars(symbol, tf)["close"].iloc[-1]
    print(f"  Spot ~ {spot:.2f}")

    print("[3/5] Picking nearest-expiry ATM call + put...")
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

    print(f"[4/5] Ingesting {tf} option bars for {len(chosen)} contract(s)...")
    n_o = ingest.ingest_options(client, store, chosen, start, end, tf)
    print(f"  {n_o} option bars.")

    print("[5/5] Verifying point-in-time integrity...")
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
