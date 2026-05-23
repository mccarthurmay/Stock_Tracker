import os
import pickle
import concurrent.futures
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Lock
from typing import List, Dict, Any, Tuple

from data.analysis import AnalysisManager


def _is_portfolio(dbname: str) -> bool:
    return dbname.startswith(('p_', 'portfolio_', 'portfolio'))


class ProgressTracker:
    def __init__(self, total: int):
        self.total = total
        self.completed = 0
        self.lock = Lock()
        self.start_time = datetime.now()
        self.errors = []
        self.active = {}

    def started(self, ticker: str, worker_id: int):
        with self.lock:
            self.active[worker_id] = ticker
            self._print()

    def done(self, ticker: str, worker_id: int, success: bool):
        with self.lock:
            self.completed += 1
            if not success:
                self.errors.append(ticker)
            self.active.pop(worker_id, None)
            self._print()

    def _print(self):
        pct = self.completed / self.total * 100
        elapsed = datetime.now() - self.start_time
        est = (elapsed / self.completed * (self.total - self.completed)
               if self.completed else timedelta(0))

        print('\033[F\033[K' * (4 + len(self.active)), end='')
        filled = int(pct * 30 / 100)
        print(f"\nProgress: [{'█' * filled}{'-' * (30 - filled)}] {pct:.1f}%")
        print(f"Completed: {self.completed}/{self.total}")
        print(f"Time: {str(elapsed).split('.')[0]} elapsed, ~{str(est).split('.')[0]} remaining")
        for wid, t in self.active.items():
            print(f"Worker {wid}: {t}")


class WorkerPoolManager:
    def __init__(self, data_manager, api_limit_per_minute: int = 150):
        self.data_manager = data_manager
        self.api_limit_per_minute = api_limit_per_minute
        self.calls_per_ticker = 4

    def analyze_workload(self, tickers: List[str]) -> Tuple[int, int, int]:
        cached = sum(
            1 for t in tickers
            if hasattr(self.data_manager, '_cache') and (
                f"{t}_1D_5" in self.data_manager._cache or
                f"{t}_1Min_5" in self.data_manager._cache
            )
        )
        total_calls = (len(tickers) - cached) * self.calls_per_ticker

        try:
            cpu = len(os.sched_getaffinity(0))
        except AttributeError:
            cpu = os.cpu_count() or 4

        workers = max(1, min(cpu * 2, len(tickers), 8))

        print(f"\nWorkload: {workers} workers, {total_calls} API calls, "
              f"~{total_calls / self.api_limit_per_minute:.1f} min\n")

        return cached, total_calls, workers

    def process_tickers(self, tickers: List[str], process_func) -> Dict[str, Any]:
        _, _, workers = self.analyze_workload(tickers)
        tracker = ProgressTracker(len(tickers))
        print("\n" * (workers + 4))

        results = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            def run(ticker, wid):
                tracker.started(ticker, wid)
                try:
                    result = process_func(ticker)
                    tracker.done(ticker, wid, True)
                    return result
                except Exception as e:
                    print(f"\nError processing {ticker}: {e}")
                    tracker.done(ticker, wid, False)
                    return None

            futures = {
                executor.submit(run, t, i % workers): t
                for i, t in enumerate(tickers)
            }
            for future in concurrent.futures.as_completed(futures):
                results[futures[future]] = future.result()

        print("\nDone!")
        if tracker.errors:
            print(f"Errors: {', '.join(tracker.errors)}")
        return results


