import yfinance as yf
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score

def fetch_data(stock_ticker, start_date, end_date):
    stock_data = yf.download(stock_ticker, start=start_date, end=end_date)
    stock_data['Date'] = stock_data.index
    return stock_data

def get_earnings_dates(stock_ticker, start_date, end_date):
    stock = yf.Ticker(stock_ticker)
    earnings_dates = stock.earnings_dates
    earnings_dates = earnings_dates[(earnings_dates.index >= pd.Timestamp(start_date)) & (earnings_dates.index <= pd.Timestamp(end_date))]
    return earnings_dates

def create_features(data, earnings_dates):
    features = []
    for date in earnings_dates.index:
        date = pd.Timestamp(date)  # Ensure the date is a Timestamp object
        before_earnings = data[(data['Date'] < date) & (data['Date'] >= date - pd.DateOffset(days=30))]
        if before_earnings.empty:
            continue
        price_change = (data[data['Date'] == date]['Close'].values[0] - before_earnings['Close'].iloc[0]) / before_earnings['Close'].iloc[0]
        features.append({
            'price_change_before': price_change,
            'volatility': before_earnings['Close'].pct_change().std(),
            'previous_close': before_earnings['Close'].iloc[-1],
            'increase': int(data[data['Date'] == date]['Close'].values[0] > before_earnings['Close'].iloc[0])
        })
    return pd.DataFrame(features)

def main(stock_ticker, start_date, end_date):
    stock_data = fetch_data(stock_ticker, start_date, end_date)
    earnings_dates = get_earnings_dates(stock_ticker, start_date, end_date)
    
    if earnings_dates.empty:
        print("No earnings dates found within the specified range.")
        return
    
    features = create_features(stock_data, earnings_dates)
    
    if features.empty:
        print("No features created.")
        return

    X = features[['price_change_before', 'volatility', 'previous_close']]
    y = features['increase']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred)
    
    print(f"Accuracy: {accuracy:.2f}")
    print("Classification Report:")
    print(report)
    
    # Predict the outcome for the next earnings date
    latest_features = create_features(stock_data, pd.DataFrame([pd.Timestamp(end_date)], columns=['Date']))
    if not latest_features.empty:
        X_latest = latest_features[['price_change_before', 'volatility', 'previous_close']]
        prediction = model.predict(X_latest)
        prediction_prob = model.predict_proba(X_latest)
        print(f"Probability of increase for the next earnings date: {prediction_prob[0][1]:.2f}")

if __name__ == "__main__":
    main('AAPL', '2020-01-01', '2024-01-01')
