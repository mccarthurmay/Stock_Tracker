import sys
sys.path.append("C:\\Users\\Max\\Desktop\\Stock_Tracker")
from data.paper import run
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca_trade_api.rest import REST, TimeFrame
from data.min_rsi import ab_lowManager as ab_lowM
from data.rsi_analysis import ab_lowManager as ab_low
import os
from config import *
from data.day_trade import DTManager
import time as tm
import yfinance as yf
import concurrent.futures
import keyboard
from queue import Queue
dt = DTManager()
ab_min = ab_lowM()
ab = ab_low()

run()
#ab_min.limit("GM")  #Runs min_rsi analysis
#ab.limit() #Runs rsi_analysis analysis




#98,314 for win rate
#hit 98,800 with win rate, made changes went down to 98100

#restart with win rate at 98072


#restart 97276, -335 for td