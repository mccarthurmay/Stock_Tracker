import yfinance as yf
import numpy as np
import pandas as pd
from data.ab_low_minute import ab_lowManager
ab_low = ab_lowManager()

def calculate_rsi_prices(ticker, period=14, target_rsis=[30, 70]):
    # Fetch data
    end_date = pd.Timestamp.now()
    start_date = end_date - pd.Timedelta(days=5)
    df = yf.download(ticker, start=start_date, end=end_date, interval="1m")
    
    # Calculate RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    current_rsi = rsi.iloc[-1]
    current_price = df['Close'].iloc[-1]
    
    results = {'current_rsi': current_rsi, 'current_price': current_price}
    
    for target_rsi in target_rsis:
        target_rs = (100 / (100 - target_rsi) - 1)
        
        if target_rsi > current_rsi:  # Price needs to go up
            required_gain = target_rs * loss.iloc[-1] - gain.iloc[-1]
            price_change = required_gain * period
        else:  # Price needs to go down
            required_loss = gain.iloc[-1] / target_rs - loss.iloc[-1]
            price_change = -required_loss * period
        
        target_price = current_price + price_change
        results[f'price_at_rsi_{target_rsi}'] = target_price
    
    return results
def main_t(ticker, range = True):
# Example usage:
  # Replace with your desired ticker
    
    rsi_info = calculate_rsi_prices(ticker)
    


    
    if range == True:
        print(f"Current RSI: {rsi_info['current_rsi']:.2f}")
        print(f"Current Price: ${rsi_info['current_price']:.2f}")
        print(f"Estimated price at RSI 30: ${rsi_info['price_at_rsi_30']:.2f}")
        print(f"Estimated price at RSI 70: ${rsi_info['price_at_rsi_70']:.2f}")

        rsi1= input("range: ")
        rsi2= input("range: ")
        rsi_range = [(int(rsi1), int(rsi2))]
        stop = ab_low.limit(ticker, rsi_range)
        stop_p = 1 - stop / 100
        
        print(f"Stop Price: ${rsi_info['current_price']*(stop_p)}")
        print(f"Sell Price: ${rsi_info['price_at_rsi_70']:.2f}")
        
    else:
        return rsi_info['current_rsi'], ticker
    

    
def find():
    with open("./storage/ticker_lists/safe_tickers.txt", "r") as stock_file:
        stock_list = stock_file.read().split('\n')
    full = []
    for ticker in stock_list[:20]:
        try:
            rsi, ticker = main_t(ticker, range = False)
            full.append((round(rsi, 2), ticker))
        except:
            pass
    print(sorted(full))
