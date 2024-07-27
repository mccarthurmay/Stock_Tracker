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
        return df['RSI'].values, df['RSI'].values, df

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
            return gain_per_day

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

    def process_ticker(self, ticker, ltr, ht):
        results = {
            'n_d': [], 'd_i': [], 'd_d': [],
            'd_d_value': [], 'd_i_value': [], 'n_d_value': [],
            'avg_turnover': [], 'd_i_temp': [], 'd_d_temp': []
        }
        
        # Calculate RSI, retrieve entire dataframe for 5 days with 1-minute intervals
        rsi, _, df = self.data_calc.rsi_base(ticker, '5d', '1m')

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
                'n_d': [], 'd_i': [], 'd_d': [],
                'd_d_value': [], 'd_i_value': [], 'n_d_value': [],
                'avg_turnover': [], 'd_i_temp': [], 'd_d_temp': []
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

            d_d_mean, d_d_ci = self.data_calc.calculate_ci(d_d_value)
            d_i_mean, d_i_ci = self.data_calc.calculate_ci(d_i_value)
            n_d_mean, n_d_ci = self.data_calc.calculate_ci(n_d_value)
            d_i_temp_mean, d_i_temp_ci = self.data_calc.calculate_ci(d_i_temp)
            d_d_temp_mean, d_d_temp_ci = self.data_calc.calculate_ci(d_d_temp)
            
            turnover_mean, turnover_ci = self.data_calc.calculate_ci(all_results['avg_turnover']) if all_results['avg_turnover'] else None
            gain = self.data_calc.calc(len(all_results['d_d']), (len(all_results['d_i']) + len(all_results['n_d'])), d_i_temp_mean, d_i_mean , turnover_mean)
            #print("Decrease vs Increase")
            #print(f"{len(all_results['d_d'])} vs {len(all_results['d_i']) + len(all_results['n_d'])}")
            #print(f"Average Decrease %: {d_d_mean} (CI: {d_d_ci}) (limit {d_d_temp_mean}, CI: {d_d_temp_ci})")
            #print(f"Average DI Increase %: {d_i_mean} (CI: {d_i_ci}) (limit {d_i_temp_mean}, CI: {d_i_temp_ci})")
            #print(f"Average ND Increase %: {n_d_mean} (CI: {n_d_ci})")
            #print(f"Turnover CI: {turnover_mean:.2f} minutes (CI: {turnover_ci})")
            #print(f"Gain: {gain:.4f}%")
            #print("\n" + "="*200 + "\n")
            return d_i_temp_mean, gain, turnover_mean

class DTManager:
    def __init__(self):
        self.data_manager = DTData()

    def calculate_rsi_prices(self, ticker, period=14, target_rsis=[30, 70]):
        # Fetch data
        end_date = pd.Timestamp.now()
        start_date = end_date - pd.Timedelta(days=5)
        df = yf.download(ticker, start=start_date, end=end_date, interval="1m")
        
        # Calculate RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = rsi.iloc[-1]
        current_price = df['Close'].iloc[-1]
        
        results = {'current_rsi': current_rsi, 'current_price': current_price}
        
        for target_rsi in target_rsis:
            target_rs = (100 / (100 - target_rsi) - 1)
            
            if target_rsi > current_rsi:  # Price needs to go up
                required_gain = target_rs * loss.iloc[-1] - gain.iloc[-1]
                price_change = required_gain * period
            else:  # Price needs to go down
                required_loss = gain.iloc[-1] / target_rs - loss.iloc[-1]
                price_change = -required_loss * period
            
            target_price = current_price + price_change
            results[f'price_at_rsi_{target_rsi}'] = target_price
        
        return results
    
    def main(self, ticker, range = True):
        rsi_info = self.calculate_rsi_prices(ticker)
        
        if range == True:
            print(f"Current RSI: {rsi_info['current_rsi']:.2f}")
            print(f"Current Price: ${rsi_info['current_price']:.2f}")
            print(f"Estimated price at RSI 30: ${rsi_info['price_at_rsi_30']:.2f}")
            print(f"Estimated price at RSI 70: ${rsi_info['price_at_rsi_70']:.2f}")
            messagebox.showinfo("RSI Information", f"{rsi_info['current_rsi']:.2f}")
            rsi1= simpledialog.askstring("Input", "Range for analysis (#1): ").strip()
            rsi2= simpledialog.askstring("Input", "Range for analysis (#2): ").strip()
            rsi_range = [(int(rsi1), int(rsi2))]
            stop, gain, time = self.data_manager.limit(ticker, rsi_range)
            stop_p = 1 - stop / 100
            print(f"Stop Price: ${rsi_info['current_price']*(stop_p)}")
            print(f"Sell Price: ${rsi_info['price_at_rsi_70']:.2f}")
            return rsi_info, stop_p, gain, time
            
        else:
            c_rsi = rsi_info['current_rsi']
            if c_rsi < 65:
                rsi_range = [(int(c_rsi- 3), int(c_rsi + 5))]
                stop, gain, time= self.data_manager.limit(ticker, rsi_range)
                return rsi_info['current_rsi'], ticker, gain
            else:
                pass
        
     
    def find(self):
        with open("./storage/ticker_lists/safe_tickers.txt", "r") as stock_file:
            stock_list = stock_file.read().split('\n')
        full = []
        stock_list = random.sample(stock_list, 50)
        print(stock_list)
        for ticker in stock_list:
            print(ticker)
            try:
                rsi, ticker, gain = self.main(ticker, range = False)
                full.append((round(gain, 2), ticker, round(rsi, 0)))
            except:
                pass
        messagebox.showinfo(title = "RSI", message = sorted(full))

class DTViewer:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title("Day Trading Module")
        self.root.geometry("300x300+700+100")
        self.dt_manager = DTManager()

    def run(self):
        task = simpledialog.askstring("Input", "Find best stock (1) or Run (2)?: ").strip()
        if task == '1':
            self.dt_manager.find()
        ticker = simpledialog.askstring("Input", "Ticker: ").strip()
        rsi_info, stop_p, gain, time = self.dt_manager.main(ticker)
        self.ResultFrame(rsi_info, stop_p, gain, time)

    def ResultFrame(self, rsi_info, stop_p, gain, time):
        frame = tk.Frame(self.root) 
        frame.pack(fill=tk.X, padx=10, pady=10)  
        canvas = tk.Canvas(frame, width=250, height=275, highlightthickness = 1, highlightbackground = 'black')
        canvas.pack(side=tk.TOP)

        y_pos = 25
        canvas.create_text(125, y_pos, text="Potential Sell", font=("Arial", 16), anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Current RSI: {rsi_info['current_rsi']:.2f}", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Current Price: ${rsi_info['current_price']:.2f}", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Estimated price at RSI 30: ${rsi_info['price_at_rsi_30']:.2f}", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Estimated price at RSI 70: ${rsi_info['price_at_rsi_70']:.2f}", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Stop Price: ${rsi_info['current_price']*(stop_p):.2f}", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Sell Price: ${rsi_info['price_at_rsi_70']:.2f}", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Estimated Gain Per Day: {gain:.4f}%", anchor = "center")
        y_pos += 25
        canvas.create_text(125, y_pos, text=f"Estimated Turnover Time: {time:.0f} minutes", anchor = "center")

