import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import linregress
import matplotlib.pyplot as plt
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox

class AnalysisManager:
    def __init__(self):
        self.CI = CIManager()
        self.RSI = RSIManager()
        
    def runall(self, ticker, db):
        percent_under = round(self.CI.under_confidence(ticker, db).iloc[0])
        percent_over = round(self.CI.over_confidence(ticker, db).iloc[0])
        ma, ma_date, converging = self.RSI.MA(ticker, graph = False)
        rsi = self.RSI.rsi_calc(ticker, graph = False, date = None)
        buy_bool = self.buy(rsi, percent_under)
        short_bool = self.short(rsi, percent_over)
        cos, msd = self.RSI.rsi_accuracy(ticker)
        turnover = self.RSI.rsi_turnover(ticker)
        db[ticker] = {
            'Ticker': ticker,
            'Buy': buy_bool,
            'Short': short_bool,
            '% Above 95% CI': percent_over,
            '% Below 95% CI': percent_under,
            'RSI': rsi,
            'RSI COS': round(cos,2),
            'RSI MSD': round(msd,2),
            'RSI Avg Turnover': turnover,
            'MA': (ma, ma_date),
            'MA Converging': converging
        }


    def runall_sell(self, ticker, db, price):
        percent_under = round(self.CI.under_confidence(ticker, db).iloc[0])
        percent_over = round(self.CI.over_confidence(ticker, db).iloc[0])
        ma, ma_date, converging = self.RSI.MA(ticker, graph = False)
        rsi = self.RSI.rsi_calc(ticker, graph = False, date = None)
        sell_bool = self.sell(rsi)
        short_sell_bool = self.short_sell(rsi)
        cos, msd = self.RSI.rsi_accuracy(ticker)
        turnover = self.RSI.rsi_turnover(ticker)
        #if sell_bool == True:
        #    messagebox.showinfo(title = "SELL ALERT", message = f"{ticker} is currently a sell.")
        if ticker in db:
            #If it exists, preserve the buy price
            buy_price = db[ticker]['Buy Price']
        
        else:
            #If it's a new entry, use the provided price
            buy_price = price
        
        #Update the database entry
        db[ticker] = {
            'Ticker': ticker,
            'Buy Price': buy_price,
            'Sell': sell_bool,
            'Short Sell': short_sell_bool,
            '% Above 95% CI': percent_over,
            '% Below 95% CI': percent_under,
            'RSI': rsi,
            'RSI COS': round(cos, 2),
            'RSI MSD': round(msd, 2),
            'RSI Avg Turnover': turnover,
            'MA': (ma, ma_date),
            'MA Converging': converging,
        }


    #BUY/SELL BOOL
    def buy(self, rsi, percent_under):
        if percent_under > -1 and rsi < 31:
            return True
        else:
            return False
        


                
                

    def short(self, rsi, percent_over):
        if percent_over > -1 and rsi > 79:
            return True
        else:
            return False

    def sell(self, rsi):
        if rsi > 69:
            return True
        else:
            return False

    def short_sell(self, rsi): #should switch to something else
        if rsi < 31:
            return True
        else:
            return False




