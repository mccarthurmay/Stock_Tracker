import yfinance as yf
import pandas as pd
from datetime import datetime

def performance(ticker, start_year, end_year):
    stock = yf.Ticker(ticker)
    data = stock.history(start=f"{start_year}-01-01", end=f"{end_year}-12-31")

    #Initialize counters
    total_months = 0
    positive_months = 0

    for year in range(start_year, end_year + 1):
        #Get month data for the year
        month_data = data[(data.index.month == 7) & (data.index.year == year)]
        
        if not month_data.empty:
            total_months += 1
            start_price = month_data.iloc[0]['Close']
            end_price = month_data.iloc[-1]['Close']
            
            if end_price > start_price:
                positive_months += 1

    #Calculate percentage
    if total_months > 0:
        percentage = (positive_months / total_months) * 100
    else:
        percentage = 0

    return positive_months, total_months, percentage


p = True
while p == True:
    ticker = input("Ticker")
    start_year = 2012  #Adjust this to the earliest year you want to analyze
    end_year = datetime.now().year - 1  #Last full year

    # Run the analysis
    positive, total, percent = performance(ticker, start_year, end_year)

    print(f"{ticker} gained in {positive} out of {total} months analyzed: ({percent:.2f}%) from {start_year} to {end_year}")

