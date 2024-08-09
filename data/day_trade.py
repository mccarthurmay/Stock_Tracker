import yfinance as yf
from datetime import date, timedelta
from data.database import open_file, close_file
from data.analysis import RSIManager, AnalysisManager
import os
import pandas as pd
import concurrent.futures
from functools import partial
from datetime import datetime, timedelta
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import tkinter as tk
from tkinter import messagebox, simpledialog
import random


class DTCalc:
    def rsi_base(self, ticker, period='5d', interval='1m'):
        ticker = yf.Ticker(ticker)
        df = ticker.history(interval=interval, period=period)
        
        change = df['Close'].diff()
        change_up = change.copy()
        change_down = change.copy()

        change_up[change_up < 0] = 0
        change_down[change_down > 0] = 0
        
        #(14 periods = 14 minutes)
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
        
        current_price = ticker.info['currentPrice']
        return df['RSI'].values, current_price, df

    def calculate_ci(self, data):
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
        
    def calc(self, lenloss, lengain, d, i, turnover):
            p_loss = lenloss / (lenloss + lengain)
            p_gain = lengain / (lenloss + lengain)
            expected = p_gain * (i/100) + p_loss * (d/100)
            events_per_day = (6.5 * 60) / turnover  # Events per day
            value_per_day = (1+expected)**events_per_day
            gain_per_day = (value_per_day - 1) * 100
            return gain_per_day, p_gain, p_gain

class DTData:
    def __init__(self):
        self.data_calc = DTCalc()

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

    

    def limit(self, tick, rsi_range):
        stock_list = tick
        ltr_list = rsi_range
        #ltr_list = [(65, 70), (60, 65), (55, 60), (50, 55), (45, 50), (40, 45), (35, 40), (30, 35), (25, 30), (20, 25), (15, 20), (10, 15), (5, 10), (0,5)] 
        ht = 70
        results = {
            'n_d': [], 'd_i': [], 'd_d': [],
            'd_d_value': [], 'd_i_value': [], 'n_d_value': [],
            'avg_turnover': [], 'd_i_temp': [], 'd_d_temp': []
        }
        
            
        # Calculate RSI, retrieve entire dataframe for 5 days with 1-minute intervals
        rsi, _, df = self.data_calc.rsi_base(tick, '5d', '1m')
        lows_and_highs = self.find_lows_and_highs(rsi, df, rsi_range, ht)
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
        
        d_d = results['d_d']
        d_d_value = results['d_d_value']
        d_i = results['d_i']
        d_i_value= results['d_i_value']
        n_d = results['n_d']
        n_d_value =  results['n_d_value']
        avg_turnover = results['avg_turnover']
        d_i_temp = results['d_i_temp']
        d_d_temp = results['d_d_temp']

        d_d_mean, d_d_ci = self.data_calc.calculate_ci(d_d_value)
        d_i_mean, d_i_ci = self.data_calc.calculate_ci(d_i_value)
        n_d_mean, n_d_ci = self.data_calc.calculate_ci(n_d_value)
        d_i_temp_mean, d_i_temp_ci = self.data_calc.calculate_ci(d_i_temp) 
        d_d_temp_mean, d_d_temp_ci = self.data_calc.calculate_ci(d_d_temp)
        
        turnover_mean, turnover_ci = self.data_calc.calculate_ci(results['avg_turnover']) if results['avg_turnover'] else None
        gain, p_pos, wl = self.data_calc.calc(len(results['d_d']), (len(results['d_i']) + len(results['n_d'])), d_i_temp_ci[0], d_i_mean , turnover_mean) #changed d_i_temp_mean for d_i_temp_ci[0]
        
        #print("Decrease vs Increase")
        #print(f"{len(all_results['d_d'])} vs {len(all_results['d_i']) + len(all_results['n_d'])}")
        #print(f"Average Decrease %: {d_d_mean} (CI: {d_d_ci}) (limit {d_d_temp_mean}, CI: {d_d_temp_ci})")
        #print(f"Average DI Increase %: {d_i_mean} (CI: {d_i_ci}) (limit {d_i_temp_mean}, CI: {d_i_temp_ci})")
        #print(f"Average ND Increase %: {n_d_mean} (CI: {n_d_ci})")
        #print(f"Turnover CI: {turnover_mean:.2f} minutes (CI: {turnover_ci})")
        #print(f"Gain: {gain:.4f}%")
        #print("\n" + "="*200 + "\n")
        return d_i_temp_mean, gain, turnover_mean, d_i_mean, d_i_ci, d_i_temp_ci, p_pos, wl

