from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca_trade_api.rest import REST, TimeFrame
import os
from config import *
from data.day_trade import DTManager, DTCalc
import time as tm
import yfinance as yf
import concurrent.futures
from data.analysis import RSIManager
from datetime import datetime, time
import matplotlib.pyplot as plt
import keyboard
from queue import Queue
dt = DTManager()
dtc = DTCalc()
rsim = RSIManager()


        
try:
    api = REST(
    key_id=os.getenv("APCA_API_KEY_ID"),
    secret_key=os.getenv("APCA_API_SECRET_KEY"),
    base_url="https://paper-api.alpaca.markets"
    )
    account = api.get_account()
except:
    print("API Environment not set up. Please refer to 'config.py' or 'README'.")



def process_entry(entry):
    #Set parameters
    ticker = entry[1]
    rsi, current_price, stop_l, gain, time, stop, limit, wl = dt.main(ticker)
    equity = float(account.equity)
    quantity = round((float(equity)/5) / current_price, 0) - 1
    stp = round(stop,2) # lower confidence interval of decrease increase gain
    lmt = round(limit,2) # mean of decrease increase
    #stp_l = round(stop_l,2) # lower confidence interval of decrease increase range
    stp_l = round((current_price * .998),2) #trading based on win rate
    print(f"Buy: {current_price}, Sell: {stp}, Stop Loss: {stp_l}, Quantity: {quantity}")
    try:
    #Buy order
        buy_order = api.submit_order(   # buy
            symbol = ticker,
            qty = quantity,
            side = 'buy',
            type = 'market',
            order_class='oto',
            stop_loss = {'stop_price': stp_l},
            #stop_price= stp_l,
            #stop_loss={'stop_price': stp_l},  # Stop-loss order
            #take_profit={'limit_price': stp},  # Take-profit order
            time_in_force = 'gtc',
    #WAS CAUSING PROBLEMS PREVIOUSLY
            ) 

    except Exception as e:
        print(e, "Buy order not submitted")

    

    #Check if order was filled
    order_filled = False       # check if this is needed
    print(f"Waiting for {ticker} to be filled.")
    while not order_filled:
        order = api.get_order(buy_order.id)
        stop_order = api.get_order(stop_order.id)
        if order.status == 'filled':
            order_filled = True
            fill_price = order.filled_avg_price
            print(f"{ticker} has filled.")
        else:
            tm.sleep(2)
            

    #When order is filled:       
    if order_filled:
        pass

def get_open_positions():
    positions = api.list_positions()
    return {position.symbol for position in positions}, len(positions)

# Close orders once sold
def close_all_orders(ticker):
    orders = api.list_orders(status='open', symbols=[ticker])
    for order in orders:
        try:
            api.cancel_order(order.id)
        except Exception as e:
            print(f"Error cancelling order for {ticker}: {str(e)}")

def monitor_position(ticker):
    trailing_percent = 0.0005  # .05% trailing stop
    highest_price = 0
    trailing_stop_active = False

    while True:
        
        # Test if position exists
        position = api.get_position(ticker)
        if position is None:
            close_all_orders(ticker)
            print(f"No position for {ticker}. Exiting monitor.")
            break

        quantity = float(position.qty)
        current_price = float(position.current_price)
        buy_price = float(position.avg_entry_price)

        rsi, _, df = rsim.rsi_base(ticker, interval = "1m", time = "5d")
        current_rsi = rsi[-1]

        if not trailing_stop_active:
            if current_rsi > 70 and current_price > buy_price:
                trailing_stop_active = True
                highest_price = current_price
                print(f"RSI > 70 ({current_rsi:.2f}). Trailing stop activated for {ticker}.")
            else:
                print(f"Waiting for RSI to exceed 70. Current RSI: {current_rsi:.2f}")
                tm.sleep(30)
                continue

        # Update highest price seen if trailing stop is active
        highest_price = max(highest_price, current_price)

        # Calculate trailing stop price
        stop_price = highest_price * (1 - trailing_percent)

        if current_price <= stop_price:
            close_all_orders(ticker)
            order = api.submit_order(
                symbol=ticker,
                qty=quantity,
                side='sell',
                type='market',
                time_in_force='gtc',
            )
            print(f"{ticker} has been sold!!! Order ID: {order.id}")
            print(f"Trailing stop triggered. Highest: ${highest_price:.2f}, Stop: ${stop_price:.2f}")
            break  # Exit the loop after selling

        print(f"Stock: {ticker}, Current: ${current_price:.2f}, Highest: ${highest_price:.2f}, Stop: ${stop_price:.2f}, RSI: {current_rsi:.2f}")
        tm.sleep(5)






