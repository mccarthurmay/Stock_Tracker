from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca_trade_api.rest import REST, TimeFrame
import os
from config import *
from data.day_trade import DTManager
import time as tm
import yfinance as yf
import concurrent.futures
import keyboard
from queue import Queue
dt = DTManager()



        
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
    buy_stop = current_price * 1.001
    equity = float(account.equity)
    quantity = round((float(equity)/10) / current_price, 0) - 1
    print(quantity)
    stp = round(stop,2)
    lmt = round(limit,2)
    stp_l = round(stop_l,2)

    #Buy order
    buy_order = api.submit_order(   # buy
        symbol = ticker,
        qty = quantity,
        side = 'buy',
        type = 'market',
        time_in_force = 'gtc',
        order_class = 'bracket',
        take_profit={
                #'stop_price': stp,
                'limit_price': stp
            },
        stop_loss={'stop_price': stp_l}
        ) 

    #Check if order was filled
    order_filled = False       # check if this is needed
    print(f"Waiting for {ticker} to be filled.")
    while not order_filled:
        order = api.get_order(buy_order.id)
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
    return {position.symbol for position in positions}

# Close orders once sold
def close_all_orders(ticker):
    orders = api.list_orders(status='open', symbols=[ticker])
    for order in orders:
        try:
            api.cancel_order(order.id)
        except Exception as e:
            print(f"Error cancelling order for {ticker}: {str(e)}")

def monitor_position(ticker, position_queue):
    while True:
        try:
            # Test if position exists
            position = api.get_position(ticker)
            # If position dne, close all orders for ticker, add to queue
            if position is None:
                close_all_orders(ticker)
                position_queue.put(ticker)
                break #runs until orders closed
        #Error handling
        except Exception as e:
            if 'position does not exist' in str(e).lower():
                close_all_orders(ticker)
                position_queue.put(ticker)
                break
            else:
                print(f"Error monitoring position for {ticker}: {str(e)}")
        tm.sleep(5)

def run():
    open_positions = get_open_positions()
    max_positions = 10
    position_queue = Queue()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_positions) as executor:
        futures = {}

        while True:
            # Runs when there are less than 10 positions
            while len(futures) < max_positions:
                # Runs results each time to make sure data is up to date
                results = dt.find()  # Prevent 'unlisted' error
                results.sort(key=lambda x: x[3], reverse=True)
                print(results)
                # Creates a two threads
                    # - one for each ticker's order (wait until filled)
                    # - one for portfolio to be monitored for the ticker (if )
                for entry in results:
                    ticker = entry[1]
                    if ticker not in open_positions and ticker not in futures:
                        future = executor.submit(process_entry, entry)
                        futures[ticker] = future
                        executor.submit(monitor_position, ticker, position_queue)
                        break
            
            # Runs when portfolio is full
                # - Goes through queue and removes depreciated tickers from all threads
            closed_position = position_queue.get()
            if closed_position in futures:
                del futures[closed_position]
            if closed_position in open_positions:
                open_positions.remove(closed_position)

            # Remove completed futures
            completed_futures = [ticker for ticker, future in futures.items() if future.done()]
            for ticker in completed_futures:
                del futures[ticker]
                if future.exception() is None:
                    open_positions.add(ticker)

            tm.sleep(1)
        



        





            

        #print (tick[0])

    
#result[-1] --- 0 = % gain, 1 = ticker, 2 = rsi, 3 = win rate


#take the top 10 most earning ones and buy 
    # keep top 10 in list
    # if 1 sells, redo "find" and look for the highest that is not in list




#constantly update to see if a sell occurs

# 1. run 'find'



# 2. get top 10 from "find"