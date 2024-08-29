import sys
sys.path.append("C:\\Users\\Max\\Desktop\\Stock_Tracker")
from data.paper import run
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca_trade_api.rest import REST, TimeFrame
import os
from config import *
from data.day_trade import DTManager, DTCalc, DTData
from data.analysis import RSIManager
import time as tm
import yfinance as yf
import concurrent.futures
import keyboard
from queue import Queue
import pandas as pd
from datetime import datetime, timedelta
dt = DTManager()
rsim = RSIManager()
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

def sector_sort():
    # List of major sector ETFs
    sector_etfs = {
        "XLK": "Technology",
        "XLF": "Financials",
        "XLV": "Healthcare",
        "XLE": "Energy",
        "XLY": "Consumer Discretionary",
        "XLP": "Consumer Staples",
        "XLI": "Industrials",
        "XLB": "Materials",
        "XLU": "Utilities",
        "XLRE": "Real Estate"
    }

    today = datetime.now().strftime('%Y-%m-%d')
    data = yf.download(list(sector_etfs.keys()), start=today, end=None, interval='1d')

    if data.empty:
        print("No data available for today. The market may not have opened yet.")
        return pd.DataFrame(columns=['Sector', 'Change'])

    # Calculate today
    changes = ((data['Close'] - data['Open']) / data['Open'] * 100).iloc[0]
    
    # Create a dataframe 
    sector_performance = pd.DataFrame({
        'Sector': changes.index,
        'Change': changes.values
    })
    # Sort sectors by change 
    sector_performance.sort_values('Change', ascending=False)

    if not sector_performance.empty:
        #print("Today's Sector Performance:")
        #print(sector_performance)
        
        #print("\nIncreasing Sectors:")
        increasing = sector_performance[sector_performance['Change'] > 0]
        #print(increasing if not increasing.empty else "No sectors are currently increasing.")
        
        #print("\nDecreasing Sectors:")
        #decreasing = sector_performance[sector_performance['Change'] < 0]
        #print(decreasing if not decreasing.empty else "No sectors are currently decreasing.")
    else:
        print("No sector data available for today.")
    sector_list = []
    for sector in increasing['Sector']:
        sector_list.append(sector)

    return sector_list
sector_list = sector_sort()
print(sector_list)