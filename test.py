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

######STORAGE CODE#############
def storeData(dbname, stock_list):
    try:
        db, dbfile = open_file(dbname)
    except FileNotFoundError:
        db = {}

    for ticker in stock_list:
        db[ticker] = {'Ticker': None, 'Buy': None, '{Percent above 95% confidence': None,  'RSI': None, 'Slope': None}
    #source, destination
    close_file(db, dbname)
    updateData(dbname)


def mainPortfolio(dbname):
    try:
        db, dbfile = open_file(dbname)
    except FileNotFoundError:
        db = {}

    while True:
        ticker = input("Input ticker to be added ('done' to leave): ").strip().upper()

        if ticker == "DONE":
            break

        if ticker not in db:
            try:
                portfolio_runall(ticker, db)
            except Exception as e:
                print(f"Removing {ticker}: {e}")
                del db[ticker]
        else:
            print("Ticker already exists")

    close_file(db, dbname)


def addData(ticker, dbname):
    try:
        db, dbfile = open_file(dbname)

        if ticker not in db:
            try:
                runall(ticker, db)
            except Exception as e:
                print(f"Removing {ticker}: {e}")
                del db[ticker]
        else:
            print("Ticker already exists")

        close_file(db, dbname)

    except FileNotFoundError:
        print("File not found")


def remData(ticker, dbname):
    try:
        db, dbfile = open_file(dbname)
        del db[ticker]
        close_file(db, dbname)
        print(f"Removing {ticker}")
    except FileNotFoundError:
        print("File not found")


def resetData(dbname):
    os.remove(f'./storage/{dbname}.pickle')


def loadData(dbname):
    #reading binary
    try:
        db, dbfile = open_file(dbname)
        sorted_data = sorted(db.values(), key=lambda x: x['Percent under 95% confidence'] if x['Percent under 95% confidence'] is not None else float('inf'))
        for ticker in sorted_data:
            print(ticker)
        dbfile.close()
    except FileNotFoundError:
        print("File not found")

def updateMain(dbname):
    try:
        db, dbfile = open_file(dbname)
        print(f"{dbname} loading...")
    except FileNotFoundError:
        print("file not found")

    def process_ticker(ticker):
        try:
            portfolio_runall(ticker, db)
        except Exception as e:
            print(f"Removing {ticker}: {e}")
            del db[ticker]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_ticker, db.keys())

    close_file(db, dbname)

def updateData(dbname):
    try:
        db, dbfile = open_file(dbname)
        print(f"{dbname} loading...")
    except FileNotFoundError:
        print("file not found")
        return

    def process_ticker(ticker):
        try:
            runall(ticker, db)
        except Exception as e:
            print(f"Removing {ticker}: {e}")
            del db[ticker]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_ticker, db.keys())

    close_file(db, dbname)

def open_file(dbname):
    with open(f'./storage/{dbname}.pickle', 'rb') as dbfile:
        db = pickle.load(dbfile)
    return db, dbfile

def close_file(db, dbname):
    with open(f'./storage/{dbname}.pickle', 'wb') as dbfile:
        pickle.dump(db, dbfile)
    dbfile.close()

######FUNCTIONAL CODE################
def runall(ticker, db):
    percent_under = round(confidence(ticker, db).iloc[0])
    rsi = rsi_calc(ticker, graph = False)
    slope_value = slope(ticker)
    buy_bool = buy(rsi, percent_under, slope_value)
    db[ticker] = {'Ticker': ticker, 'Buy': buy_bool, 'Percent under 95% confidence': percent_under, 'RSI': rsi, 'Slope': slope_value}

def portfolio_runall(ticker, db):
    percent_under = round(confidence(ticker, db).iloc[0])
    rsi = rsi_calc(ticker, graph = False)
    slope_value = slope(ticker)
    sell_bool = sell(rsi)
    db[ticker] = {'Ticker': ticker, 'Sell': sell_bool, 'Percent under 95% confidence': percent_under, 'RSI': rsi, 'Slope': slope_value}

def winrate():
    db, dbfile = open_file(dbname)
    print(db['GM'])
    if ticker in db:
        if ticker.item[buy] == true:
            




def buy(rsi, percent_under, slope_value):
    if percent_under >! 0 and rsi !< 30 and slope_value > -.05:
        return True
    else:
        return False