def run_ma(ticker, graph = False): 
    try:
        ma_l, _, cnvrg_l = rsim.MA(ticker, 
                                    graph, 
                                    input_interval = "1m", 
                                    input_period = "5d",
                                    span1 = 50,
                                    span2 = 200,
                                    #standardize= True
                                    )
        ma_s, _, cnvrg_s = rsim.MA(ticker, 
                                    graph, 
                                    input_interval = "1m", 
                                    input_period = "5d",
                                    span1 = 20,
                                    span2 = 50
                                    )
        print(ma_l, ma_s, cnvrg_l, cnvrg_s) 
    except Exception as e:
        ma_l = "None"
        ma_s = "None"
        cnvrg_l = True
        cnvrg_s = True
        print("MA NOT WORK", e)
    return ma_l, ma_s, cnvrg_l, cnvrg_s


def close_shop():
    positions = api.list_positions()
    for position in positions:
        ticker = position.symbol
        qty = position.qty
        
        # Submit a market order to sell the position
        api.submit_order(
            symbol=ticker,
            qty=qty,
            side='sell',
            type='market',
            time_in_force='gtc'
        )
        orders = api.list_orders(status='open')

        for order in orders:
            order_id = order.id
            
            # Cancel the open order
            api.cancel_order(order_id)
        
        print(f"Closed for the day!")

def run():
    open_positions, num_position = get_open_positions()
    max_positions = 5
    with concurrent.futures.ThreadPoolExecutor() as executor:
        
            while True:
                while datetime.now().time() > time(10,00) and datetime.now().time() < time(14,00):
                    open_positions, num_position = get_open_positions()
                    futures = {}
                    futures_positions = {}
                    print(f"Outer loop, num = {num_position}")
                    # Runs results out of loop to make process faster
                    
                    while num_position >= max_positions:
                        for ticker in open_positions:
                            if ticker not in futures_positions:
                                futures_p = executor.submit(monitor_position, ticker)
                                futures_positions[ticker] = futures_p
                        open_positions, num_position = get_open_positions()
                        print(f"Waiting for sell signal. Position # = {num_position}")
                        tm.sleep(30)
                    # If time is greater than 1:50
                    if datetime.now().time() > time(13,50):
                        close_shop()

                    # If time is less than 1:30  (13:30)
                    if datetime.now().time() < time(13,30):
                        # Runs when there are less than 10 positions
                        while num_position < max_positions:                
                            # Creates a two threads
                                # - one for each ticker's order (wait until filled)
                                # - one for portfolio to be monitored for the ticker
                            i = 0
                            open_positions, num_position = get_open_positions()

                            results = dt.find()
                            print("Results Finished, not sort")
                            results.sort(key=lambda x: x[3], reverse=True)
                            limit_results = results
                            print(f"resuiltsd (% gain, ticker, rsi, % win): {limit_results} ")

                            for entry in limit_results:
                                ticker = entry[1]
                                i += 1
                                print(entry[3], entry[2], ticker, i)
                                ma_l, ma_s, cnvrg_l, cnvrg_s = run_ma(ticker)
                                rsi, _, df = dtc.rsi_base(ticker, "1min", "today")
                                #macd = rsim.macd(ticker)
                                conditions = [
                                    ticker not in open_positions,
                                    len(futures) < max_positions,
                                    ticker not in futures,
                                    rsi[-1] > 50,
                                    ma_l == "BULL",
                                    cnvrg_l == False,
                                    ma_s == "BULL",
                                    cnvrg_s == False,
                                    #macd == "BULL"
                                    ]
                                
                                if all(conditions):
                                    future = executor.submit(process_entry, entry)
                                    futures[ticker] = future
                                    print(len(futures), "futures")
                                    executor.submit(monitor_position, ticker)
                                    tm.sleep(5)
                                    open_positions, num_position = get_open_positions()
                                    print(f"Inner loop, num = {num_position}")

                                if num_position > max_positions:
                                    break

                                if datetime.now().time() > time(13,30):
                                    break 
                        
                else:
                    print("waiting")
                    tm.sleep(600)
            
                        



            



            
    #if lose more than 1%, then sell
        
    #result[-1] --- 0 = % gain, 1 = ticker, 2 = rsi, 3 = win rate


    #moving averages next