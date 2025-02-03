from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from scipy.stats import linregress
import matplotlib.pyplot as plt
from sklearn.metrics.pairwise import cosine_similarity
import pytz
import os
import config
import time
from datetime import datetime

class RateLimiter:
    def __init__(self, max_requests_per_minute):
        self.max_requests = max_requests_per_minute
        self.requests = []
    
    def wait_if_needed(self):
        now = datetime.now()
        # Remove requests older than 1 minute
        self.requests = [req_time for req_time in self.requests 
                        if (now - req_time).total_seconds() < 60]
        
        if len(self.requests) >= self.max_requests:
            # Get the oldest request
            oldest_request = self.requests[0]
            # Calculate how long to wait
            sleep_time = 60 - (now - oldest_request).total_seconds()
            if sleep_time > 0:
                time.sleep(sleep_time)
            # Clear old requests after waiting
            self.requests = []
        
        # Add the new request
        self.requests.append(now)


class AlpacaDataManager:
    _instance = None

    def __init__(self):
        self.data_client = StockHistoricalDataClient
        self.rate_limiter = RateLimiter(max_requests_per_minute=100)
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.api_key = os.getenv('ALPACA_KEY')
            cls._instance.api_secret = os.getenv('ALPACA_SECRET')
            if not cls._instance.api_key or not cls._instance.api_secret:
                raise ValueError("ALPACA_KEY and ALPACA_SECRET environment variables not set")
            cls._instance.historical_client = StockHistoricalDataClient(
                cls._instance.api_key, 
                cls._instance.api_secret
            )
            cls._instance.trading_client = TradingClient(
                cls._instance.api_key,
                cls._instance.api_secret
            )
            cls._instance._cache = {}
        return cls._instance
        
    def get_data(self, ticker, days_back=5, frequency="1D"):
        self.rate_limiter.wait_if_needed()
        
        """Get stock data from Alpaca with smart caching"""
        cache_key = f"{ticker}_{frequency}_{days_back}"
        eastern_tz = pytz.timezone('US/Eastern')
        
        # Check cache
        if cache_key in self._cache:
            return self._cache[cache_key]
            
        # Calculate dates for API call
        # End time is now minus 15 minutes to avoid subscription limitations
        end_dt = datetime.now(pytz.UTC) - timedelta(minutes=15)
        start_dt = end_dt - timedelta(days=days_back)
        
        # Convert frequency string to TimeFrame
        timeframe_map = {
            "daily": TimeFrame.Day,
            "1D": TimeFrame.Day,
            "1H": TimeFrame.Hour,
            "1Min": TimeFrame.Minute
        }
        timeframe = timeframe_map.get(frequency, TimeFrame.Day)
        
        # Make API call
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            start=start_dt,
            end=end_dt,
            timeframe=timeframe,
            adjustment='raw'  # Use raw data since we don't have premium access
        )

        
        try:
            response = self.historical_client.get_stock_bars(request)
            # Convert to DataFrame
                    #print(f"Processing {symbol}")
            symbol_data = response[ticker]
            data_dicts = [
                {key: value for key, value in row}  # Convert each row of tuples into a dictionary
                for row in symbol_data
            ]

            # Create a DataFrame from the list of dictionaries
            df = pd.DataFrame(data_dicts)

            
            if df.empty:
                return df
                
            df.set_index('timestamp', inplace=True)
            df.sort_index(ascending=True, inplace=True)
            
            # Cache the result
            self._cache[cache_key] = df
            return df
            
        except Exception as e:
            print(f"Error getting data for {ticker}: {e}")
            return pd.DataFrame()
    
    def get_price(self, ticker):
        """Get latest available price (delayed by 15 minutes)"""
        try:
            # Use get_data to fetch the recent data with 5 minute lookback
            df = self.get_data(ticker, days_back=0.003472, frequency="1Min")  # ~5 minutes in days
            if not df.empty:
                return float(df['close'].iloc[-1])
            
            df = self.get_data(ticker, days_back = 1, frequency="1Min")
            if not df.empty:
                return float(df['close'].iloc[-1])
            
            df = self.get_data(ticker, days_back = 3, frequency="1Min")
            if not df.empty:
                return float(df['close'].iloc[-1])
            
            df = self.get_data(ticker, days_back = 5, frequency="1Min")
            if not df.empty:
                return float(df['close'].iloc[-1])
            
            return None
        
                
        except Exception as e:
            print(f"Error getting price for {ticker}: {e}")
            return None
            
            

    
    def clear_cache(self):
        """Clear the entire cache"""
        self._cache = {}
        print("Cache cleared")

    def get_cache_info(self):
        """Print information about what's currently in cache"""
        print("\nCurrent Cache Contents:")
        for key in self._cache.keys():
            df = self._cache[key]
            print(f"Key: {key}")
            print(f"Shape: {df.shape}")
            print(f"Date Range: {df.index[0]} to {df.index[-1]}\n")

