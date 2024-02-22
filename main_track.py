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
#FUNCTIONS


######FOR OTHER CODE FROM PROJECT#######
def storeData(dbname, stock_list, percent_under):
    try:
        with open(dbname+'.pickle', 'rb') as dbfile:
            db = pickle.load(dbfile)
    except FileNotFoundError:
        db = {}
    for tracker in stock_list:
        db[tracker] = {'tracker' : tracker, 'percent' : percent_under}

    #source, destination
    with open(dbname + '.pickle', 'wb') as dbfile:
        pickle.dump(db, dbfile)

def resetData(dbname):
    os.remove(dbname+'.pickle')


def loadData(dbname):
    #reading binary
    dbfile = open(dbname+'.pickle', 'rb')
    db = pickle.load(dbfile)
    sorted_data = sorted(db.values(), key=lambda x: x['percent'])
    for tracker in sorted_data:
        print(tracker)
    dbfile.close()

def updateData(dbname):
    dbfile = open(dbname+'.pickle', 'rb')
    db = pickle.load(dbfile)

    for tracker in db:
        try:
            percent_under = confidence(tracker).iloc[0]
        except:
            pass
        db[tracker] = {'tracker' : tracker, 'percent' : percent_under}

    with open(dbname + '.pickle', 'wb') as dbfile:
        pickle.dump(db, dbfile)

def confidence(tracker):

    # closing price of input stock
    stock_data = yf.Ticker(tracker).history(period="3mo").reset_index(drop=True)
    stock_close = pd.DataFrame(stock_data['Close'])
    # confidence interval of 95% = standard deviation of data * 2
    ci = stock_close.std() * 2
    # lower bound of 95%
    lower_bound = stock_close.mean() - ci
    # grab current price
    current_close = yf.Ticker(tracker).history(period='1d', interval='1m').reset_index(drop=True)
    if not current_close.empty:
        current_price = current_close['Close'].iloc[-1]
        # percent over the lower bound of 2 std deviations (95% confidence interval)
        percent_under = (1 - current_price / lower_bound ) * 100
        return percent_under
    else:
        print(f"No price data available for {tracker}.")
        return None




def main():


#actions
    def command(action):
        if action == "help":
            print("\t'store': store trackers into database")
            print("\t'load': load trackers from database   ")
            print("\t'show ci': show data from confidence interval    ")
            print("\t'update': update stock  ")
            print("\t'pattern stocks': stocks for pattern    ")
            print("\t'':    ")
            print("\t'':    ")
            print("\t'':    ")
            print("\t'quit': quit   ")

        if action == "store":
            input_file = input("what file you wnat: ")
            with open(input_file+'.txt', 'r') as txt:
                data_txt = txt.read()
                data_txt = data_txt.split('\n')
            dbname = input("name of database: ")
            stock_list = list(data_txt)
            percent_under = 0
            storeData(dbname, stock_list, percent_under)

        if action == "load":
            dbname = input("what db:")
            loadData(dbname)

        if action == "reset":
            dbname = input("what db to delete: ")
            resetData(dbname)

        if action == "update":
            dbname = input("what db:")
            updateData(dbname)

        if action == "con": #for testing
            confidence("GM")

        #if action == "":

    action = ""

    while action != 'quit':

        action = input("Do something (help for more): ")
        command(action)
main()

##########IDEAS FOR UPDATE#################

#update at once to speed up process

#only keep recommendations or equity score that are also below 95%

#have different functions ----- different choices. One for pattern stocks, one for guessing a little dip



####FOR STOCKS WITH PATTERNS#####
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
