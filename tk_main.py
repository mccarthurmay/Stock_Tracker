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

# Suppress warning
warnings.simplefilter(action='ignore', category=FutureWarning)

class StockTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Stock Tracker")
        self.settings_manager = SettingsManager()
        self.winrate_manager = WinrateManager()
        tk.Label(root, text="Main Menu", font=("Arial", 20)).pack(pady=0)

        tk.Button(root, text="Run", command=self.run).pack(pady=10)

        tk.Button(root, text="Commands", command=self.commands).pack(pady=20)
        tk.Label(root, text="Run individual tasks.", font=("Arial", 10)).pack(pady=0)

        tk.Button(root, text="Manage Databases", command=self.settings).pack(pady=20)

        tk.Button(root, text="Portfolio", command=self.portfolio).pack(pady=20) #make this more suitable for tkinter
        tk.Label(root, text="Manage running portfolios.", font=("Arial", 10)).pack(pady=0)


        tk.Button(root, text="Quit", command=self.quit).pack(pady=5)


    def run(self):
        self.settings_manager.checkSettings()
        self.winrate_manager.winrate()
        self.winrate_manager.checkwinrate()

        result_frame = tk.Frame(root)
        result_frame.pack(fill = tk.X, expand = True)


        result_canvas = tk.Canvas(result_frame, width=600, height=200)
        result_canvas.pack(side=tk.LEFT)

        y_scrollbar = tk.Scrollbar(result_frame, orient=tk.VERTICAL, command=result_canvas.yview)
        y_scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        y_pos = 10

        result_canvas.create_text(400, y_pos, text="Sold", font=("Arial", 16), anchor = "center")
        y_pos += 20

        db, dbfile = open_file('winrate')
        for key, value in db.items():
            label_text = f"{key}: {value}\n"
            y_pos +=15
            result_canvas.create_text(400, y_pos, text=label_text, anchor = "center")


        result_canvas.create_text(400, y_pos, text="Holding", font=("Arial", 16), anchor = "center")
        y_pos += 20

        db, dbfile = open_file('winrate_storage')
        for key, value in db.items():
            label_text = f"{key}: {value}\n"
            y_pos +=15
            result_canvas.create_text(400, y_pos, text=label_text, anchor = "center")

        actual_height= y_pos
        result_canvas.configure(yscrollcommand=y_scrollbar.set, scrollregion=(0,0,500, actual_height))


    def commands(self):
        commands_window = Commands(self.root)
        commands_window.root.mainloop()

    def settings(self):
        edit_window = EditWindow(self.root)
        edit_window.root.mainloop()

    def portfolio(self):
        port_window = PortWindow(self.root)
        port_window.root.mainloop()

    def quit(self):
        self.root.quit()





class EditWindow:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title("Database Manager")
        self.settings_manager = SettingsManager()
        self.root.geometry("800x600+200+100")
        tk.Button(self.root, text="Store", command=self.store).pack(pady=5)
        tk.Button(self.root, text="Load", command=self.load).pack(pady=5)
        tk.Button(self.root, text="Add Ticker", command=self.add).pack(pady=5)
        tk.Button(self.root, text="Remove Ticker", command=self.remove).pack(pady=5)
        tk.Button(self.root, text="Reset Database", command=self.reset).pack(pady=5)
        tk.Button(self.root, text="Back", command=self.back).pack(pady=50)

    def store(self):
        input_file = simpledialog.askstring("Input", "File containing tickers:")
        dbname = simpledialog.askstring("Input", "Name of database:")
        try:
            with open(f'./storage/ticker_lists/{input_file}.txt', 'r') as txt:
                data_txt = txt.read()
                data_txt = data_txt.split('\n')
            stock_list = list(data_txt)
            storeData(dbname, stock_list)
            messagebox.showinfo("Info", "Tickers stored successfully.")
        except:
            messagebox.showinfo("Info", "We ran into a problem, please check names of files and resubmit.")

    def load(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        loadData(dbname)

    def add(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        ticker = simpledialog.askstring("Input", "Name of ticker:").upper()
        addData(ticker, dbname)

    def remove(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        ticker = simpledialog.askstring("Input", "Name of ticker:").upper()
        remData(ticker, dbname)

    def reset(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        resetData(dbname)

    def back(self):
        self.root.destroy()






class Commands:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title = "Commands"
        self.root.geometry("800x600+200+100")
        tk.Button(self.root, text="Update", command=self.update).pack(pady=5)
        tk.Button(self.root, text="Winrate", command=self.winrate).pack(pady=5)
        tk.Button(self.root, text="RSI", command=self.rsi).pack(pady=5)
        tk.Button(self.root, text="Back", command=self.back).pack(pady=10)

        self.settings_manager = SettingsManager()
        self.winrate_manager = WinrateManager()

    def update(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        updateData(dbname)

    def winrate(self):
        winrate_manager.winrate()
        winrate_manager.checkwinrate()
        db, dbfile = open_file('winrate')
        #WIP

    def rsi(self):
        ticker = simpledialog.askstring("Input", "Name of ticker:").upper()
        graph = messagebox.askyesno("Y/N","Would you like a graph?")
        if graph == False:
            rsi_value = rsi_calc(ticker, graph = False)
            messagebox.showinfo(title = "RSI", message = f"RSI for {ticker}: {rsi_value}")
        else:
            rsi_calc(ticker, graph)

    def back(self):
        self.root.destroy()



#WIP
class PortWindow:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title = "Portfolio Manager"
        self.root.geometry("800x600+200+100")
        tk.Button(self.root, text = "Portfolio", command = self.portfolio).pack(pady=5)
        tk.Button(self.root, text = "Portfolio Update", command = self.portfolio).pack(pady=5)
        tk.Button(self.root, text="Back", command=self.back).pack(pady=50)



    def portfolio(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        mainPortfolio(dbname)

    def back(self):
        self.root.destroy()


    def updatePortfolio(self):
        pass




root = tk.Tk()
app = StockTracker(root)
root.geometry("800x600+200+100")
root.mainloop()
