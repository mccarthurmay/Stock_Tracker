"""DuckDB storage for the data spine.

Tables
------
underlying_bars   OHLCV for the underlying, dense per timeframe.
option_bars       OHLCV per option contract; carries the parsed contract
                  fields and the ``feed`` the bars came from (ROADMAP §2a).
contract_universe Point-in-time snapshot of listed contracts (one row per
                  (option_symbol, as_of_date)); carries daily-snapshot OI.
ingest_log        One row per pull: what/when/feed/range/rows — this is the
                  audit trail the validation harness (ROADMAP §6.6) builds on.

Bar timestamps are the bar *start* (UTC, as Alpaca returns them). A bar
labelled ``t`` covers ``[t, t+timeframe)`` and is therefore only *knowable*
at ``t + timeframe`` — the basis for the signal->fill invariant downstream.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from .settings import DEFAULT_DB_PATH, DATA_DIR

UNDERLYING_COLS = [
    "symbol", "timeframe", "ts", "open", "high", "low", "close",
    "volume", "trade_count", "vwap",
]
OPTION_COLS = [
    "option_symbol", "underlying", "expiry", "strike", "opt_type", "timeframe",
    "ts", "open", "high", "low", "close", "volume", "trade_count", "vwap", "feed",
]
UNIVERSE_COLS = [
    "option_symbol", "underlying", "expiry", "strike", "opt_type", "style",
    "status", "tradable", "size", "open_interest", "open_interest_date",
    "close_price", "close_price_date", "as_of_date",
]
GREEKS_COLS = [
    "option_symbol", "underlying", "expiry", "strike", "opt_type", "timeframe",
    "ts", "under_price", "opt_price", "price_source", "dte_days", "tte_years",
    "rate", "div_yield", "model", "iv", "iv_converged", "iv_residual",
    "delta", "gamma", "vega_pct", "theta_day", "rho_pct", "feed", "computed_at",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS underlying_bars (
    symbol      VARCHAR      NOT NULL,
    timeframe   VARCHAR      NOT NULL,
    ts          TIMESTAMPTZ  NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    volume      BIGINT,
    trade_count BIGINT,
    vwap        DOUBLE,
    PRIMARY KEY (symbol, timeframe, ts)
);

CREATE TABLE IF NOT EXISTS option_bars (
    option_symbol VARCHAR     NOT NULL,
    underlying    VARCHAR     NOT NULL,
    expiry        DATE,
    strike        DOUBLE,
    opt_type      VARCHAR,
    timeframe     VARCHAR     NOT NULL,
    ts            TIMESTAMPTZ NOT NULL,
    open          DOUBLE,
    high          DOUBLE,
    low           DOUBLE,
    close         DOUBLE,
    volume        BIGINT,
    trade_count   BIGINT,
    vwap          DOUBLE,
    feed          VARCHAR     NOT NULL,
    PRIMARY KEY (option_symbol, timeframe, ts)
);

CREATE TABLE IF NOT EXISTS contract_universe (
    option_symbol      VARCHAR NOT NULL,
    underlying         VARCHAR NOT NULL,
    expiry             DATE,
    strike             DOUBLE,
    opt_type           VARCHAR,
    style              VARCHAR,
    status             VARCHAR,
    tradable           BOOLEAN,
    size               VARCHAR,
    open_interest      BIGINT,
    open_interest_date DATE,
    close_price        DOUBLE,
    close_price_date   DATE,
    as_of_date         DATE    NOT NULL,
    PRIMARY KEY (option_symbol, as_of_date)
);

CREATE TABLE IF NOT EXISTS option_greeks (
    option_symbol VARCHAR     NOT NULL,
    underlying    VARCHAR,
    expiry        DATE,
    strike        DOUBLE,
    opt_type      VARCHAR,
    timeframe     VARCHAR     NOT NULL,
    ts            TIMESTAMPTZ NOT NULL,
    under_price   DOUBLE,
    opt_price     DOUBLE,
    price_source  VARCHAR,
    dte_days      INTEGER,
    tte_years     DOUBLE,
    rate          DOUBLE,
    div_yield     DOUBLE,
    model         VARCHAR,
    iv            DOUBLE,
    iv_converged  BOOLEAN,
    iv_residual   DOUBLE,
    delta         DOUBLE,
    gamma         DOUBLE,
    vega_pct      DOUBLE,
    theta_day     DOUBLE,
    rho_pct       DOUBLE,
    feed          VARCHAR,
    computed_at   TIMESTAMPTZ,
    PRIMARY KEY (option_symbol, timeframe, ts)
);

-- Executed-configuration ledger (ROADMAP §4, §6.5). Every distinct backtest
-- configuration actually run is recorded here; the COUNT of distinct
-- config_hash values is the N fed into the multiple-testing correction (DSR /
-- White's Reality Check). Counting registered hypotheses instead would be
-- anti-conservative -- this captures the garden of forking paths.
CREATE TABLE IF NOT EXISTS config_runs (
    config_hash  VARCHAR     NOT NULL,
    hypothesis   VARCHAR,
    phase        VARCHAR,
    params_json  VARCHAR,
    dataset      VARCHAR,
    split        VARCHAR,
    first_run_ts TIMESTAMPTZ NOT NULL,
    last_run_ts  TIMESTAMPTZ NOT NULL,
    run_count    BIGINT      NOT NULL,
    PRIMARY KEY (config_hash)
);

-- One row per backtest run (per spread-sweep level). Stores the headline
-- metrics + the objective verdict so results are auditable and a run can never
-- be silently re-run-until-it-passes. Linked to config_runs via config_hash.
CREATE SEQUENCE IF NOT EXISTS backtest_runs_seq START 1;
CREATE TABLE IF NOT EXISTS backtest_runs (
    id            BIGINT DEFAULT nextval('backtest_runs_seq'),
    run_ts        TIMESTAMPTZ NOT NULL,
    config_hash   VARCHAR,
    hypothesis    VARCHAR,
    phase         VARCHAR,
    dataset       VARCHAR,
    split         VARCHAR,
    spread_mult   DOUBLE,
    n_trades      BIGINT,
    effective_n   DOUBLE,
    win_rate      DOUBLE,
    expectancy    DOUBLE,
    profit_factor DOUBLE,
    total_pnl     DOUBLE,
    sharpe        DOUBLE,
    sortino       DOUBLE,
    calmar        DOUBLE,
    max_drawdown  DOUBLE,
    return_skew   DOUBLE,
    worst_trade   DOUBLE,
    passed        BOOLEAN,
    reasons       VARCHAR,
    PRIMARY KEY (id)
);

CREATE SEQUENCE IF NOT EXISTS ingest_log_seq START 1;
CREATE TABLE IF NOT EXISTS ingest_log (
    id           BIGINT DEFAULT nextval('ingest_log_seq'),
    run_ts       TIMESTAMPTZ NOT NULL,
    kind         VARCHAR     NOT NULL,
    symbol       VARCHAR,
    timeframe    VARCHAR,
    start_ts     TIMESTAMPTZ,
    end_ts       TIMESTAMPTZ,
    feed         VARCHAR,
    rows_written BIGINT,
    note         VARCHAR,
    PRIMARY KEY (id)
);
"""


