"""Point-in-time Fama-French factor values from SEC EDGAR (filing-lag enforced).

The live backend's FundamentalsManager returns *latest* values — fine for a
screener, but LOOKAHEAD for a backtest: at a 2019 rebalance you must not use a
10-K that wasn't filed until 2020. EDGAR's companyfacts endpoint carries every
historical filing *with its `filed` date*, so here we build an as-of accessor
that, for any date, uses only 10-K/10-K-A filings with `filed <= as_of`.

Produces the three factors the screener is built on, academically signed:
  BM  = book equity / market cap        (higher = cheaper, value)
  OP  = operating income / |book eq|    (higher = more profitable)
  INV = YoY total-asset growth          (lower = conservative; we feed raw, the
                                          composite subtracts its z-score)

Market cap uses the point-in-time share count (latest 10-K as-of date) × the
price at the rebalance date (supplied by the caller, from SIP bars).

CAVEAT still standing: this fixes filing-lag lookahead, NOT survivorship — the
ticker universe must still be point-in-time/delisted-aware for a trustworthy
result (see equity.py TODOs, ROADMAP §12).
"""
from __future__ import annotations

import time
from datetime import date

import requests

_HEADERS = {"User-Agent": "StockTracker-Research research@stocktracker.local",
            "Accept-Encoding": "gzip, deflate"}
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_MIN_INTERVAL = 0.12  # stay under EDGAR's 10 req/s