class CIManager:
    def under_confidence(self, ticker, dbname):
        # closing price of input stock
        stock_data = yf.Ticker(ticker).history(period="3mo").reset_index(drop=True)

        stock_close = pd.DataFrame(stock_data['Close'])

        if int(stock_close.iloc[-1]) > 5:
            # confidence interval of 95% = standard deviation of data * 2
            ci = stock_close.std() * 2
            # lower bound of 95%
            lower_bound = stock_close.mean() - ci
            try:
                current_price = yf.Ticker(ticker).info['currentPrice']
                # percent over the lower bound of 2 std deviations (95% confidence interval)
                percent_under = (1 - current_price / lower_bound) * 100
                return percent_under
            except:
                print(f"No current price available for {ticker}.")

        else:
            try:
                del dbname[ticker]
                print(f"{ticker} is a penny stock. Removing ticker.")
            except:
                print(f"{ticker} is a penny stock. Not adding ticker.")

    #CONFIDENCE - OVER
    def over_confidence(self, ticker, dbname):
        # closing price of input stock
        stock_data = yf.Ticker(ticker).history(period="3mo").reset_index(drop=True)

        stock_close = pd.DataFrame(stock_data['Close'])

        if int(stock_close.iloc[-1]) > 5:
            # confidence interval of 95% = standard deviation of data * 2
            ci = stock_close.std() * 2
            # upper bound of 95%
            upper_bound = stock_close.mean() + ci
            try:
                current_price = yf.Ticker(ticker).info['currentPrice']
                # percent over the upper bound of 2 std deviations (95% confidence interval)
                percent_under = (1 - upper_bound/current_price) * 100
                return percent_under
            except:
                print(f"No current price available for {ticker}.")

        else:
            try:
                del dbname[ticker]
                print(f"{ticker} is a penny stock. Removing ticker.")
            except:
                print(f"{ticker} is a penny stock. Not adding ticker.")


