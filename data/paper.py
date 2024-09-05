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
    stp_l = round(stop_l,2) # lower confidence interval of decrease increase range
    #stp_l = round((current_price * .99),2) #trading based on win rate
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
    while True:
        try:
            # Test if position exists
            position = api.get_position(ticker)
            ###GRAB RSI, if RSI > 70, sell
            quantity = position.qty
            rsi, _, df = dtc.rsi_base(ticker, "1min", "2024-08-29")
            #print(ticker, rsi[-1])
            if rsi[-1] > 70:
                close_all_orders(ticker)
                order = api.submit_order(   # buy
                symbol = ticker,
                qty = quantity,
                side = 'sell',
                type = 'market',
                time_in_force = 'gtc',
                )
                print(f"{ticker} has been sold!!! Order ID: {order.id}")
        
            #else:
            #    tm.sleep(30)
            tm.sleep(30)
            # If position dne, close all orders for ticker, add to queue
            if position is None:
                close_all_orders(ticker)
                break #runs until orders closed
                
        
        #Error handling
        except Exception as e:
            if 'position does not exist' in str(e).lower():
                close_all_orders(ticker)
                break
            else:
                print(f"Error monitoring position for {ticker}: {str(e)}")
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




def run():
    open_positions, num_position = get_open_positions()
    max_positions = 5

    with concurrent.futures.ThreadPoolExecutor() as executor:

        while True:
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
                    conditions = [
                        ticker not in open_positions,
                        len(futures) < max_positions,
                        ticker not in futures,
                        rsi[-1] < 45,
                        ma_l == "BULL",
                        cnvrg_l == False,
                        ma_s == "BULL",
                        cnvrg_s == False
                        ]
                    
                    if all(conditions):
                        run_ma(ticker, graph = True )
                        future = executor.submit(process_entry, entry)
                        futures[ticker] = future
                        print(len(futures), "futures")
                        executor.submit(monitor_position, ticker)
                        tm.sleep(5)
                        open_positions, num_position = get_open_positions()
                        print(f"Inner loop, num = {num_position}")

                    if num_position > max_positions:
                        break
                    



        



        
#if lose more than 1%, then sell
    
#result[-1] --- 0 = % gain, 1 = ticker, 2 = rsi, 3 = win rate


#moving averages next