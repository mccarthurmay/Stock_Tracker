import yfinance as yf
from datetime import date, timedelta
from data.database import open_file, close_file
from data.analysis import RSIManager
import os
import pandas as pd
import concurrent.futures
from functools import partial
from datetime import datetime, timedelta
import numpy as np
from scipy import stats
from data.day_trade import DTCalc
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
dt = DTCalc()




def rsi_base(ticker, df, period='5d', interval='1m'):
    #ticker = yf.Ticker(ticker)
    #df = ticker.history(interval=interval, period=period)
    #df = alpha("GM")
    #df = dt.tiingo(ticker, frequency = "1min", start_date = "2022-07-30")
    #print(df)
    change = df['Close'].diff()
    change_up = change.copy()
    change_down = change.copy()

    change_up[change_up < 0] = 0
    change_down[change_down > 0] = 0
    
    # Adjust the rolling window for 1-minute data (14 periods = 14 minutes)
    mean_up = change_up.rolling(14).mean()
    mean_down = change_down.rolling(14).mean().abs()
    
    rsi = 100 * mean_up / (mean_up + mean_down)
    df['RSI'] = rsi
    
    # Adjust rolling windows for 1-minute data
    df['Avg_Volume'] = df['Volume'].rolling(14).mean()
    df['Volume_Change'] = df['Volume'].pct_change()
    df['RSI_MA'] = df['RSI'].rolling(5).mean()
    df['Volatility'] = df['Close'].rolling(14).std()
    
    df = df.dropna(subset=['RSI', 'Avg_Volume', 'RSI_MA', 'Volatility'])
    return df['RSI'].values, df['RSI'].values, df

def calculate_ci(data):
    if not data or len(data) < 2:  # We need at least 2 data points to calculate CI
        return "None", "None"
    
    data = [x for x in data if x is not None]  # Remove any None values
    
    if not data or len(data) < 2:
        return "None", "None"
    
    # Convert Timedelta to minutes if necessary
    if isinstance(data[0], timedelta):
        data = [d.total_seconds() / 60 for d in data]  # Convert to minutes
    
    mean = np.mean(data)
    
    if len(data) == 2:
        # If we only have 2 data points, return the range instead of CI
        return round(mean, 2), (round(min(data), 2), round(max(data), 2))
    
    try:
        ci = stats.t.interval(confidence=0.95, df=len(data)-1, loc=mean, scale=stats.sem(data))
        return round(mean, 2), (round(ci[0], 2), round(ci[1], 2))
    except Exception as e:
        print(f"Error calculating CI: {e}")
        return round(mean, 2), "Error"


