import pandas as pd
import numpy as np
from typing import Dict, Callable, List
from scipy import stats
import itertools
import warnings
import time
from datetime import datetime
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import concurrent.futures
warnings.filterwarnings('ignore')

class DataPreprocessor:
    @staticmethod
    def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
        """Prepare and clean the data"""
        df = df.copy()
        df['Date'] = pd.to_datetime(df['Date'])
        
        # Calculate basic indicators
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # Moving Averages
        df['SMA_5'] = df['Close'].rolling(window=5).mean()
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['EMA_5'] = df['Close'].ewm(span=5, adjust=False).mean()
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        
        # MACD
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        # Bollinger Bands
        df['BB_middle'] = df['Close'].rolling(window=20).mean()
        df['BB_std'] = df['Close'].rolling(window=20).std()
        df['BB_upper'] = df['BB_middle'] + (df['BB_std'] * 2)
        df['BB_lower'] = df['BB_middle'] - (df['BB_std'] * 2)
        
        # Fill NaN values
        df = df.fillna(method='bfill').fillna(method='ffill')
        
        return df

class TradingSimulator:
    def __init__(self, data: pd.DataFrame, initial_capital: float = 10000):
        self.data = data
        self.initial_capital = initial_capital
        self.buy_price = 0  # Add this line to initialize buy_price
        self.reset()
        
    def reset(self):
        """Reset the simulator state"""
        self.position = 0  # -1: short, 0: neutral, 1: long
        self.cash = self.initial_capital
        self.trades = []
        self.equity_curve = []
        
    def run_backtest(self, strategy_funcs: List[Callable], strategy_params: List[Dict] = None):
        """Run backtest with multiple strategies"""
        self.reset()
        for i in range(len(self.data)):
            current_data = self.data.iloc[:i+1].copy()
            current_data['buy_price'] = self.buy_price  # Add this line to include buy_price in current_data
            if i < 26:  # Skip first few candles for indicator calculation
                continue
            
            # Get signals from all strategies
            signals = []
            for j, strategy_func in enumerate(strategy_funcs):
                params = strategy_params[j] if strategy_params else None
                signal = strategy_func(current_data, params) if params else strategy_func(current_data)
                signals.append(signal)
            
            # Combine signals (requires all strategies to agree)
            combined_signal = self._combine_signals(signals)
            
            self._execute_trade(combined_signal, self.data.iloc[i])
            current_equity = self.cash + (self.position * self.data.iloc[i]['Close'])
            self.equity_curve.append({
                'timestamp': self.data.index[i],
                'equity': current_equity,
                'position': self.position
            })
    
    def _combine_signals(self, signals: List[int]) -> int:
        """Combine signals from multiple strategies"""
        if all(s == 1 for s in signals):  # All strategies agree on buy
            return 1
        elif all(s == -1 for s in signals):  # All strategies agree on sell
            return -1
        return 0  # No consensus
    
    def _execute_trade(self, signal, current_bar):
        """Execute trading signal"""
        price = current_bar['Close']
        if signal == 1 and self.position <= 0:  # Buy signal
            self.position = 1
            self.buy_price = price
            self.cash -= price
            self.trades.append({
                'timestamp': current_bar.name,
                'type': 'buy',
                'price': price
            })
        elif (signal == -1 and self.position >= 0 and price > self.buy_price) or \
            (self.position > 0 and price < self.buy_price * 0.998):  # Sell signal or stop loss
            self.position = -1
            self.cash += price
            trade_type = 'sell' if price > self.buy_price else 'stop_loss'
            self.trades.append({
                'timestamp': current_bar.name,
                'type': trade_type,
                'price': price
            })
        
    def get_results(self) -> Dict:
        """Calculate and return detailed backtest results"""
        if not self.equity_curve:
            return None
        
        equity_df = pd.DataFrame(self.equity_curve)
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()
        
        # Calculate returns
        equity_df['returns'] = equity_df['equity'].pct_change()
        returns = equity_df['returns'].dropna()
        
        # Calculate metrics
        total_return = ((equity_df['equity'].iloc[-1] - self.initial_capital) / 
                    self.initial_capital)
        volatility = returns.std() * np.sqrt(252)  # Annualized volatility
        sharpe_ratio = (total_return / volatility) if volatility != 0 else 0
        max_drawdown = self._calculate_max_drawdown(equity_df['equity'])
        win_rate = self._calculate_win_rate()
        
        # Calculate number of stop loss trades
        stop_loss_trades = len(trades_df[trades_df['type'] == 'stop_loss'])
        
        results = {
            'initial_capital': self.initial_capital,
            'final_equity': equity_df['equity'].iloc[-1],
            'total_return': total_return * 100,  # Convert to percentage
            'sharpe_ratio': sharpe_ratio,
            'volatility': volatility * 100,  # Convert to percentage
            'max_drawdown': max_drawdown * 100,  # Convert to percentage
            'num_trades': len(self.trades),
            'win_rate': win_rate * 100,  # Convert to percentage
            'stop_loss_trades': stop_loss_trades,
            'equity_curve': equity_df
        }
        
        return results
        
    def _calculate_max_drawdown(self, equity_series):
        """Calculate maximum drawdown from peak"""
        peak = equity_series.expanding(min_periods=1).max()
        drawdown = (equity_series - peak) / peak
        return abs(drawdown.min())
    
    def _calculate_win_rate(self):
        """Calculate percentage of winning trades"""
        if not self.trades:
            return 0
            
        trades_df = pd.DataFrame(self.trades)
        if len(trades_df) < 2:
            return 0
        
        profits = []
        for i in range(1, len(trades_df)):
            if trades_df.iloc[i-1]['type'] == 'buy':
                profit = trades_df.iloc[i]['price'] - trades_df.iloc[i-1]['price']
            else:
                profit = trades_df.iloc[i-1]['price'] - trades_df.iloc[i]['price']
            profits.append(profit)
        
        return sum(1 for p in profits if p > 0) / len(profits)

