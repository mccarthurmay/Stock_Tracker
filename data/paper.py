from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca_trade_api.rest import REST, TimeFrame
import os
from config import *
from data.day_trade import DTManager, DTCalc
import time as tm
import yfinance as yf
import concurrent.futures
import keyboard
from queue import Queue
dt = DTManager()
dtc = DTCalc()



        
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
    quantity = round((float(equity)/10) / current_price, 0) - 1
    print(quantity)
    stp = round(stop,2)
    #stp = round((current_price * 1.002), 2)
    lmt = round(limit,2)
    #stp_l = round(stop_l,2)
    stp_l = round((current_price * .99),2)
    print(current_price)
    print((stp_l - current_price) / current_price, "stpl")
    #Buy order
    buy_order = api.submit_order(   # buy
        symbol = ticker,
        qty = quantity,
        side = 'buy',
        type = 'market',
        time_in_force = 'gtc',
  #WAS CAUSING PROBLEMS PREVIOUSLY
        ) 
    stop_order = api.submit_order(
        symbol=ticker,
        qty= quantity,
        side='sell',
        type='stop',
        time_in_force='gtc',
        stop_price= stp_l
        )
    #Check if order was filled
    order_filled = False       # check if this is needed
    print(f"Waiting for {ticker} to be filled.")
    while not order_filled:
        order = api.get_order(buy_order.id)
        stop_order = api.get_order(stop_order.id)
        if order.status == 'filled' and stop_order.status == 'filled':
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
            rsi, _, df = dtc.rsi_base(ticker, "7d", "1m")
            print(ticker, rsi[-1])
            if rsi[-1] > 70:
                order = api.submit_order(   # buy
                symbol = ticker,
                qty = quantity,
                side = 'sell',
                type = 'market',
                time_in_force = 'gtc',
                )
                print(f"{ticker} has been sold!!! Order ID: {order.id}")
            else:
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

def run():
    open_positions, num_position = get_open_positions()
    max_positions = 10 

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

            if num_position < max_positions:
                results = dt.find()
                results.sort(key=lambda x: x[1], reverse=True)
                limit_results = results[30:]
                print(limit_results)


            # Runs when there are less than 10 positions
            while num_position < max_positions:                
                # Creates a two threads
                    # - one for each ticker's order (wait until filled)
                    # - one for portfolio to be monitored for the ticker
                i = 0
                open_positions, num_position = get_open_positions()


                for entry in limit_results:
                    ticker = entry[1]
                    i += 1
                    print(entry[3], entry[2], ticker, i)
                    if ticker not in open_positions and len(futures) < max_positions and ticker not in futures:
                        future = executor.submit(process_entry, entry)
                        futures[ticker] = future
                        print(len(futures), "futures")
                        executor.submit(monitor_position, ticker)
                        tm.sleep(5)
                        open_positions, num_position = get_open_positions()
                        print(f"Inner loop, num = {num_position}")
                        break




        



        
#if lose more than 1%, then sell
    
#result[-1] --- 0 = % gain, 1 = ticker, 2 = rsi, 3 = win rate


#moving averages next