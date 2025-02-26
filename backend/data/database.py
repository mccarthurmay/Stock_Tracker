import os
import pickle
from data.analysis import AnalysisManager
from tkinter import messagebox, simpledialog
from datetime import datetime, timedelta
import yfinance as yf

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import math
from typing import List, Dict, Any, Tuple
import time
from threading import Lock
from datetime import datetime, timedelta

class ProgressTracker:
    def __init__(self, total_tickers: int):
        self.total = total_tickers
        self.completed = 0
        self.started = 0
        self.lock = Lock()
        self.start_time = datetime.now()
        self.errors = []
        self.current_tickers = {}  # Track currently processing tickers by worker
        
    def ticker_started(self, ticker: str, worker_id: int):
        with self.lock:
            self.started += 1
            self.current_tickers[worker_id] = ticker
            self._print_progress()
    
    def ticker_completed(self, ticker: str, worker_id: int, success: bool):
        with self.lock:
            self.completed += 1
            if not success:
                self.errors.append(ticker)
            if worker_id in self.current_tickers:
                del self.current_tickers[worker_id]
            self._print_progress()
    
    def _print_progress(self):
        # Calculate progress percentage
        progress = (self.completed / self.total) * 100
        
        # Calculate time elapsed and estimate remaining
        elapsed = datetime.now() - self.start_time
        if self.completed > 0:
            time_per_ticker = elapsed / self.completed
            remaining_tickers = self.total - self.completed
            est_remaining = time_per_ticker * remaining_tickers
        else:
            est_remaining = timedelta(0)
        
        # Clear previous lines
        print('\033[F\033[K' * (4 + len(self.current_tickers)), end='')
        
        # Print progress bar and stats
        bar_length = 30
        filled = int(progress * bar_length / 100)
        bar = '█' * filled + '-' * (bar_length - filled)
        
        print(f"\nProgress: [{bar}] {progress:.1f}%")
        print(f"Completed: {self.completed}/{self.total} tickers")
        print(f"Time: {str(elapsed).split('.')[0]} elapsed, ~{str(est_remaining).split('.')[0]} remaining")
        
        # Print current worker status
        for worker_id, ticker in self.current_tickers.items():
            print(f"Worker {worker_id}: Processing {ticker}")

class WorkerPoolManager:
    def __init__(self, data_manager, api_limit_per_minute: int = 150):
        self.data_manager = data_manager
        self.api_limit_per_minute = api_limit_per_minute
        self.calls_per_ticker = 4
        
    def analyze_workload(self, tickers: List[str]) -> Tuple[int, int, int]:
        """
        Analyzes workload and determines optimal worker count based on cache status and API limits
        
        Args:
            tickers: List of ticker symbols to process
            
        Returns:
            Tuple of (cached_tickers, total_api_calls, optimal_workers)
        """
        # Count cached tickers
        cached_tickers = 0
        for ticker in tickers:
            cache_key_daily = f"{ticker}_1D_5"
            cache_key_minute = f"{ticker}_1Min_5"
            if (hasattr(self.data_manager, '_cache') and 
                (cache_key_daily in self.data_manager._cache or 
                cache_key_minute in self.data_manager._cache)):
                cached_tickers += 1
        
        # Calculate API calls needed
        new_tickers = len(tickers) - cached_tickers
        total_api_calls = new_tickers * self.calls_per_ticker
        
        try:
            cpu_count = len(os.sched_getaffinity(0))
        except AttributeError:
            cpu_count = os.cpu_count() or 4
        
        # Calculate optimal worker distribution
        potential_workers = min(cpu_count * 2, len(tickers), 8)
        
        # Calculate calls per worker per minute based on API limit
        if potential_workers > 0:
            calls_per_worker_per_minute = self.api_limit_per_minute / potential_workers
        else:
            calls_per_worker_per_minute = self.api_limit_per_minute
        
        # Adjust worker count if needed to respect API limit
        api_workers = math.ceil(self.api_limit_per_minute / calls_per_worker_per_minute)
        
        # Final worker count calculation
        optimal_workers = min(
            api_workers,
            potential_workers
        )
        
        # Calculate actual calls per worker for logging
        actual_calls_per_worker = (self.api_limit_per_minute / optimal_workers 
                                if optimal_workers > 0 else 0)
        
        print(f"\nWorkload Analysis:")
        print(f"API Limit: {self.api_limit_per_minute} calls/minute")
        print(f"Workers: {optimal_workers}")
        print(f"Calls per worker: {actual_calls_per_worker:.1f} calls/minute")
        print(f"Total API calls needed: {total_api_calls}")
        print(f"Estimated minutes: {(total_api_calls / self.api_limit_per_minute):.1f}\n")
        
        return cached_tickers, total_api_calls, max(1, optimal_workers)

    def process_tickers(self, tickers: List[str], process_func) -> Dict[str, Any]:
        """Process tickers with progress tracking"""
        cached_tickers, total_api_calls, optimal_workers = self.analyze_workload(tickers)
        
        print("\nInitializing Processing:")
        print(f"Total tickers: {len(tickers)}")
        print(f"Cached tickers: {cached_tickers}")
        print(f"New API calls needed: {total_api_calls}")
        print(f"Workers: {optimal_workers}\n")
        
        # Initialize progress tracker
        progress = ProgressTracker(len(tickers))
        print("\n" * (optimal_workers + 4))  # Make space for progress display
        
        results = {}
        with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
            def wrapped_process(ticker, worker_id):
                progress.ticker_started(ticker, worker_id)
                try:
                    result = process_func(ticker)
                    progress.ticker_completed(ticker, worker_id, True)
                    return result
                except Exception as e:
                    print(f"\nError processing {ticker}: {e}")
                    progress.ticker_completed(ticker, worker_id, False)
                    return None
            
            # Submit tasks with worker IDs
            future_to_ticker = {
                executor.submit(wrapped_process, ticker, i % optimal_workers): ticker
                for i, ticker in enumerate(tickers)
            }
            
            # Collect results
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    results[ticker] = future.result()
                except Exception as e:
                    results[ticker] = None
        
        # Print final summary
        print("\nProcessing Complete!")
        if progress.errors:
            print(f"Errors occurred for: {', '.join(progress.errors)}")
        
        return results
    
