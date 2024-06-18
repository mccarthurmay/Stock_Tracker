import yfinance as yf
from datetime import date
from data.database import open_file, close_file
from data.analysis import rsi_calc, sell

#note

#winrate_storage stores 'holds'
#winrate stores 'sold'
#winrate_potential stores 'best possible sell'





class WinrateManager:
    def __init__(self):
        pass


    def makeWinrate(self):

        db = {}
        close_file(db, 'winrate_storage')
        close_file(db, 'winrate')
        close_file(db, 'winrate_potential')


    def winrate(self):
        try:
            db, dbfile = open_file('t_safe') #NEED TO MAKE THIS CHANGEABLE, OR HAVE MULTIPLE FILES
            db_w, dbfile_w = open_file('winrate_storage')
            for ticker, ticker_data in db.items():
                if ticker_data['Buy'] == True:
                    price = yf.Ticker(ticker).info['currentPrice']
                    if ticker not in db_w or db_w[ticker]['Price'] > price:
                        db_w[ticker] = {'Price': price, 'Date': date.today().strftime("%Y-%m-%d")}
                        print(f"Updated {ticker}: Price {price}, Date {date.today().strftime('%Y-%m-%d')} (win)")
            close_file(db_w, 'winrate_storage')
        except:
            self.makeWinrate()
            self.winrate()

    def w_dupes(self):
        try:
            db, dbfile = open_file('winrate_storage')
            db_w, dbfile_w = open_file('winrate')
            for ticker in db_w:
                if ticker in db:
                    del db[ticker]
                    print(f"{ticker} deleted (win)")
            close_file(db, 'winrate_storage')

        except Exception as e:
            print(f"duplicate did not work(winrate){e}")
        
        
        
    def checkwinrate(self):
        try:
            db, dbfile = open_file('winrate_storage')
            db_w, dbfile_w = open_file('winrate')
            for ticker, data in db.items():
                old_price = data['Price']
                old_date = data['Date']
                rsi = rsi_calc(ticker, graph = False)
                sell_bool = sell(rsi)
                if sell_bool == True and ticker not in db_w:
                    new_price = yf.Ticker(ticker).info['currentPrice']
                    gain = new_price - old_price
                    db_w[ticker] = {
                        'New Price': new_price,
                        'Old Price': old_price,
                        'Percent Gain': round( gain / old_price ,2),
                        'Old Date': old_date,
                        'New Date': date.today().strftime("%Y-%m-%d"),
                    }
                    print(f"Updated sold: {ticker}")

            close_file(db_w, 'winrate')
            close_file(db, 'winrate_storage')
            self.w_dupes()

        except Exception as e:
            print(f"Did not work (winrate): {e}")
            close_file(db_w, 'winrate')
            close_file(db, 'winrate_storage')

    def winrate_potential(self):  #third database to track potential best sell
        #try: 
        db_w, dbfile_w = open_file('winrate')
        db_p, dbfile_p = open_file('winrate_potential')

        for ticker, data in db_w.items():
            sold_price = data['New Price']
            sold_date = data['New Date']
            previous_gain = data['Gain']
            rsi = rsi_calc(ticker, graph = False)
            sell_bool = sell(rsi)

            if sell_bool == True:
                new_price = yf.Ticker(ticker).info['currentPrice']



                if ticker not in db_p:

                        
                    db_p[ticker] = {
                        'New Price': new_price,
                        '"Sold" Price': sold_price,
                        'Gain': round(new_price - sold_price,2),
                        'Total Gain': round(new_price - sold_price + previous_gain, 2),
                        '"Sold" Date': sold_date,
                        'New Date': date.today().strftime("%Y-%m-%d")
                    }
                    print(f"Created potential: {ticker}")
                else:
                    if db_p[ticker]['New Price'] < new_price:
                        db_p[ticker] = {
                            'New Price': new_price,
                            '"Sold" Price': sold_price,
                            'Gain': round(new_price - sold_price,2),
                            'Total Gain': round(new_price - sold_price + previous_gain, 2),
                            '"Sold" Date': sold_date,
                            'New Date': date.today().strftime("%Y-%m-%d")
                        }
                        print(f"Updated sold: {ticker}")


            
            close_file(db_w, 'winrate')
            close_file(db_p, 'winrate_potential')

        #except Exception as e:
            #print(f"Did not work (winrate_potential): {e}")








#UPDATE ALL HoLDINGS TO KEEP TRACK WITH RSI AND PRICE BUT DONT UPDATE ANYTHING ELSE