def sell(rsi):
    if rsi >! 70:
        return True
    else:
        return False

def slope(ticker):
    df = yf.Ticker(ticker)
    df = df.history(interval='1d', period='20mo')
    dates = np.arange(len(df))
    closing_prices = df['Close'].values
    slope, _, _, _, _ = linregress(dates, closing_prices)
    return slope

    #not sure if slope works, maybe do period prior to crash so 3-20 months

def confidence(ticker, dbname):
    # closing price of input stock
    stock_data = yf.Ticker(ticker).history(period="2mo").reset_index(drop=True)

    stock_close = pd.DataFrame(stock_data['Close'])

    if int(stock_close.iloc[-1]) > 5:
        # confidence interval of 95% = standard deviation of data * 2
        ci = stock_close.std() * 2
        # lower bound of 95%
        lower_bound = stock_close.mean() - ci
        try:
            current_price = yf.Ticker(ticker).info['currentPrice']
            # percent over the lower bound of 2 std deviations (95% confidence interval)
            percent_under = (1 - current_price / lower_bound) * 100
            return percent_under
        except:
            print(f"No current price available for {ticker}.")

    else:
        try:
            del dbname[ticker]
            print(f"{ticker} is a penny stock. Removing ticker.")
        except:
            print(f"{ticker} is a penny stock. Not adding ticker.")




def con_plot(ticker):

    tick = yf.Ticker(ticker)
    df_list = tick.history(interval='1d', period='20mo')
    df = pd.DataFrame(df_list['Close'])
    ci_list = []
    ci = df.std() * 2
    upper_bound = df.mean() + ci
    lower_bound = df.mean() - ci
    mean = df.mean()
    current = yf.Ticker(ticker).info['currentPrice']
    print(f"CI:{ci.values} \nUpper Bound:{upper_bound.values} \nLower Bound:{lower_bound.values} \nMean:{mean.values} \nCurrent:{current}")
    for close in df_list['Close']:
        percent_lower = (close - lower_bound) / (upper_bound - lower_bound) * 100
        ci_list.append(percent_lower)  # Append to list
    plt.style.use('fivethirtyeight')
    #figure size
    plt.rcParams['figure.figsize'] = (15,10)

    ax1 = plt.subplot2grid((10,1), (0,0), rowspan = 4, colspan = 1)
    ax2 = plt.subplot2grid((10, 1), (5, 0), rowspan=4, colspan=1)

    ax1.plot(df['Close'], linewidth = 2)
    ax1.set_title('Close prices')

    ax2.set_title('Confidence Interval')
    ax2.plot(ci_list, color = 'orange', linewidth = 1)

    #Oversold
    ax2.axhline(30, linestyle = '--', linewidth = 1.5, color = 'green')
    ax2.axhline(70, linestyle = '--', linewidth = 1.5, color = 'red')

    plt.show()

    ###test###



def rsi_calc(ticker, graph):
    ticker = yf.Ticker(ticker)
    df = ticker.history(interval="1d", period="2y")

    change = df['Close'].diff()
    change.dropna(inplace=True)
    #create two copies of closing price
    change_up = change.copy()
    change_down = change.copy()

    change_up[change_up<0]= 0
    change_down[change_down>0]= 0
    #check if mistakes
    change.equals(change_up+change_down)
    #calculate rolling average of average up and average down
    mean_up = change_up.rolling(14).mean()
    mean_down = change_down.rolling(14).mean().abs()
    #calculate rsi
    rsi = 100 * mean_up / (mean_up + mean_down)

    #Graph
    if graph == True:
        plt.style.use('fivethirtyeight')
        #figure size
        plt.rcParams['figure.figsize'] = (15,10)

        ax1 = plt.subplot2grid((10,1), (0,0), rowspan = 4, colspan = 1)
        ax2 = plt.subplot2grid((10, 1), (5, 0), rowspan=4, colspan=1)

        ax1.plot(df['Close'], linewidth = 2)
        ax1.set_title('Close prices')

        ax2.set_title('Relative Strength Index')
        ax2.plot(rsi, color = 'orange', linewidth = 1)

        #Oversold
        ax2.axhline(30, linestyle = '--', linewidth = 1.5, color = 'green')
        #Overbought
        ax2.axhline(70, linestyle = '--', linewidth = 1.5, color = 'red')

        plt.show()
    elif graph == False:
        print(rsi)
    else:
        return (round(rsi[-1]))