def rsi_strategy(data: pd.DataFrame, params: Dict = None) -> int:
    """RSI strategy"""
    if params is None:
        params = {'oversold': 30, 'overbought': 70}
    
    current_price = data['Close'].iloc[-1]
    current_rsi = data['RSI'].iloc[-1]
    buy_price = data['buy_price'].iloc[-1] if 'buy_price' in data.columns else 0
    
    if pd.isna(current_rsi):
        return 0
    
    if current_rsi < params['oversold']:
        return 1  # Buy signal
    elif current_rsi > params['overbought'] and current_price > buy_price:
        return -1  # Sell signal
    return 0

def macd_strategy(data: pd.DataFrame, params: Dict = None) -> int:
    """MACD crossover strategy"""
    if params is None:
        params = {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}
    
    if len(data) < 2:
        return 0
    
    current_macd = data['MACD'].iloc[-1]
    current_signal = data['Signal'].iloc[-1]
    prev_macd = data['MACD'].iloc[-2]
    prev_signal = data['Signal'].iloc[-2]
    
    if current_macd > current_signal and prev_macd <= prev_signal:
        return 1  # Buy signal
    elif current_macd < current_signal and prev_macd >= prev_signal:
        return -1  # Sell signal
    return 0

def sma_crossover_strategy(data: pd.DataFrame, params: Dict = None) -> int:
    """SMA crossover strategy"""
    if params is None:
        params = {'fast_period': 5, 'slow_period': 20}
    
    fast_sma = data['Close'].rolling(window=params['fast_period']).mean()
    slow_sma = data['Close'].rolling(window=params['slow_period']).mean()
    
    if len(data) < 2:
        return 0
    
    current_fast = fast_sma.iloc[-1]
    current_slow = slow_sma.iloc[-1]
    prev_fast = fast_sma.iloc[-2]
    prev_slow = slow_sma.iloc[-2]
    
    if current_fast > current_slow and prev_fast <= prev_slow:
        return 1  # Buy signal
    elif current_fast < current_slow and prev_fast >= prev_slow:
        return -1  # Sell signal
    return 0