class DBManager:
    def __init__(self):
        self.analysis = AnalysisManager()
        self.worker_pool = WorkerPoolManager(self.analysis.data_manager)

    def storeData(self, dbname: str, stock_list: List[str]) -> None:
        """Store data for multiple stocks with optimized worker pool"""
        try:
            db, dbfile = open_file(dbname)
        except FileNotFoundError:
            db = {}

        # Initialize empty entries
        for ticker in stock_list:
            db[ticker] = {}
        
        close_file(db, dbname)
        db, dbfile = open_file(dbname)
        
        def process_ticker_data(ticker):
            try:

                self.analysis.runall(ticker, db)
                return True
            except Exception as e:
                print(f"Removing {ticker}: {e}")
                if ticker in db:
                    del db[ticker]
                return False
            
        def process_ticker_portfolio(ticker):
            try:

                self.analysis.runall_sell(ticker, db)
                return True
            except Exception as e:
                print(f"Removing {ticker}: {e}")
                if ticker in db:
                    del db[ticker]
                return False

        # Process tickers with optimized worker pool
        if dbname.startswith('p_') or dbname.startswith('portfolio_') or dbname.startswith('portfolio'):

            results = self.worker_pool.process_tickers(
                tickers=list(db.keys()),
                process_func=process_ticker_portfolio
            )
        else:
            results = self.worker_pool.process_tickers(
                tickers=list(db.keys()),
                process_func=process_ticker_data
            )
        
        close_file(db, dbname)
        
        # Report statistics
        success_count = sum(1 for result in results.values() if result)
        print(f"Successfully processed {success_count} out of {len(stock_list)} tickers")


    #ADD TICKER
    def addData(self, ticker, dbname):
        try:
            db, dbfile = open_file(dbname)

            if ticker not in db:
                try:
                    if dbname.startswith('p_') or dbname.startswith('portfolio_') or dbname.startswith('portfolio') or dbname.equals('portfolio'):
                        price = self.analysis.data_manager.get_price(ticker)
                        self.analysis.runall_sell(ticker,db, price)
                    else:
                        self.analysis.runall(ticker, db)
                except Exception as e:
                    print(f"Removing {ticker}: {e}")
                    del db[ticker]
            else:
                print("Ticker already exists")

            close_file(db, dbname)

        except FileNotFoundError:
            print("File not found")


    #REMOVE TICKER
    def remData(self, ticker, dbname):
        try:
            db, dbfile = open_file(dbname)
            del db[ticker]
            close_file(db, dbname)
            print(f"Removing {ticker}")
        except FileNotFoundError:
            print("File not found")


    #DELETE DATABASE
    def resetData(self, dbname):
        os.remove(f'./storage/databases/{dbname}.pickle')


    #DISPLAY DATABASE
    def loadData(self, dbname, sort_choice):
        #try:
        db, dbfile = open_file(dbname)
        if sort_choice == "normal":
            sorted_data = sorted(db.values(), key=lambda x: x['% Below 95% CI'] if x['% Below 95% CI'] is not None else float('inf'), reverse = True)
        elif sort_choice == "short":
            sorted_data = sorted(db.values(), key=lambda x: x['% Above 95% CI'] if x['% Above 95% CI'] is not None else float('inf'), reverse = True)
        elif sort_choice == "msd":
            sorted_data = sorted(db.values(), key=lambda x: x['RSI MSD'] if x['RSI MSD'] is not None else float('inf'), reverse = True)
        elif sort_choice == "rsi":
            sorted_data = sorted(db.values(), key=lambda x: x['RSI'] if x['RSI'] is not None else float('inf'), reverse = True)
        elif sort_choice == "turn":
            sorted_data = sorted(db.values(), key=lambda x: x['RSI Avg Turnover'] if x['RSI Avg Turnover'] is not None else float('inf'), reverse = False)
        
        for ticker in sorted_data:
            print(ticker)
        dbfile.close()
        return sorted_data

        #except Exception as e:
        #    print(f"{e}")



