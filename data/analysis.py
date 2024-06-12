import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import linregress
import matplotlib.pyplot as plt

def runall(ticker, db):
    percent_under = round(under_confidence(ticker, db).iloc[0])
    percent_over = round(over_confidence(ticker, db).iloc[0])
    rsi = rsi_calc(ticker, graph = False)
    buy_bool = buy(rsi, percent_under)
    short_bool = short(rsi, percent_over)
    db[ticker] = {
        'Ticker': ticker,
        'Buy': buy_bool,
        'Short': short_bool,
        '% Above 95% Confidence Interval': percent_over,
        '% Below 95% Confidence Interval': percent_under,
        'RSI': rsi
    }


def runall_sell(ticker, db):
    percent_under = round(under_confidence(ticker, db).iloc[0])
    percent_over = round(over_confidence(ticker, db).iloc[0])
    rsi = rsi_calc(ticker, graph = False)
    sell_bool = sell(rsi)
    short_sell_bool = short_sell(rsi)
    db[ticker] = {
        'Ticker': ticker,
        'Sell': sell_bool,
        'Short Sell': short_sell_bool,
        '% Above 95% Confidence Interval': percent_over,
        '% Below 95% Confidence Interval': percent_under,
        'RSI': rsi
    }


#BUY/SELL BOOL
def buy(rsi, percent_under):
    if percent_under > -1 and rsi < 31:
        return True
    else:
        return False

def short(rsi, percent_over):
    if percent_over > -1 and rsi > 79:
        return True
    else:
        return False

def sell(rsi):
    if rsi > 69:
        return True
    else:
        return False

def short_sell(rsi): #should switch to something else
    if rsi < 31:
        return True
    else:
        return False


#SLOPE CALCULATOR
#def slope(ticker):
    #df = yf.Ticker(ticker)
    #df = df.history(interval='1d', period='20mo')
    #dates = np.arange(len(df))
    #closing_prices = df['Close'].values
    #slope, _, _, _, _ = linregress(dates, closing_prices)
    #return slope
    #not sure if slope works, maybe do period prior to crash so 3-20 months


#CONFIDENCE - UNDER
def under_confidence(ticker, dbname):
    # closing price of input stock
    stock_data = yf.Ticker(ticker).history(period="2mo").reset_index(drop=True)

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
def over_confidence(ticker, dbname):
    # closing price of input stock
    stock_data = yf.Ticker(ticker).history(period="2mo").reset_index(drop=True)

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


#RSI
def rsi_calc(ticker, graph):
    ticker = yf.Ticker(ticker)
    df = ticker.history(interval="1d", period="2y")

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

    #Graph
    if graph == True:
        plt.style.use('fivethirtyeight')
        #figure size
        plt.rcParams['figure.figsize'] = (15,10)

        ax1 = plt.subplot2grid((10,1), (0,0), rowspan = 4, colspan = 1)
        ax2 = plt.subplot2grid((10, 1), (5, 0), rowspan=4, colspan=1)

        ax1.plot(df['Close'], linewidth = 2)
        ax1.set_title('Close prices')

        ax2.set_title('Relative Strength Index')
        ax2.plot(rsi, color = 'orange', linewidth = 1)

        #Oversold
        ax2.axhline(30, linestyle = '--', linewidth = 1.5, color = 'green')
        #Overbought
        ax2.axhline(70, linestyle = '--', linewidth = 1.5, color = 'red')

        plt.show()
    else:
        return (round(rsi[-1]))


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
