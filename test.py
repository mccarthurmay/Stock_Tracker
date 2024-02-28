#huge drop, 5 days flat, will raise
#volume always peaks at lowest point - look at this data
#   -huge volume increase when dropping significantly or rising significantly
#   -levels out while decreasing until it hits rock bottom where there's another spike
import warnings

# Suppress warning
warnings.simplefilter(action='ignore', category=FutureWarning)
import pickle
import yfinance as yf
import statistics
import pandas as pd
import os
import concurrent.futures
#FUNCTIONS


######FOR OTHER CODE FROM PROJECT#######
def storeData(dbname, stock_list, percent_under, recommendation):
    try:
        with open(dbname+'.pickle', 'rb') as dbfile:
            db = pickle.load(dbfile)
    except FileNotFoundError:
        db = {}
    for ticker in stock_list:
        db[ticker] = {'ticker' : ticker, 'percent' : percent_under, 'recommendation': recommendation}

    #source, destination
    with open(dbname + '.pickle', 'wb') as dbfile:
        pickle.dump(db, dbfile)

def resetData(dbname):
    os.remove(dbname+'.pickle')


def loadData(dbname):
    #reading binary
    dbfile = open(dbname+'.pickle', 'rb')
    db = pickle.load(dbfile)
    sorted_data = sorted(db.values(), key=lambda x: x['percent'] if x['percent'] is not None else float('inf'))
    for ticker in sorted_data:
        print(ticker)
    dbfile.close()

def updateData(dbname):
    try:
        with open(dbname + '.pickle', 'rb') as dbfile:
            db = pickle.load(dbfile)
    except FileNotFoundError:
        return

    def process_ticker(ticker):
        try:
            percent_under = confidence(ticker).iloc[0]
            recommendation = recommendation_analysis(ticker)
            db[ticker] = {'ticker': ticker, 'percent': percent_under, 'recommendation': recommendation}
        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_ticker, db.keys())

    with open(dbname + '.pickle', 'wb') as dbfile:
        pickle.dump(db, dbfile)

def recommendation_analysis(ticker):
    recommendation = yf.Ticker(ticker).recommendations
    SB = recommendation['strongBuy'].iloc[0]
    B = recommendation['buy'].iloc[0]
    H = recommendation['hold'].iloc[0]
    S = recommendation['sell'].iloc[0]
    SS = recommendation['strongSell'].iloc[0]
    result = f'Strong Buy:{SB} Buy:{B} Hold:{H} Sell:{S} Strong Sell:{SS}'
    return result

def confidence(ticker):

    # closing price of input stock
    stock_data = yf.Ticker(ticker).history(period="3mo").reset_index(drop=True)
    stock_close = pd.DataFrame(stock_data['Close'])
    # confidence interval of 95% = standard deviation of data * 2
    ci = stock_close.std() * 2
    # lower bound of 95%
    lower_bound = stock_close.mean() - ci
    # grab current price
    current_close = yf.Ticker(ticker).history(period='1d', interval='1m').reset_index(drop=True)
    if not current_close.empty:
        current_price = yf.Ticker(ticker).info['currentPrice']
        # percent over the lower bound of 2 std deviations (95% confidence interval)
        percent_under = (1 - current_price / lower_bound ) * 100
        return percent_under
    else:
        print(f"No price data available for {ticker}.")
        return None

#test this
def day_movement(ticker):
    stock_data = yf.Ticker(ticker).history(period="3mo").reset_index(drop=True)
    stock_close = pd.DataFrame(stock_data['Close'])
    stock_close = stock_close.iloc[-1]
    stock_curr = yf.Ticker(ticker).info['currentPrice']
    stock_perc = (stock_close - stock_curr) / stock_close
    print(f"{float(stock_perc.values):.15f}")


def showinfo(ticker):
    stock_data = yf.Ticker(ticker)
    stock_history = stock_data.history(period = '3mo')
    print('\n',stock_data.info['longBusinessSummary'])
    stock_close = pd.DataFrame(stock_history['Close']).iloc[-2].item()
    stock_curr = yf.Ticker(ticker).info['currentPrice']
    print('\nStock Close:',stock_close,'\nCurrent Price:', stock_curr)
    print(recommendation_analysis(ticker), '\n')


def main():


#actions
    def command(action):
        if action == "help":
            print("\t'store': store tickers into database")
            print("\t'load': load tickers from database   ")
            print("\t'show ci': show data from confidence interval    ")
            print("\t'update': update stock  ")
            print("\t'pattern stocks': stocks for pattern    ")
            print("\t'dmove': daily movement   ")
            print("\t'info':  info  ")
            print("\t'':    ")
            print("\t'quit': quit   ")

#rename functions so I could combine names and have action_tly()

        if action == "store":
            input_file = input("what file you wnat: ")
            with open(input_file+'.txt', 'r') as txt:
                data_txt = txt.read()
                data_txt = data_txt.split('\n')
            dbname = input("name of database: ")
            stock_list = list(data_txt)
            percent_under = 0
            recommendation = 0
            storeData(dbname, stock_list, percent_under, recommendation)

        if action == "load":
            dbname = input("what db:")
            loadData(dbname)

        if action == "reset":
            dbname = input("what db to delete: ")
            resetData(dbname)

        if action == "info":
            ticker = input("What ticker you want: ")
            showinfo(ticker)
            recommendation_analysis(ticker)

        if action == "update":
            dbname = input("what db:")
            updateData(dbname)

        if action == "con": #for testing
            confidence("SPY")

        if action == "dmove":
            day_movement("GM")

        #if action == "":

    action = ""

    while action != 'quit':

        action = input("Do something (help for more): ")
        command(action)
main()


    #ticker.info['longBusinessSummary']
##########IDEAS FOR UPDATE#################

#only keep recommendations or equity score that are also below 95%

#have different functions ----- different choices. One for pattern stocks, one for guessing a little dip



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
#def day_movement(stock)
    #get last close
    #compare to now
    #if 5%+ drop, email
    #if 5%+ increase, email
#def minimum_price(stock)
    #get close