class ResearchStore:
    """Thin DuckDB wrapper. Use as a context manager or call close()."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH, read_only: bool = False):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(db_path), read_only=read_only)
        # Fetch TIMESTAMPTZ back as UTC regardless of the host timezone, so
        # integrity checks and alignment are deterministic.
        self.con.execute("SET TimeZone='UTC'")
        if not read_only:
            self.con.execute(_SCHEMA)

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> "ResearchStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.con.close()

    # -- writes -------------------------------------------------------------
    def _upsert(self, table: str, df: pd.DataFrame, cols: list[str]) -> int:
        if df is None or df.empty:
            return 0
        df = df[cols]  # exact column order; raises if a column is missing
        self.con.register("_stage", df)
        self.con.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM _stage")
        self.con.unregister("_stage")
        return len(df)

    def upsert_underlying_bars(self, df: pd.DataFrame) -> int:
        return self._upsert("underlying_bars", df, UNDERLYING_COLS)

    def upsert_option_bars(self, df: pd.DataFrame) -> int:
        return self._upsert("option_bars", df, OPTION_COLS)

    def upsert_universe(self, df: pd.DataFrame) -> int:
        return self._upsert("contract_universe", df, UNIVERSE_COLS)

    def upsert_option_greeks(self, df: pd.DataFrame) -> int:
        return self._upsert("option_greeks", df, GREEKS_COLS)

    def record_config_run(self, config_hash: str, hypothesis: str, phase: str,
                          params_json: str, dataset: str = "", split: str = "") -> int:
        """Upsert one executed configuration; return its cumulative run_count.

        Idempotent on config_hash: re-running the same config bumps run_count
        and last_run_ts but does not inflate the *distinct-config* count that
        the multiple-testing correction uses.
        """
        existing = self.con.execute(
            "SELECT run_count FROM config_runs WHERE config_hash = ?", [config_hash]
        ).fetchone()
        if existing is None:
            self.con.execute(
                "INSERT INTO config_runs (config_hash, hypothesis, phase, params_json, "
                "dataset, split, first_run_ts, last_run_ts, run_count) "
                "VALUES (?, ?, ?, ?, ?, ?, now(), now(), 1)",
                [config_hash, hypothesis, phase, params_json, dataset, split],
            )
            return 1
        self.con.execute(
            "UPDATE config_runs SET last_run_ts = now(), run_count = run_count + 1 "
            "WHERE config_hash = ?", [config_hash],
        )
        return int(existing[0]) + 1

    def record_backtest_run(self, *, config_hash, hypothesis, phase, dataset, split,
                            spread_mult, metrics, passed, reasons) -> None:
        """Persist a backtest run's metrics + objective verdict (ROADMAP §5/§6)."""
        m = metrics
        self.con.execute(
            "INSERT INTO backtest_runs (run_ts, config_hash, hypothesis, phase, "
            "dataset, split, spread_mult, n_trades, effective_n, win_rate, expectancy, "
            "profit_factor, total_pnl, sharpe, sortino, calmar, max_drawdown, "
            "return_skew, worst_trade, passed, reasons) VALUES "
            "(now(), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [config_hash, hypothesis, phase, dataset, split, spread_mult,
             m.n_trades, m.effective_n, m.win_rate, m.expectancy, m.profit_factor,
             m.total_pnl, m.sharpe, m.sortino, m.calmar, m.max_drawdown,
             m.return_skew, m.worst_trade, passed, reasons],
        )

    def read_backtest_runs(self, hypothesis: Optional[str] = None) -> pd.DataFrame:
        if hypothesis:
            return self.con.execute(
                "SELECT * FROM backtest_runs WHERE hypothesis = ? ORDER BY run_ts, spread_mult",
                [hypothesis],
            ).df()
        return self.con.execute("SELECT * FROM backtest_runs ORDER BY run_ts").df()

    def distinct_config_count(self, phase: Optional[str] = None) -> int:
        """N for the multiple-testing correction: distinct configs executed."""
        if phase:
            return self.con.execute(
                "SELECT count(*) FROM config_runs WHERE phase = ?", [phase]
            ).fetchone()[0]
        return self.con.execute("SELECT count(*) FROM config_runs").fetchone()[0]

    def log_ingest(self, kind: str, symbol: Optional[str], timeframe: Optional[str],
                   start_ts, end_ts, feed: Optional[str], rows_written: int,
                   note: str = "") -> None:
        self.con.execute(
            "INSERT INTO ingest_log "
            "(run_ts, kind, symbol, timeframe, start_ts, end_ts, feed, rows_written, note) "
            "VALUES (now(), ?, ?, ?, ?, ?, ?, ?, ?)",
            [kind, symbol, timeframe, start_ts, end_ts, feed, int(rows_written), note],
        )

    # -- reads --------------------------------------------------------------
    def read_underlying_bars(self, symbol: str, timeframe: str) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM underlying_bars WHERE symbol = ? AND timeframe = ? ORDER BY ts",
            [symbol, timeframe],
        ).df()

    def read_option_bars(self, option_symbol: str, timeframe: str) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM option_bars WHERE option_symbol = ? AND timeframe = ? ORDER BY ts",
            [option_symbol, timeframe],
        ).df()

    def read_option_greeks(self, option_symbol: str, timeframe: str) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM option_greeks WHERE option_symbol = ? AND timeframe = ? ORDER BY ts",
            [option_symbol, timeframe],
        ).df()

    def option_symbols(self, underlying: str | None = None) -> list[str]:
        """Distinct option symbols present in option_bars (optionally filtered)."""
        if underlying:
            rows = self.con.execute(
                "SELECT DISTINCT option_symbol FROM option_bars WHERE underlying = ? ORDER BY 1",
                [underlying],
            ).fetchall()
        else:
            rows = self.con.execute(
                "SELECT DISTINCT option_symbol FROM option_bars ORDER BY 1"
            ).fetchall()
        return [r[0] for r in rows]

    def latest_universe(self, underlying: str) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM contract_universe WHERE underlying = ? "
            "AND as_of_date = (SELECT max(as_of_date) FROM contract_universe WHERE underlying = ?) "
            "ORDER BY expiry, opt_type, strike",
            [underlying, underlying],
        ).df()

    def table_counts(self) -> dict[str, int]:
        out = {}
        for t in ("underlying_bars", "option_bars", "option_greeks",
                  "contract_universe", "config_runs", "backtest_runs", "ingest_log"):
            out[t] = self.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        return out
