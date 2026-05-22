import time
import requests
from threading import Lock


_SEC_HEADERS = {
    "User-Agent": "StockTracker/1.0 contact@stocktracker.local",
    "Accept-Encoding": "gzip, deflate",
}
_TICKERS_URL    = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL      = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SEC_MIN_INTERVAL = 0.12   # stay under SEC EDGAR's 10 req/s limit


def _safe_round(val, digits=3):
    try:
        return round(float(val), digits) if val is not None else None
    except (TypeError, ValueError):
        return None


class FundamentalsManager:
    """
    Fama-French fundamental metrics using:
      - Alpaca (same credentials as analysis.py) for market price
      - SEC EDGAR public API for accounting data (no API key required)

      BM  — Book-to-Market  = Book Equity / Market Cap   (higher = cheaper vs book value)
      OP  — Operating Profitability = Operating Income / |Book Equity|  (higher = better)
      INV — Investment ratio = YoY total-asset growth                   (lower = conservative)

    Singleton with per-session caching so each ticker is only fetched once.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._fund_cache  = {}      # ticker  → {BM, OP, INV}
            inst._facts_cache = {}      # CIK str → raw EDGAR facts JSON
            inst._cik_map     = None    # ticker  → zero-padded CIK string
            inst._lock        = Lock()
            inst._last_req    = 0.0
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

    # ------------------------------------------------------------------ HTTP helpers

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

    # ------------------------------------------------------------------ EDGAR helpers

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

    # ------------------------------------------------------------------ parsing

    def _annual_value(self, facts, concept, taxonomy="us-gaap"):
        """
        Most recent 10-K value for a US-GAAP concept.
        When a period has multiple filings (e.g. amended 10-K/A),
        the most recently filed one wins.
        """
        try:
            concept_units = facts["facts"][taxonomy][concept]["units"]
        except KeyError:
            return None

        for unit_key in ("USD", "shares", "pure"):
            if unit_key not in concept_units:
                continue
            seen = {}   # period end-date → best entry
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
        """Return (current, prior) annual values — needed for growth calculations."""
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

    def _book_to_market(self, facts, price):
        # Try primary concept, fall back to version that includes minority interest
        equity = (
            self._annual_value(facts, "StockholdersEquity")
            or self._annual_value(facts, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
        )
        shares = (
            self._annual_value(facts, "CommonStockSharesOutstanding")
            or self._annual_value(facts, "CommonStockSharesOutstandingIncludingTreasuryShares")
        )
        if not all([equity, shares, price]) or shares <= 0 or price <= 0:
            return None
        return _safe_round(equity / (shares * price))

    def _operating_profitability(self, facts):
        op_income = (
            self._annual_value(facts, "OperatingIncomeLoss")
            or self._annual_value(facts, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest")
        )
        equity = (
            self._annual_value(facts, "StockholdersEquity")
            or self._annual_value(facts, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
        )
        if op_income is None or not equity or equity == 0:
            return None
        return _safe_round(op_income / abs(equity))

    def _investment(self, facts):
        curr, prev = self._two_annual_values(facts, "Assets")
        if curr is None or prev is None or prev == 0:
            return None
        return _safe_round((curr - prev) / abs(prev))

    # ------------------------------------------------------------------ fetch

    def _fetch(self, ticker):
        null = {"BM": None, "OP": None, "INV": None}
        try:
            cik = self._cik(ticker)
            if not cik:
                return null  # ETF, foreign stock, or not SEC-registered

            facts = self._facts(cik)

            # Use AlpacaDataManager for price (same credentials as analysis.py)
            from data.analysis import AlpacaDataManager
            price = AlpacaDataManager().get_price(ticker)

            return {
                "BM":  self._book_to_market(facts, price),
                "OP":  self._operating_profitability(facts),
                "INV": self._investment(facts),
            }
        except Exception as e:
            print(f"Fundamentals error for {ticker}: {e}")
            return null
