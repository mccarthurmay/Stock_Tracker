import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import linregress
import matplotlib.pyplot as plt
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime


def runall(ticker, db):
    percent_under = round(under_confidence(ticker, db).iloc[0])
    percent_over = round(over_confidence(ticker, db).iloc[0])
    rsi = rsi_calc(ticker, graph = False)
    buy_bool = buy(rsi, percent_under)
    short_bool = short(rsi, percent_over)
    cos, msd = rsi_accuracy(ticker)
    turnover = rsi_turnover(ticker)
    ma, ma_cross = MA(ticker, graph = False)
    db[ticker] = {
        'Ticker': ticker,
        'Buy': buy_bool,
        'Short': short_bool,
        '% Above 95% Confidence Interval': percent_over,
        '% Below 95% Confidence Interval': percent_under,
        'RSI': rsi,
        'RSI COS Accuracy': round(cos,2),
        'RSI MSD Accuracy': round(msd,2),
        'RSI Avg Turnover': turnover,
        'Moving Average': ma,
        'Moving Average Cross': ma_cross
    }


def runall_sell(ticker, db):
    percent_under = round(under_confidence(ticker, db).iloc[0])
    percent_over = round(over_confidence(ticker, db).iloc[0])
    rsi = rsi_calc(ticker, graph = False)
    sell_bool = sell(rsi)
    short_sell_bool = short_sell(rsi)
    cos, msd = rsi_accuracy(ticker)
    turnover = rsi_turnover(ticker)
    db[ticker] = {
        'Ticker': ticker,
        'Sell': sell_bool,
        'Short Sell': short_sell_bool,
        '% Above 95% Confidence Interval': percent_over,
        '% Below 95% Confidence Interval': percent_under,
        'RSI': rsi,
        'RSI COS Accuracy': round(cos,2),
        'RSI MSD Accuracy': round(msd,2),
        'RSI Avg Turnover': turnover
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
def over_confidence(ticker, dbname):
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
def rsi_base(ticker):
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
    return rsi, ticker, df

def rsi_calc(ticker, graph):
    rsi, ticker, df = rsi_base(ticker)

    #Graph
    if graph == True:
        plot_data(rsi, ticker, df)
    else:
        return (round(rsi[-1]))
    

def rsi_accuracy(ticker):
    rsi, ticker, df = rsi_base(ticker)
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

def rsi_turnover(ticker):
    rsi, ticker, df = rsi_base(ticker)
  
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


def plot_data(rsi, ticker, df):

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


def MA(ticker, graph):
    df = yf.Ticker(ticker).history(period="2y")
    MA = pd.DataFrame()
    MA['ST'] = df['Close'].ewm(span=20, adjust=False).mean() 
    MA['LT'] = df['Close'].ewm(span=50, adjust=False).mean()
    MA.dropna(inplace=True)

    latest_date = []
    latest_market = None
    warning = False
    for i in reversed(range(len(MA))):
        date = MA.index[i] 
        if i > 0:
            if MA['LT'].iloc[i-1] > MA['ST'].iloc[i-1] and MA['LT'].iloc[i] < MA['ST'].iloc[i]:
                latest_date = date
                latest_market = "BULL"
                if MA['ST'][-1] < MA['ST'][i]:
                    warning = True
                break  
            elif MA['LT'].iloc[i-1] < MA['ST'].iloc[i-1] and MA['LT'].iloc[i] > MA['ST'].iloc[i]:
                latest_date = date
                latest_market = "BEAR"
                if MA['ST'][-1] > MA['ST'][i]:
                    warning = True
                break 

    if latest_date:
        print(f"Most recent {latest_market} market detected on {latest_date}. Approaching cross: {warning}")

    else:
        print("No recent crossing detected")

    if graph == True:
        plt.plot(df['Close'].rolling(window=20).mean(), label = "short")
        plt.plot(df['Close'].rolling(window=50).mean())
        plt.legend()
        plt.show()

    return latest_date, warning


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