class AnalysisManager:
    def __init__(self):
        self.CI = CIManager()
        self.RSI = RSIManager()
        self.data_manager = AlpacaDataManager()
        self.rate_limiter = RateLimiter(max_requests_per_minute=150)
        
    def estimate_processing_time(self, ticker_count):
        """
        Estimates the processing time based on API rate limits and number of tickers
        Returns estimated time in seconds
        """
        # Each ticker requires approximately:
        # - 1 call for CI calculations (90 days data)
        # - 1 call for RSI calculations (720 days data)
        # - 1 call for MA calculations (60 days data)
        # - 1 call for current price
        API_CALLS_PER_TICKER = 4
        
        total_api_calls = ticker_count * API_CALLS_PER_TICKER
        rate_limit_per_minute = 150  # From rate limiter
        
        # Calculate minutes needed based on rate limit
        estimated_minutes = (total_api_calls / rate_limit_per_minute)
        # Add 10% buffer for processing overhead
        estimated_seconds = (estimated_minutes * 60) * 1.1
        return round(estimated_seconds)
        
    def runall(self, ticker, db):
        self.rate_limiter.wait_if_needed()

        percent_under = round(self.CI.under_confidence(ticker, db).iloc[0])
        percent_over = round(self.CI.over_confidence(ticker, db).iloc[0])
        ma, ma_date, converging = self.RSI.MA(ticker, graph = False)
        rsi = self.RSI.rsi_calc(ticker, graph = False, date = None)
        buy_bool = self.buy(rsi, percent_under)
        short_bool = self.short(rsi, percent_over)
        cos, msd = self.RSI.rsi_accuracy(ticker)
        turnover = self.RSI.rsi_turnover(ticker)
        db[ticker] = {
            'Ticker': ticker,
            'Buy': buy_bool,
            'Short': short_bool,
            '% Above 95% CI': percent_over,
            '% Below 95% CI': percent_under,
            'RSI': rsi,
            'RSI COS': round(cos,2),
            'RSI MSD': round(msd,2),
            'RSI Avg Turnover': turnover,
            'MA': (ma, ma_date),
            'MA Converging': converging
        }


    def runall_sell(self, ticker, db, price):
        percent_under = round(self.CI.under_confidence(ticker, db).iloc[0])
        percent_over = round(self.CI.over_confidence(ticker, db).iloc[0])
        ma, ma_date, converging = self.RSI.MA(ticker, graph = False)
        rsi = self.RSI.rsi_calc(ticker, graph = False, date = None)
        sell_bool = self.sell(rsi)
        short_sell_bool = self.short_sell(rsi)
        cos, msd = self.RSI.rsi_accuracy(ticker)
        turnover = self.RSI.rsi_turnover(ticker)
        #if sell_bool == True:
        #    messagebox.showinfo(title = "SELL ALERT", message = f"{ticker} is currently a sell.")
        if ticker in db:
            #If it exists, preserve the buy price
            buy_price = db[ticker]['Buy Price']
        
        else:
            #If it's a new entry, use the provided price
            buy_price = price
        
        #Update the database entry
        db[ticker] = {
            'Ticker': ticker,
            'Buy Price': buy_price,
            'Sell': sell_bool,
            'Short Sell': short_sell_bool,
            '% Above 95% CI': percent_over,
            '% Below 95% CI': percent_under,
            'RSI': rsi,
            'RSI COS': round(cos, 2),
            'RSI MSD': round(msd, 2),
            'RSI Avg Turnover': turnover,
            'MA': (ma, ma_date),
            'MA Converging': converging,
        }


    #BUY/SELL BOOL
    def buy(self, rsi, percent_under):
        if percent_under > -1 and rsi < 31:
            return True
        else:
            return False
        


                
                

    def short(self, rsi, percent_over):
        if percent_over > -1 and rsi > 79:
            return True
        else:
            return False

    def sell(self, rsi):
        if rsi > 69:
            return True
        else:
            return False

    def short_sell(self, rsi): #should switch to something else
        if rsi < 31:
            return True
        else:
            return False




