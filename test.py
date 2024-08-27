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
try:
    api = REST(
    key_id=os.getenv("APCA_API_KEY_ID"),
    secret_key=os.getenv("APCA_API_SECRET_KEY"),
    base_url="https://paper-api.alpaca.markets"
    )
    account = api.get_account()
except:
    print("API Environment not set up. Please refer to 'config.py' or 'README'.")



def process_entry(entry):
    #Set parameters
    ticker = entry[1]
    rsi, current_price, stop_l, gain, time, stop, limit, wl = dt.main(ticker)
    equity = float(account.equity)
    quantity = round((float(equity)/10) / current_price, 0) - 1
    print(quantity)
    stp = round(stop,2)
    #stp = round((current_price * 1.002), 2)
    lmt = round(limit,2)
    stp_l = round(stop_l,2) #trading based on statistics
    #stp_l = round((current_price * .99),2) #trading based on win rate
    print(current_price)
    print((stp_l - current_price) / current_price, "stpl")
    #Buy order
    buy_order = api.submit_order(   # buy
        symbol = ticker,
        qty = quantity,
        side = 'buy',
        type = 'market',
        time_in_force = 'gtc',
  #WAS CAUSING PROBLEMS PREVIOUSLY
        ) 
    stop_loss_order = api.submit_order(
        symbol=ticker,
        qty= quantity,
        side='sell',
        type='stop',
        time_in_force='gtc',
        stop_price= stp_l
        )
    
    sell_order = api.submit_order(
        symbol=ticker,
        qty = quantity,
        side = 'sell',
        type = 'limit',
        limit_price = stp,
        time_in_force = 'gtc'
    )

process_entry("GM")