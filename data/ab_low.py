import yfinance as yf
from datetime import date, timedelta
from data.database import open_file, close_file
from data.analysis import rsi_calc, sell, rsi_base
import os
import pandas as pd
import concurrent.futures
from functools import partial
from datetime import timedelta
class ab_lowManager:
    def __init__(self):
        pass
    
    #Finds 
    def find_lows_and_highs(self, rsi, df, ltr=(20, 30), ht=70):
        results = []
        i = 0
        while i < len(rsi):
            # Find the next local minimum within the ltr
            while i < len(rsi) - 1 and (rsi[i] >= rsi[i+1] or (rsi[i] < ltr[0] and rsi[i] >= ltr[1])):
                i += 1
            if i == len(rsi) - 1:
                break  # We've reached the end of the series
            
            low_value = rsi[i]
            low_date = df.index[i]
            
            # Only proceed if the low value is within the ltr
            if ltr[0] <= low_value < ltr[1]:
                # Look for RSI of ht without going lower than the minimum
                j = i + 1
                while j < len(rsi) and rsi[j] < ht:
                    if rsi[j] < low_value:
                        # We found a lower value, so this isn't the minimum we're looking for
                        break
                    j += 1
                
                if j < len(rsi) and rsi[j] >= ht:
                    # We found a rise to ht without a new low
                    high_date = df.index[j]
                    results.append((low_date, low_value, high_date, rsi[j]))
            else:
                j = i  # If we didn't process this point, set j = i so we can increment correctly

            i = j + 1  # Move past this high point or the current point if we didn't process it

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
        rsi, _, df = rsi_base(ticker, '6mo') 

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

        #ltr_list = [(65, 70), (60, 65), (55, 60), (50, 55), (45, 50), (40, 45), (35, 40), (30, 35), (25, 30), (20, 25), (15, 20), (10, 15), (5, 10), (0,5)] 
        ltr_list = [(45, 47.5), (47.5, 50)]
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
            avg_d_d = round(self.Average(all_results['d_d']), 2) if all_results['d_d'] else "None"
            avg_d_d_val = round(self.Average(all_results['d_d_value']), 2) if all_results['d_d_value'] else "None"
            avg_d_i = round(self.Average(all_results['d_i']), 2) if all_results['d_i'] else "None"
            avg_d_i_val = round(self.Average(all_results['d_i_value']), 2) if all_results['d_i_value'] else "None"
            avg_d = round(self.Average(all_results['n_d']), 2) if all_results['n_d'] else "None"
            avg_d_val = round(self.Average(all_results['n_d_value']), 2) if all_results['n_d_value'] else "None"
            avg_turnover = round(self.Average_Time(all_results['avg_turnover'])) if all_results['avg_turnover'] else "None"
            avg_d_i_d = round(self.Average(all_results['d_i_temp']), 2) if all_results['d_i_temp'] else "None"
            avg_d_d_d = round(self.Average(all_results['d_d_temp']), 2) if all_results['d_d_temp'] else "None"
            
            #print("Decrease after RSI, Decrease at the end of the RSI interval")
            #print(f"{all_results['d_d']}, {avg_d_d}, {len(all_results['d_d'])}")
            #print()
            print("Decrease after RSI, Increase at the end of the RSI interval")
            #print(f"{all_results['d_i']}, {avg_d_i}, {len(all_results['d_i'])}")
            #print()
            #print("Only increase over whole RSI interval")
            #print(f"{all_results['n_d']}, {avg_d}, {len(all_results['n_d'])}")
            #print()
            print(all_results['d_d_temp'])
            print("Decrease vs Increase")
            print(f"{len(all_results['d_d'])} vs {len(all_results['d_i']) + len(all_results['n_d'])}")
            print(f"Average Decrease %: {avg_d_d_val} (limit {avg_d_d_d}), Average DI Increase %: {avg_d_i_val} (limit {avg_d_i_d}), Average ND Increase %: {avg_d_val}, Average RSI Turnover: {avg_turnover}")
            print("\n" + "="*200 + "\n")



#Results