class DBManager:
    def __init__(self):
        self.analysis = AnalysisManager()
        self.worker_pool = WorkerPoolManager(self.analysis.data_manager)

    def _process_buy(self, ticker, db):
        self.analysis.runall(ticker, db)

    def _process_sell(self, ticker, db):
        price = self.analysis.data_manager.get_price(ticker)
        self.analysis.runall_sell(ticker, db, price)

    def storeData(self, dbname: str, stock_list: List[str]) -> None:
        try:
            db, _ = open_file(dbname)
        except FileNotFoundError:
            db = {}

        for ticker in stock_list:
            db[ticker] = {}
        close_file(db, dbname)

        db, _ = open_file(dbname)
        is_port = _is_portfolio(dbname)

        def process(ticker):
            try:
                if is_port:
                    self._process_sell(ticker, db)
                else:
                    self._process_buy(ticker, db)
                # runall may return silently without populating the entry
                if not db.get(ticker, {}).get('RSI'):
                    db.pop(ticker, None)
                    return False
                return True
            except Exception as e:
                print(f"Removing {ticker}: {e}")
                db.pop(ticker, None)
                return False

        results = self.worker_pool.process_tickers(list(db.keys()), process)
        close_file(db, dbname)
        print(f"Stored {sum(results.values())} / {len(stock_list)} tickers")

    def updateData(self, dbname: str) -> None:
        try:
            db, _ = open_file(dbname)
        except FileNotFoundError:
            print(f"Database '{dbname}' not found")
            return

        is_port = _is_portfolio(dbname)

        def process(ticker):
            try:
                if is_port:
                    self._process_sell(ticker, db)
                else:
                    self._process_buy(ticker, db)
                if not db.get(ticker, {}).get('RSI'):
                    db.pop(ticker, None)
                    return False
                return True
            except Exception as e:
                print(f"Error updating {ticker}: {e}")
                return False

        results = self.worker_pool.process_tickers(list(db.keys()), process)
        close_file(db, dbname)
        print(f"Updated {sum(results.values())} / {len(db)} tickers")

    def addData(self, ticker: str, dbname: str) -> None:
        try:
            db, _ = open_file(dbname)
        except FileNotFoundError:
            print("Database not found")
            return

        if ticker in db:
            print(f"{ticker} already exists")
            close_file(db, dbname)
            return

        try:
            if _is_portfolio(dbname):
                self._process_sell(ticker, db)
            else:
                self._process_buy(ticker, db)
        except Exception as e:
            print(f"Failed to add {ticker}: {e}")
            db.pop(ticker, None)

        close_file(db, dbname)

    def remData(self, ticker: str, dbname: str) -> None:
        try:
            db, _ = open_file(dbname)
            db.pop(ticker, None)
            close_file(db, dbname)
        except FileNotFoundError:
            print("Database not found")

    def loadData(self, dbname: str, sort_choice: str) -> list:
        db, _ = open_file(dbname)

        _SORTS = {
            'rsi':  (lambda x: x.get('RSI', 0),                        True),
            'bm':   (lambda x: x.get('BM') or -999,                    True),
            'op':   (lambda x: x.get('OP') or -999,                    True),
            'inv':  (lambda x: x.get('INV')  if x.get('INV')  is not None else 999, False),
            'beta': (lambda x: x.get('BETA') if x.get('BETA') is not None else 999, False),
            'mcap': (lambda x: x.get('MCAP') if x.get('MCAP') is not None else 999, False),
        }
        key_fn, reverse = _SORTS.get(
            sort_choice,
            (lambda x: x.get('% Below 95% CI', 0), True)
        )
        rows = [v for v in db.values() if v.get('Ticker') and v.get('RSI') is not None]
        return sorted(rows, key=key_fn, reverse=reverse)


def open_file(dbname: str):
    filepath = f'./storage/databases/{dbname}.pickle'
    try:
        with open(filepath, 'rb') as f:
            return pickle.load(f), f
    except EOFError:
        print(f"Warning: '{dbname}' is empty/corrupted — reinitializing")
        with open(filepath, 'wb') as f:
            pickle.dump({}, f)
        with open(filepath, 'rb') as f:
            return pickle.load(f), f


def close_file(db: dict, dbname: str) -> None:
    with open(f'./storage/databases/{dbname}.pickle', 'wb') as f:
        pickle.dump(db, f)
