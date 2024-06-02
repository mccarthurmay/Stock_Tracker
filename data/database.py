import os
import pickle
import concurrent.futures
from data.analysis import runall, runall_sell


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


#CREATE/EDIT MAIN PORTFOLIO
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
            runall_sell(ticker, db)
        else:
            print("Ticker already exists")

    close_file(db, dbname)


#ADD TICKER
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


#REMOVE TICKER
def remData(ticker, dbname):
    try:
        db, dbfile = open_file(dbname)
        del db[ticker]
        close_file(db, dbname)
        print(f"Removing {ticker}")
    except FileNotFoundError:
        print("File not found")


#DELETE DATABASE
def resetData(dbname):
    os.remove(f'./storage/databases/{dbname}.pickle')


#DISPLAY DATABASE
def loadData(dbname):
    try:
        db, dbfile = open_file(dbname)
        sorted_data = sorted(db.values(), key=lambda x: x['Percent under 95% confidence'] if x['Percent under 95% confidence'] is not None else float('inf'))
        for ticker in sorted_data:
            print(ticker)
        dbfile.close()
    except FileNotFoundError:
        print("File not found")


#UPDATE PORTFOLIO
def updateMain(dbname):
    try:
        db, dbfile = open_file(dbname)
        print(f"{dbname} loading...")
    except FileNotFoundError:
        print("Portfolio not found")

    def process_ticker(ticker):
        try:
            runall_sell(ticker, db)
        except Exception as e:
            print(f"There has been an error with {ticker}: {e}")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_ticker, db.keys())

    close_file(db, dbname)


#UPDATE DATABASES
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


#OPEN/CLOSE FILE
def open_file(dbname):
    with open(f'./storage/databases/{dbname}.pickle', 'rb') as dbfile:
        db = pickle.load(dbfile)
    return db, dbfile


def close_file(db, dbname):
    with open(f'./storage/databases/{dbname}.pickle', 'wb') as dbfile:
        pickle.dump(db, dbfile)
    dbfile.close()