class DTManager:
    def __init__(self):
        self.data_manager = DTData()
        self.calc = DTCalc()
    
    def main(self, ticker, range = True):
        rsi, current_price, df = self.calc.rsi_base(ticker)
        
        if range == True:
            #print(f"Current RSI: {rsi[-1]:.2f}")
            #print(f"Current Price: ${current_price:.2f}")
            #messagebox.showinfo("RSI Information", f"{rsi[-1]:.2f}")
            #rsi1= simpledialog.askstring("Input", "Range for analysis (#1): ").strip()
            #rsi2= simpledialog.askstring("Input", "Range for analysis (#2): ").strip()
            rsi_range = (int(rsi[-1] - 5), int(rsi[-1] + 5)) #opt to switch to automatic 
            stop, gain, time, p_increase, ci_increase, ci_decrease, p_gain, wl = self.data_manager.limit(ticker, rsi_range)
            stop_l = (1 - ci_decrease[0] / 100) * current_price
            stop = (1 + (ci_increase[0]/100)) * current_price # lower ci 
            limit = (1 + (p_increase/100)) * current_price # average
            #print(f"Stop Loss: ${stop_l}")
            #print(f"Stop: ${stop} Limit: ${limit}")
            return rsi[-1], current_price, stop_l, gain, time, stop, limit, wl
            
        else:
            c_rsi = rsi[-1]
            if c_rsi < 65:
                rsi_range = (int(c_rsi- 5), int(c_rsi + 5))
                stop, gain, time, p_increase, ci_increase, ci_decrease, p_pos, wl = self.data_manager.limit(ticker, rsi_range)
                return c_rsi, ticker, gain, p_pos
            else:
                pass
        
     
    def find(self):
        with open("./storage/ticker_lists/safe_tickers.txt", "r") as stock_file:
            stock_list = stock_file.read().split('\n')
        
        #stock_list = ["AAPL", "UNH", "CEG", "OXY", "WDC", "LLY", "WBD", "SNPS", "OKE", "NDAQ", "AMZN"]
        def process_ticker(ticker):
            try:
                rsi, ticker, gain, p_pos = self.main(ticker, range=False)
                return round(gain, 2), ticker, round(rsi, 0), round(p_pos, 2)
            except Exception as e: #occurs for index and if ticker is above 65
                return None

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = list(executor.map(process_ticker, stock_list))

        # Filter out None values before sorting
        results = [result for result in results if result is not None]

        sorted_full = sorted(results)
        
        return sorted_full

class DTViewer:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title("Day Trading Module")
        self.root.geometry("300x300+700+100")
        self.dt_manager = DTManager()

    def run(self):
        task = simpledialog.askstring("Input", "Find best stock (1) or Run (2)?: ").strip()
        if task == '1':
            results = self.dt_manager.find()
            messagebox.showinfo(title="RSI", message=results)
            print(results)
        ticker = simpledialog.askstring("Input", "Ticker: ").strip()
        rsi, current_price, stop_l, gain, time, stop, limit, wl = self.dt_manager.main(ticker)
        self.ResultFrame(rsi, current_price, stop_l, gain, time, stop, limit, wl)

    def ResultFrame(self, rsi, current_price, stop_l, gain, time, stop, limit, wl):
        frame = tk.Frame(self.root) 
        frame.pack(fill=tk.X, padx=10, pady=10)  
        canvas = tk.Canvas(frame, width=250, height=275, highlightthickness = 1, highlightbackground = 'black')
        canvas.pack(side=tk.TOP)

        y_pos = 25
        canvas.create_text(125, y_pos, text="Potential Sell", font=("Arial", 16), anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Current RSI: {rsi:.2f}", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Current Price: ${current_price:.2f}", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Stop Loss: ${stop_l:.2f}", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Stop: ${stop:.2f} Limit: ${limit:.2f}")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Estimated Gain Per Day: {gain:.4f}%", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Estimated Turnover Time: {time:.0f} minutes", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"RSI Calc Range: ({rsi - 5:.2f}, {rsi + 5:.2f})", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Win/Loss Percentage: {wl:.1f}%", anchor = "center")