class CIManager:
    def __init__(self):
        self.data_manager = AlpacaDataManager()

    def under_confidence(self, ticker, dbname):
        # closing price of input stock
        df = self.data_manager.get_data(ticker, days_back=90, frequency="daily")  # 3 months
        df_close = pd.DataFrame(df['close'])
        if int(df_close.iloc[-1]) > 5:
            
            # confidence interval of 95% = standard deviation of data * 2
            ci = df_close.std() * 2
            # lower bound of 95%
            lower_bound = df_close.mean() - ci
            try:
                current_price = self.data_manager.get_price(ticker)
                # percent over the lower bound of 2 std deviations (95% confidence interval)
                percent_under = (1 - current_price / lower_bound) * 100
                return percent_under
            except:
                print(f"No current price available for {ticker}.")

        else:
            try:
                del dbname[ticker]
                print(f"{ticker} is a penny stock. Removing ticker.")
            except:
                print(f"{ticker} is a penny stock. Not adding ticker.")

    #CONFIDENCE - OVER
    def over_confidence(self, ticker, dbname):
        # closing price of input stock
        df = self.data_manager.get_data(ticker, days_back=90, frequency="daily")  # 3 months
        
        df_close = pd.DataFrame(df['close'])

        if int(df_close.iloc[-1]) > 5:
            # confidence interval of 95% = standard deviation of data * 2
            ci = df_close.std() * 2
            # upper bound of 95%
            upper_bound = df_close.mean() + ci
            try:
                current_price = self.data_manager.get_price(ticker)
                # percent over the upper bound of 2 std deviations (95% confidence interval)
                percent_under = (1 - upper_bound/current_price) * 100
                return percent_under
            except:
                print(f"No current price available for {ticker}.")

        else:
            try:
                del dbname[ticker]
                print(f"{ticker} is a penny stock. Removing ticker.")
            except:
                print(f"{ticker} is a penny stock. Not adding ticker.")



