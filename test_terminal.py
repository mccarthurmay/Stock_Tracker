#huge drop, 5 days flat, will raise
#volume always peaks at lowest point - look at this data
#   -huge volume increase when dropping significantly or rising significantly
#   -levels out while decreasing until it hits rock bottom where there's another spike
import warnings

# Suppress warning
warnings.simplefilter(action='ignore', category=FutureWarning)
import pickle
import yfinance as yf
from yfinance import shared
import statistics
import pandas as pd
import os
import concurrent.futures
import matplotlib.pyplot as plt
from datetime import datetime
from scipy.stats import linregress
import numpy as np
from datetime import date

from data.database import ( #make this into a class
    storeData,
    mainPortfolio,
    close_file,
    addData,
    remData,
    resetData,
    loadData,
    updateMain,
    updateData,
    open_file,
    close_file
)
from data.analysis import ( #make this into a class
    runall,
    runall_sell,
    buy,
    sell,
    slope,
    confidence,
    con_plot,
    rsi_calc,
    day_movement,
    showinfo
)

from settings.settings_manager import SettingsManager
from data.winrate import WinrateManager


def display_help():
    print("Available commands:")
    print("\t'store': store tickers into database")
    print("\t'load': load tickers from database")
    print("\t'portfolio': create/edit a personal portfolio with sell indicators")
    print("\t'add': adds specific stocks to database ")
    print("\t'remove': remove specific stocks from database")
    print("\t'reset': resets requested database")
    print("\t'rsi': shows and graphs RSI of stock")
    print("\t'con': shows and graphs confidence of stock")
    print("\t'debug': debug options")
    print("\t'settings': adjusts settings file")
    print("\t'quit': quit")


def display_debug_options():
    print("Debug options:")
    print("\t'winrate': show simulated 'Holding' and 'Sold' stocks, automated")
    print("\t'update': update database")
    print("\t'update portfolio': update personal portfolio")
    print("\t'pattern stocks': stocks for pattern")  # No purpose yet
    print("\t'dmove': daily movement of ticker")
    print("\t'info': displays information on ticker")
    print("\t'show ci': show data from confidence interval")
    print("\t'makesettings': makes settings file")


def command(action):
    settings_manager = SettingsManager()
    winrate_manager = WinrateManager()

    if action == "help":
        display_help()

    elif action == "debug":
        display_debug_options()

    if action == "settings":
        settings_manager.loadSettings()
        database = input("Name of database:").strip()
        choice = input("Auto update on startup (y, n):" ).lower().strip()
        if choice == 'y':
            choice = True
        elif choice == 'n':
            choice = False
        settings_manager.adjustSettings(database, choice)

    if action == "add":
        dbname = input("Name of database: ")
        ticker = input("Ticker: ").upper()
        addData(ticker, dbname)

    if action == "remove":
        dbname = input("Name of database: ")
        ticker = input("Ticker: ").upper()
        remData(ticker, dbname)

    if action == "store":
        input_file = input("File containing tickers: ")
        with open(f'./storage/ticker_lists/{input_file}.txt', 'r') as txt:
            data_txt = txt.read()
            data_txt = data_txt.split('\n')
        dbname = input("Name of database: ")
        stock_list = list(data_txt)
        storeData(dbname, stock_list)

    if action == "load":
        dbname = input("Name of database: ")
        loadData(dbname)

    if action == "rsi":
        ticker = input("What ticker: ")
        graph = input("Do you want a graph? (y/n) ").lower()

        if graph == "y":
            graph = True
        else:
            graph = False
        rsi_calc(ticker, graph)
        print(rsi_calc(ticker, graph = False))

    if action == "portfolio":
        dbname = input("Name of database: ")
        mainPortfolio(dbname)

    if action == "update portfolio":
        dbname = input("Name of database: ")
        updateMain(dbname)

    if action == "reset":
        dbname = input("Name of database: ")
        resetData(dbname)

    if action == "info":
        ticker = input("What ticker you want: ")
        showinfo(ticker)

    if action == "update":
        dbname = input("Name of database: ")
        updateData(dbname)

    if action == "con": #for testing
        ticker = input("What ticker you want: ")
        con_plot(ticker)

    if action == "dmove":
        day_movement("GM")

    if action == "winrate":
        winrate_manager.winrate()
        winrate_manager.checkwinrate()
        db, dbfile = open_file('winrate')
        print("Sold")
        for ticker, price in db.items():
            print(ticker, price)

        db, dbfile = open_file('winrate_storage')
        print("Holding")
        for ticker, price in db.items():
            print(ticker, price)
    #if action == "":



def main():

    settings_manager = SettingsManager()
    winrate_manager = WinrateManager()

    settings_manager.checkSettings()
    winrate_manager.winrate()
    winrate_manager.checkwinrate()

    #temporary
    db, dbfile = open_file('winrate')
    print("\n\nSold\n")
    for ticker, price in db.items():
        print(ticker, price)

    db, dbfile = open_file('winrate_storage')
    print("\n\nHolding\n")
    for ticker, price in db.items():
        print(ticker, price)


    while True:
        action = input("Do something (help for more): ").strip().lower()
        if action == "quit":
            break
        else:
            command(action)
main()


    #ticker.info['longBusinessSummary']
##########IDEAS FOR UPDATE#################

#only keep recommendations or equity score that are also below 95%

#have different functions ----- different choices. One for pattern stocks, one for guessing a little dip


#def plot_confidence(ticker):
    #plot confidence against close prices to see if it is accurately working


#machine learning?? how often does confidence relate to a certain stock
    #compare against plot_confidence
    #compare rsi scores
    #put them together

#try something






####FOR STOCKS WITH PATTERNS#####
#def remtick(ticker)
    #find ticker, remove line associated with ticker in pickle
#def sell_stocks(portfolio)
    #email sell
#def gm_low(stock)
    #email me
#def current_movemement(stock) #for increase
    #store the open data at market open
    #compare to current data, if % change is greater than 2%
    #send email to me
#def minimum_price(stock)
    #get close






#DEPRECIATED CODE

#def recommendation_analysis(ticker):
    #recommendation = yf.Ticker(ticker).recommendations
    #SB = recommendation['strongBuy'].iloc[0]
    #B = recommendation['buy'].iloc[0]
    #H = recommendation['hold'].iloc[0]
    #S = recommendation['sell'].iloc[0]
    #SS = recommendation['strongSell'].iloc[0]
    #result = f'Strong Buy:{SB} Buy:{B} Hold:{H} Sell:{S} Strong Sell:{SS}'
    #return result
