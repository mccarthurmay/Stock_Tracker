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


def calculate_ci(data):
    if not data or len(data) < 2:  # We need at least 2 data points to calculate CI
        return "None", "None"
    
    data = [x for x in data if x is not None]  # Remove any None values
    
    if not data or len(data) < 2:
        return "None", "None"
    
    # Convert Timedelta to days if necessary
    if isinstance(data[0], timedelta):
        data = [d.total_seconds() / (24*60*60) for d in data]  # Convert to days
    
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
    #Finds 
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
            low_price = df.iloc[i]['Close']
            
            # Look for RSI of ht
            j = i + 1
            while j < len(rsi) and (rsi[j] < ht or df.iloc[j]['Close'] < low_price):
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
        return (sum(td.total_seconds() for td in lst) / len(lst)) / 86400


    def process_ticker(self, ticker, ltr, ht):
        # Results in form of dictionary
        results = {
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
        
        # Calculate RSI, retrieve entire dataframe
        rsi, _, df = rsi_base(ticker, '2y') 

        lows_and_highs = self.find_lows_and_highs(rsi, df, ltr, ht)
        
        for low_date, low_value, high_date, high_value in lows_and_highs:
            stock_data = yf.Ticker(ticker).history(interval='1d', start=low_date, end=(high_date + timedelta(days=1)))
            stock_data = stock_data['Close']
            rsi_price = stock_data[low_date]
            lowest_price = min(stock_data)
            sell_price = stock_data[high_date]
            
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
            results['avg_turnover'].append(high_date - low_date)

        
        return results

    def limit(self):
        with open("./storage/ticker_lists/safe_tickers.txt", "r") as stock_file:
            stock_list = stock_file.read().split('\n')
        #stock_list = ['GM']
        ltr_list = [(65, 70), (60, 65), (55, 60), (50, 55), (45, 50), (40, 45), (35, 40), (30, 35), (25, 30), (20, 25), (15, 20), (10, 15), (5, 10), (0,5)] 
        #ltr_list = [(45, 47.5), (47.5, 50)]
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


            
            #print("Decrease after RSI, Decrease at the end of the RSI interval")
            #print(f"{all_results['d_d']}, {avg_d_d}, {len(all_results['d_d'])}")
            #print()
            #print("Decrease after RSI, Increase at the end of the RSI interval")
            #print(f"{all_results['d_i']}, {avg_d_i}, {len(all_results['d_i'])}")
            #print()
            #print("Only increase over whole RSI interval")
            #print(f"{all_results['n_d']}, {avg_d}, {len(all_results['n_d'])}")
            #print()
            #print(all_results['d_d_temp'])
            
            #send averages to confidence interval

           
            d_d_mean, d_d_ci = calculate_ci(d_d_value)
            d_i_mean, d_i_ci = calculate_ci(d_i_value)
            n_d_mean, n_d_ci = calculate_ci(n_d_value)
            d_i_temp_mean, d_i_temp_ci = calculate_ci(d_i_temp)
            d_d_temp_mean, d_d_temp_ci = calculate_ci(d_d_temp)
            
                # Calculate CI for turnover times
            turnover_mean, turnover_ci = calculate_ci(all_results['avg_turnover']) 
            
            gain = self.calc(d_i_mean, turnover_mean)

            

            print("Decrease vs Increase")
            print(f"{len(all_results['d_i'])} vs {len(all_results['n_d'])}")
            print(f"Average DI Increase %: {d_i_mean} (CI: {d_i_ci}) (limit {d_i_temp_mean}, CI: {d_i_temp_ci})")
            print(f"Average ND Increase %: {n_d_mean} (CI: {n_d_ci})")
            print(f"Turnover CI: {turnover_mean} days (CI: {turnover_ci})")
            print(f"{gain}%")
            print("\n" + "="*200 + "\n")

    def calc(self, d, turnover):
        expected = 1 + d/100
        events = 365/ turnover
        gain = (expected)**events
        gain = (gain-1) * 100
        return gain



"""
=======================================================
(0,5)

5 years: 


2 years: 

1 year: 

=======================================================
(5,10)

5 years: 

2 years: 

1 year: 

=======================================================
(10,15)

5 years: 

2 years: 

1 year: 

=======================================================
(15,20)

5 years: 

2 years: 

1 year: 

=======================================================
(20,25)

5 years: 

2 years:

1 year:

=======================================================
(25,30)

5 years: 

2 years: 

1 year: 

=======================================================
(30,35)

5 years: 


2 years: 

1 year: 

=======================================================
(35,40)

5 years: 

2 years: 
 
1 year:

=======================================================
(40,45)

5 years: 

2 years: 

1 year: 


=======================================================
(45,50)

5 years: 


2 years: 

1 year: 

------------------------------------------------------------------------
(45, 47.5)

5 years: 

2 years:

1 year: 


--------------------------------------------------------------------------
(47.5, 50)

5 years: 

2 years: 

1 year: 


=======================================================
(50,55)

5 years: 



2 years: 2391 vs 3238
Average Decrease %: -8.02 (CI: (-8.34, -7.69)) (limit 15.05, CI: (14.68, 15.43))
Average DI Increase %: 4.02 (CI: (3.9, 4.15)) (limit 4.1, CI: (3.97, 4.23))
Average ND Increase %: 5.26 (CI: (4.98, 5.55))
Turnover CI: 49.31 days (CI: (48.25, 50.37))
Gain: -7.8210%


1 year:

=======================================================

(55,60)

5 years: 

2 years: 2649 vs 3615
Average Decrease %: -7.46 (CI: (-7.77, -7.14)) (limit 13.85, CI: (13.47, 14.22))
Average DI Increase %: 3.8 (CI: (3.68, 3.92)) (limit 3.82, CI: (3.7, 3.94))
Average ND Increase %: 4.57 (CI: (4.33, 4.81))
Turnover CI: 44.88 days (CI: (43.85, 45.9))
Gain: -7.5588%

1 year: 


=======================================================
(60,65)

5 years: 


2 years: 3318 vs 4168
Average Decrease %: -6.14 (CI: (-6.4, -5.89)) (limit 11.24, CI: (10.9, 11.58))
Average DI Increase %: 3.34 (CI: (3.23, 3.45)) (limit 3.6, CI: (3.48, 3.72))
Average ND Increase %: 3.66 (CI: (3.47, 3.85))
Turnover CI: 37.02 days (CI: (36.09, 37.94))
Gain: -8.1797%

1 year:


=======================================================
(65,70)

5 years: 


2 years: 4753 vs 4832
Average Decrease %: -4.34 (CI: (-4.52, -4.15)) (limit 7.57, CI: (7.3, 7.83))
Average DI Increase %: 3.05 (CI: (2.93, 3.16)) (limit 3.49, CI: (3.38, 3.61))
Average ND Increase %: 2.26 (CI: (2.15, 2.37))
Turnover CI: 26.39 days (CI: (25.63, 27.14))
Gain: -8.1727%

1 year: 

=======================================================













"""