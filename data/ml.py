import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
from sklearn.preprocessing import MinMaxScaler
from keras.models import Sequential
from keras.layers import LSTM, Dense, Dropout, Conv1D, MaxPooling1D, Flatten
from keras.callbacks import EarlyStopping

#Load dataset

#   - Moving averages added to identify trend direction of stock (20 short term, 75 longer term)
#       - Bullish crossover 
#           - when short-term moving average crosses above a longer-term moving average
#       - Bearish crossover
#           - Short-term moving average crosses below a longer-term moving average

ds = yf.Ticker('F').history(period="3y")
ds['S_MA'] = ds['Close'].rolling(window=20).mean()
ds['L_MA'] = ds['Close'].rolling(window=50).mean()
ds['RSI'] = ds['Close'].diff(1).apply(lambda x: max(x, 0)).rolling(window=14).mean() / ds['Close'].diff(1).abs().rolling(window=14).mean() * 100
ds.dropna(inplace=True)
ds_train = ds[['Close', 'S_MA', 'L_MA', 'RSI']].values


#Scale data

#   - Scaling data ensures all features have same range
#       - Normalizes data
#       - Improves convergence (neural networks are sensitive to scale of input data)
#       - Avoids dominance (larger ranges may dominate learning process, neglecting shorter ranges)

scaler = MinMaxScaler(feature_range=(0, 1))
ds_scaled = scaler.fit_transform(ds_train)

#Create training dataset

X_train = []
y_train = []
for i in range(60, len(ds_scaled)):
    X_train.append(ds_scaled[i-60:i, :])
    y_train.append(ds_scaled[i, 0])
X_train = np.array(X_train)
y_train = np.array(y_train)

#Build LSTM Model
#   - Layers are added sequentially, initializing linear stack of layers
regressor = Sequential()

#Convolutional layer

#   - commonly used for image recognition, however can be applied to spacial relationships (time series data)
#   - filter specifies number of kernals that the layer will learn
#   - kernal_size indicates size of convolutional matrix, so the layer will convolve each input sequence with 64 different 1D filters, all size 3
#   - activation = relu is Rectified Linear Unit, a common activation function that introduces non-linearity
regressor.add(Conv1D(filters=64, kernel_size=3, activation='relu', input_shape=(X_train.shape[1], X_train.shape[2])))
regressor.add(MaxPooling1D(pool_size=2))

#LSTM layers

# Long Short-Term Memory
#       - type of recurrent neural network architecture, different from traditional RNNs in that it remembers long-term dependencies
#   - memory cell (units)
#       - maintain a cell state over time, stores information for long periods
#   - gates
#       -forget gate = decides what in information to discard from the cell state
#       -input gate = updates the cell by selectively adding new information
#       -output gate = controls flow of information from cell state to output based on current input and previous state
#   
regressor.add(LSTM(units=50, return_sequences=True))
regressor.add(Dropout(0.2))
regressor.add(LSTM(units=50))
regressor.add(Dropout(0.2))


#Dense layer
#   - fully connected layer, performs a linear operation on input data followed by activation function. Connects every neuron in one layer to every neuron in the next layer, making the network.
#   - Linear Operation
#       - Performs matrix-vector multiplication on input data 
#           - y=f(W⋅x+b), where W is weight of matrix shape (m,n), b is a bias vector of shape (m,), and f is an activation function
#   - Activation Function
#       - After (W⋅x+b), the output is passed through the activation function, ReLU , Sigmoid, or Tanh (relu in this case)
regressor.add(Dense(units=1))

#Compile Model
#   - optimizers adjust weights during training to minimize loss
#   - loss measues hnow well the model performs on training and validation data
regressor.compile(optimizer='adam', loss='mean_squared_error')

#Early stopping to prevent overfitting
#   - prevents overfitting of a model to training data
#       - during training, the performance is evaluated on a separate validation dataset at the end of each epoch
early_stopping = EarlyStopping(monitor='loss', patience=10, restore_best_weights=True)

#Train Model
#   - epoch = a complete pass through the entire dataset
#       - machine model learns from training data, adjusting weights to minimize loss
#       - increasing epochs allows model to see training data more times
#   - batch size = number of training examples utilized in one interaction
regressor.fit(X_train, y_train, epochs=200, batch_size=32, callbacks=[early_stopping])

#Show Prediction of Past Values
dataset_total = pd.concat((pd.DataFrame(ds_train, columns=['Close', 'S_MA', 'L_MA', 'RSI']), ds[['Close', 'S_MA', 'L_MA', 'RSI']]), axis=0)
inputs = dataset_total[len(dataset_total) - len(ds) - 60:].values
inputs = scaler.transform(inputs)

X_test = []
for i in range(60, len(inputs)):
    X_test.append(inputs[i-60:i, :])
X_test = np.array(X_test)

predicted_ds = regressor.predict(X_test)
predicted_ds = scaler.inverse_transform(np.concatenate([predicted_ds, np.zeros((predicted_ds.shape[0], 3))], axis=1))[:, 0]

#Predict future values
future_days = 30
future_inputs = inputs[-60:]
future_predictions = []

for _ in range(future_days):
    future_X_test = np.reshape(future_inputs, (1, future_inputs.shape[0], future_inputs.shape[1]))
    future_predicted = regressor.predict(future_X_test)
    future_predictions.append(future_predicted[0, 0])
    future_inputs = np.append(future_inputs[1:], np.concatenate([future_predicted, np.zeros((1, 3))], axis=1), axis=0)

future_predictions = scaler.inverse_transform(np.concatenate([np.array(future_predictions).reshape(-1, 1), np.zeros((future_days, 3))], axis=1))[:, 0]

#Plotting the results
plt.plot(ds.index, ds['Close'], color='black', label='Actual Price')
#plt.plot(ds.index[len(ds)-len(predicted_ds):], predicted_ds, color='gray', label='Predicted Price')

#Append future predictions to the dataset for plotting
future_indices = pd.date_range(start=ds.index[-1], periods=future_days + 1, freq='B')[1:]
future_df = pd.DataFrame(future_predictions, index=future_indices, columns=['Close'])

#Plot the moving averages
plt.plot(ds.index, ds['S_MA'], color='purple', label='Short Term MA')
plt.plot(ds.index, ds['L_MA'], color='red', label='Long Term MA')

plt.plot(future_df.index, future_df['Close'], color='blue', label='Future Predictions')
plt.title('Stock Price Prediction')
plt.xlabel('Time')
plt.ylabel('Price')
plt.legend()
plt.show()


f = open("test.txt", "a")
f.write(str(future_df['Close']))
