import yfinance as yf
from datetime import date
from data.database import open_file, close_file
from data.analysis import rsi_calc, sell
import os
#note

#winrate_storage stores 'holds'
#winrate stores 'sold'
#winrate_potential stores 'best possible sell'





class WinrateManager:
    def __init__(self):
        pass


    def checkWinrate(self):
        db = {}
        if not os.path.exists('./storage/databases/winrate_storage.pickle'):
            close_file(db, 'winrate_storage')
            print('winrate_storage.py created')
        if not os.path.exists('./storage/databases/winrate.pickle'):
            close_file(db, 'winrate')
            print('winrate.py created')
        if not os.path.exists('./storage/databases/winrate_potential.pickle'):
            close_file(db, 'winrate_potential')
            print('winrate_potential.py created')


    def winrate(self):

        db, dbfile = open_file('t_safe') #NEED TO MAKE THIS CHANGEABLE, OR HAVE MULTIPLE FILES
        db_w, dbfile_w = open_file('winrate_storage')
        open_file('winrate')
        open_file('winrate_potential')
        for ticker, ticker_data in db.items():
            if ticker_data['Buy'] == True:
                price = yf.Ticker(ticker).info['currentPrice']
                if ticker not in db_w or db_w[ticker]['Price'] < price:
                    db_w[ticker] = {'Price': price, 
                                    'Date': date.today().strftime("%Y-%m-%d"), 
                                    'RSI': ticker_data['RSI'], 
                                    'RSI Avg Turnover': ticker_data['RSI Avg Turnover'], 
                                    'RSI MSD Accuracy': ticker_data['RSI MSD'], 
                                    'RSI COS Accuracy': ticker_data['RSI COS'],
                                    'MA': (ticker_data['MA'])
                                    }
                    print(f"Updated {ticker}: Price {price}, Date {date.today().strftime('%Y-%m-%d')} (win)")
        close_file(db_w, 'winrate_storage')

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
        


        
    def scanWinrate(self):
        try:
            db, dbfile = open_file('winrate_storage')
            db_w, dbfile_w = open_file('winrate')
            for ticker, data in db.items():
                old_price = data['Price']
                old_date = data['Date']
                rsi = rsi_calc(ticker, graph = False)
                sell_bool = sell(rsi)
                turnover = data['RSI Avg Turnover']
                accuracy_msd = data['RSI MSD Accuracy']
                accuracy_cos = data['RSI COS Accuracy']
                ma = data['MA']


                if sell_bool == True and ticker not in db_w:
                    new_price = yf.Ticker(ticker).info['currentPrice']
                    gain = new_price - old_price
                    db_w[ticker] = {
                        'New Price': new_price,
                        'Old Price': old_price,
                        'Gain': round(gain, 2),
                        '% Gain': str(round( gain / old_price * 100 ,1)) + '%',
                        'Old Date': old_date,
                        'New Date': date.today().strftime("%Y-%m-%d"),
                        'RSI Avg Turnover': turnover,
                        'RSI MSD Accuracy': accuracy_msd,
                        'RSI COS Accuracy': accuracy_cos,
                        'MA': ma
                    }
                    print(f"Updated Sold: {ticker} (win)")

            close_file(db_w, 'winrate')
            close_file(db, 'winrate_storage')
            self.w_dupes()

        except Exception as e:
            print(f"Did not work (winrate): {e}")
            close_file(db_w, 'winrate')
            close_file(db, 'winrate_storage')

    def winratePotential(self):  #third database to track potential best sell
        #try: 
        db_w, dbfile_w = open_file('winrate')
        db_p, dbfile_p = open_file('winrate_potential')

        for ticker, data in db_w.items():
            sold_price = data['New Price']
            sold_date = data['New Date']
            previous_gain = data['Gain']
            turnover = data['RSI Avg Turnover']
            accuracy_msd = data['RSI MSD Accuracy']
            accuracy_cos = data['RSI COS Accuracy']
            ma = data['MA']
            rsi = rsi_calc(ticker, graph = False)
            sell_bool = sell(rsi)

            if sell_bool == True:
                new_price = yf.Ticker(ticker).info['currentPrice']
                gain = new_price - sold_price
                old_price = data['Old Price']


                if ticker not in db_p:

                        
                    db_p[ticker] = {
                        'New Price': new_price,
                        '"Sold" Price': sold_price,
                        '% Gain': str(round(gain/old_price * 100,1)),
                        'Total % Gain': str(round((gain + float(previous_gain))/old_price * 100, 1)) + '%',
                        '"Sold" Date': sold_date,
                        'New Date': date.today().strftime("%Y-%m-%d"),
                        'RSI Avg Turnover': turnover,
                        'RSI MSD Accuracy': accuracy_msd,
                        'RSI COS Accuracy': accuracy_cos,
                        'MA': ma
                    }
                    print(f"Created potential: {ticker} (win)")
                else:
                    if db_p[ticker]['New Price'] < new_price:
                        db_p[ticker] = {
                            'New Price': new_price,
                            '"Sold" Price': sold_price,
                            '% Gain': str(round(gain/old_price * 100,1)),
                            'Total % Gain': str(round((gain + float(previous_gain))/old_price * 100, 1)) + '%',
                            '"Sold" Date': sold_date,
                            'New Date': date.today().strftime("%Y-%m-%d"),
                            'RSI Avg Turnover': turnover,
                            'RSI MSD Accuracy': accuracy_msd,
                            'RSI COS Accuracy': accuracy_cos,
                            'MA': ma
                        }
                        print(f"Updated potential: {ticker} (win)")


            
            close_file(db_w, 'winrate')
            close_file(db_p, 'winrate_potential')

        #except Exception as e:
            #print(f"Did not work (winrate_potential): {e}")








#UPDATE ALL HoLDINGS TO KEEP TRACK WITH RSI AND PRICE BUT DONT UPDATE ANYTHING ELSE