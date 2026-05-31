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

    def latest_universe(self, underlying: str) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM contract_universe WHERE underlying = ? "
            "AND as_of_date = (SELECT max(as_of_date) FROM contract_universe WHERE underlying = ?) "
            "ORDER BY expiry, opt_type, strike",
            [underlying, underlying],
        ).df()

    def table_counts(self) -> dict[str, int]:
        out = {}
        for t in ("underlying_bars", "option_bars", "contract_universe", "ingest_log"):
            out[t] = self.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        return out