class RSIManager:
    def __init__(self):
        self.CI = CIManager()
        self.data_manager = AlpacaDataManager()

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

    def rsi_calc(self, ticker, graph, date):
        rsi, ticker, df = self.rsi_base(ticker, 720)

        #Graph
        if graph == True:
            self.plot_data(rsi, ticker, df)
        elif date != None:
            return (round(rsi[date]))
        else:
            rsi = round(rsi[-1])
            return rsi
        

    def rsi_accuracy(self, ticker):
        rsi, ticker, df = self.rsi_base(ticker, 720)
        df = df['close']
        #calculate mean + std of both datasets
        mean_df = np.mean(df)
        mean_rsi = np.mean(rsi)
        std_df = np.std(df)
        std_rsi = np.std(rsi)
        
        #standardize data
        df_standardized = (df - mean_df) / std_df
        rsi_standardized = (rsi - mean_rsi) / std_rsi


        #COSINE SIMIlARITY - penalizes larger differences more heavily
        df_standardized = df_standardized.iloc[14:] #deleting first 13 numbers due to rolling average producing NAN in rsi
        rsi_standardized = rsi_standardized.iloc[13:] #deleting first 13 numbers due to rolling average producing NAN in rsi
        df_standardized = df_standardized.values.reshape(1,-1)
        rsi_standardized = rsi_standardized.values.reshape(1,-1)
        cos_accuracy = cosine_similarity(df_standardized, rsi_standardized)[0][0]


        #MEAN SQUARED DIFFERENCE - prioritizes relative direction and order of data points more than absolute values
        MSD = (np.mean(np.square(df_standardized - rsi_standardized)))
        msd_accuracy = 1 / (1 + MSD)

        return cos_accuracy, msd_accuracy

    def rsi_turnover(self, ticker):
        rsi, ticker, df = self.rsi_base(ticker, 720)
    
        rsi_frame = rsi.iloc[13:]
        low_threshold = True
        peak_dates = []   
        for date, value in rsi_frame.items():
            if value > 70 and low_threshold == True:
                peak_dates.append(date)
                low_threshold = False
            if value < 30:
                low_threshold = True

        turnover = []
        for i in range(len(peak_dates) - 1):
            date1_obj = datetime.fromisoformat(str(peak_dates[i]))
            date2_obj = datetime.fromisoformat(str(peak_dates[i + 1]))
            delta = date2_obj - date1_obj
            turnover.append(delta.days)
        average_turnaround = sum(turnover) / len(turnover)
        return round(average_turnaround, 0)


    def plot_data(self, rsi, ticker, df):
        plt.style.use('fivethirtyeight')
        plt.rcParams['figure.figsize'] = (15,10)
        
        # Prepare data and ensure alignment
        df = df.iloc[13:]  # Remove first 13 rows from price data
        rsi = rsi[13:]     # Remove first 13 rows from RSI
        
        # Make sure indexes match
        common_index = df.index.intersection(rsi.index)
        df = df.loc[common_index]
        rsi = rsi.loc[common_index]
        
        # Calculate MAs
        s_df = {}
        l_df = {}
        s_df['MA'] = df['close'].rolling(window=20).mean()
        l_df['MA'] = df['close'].rolling(window=50).mean()
        
        # Create figure and primary axis
        fig, ax1 = plt.subplots(figsize=(15,10))
        
        # Plot price data on primary axis
        ax1.plot(df.index, df['close'], linewidth=2, label='Price', color='blue')
        ax1.plot(df.index, s_df['MA'], label='Short-Term MA', color='Red', linestyle='--', linewidth=2)
        ax1.plot(df.index, l_df['MA'], label='Long-Term MA', color='Purple', linestyle='--', linewidth=2)
        ax1.set_ylabel('Price', color='black')
        ax1.tick_params(axis='y', labelcolor='black')
        
        # Create secondary axis for RSI
        ax2 = ax1.twinx()
        ax2.plot(df.index, rsi, color='orange', linewidth=1, label='RSI', alpha=0.7)
        ax2.set_ylabel('RSI', color='orange')
        ax2.tick_params(axis='y', labelcolor='orange')
        
        # Add RSI levels
        ax2.axhline(30, linestyle='--', linewidth=1.5, color='green', alpha=0.5)
        ax2.axhline(70, linestyle='--', linewidth=1.5, color='red', alpha=0.5)
        ax2.set_ylim(0, 100)
        
        # Combine legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        plt.title(f'{ticker} Price and RSI')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    # Only used for individual calls; remains on yFinance
    def MA(self, ticker, graph, frequency="daily", days_back = 60, span1=5, span2=20, standardize=False):
        df = self.data_manager.get_data(ticker, days_back, frequency)
        
        if standardize:
            mean = df['close'].mean()
            std = df['close'].std()
            close_data = (df['close'] - mean) / std
        else:
            close_data = df['close']
        
        MA = pd.DataFrame()
        MA['ST'] = close_data.ewm(span=span1, adjust=False).mean() 
        MA['LT'] = close_data.ewm(span=span2, adjust=False).mean()
        MA.dropna(inplace=True)
        
        converging = False
        latest_date = None
        converging_li = []    
        latest_market = None
        
        for i in reversed(range(len(MA))):
            date = MA.index[i] 
            if i > 0:
                if MA['ST'].iloc[-1] > MA['LT'].iloc[-1]:
                    latest_date = date
                    latest_market = "BULL"
                    break  
                elif  MA['ST'].iloc[-1] < MA['LT'].iloc[-1]:
                    latest_date = date
                    latest_market = "BEAR"
                    break 
                converging_li.append(abs(MA['LT'].iloc[i] - MA['ST'].iloc[i]))
        
        converging_li.reverse()
        if len(converging_li) >= 20 and all(converging_li[i] < converging_li[i-1] for i in range(-1, -21, -1)):
            converging = True
        
        if standardize:
            MA['ST'] = (MA['ST'] * std) + mean
            MA['LT'] = (MA['LT'] * std) + mean
        
        if graph:
            plt.figure(figsize=(12, 6))
            plt.plot(df.index, MA['ST'], label=f'{span1}-day EMA', color='blue')
            plt.plot(df.index, MA['LT'], label=f'{span2}-day EMA', color='red')
            plt.plot(df.index, df['close'], label="close Price", alpha=0.5, color='gray')
            plt.title(f"{ticker} Moving Averages Analysis\n{span1}-day vs {span2}-day EMA")
            plt.xlabel("Date")
            plt.ylabel(f"Price ({ticker})")
            plt.grid(True, alpha=0.3)
            plt.legend(loc='best')
            
            # Add market condition annotation if available
            if latest_market and latest_date:
                plt.figtext(0.02, 0.02, f'Market Condition: {latest_market}, {converging}', 
                          bbox=dict(facecolor='white', alpha=0.8),
                          fontsize=10)
            
            plt.tight_layout()
            plt.show()
        
        if latest_date:
            latest_date_str = latest_date.strftime('%m-%d')
            return latest_market, latest_date_str, converging
        else:
            print("No recent crossing detected")
            return None, None, converging

    def macd(self, ticker, frequency = "daily", fast_period=12, slow_period=26, signal_period=9):

        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        df = self.data_manager.get_data(ticker, days_back = 60, frequency= frequency)
        if df.empty:
            return None


        df['EMA_fast'] = df['close'].ewm(span=fast_period, adjust=False).mean()
        df['EMA_slow'] = df['close'].ewm(span=slow_period, adjust=False).mean()

        df['MACD'] = df['EMA_fast'] - df['EMA_slow']

        df['Signal'] = df['MACD'].ewm(span=signal_period, adjust=False).mean()

        current_data = df.iloc[-1]

        if current_data['MACD'] > current_data['Signal']:
            return "BULL"
        else:
            return "BEAR"
        