class Update():
    def __init__(self):
        self.analysis = AnalysisManager()
        self.worker_pool = WorkerPoolManager(self.analysis.data_manager)

    #UPDATE DATABASES
    
    def updateData(self, dbname: str) -> None:
        """Update database with optimized worker pool"""
        try:
            db, dbfile = open_file(dbname)
            print(f"{dbname} loading...")
        except FileNotFoundError:
            print("File not found")
            return

        def process_ticker_data(ticker):
            try:
                self.analysis.runall(ticker, db)    
                return True
            except Exception as e:
                print(f"Error processing {ticker}: {e}")
                return False
            
        def process_ticker_portfolio(ticker):
            try:
                
                self.analysis.runall_sell(ticker, db, self.analysis.data_manager.get_price)
                return True
            except Exception as e:
                print(f"Error processing {ticker}: {e}")
                return False

        # Process updates with optimized worker pool
        if dbname.startswith('p_') or dbname.startswith('portfolio_') or dbname.startswith('portfolio'):
            results = self.worker_pool.process_tickers(
                tickers=list(db.keys()),
                process_func=process_ticker_portfolio
            )
        else: 
            results = self.worker_pool.process_tickers(
                tickers=list(db.keys()),
                process_func=process_ticker_data
            )
        
        close_file(db, dbname)
        
        # Report statistics
        success_count = sum(1 for result in results.values() if result)
        print(f"Successfully updated {success_count} out of {len(db)} tickers")

    def find_s_buy(self, database):
        db, dbfile = open_file(database)
        for ticker, info in db.items():
            try:           
                if info['MA'][0] == "BULL" and info['Buy'] == True:
                    date_obj = datetime.strptime(info['MA'][1], "%m-%d")
                    if (datetime.today() - date_obj) < timedelta(days=30):
                        messagebox.showinfo(title = "strong buy", message = f"{ticker} is currently a strong buy.")
            except Exception as e:
                print(e)
                pass
    
    #CREATE/EDIT MAIN PORTFOLIO
    def mainPortfolio(self, dbname):
        try:
            db, dbfile = open_file(dbname)
        except FileNotFoundError:
            db = {}

        while True:
            ticker = simpledialog.askstring("Input", "Input ticker to be added (type 'done' to exit):").strip().upper()


            if ticker == "DONE":
                break

            if ticker not in db:
                price = simpledialog.askstring("Input", "Price of purchased stock:")
                self.analysis.runall_sell(ticker, db, price)
                
            else:
                print("Ticker already exists")

        close_file(db, dbname)


#OPEN/CLOSE FILE
def open_file(dbname):
    with open(f'./storage/databases/{dbname}.pickle', 'rb') as dbfile:
        db = pickle.load(dbfile)
    return db, dbfile


def close_file(db, dbname):
    with open(f'./storage/databases/{dbname}.pickle', 'wb') as dbfile:
        pickle.dump(db, dbfile)
    dbfile.close()