class RSIManager:
    def __init__(self):
        self.CI = CIManager()

    def rsi_base(self, ticker, time, interval = "1d"):
        ticker = yf.Ticker(ticker)
        df = ticker.history(interval=interval, period= time)

        change = df['Close'].diff()
        change.dropna(inplace=True)
        #create two copies of closing price
        change_up = change.copy()
        change_down = change.copy()

        change_up[change_up<0]= 0
        change_down[change_down>0]= 0
        #check if mistakes
        change.equals(change_up+change_down)
        #calculate rolling average of average up and average down
        mean_up = change_up.rolling(14).mean()
        mean_down = change_down.rolling(14).mean().abs()
        #calculate rsi
        rsi = 100 * mean_up / (mean_up + mean_down)
        return rsi, ticker, df

    def rsi_calc(self, ticker, graph, date):
        rsi, ticker, df = self.rsi_base(ticker, '2y')

        #Graph
        if graph == True:
            self.plot_data(rsi, ticker, df)
        elif date != None:
            return (round(rsi[date]))
        else:
            rsi = round(rsi[-1])
            return rsi
        

    def rsi_accuracy(self, ticker):
        rsi, ticker, df = self.rsi_base(ticker, '2y')
        df = df['Close']
        #calculate mean + std of both datasets
        mean_df = np.mean(df)
        mean_rsi = np.mean(rsi)
        std_df = np.std(df)
        std_rsi = np.std(rsi)
        
        #standardize data
        df_standardized = (df - mean_df) / std_df
        rsi_standardized = (rsi - mean_rsi) / std_rsi


        #COSINE SIMIlARITY - penalizes larger differences more heavily
        df_standardized = df_standardized.iloc[14:] #deleting first 13 numbers due to rolling average producing NAN in rsi
        rsi_standardized = rsi_standardized.iloc[13:] #deleting first 13 numbers due to rolling average producing NAN in rsi
        df_standardized = df_standardized.values.reshape(1,-1)
        rsi_standardized = rsi_standardized.values.reshape(1,-1)
        cos_accuracy = cosine_similarity(df_standardized, rsi_standardized)[0][0]


        #MEAN SQUARED DIFFERENCE - prioritizes relative direction and order of data points more than absolute values
        MSD = (np.mean(np.square(df_standardized - rsi_standardized)))
        msd_accuracy = 1 / (1 + MSD)

        return cos_accuracy, msd_accuracy

    def rsi_turnover(self, ticker):
        rsi, ticker, df = self.rsi_base(ticker, '2y')
    
        rsi_frame = rsi.iloc[13:]
        low_threshold = True
        peak_dates = []   
        for date, value in rsi_frame.items():
            if value > 70 and low_threshold == True:
                peak_dates.append(date)
                low_threshold = False
            if value < 30:
                low_threshold = True

        turnover = []
        for i in range(len(peak_dates) - 1):
            date1_obj = datetime.fromisoformat(str(peak_dates[i]))
            date2_obj = datetime.fromisoformat(str(peak_dates[i + 1]))
            delta = date2_obj - date1_obj
            turnover.append(delta.days)
        average_turnaround = sum(turnover) / len(turnover)
        return round(average_turnaround, 0)


    def plot_data(self, rsi, ticker, df):

        plt.style.use('fivethirtyeight')
        #figure size
        plt.rcParams['figure.figsize'] = (15,10)
        df = df.iloc[13:]
        s_df = {}
        l_df = {}
        s_df['MA'] = df['Close'].rolling(window=20).mean()
        l_df['MA'] = df['Close'].rolling(window=50).mean()
        ax1 = plt.subplot2grid((10,1), (0,0), rowspan = 4, colspan = 1)
        ax2 = plt.subplot2grid((10, 1), (5, 0), rowspan=4, colspan=1)

        ax1.plot(df['Close'], linewidth = 3)
        ax1.plot(s_df['MA'], label = 'Short-Term Moving Average', color = 'Red', linestyle = '--', linewidth = 2)
        ax1.plot(l_df['MA'], label = 'Long-Term Moving Average', color = 'Purple', linestyle = '--', linewidth = 2)
        ax1.set_title('Close prices')

        ax2.set_title('Relative Strength Index')
        ax2.plot(rsi, color = 'orange', linewidth = 1)

        #Oversold
        ax2.axhline(30, linestyle = '--', linewidth = 1.5, color = 'green')
        #Overbought
        ax2.axhline(70, linestyle = '--', linewidth = 1.5, color = 'red')
        ax1.legend()
        plt.show()



    def MA(self, ticker, graph, input_interval="1m", input_period="5d", span1=50, span2=200, standardize=False):
        df = yf.Ticker(ticker).history(interval=input_interval, period=input_period)
        df = df.between_time('09:30', '16:00')
        
        if standardize:
            mean = df['Close'].mean()
            std = df['Close'].std()
            close_data = (df['Close'] - mean) / std
        else:
            close_data = df['Close']
        
        MA = pd.DataFrame()
        MA['ST'] = close_data.ewm(span=span1, adjust=False).mean() 
        MA['LT'] = close_data.ewm(span=span2, adjust=False).mean()
        MA.dropna(inplace=True)
        
        converging = False
        latest_date = None
        converging_li = []    
        latest_market = None
        
        for i in reversed(range(len(MA))):
            date = MA.index[i] 
            if i > 0:
                if MA['ST'].iloc[-1] > MA['LT'].iloc[-1]:
                    latest_date = date
                    latest_market = "BULL"
                    break  
                elif  MA['ST'].iloc[-1] < MA['LT'].iloc[-1]:
                    latest_date = date
                    latest_market = "BEAR"
                    break 
                converging_li.append(abs(MA['LT'].iloc[i] - MA['ST'].iloc[i]))
        
        converging_li.reverse()
        if len(converging_li) >= 20 and all(converging_li[i] < converging_li[i-1] for i in range(-1, -21, -1)):
            converging = True
        
        if standardize:
            MA['ST'] = (MA['ST'] * std) + mean
            MA['LT'] = (MA['LT'] * std) + mean
        
        if graph:
            plt.figure(figsize=(12, 6))
            plt.plot(df.index, MA['ST'])
            plt.plot(df.index, MA['LT'])
            plt.plot(df.index, df['Close'], label="Close Price", alpha=0.5)
            plt.title(f"{ticker} Moving Averages")
            plt.xlabel("Date")
            plt.ylabel("Price")
            plt.legend()
            plt.show()
        
        if latest_date:
            latest_date_str = latest_date.strftime('%m-%d')
            return latest_market, latest_date_str, converging
        else:
            print("No recent crossing detected")
            return None, None, converging

    
    def macd(self, symbol, interval='1m', fast_period=12, slow_period=26, signal_period=9):

        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        stock = yf.Ticker(symbol)
        df = stock.history(start=start_date, end=end_date, interval=interval)
        if df.empty:
            return None


        df['EMA_fast'] = df['Close'].ewm(span=fast_period, adjust=False).mean()
        df['EMA_slow'] = df['Close'].ewm(span=slow_period, adjust=False).mean()

        df['MACD'] = df['EMA_fast'] - df['EMA_slow']

        df['Signal'] = df['MACD'].ewm(span=signal_period, adjust=False).mean()

        current_data = df.iloc[-1]

        if current_data['MACD'] > current_data['Signal']:
            return "BULL"
        else:
            return "BEAR"
        


