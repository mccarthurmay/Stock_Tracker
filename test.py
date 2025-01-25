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
from datetime import datetime, timedelta
from queue import Queue
import pandas as pd
from datetime import datetime, timedelta
from r_analysis.data_download import run_download

dt = DTManager()
rsim = RSIManager()
dtc = DTCalc()

#run_download()

#tick = "ANSS"
#range = (40,50)
#dt.limit(tick, range)
############################run()
#print("running")
#print(rsim.macd("GM"))
#print("what")
#run_download()


#98,314 for win rate
#hit 98,800 with win rate, made changes went down to 98100

#restart with win rate at 98072


from data.min_rsi import ab_lowManager
range = [(40,50)]
ab = ab_lowManager()
#tick = ["AAPL", "GM", "AAA", "VZ", "IBM"]
from random import sample
#with open("./storage/ticker_lists/safe_tickers.txt", "r") as stock_file:
#    stock_list = stock_file.read().split('\n')
#stock_list = sample(stock_list,50)
#ab.limit(stock_list)




#def check_volume(ticker):
    # find confidence interval of volume of stock , probably 80%
        # download freq 20 and some data to find interval
        # download current volume data with yfinance and if statement it
#    df = dtc.tiingo(ticker, frequency = "20min", start_date = "2024-08-20")
#    print(df)
#    volume = df['Volume'].tolist()
#    print(volume[-1])
#    mean, cf_range = dtc.calculate_ci(volume, confidence_level = 0.80)

#    ticker = yf.Ticker(ticker)
#    intraday_data = ticker.history(interval='1m', period='1d')
#    print(intraday_data['Volume'])
#    print(mean, cf_range, current_volume)

#check_volume("AAPL")
    # if volume is over interval, send signal (add later to conditions; if volume is high use a trailing sell; ride the wave)


# TEST HOW MUCH CONFIDENCE INTERVAL OF DATA INCREASES OR DECREASES WITH TIME (in main paper.py for those calculations)