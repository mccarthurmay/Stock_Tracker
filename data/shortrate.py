import yfinance as yf
from datetime import date
from data.database import open_file, close_file
from data.analysis import rsi_calc, sell, short_sell

class ShortrateManager:
    def __init__(self):
        pass


    def makeshortrate(self):

        db = {}
        close_file(db, 'shortrate_storage')
        close_file(db, 'shortrate')
        close_file(db, 'shortrate_potential')


    def shortrate(self):
        try:
            db, dbfile = open_file('t_safe') #NEED TO MAKE THIS CHANGEABLE, OR HAVE MULTIPLE FILES
            db_w, dbfile_w = open_file('shortrate_storage')
            for ticker, ticker_data in db.items():
                if ticker_data['Short'] == True:
                    price = yf.Ticker(ticker).info['currentPrice']
                    if ticker not in db_w or db_w[ticker]['Price'] < price:
                        db_w[ticker] = {'Price': price, 'Date': date.today().strftime("%Y-%m-%d"), 'RSI': ticker_data['RSI']}
                        print(f"Updated {ticker}: Price {price}, Date {date.today().strftime('%Y-%m-%d')} (short)")  #needs to hold different data
            close_file(db_w, 'shortrate_storage')
        except:
            self.makeshortrate()
            self.shortrate()



    def w_dupes(self):
        try:
            db, dbfile = open_file('shortrate_storage')
            db_w, dbfile_w = open_file('shortrate')
            for ticker in db_w:
                if ticker in db:
                    del db[ticker]
                    print(f"{ticker} deleted (short)")
            close_file(db, 'shortrate_storage')

        except Exception as e:
            print(f"duplicate did not work(shortrate){e}")
        

    def checkshortrate(self):
        try:
            db, dbfile = open_file('shortrate_storage')
            db_w, dbfile_w = open_file('shortrate')
            for ticker, data in db.items():
                old_price = data['Price']
                old_date = data['Date']
                old_rsi = data['RSI']
                rsi = rsi_calc(ticker, graph = False)
                short_sell_bool = short_sell(rsi)
                if short_sell_bool == True and ticker not in db_w:
                    new_price = round(yf.Ticker(ticker).info['currentPrice'], 2)
                    new_rsi = rsi_calc(ticker, graph = False)
                    db_w[ticker] = {
                        'New Price': new_price,
                        'Old Price': old_price,
                        'Gain': old_price - new_price,
                        'Old Date': old_date,
                        'New Date': date.today().strftime("%Y-%m-%d"),
                        'Old RSI': old_rsi,
                        'New RSI': new_rsi
                    }
                    print(f"Updated sold: {ticker}")
            close_file(db_w, 'shortrate')
            close_file(db, 'shortrate_storage')
            self.w_dupes()
        except Exception as e:
            print(e)



    def shortrate_potential(self):  #third database to track potential best sell
        #try: 
        db_w, dbfile_w = open_file('shortrate')
        db_p, dbfile_p = open_file('shortrate_potential')

        for ticker, data in db_w.items():
            sold_price = data['New Price']
            sold_date = data['New Date']
            previous_gain = data['Gain']
            rsi = rsi_calc(ticker, graph = False)
            sold_rsi = data['New RSI']
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
                        'New Date': date.today().strftime("%Y-%m-%d"),
                        '"Sold" RSI': sold_rsi,
                        'New RSI': rsi
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
                            'New Date': date.today().strftime("%Y-%m-%d"),
                            '"Sold" RSI': sold_rsi,
                            'New RSI': rsi
                        }
                        print(f"Updated sold: {ticker}")


            
            close_file(db_w, 'shortrate')
            close_file(db_p, 'shortrate_potential')