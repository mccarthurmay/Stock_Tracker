import tkinter as tk
from tkinter import messagebox, simpledialog
import warnings
import pickle
import yfinance as yf
import statistics
import pandas as pd
import os
import concurrent.futures
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
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
    updatePortfolio,
    updateData,
    open_file,
    close_file,
)
from data.analysis import (
    runall,
    runall_sell,
    buy,
    sell,
    over_confidence,
    under_confidence,
    con_plot,
    rsi_calc,
    day_movement,
    showinfo,
    rsi_accuracy,
    rsi_turnover,
    MA,
    
)
from data.ab_low import ab_lowManager

from data.ml import ml
from settings.settings_manager import SettingsManager
from data.winrate import WinrateManager
from data.shortrate import ShortrateManager
from applications.scraper import scraper
from applications.converter import convert

ab_low = ab_lowManager()
ab_low.checkfile()
ab_low.scanRSI()

db, dbfile = open_file('15')
for key, value in db.items():
    print(key, value)