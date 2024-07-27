import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV, train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report
import ta  # Technical Analysis Library in Python

def fetch_data(ticker):
    stock_data = yf.download(ticker, start='2014-07-23', end='2024-01-22', interval='1d')
    return stock_data

def feature_engineering(stock_data):
    stock_data['Return'] = stock_data['Close'].pct_change()
    stock_data['SMA_30'] = stock_data['Close'].rolling(window=30).mean()
    stock_data['SMA_100'] = stock_data['Close'].rolling(window=100).mean()
    stock_data['RSI'] = ta.momentum.RSIIndicator(stock_data['Close'], window=14).rsi()
    stock_data['MACD'] = ta.trend.MACD(stock_data['Close']).macd()
    stock_data['MACD_signal'] = ta.trend.MACD(stock_data['Close']).macd_signal()
    stock_data['Bollinger_Mavg'] = ta.volatility.BollingerBands(stock_data['Close']).bollinger_mavg()
    stock_data['Bollinger_Upper'] = ta.volatility.BollingerBands(stock_data['Close']).bollinger_hband()
    stock_data['Bollinger_Lower'] = ta.volatility.BollingerBands(stock_data['Close']).bollinger_lband()
    
    stock_data['Target'] = (stock_data['Return'].shift(-1) > 0).astype(int)
    stock_data = stock_data.dropna()
    
    features = stock_data[['Return', 'SMA_30', 'SMA_100', 'RSI', 'MACD', 'MACD_signal', 'Bollinger_Mavg', 'Bollinger_Upper', 'Bollinger_Lower']]
    target = stock_data['Target']
    
    return features, target, stock_data

def train_model(features, target):
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)
    
    tscv = TimeSeriesSplit(n_splits=5)
    
    model = GradientBoostingClassifier(random_state=42)
    param_grid = {
        'n_estimators': [100, 200],
        'learning_rate': [0.01, 0.1, 0.2],
        'max_depth': [3, 5, 7]
    }
    
    grid_search = GridSearchCV(model, param_grid, cv=tscv, scoring='accuracy')
    grid_search.fit(features_scaled, target)
    
    best_model = grid_search.best_estimator_
    
    # Train-test split for evaluation
    X_train, X_test, y_train, y_test = train_test_split(features_scaled, target, test_size=0.3, random_state=42)
    y_pred = best_model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f'Best Model Accuracy: {accuracy:.2f}')
    print('Classification Report:')
    print(classification_report(y_test, y_pred))
    
    # Feature Importances
    importances = best_model.feature_importances_
    feature_names = features.columns
    importance_df = pd.DataFrame({'Feature': feature_names, 'Importance': importances})
    print('Feature Importances:')
    print(importance_df.sort_values(by='Importance', ascending=False))
    
    return best_model, scaler

def predict_next_earnings(model, scaler, stock_data):
    latest_features = stock_data[['Return', 'SMA_30', 'SMA_100', 'RSI', 'MACD', 'MACD_signal', 'Bollinger_Mavg', 'Bollinger_Upper', 'Bollinger_Lower']].iloc[-1:]
    latest_features_scaled = scaler.transform(latest_features)
    prediction_proba = model.predict_proba(latest_features_scaled)
    increase_prob = prediction_proba[0][1] * 100  # Probability of increase
    return increase_prob

def main(ticker):
    stock_data = fetch_data(ticker)
    features, target, stock_data_with_targets = feature_engineering(stock_data)
    model, scaler = train_model(features, target)
    
    # Count the number of earnings dates
    num_earnings_dates = stock_data_with_targets['Target'].sum()
    print(f'Number of earnings dates used: {num_earnings_dates}')
    
    increase_prob = predict_next_earnings(model, scaler, stock_data)
    print(f'Percentage likelihood of increase for next earnings date: {increase_prob:.2f}%')

if __name__ == "__main__":
    main('GE')  # Example ticker