def bollinger_bands_strategy(data: pd.DataFrame, params: Dict = None) -> int:
    """Bollinger Bands strategy"""
    if params is None:
        params = {'period': 20, 'std_dev': 2.0}
    
    period = params['period']
    std_dev = params['std_dev']
    
    middle = data['Close'].rolling(window=period).mean()
    std = data['Close'].rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    current_price = data['Close'].iloc[-1]
    
    if current_price < lower.iloc[-1]:
        return 1  # Buy signal
    elif current_price > upper.iloc[-1]:
        return -1  # Sell signal
    return 0

class StrategyTester:
    def __init__(self, data: pd.DataFrame):
        self.data = data
        self.results_list = []
        self.strategy_params = {
            'RSI': {
                'func': rsi_strategy,
                'params': {
                    'oversold': [30, 35],
                    'overbought': [65, 70]
                }
            },
            'MACD': {
                'func': macd_strategy,
                'params': {
                    'fast_period': [12, 15],
                    'slow_period': [26, 30],
                    'signal_period': [9]
                }
            },
            'SMA': {
                'func': sma_crossover_strategy,
                'params': {
                    'fast_period': [5, 8],
                    'slow_period': [20, 25]
                }
            },
            'BB': {
                'func': bollinger_bands_strategy,
                'params': {
                    'period': [20],
                    'std_dev': [2.0]
                }
            }
        }
        self.num_cores = max(1, mp.cpu_count() - 1) # Leave one core free
    
    def calculate_total_combinations(self, min_strategies, max_strategies):
        """Calculate total number of combinations to be tested"""
        total_combinations = 0
        strategy_names = list(self.strategy_params.keys())
        
        for num_strategies in range(min_strategies, max_strategies + 1):
            strategy_combinations = list(itertools.combinations(strategy_names, num_strategies))
            
            for strat_combo in strategy_combinations:
                # Calculate parameter combinations for this strategy combination
                param_counts = []
                for strat_name in strat_combo:
                    params = self.strategy_params[strat_name]['params']
                    param_count = 1
                    for param_values in params.values():
                        param_count *= len(param_values)
                    param_counts.append(param_count)
                
                # Total combinations for this strategy set is product of parameter combinations
                combo_count = np.prod(param_counts)
                total_combinations += combo_count
        
        return total_combinations
    
    def _test_single_combination(self, combo_data):
        """Test a single combination of strategies and parameters"""
        strat_combo, param_combo = combo_data
        try:
            strategy_funcs = [self.strategy_params[name]['func'] for name in strat_combo]
            simulator = TradingSimulator(self.data)
            simulator.run_backtest(strategy_funcs, list(param_combo))
            strategy_results = simulator.get_results()
            
            if strategy_results:
                strategy_results['strategies'] = ' + '.join(strat_combo)
                strategy_results['parameters'] = str(dict(zip(strat_combo, param_combo)))
                return strategy_results
            
        except Exception as e:
            print(f"Error testing combination {strat_combo}: {str(e)}")
        return None
    
    def generate_combinations(self, min_strategies, max_strategies):
        """Generate all possible combinations of strategies and parameters"""
        all_combinations = []
        strategy_names = list(self.strategy_params.keys())
        
        for num_strategies in range(min_strategies, max_strategies + 1):
            strategy_combinations = list(itertools.combinations(strategy_names, num_strategies))
            
            for strat_combo in strategy_combinations:
                param_lists = []
                for strat_name in strat_combo:
                    params = self.strategy_params[strat_name]['params']
                    param_combinations = [dict(zip(params.keys(), v)) 
                                       for v in itertools.product(*params.values())]
                    param_lists.append(param_combinations)
                
                for param_combo in itertools.product(*param_lists):
                    all_combinations.append((strat_combo, param_combo))
        
        return all_combinations
    
    def estimate_runtime(self, min_strategies, max_strategies, sample_size=10):
        """Estimate runtime using parallel processing"""
        print("Estimating runtime using parallel processing...")
        
        # Generate all combinations
        all_combinations = self.generate_combinations(min_strategies, max_strategies)
        total_combinations = len(all_combinations)
        
        # Select sample combinations
        sample_size = min(sample_size, total_combinations)
        sample_combinations = np.random.choice(range(total_combinations), 
                                            size=sample_size, 
                                            replace=False)
        sample_combos = [all_combinations[i] for i in sample_combinations]
        
        # Run sample combinations in parallel
        start_time = time.time()
        with ProcessPoolExecutor(max_workers=self.num_cores) as executor:
            results = list(executor.map(self._test_single_combination, sample_combos))
        
        elapsed_time = time.time() - start_time
        avg_time_per_combo = elapsed_time / sample_size
        
        # Estimate total time considering parallel processing
        estimated_total_time = (avg_time_per_combo * total_combinations) / self.num_cores
        
        return total_combinations, estimated_total_time
    


    def test_strategy_combinations(self, min_strategies=2, max_strategies=2) -> pd.DataFrame:
        """Test combinations of different strategies using parallel processing"""
        # Calculate and display estimates
        total_combinations, estimated_time = self.estimate_runtime(min_strategies, max_strategies)
        
        print("\nTesting Summary:")
        print(f"Using {self.num_cores} CPU cores")
        print(f"Total combinations to test: {total_combinations:,}")
        print(f"Estimated runtime: {estimated_time/60:.1f} minutes ({estimated_time/3600:.1f} hours)")
        print(f"Estimated completion time: {pd.Timestamp.now() + pd.Timedelta(seconds=estimated_time)}")
        
        proceed = input("\nProceed with testing? (y/n): ")
        if proceed.lower() != 'y':
            return pd.DataFrame()
        
        # Generate all combinations
        all_combinations = self.generate_combinations(min_strategies, max_strategies)
        combinations_tested = 0
        start_time = time.time()
        
        # Process combinations in parallel
        try:
            with ProcessPoolExecutor(max_workers=self.num_cores) as executor:
                futures = []
                batch_size = max(100, total_combinations // 100)  # Process in batches
                
                for i in range(0, len(all_combinations), batch_size):
                    batch = all_combinations[i:i + batch_size]
                    for combo in batch:
                        futures.append(executor.submit(self._test_single_combination, combo))
                
                # Process results as they complete
                for future in concurrent.futures.as_completed(futures):
                    combinations_tested += 1
                    result = future.result()
                    
                    if result:
                        self.results_list.append(result)
                        
                        # Display progress
                        if combinations_tested % 10 == 0:
                            elapsed_time = time.time() - start_time
                            progress = combinations_tested / total_combinations
                            estimated_remaining = (elapsed_time / combinations_tested) * (total_combinations - combinations_tested)
                            
                            print(f"\rProgress: {combinations_tested}/{total_combinations} "
                                  f"({progress*100:.1f}%) - "
                                  f"Estimated remaining time: {estimated_remaining/60:.1f} minutes", 
                                  end='')
                        
                        # Save intermediate results periodically
                        if combinations_tested % 50 == 0:
                            self.save_current_results()
                            self.display_current_best()
        
        except KeyboardInterrupt:
            print("\nInterrupted by user. Saving current results...")
        except Exception as e:
            print(f"\nError in parallel processing: {e}")
        
        return self.get_results_dataframe()
        
    def save_current_results(self):
        """Save current results to CSV"""
        if self.results_list:
            df = pd.DataFrame(self.results_list)
            df.to_csv('intermediate_results.csv', index=False)
    
    def get_results_dataframe(self) -> pd.DataFrame:
        """Convert results list to DataFrame and add statistical tests"""
        if not self.results_list:
            return pd.DataFrame()
        
        results_df = pd.DataFrame(self.results_list)
        metrics = [
            'parameters',
            'total_return',
            'sharpe_ratio',
            'max_drawdown',
            'num_trades',
            'win_rate'
        ]
        
        comparison_df = results_df[['strategies'] + metrics].set_index(['strategies', 'parameters'])
        
        # Add statistical significance tests
        benchmark_returns = self.data['Close'].pct_change().dropna()
        for idx in comparison_df.index:
            strategy_data = results_df[
                (results_df['strategies'] == idx[0]) & 
                (results_df['parameters'] == idx[1])
            ].iloc[0]
            
            equity_curve = strategy_data['equity_curve']
            strategy_returns = equity_curve['equity'].pct_change().dropna()
            
            t_stat, p_value = stats.ttest_ind(strategy_returns, benchmark_returns)
            comparison_df.loc[idx, 't_statistic'] = t_stat
            comparison_df.loc[idx, 'p_value'] = p_value
        
        return comparison_df
    
    def display_current_best(self):
        """Display current best results"""
        if not self.results_list:
            print("No results yet")
            return
        
        df = pd.DataFrame(self.results_list)
        print("\nCurrent Top 3 by Returns:")
        top_return = df.nlargest(3, 'total_return')
        for _, row in top_return.iterrows():
            print(f"\nStrategy: {row['strategies']}")
            print(f"Parameters: {row['parameters']}")
            print(f"Total Return: {row['total_return']:.2f}%")
            print(f"Sharpe Ratio: {row['sharpe_ratio']:.2f}")

def main():
    print("Loading and preparing data...")
    data = pd.read_pickle('amzn_data3.pkl')
    preprocessor = DataPreprocessor()
    prepared_data = preprocessor.prepare_data(data)
    
    print("\nInitializing parallel strategy tester...")
    tester = StrategyTester(prepared_data)
    
    try:
        results = tester.test_strategy_combinations(min_strategies=2, max_strategies=3)
        
        if not results.empty:
            print("\nFinal Results Summary")
            print("=" * 80)
            
            print("\nTop 5 by Total Return:")
            top_by_return = results.sort_values('total_return', ascending=False).head(5)
            for idx, row in top_by_return.iterrows():
                print(f"\n{idx[0]}")
                print(f"Parameters: {idx[1]}")
                print(f"Return: {row['total_return']:.2f}%")
                print(f"Sharpe: {row['sharpe_ratio']:.2f}")
                print(f"Max Drawdown: {row['max_drawdown']:.2f}%")
                print(f"Win Rate: {row['win_rate']:.2f}%")
                print(f"Number of Trades: {row['num_trades']}")
                print(f"Statistical Significance (p-value): {row['p_value']:.4f}")
            
            print("\nTop 5 by Sharpe Ratio:")
            top_by_sharpe = results.sort_values('sharpe_ratio', ascending=False).head(5)
            for idx, row in top_by_sharpe.iterrows():
                print(f"\n{idx[0]}")
                print(f"Parameters: {idx[1]}")
                print(f"Sharpe: {row['sharpe_ratio']:.2f}")
                print(f"Return: {row['total_return']:.2f}%")
                print(f"Max Drawdown: {row['max_drawdown']:.2f}%")
                print(f"Win Rate: {row['win_rate']:.2f}%")
                print(f"Number of Trades: {row['num_trades']}")
                print(f"Statistical Significance (p-value): {row['p_value']:.4f}")
            
            # Save final results
            results.to_csv('final_results.csv')
            print("\nComplete results saved to 'final_results.csv'")
            
    except KeyboardInterrupt:
        print("\nTesting interrupted. Saving current results...")
        current_results = tester.get_results_dataframe()
        if not current_results.empty:
            current_results.to_csv('interrupted_results.csv')
            print("Partial results saved to 'interrupted_results.csv'")
    
    except Exception as e:
        print(f"\nError in main execution: {e}")
        print("Attempting to save partial results...")
        current_results = tester.get_results_dataframe()
        if not current_results.empty:
            current_results.to_csv('error_results.csv')
            print("Partial results saved to 'error_results.csv'")

if __name__ == "__main__":
    main()