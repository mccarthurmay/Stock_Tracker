"""Point-in-time integrity checks for the data spine (ROADMAP §2c, §11).

These are guardrails, not unit tests: they assert that what landed in DuckDB
could not encode lookahead and that option bars align to the underlying. Run
after every ingest; treat a failure as a stop-the-line event.
"""
from __future__ import annotations

from dataclasses import dataclass

from .occ import parse_occ

ALIGN_MIN_COVERAGE = 0.90


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        mark = "PASS" if self.passed else "FAIL"
        return f"[{mark}] {self.name}: {self.detail}"


def _scalar(store, sql: str, params=None):
    return store.con.execute(sql, params or []).fetchone()[0]


def run_all_checks(store) -> list[CheckResult]:
    r: list[CheckResult] = []

    # 1-2. No bar may be timestamped in the future.
    fut_u = _scalar(store, "SELECT count(*) FROM underlying_bars WHERE ts > now()")
    r.append(CheckResult("underlying_no_future", fut_u == 0, f"{fut_u} future-dated rows"))
    fut_o = _scalar(store, "SELECT count(*) FROM option_bars WHERE ts > now()")
    r.append(CheckResult("option_no_future", fut_o == 0, f"{fut_o} future-dated rows"))

    # 3. Every option bar must record the feed it came from.
    no_feed = _scalar(store, "SELECT count(*) FROM option_bars WHERE feed IS NULL OR feed = ''")
    r.append(CheckResult("option_feed_recorded", no_feed == 0, f"{no_feed} rows missing feed"))

    # 4. No option bar may be dated after the contract's expiry.
    post_exp = _scalar(store, "SELECT count(*) FROM option_bars WHERE CAST(ts AS DATE) > expiry")
    r.append(CheckResult("option_within_expiry", post_exp == 0, f"{post_exp} rows after expiry"))

    # 5. No NULL timestamps anywhere.
    null_ts = _scalar(store, "SELECT count(*) FROM underlying_bars WHERE ts IS NULL") + \
        _scalar(store, "SELECT count(*) FROM option_bars WHERE ts IS NULL")
    r.append(CheckResult("no_null_ts", null_ts == 0, f"{null_ts} null timestamps"))

    # 6. Alignment coverage: each option bar should have a same-ts underlying bar.
    total_o = _scalar(store, "SELECT count(*) FROM option_bars")
    if total_o == 0:
        r.append(CheckResult("alignment_coverage", True, "no option bars yet (skipped)"))
    else:
        unmatched = _scalar(store, """
            SELECT count(*) FROM option_bars o
            LEFT JOIN underlying_bars u
              ON u.symbol = o.underlying AND u.timeframe = o.timeframe AND u.ts = o.ts
            WHERE u.ts IS NULL
        """)
        cov = 1.0 - unmatched / total_o
        r.append(CheckResult(
            "alignment_coverage", cov >= ALIGN_MIN_COVERAGE,
            f"{cov:.1%} of {total_o} option bars matched an underlying bar "
            f"({unmatched} unmatched; threshold {ALIGN_MIN_COVERAGE:.0%})",
        ))

    # 7. Stored contract fields must agree with the parsed OCC symbol.
    rows = store.con.execute(
        "SELECT DISTINCT option_symbol, underlying, strike, opt_type, expiry FROM option_bars"
    ).fetchall()
    mismatches = []
    for sym, und, strike, otype, exp in rows:
        try:
            c = parse_occ(sym)
        except ValueError as e:
            mismatches.append(f"{sym} ({e})")
            continue
        if (c.underlying != und or abs(c.strike - float(strike)) > 1e-6
                or c.opt_type != otype or c.expiry != exp):
            mismatches.append(sym)
    r.append(CheckResult(
        "symbol_fields_consistent", not mismatches,
        "all symbols consistent" if not mismatches
        else f"{len(mismatches)} mismatched: {mismatches[:5]}",
    ))

    return r


def all_passed(results: list[CheckResult]) -> bool:
    return all(c.passed for c in results)
