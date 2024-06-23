import os
import pickle
import concurrent.futures
from data.analysis import runall, runall_sell
from tkinter import messagebox, simpledialog

def storeData(dbname, stock_list):
    try:
        db, dbfile = open_file(dbname)
    except FileNotFoundError:
        db = {}

    for ticker in stock_list:
        db[ticker] = {
            'Ticker': None,
            'Buy': None,
            'Short': None,
            '% Above 95% Confidence Interval': None,
            '% Below 95% Convidence Interval': None,
            'RSI': None,
            'RSI COS Accuracy': None,
            'RSI MSD Accuracy': None,
            'RSI Avg Turnover': None
        }

    #source, destination
    close_file(db, dbname)

    db, dbfile = open_file(dbname)

    def process_ticker(ticker):
        try:
            runall(ticker, db)
        except Exception as e:
            print(f"Removing {ticker}: {e}")
            del db[ticker]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(process_ticker, db.keys())

    close_file(db, dbname)


#CREATE/EDIT MAIN PORTFOLIO
def mainPortfolio(dbname):
    try:
        db, dbfile = open_file(dbname)
    except FileNotFoundError:
        db = {}

    while True:
        ticker = simpledialog.askstring("Input", "Input ticker to be added (type 'done' to exit):").strip().upper()


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
def loadData(dbname, sort_choice):
    try:
        db, dbfile = open_file(dbname)
        if sort_choice == "normal":
            sorted_data = sorted(db.values(), key=lambda x: x['% Below 95% Confidence Interval'] if x['% Below 95% Confidence Interval'] is not None else float('inf'), reverse = True)
        elif sort_choice == "short":
            sorted_data = sorted(db.values(), key=lambda x: x['% Above 95% Confidence Interval'] if x['% Above 95% Confidence Interval'] is not None else float('inf'), reverse = True)
        elif sort_choice == "msd":
            sorted_data = sorted(db.values(), key=lambda x: x['RSI MSD Accuracy'] if x['RSI MSD Accuracy'] is not None else float('inf'), reverse = True)
        elif sort_choice == "cos":
            sorted_data = sorted(db.values(), key=lambda x: x['RSI COS Accuracy'] if x['RSI COS Accuracy'] is not None else float('inf'), reverse = True)
        elif sort_choice == "turn":
            sorted_data = sorted(db.values(), key=lambda x: x['RSI Avg Turnover'] if x['RSI Avg Turnover'] is not None else float('inf'), reverse = False)
        
        for ticker in sorted_data:
            print(ticker)
        dbfile.close()
        return sorted_data

    except Exception as e:
        print(f"{e}")


#UPDATE PORTFOLIO
def updatePortfolio(dbname):
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
            print(f"There has been an error with {ticker}: {e}")


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



