import sys
sys.path.append("C:\\Users\\Max\\Desktop\\Stock_Tracker")
from data.paper import run
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca_trade_api.rest import REST, TimeFrame
import os
from config import *
from data.day_trade import DTManager, DTCalc, DTData
import time as tm
import yfinance as yf
import concurrent.futures
import keyboard
from queue import Queue
#dt = DTData()
#tick = "ANSS"
#range = (40,50)
#dt.limit(tick, range)
#run()





#98,314 for win rate
#hit 98,800 with win rate, made changes went down to 98100

#restart with win rate at 98072


#from data.min_rsi import ab_lowManager
#range = [(40,50)]
#ab = ab_lowManager()

#ab.limit(tick, range)

import requests
import pandas as pd
from datetime import datetime, time, timedelta
import pytz

API_KEY = os.getenv("ALPHA_API_KEY_ID")
SYMBOL = 'IBM'
INTERVAL = '1min'

url = f'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={SYMBOL}&interval={INTERVAL}&outputsize=full&apikey={API_KEY}'

response = requests.get(url)
data = response.json()


time_series = data.get(f'Time Series ({INTERVAL})', {})


df_data = []
eastern_tz = pytz.timezone('US/Eastern')
market_open = time(9, 30)
market_close = time(16, 0)
trading_period= datetime.now(eastern_tz) - timedelta(days=30) 



for timestamp, values in time_series.items():
    dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    dt_eastern = eastern_tz.localize(dt)
    
    # Check if the time is within market hours and within the last 10 trading days
    if market_open <= dt_eastern.time() < market_close and dt_eastern > trading_period:
        df_data.append({
            'Datetime': dt_eastern,
            'Close': float(values['4. close']),
            'Volume': int(values['5. volume'])
        })

# Copy yFinance Dataframe
df = pd.DataFrame(df_data)

# Set Datetime as index
df.set_index('Datetime', inplace=True)
df.sort_index(ascending=True, inplace=True)

print(df)
