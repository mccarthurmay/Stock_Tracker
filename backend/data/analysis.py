from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from datetime import datetime, timedelta
import pandas as pd
import warnings
import pytz
import os
import time
import threading
from data.fundamentals import FundamentalsManager
warnings.filterwarnings('ignore')


max_requests_per_minute = 200

class RateLimiter:
    def __init__(self, max_requests_per_minute):
        self.max_requests = max_requests_per_minute
        self.requests = []
        self.lock = threading.Lock()

    def wait_if_needed(self, is_cached=False):
        if is_cached:
            return
        while True:
            with self.lock:
                now = datetime.now()
                self.requests = [t for t in self.requests if (now - t).total_seconds() < 60]
                if len(self.requests) < self.max_requests:
                    self.requests.append(now)
                    return
                sleep_time = 60 - (now - self.requests[0]).total_seconds()
            if sleep_time > 0:
                time.sleep(sleep_time)


class AlpacaDataManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            api_key = os.getenv('ALPACA_KEY')
            api_secret = os.getenv('ALPACA_SECRET')
            if not api_key or not api_secret:
                raise ValueError("ALPACA_KEY and ALPACA_SECRET environment variables not set")
            cls._instance.historical_client = StockHistoricalDataClient(api_key, api_secret)
            cls._instance.trading_client = TradingClient(api_key, api_secret)
            cls._instance.rate_limiter = RateLimiter(max_requests_per_minute)
            cls._instance._cache = {}
        return cls._instance

    def __init__(self):
        pass  # singleton — all state set in __new__

    def get_data(self, ticker, days_back=5, frequency="1D"):
        """Get stock data from Alpaca with smart caching"""
        cache_key = f"{ticker}_{frequency}_{days_back}"

        if cache_key in self._cache:
            self.rate_limiter.wait_if_needed(is_cached=True)
            return self._cache[cache_key]

        self.rate_limiter.wait_if_needed(is_cached=False)

        end_dt = datetime.now(pytz.UTC) - timedelta(minutes=20)
        start_dt = end_dt - timedelta(days=days_back)

        timeframe_map = {
            "daily": TimeFrame.Day,
            "1D": TimeFrame.Day,
            "1H": TimeFrame.Hour,
            "1Min": TimeFrame.Minute
        }
        timeframe = timeframe_map.get(frequency, TimeFrame.Day)

        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            start=start_dt,
            end=end_dt,
            timeframe=timeframe,
            adjustment='raw'
        )

        try:
            response = self.historical_client.get_stock_bars(request)
            symbol_data = response[ticker]
            df = pd.DataFrame([{k: v for k, v in row} for row in symbol_data])
            if df.empty:
                return df
            df.set_index('timestamp', inplace=True)
            df.sort_index(ascending=True, inplace=True)
            self._cache[cache_key] = df
            return df
        except Exception as e:
            print(f"Error getting data for {ticker}: {e}")
            return pd.DataFrame()

    def get_price(self, ticker):
        for days_back in [0.003472, 1, 3, 5]:
            df = self.get_data(ticker, days_back=days_back, frequency="1Min")
            if not df.empty:
                return float(df['close'].iloc[-1])
        return None


class AnalysisManager:
    def __init__(self, data_manager=None):
        self.data_manager = data_manager or AlpacaDataManager()
        self.CI = CIManager(self.data_manager)
        self.RSI = RSIManager(self.data_manager)
        self.fundamentals = FundamentalsManager()

    def runall(self, ticker, db):
        try:
            enhanced_results = self.CI.enhanced_analysis(ticker, db)
            if enhanced_results is None:
                return
            percent_under = enhanced_results['CI_UNDER']
        except Exception as e:
            print("Enhanced analysis failed:", e)
            return

        try:
            rsi = self.RSI.rsi_calc(ticker)
        except Exception as e:
            print("RSI failed:", e)
            return

        try:
            ff = self.fundamentals.get_fundamentals(ticker)
        except Exception as e:
            print(f"Fundamentals failed for {ticker}: {e}")
            ff = {'BM': None, 'OP': None, 'INV': None, 'BETA': None, 'MCAP': None}

        db[ticker] = {
            'Ticker': ticker,
            '% Below 95% CI': percent_under,
            'RSI': rsi,
            'BM':   ff['BM'],
            'OP':   ff['OP'],
            'INV':  ff['INV'],
            'BETA': ff['BETA'],
            'MCAP': ff['MCAP'],
        }

    def runall_sell(self, ticker, db):
        try:
            enhanced_results = self.CI.enhanced_analysis(ticker, db)
            if enhanced_results is None:
                return
            percent_under = enhanced_results['CI_UNDER']
        except Exception as e:
            print(f"Enhanced analysis failed for {ticker}: {e}")
            return

        try:
            rsi = self.RSI.rsi_calc(ticker)
        except Exception as e:
            print("RSI error:", e)
            return

        try:
            ff = self.fundamentals.get_fundamentals(ticker)
        except Exception as e:
            print(f"Fundamentals failed for {ticker}: {e}")
            ff = {'BM': None, 'OP': None, 'INV': None, 'BETA': None, 'MCAP': None}

        db[ticker] = {
            'Ticker': ticker,
            '% Below 95% CI': percent_under,
            'RSI': rsi,
            'BM':   ff['BM'],
            'OP':   ff['OP'],
            'INV':  ff['INV'],
            'BETA': ff['BETA'],
            'MCAP': ff['MCAP'],
        }


class CIManager:
    def __init__(self, data_manager):
        self.data_manager = data_manager

    def enhanced_analysis(self, ticker, dbname):
        df = self.data_manager.get_data(ticker, days_back=90, frequency="daily")
        if df.empty:
            return None

        if df['close'].iloc[-1] <= 5:
            try:
                del dbname[ticker]
                print(f"{ticker} is a penny stock. Removing ticker.")
            except:
                print(f"{ticker} is a penny stock. Not adding ticker.")
            return None

        ci = df['close'].std() * 2
        mean_price = df['close'].mean()
        lower_bound = mean_price - ci

        try:
            current_price = self.data_manager.get_price(ticker)
            percent_under = (1 - current_price / lower_bound) * 100
        except:
            print(f"No current price available for {ticker}.")
            return None

        return {
            'CI_UNDER': round(percent_under, 2),
        }


class RSIManager:
    def __init__(self, data_manager=None):
        self.data_manager = data_manager or AlpacaDataManager()

    def rsi_base(self, ticker, days_back, frequency="1D"):
        df = self.data_manager.get_data(ticker, days_back, frequency)

        if df.empty:
            return pd.Series(), ticker, df

        change = df['close'].diff()
        change.dropna(inplace=True)

        change_up = change.copy()
        change_down = change.copy()

        change_up[change_up < 0] = 0
        change_down[change_down > 0] = 0

        mean_up = change_up.rolling(14).mean()
        mean_down = change_down.rolling(14).mean().abs()

        rsi = 100 * mean_up / (mean_up + mean_down)
        return rsi, ticker, df

    def rsi_calc(self, ticker, date=None):
        rsi, ticker, _ = self.rsi_base(ticker, 720)
        return round(rsi[date]) if date is not None else round(rsi[-1])
