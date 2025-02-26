from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
from data.analysis import RSIManager, AnalysisManager, AlpacaDataManager
from data.database import DBManager, Update, WorkerPoolManager
from data.day_trade import DTManager, DTData
from data.winrate import WinrateManager
from applications.scraper import scraper
from applications.converter import convert
from data.database import open_file, close_file
import numpy as np
import pandas as pd
import pickle
import os
import data.config
from werkzeug.utils import secure_filename
import subprocess
import sys

# Get the absolute path of the current file (app.py)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Navigate to the ticker_lists directory relative to backend
TICKER_LISTS_PATH = os.path.join(current_dir, 'storage', 'ticker_lists')


app = Flask(__name__)
CORS(app)

# Initialize existing managers
dt_manager = DTManager()
analysis_manager = AnalysisManager()
db_manager = DBManager()
rsi_manager = RSIManager()


@app.route('/api/scrape', methods=['POST'])
def scrape_index():
    print("Scraping...")
    data = request.json
    index = data.get('index')
    file_name = data.get('fileName')
    file_mode = data.get('fileMode')
    
    try:
        scraper(index, file_mode, file_name)
        return jsonify({
            'success': True,
            'message': f'Successfully scraped {index} index'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/', defaults = {'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/rsi/<ticker>')
def get_rsi(ticker):
    try:
        rsi = rsi_manager.rsi_calc(ticker, graph=False, date=None)
        return jsonify({
            'success': True,
            'data': {
                'rsi':rsi
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rsi/accuracy/<ticker>')
def get_rsi_accuracy(ticker):
    try:
        cos, msd = rsi_manager.rsi_accuracy(ticker)
        return jsonify({
            'success': True,
            'data': {
                'cos': cos,
                'msd': msd
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/rsi/turnover/<ticker>')
def get_rsi_turnover(ticker):
    try:
        turnover = rsi_manager.rsi_turnover(ticker)
        return jsonify({
            'success': True,
            'data': {
                'turnover': turnover
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/rsi/ma/<ticker>')
def get_ma(ticker):
    try:
        latest_market, latest_date, converging = rsi_manager.MA(ticker, graph = False)
        if converging: 
            converging = "True"
        else:
            converging = "False"
        print(converging)
        return jsonify({
            'success': True,
            'data': {
                'latest_market':latest_market,
                'latest_date':latest_date,
                'converging':converging
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
        
@app.route('/api/databases')
def get_databases():
    try:
        db_dir = './storage/databases'
        databases = [f.replace('.pickle', '') for f in os.listdir(db_dir)
                     if f.endswith('pickle')]
        return jsonify({
            'success': True,
            'data': databases
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/database/<dbname>/add', methods=['POST'])
def add_ticker(dbname):  
    try:
        data = request.get_json()
        ticker = data.get('ticker')
        if not ticker:
            return jsonify({'success': False, 'error': 'No ticker provided'}), 400
        
        db_manager.addData(ticker,dbname)
        return jsonify({'success':True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/database/<dbname>/remove', methods = ['POST'])
def remove_ticker(dbname):
    try:
        data = request.get_json()
        ticker = data.get('ticker')
        if not ticker:
            return jsonify({'success': False, 'error': 'No ticker provided'}), 400
        
        db_manager.remData(ticker, dbname)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# DOES NOT WORK 
@app.route('/api/database/<dbname>/reset', methods=['POST'])
def reset_database(dbname):
    try:
        db_manager.resetData(dbname)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/database/<dbname>/create', methods=['POST'])
def create_database(dbname):
    try:
        data = request.get_json()
        stock_list = data.get('tickers', [])
        
        if not stock_list:
            return jsonify({'success': False, 'error': 'No tickers provided'}), 400
            
        # Create the storage directory if it doesn't exist
        os.makedirs('./storage/databases', exist_ok=True)
        
        db_manager.storeData(dbname, stock_list)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/ticker-lists', methods=['GET'])
def get_ticker_lists():
    try:
        if not os.path.exists(TICKER_LISTS_PATH):
            os.makedirs(TICKER_LISTS_PATH)
            
        files = [f for f in os.listdir(TICKER_LISTS_PATH) if os.path.isfile(os.path.join(TICKER_LISTS_PATH, f))]
        return jsonify({
            'success': True,
            'files': files
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/ticker-lists/<filename>', methods=['GET'])
def get_ticker_list_content(filename):
    try:
        file_path = os.path.join(TICKER_LISTS_PATH, filename)
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': 'File not found'
            }), 404
            
        with open(file_path, 'r') as f:
            content = f.read()
            
        return jsonify({
            'success': True,
            'content': content
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500





# ConfidenceModule handling

@app.route('/api/database/<dbname>/load')
def load_database(dbname):
    try:
        sort_choice = request.args.get('sort', 'normal')
        db_manager = DBManager()
        sorted_data = db_manager.loadData(dbname, sort_choice)
        return jsonify({
            'success': True,
            'data': sorted_data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/experiments/run', methods=['POST'])
def run_experiments():
    try:
        # Initialize managers
        winrate_manager = WinrateManager()

        # Run the experiments
        winrate_manager.checkWinrate()
        winrate_manager.winrate()
        winrate_manager.scanWinrate()
        winrate_results = winrate_manager.winratePotential()

        return jsonify({
            'success': True,
            'results': {
                'winrate_results': winrate_results,
                # Add other results as needed
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
@app.route('/api/database/<dbname>/estimate', methods=['GET'])
def estimate_update_time(dbname):
    try:
        # Get the database
        db, dbfile = open_file(dbname)
        tickers = list(db.keys())
        
        # Close the database file
        dbfile.close()
        
        # Initialize WorkerPoolManager with AlpacaDataManager
        data_manager = AlpacaDataManager()
        worker_pool = WorkerPoolManager(data_manager)
        
        # Get workload analysis
        cached_tickers, total_api_calls, optimal_workers = worker_pool.analyze_workload(tickers)
        
        # Calculate time in seconds (convert from minutes)
        if total_api_calls > 0:
            estimated_minutes = total_api_calls / worker_pool.api_limit_per_minute
            estimated_seconds = estimated_minutes * 60
        else:
            estimated_seconds = 0
            
        return jsonify({
            'success': True,
            'estimated_time': estimated_seconds,
            'workers': optimal_workers,
            'total_api_calls': total_api_calls,
            'cached_tickers': cached_tickers,
            'api_limit': worker_pool.api_limit_per_minute
        })
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'error': 'Database not found'
        }), 404
    except Exception as e:
        print(f"Error in estimate_update_time: {str(e)}")  # Add logging
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/database/<dbname>/update', methods=['POST'])
def update_database(dbname):
    try:
        update_manager = Update()
        update_manager.updateData(dbname)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
    
@app.route('/api/analysis/<ticker>')
def get_combined_analysis(ticker):
    try:
        rsi_manager = RSIManager()
        # Get RSI data and dataframe
        rsi, _, df = rsi_manager.rsi_base(ticker, 720)
        
        if df.empty or rsi.empty:
            return jsonify({
                'success': False,
                'error': 'No data available for this ticker'
            }), 400
        
        # Remove first 13 rows as done in plot_data
        df = df.iloc[13:]  
        rsi = rsi[13:]
        
        # Make sure indexes match
        common_index = df.index.intersection(rsi.index)
        df = df.loc[common_index]
        rsi = rsi.loc[common_index]
        
        # Calculate MAs using the existing MA function
        close_data = df['close']
        MA = pd.DataFrame()
        MA['ST'] = close_data.ewm(span=5, adjust=False).mean() 
        MA['LT'] = close_data.ewm(span=20, adjust=False).mean()
        MA.dropna(inplace=True)
        
        # Ensure all indexes align
        common_index = df.index.intersection(MA.index)
        df = df.loc[common_index]
        rsi = rsi.loc[common_index]
        MA = MA.loc[common_index]
        
        # Convert DataFrame to dictionary format
        df = df.reset_index()
        
        # Create data points
        data = []
        for i in range(1, len(df)):  # Start at 1 to compare previous day's data
            if (not pd.isna(df['close'][i]) and 
                not pd.isna(rsi.iloc[i]) and 
                not pd.isna(MA['ST'].iloc[i]) and 
                not pd.isna(MA['LT'].iloc[i])):
                
                # Check for short MA crossing above long MA (bullish signal)
                bull_run = False
                if MA['ST'].iloc[i] > MA['LT'].iloc[i] and MA['ST'].iloc[i-1] <= MA['LT'].iloc[i-1]:
                    bull_run = True
                
                data_point = {
                    'timestamp': df['timestamp'][i].isoformat(),
                    'price': float(df['close'][i]),
                    'rsi': float(rsi.iloc[i]),
                    'ma_short': float(MA['ST'].iloc[i]),
                    'ma_long': float(MA['LT'].iloc[i]),
                    'bull_run': bull_run  # Add bull_run field to indicate crossover
                }
                data.append(data_point)
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No valid data points after processing'
            }), 400
            
        print("Final data length:", len(data))
        print("Sample data points:")
        for i in range(min(3, len(data))):
            print(f"Point {i}:", data[i])
        
        # Verify no null values in the data
        for point in data:
            if any(v is None for v in point.values()):
                print("Warning: Found null values in data point:", point)
            
        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        print(f"Error in get_combined_analysis: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

    
if __name__ == '__main__':
    app.run(debug=True, port=5000)