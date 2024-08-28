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
from datetime import datetime, timedelta
from queue import Queue
dt = DTManager()
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
#df_temp = df["Datetime"] < datetime.today and df["Datetime"] > range
#print(df_temp)

ticker = "^GSPC"
smp = yf.Ticker(ticker)
end_time = datetime.now()
start_time = end_time - timedelta(hours=1)
data = smp.history(start=start_time, end=end_time, interval="1m")
close = data["Close"]

#A better one would be a simple moving average - take form analysis. if moving average is positive in smp,
# follow smp. If not, use stocks that contrast

# big movers cause drop... maybe separate by sector. one sector may increase as another decrease

if close.iloc[-1] > close.iloc[0]:
    print ("increase")
else:
    print("dc")
    print(close.iloc[-1], close.iloc[0])

    #