import os
import pickle
import concurrent.futures
from data.analysis import AnalysisManager
from tkinter import messagebox, simpledialog
from datetime import datetime, timedelta
import yfinance as yf
class DBManager:
    def __init__(self):
        self.analysis = AnalysisManager()

    def storeData(self, dbname, stock_list):
        try:
            db, dbfile = open_file(dbname)
        except FileNotFoundError:
            db = {}

        for ticker in stock_list:
            db[ticker] = {
            }

        #source, destination
        close_file(db, dbname)

        db, dbfile = open_file(dbname)

        def process_ticker(ticker):
            try:
                self.analysis.runall(ticker, db)
            except Exception as e:
                print(f"Removing {ticker}: {e}")
                del db[ticker]

        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.map(process_ticker, db.keys())

        close_file(db, dbname)

    #ADD TICKER
    def addData(self, ticker, dbname):
        try:
            db, dbfile = open_file(dbname)

            if ticker not in db:
                try:
                    self.analysis.runall(ticker, db)
                except Exception as e:
                    print(f"Removing {ticker}: {e}")
                    del db[ticker]
            else:
                print("Ticker already exists")

            close_file(db, dbname)

        except FileNotFoundError:
            print("File not found")


    #REMOVE TICKER
    def remData(self, ticker, dbname):
        try:
            db, dbfile = open_file(dbname)
            del db[ticker]
            close_file(db, dbname)
            print(f"Removing {ticker}")
        except FileNotFoundError:
            print("File not found")


    #DELETE DATABASE
    def resetData(self, dbname):
        os.remove(f'./storage/databases/{dbname}.pickle')


    #DISPLAY DATABASE
    def loadData(self, dbname, sort_choice):
        #try:
        db, dbfile = open_file(dbname)
        if sort_choice == "normal":
            sorted_data = sorted(db.values(), key=lambda x: x['% Below 95% CI'] if x['% Below 95% CI'] is not None else float('inf'), reverse = True)
        elif sort_choice == "short":
            sorted_data = sorted(db.values(), key=lambda x: x['% Above 95% CI'] if x['% Above 95% CI'] is not None else float('inf'), reverse = True)
        elif sort_choice == "msd":
            sorted_data = sorted(db.values(), key=lambda x: x['RSI MSD'] if x['RSI MSD'] is not None else float('inf'), reverse = True)
        elif sort_choice == "rsi":
            sorted_data = sorted(db.values(), key=lambda x: x['RSI'] if x['RSI'] is not None else float('inf'), reverse = True)
        elif sort_choice == "turn":
            sorted_data = sorted(db.values(), key=lambda x: x['RSI Avg Turnover'] if x['RSI Avg Turnover'] is not None else float('inf'), reverse = False)
        
        for ticker in sorted_data:
            print(ticker)
        dbfile.close()
        return sorted_data

        #except Exception as e:
        #    print(f"{e}")



class Update():
    def __init__(self):
        self.analysis = AnalysisManager()
    def updatePortfolio(self, dbname):
        try:
            db, dbfile = open_file(dbname)
            print(f"{dbname} loading...")
        except FileNotFoundError:
            print("Portfolio not found")

        def process_ticker(ticker):
            try:
                self.analysis.runall_sell(ticker, db, price = None)
            except Exception as e:
                print(f"There has been an error with {ticker}: {e}")

        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.map(process_ticker, db.keys())

        close_file(db, dbname)


    #UPDATE DATABASES
    def updateData(self, dbname):
        try:
            db, dbfile = open_file(dbname)
            print(f"{dbname} loading...")
        except FileNotFoundError:
            print("file not found")
            return None

        def process_ticker(ticker):
            try:
                self.analysis.runall(ticker, db)
            except Exception as e:
                print(f"There has been an error with {ticker}: {e}")

        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.map(process_ticker, db.keys())

        close_file(db, dbname)

    def find_s_buy(self, database):
        db, dbfile = open_file(database)
        for ticker, info in db.items():
            try:           
                if info['MA'][0] == "BULL" and info['Buy'] == True:
                    date_obj = datetime.strptime(info['MA'][1], "%m-%d")
                    if (datetime.today() - date_obj) < timedelta(days=30):
                        messagebox.showinfo(title = "strong buy", message = f"{ticker} is currently a strong buy.")
            except Exception as e:
                print(e)
                pass
    
    #CREATE/EDIT MAIN PORTFOLIO
    def mainPortfolio(self, dbname):
        try:
            db, dbfile = open_file(dbname)
        except FileNotFoundError:
            db = {}

        while True:
            ticker = simpledialog.askstring("Input", "Input ticker to be added (type 'done' to exit):").strip().upper()


            if ticker == "DONE":
                break

            if ticker not in db:
                price = simpledialog.askstring("Input", "Price of purchased stock:")
                self.analysis.runall_sell(ticker, db, price)
                
            else:
                print("Ticker already exists")

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




