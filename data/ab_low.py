import yfinance as yf
from datetime import date
from data.database import open_file, close_file
from data.analysis import rsi_calc, sell
import os

class ab_lowManager:
    def __init__(self):
        pass


    def checkfile(self):
        db = {}
        if not os.path.exists('./storage/databases/10.pickle'):
            close_file(db, '10')
            print('10.py created')
        if not os.path.exists('./storage/databases/15.pickle'):
            close_file(db, '15')
            print('15.py created')    
        if not os.path.exists('./storage/databases/20.pickle'):
            close_file(db, '20')
            print('20.py created')
        if not os.path.exists('./storage/databases/25.pickle'):
            close_file(db, '25')
            print('25.py created')    
        if not os.path.exists('./storage/databases/30.pickle'):
            close_file(db, '30')
            print('30.py created')
        if not os.path.exists('./storage/databases/40.pickle'):
            close_file(db, '40')
            print('40.py created')


    def set_param(self, data, db, ticker, num):
        old_price = yf.Ticker(ticker).info['currentPrice']
        old_date = date.today().strftime("%Y-%m-%d")
        old_rsi = data['RSI']
        turnover = data['RSI Avg Turnover']
        accuracy_msd = data['RSI MSD']
        accuracy_cos = data['RSI COS']
        ma = data['MA']
        converging = data['MA Converging']
        
        db[ticker] = {
            'Price': old_price, 
            'Date': old_date, 
            'RSI': old_rsi, 
            'Turnover': turnover, 
            'MSD': accuracy_msd, 
            'COS': accuracy_cos,
            'MA': ma,
            'Converging': converging,
        }
        close_file(db, num)


    def open_all_files(self):
        db, dbfile = open_file('t_safe')
        db_10, dbfile_10 = open_file('10')
        db_15, dbfile_15 = open_file('15')
        db_20, dbfile_20 = open_file('20')
        db_25, dbfile_25 = open_file('25')
        db_30, dbfile_30 = open_file('30')
        db_40, dbfile_40 = open_file('40')
        return db, dbfile, db_10, dbfile_10, db_15, dbfile_15, db_20, dbfile_20, db_25, dbfile_25, db_30, dbfile_30, db_40, dbfile_40
    
    def scanRSI(self):
        db, dbfile, db_10, dbfile_10, db_15, dbfile_15, db_20, dbfile_20, db_25, dbfile_25, db_30, dbfile_30, db_40, dbfile_40 = self.open_all_files()

        for ticker, data in db.items():
            if data['RSI'] <= 10 and ticker not in db_10:
                self.set_param(data, db_10, ticker, '10')
                print(ticker, '10')

            if data['RSI'] > 10 and data['RSI'] <=15 and ticker not in db_15:
                self.set_param(data, db_15, ticker, '15')
                print(ticker, '15')

            if data['RSI'] > 15 and data['RSI'] <=20 and ticker not in db_20:
                self.set_param(data, db_20, ticker, '20')
                print(ticker, '20')

            if data['RSI'] > 20 and data['RSI'] <=25 and ticker not in db_25: 
                self.set_param(data, db_25, ticker, '25')
                print(ticker), '25'
            if data['RSI'] > 25 and data['RSI'] <=30 and ticker not in db_30:
                self.set_param(data, db_30, ticker, '30')
                print(ticker, '30')

            if data['RSI'] > 30 and data['RSI'] <=40 and ticker not in db_40:
                self.set_param(data, db_40, ticker, '40')
                print(ticker, '40')

    def update():
        #checks for sell signal
        #db, dbfile, db_10, dbfile_10, db_15, dbfile_15, db_20, dbfile_20, db_25, dbfile_25, db_30, dbfile_30, db_40, dbfile_40 = self.open_all_files()
        #rsi = rsi_calc(ticker, graph = False, date = None)
        #sell_bool = sell(rsi)
        pass
    def limit():
        #db, dbfile, db_10, dbfile_10, db_15, dbfile_15, db_20, dbfile_20, db_25, dbfile_25, db_30, dbfile_30, db_40, dbfile_40 = self.open_all_files()
        
        #get history of each stock in for loop from buy date
        #   - find the lowest price in that history and compare (percentages)

        pass



    #1. absolute low project 
    #    - find how much holders fluctuate 
    #    - use 10 rsi, 15 rsi, 20 rsi, and 30 rsi as buy signals
    #    - collect all necessary information at purchase date
    #        - date, volume, rsi, moving average (maybe a ratio)
    #    - gives information on how to set limits


    #ISSUES
    # - Not constantly running, so comparison of the same stock may not always occur (i will miss the point where it hits 20 rsi)