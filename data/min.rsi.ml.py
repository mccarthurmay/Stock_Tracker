import yfinance as yf
import pandas as pd
from sklearn.model_selection import train_test_split, GridSearchCV, KFold
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_class_weight
import numpy as np
from data.database import open_file
from concurrent.futures import ThreadPoolExecutor, as_completed

def rsi_base(ticker, period='7d', interval='1m'):
    ticker = yf.Ticker(ticker)
    df = ticker.history(interval=interval, period=period)
    
    change = df['Close'].diff()
    change_up = change.copy()
    change_down = change.copy()

    change_up[change_up < 0] = 0
    change_down[change_down > 0] = 0
    
    # Adjust the rolling window for 1-minute data (14 periods = 14 minutes)
    mean_up = change_up.rolling(14).mean()
    mean_down = change_down.rolling(14).mean().abs()
    
    rsi = 100 * mean_up / (mean_up + mean_down)
    df['RSI'] = rsi
    
    # Adjust rolling windows for 1-minute data
    df['Avg_Volume'] = df['Volume'].rolling(14).mean()
    df['Volume_Change'] = df['Volume'].pct_change()
    df['RSI_MA'] = df['RSI'].rolling(5).mean()
    df['Volatility'] = df['Close'].rolling(14).std()
    
    df = df.dropna(subset=['RSI', 'Avg_Volume', 'RSI_MA', 'Volatility'])
    return df

def analyze_rsi_behavior(df):
    events = []
    

    
    for i in range(len(df)):
        if pd.notna(df['RSI'].iloc[i]):
            if df['RSI'].iloc[i] > 0 and df['RSI'].iloc[i] < 65:
                for j in range(i + 1, min(i + 10 , len(df))):
                    if pd.notna(df['RSI'].iloc[j]) and df['RSI'].iloc[j] > 70:
                        events.append((df.index[i], 'Directly to 70'))
                        break
                else:
                    events.append((df.index[i], 'Not to 70'))
    
    events_df = pd.DataFrame(events, columns=['Date', 'Outcome'])

    
    return events_df

def prepare_features(df):
    df['Prev_RSI'] = df['RSI'].shift(1)
    df['Prev_Avg_Volume'] = df['Avg_Volume'].shift(1)
    df['Prev_Volume_Change'] = df['Volume_Change'].shift(1)
    df['Prev_RSI_MA'] = df['RSI_MA'].shift(1)
    df['Prev_Volatility'] = df['Volatility'].shift(1)
    df.dropna(inplace=True)
    
    if df.empty:
        raise ValueError("DataFrame is empty after feature preparation.")
    
    X = df[['Prev_RSI', 'Prev_Avg_Volume', 'Prev_Volume_Change', 'Prev_RSI_MA', 'Prev_Volatility']]
    y = df['Outcome'].apply(lambda x: 1 if x == 'Directly to 70' else 0)
    

    return X, y

def main(ticker):
    df = rsi_base(ticker, period='7d', interval='1m')
    events_df = analyze_rsi_behavior(df)
    df = df.join(events_df.set_index('Date'), how='left', on=df.index)
    X, y = prepare_features(df)
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    class_weights = compute_class_weight('balanced', classes=np.unique(y), y=y)
    class_weight_dict = dict(enumerate(class_weights))
    
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    model = RandomForestClassifier(random_state=42, class_weight=class_weight_dict)
    
    param_grid = {
        'n_estimators': [100, 200],
        'max_depth': [None, 10, 20],
        'min_samples_split': [2, 5, 10]
    }
    
    grid_search = GridSearchCV(model, param_grid, cv=kf, scoring='accuracy', n_jobs=-1)
    grid_search.fit(X_scaled, y)
    
    best_model = grid_search.best_estimator_
    #print(f'Best Parameters: {grid_search.best_params_}')
    
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.3, random_state=42)
    best_model.fit(X_train, y_train)
    
    y_pred = best_model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    latest_features = [df[['Prev_RSI', 'Prev_Avg_Volume', 'Prev_Volume_Change', 'Prev_RSI_MA', 'Prev_Volatility']].iloc[-1]]
    latest_features_scaled = scaler.transform(latest_features)
    probas = best_model.predict_proba(latest_features_scaled)
    probability_of_direct = probas[0][1]
    
    # Print current RSI and last time RSI hit 45
    current_rsi = df['RSI'].iloc[-1]
    #print(f'Accuracy: {accuracy:.2f}')
    #print(f'Current RSI: {current_rsi:.2f}')
    #print(f'Probability of RSI increasing directly to 70: {probability_of_direct:.2f}')
    return accuracy, probability_of_direct


def test():
    db, dbfile = open_file('t_safe')
    
    def process_ticker(ticker):
        try:
            if db[ticker]['RSI'] > 0 and db[ticker]['RSI'] < 65:
                accuracy, prob = main(ticker)
                return ticker, accuracy, prob
        except Exception as e:

            return None

    # Use ThreadPoolExecutor to run ticker processing in parallel
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_ticker, ticker): ticker for ticker in db}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                ticker, accuracy, prob = result
                if accuracy > 0.7 and prob > 0.7:
                    print(ticker, accuracy, prob, "===================================================================================================================================================================================")