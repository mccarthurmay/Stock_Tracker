import yfinance as yf
from datetime import date, timedelta
from data.database import open_file, close_file
from data.analysis import rsi_calc, sell, rsi_base
import os
import pandas as pd

class ab_lowManager:
    def __init__(self):
        pass
    
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


    
    def limit(self):
        #stock_list = ['AAPL', 'GM', 'UNH']
        stock_file = open("./storage/ticker_lists/safe_tickers.txt", "r")
        stock_data = stock_file.read()
        stock_list = stock_data.split('\n')

        

        ltr_list = [(30, 40), (25, 30), (20, 25), (15, 20), (10, 15), (5, 10), (0, 5)]
        ht = 70
        for ltr in ltr_list:
            no_decrease = []
            decrease_increase = []
            decrease_decrease = []
            decrease_decrease_value = []
            for tickers in stock_list:

                rsi, ticker, df = rsi_base(tickers, '2y')
                lows_and_highs = self.find_lows_and_highs(rsi, df, ltr, ht)
            
                for low_date, low_value, high_date, high_value in lows_and_highs:
                    stock_data = yf.Ticker(tickers).history(interval = '1d', start = low_date, end = (high_date + timedelta(days = 1)) )
                    stock_data = stock_data['Close']
                    rsi_price = stock_data[low_date]
                    lowest_price = rsi_price

                    sell_price = stock_data[high_date]

                    for price in stock_data:
                        if price < lowest_price:
                            lowest_price = price
                    
                    p_decrease = (rsi_price - lowest_price) / rsi_price * 100
                    p_increase = (sell_price - rsi_price) /sell_price * 100

                #print(f"Ticker: {ticker}, Period: {low_date} - {high_date}, RSI: {round(low_value,2)}, Price at RSI: {round(rsi_price,2)}, Lowest Price within Period: {round(lowest_price,2)}, Percent Decrease: {round(p_decrease, 2)}, Highest Price within Period: {round(sell_price,2)}, Percent Increase: {round(p_increase, 2)}")
                    #print(f"LTR: {ltr}, Ticker: {ticker}, Percent Increase: {p_increase}, RSI: {low_value}")
                    #print(ltr)
                    if p_decrease == 0 and p_increase > 0:
                        no_decrease.append(round(low_value,2))
                    if p_decrease > 0 and p_increase > 0:
                        decrease_increase.append(round(low_value,2))
                    if p_decrease > 0 and p_increase < 0:
                        decrease_decrease.append(round(low_value,2))
                        decrease_decrease_value.append(round(p_decrease),2)
                    

            try:
                avg_dec_dec = round(self.Average(decrease_decrease),2)
            except:
                avg_dec_dec = "None"
            try:
                avg_dec_dec_val = round(self.Average(decrease_decrease_value),2)
            except:
                avg_dec_dec_val = "None"
            try:
                avg_dec_inc = round(self.Average(decrease_increase),2)
            except:
                avg_dec_inc = "None"
            try:
                avg_dec = round(self.Average(no_decrease),2)
            except:
                avg_dec = "None"
            print(ltr)
            print("Double Decrease", decrease_decrease, avg_dec_dec, len(avg_dec_dec), avg_dec_dec_val)
            print()
            print("Decrease Temp, Increase",decrease_increase, avg_dec_inc, len(avg_dec_inc))
            print()
            print("Double Increase",no_decrease, avg_dec, len(avg_dec))
            print()
            print(len(avg_dec_dec), " vs ", len(avg_dec_inc)+len(avg_dec))

    def test_rsi(self):
        pass#

        #NEED TO CHANGE HEIRARCHY, LTR NEEDS TO COME FIRST OR CHANGE HOW LISTS WORK


    #1. absolute low project 
    #    - find how much holders fluctuate 
    #    - use 10 rsi, 15 rsi, 20 rsi, and 30 rsi as buy signals
    #    - collect all necessary information at purchase date
    #        - date, volume, rsi, moving average (maybe a ratio)
    #    - gives information on how to set limits


    #ISSUES
    # - Not constantly running, so comparison of the same stock may not always occur (i will miss the point where it hits 20 rsi)


    #IDEA
    # - Test historical data

    


        #for ticker, data in stock.items():
        #    if data['RSI'] <= 10 and ticker not in db_10:
        #        self.set_param(data, db_10, ticker, '10')
        #        print(ticker, '10')

        #    if data['RSI'] > 10 and data['RSI'] <=15 and ticker not in db_15:
        #        self.set_param(data, db_15, ticker, '15')
        #        print(ticker, '15')

        #   if data['RSI'] > 15 and data['RSI'] <=20 and ticker not in db_20:
        #        self.set_param(data, db_20, ticker, '20')
        #        print(ticker, '20')

        #    if data['RSI'] > 20 and data['RSI'] <=25 and ticker not in db_25: 
        #        self.set_param(data, db_25, ticker, '25')
        #        print(ticker), '25'
        #    if data['RSI'] > 25 and data['RSI'] <=30 and ticker not in db_30:
        #        self.set_param(data, db_30, ticker, '30')
        #        print(ticker, '30')

        #    if data['RSI'] > 30 and data['RSI'] <=40 and ticker not in db_40:
        #        self.set_param(data, db_40, ticker, '40')
        #        print(ticker, '40')