"""
=======================================================
(0,5)

5 years: 


2 years: 


1 year: 12 vs 14
Average Decrease %: -8.83 (limit 16.58), Average DI Increase %: 5.38 (limit 3.91), Average ND Increase %: 26.25, Average RSI Turnover: 50
-22.3%
=======================================================
(5,10)

5 years: 

2 years: 
1 year: 61 vs 122
Average Decrease %: -8.69 (limit 17.17), Average DI Increase %: 5.28 (limit 4.0), Average ND Increase %: 8.41, Average RSI Turnover: 48
-6.3%
=======================================================
(10,15)

5 years: 

2 years: 
1 year: 110 vs 309
Average Decrease %: -5.96 (limit 13.08), Average DI Increase %: 5.57 (limit 3.4), Average ND Increase %: 8.5, Average RSI Turnover: 46
6%
=======================================================
(15,20)

5 years: 

2 years: 

1 year: 137 vs 557
Average Decrease %: -4.65 (limit 11.04), Average DI Increase %: 5.47 (limit 3.01), Average ND Increase %: 8.92, Average RSI Turnover: 40
14.5%
=======================================================
(20,25)

5 years: 

2 years: 

1 year: 89 vs 849
Average Decrease %: -3.64 (limit 9.36), Average DI Increase %: 5.56 (limit 2.73), Average ND Increase %: 7.98, Average RSI Turnover: 32
29.8%

=======================================================
(25,30)

5 years: 

2 years: 
1 year: 47 vs 1142
Average Decrease %: -2.82 (limit 7.62), Average DI Increase %: 5.66 (limit 2.22), Average ND Increase %: 7.8, Average RSI Turnover: 26
44.5%
=======================================================
(30,35)

5 years: 


2 years: 

1 year: 33 vs 1237
Average Decrease %: -0.94 (limit 5.72), Average DI Increase %: 5.65 (limit 1.8), Average ND Increase %: 7.49, Average RSI Turnover: 22
37.6%
=======================================================
(35,40)

5 years: 

2 years: 
 
16 vs 1404
Average Decrease %: -0.88 (limit 2.0), Average DI Increase %: 5.05 (limit 1.44), Average ND Increase %: 6.61, Average RSI Turnover: 17
69.6%
=======================================================
(40,45)

5 years: 

2 years: 

1 year: 54 vs 1462
Average Decrease %: -0.94 (limit 1.5), Average DI Increase %: 4.64 (limit 1.25), Average ND Increase %: 6.1, Average RSI Turnover: 13
85.1%
=======================================================
(45,50)

5 years: 


2 years: 

1 year: 74 vs 1563
Average Decrease %: -0.71 (limit 1.46), Average DI Increase %: 4.16 (limit 1.08), Average ND Increase %: 4.96, Average RSI Turnover: 10 
103.4%
------------------------------------------------------------------------
(45, 47.5)

5 years: 223 vs 5261
Average Decrease %: -0.99 (limit 1.8), Average DI Increase %: 5.28 (limit 1.54), Average ND Increase %: 6.66, Average RSI Turnover: 12
112.4%

2 years: 90 vs 1855
Average Decrease %: -0.88 (limit 1.53), Average DI Increase %: 4.79 (limit 1.33), Average ND Increase %: 5.66, Average RSI Turnover: 12
102.3%

1 year: 46 vs 968
Average Decrease %: -0.77 (limit 1.71), Average DI Increase %: 3.77 (limit 1.11), Average ND Increase %: 4.65, Average RSI Turnover: 9
104.5%

6 month: 31 vs 400
Average Decrease %: -0.65 (limit 1.49), Average DI Increase %: 4.59 (limit 1.12), Average ND Increase %: 4.9, Average RSI Turnover: 11
98.8%
--------------------------------------------------------------------------
(47.5, 50)

5 years: 295 vs 5358
Average Decrease %: -1.1 (limit 2.08), Average DI Increase %: 4.73 (limit 1.34), Average ND Increase %: 5.95, Average RSI Turnover: 10
121.6%

2 years: 97 vs 1967
Average Decrease %: -1.0 (limit 1.94), Average DI Increase %: 4.36 (limit 1.16), Average ND Increase %: 5.27, Average RSI Turnover: 10
109.6%

1 year: 51 vs 925
Average Decrease %: -0.69 (limit 1.24), Average DI Increase %: 4.3 (limit 1.12), Average ND Increase %: 5.09, Average RSI Turnover: 11
93.7%

6 month: 17 vs 432
Average Decrease %: -0.82 (limit 1.5), Average DI Increase %: 3.62 (limit 1.18), Average ND Increase %: 4.41, Average RSI Turnover: 10
86.5%
=======================================================
(50,55)

5 years: 



2 years: 


1 year: 165 vs 1621
Average Decrease %: -0.94 (limit 1.33), Average DI Increase %: 3.22 (limit 0.95), Average ND Increase %: 4.24, Average RSI Turnover: 8
88.4%
=======================================================

(55,60)

5 years: 

2 years: 

1 year: 365 vs 1587
Average Decrease %: -0.82 (limit 1.16), Average DI Increase %: 2.26 (limit 0.88), Average ND Increase %: 3.44, Average RSI Turnover: 5
75.8%
=======================================================
(60,65)

5 years: 


2 years: 

1 year: 640 vs 1882
Average Decrease %: -0.81 (limit 1.01), Average DI Increase %: 1.39 (limit 0.85), Average ND Increase %: 2.39, Average RSI Turnover: 3
47.7%
=======================================================
(65,70)

5 years: 


2 years: 

1 year: 1109 vs 2051
Average Decrease %: -0.89 (limit 0.96), Average DI Increase %: 0.99 (limit 0.68), Average ND Increase %: 1.69, Average RSI Turnover: 2
-2.4%
=======================================================













"""