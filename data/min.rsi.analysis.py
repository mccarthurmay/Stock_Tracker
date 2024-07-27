import yfinance as yf
from datetime import date, timedelta
from data.database import open_file, close_file
from data.analysis import rsi_calc, sell, rsi_base
import os
import pandas as pd
import concurrent.futures
from functools import partial
from datetime import datetime, timedelta
import numpy as np
from scipy import stats

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def rsi_base(ticker, period='7d', interval='1m'):
    ticker = yf.Ticker(ticker)
    df = ticker.history(interval=interval, period=period)
    
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
        pass

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

    def process_ticker(self, ticker, ltr, ht):
        results = {
            'n_d': [], 'd_i': [], 'd_d': [],
            'd_d_value': [], 'd_i_value': [], 'n_d_value': [],
            'avg_turnover': [], 'd_i_temp': [], 'd_d_temp': []
        }
        
        # Calculate RSI, retrieve entire dataframe for 7 days with 1-minute intervals
        rsi, _, df = rsi_base(ticker, '7d', '1m')

        lows_and_highs = self.find_lows_and_highs(rsi, df, ltr, ht)
        
        for low_date, low_value, high_date, high_value in lows_and_highs:
            stock_data = df['Close'].loc[low_date:high_date]
            rsi_price = stock_data.iloc[0]
            lowest_price = stock_data.min()
            sell_price = stock_data.iloc[-1]
            
            p_decrease = (rsi_price - lowest_price) / rsi_price * 100
            p_increase = (sell_price - rsi_price) / rsi_price * 100

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
            results['avg_turnover'].append((high_date - low_date).total_seconds() / 60)  # Convert to minutes

        return results

    def limit(self, tick, rsi_range):
        stock_list = tick
        ltr_list = rsi_range
        #ltr_list = [(65, 70), (60, 65), (55, 60), (50, 55), (45, 50), (40, 45), (35, 40), (30, 35), (25, 30), (20, 25), (15, 20), (10, 15), (5, 10), (0,5)] 
        ht = 70

        for ltr in ltr_list:
            all_results = {
                'n_d': [],  # No decrease across the board
                'd_i': [],  # Decrease after RSI, Increase at the end of the interval
                'd_d': [],  # Decrease after RSI, Decrease at the end of the interval
                'd_d_value': [], #Amount of decrease if both decrease
                'd_i_value': [], #Amount of increase if decrease after RSI but increase at end
                'n_d_value': [], #Amount of increase if no decrease
                'avg_turnover': [], #Time between buy/sell
                'd_i_temp': [], #Amount of temporary decrease in the (decrease, increase)
                'd_d_temp': [] #Amount of temporary decrease in the (decrease, decrease)
            }
            
            process_ticker_partial = partial(self.process_ticker, ltr=ltr, ht=ht)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_ticker = {executor.submit(process_ticker_partial, ticker): ticker for ticker in stock_list}
                for future in concurrent.futures.as_completed(future_to_ticker):
                    ticker = future_to_ticker[future]
                    try:
                        result = future.result()
                        for key in all_results:
                            all_results[key].extend(result[key])
                    except Exception as e:
                        print(f'{ticker} generated an exception: {e}')

            print(ltr)
            d_d = all_results['d_d']
            d_d_value = all_results['d_d_value']
            d_i = all_results['d_i']
            d_i_value= all_results['d_i_value']
            n_d = all_results['n_d']
            n_d_value =  all_results['n_d_value']
            avg_turnover = all_results['avg_turnover']
            d_i_temp = all_results['d_i_temp']
            d_d_temp = all_results['d_d_temp']

            d_d_mean, d_d_ci = calculate_ci(d_d_value)
            d_i_mean, d_i_ci = calculate_ci(d_i_value)
            n_d_mean, n_d_ci = calculate_ci(n_d_value)
            d_i_temp_mean, d_i_temp_ci = calculate_ci(d_i_temp)
            d_d_temp_mean, d_d_temp_ci = calculate_ci(d_d_temp)
            
            # Calculate CI for turnover times
            turnover_mean, turnover_ci = calculate_ci(all_results['avg_turnover']) if all_results['avg_turnover'] else None

            print("Decrease vs Increase")
            print(f"{len(all_results['d_d'])} vs {len(all_results['d_i']) + len(all_results['n_d'])}")
            print(f"Average Decrease %: {d_d_mean} (CI: {d_d_ci}) (limit {d_d_temp_mean}, CI: {d_d_temp_ci})")
            print(f"Average DI Increase %: {d_i_mean} (CI: {d_i_ci}) (limit {d_i_temp_mean}, CI: {d_i_temp_ci})")
            print(f"Average ND Increase %: {n_d_mean} (CI: {n_d_ci})")
            print(f"Turnover CI: {turnover_mean:.2f} minutes (CI: {turnover_ci})")
            gain = self.calc(len(all_results['d_d']), (len(all_results['d_i']) + len(all_results['n_d'])), d_i_temp_mean, d_i_mean , turnover_mean)
            print(f"Gain: {gain:.4f}%")
            print("\n" + "="*200 + "\n")
            return d_i_temp_mean

    def calc(self, lenloss, lengain, d, i, turnover):
        p_loss = lenloss / (lenloss + lengain)
        p_gain = lengain / (lenloss + lengain)
        expected = p_gain * (i/100) + p_loss * (d/100)
        events_per_day = (24 * 60) / turnover  # Events per day
        value_per_day = (1+expected)**events_per_day
        gain_per_day = (value_per_day - 1) * 100
        return gain_per_day