#possibly add this to main filter function,(most recent rsi score indicates 'buy' or add rsi score to print in summary)
#not done
def day_movement(ticker):
    stock_data = yf.Ticker(ticker).history(period="3mo").reset_index(drop=True)
    stock_close = pd.DataFrame(stock_data['close'])
    stock_close = stock_close.iloc[-1]
    stock_curr = yf.Ticker(ticker).info['currentPrice']
    stock_perc = (stock_close - stock_curr) / stock_close
    print(f"{float(stock_perc.values):.15f}")


#SHOWINFO
def showinfo(ticker):
    stock_data = yf.Ticker(ticker)
    stock_history = stock_data.history(period = '3mo')
    print('\n',stock_data.info['longBusinessSummary'])
    stock_close = pd.DataFrame(stock_history['close']).iloc[-2].item()
    stock_curr = yf.Ticker(ticker).info['currentPrice']
    print('\nStock close:',stock_close,'\nCurrent Price:', stock_curr)


  
def main():
    # Initialize the manager
    manager = AlpacaDataManager()
    RM = RSIManager()
    AM = AnalysisManager()
    
    # First get_data call will cache the data
    print("First call - should fetch from API:")
    macd_result = RM.macd(ticker="AAPL")
    print(f"MACD Result: {macd_result}")
    
    # Check cache after first call
    print("\nCache after first call:")
    manager.get_cache_info()
    
    # Second call should use cached data
    print("\nSecond call - should use cache:")
    macd_result = RM.macd(ticker="NVDA")
    print(f"MACD Result: {macd_result}")

    # Check cache again
    print("\nCache should be the same:")
    manager.get_cache_info()
    
    print("\nSecond call - should use cache:")
    macd_result = RM.macd(ticker="NVDA")
    print(f"MACD Result: {macd_result}")
    print("\nSecond call - should use cache:")
    macd_result = RM.macd(ticker="NVDA")
    print(f"MACD Result: {macd_result}")

if __name__ == "__main__":
    main()


###CALLING yf.ticker.history for many functions... may be increasing time signfificantly


###Add to winrate/shortrate... 'current rsi current approaching' and update that each time


#Depreciated 
"""
#VISUALIZE CONFIDENCE INTERVAL
def con_plot(ticker):

    tick = yf.Ticker(ticker)
    df_list = tick.history(interval='1d', period='20mo')
    df = pd.DataFrame(df_list['close'])
    ci_list = []
    ci = df.std() * 2
    upper_bound = df.mean() + ci
    lower_bound = df.mean() - ci
    mean = df.mean()
    current = yf.Ticker(ticker).info['currentPrice']
    print(f"CI:{ci.values} \nUpper Bound:{upper_bound.values} \nLower Bound:{lower_bound.values} \nMean:{mean.values} \nCurrent:{current}")
    for close in df_list['close']:
        percent_lower = (close - lower_bound) / (upper_bound - lower_bound) * 100
        ci_list.append(percent_lower)  # Append to list
    plt.style.use('fivethirtyeight')
    #figure size
    plt.rcParams['figure.figsize'] = (15,10)

    ax1 = plt.subplot2grid((10,1), (0,0), rowspan = 4, colspan = 1)
    ax2 = plt.subplot2grid((10, 1), (5, 0), rowspan=4, colspan=1)

    ax1.plot(df['close'], linewidth = 2)
    ax1.set_title('close prices')

    ax2.set_title('Confidence Interval')
    ax2.plot(ci_list, color = 'orange', linewidth = 1)

    #Oversold
    ax2.axhline(30, linestyle = '--', linewidth = 1.5, color = 'green')
    ax2.axhline(70, linestyle = '--', linewidth = 1.5, color = 'red')

    plt.show()



#SLOPE CALCULATOR
#def slope(ticker):
    #df = yf.Ticker(ticker)
    #df = df.history(interval='1d', period='20mo')
    #dates = np.arange(len(df))
    #closing_prices = df['close'].values
    #slope, _, _, _, _ = linregress(dates, closing_prices)
    #return slope
    #not sure if slope works, maybe do period prior to crash so 3-20 months    
"""

## COPY AND PASTE SCALPING STUFF - correct way to call api