#possibly add this to main filter function,(most recent rsi score indicates 'buy' or add rsi score to print in summary)
#not done
def day_movement(ticker):
    stock_data = yf.Ticker(ticker).history(period="3mo").reset_index(drop=True)
    stock_close = pd.DataFrame(stock_data['Close'])
    stock_close = stock_close.iloc[-1]
    stock_curr = yf.Ticker(ticker).info['currentPrice']
    stock_perc = (stock_close - stock_curr) / stock_close
    print(f"{float(stock_perc.values):.15f}")


#SHOWINFO
def showinfo(ticker):
    stock_data = yf.Ticker(ticker)
    stock_history = stock_data.history(period = '3mo')
    print('\n',stock_data.info['longBusinessSummary'])
    stock_close = pd.DataFrame(stock_history['Close']).iloc[-2].item()
    stock_curr = yf.Ticker(ticker).info['currentPrice']
    print('\nStock Close:',stock_close,'\nCurrent Price:', stock_curr)




###CALLING yf.ticker.history for many functions... may be increasing time signfificantly


###Add to winrate/shortrate... 'current rsi current approaching' and update that each time


#Depreciated 
"""
#VISUALIZE CONFIDENCE INTERVAL
def con_plot(ticker):

    tick = yf.Ticker(ticker)
    df_list = tick.history(interval='1d', period='20mo')
    df = pd.DataFrame(df_list['Close'])
    ci_list = []
    ci = df.std() * 2
    upper_bound = df.mean() + ci
    lower_bound = df.mean() - ci
    mean = df.mean()
    current = yf.Ticker(ticker).info['currentPrice']
    print(f"CI:{ci.values} \nUpper Bound:{upper_bound.values} \nLower Bound:{lower_bound.values} \nMean:{mean.values} \nCurrent:{current}")
    for close in df_list['Close']:
        percent_lower = (close - lower_bound) / (upper_bound - lower_bound) * 100
        ci_list.append(percent_lower)  # Append to list
    plt.style.use('fivethirtyeight')
    #figure size
    plt.rcParams['figure.figsize'] = (15,10)

    ax1 = plt.subplot2grid((10,1), (0,0), rowspan = 4, colspan = 1)
    ax2 = plt.subplot2grid((10, 1), (5, 0), rowspan=4, colspan=1)

    ax1.plot(df['Close'], linewidth = 2)
    ax1.set_title('Close prices')

    ax2.set_title('Confidence Interval')
    ax2.plot(ci_list, color = 'orange', linewidth = 1)

    #Oversold
    ax2.axhline(30, linestyle = '--', linewidth = 1.5, color = 'green')
    ax2.axhline(70, linestyle = '--', linewidth = 1.5, color = 'red')

    plt.show()



#SLOPE CALCULATOR
#def slope(ticker):
    #df = yf.Ticker(ticker)
    #df = df.history(interval='1d', period='20mo')
    #dates = np.arange(len(df))
    #closing_prices = df['Close'].values
    #slope, _, _, _, _ = linregress(dates, closing_prices)
    #return slope
    #not sure if slope works, maybe do period prior to crash so 3-20 months    
"""