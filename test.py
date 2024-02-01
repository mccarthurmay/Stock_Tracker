#huge drop, 5 days flat, will raise
#volume always peaks at lowest point - look at this data
#   -huge volume increase when dropping significantly or rising significantly
#   -levels out while decreasing until it hits rock bottom where there's another spike
import pickle
import yfinance as yf
import statistics
import pandas as pd
#STORAGE

#use a lot of pandas
#find the best way to store information
#make a huge database of smp500 + bluechip



#yfinance,
    #i think i would only need to store % lower than 95% confidence
        #grab stock history - 2 months??
        #grab stock information
            #avg close of 2 months
            #std dev of 2 months
            #confidence interval =  (std dev * 2)
            #avg - confidence interval = lower 95% ******
            #=1-(current price)/(lower 95% price)
        #grab volume of each day


#DATABASE CREATION

#input list of stock trackers
#write onto database with columns for each thing

#FUNCTIONS

def storeData(tracker, percent_over):

    try:
        dbfile = open('data.pickle', 'rb')
        db = pickle.load(dbfile)
    #initialize data to be stored into db
    except FileNotFoundError:
        db = {}

    db[tracker] = {'tracker' : tracker, 'percent' : percent_over}

    #source, destination
    with open('data.pickle', 'wb') as dbfile:
        pickle.dump(db, dbfile)


def loadData():
    #reading binary
    dbfile = open('data.pickle', 'rb')
    db = pickle.load(dbfile)
    for tracker in db:
        print(tracker, '=>', db[tracker])
    dbfile.close()

def confidence(stock):
    #closing price of input stock
    stock_data = yf.Ticker(stock).history(period="2mo").reset_index(drop=True)
    stock_close = pd.DataFrame(stock_data['Close'])
    #confidence interval of 95% = standard deviation of data * 2
    ci = stock_close.std() * 2
    #lower bound of 95%
    lower_bound = stock_close.mean() - ci
    #grab current price
    current_close = yf.Ticker(stock).history(period = '1m').reset_index(drop=True)
    current_price = pd.DataFrame(current_close['Close'])
    #percent over the lower bound of 2 std devations (95% confidence interval)
    percent_over = 1 - current_price / lower_bound
    print(percent_under)

#input list of stocks, handmade
stock_list = ['AMD', 'AAPL', 'F']

for tracker in stock_list:
    storeData(tracker, 0)
loadData()



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
