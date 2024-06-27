import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
from sklearn.preprocessing import MinMaxScaler
from keras.models import Sequential
from keras.layers import LSTM, Dense, Dropout

#Load dataset
ds = yf.Ticker('F').history(period="2y")
ds = pd.DataFrame(ds['Close'])
ds_train = ds.values

#Scale data
scaler = MinMaxScaler(feature_range=(0, 1))
ds_scaled = scaler.fit_transform(ds_train)

#Create training dataset
X_train = []
y_train = []
for i in range(60, len(ds_scaled)):
    X_train.append(ds_scaled[i-60:i, 0])
    y_train.append(ds_scaled[i, 0])
X_train = np.array(X_train)
y_train = np.array(y_train)

X_train = np.reshape(X_train, (X_train.shape[0], X_train.shape[1], 1))

#Build LSTM Model
regressor = Sequential()

regressor.add(LSTM(units=50, return_sequences=True, input_shape=(X_train.shape[1], 1)))
regressor.add(Dropout(0.2))

regressor.add(LSTM(units=50, return_sequences=True))
regressor.add(Dropout(0.2))

regressor.add(LSTM(units=50, return_sequences=True))
regressor.add(Dropout(0.2))

regressor.add(LSTM(units=50))
regressor.add(Dropout(0.2))

regressor.add(Dense(units=1))

#Compile Model
regressor.compile(optimizer='adam', loss='mean_squared_error')
#Train Model
regressor.fit(X_train, y_train, epochs=50, batch_size=32)

#Show Prediction of Past Values
dataset_total = pd.concat((pd.DataFrame(ds_train, columns=['Close']), ds), axis=0)
inputs = dataset_total[len(dataset_total) - len(ds) - 60:].values
inputs = inputs.reshape(-1, 1)
inputs = scaler.transform(inputs)

X_test = []
for i in range(60, len(inputs)):
    X_test.append(inputs[i-60:i, 0])
X_test = np.array(X_test)
X_test = np.reshape(X_test, (X_test.shape[0], X_test.shape[1], 1))

predicted_ds = regressor.predict(X_test)
predicted_ds = scaler.inverse_transform(predicted_ds)

#Predict future values
future_days = 30
future_inputs = inputs[-60:]
future_predictions = []

for _ in range(future_days):
    future_X_test = np.reshape(future_inputs, (1, future_inputs.shape[0], 1))
    future_predicted = regressor.predict(future_X_test)
    future_predictions.append(future_predicted[0, 0])
    future_inputs = np.append(future_inputs, future_predicted)[1:]

future_predictions = scaler.inverse_transform(np.array(future_predictions).reshape(-1, 1))

#Plotting the results
plt.plot(ds.index, ds['Close'], color='red', label='Actual Price')
plt.plot(ds.index[len(ds)-len(predicted_ds):], predicted_ds, color='green', label='Predicted Price')

#Append future predictions to the dataset for plotting
future_indices = pd.date_range(start=ds.index[-1], periods=future_days + 1, freq='B')[1:]
future_df = pd.DataFrame(future_predictions, index=future_indices, columns=['Close'])

plt.plot(future_df.index, future_df['Close'], color='blue', label='Future Predictions')
plt.title('Stock Price Prediction')
plt.xlabel('Time')
plt.ylabel('Price')
plt.legend()
plt.show()


f = open("test.txt", "a")
f.write(str(future_df['Close']))