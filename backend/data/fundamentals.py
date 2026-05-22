import time
import requests
import numpy as np
from threading import Lock


_SEC_HEADERS = {
    "User-Agent": "StockTracker/1.0 contact@stocktracker.local",
    "Accept-Encoding": "gzip, deflate",
}
_TICKERS_URL      = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL        = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SEC_MIN_INTERVAL = 0.12   # stay under SEC EDGAR's 10 req/s limit
_BETA_DAYS        = 400    # calendar days back (~252 trading days) for beta


def _safe_round(val, digits=3):
    try:
        return round(float(val), digits) if val is not None else None
    except (TypeError, ValueError):
        return None


class FundamentalsManager:
    """
    All five Fama-French factors plus market beta:

      BETA — Market factor  : beta vs SPY over ~1 year of daily returns
                              Measures market-risk exposure. Not a good/bad axis.
      MCAP — Size factor    : market cap in $B (smaller historically favored, weakly)
      BM   — Value factor   : Book Equity / Market Cap  (higher = cheaper vs book)
      OP   — Profitability  : Operating Income / |Book Equity|  (higher = better)
      INV  — Investment     : YoY total-asset growth  (lower = conservative)

    Price / returns via AlpacaDataManager (same credentials as analysis.py).
    Accounting data via SEC EDGAR public API (no key required).
    Singleton with per-session caching.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._fund_cache   = {}
            inst._facts_cache  = {}
            inst._cik_map      = None
            inst._lock         = Lock()
            inst._last_req     = 0.0
            cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ public

    def get_fundamentals(self, ticker):
        ticker = ticker.upper()
        if ticker in self._fund_cache:
            return self._fund_cache[ticker]
        result = self._fetch(ticker)
        self._fund_cache[ticker] = result
        return result

    # ------------------------------------------------------------------ SEC helpers

    def _throttle(self):
        with self._lock:
            gap = time.time() - self._last_req
            if gap < _SEC_MIN_INTERVAL:
                time.sleep(_SEC_MIN_INTERVAL - gap)
            self._last_req = time.time()

    def _get(self, url):
        self._throttle()
        r = requests.get(url, headers=_SEC_HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()

    def _load_cik_map(self):
        if self._cik_map is None:
            data = self._get(_TICKERS_URL)
            self._cik_map = {
                v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                for v in data.values()
            }
        return self._cik_map

    def _cik(self, ticker):
        return self._load_cik_map().get(ticker)

    def _facts(self, cik):
        if cik in self._facts_cache:
            return self._facts_cache[cik]
        data = self._get(_FACTS_URL.format(cik=cik))
        self._facts_cache[cik] = data
        return data

    # ------------------------------------------------------------------ EDGAR parsing

    def _annual_value(self, facts, concept, taxonomy="us-gaap"):
        """Most recent 10-K value; amended filings (10-K/A) win for the same period."""
        try:
            concept_units = facts["facts"][taxonomy][concept]["units"]
        except KeyError:
            return None

        for unit_key in ("USD", "shares", "pure"):
            if unit_key not in concept_units:
                continue
            seen = {}
            for e in concept_units[unit_key]:
                if e.get("form") not in ("10-K", "10-K/A"):
                    continue
                end, filed = e.get("end", ""), e.get("filed", "")
                if end not in seen or filed > seen[end]["filed"]:
                    seen[end] = e
            if not seen:
                continue
            return max(seen.values(), key=lambda e: e["end"])["val"]
        return None

    def _two_annual_values(self, facts, concept):
        """(current, prior) annual values for growth calculations."""
        try:
            units = facts["facts"]["us-gaap"][concept]["units"]["USD"]
        except KeyError:
            return None, None

        seen = {}
        for e in units:
            if e.get("form") not in ("10-K", "10-K/A"):
                continue
            end, filed = e.get("end", ""), e.get("filed", "")
            if end not in seen or filed > seen[end]["filed"]:
                seen[end] = e

        if len(seen) < 2:
            return None, None
        periods = sorted(seen.keys(), reverse=True)
        return seen[periods[0]]["val"], seen[periods[1]]["val"]

    # ------------------------------------------------------------------ metrics

    def _compute_beta(self, ticker, dm):
        """Beta vs SPY using ~1 year of daily returns from AlpacaDataManager."""
        try:
            stock_df = dm.get_data(ticker, days_back=_BETA_DAYS, frequency="1D")
            spy_df   = dm.get_data("SPY",   days_back=_BETA_DAYS, frequency="1D")
            if stock_df.empty or spy_df.empty:
                return None

            stock_r = stock_df["close"].pct_change().dropna()
            spy_r   = spy_df["close"].pct_change().dropna()

            common = stock_r.index.intersection(spy_r.index)
            if len(common) < 30:
                return None

            s = stock_r.loc[common]
            m = spy_r.loc[common]
            var_m = float(m.var())
            if var_m == 0:
                return None
            return _safe_round(float(s.cov(m)) / var_m, 2)
        except Exception:
            return None

    def _compute_accounting(self, facts, price):
        """
        Returns (bm, op, inv, mcap) from SEC EDGAR facts + current price.
        All may be None for ETFs/foreign stocks without EDGAR filings.
        """
        equity = (
            self._annual_value(facts, "StockholdersEquity")
            or self._annual_value(facts, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
        )
        shares = (
            self._annual_value(facts, "CommonStockSharesOutstanding")
            or self._annual_value(facts, "CommonStockSharesOutstandingIncludingTreasuryShares")
        )
        op_income = (
            self._annual_value(facts, "OperatingIncomeLoss")
            or self._annual_value(facts, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest")
        )
        curr_assets, prev_assets = self._two_annual_values(facts, "Assets")

        # B/M
        bm = None
        if equity and shares and price and shares > 0 and price > 0:
            bm = _safe_round(equity / (shares * price))

        # Market cap ($B)
        mcap = None
        if shares and price and shares > 0 and price > 0:
            mcap = _safe_round(shares * price / 1e9, 2)

        # Operating profitability
        op = None
        if op_income is not None and equity and equity != 0:
            op = _safe_round(op_income / abs(equity))

        # Investment (asset growth)
        inv = None
        if curr_assets is not None and prev_assets and prev_assets != 0:
            inv = _safe_round((curr_assets - prev_assets) / abs(prev_assets))

        return bm, op, inv, mcap

    # ------------------------------------------------------------------ main fetch

    def _fetch(self, ticker):
        null = {"BM": None, "OP": None, "INV": None, "BETA": None, "MCAP": None}
        try:
            from data.analysis import AlpacaDataManager
            dm    = AlpacaDataManager()
            price = dm.get_price(ticker)
            beta  = self._compute_beta(ticker, dm)

            cik = self._cik(ticker)
            if not cik:
                # ETF, foreign stock, or not SEC-registered — return what we can
                return {**null, "BETA": beta}

            facts              = self._facts(cik)
            bm, op, inv, mcap  = self._compute_accounting(facts, price)

            return {"BM": bm, "OP": op, "INV": inv, "BETA": beta, "MCAP": mcap}
        except Exception as e:
            print(f"Fundamentals error for {ticker}: {e}")
            return null
