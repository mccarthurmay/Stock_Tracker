from data.day_trade import DTManager, DTCalc
import time as tm
import yfinance as yf
import concurrent.futures
from data.analysis import RSIManager
import keyboard
from queue import Queue
import pandas as pd
import requests
dt = DTManager()
dtc = DTCalc()
rsim = RSIManager()

import pandas as pd

def calculate_rsi(prices, period=14):
    delta = prices.diff()  
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()  
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()  

    rs = gain / loss 
    rsi = 100 - (100 / (1 + rs))  
    return rsi

def run_download():
    # Download the data
    df = dtc.tiingo("NVDA")
    print(len(df))
    # Check if df is None or empty
    if df is None or df.empty:
        print("Error: Data download failed or returned an empty DataFrame.")
        return
    
    # Reset the index to move 'Datetime' into a column
    df = df.reset_index()
    df.rename(columns={'Datetime': 'Date'}, inplace=True)  # Rename 'Datetime' to 'Date'
    
    # Calculate RSI directly in this function
    df['RSI'] = calculate_rsi(df['Close'])

    # Save the DataFrame to a CSV file
    df.to_csv('data3.csv', index=False)
    print(df)
    print(len(df))