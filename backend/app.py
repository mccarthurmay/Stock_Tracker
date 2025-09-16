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
import config
from werkzeug.utils import secure_filename
import subprocess
import sys
from datetime import datetime

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


import json

def convert_numpy_types(obj):
    """Convert numpy types to native Python types for JSON serialization"""
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    else:
        return obj


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
        
        # Convert numpy types to native Python types
        converted_data = convert_numpy_types(sorted_data)
        
        return jsonify({
            'success': True,
            'data': converted_data
        })
    except Exception as e:
        print(f"ERROR loading database {dbname}: {str(e)}")
        print(f"ERROR type: {type(e).__name__}")
        import traceback
        traceback.print_exc()  # This will show the full error stack
        
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
    

@app.route('/api/monte-carlo/<ticker>')
def monte_carlo_analysis(ticker):
    try:
        ci_manager = analysis_manager.CI
        result = ci_manager.run_monte_carlo_validation(ticker)
        
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    

@app.route('/api/why-analysis/<ticker>')
def get_why_analysis(ticker):
    try:
        # Get fresh analysis data
        enhanced_results = analysis_manager.CI.enhanced_analysis(ticker, {})
        if enhanced_results is None:
            return jsonify({'success': False, 'error': 'No data available for ticker'}), 404
        
        # Get RSI and other indicators
        rsi = analysis_manager.RSI.rsi_calc(ticker, graph=False, date=None)
        ma, ma_date, converging = analysis_manager.RSI.MA(ticker, graph=False)
        cos, msd = analysis_manager.RSI.rsi_accuracy(ticker)
        turnover = analysis_manager.RSI.rsi_turnover(ticker)
        
        # Get current price for context
        current_price = analysis_manager.data_manager.get_price(ticker)
        
        # Generate detailed explanations
        explanations = generate_detailed_explanations(
            ticker, enhanced_results, rsi, ma, ma_date, converging, 
            cos, msd, turnover, current_price
        )
        
        return jsonify({
            'success': True,
            'data': explanations
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def generate_detailed_explanations(ticker, enhanced_results, rsi, ma, ma_date, converging, cos, msd, turnover, current_price):
    """Generate comprehensive explanations for why analysis"""
    
    # Technical condition analysis
    ci_under = enhanced_results.get('CI_UNDER', 0)
    anomaly_count = enhanced_results.get('ANOM_COUNT', 0)
    
    # RSI analysis
    if rsi < 30:
        rsi_condition = "severely oversold"
        rsi_implication = "Strong potential for upward reversal as selling pressure may be exhausted."
    elif rsi < 35:
        rsi_condition = "oversold"
        rsi_implication = "Moderate potential for price recovery as technical indicators suggest undervaluation."
    elif rsi > 70:
        rsi_condition = "overbought"
        rsi_implication = "Potential for price decline as buying momentum may be weakening."
    elif rsi > 65:
        rsi_condition = "approaching overbought"
        rsi_implication = "Caution advised as price may be reaching short-term peaks."
    else:
        rsi_condition = "neutral"
        rsi_implication = "No strong directional bias from momentum indicators."
    
    # Confidence interval analysis
    if ci_under > 10:
        ci_explanation = f"Price is {ci_under:.1f}% below the 95% confidence interval, indicating significant statistical undervaluation."
        ci_strength = "Strong"
    elif ci_under > 5:
        ci_explanation = f"Price is {ci_under:.1f}% below normal trading range, suggesting moderate undervaluation."
        ci_strength = "Moderate"
    elif ci_under > 0:
        ci_explanation = f"Price is {ci_under:.1f}% below average, showing slight undervaluation."
        ci_strength = "Weak"
    else:
        ci_explanation = "Price is within or above normal statistical range."
        ci_strength = "None"
    
    # Anomaly analysis
    if anomaly_count >= 3:
        anomaly_explanation = f"Multiple anomaly detection methods ({anomaly_count}/4) flagged unusual behavior, indicating high confidence in abnormal market conditions."
        anomaly_strength = "Very High"
    elif anomaly_count >= 2:
        anomaly_explanation = f"Two anomaly detection methods flagged unusual behavior, suggesting moderate confidence in market deviation."
        anomaly_strength = "High"
    elif anomaly_count >= 1:
        anomaly_explanation = f"One anomaly detection method flagged unusual behavior, indicating potential market irregularity."
        anomaly_strength = "Moderate"
    else:
        anomaly_explanation = "No significant anomalies detected in current market behavior."
        anomaly_strength = "Low"
    
    # Moving average analysis
    if ma == "BULL":
        ma_explanation = f"Stock is in bullish trend (confirmed {ma_date}). {'Trend may be strengthening.' if not converging else 'Moving averages are converging - potential trend change ahead.'}"
    elif ma == "BEAR":
        ma_explanation = f"Stock is in bearish trend (confirmed {ma_date}). {'Trend continues.' if not converging else 'Moving averages are converging - potential reversal possible.'}"
    else:
        ma_explanation = "Trend direction is unclear or transitioning between bullish and bearish phases."
    
    # Risk factors based on current conditions
    risk_factors = []
    
    if rsi > 70:
        risk_factors.append("Overbought conditions increase probability of short-term pullback")
    if anomaly_count == 0:
        risk_factors.append("Lack of anomalies suggests this may be normal market behavior rather than opportunity")
    if turnover > 60:
        risk_factors.append(f"Long average turnover ({turnover} days) suggests extended holding periods may be required")
    if cos < 0.6:
        risk_factors.append(f"Low RSI correlation ({cos:.2f}) reduces confidence in momentum-based signals")
    if ma == "BEAR" and not converging:
        risk_factors.append("Bearish trend without convergence signals suggests continued downward pressure")
    
    # Opportunity factors
    opportunity_factors = []
    
    if ci_under > 5:
        opportunity_factors.append(f"Significant statistical undervaluation ({ci_under:.1f}% below CI)")
    if rsi < 35:
        opportunity_factors.append(f"Oversold RSI ({rsi:.1f}) historically precedes recoveries")
    if anomaly_count >= 2:
        opportunity_factors.append(f"Multiple anomalies ({anomaly_count}) suggest unusual opportunity")
    if cos > 0.7:
        opportunity_factors.append(f"High RSI accuracy ({cos:.2f}) increases signal reliability")
    if ma == "BULL" or (ma == "BEAR" and converging):
        opportunity_factors.append("Trend analysis supports potential upward movement")
    
    # Time horizon estimation
    if turnover < 20:
        time_horizon = f"Short-term opportunity (avg {turnover} days) - quick movements expected"
    elif turnover < 40:
        time_horizon = f"Medium-term setup (avg {turnover} days) - patience required"
    else:
        time_horizon = f"Long-term position (avg {turnover} days) - extended holding period likely"
    
    # Overall assessment
    total_strength = 0
    if ci_strength == "Strong": total_strength += 3
    elif ci_strength == "Moderate": total_strength += 2
    elif ci_strength == "Weak": total_strength += 1
    
    if anomaly_strength == "Very High": total_strength += 4
    elif anomaly_strength == "High": total_strength += 3
    elif anomaly_strength == "Moderate": total_strength += 2
    elif anomaly_strength == "Low": total_strength += 1
    
    if rsi < 30: total_strength += 3
    elif rsi < 35: total_strength += 2
    elif rsi > 70: total_strength -= 2
    
    if total_strength >= 7:
        overall_confidence = "High"
        confidence_explanation = "Multiple strong indicators align to suggest significant opportunity."
    elif total_strength >= 4:
        overall_confidence = "Moderate"  
        confidence_explanation = "Several indicators suggest potential opportunity with moderate confidence."
    elif total_strength >= 2:
        overall_confidence = "Low"
        confidence_explanation = "Limited indicators suggest weak opportunity signal."
    else:
        overall_confidence = "Very Low"
        confidence_explanation = "Current conditions do not strongly support entry signals."
    
    return {
        'ticker': ticker,
        'current_price': current_price,
        'analysis_timestamp': datetime.now().isoformat(),
        'technical_conditions': {
            'rsi_value': rsi,
            'rsi_condition': rsi_condition,
            'rsi_implication': rsi_implication,
            'ci_percentage': ci_under,
            'ci_explanation': ci_explanation,
            'ci_strength': ci_strength,
            'anomaly_count': anomaly_count,
            'anomaly_explanation': anomaly_explanation,
            'anomaly_strength': anomaly_strength
        },
        'trend_analysis': {
            'moving_average': ma,
            'trend_date': ma_date,
            'converging': converging,
            'explanation': ma_explanation
        },
        'accuracy_metrics': {
            'rsi_correlation': cos,
            'rsi_msd': msd,
            'turnover_days': turnover,
            'time_horizon': time_horizon
        },
        'risk_assessment': {
            'risk_factors': risk_factors,
            'opportunity_factors': opportunity_factors,
            'overall_confidence': overall_confidence,
            'confidence_explanation': confidence_explanation
        },
        'detailed_reasoning': {
            'why_flagged': f"This stock was flagged due to {rsi_condition} RSI conditions ({rsi:.1f}), {ci_explanation.lower()}, and {anomaly_explanation.lower()}",
            'expected_outcome': f"Based on historical patterns with {turnover}-day average turnover and {cos:.2f} RSI correlation, {confidence_explanation.lower()}",
            'key_factors': opportunity_factors if len(opportunity_factors) > 0 else risk_factors
        }
    }
    
if __name__ == '__main__':
    app.run(debug=True, port=5000)