import yfinance as yf
from datetime import date
from data.database import open_file, close_file
from data.analysis import rsi_calc, sell

class WinrateManager:
    def __init__(self):
        pass


    def makeWinrate(self):

        db = {}
        close_file(db, 'winrate_storage')
        close_file(db, 'winrate')


    def winrate(self):
        try:
            db, dbfile = open_file('t_safe') #NEED TO MAKE THIS CHANGEABLE, OR HAVE MULTIPLE FILES
            db_w, dbfile_w = open_file('winrate_storage')
            for ticker, ticker_data in db.items():
                if ticker_data['Buy'] == True:
                    price = yf.Ticker(ticker).info['currentPrice']
                    if ticker not in db_w or db_w[ticker]['Price'] > price:
                        db_w[ticker] = {'Price': price, 'Date': date.today().strftime("%Y-%m-%d")}
                        print(f"Updated {ticker}: Price {price}, Date {date.today().strftime('%Y-%m-%d')}")
            close_file(db_w, 'winrate_storage')
        except:
            self.makeWinrate()
            self.winrate()

    def checkwinrate(self):
        db, dbfile = open_file('winrate_storage')
        db_w, dbfile_w = open_file('winrate')
        for ticker, data in db.items():
            old_price = data['Price']
            old_date = data['Date']
            rsi = rsi_calc(ticker, graph = False)
            sell_bool = sell(rsi)
            if sell_bool == True and ticker not in db_w:
                new_price = yf.Ticker(ticker).info['currentPrice']
                db_w[ticker] = {
                    'New Price': new_price,
                    'Old Price': old_price,
                    'Gain': new_price - old_price,
                    'Old Date': date,
                    'New Date': date.today().strftime("%Y-%m-%d")
                }
                del db[ticker]
                print(f"{ticker} deleted")
        close_file(db_w, 'winrate')
        close_file(db, 'winrate_storage')
