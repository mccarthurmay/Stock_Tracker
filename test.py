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
dt = DTData()
tick = "ANSS"
range = (40,50)
dt.limit(tick, range)
#run()





#98,314 for win rate
#hit 98,800 with win rate, made changes went down to 98100

#restart with win rate at 98072


from data.min_rsi import ab_lowManager
range = [(40,50)]
ab = ab_lowManager()

ab.limit(tick, range)