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
            turnover_mean, turnover_ci = calculate_ci(all_results['avg_turnover']) if all_results['avg_turnover'] else None
            




            print("Decrease vs Increase")
            print(f"{len(all_results['d_d'])} vs {len(all_results['d_i']) + len(all_results['n_d'])}")
            print(f"Average Decrease %: {d_d_mean} (CI: {d_d_ci}) (limit {d_d_temp_mean}, CI: {d_d_temp_ci})")
            print(f"Average DI Increase %: {d_i_mean} (CI: {d_i_ci}) (limit {d_i_temp_mean}, CI: {d_i_temp_ci})")
            print(f"Average ND Increase %: {n_d_mean} (CI: {n_d_ci})")
            print(f"Turnover CI: {turnover_mean:.2f} days (CI: {turnover_ci})")
            gain = self.calc(len(all_results['d_d']), (len(all_results['d_i']) + len(all_results['n_d'])), d_d_mean, d_i_mean , turnover_mean)
            print(f"Gain: {gain:.4f}%")
            print("\n" + "="*200 + "\n")

    def calc(self, lenloss, lengain, d, i, turnover):
        p_loss = lenloss / (lenloss + lengain)
        p_gain = lengain / (lenloss + lengain)
        expected = p_gain * (i/100) + p_loss * (d/100)
        events = 365/ turnover
        value = (1+expected)**events
        gain = (value - 1) /1 * 100
        return gain

"""
=======================================================
(0,5)

5 years: 


2 years: 23 vs 34
Average Decrease %: -11.64 (CI: (-15.39, -7.88)) (limit 19.84, CI: (14.98, 24.7))
Average DI Increase %: 4.68 (CI: (3.38, 5.98)) (limit 5.32, CI: (4.21, 6.43))
Average ND Increase %: None (CI: None)
Turnover CI: 53.53 days (CI: (44.55, 62.5))
Gain: -12.2928%


1 year: 

=======================================================
(5,10)

5 years: 

2 years: 164 vs 186
Average Decrease %: -9.8 (CI: (-11.25, -8.34)) (limit 18.5, CI: (16.88, 20.12))
Average DI Increase %: 5.51 (CI: (4.95, 6.08)) (limit 4.59, CI: (4.09, 5.1))
Average ND Increase %: 7.92 (CI: (6.1, 9.75))
Turnover CI: 55.91 days (CI: (52.1, 59.72))
Gain: -10.3749%

1 year: 

=======================================================
(10,15)

5 years: 

2 years: 414 vs 556
Average Decrease %: -8.37 (CI: (-9.19, -7.55)) (limit 16.31, CI: (15.44, 17.18))
Average DI Increase %: 5.75 (CI: (5.36, 6.13)) (limit 4.22, CI: (3.91, 4.53))
Average ND Increase %: 8.66 (CI: (6.5, 10.81))
Turnover CI: 54.70 days (CI: (52.27, 57.14))
Gain: -1.8304%

1 year: 

=======================================================
(15,20)

5 years: 

2 years: 767 vs 1068
Average Decrease %: -8.37 (CI: (-8.97, -7.77)) (limit 16.23, CI: (15.56, 16.89))
Average DI Increase %: 5.23 (CI: (4.99, 5.47)) (limit 4.31, CI: (4.08, 4.53))
Average ND Increase %: 8.63 (CI: (7.62, 9.63))
Turnover CI: 54.04 days (CI: (52.31, 55.76))
Gain: -3.0305%

1 year: 

=======================================================
(20,25)

5 years: 

2 years: 1110 vs 1498
Average Decrease %: -7.81 (CI: (-8.28, -7.33)) (limit 15.45, CI: (14.92, 15.99))
Average DI Increase %: 5.22 (CI: (5.01, 5.43)) (limit 4.28, CI: (4.1, 4.46))
Average ND Increase %: 8.3 (CI: (7.63, 8.97))
Turnover CI: 53.24 days (CI: (51.81, 54.67))
Gain: -2.2120%

1 year:

=======================================================
(25,30)

5 years: 

2 years: 1411 vs 1984
Average Decrease %: -8.11 (CI: (-8.55, -7.68)) (limit 15.64, CI: (15.17, 16.12))
Average DI Increase %: 5.29 (CI: (5.1, 5.48)) (limit 4.2, CI: (4.03, 4.37))
Average ND Increase %: 7.74 (CI: (7.28, 8.21))
Turnover CI: 52.67 days (CI: (51.41, 53.94))
Gain: -1.9188%

1 year: 

=======================================================
(30,35)

5 years: 


2 years: 1667 vs 2262
Average Decrease %: -8.14 (CI: (-8.54, -7.75)) (limit 15.72, CI: (15.29, 16.15))
Average DI Increase %: 4.89 (CI: (4.72, 5.06)) (limit 4.15, CI: (4.0, 4.29))
Average ND Increase %: 8.76 (CI: (8.13, 9.39))
Turnover CI: 53.22 days (CI: (52.02, 54.41))
Gain: -4.2972%

1 year: 

=======================================================
(35,40)

5 years: 

2 years: 1932 vs 2459
Average Decrease %: -8.03 (CI: (-8.39, -7.68)) (limit 15.47, CI: (15.08, 15.86))
Average DI Increase %: 4.69 (CI: (4.54, 4.85)) (limit 4.18, CI: (4.03, 4.33))
Average ND Increase %: 7.65 (CI: (7.15, 8.14))
Turnover CI: 53.55 days (CI: (52.41, 54.69))
Gain: -6.0194%
 
1 year:

=======================================================
(40,45)

5 years: 

2 years: 2118 vs 2661
Average Decrease %: -8.0 (CI: (-8.33, -7.67)) (limit 15.43, CI: (15.06, 15.8))
Average DI Increase %: 4.48 (CI: (4.33, 4.62)) (limit 4.18, CI: (4.03, 4.32))
Average ND Increase %: 6.77 (CI: (6.37, 7.17))
Turnover CI: 52.65 days (CI: (51.55, 53.75))
Gain: -7.0629%

1 year: 


=======================================================
(45,50)

5 years: 


2 years: 2216 vs 2982
Average Decrease %: -8.14 (CI: (-8.47, -7.81)) (limit 15.49, CI: (15.11, 15.87))
Average DI Increase %: 4.34 (CI: (4.21, 4.48)) (limit 4.01, CI: (3.88, 4.14))
Average ND Increase %: 6.01 (CI: (5.67, 6.34))
Turnover CI: 50.95 days (CI: (49.87, 52.03))
Gain: -6.8151%

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