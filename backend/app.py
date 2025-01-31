from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from data.analysis import RSIManager, AnalysisManager, AlpacaDataManager
from data.database import DBManager, Update
from data.day_trade import DTManager, DTData
from data.winrate import WinrateManager
from settings.settings_manager import SettingsManager
import os
import data.config

app = Flask(__name__, static_folder ='../frontend/build')
CORS(app)

dt_manager = DTManager()
analysis_manager = AnalysisManager()
db_manager = DBManager()
settings_manager = SettingsManager()
rsi_manager = RSIManager()

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


@app.route('/api/database/<dbname>/update', methods=['POST'])
def update_database(dbname):
    try:
        update_manager = Update()
        update_manager.updateData(dbname)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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
        settings_manager = SettingsManager()
        winrate_manager = WinrateManager()

        # Run the experiments
        settings_manager.checkSettings()
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
    
if __name__ == '__main__':
    app.run(debug=True, port=5000)