class PITFundamentals:
    """As-of EDGAR fundamentals with per-CIK companyfacts caching."""

    def __init__(self, cache_facts: bool = True):
        self._cik_map: dict | None = None
        self._facts: dict[str, dict] = {}
        # at large universe sizes each companyfacts JSON is multi-MB; caching
        # all of them exhausts memory. cache_facts=False frees each after use.
        self._cache_facts = cache_facts
        self._last_req = 0.0

    # -- http ---------------------------------------------------------------
    def _throttle(self):
        gap = time.time() - self._last_req
        if gap < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - gap)
        self._last_req = time.time()

    def _get(self, url):
        self._throttle()
        r = requests.get(url, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        return r.json()

    def _cik(self, ticker: str) -> str | None:
        if self._cik_map is None:
            data = self._get(_TICKERS_URL)
            self._cik_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                             for v in data.values()}
        return self._cik_map.get(ticker.upper())

    def _facts_for(self, ticker: str) -> dict | None:
        cik = self._cik(ticker)
        if not cik:
            return None
        if self._cache_facts and cik in self._facts:
            return self._facts[cik] or None
        try:
            facts = self._get(_FACTS_URL.format(cik=cik))
        except Exception:
            facts = {}
        if self._cache_facts:
            self._facts[cik] = facts
        return facts or None

    # -- as-of concept extraction ------------------------------------------
    @staticmethod
    def _asof_concept(facts, concept, as_of, taxonomy, forms):
        """Latest-period value for one concept among filings of `forms` filed
        on/before as_of. Returns (val, end) or (None, None)."""
        try:
            units = facts["facts"][taxonomy][concept]["units"]
        except (KeyError, TypeError):
            return None, None
        iso = as_of.isoformat()
        for unit_key in ("USD", "shares", "pure"):
            if unit_key not in units:
                continue
            seen = {}
            for e in units[unit_key]:
                if e.get("form") not in forms:
                    continue
                filed = e.get("filed", "")
                if filed > iso:          # NOT yet knowable at as_of -> skip
                    continue
                end = e.get("end", "")
                if end not in seen or filed > seen[end]["filed"]:
                    seen[end] = e
            if seen:
                best = max(seen.values(), key=lambda e: e["end"])
                return best["val"], best["end"]
        return None, None

    def _asof_annual(self, facts, concept, as_of: date, taxonomy="us-gaap"):
        """As-of annual value, 10-K filings only."""
        return self._asof_concept(facts, concept, as_of, taxonomy, ("10-K", "10-K/A"))

    def _asof_shares(self, facts, as_of: date):
        """Shares outstanding, trying several GAAP + dei cover-page concepts and
        accepting any annual/quarterly form (financials/energy tag this oddly)."""
        forms_any = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F")
        for tax, concept in [
            ("us-gaap", "CommonStockSharesOutstanding"),
            ("us-gaap", "CommonStockSharesIssued"),
            ("dei", "EntityCommonStockSharesOutstanding"),
        ]:
            v, _ = self._asof_concept(facts, concept, as_of, tax, forms_any)
            if v:
                return v
        return None

    @staticmethod
    def _asof_two_annual(facts, concept, as_of: date):
        """(current, prior) annual values filed on/before as_of, for growth."""
        try:
            units = facts["facts"]["us-gaap"][concept]["units"]["USD"]
        except (KeyError, TypeError):
            return None, None
        iso = as_of.isoformat()
        seen = {}
        for e in units:
            if e.get("form") not in ("10-K", "10-K/A"):
                continue
            if e.get("filed", "") > iso:
                continue
            end = e.get("end", "")
            if end not in seen or e.get("filed", "") > seen[end]["filed"]:
                seen[end] = e
        if len(seen) < 2:
            return None, None
        periods = sorted(seen.keys(), reverse=True)
        return seen[periods[0]]["val"], seen[periods[1]]["val"]

    # -- public -------------------------------------------------------------
    def factors_asof(self, ticker: str, as_of: date, price: float) -> dict | None:
        """BM, OP, INV (+ raw equity/shares) using only filings <= as_of.
        Returns None if EDGAR has no usable filing by then."""
        facts = self._facts_for(ticker)
        if not facts:
            return None
        return self.factors_from(facts, as_of, price)

    def factors_from(self, facts: dict, as_of: date, price: float) -> dict | None:
        """factors_asof given ALREADY-fetched facts (avoids per-date refetch)."""
        equity, _ = self._asof_annual(facts, "StockholdersEquity", as_of)
        if equity is None:
            equity, _ = self._asof_annual(
                facts, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", as_of)
        shares = self._asof_shares(facts, as_of)
        op_income, _ = self._asof_annual(facts, "OperatingIncomeLoss", as_of)
        if op_income is None:  # banks/insurers rarely report OperatingIncomeLoss
            op_income, _ = self._asof_annual(
                facts, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", as_of)
        curr_assets, prev_assets = self._asof_two_annual(facts, "Assets", as_of)

        if equity is None or not shares or not price or shares <= 0 or price <= 0:
            return None
        mcap = shares * price
        bm = equity / mcap if mcap > 0 else None
        op = (op_income / abs(equity)) if (op_income is not None and equity != 0) else None
        inv = ((curr_assets - prev_assets) / abs(prev_assets)
               if (curr_assets is not None and prev_assets) else None)
        if bm is None or op is None or inv is None:
            return None
        return {"BM": bm, "OP": op, "INV": inv, "equity": equity,
                "shares": shares, "mcap": mcap}


def build_factor_panel(prices, rebalance_dates, pit: "PITFundamentals | None" = None,
                       progress_every: int = 100):
    """Long-form panel of PIT FF factors at each rebalance date.

    prices: wide DataFrame (index=month-end ts, columns=tickers) of total-return
            adjusted closes (from equity.monthly_total_return_panel).
    Returns a DataFrame with columns [date, ticker, BM, OP, INV, mcap].

    STREAMING by ticker: fetch each ticker's companyfacts once, compute all its
    rebalance dates, then drop it. With pit.cache_facts=False this keeps memory
    flat over thousands of names (each companyfacts JSON is multi-MB).
    """
    import pandas as pd
    pit = pit or PITFundamentals(cache_facts=False)
    # precompute the price row position for each rebalance date once
    date_pos = []
    for d in rebalance_dates:
        pos = prices.index.get_indexer([d], method="ffill")[0]
        if pos >= 0:
            date_pos.append((d, d.date() if hasattr(d, "date") else d, pos))

    rows = []
    tickers = list(prices.columns)
    have_facts = 0
    for n, tkr in enumerate(tickers, 1):
        facts = pit._facts_for(tkr)
        if facts:
            have_facts += 1
            col = prices[tkr]
            for d, dd, pos in date_pos:
                px = col.iat[pos]
                if px is None or pd.isna(px):
                    continue
                f = pit.factors_from(facts, dd, float(px))
                if f is None:
                    continue
                rows.append({"date": d, "ticker": tkr, "BM": f["BM"],
                             "OP": f["OP"], "INV": f["INV"], "mcap": f["mcap"]})
        del facts
        if progress_every and n % progress_every == 0:
            print(f"  EDGAR {n}/{len(tickers)} tickers ({have_facts} with facts, "
                  f"{len(rows)} factor rows)", flush=True)
    return pd.DataFrame(rows)
