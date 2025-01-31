from alpaca_trade_api.rest import REST, TimeFrame
import os
from datetime import datetime, time
import pandas as pd
import concurrent.futures
import time as tm

try:
    api = REST(
        key_id=os.getenv("APCA_API_KEY_ID"),
        secret_key=os.getenv("APCA_API_SECRET_KEY"),
        base_url="https://paper-api.alpaca.markets"
    )
    account = api.get_account()
except:
    print("API Environment not set up. Please refer to 'config.py' or 'README'.")

def run_volume_analysis(ticker):
    # Get VWAP data
    minute_bars = api.get_bars(ticker, TimeFrame.Minute, start=datetime.now().date(), end=datetime.now().date()).df
    minute_bars['vwap'] = (minute_bars['high'] + minute_bars['low'] + minute_bars['close']) / 3 * minute_bars['volume']
    minute_bars['vwap'] = minute_bars['vwap'].cumsum() / minute_bars['volume'].cumsum()
    
    # Volume Profile
    volume_profile = minute_bars.groupby(pd.cut(minute_bars['close'], bins=10))['volume'].sum()
    poc_price = volume_profile.idxmax().mid  # Point of Control
    
    # Market Profile (Value Area)
    value_area_volume = volume_profile.sum() * 0.70  # 70% value area
    cumsum = 0
    value_area_high = poc_price
    value_area_low = poc_price
    
    for price, volume in volume_profile.items():
        cumsum += volume
        if cumsum <= value_area_volume:
            value_area_low = min(value_area_low, price.left)
            value_area_high = max(value_area_high, price.right)
    
    current_price = minute_bars['close'].iloc[-1]
    vwap = minute_bars['vwap'].iloc[-1]
    volume_trend = minute_bars['volume'].tail(5).mean() > minute_bars['volume'].tail(20).mean()
    
    return {
        'vwap': vwap,
        'poc': poc_price,
        'va_high': value_area_high,
        'va_low': value_area_low,
        'current_price': current_price,
        'volume_trend': volume_trend
    }

def scan_for_setups(symbols):
    setups = []
    for symbol in symbols:
        try:
            analysis = run_volume_analysis(symbol)
            
            # Entry conditions:
            # 1. Price is above VWAP
            # 2. Price is near POC (within 0.2%)
            # 3. Price is inside Value Area
            # 4. Volume is increasing
            
            price = analysis['current_price']
            if (price > analysis['vwap'] and
                abs(price - analysis['poc']) / price < 0.002 and
                analysis['va_low'] <= price <= analysis['va_high'] and
                analysis['volume_trend']):
                
                setups.append(symbol)
                
        except Exception as e:
            continue
            
    return setups

def calculate_position_size(equity, current_price, risk_percent=0.02):
    risk_amount = equity * risk_percent
    return int(risk_amount / current_price)

def process_entry(ticker):
    try:
        vol_analysis = run_volume_analysis(ticker)
        current_price = vol_analysis['current_price']
        
        # Risk management
        equity = float(account.equity)
        quantity = calculate_position_size(equity, current_price)
        
        # 1% risk per trade with 1.5:1 reward/risk
        stop_loss_price = current_price * 0.99
        take_profit_price = current_price * (1 + (0.01 * 1.5))
        
        # Place bracket order
        buy_order = api.submit_order(
            symbol=ticker,
            qty=quantity,
            side='buy',
            type='market',
            order_class='bracket',
            take_profit={'limit_price': take_profit_price},
            stop_loss={'stop_price': stop_loss_price},
            time_in_force='gtc'
        )
        print(f"Order placed for {ticker}: Quantity={quantity}, Stop={stop_loss_price}, Target={take_profit_price}")
        
    except Exception as e:
        print(f"Error placing order for {ticker}: {e}")

def get_open_positions():
    positions = api.list_positions()
    return {position.symbol for position in positions}, len(positions)

def monitor_position(ticker):
    trailing_percent = 0.005  # 0.5% trailing stop
    highest_price = 0
    trailing_stop_active = False

    while True:
        try:
            position = api.get_position(ticker)
            if position is None:
                break

            current_price = float(position.current_price)
            buy_price = float(position.avg_entry_price)
            vol_analysis = run_volume_analysis(ticker)
            
            # Exit conditions:
            # 1. Price drops below VWAP
            # 2. Price moves outside Value Area
            # 3. Trailing stop hit
            
            if (current_price < vol_analysis['vwap'] or 
                current_price < vol_analysis['va_low'] or 
                current_price > vol_analysis['va_high']):
                api.submit_order(
                    symbol=ticker,
                    qty=position.qty,
                    side='sell',
                    type='market',
                    time_in_force='gtc'
                )
                print(f"Exiting {ticker} - Outside valid range")
                break
                
            if not trailing_stop_active and current_price > buy_price * 1.005:
                trailing_stop_active = True
                highest_price = current_price
            
            if trailing_stop_active:
                stop_price = highest_price * (1 - trailing_percent)
                highest_price = max(highest_price, current_price)
                
                if current_price <= stop_price:
                    api.submit_order(
                        symbol=ticker,
                        qty=position.qty,
                        side='sell',
                        type='market',
                        time_in_force='gtc'
                    )
                    print(f"Trailing stop triggered for {ticker}")
                    break
            
            print(f"{ticker} - Price: ${current_price:.2f}, VWAP: ${vol_analysis['vwap']:.2f}")
            tm.sleep(5)
            
        except Exception as e:
            print(f"Error monitoring {ticker}: {e}")
            tm.sleep(5)

def close_all_positions():
    positions = api.list_positions()
    for position in positions:
        api.submit_order(
            symbol=position.symbol,
            qty=position.qty,
            side='sell',
            type='market',
            time_in_force='gtc'
        )
    print("All positions closed")

def run():
    max_positions = 5
    universe = api.list_assets(status='active', asset_class='us_equity')
    tradeable_symbols = [asset.symbol for asset in universe if asset.tradable]
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        while True:
            current_time = datetime.now().time()
            
            if time(10,00) <= current_time <= time(15,30):
                open_positions, num_positions = get_open_positions()
                
                # Monitor existing positions
                for ticker in open_positions:
                    executor.submit(monitor_position, ticker)
                
                # Look for new setups if we have capacity
                if num_positions < max_positions and current_time < time(15,30):
                    setups = scan_for_setups(tradeable_symbols)
                    for ticker in setups[:max_positions - num_positions]:
                        if ticker not in open_positions:
                            executor.submit(process_entry, ticker)
                            tm.sleep(5)  # Space out orders
                
                # Close all positions near end of day
                if current_time > time(15,45):
                    close_all_positions()
                    tm.sleep(300)  # Wait 5 minutes before scanning again
            
            tm.sleep(60)  # Main loop interval

if __name__ == "__main__":
    run()