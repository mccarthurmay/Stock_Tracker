import tkinter as tk
from tkinter import messagebox
import warnings
import pickle
import yfinance as yf
import statistics
import pandas as pd
import os
import concurrent.futures
import matplotlib.pyplot as plt
from datetime import datetime
from scipy.stats import linregress
import numpy as np
from datetime import date

from data.database import (
    storeData,
    mainPortfolio,
    close_file,
    addData,
    remData,
    resetData,
    loadData,
    updateMain,
    updateData,
    open_file,
    close_file
)
from data.analysis import (
    runall,
    runall_sell,
    buy,
    sell,
    slope,
    confidence,
    con_plot,
    rsi_calc,
    day_movement,
    showinfo
)
from settings.settings_manager import SettingsManager
from data.winrate import WinrateManager

class StockTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Stock Tracker")
        self.settings_manager = SettingsManager()
        self.winrate_manager = WinrateManager()

        #buttons
        tk.Button(root, text="Store", command=self.store).pack(pady=5)
        tk.Button(root, text="Load", command=self.load).pack(pady=5)
        tk.Button(root, text="Portfolio", command=self.portfolio).pack(pady=5)
        tk.Button(root, text="Add", command=self.add).pack(pady=5)
        tk.Button(root, text="Remove", command=self.remove).pack(pady=5)
        tk.Button(root, text="Reset", command=self.reset).pack(pady=5)
        tk.Button(root, text="RSI", command=self.rsi).pack(pady=5)
        tk.Button(root, text="Debug", command=self.debug).pack(pady=5)
        tk.Button(root, text="Settings", command=self.settings).pack(pady=5)
        tk.Button(root, text="Quit", command=self.quit).pack(pady=5)


    def store(self):
        pass

    def load(self):
        pass

    def portfolio(self):
        pass

    def add(self):
        pass

    def remove(self):
        pass

    def reset(self):
        pass

    def rsi(self):
        pass

    def debug(self):
        pass

    def settings(self):
        pass

    def quit(self):
        self.root.quit()

root = tk.Tk()
app = StockTracker(root)
root.mainloop()
