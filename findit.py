import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict, Callable

class DataPreprocessor:
    @staticmethod
    def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
        """Prepare and clean the data"""
        df['Date'] = pd.to_datetime(df['Date'])
        df['RSI'] = df['RSI'].fillna(method='ffill')
        df['SMA_5'] = df['Close'].rolling(window=5).mean()
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['EMA_5'] = df['Close'].ewm(span=5, adjust=False).mean()
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        return df

class TradingSimulator:
    def __init__(self, data: pd.DataFrame, initial_capital: float = 10000):
        self.data = data
        self.initial_capital = initial_capital
        self.reset()
        
    def reset(self):
        """Reset the simulator state"""
        self.position = 0
        self.cash = self.initial_capital
        self.trades = []
        self.equity_curve = []
        
    def run_backtest(self, strategy_func: Callable, params: Dict = None):
        """Run backtest with given strategy"""
        self.reset()
        for i in range(len(self.data)):
            current_data = self.data.iloc[:i+1].copy()
            if i < 20:  # Skip first few candles for indicator calculation
                continue
            signal = strategy_func(current_data, params) if params else strategy_func(current_data)
            self._execute_trade(signal, self.data.iloc[i])
            current_equity = self.cash + (self.position * self.data.iloc[i]['Close'])
            self.equity_curve.append({
                'timestamp': self.data.index[i],
                'equity': current_equity,
                'position': self.position
            })
    
    def _execute_trade(self, signal, current_bar):
        price = current_bar['Close']
        if signal == 1 and self.position <= 0:  # Buy
            self.position = 1
            self.cash -= price
            self.trades.append({
                'timestamp': current_bar.name,
                'type': 'buy',
                'price': price,
                'rsi': current_bar['RSI']
            })
        elif signal == -1 and self.position >= 0:  # Sell
            self.position = -1
            self.cash += price
            self.trades.append({
                'timestamp': current_bar.name,
                'type': 'sell',
                'price': price,
                'rsi': current_bar['RSI']
            })
    
    def get_results(self) -> Dict:
        """Calculate and return backtest results"""
        if not self.equity_curve:
            return None
        equity_df = pd.DataFrame(self.equity_curve)
        trades_df = pd.DataFrame(self.trades)
        results = {
            'initial_capital': self.initial_capital,
            'final_equity': equity_df['equity'].iloc[-1],
            'return_pct': ((equity_df['equity'].iloc[-1] - self.initial_capital) / 
                          self.initial_capital * 100),
            'num_trades': len(self.trades),
            'equity_curve': equity_df
        }
        return results

# Strategy Definitions
def rsi_strategy(data: pd.DataFrame, params: Dict = None) -> int:
    if params is None:
        params = {'oversold': 30, 'overbought': 70}
    current_rsi = data['RSI'].iloc[-1]
    if pd.isna(current_rsi):
        return 0
    if current_rsi < params['oversold']:
        return 1  # Buy signal
    elif current_rsi > params['overbought']:
        return -1  # Sell signal
    return 0

def evaluate_rsi_combinations(data: pd.DataFrame) -> Dict:
    preprocessor = DataPreprocessor()
    prepared_data = preprocessor.prepare_data(data)
    sim = TradingSimulator(prepared_data)
    best_result = {'best_combination': None, 'best_return': -np.inf}
    for oversold in range(1, 55):
        for overbought in range(55, 70):
            params = {'oversold': oversold, 'overbought': overbought}
            sim.run_backtest(rsi_strategy, params)
            result = sim.get_results()
            if result['return_pct'] > best_result['best_return']:
                best_result = {'best_combination': params, 'best_return': result['return_pct']}
    return best_result

def process_file(file_path: str) -> Dict:
    data = pd.read_csv(file_path)
    return evaluate_rsi_combinations(data)

def main():
    files = ['data1.csv', 'data2.csv', 'data3.csv', 'data4.csv']
    with ProcessPoolExecutor() as executor:
        results = list(executor.map(process_file, files))
    
    # Output results
    for i, result in enumerate(results):
        print(f"Results for {files[i]}:")
        print(f"Best RSI combination: {result['best_combination']}")
        print(f"Best return: {result['best_return']}%")

if __name__ == "__main__":
    main()
Best RSI combination: {'oversold': 23, 'overbought': 66}
Best return: 0.24330000000001745%
Results for data2.csv:
Best RSI combination: {'oversold': 29, 'overbought': 69}
Best return: 1.6714499999997134%
Results for data3.csv:
Best RSI combination: {'oversold': 26, 'overbought': 62}
Best return: 1.3188499999999839%
Results for data4.csv:
Best RSI combination: {'oversold': 32, 'overbought': 69}