#possibly add this to main filter function,(most recent rsi score indicates 'buy' or add rsi score to print in summary)

#not done
def day_movement(ticker):
    stock_data = yf.Ticker(ticker).history(period="3mo").reset_index(drop=True)
    stock_close = pd.DataFrame(stock_data['Close'])
    stock_close = stock_close.iloc[-1]
    stock_curr = yf.Ticker(ticker).info['currentPrice']
    stock_perc = (stock_close - stock_curr) / stock_close
    print(f"{float(stock_perc.values):.15f}")
        #def day_movement(stock)
            #get last close
            #compare to now
            #if 5%+ drop, email
            #if 5%+ increase, email

def showinfo(ticker):
    stock_data = yf.Ticker(ticker)
    stock_history = stock_data.history(period = '3mo')
    print('\n',stock_data.info['longBusinessSummary'])
    stock_close = pd.DataFrame(stock_history['Close']).iloc[-2].item()
    stock_curr = yf.Ticker(ticker).info['currentPrice']
    print('\nStock Close:',stock_close,'\nCurrent Price:', stock_curr)


def open_settings():
    with open(f'./storage/settings/settings.pickle', 'rb') as settingsFile:
        settings = pickle.load(settingsFile)
        print("Settings loaded.")
    return settings, settingsFile


def close_settings(settings, settingsFile):
    with open('./storage/settings/settings.pickle', 'wb') as settingsFile:
        pickle.dump(settings, settingsFile)
    settingsFile.close()


def makeSettings():
    try:
        settings, settingsFile = open_settings()

    except FileNotFoundError:
        settings = {}
        print("Settings file created.")

    for database in os.listdir('./storage/'):
        if database.endswith('.pickle'):
            database = os.path.splitext(database)[0]
            settings[database] = {'AutoUpdate': False}

    close_settings(settings, settingsFile)


def settings():

    settings, settingsFile = open_settings()

    for database, values in settings.items():
        if values.get('AutoUpdate', True) and database != "main":
            updateData(database)
        elif database == "main": # temp fix
            updateMain(database)

    close_settings(settings, settingsFile)


def adjustSettings(database, choice):
    settings, settingsFile = open_settings()


    if database in settings:
        settings[database]['AutoUpdate'] = choice
        print(f"Updated 'AutoUpdate' for '{database}' to {choice}")
    else:
        print(f"Database '{database}' not found")

    close_settings(settings, settingsFile)

def loadSettings():
    settings, settingsFile = open_settings()
    for database, values in settings.items():
        print(f"{database}: {values}")


def main():
    try:
        settings()
    except:
        makeSettings()



#actions
    def command(action):
        if action == "help":
            print("\t'store': store tickers into database")
            print("\t'update': update database")
            print("\t'update portfolio': update personal portfolio")
            print("\t'load': load tickers from database")
            print("\t'portfolio': create a personal portfolio with sell indicators")
            print("\t'add': adds specific stocks to database ")
            print("\t'remove': remove specific stocks from database")
            print("\t'reset': resets requested database")
            print("\t'rsi': shows and graphs RSI of stock")
            print("\t'con':  shows and graphs confidence of stock")
            print("\t'quit': quit")
            print("\t'debug': debug options")
            print("\t'settings': adjusts settings file")

        if action == "debug":
            print("\t'winrate': win rate of stocks, automatic")
            print("\t'pattern stocks': stocks for pattern") #no purpose yet
            print("\t'dmove': daily movement of ticker")
            print("\t'info': displays information on ticker")
            print("\t'show ci': show data from confidence interval    ")
            print("\t'makesettings': makes settings file")
#rename functions so I could combine names and have action_tly()


        if action == "settings":
            loadSettings()
            database = input("Name of database:").strip()
            choice = input("Auto update on startup (y, n):" ).lower().strip()
            if choice == 'y':
                choice = True
            elif choice == 'n':
                choice = False
            adjustSettings(database, choice)

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
            recommendation_analysis(ticker)

        if action == "update":
            dbname = input("Name of database: ")
            updateData(dbname)

        if action == "con": #for testing
            ticker = input("What ticker you want: ")
            con_plot(ticker)

        if action == "dmove":
            day_movement("GM")

        if action == "winrate":
            winrate()
        #if action == "":


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