class ab_lowManager:
    def __init__(self):
        self.reset_counters()

    def reset_counters(self):
        self.combined_ma_counter = {}
        self.combined_ma_dd = {}


    def find_lows_and_highs(self, rsi, df, ltr=(20, 30), ht=70):
        results = []
        i = 0
        while i < len(rsi):
            # Find the first instance within the ltr
            while i < len(rsi) and not (ltr[0] <= rsi[i] < ltr[1]):
                i += 1
            
            if i == len(rsi):
                break  # We've reached the end of the series
            
            low_value = rsi[i]
            low_date = df.index[i]
            
            # Look for RSI of ht
            j = i + 1
            while j < len(rsi) and rsi[j] < ht:
                j += 1
            
            if j < len(rsi):  # We found a rise to ht
                high_date = df.index[j]
                results.append((low_date, low_value, high_date, rsi[j]))
                i = j + 1  # Move past this high point
            else:
                break  # We've reached the end without finding a high

        return results
    
    def Average(self, lst): 
        return sum(lst) / len(lst) 

    def Average_Time(self, lst): 
        return (sum(td.total_seconds() for td in lst) / len(lst)) / 60  # Changed to minutes
    
    def MA(self, ticker, df, low_date, high_date, span1=20, span2=50, standardize=False):
        # Extend the date range to include enough previous data for moving averages and MACD
        extended_low_date = pd.to_datetime(low_date) - pd.Timedelta(days=max(span1, span2, 26) * 2)
        df = df[df.index >= extended_low_date]
        
        if standardize:
            mean = df['Close'].mean()
            std = df['Close'].std()
            close_data = (df['Close'] - mean) / std
        else:
            close_data = df['Close']
        
        MA = pd.DataFrame()
        MA['ST'] = close_data.ewm(span=span1, adjust=False).mean() 
        MA['LT'] = close_data.ewm(span=span2, adjust=False).mean()
        
        # Calculate MACD
        MA['EMA12'] = close_data.ewm(span=12, adjust=False).mean()
        MA['EMA26'] = close_data.ewm(span=26, adjust=False).mean()
        MA['MACD'] = MA['EMA12'] - MA['EMA26']
        MA['Signal'] = MA['MACD'].ewm(span=9, adjust=False).mean()
        MA['Histogram'] = MA['MACD'] - MA['Signal']
        
        MA.dropna(inplace=True)
        
        # Fetch longer-term data using yfinance
        yf_ticker = yf.Ticker(ticker)
        end_date = pd.to_datetime(low_date)
        start_date = end_date - pd.Timedelta(days=365)  # Get 1 year of data
        long_term_data = yf_ticker.history(start=start_date, end=end_date)
        
        # Calculate longer-term moving averages
        long_term_MA = pd.DataFrame()
        long_term_MA['MA50'] = long_term_data['Close'].rolling(window=50).mean()
        long_term_MA['MA100'] = long_term_data['Close'].rolling(window=100).mean()
        long_term_MA['MA200'] = long_term_data['Close'].rolling(window=200).mean()
        
        def determine_market(ma_data):
            if ma_data['ST'].iloc[-1] > ma_data['LT'].iloc[-1]:
                return "BULL"
            else:
                return "BEAR"
        
        def determine_macd_trend(ma_data):
            if ma_data['MACD'].iloc[-1] > ma_data['Signal'].iloc[-1]:
                return "BULLISH"
            else:
                return "BEARISH"
        
        def determine_long_term_trend(lt_ma_data):
            last_price = long_term_data['Close'].iloc[-1]
            if last_price > lt_ma_data['MA50'].iloc[-1] > lt_ma_data['MA100'].iloc[-1] > lt_ma_data['MA200'].iloc[-1]:
                return "STRONG_BULL"
            elif last_price > lt_ma_data['MA200'].iloc[-1]:
                return "BULL"
            elif last_price < lt_ma_data['MA200'].iloc[-1]:
                return "BEAR"
            else:
                return "NEUTRAL"
        
        low_market = determine_market(MA.loc[:low_date])
        low_macd_trend = determine_macd_trend(MA.loc[:low_date])
        
        # Check for convergence
        low_converging = self.is_converging(MA.loc[:low_date])
        
        # Check for MACD convergence
        low_macd_converging = self.is_converging(MA.loc[:low_date][['MACD', 'Signal']])
        
        # Determine long-term trend
        long_term_trend = determine_long_term_trend(long_term_MA)
        
        return {
            "low_date": {
                "market": low_market,
                "converging": low_converging,
                "macd_trend": low_macd_trend,
                "macd_converging": low_macd_converging,
                "long_term_trend": long_term_trend
            }
        }
    def is_converging(self, ma_data, window=20):
        if 'ST' in ma_data.columns and 'LT' in ma_data.columns:
            diff = abs(ma_data['ST'] - ma_data['LT'])
        elif 'MACD' in ma_data.columns and 'Signal' in ma_data.columns:
            diff = abs(ma_data['MACD'] - ma_data['Signal'])
        else:
            raise ValueError("Unexpected data format in is_converging")
        return diff.iloc[-window:].is_monotonic_decreasing

    def update_ma_counter(self, ma_l, ma_s, is_dd, dd_value):
        ma_l_key = f"MA_L {ma_l['low_date']['market']},{ma_l['low_date']['converging']}"
        ma_s_key = f"MA_S {ma_s['low_date']['market']},{ma_s['low_date']['converging']}"
        macd_key = f"MACD {ma_l['low_date']['macd_trend']},{ma_l['low_date']['macd_converging']}"
        lt_key = f"LT {ma_l['low_date']['long_term_trend']}"
        combined_key = f"{ma_l_key} + {ma_s_key} + {macd_key} + {lt_key}"
        
        self.combined_ma_counter[combined_key] = self.combined_ma_counter.get(combined_key, 0) + 1
        
        if is_dd:
            if combined_key not in self.combined_ma_dd:
                self.combined_ma_dd[combined_key] = {'count': 0, 'total': 0}
            self.combined_ma_dd[combined_key]['count'] += 1
            self.combined_ma_dd[combined_key]['total'] += dd_value

    def process_ticker(self, ticker, ltr, ht):
        results = {
            'n_d': [], 'd_i': [], 'd_d': [],
            'd_d_value': [], 'd_i_value': [], 'n_d_value': [],
            'avg_turnover': [], 'd_i_temp': [], 'd_d_temp': [], 'ma_l': [], 'ma_s': []
        }
        df = dt.tiingo(ticker, frequency="1min", start_date="2019-07-30")
        rsi, _, df = rsi_base(ticker, df)
        lows_and_highs = self.find_lows_and_highs(rsi, df, ltr, ht)
        
        for low_date, low_value, high_date, high_value in lows_and_highs:
            stock_data = df['Close'].loc[low_date:high_date]
            rsi_price = stock_data.iloc[0]
            lowest_price = stock_data.min()
            sell_price = stock_data.iloc[-1]
            ma_l = self.MA(ticker, df, low_date, high_date, span1=50, span2=200)
            ma_s = self.MA(ticker, df, low_date, high_date, span1=20, span2=50)
            p_decrease = (rsi_price - lowest_price) / rsi_price * 100
            p_increase = (sell_price - rsi_price) / rsi_price * 100

            # Update the MA combinations counter and track d_d occurrences
            self.update_ma_counter(ma_l, ma_s, p_decrease > 0 and p_increase < 0, p_increase)

            if p_decrease == 0 and p_increase > 0:
                results['n_d'].append(round(low_value, 2))
                results['n_d_value'].append(round(p_increase,2))
            elif p_decrease > 0 and p_increase > 0:
                results['d_i'].append(round(low_value, 2))
                results['d_i_value'].append(round(p_increase, 2))
                results['d_i_temp'].append(round(p_decrease, 2))
            elif p_decrease > 0 and p_increase < 0:
                results['d_d'].append(round(low_value, 2))
                results['d_d_value'].append(round(p_increase, 2))
                results['d_d_temp'].append(round(p_decrease, 2))
            results['avg_turnover'].append((high_date - low_date).total_seconds() / 60)
            results['ma_l'].append(ma_l)
            results['ma_s'].append(ma_s)

        return results
    
    #182/51 28
    #83/26 31
    
        
    def limit(self, ticker_list):
        ltr_list = [ (65, 70),  (60, 65), (55, 60), (50, 55), (45, 50), (40, 45), (35, 40), (30, 35)]

        # (65, 70),  (60, 65), (55, 60), (50, 55), (45, 50), (40, 45), (35, 40), (30, 35), (25, 30), (20, 25), (15, 20), (10, 15), (5, 10), (0,5)] 
        ht = 70

        for ltr in ltr_list:
            # Reset counters for each RSI range
            self.reset_counters()

            all_results = {
                'n_d': [], 'd_i': [], 'd_d': [],
                'd_d_value': [], 'd_i_value': [], 'n_d_value': [],
                'avg_turnover': [], 'd_i_temp': [], 'd_d_temp': [], 'ma_l': [], 'ma_s': []
            }
            process_ticker_partial = partial(self.process_ticker, ltr=ltr, ht=ht)
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_ticker = {executor.submit(process_ticker_partial, ticker): ticker for ticker in ticker_list}
                for future in concurrent.futures.as_completed(future_to_ticker):
                    ticker = future_to_ticker[future]
                    try:
                        result = future.result()
                        for key in all_results:
                            all_results[key].extend(result[key])
                    except Exception as e:
                        print(f'{ticker} generated an exception: {e}')
            # Calculate statistics
            d_d_mean, d_d_ci = calculate_ci(all_results['d_d_value'])
            d_i_mean, d_i_ci = calculate_ci(all_results['d_i_value'])
            n_d_mean, n_d_ci = calculate_ci(all_results['n_d_value'])
            d_i_temp_mean, d_i_temp_ci = calculate_ci(all_results['d_i_temp'])
            d_d_temp_mean, d_d_temp_ci = calculate_ci(all_results['d_d_temp'])
            turnover_mean, turnover_ci = calculate_ci(all_results['avg_turnover']) if all_results['avg_turnover'] else (None, None)

            print(f"\nResults for RSI range {ltr}:")
            #print("Decrease vs Increase")
            #print(f"{len(all_results['d_d'])} vs {len(all_results['d_i'])} + {len(all_results['n_d'])}")
            #print(f"Average Decrease %: {d_d_mean} (CI: {d_d_ci}) (limit {d_d_temp_mean}, CI: {d_d_temp_ci})")
            #print(f"Average DI Increase %: {d_i_mean} (CI: {d_i_ci}) (limit {d_i_temp_mean}, CI: {d_i_temp_ci})")
           # print(f"Average ND Increase %: {n_d_mean} (CI: {n_d_ci})")
            if turnover_mean and turnover_ci:
                print(f"Turnover CI: {turnover_mean:.2f} minutes (CI: {turnover_ci})")
            gain = self.calc(len(all_results['d_d']), (len(all_results['d_i']) + len(all_results['n_d'])), d_i_temp_mean, d_i_mean, turnover_mean)
            print(f"Gain: {gain:.4f}%")
            
            print("\nCombined MA Analysis (ordered by frequency):")
            sorted_combinations = sorted(self.combined_ma_counter.items(), key=lambda x: x[1], reverse=True)
            for combined_key, count in sorted_combinations:
                print(f"{combined_key}: {count}")
                if combined_key in self.combined_ma_dd:
                    dd_count = self.combined_ma_dd[combined_key]['count']
                    dd_avg = self.combined_ma_dd[combined_key]['total'] / dd_count if dd_count > 0 else 0
                    dd_percentage = (dd_count / count) * 100
                    print(f"  d_d occurrences: {dd_count} ({dd_percentage:.2f}%)")
                    print(f"  Average d_d value: {dd_avg:.2f}%")
                else:
                    print("  No d_d occurrences")
            
           # print("\n" + "="*200 + "\n")

    def calc(self, lenloss, lengain, d, i, turnover):
        p_loss = lenloss / (lenloss + lengain)
        p_gain = lengain / (lenloss + lengain)
        expected = p_gain * (i/100) + p_loss * (d/100)
        events_per_day = (24 * 60) / turnover  # Events per day
        value_per_day = (1+expected)**events_per_day
        gain_per_day = (value_per_day - 1) * 100
        return gain_per_day