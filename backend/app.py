import os
import traceback
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from data.analysis import AnalysisManager, AlpacaDataManager
from data.database import DBManager, WorkerPoolManager, open_file

TICKER_LISTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'storage', 'ticker_lists')

app = Flask(__name__)
CORS(app)

analysis_manager = AnalysisManager()
db_manager = DBManager()


def _numpy(obj):
    """Recursively convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _numpy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_numpy(i) for i in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _ok(data=None, **kwargs):
    payload = {'success': True}
    if data is not None:
        payload['data'] = data
    payload.update(kwargs)
    return jsonify(payload)


def _err(msg, status=500):
    return jsonify({'success': False, 'error': msg}), status


# ── Static serving ────────────────────────────────────────────────────────────

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static = app.static_folder or ''
    if path and os.path.exists(os.path.join(static, path)):
        return send_from_directory(static, path)
    return send_from_directory(static, 'index.html')


# ── Single ticker lookup ──────────────────────────────────────────────────────

@app.route('/api/ticker/<ticker>')
def get_ticker(ticker):
    try:
        ticker = ticker.upper().strip()
        rsi      = analysis_manager.RSI.rsi_calc(ticker)
        enhanced = analysis_manager.CI.enhanced_analysis(ticker, {})
        if enhanced is None:
            return _err(f'No data available for {ticker}', 404)
        ff = analysis_manager.fundamentals.get_fundamentals(ticker)
        return _ok(_numpy({
            'Ticker':          ticker,
            'RSI':             rsi,
            '% Below 95% CI': enhanced.get('CI_UNDER', 0),
            'BM':              ff['BM'],
            'OP':              ff['OP'],
            'INV':             ff['INV'],
            'BETA':            ff['BETA'],
            'MCAP':            ff['MCAP'],
        }))
    except Exception as e:
        return _err(str(e))


# ── Databases ─────────────────────────────────────────────────────────────────

@app.route('/api/databases')
def get_databases():
    try:
        db_dir = './storage/databases'
        dbs = [f.replace('.pickle', '') for f in os.listdir(db_dir) if f.endswith('.pickle')]
        return _ok(dbs)
    except Exception as e:
        return _err(str(e))


@app.route('/api/database/<dbname>/load')
def load_database(dbname):
    try:
        sort_choice = request.args.get('sort', 'normal')
        data = db_manager.loadData(dbname, sort_choice)
        return _ok(_numpy(data))
    except Exception as e:
        traceback.print_exc()
        return _err(str(e))


@app.route('/api/database/<dbname>/create', methods=['POST'])
def create_database(dbname):
    try:
        tickers = request.get_json().get('tickers', [])
        if not tickers:
            return _err('No tickers provided', 400)
        os.makedirs('./storage/databases', exist_ok=True)
        db_manager.storeData(dbname, tickers)
        return _ok()
    except Exception as e:
        return _err(str(e))


@app.route('/api/database/<dbname>/update', methods=['POST'])
def update_database(dbname):
    try:
        db_manager.updateData(dbname)
        return _ok()
    except Exception as e:
        return _err(str(e))


@app.route('/api/database/<dbname>/add', methods=['POST'])
def add_ticker(dbname):
    try:
        ticker = request.get_json().get('ticker')
        if not ticker:
            return _err('No ticker provided', 400)
        db_manager.addData(ticker, dbname)
        return _ok()
    except Exception as e:
        return _err(str(e))


@app.route('/api/database/<dbname>/remove', methods=['POST'])
def remove_ticker(dbname):
    try:
        ticker = request.get_json().get('ticker')
        if not ticker:
            return _err('No ticker provided', 400)
        db_manager.remData(ticker, dbname)
        return _ok()
    except Exception as e:
        return _err(str(e))


@app.route('/api/database/<dbname>/estimate')
def estimate_update_time(dbname):
    try:
        db, _ = open_file(dbname)
        tickers = list(db.keys())
        pool = WorkerPoolManager(AlpacaDataManager())
        cached, total_calls, workers = pool.analyze_workload(tickers)
        estimated_seconds = (total_calls / pool.api_limit_per_minute * 60) if total_calls else 0
        return _ok({
            'estimated_time': estimated_seconds,
            'workers':        workers,
            'total_api_calls': total_calls,
            'cached_tickers':  cached,
            'api_limit':       pool.api_limit_per_minute,
        })
    except FileNotFoundError:
        return _err('Database not found', 404)
    except Exception as e:
        return _err(str(e))


# ── Ticker lists ──────────────────────────────────────────────────────────────

@app.route('/api/ticker-lists')
def get_ticker_lists():
    try:
        os.makedirs(TICKER_LISTS_PATH, exist_ok=True)
        files = [f for f in os.listdir(TICKER_LISTS_PATH)
                 if os.path.isfile(os.path.join(TICKER_LISTS_PATH, f))]
        return _ok(files=files)
    except Exception as e:
        return _err(str(e))


@app.route('/api/ticker-lists/<filename>')
def get_ticker_list_content(filename):
    try:
        path = os.path.join(TICKER_LISTS_PATH, filename)
        if not os.path.exists(path):
            return _err('File not found', 404)
        with open(path, 'r') as f:
            return _ok(content=f.read())
    except Exception as e:
        return _err(str(e))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
