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

from data.ml import ml
from settings.settings_manager import SettingsManager
from data.winrate import WinrateManager
from data.shortrate import ShortrateManager
from applications.scraper import scraper
from applications.converter import convert

# Suppress warning
warnings.simplefilter(action='ignore', category=FutureWarning)

class StockTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Stock Tracker")
        self.settings_manager = SettingsManager()
        self.winrate_manager = WinrateManager()
        self.shortrate_manager = ShortrateManager()
        tk.Label(root, text="Main Menu", font=("Arial", 25)).pack(pady=20)

        tk.Button(root, text="Run", command=self.run, height = 2, width = 15).pack(pady=20)
        tk.Label(root, text="Check settings, update portfolios, update databases, run short and winrate experiments.", font = ("Arial", 10)).pack(pady=0)

        tk.Button(root, text="Commands", command=self.commands, height = 2, width = 15).pack(pady=20)
        tk.Label(root, text="Run individual tasks.", font=("Arial", 10)).pack(pady=0)

        tk.Button(root, text="Manage Databases", command=self.manage_databases, height = 2, width = 15).pack(pady=20)
        tk.Label(root, text="Database related settings.", font=("Arial", 10)).pack(pady=0)

        tk.Button(root, text="Portfolio", command=self.portfolio, height = 2, width = 15).pack(pady=20) #make this more suitable for tkinter
        tk.Label(root, text="Manage running portfolios.", font=("Arial", 10)).pack(pady=0)

        tk.Button(root, text="Applications", command=self.application, height = 2, width = 15).pack(pady=20)
        tk.Label(root, text="External applications.", font=("Arial", 10)).pack(pady=0)

        tk.Button(root, text="Settings", command=self.settings, height = 2, width = 15).pack(pady=20)
        tk.Label(root, text="Edit Settings File.", font=("Arial", 10)).pack(pady=0)

        tk.Button(root, text="Quit", command=self.quit, height = 2, width = 15).pack(pady=20)

    def run(self):
        #Run settings/winrate/shortrate
        self.settings_manager.checkSettings()
        self.winrate_manager.checkWinrate()
        self.shortrate_manager.checkShortrate()

        self.winrate_manager.winrate()
        self.winrate_manager.scanWinrate()
        self.winrate_manager.winratePotential()

        #self.shortrate_manager.shortrate()
        #self.shortrate_manager.scanShortrate()
        #self.shortrate_manager.shortratePotential()

        winshort_window = WinShortWindow(self.root)
        winshort_window.run()

    def commands(self):
        commands_window = CommandsWindow(self.root)
        commands_window.run()
    

    def manage_databases(self):
        edit_window = EditWindow(self.root)
        edit_window.run()

    def portfolio(self):
        port_window = PortWindow(self.root)
        port_window.run()

    def application(self):
        app_window = AppWindow(self.root)
        app_window.run()

    def settings(self):
        settings_window = SettingsWindow(self.root)
        settings_window.run()


    def quit(self):
        self.root.quit()



class WinShortWindow:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title("Winrate Results/Shorting Results")
        self.root.geometry("1500x800+200+100")

    def WinFrame(self):
        win_frame = tk.Frame(self.root)
        win_frame.pack(fill = tk.X, expand = True)
        win_canvas = tk.Canvas(win_frame, width=1480, height=380, highlightthickness = 1, highlightbackground = 'black')
        win_canvas.pack(side=tk.LEFT)

        y_scrollbar = tk.Scrollbar(win_frame, orient=tk.VERTICAL, command=win_canvas.yview)
        y_scrollbar.pack(side=tk.LEFT, fill=tk.Y)
        y_pos = 20


        win_canvas.create_text(750, y_pos, text="Potential Sell", font=("Arial", 16), anchor = "center")
        y_pos += 20 
    
        db, dbfile = open_file('winrate_potential')
        for key, value in db.items():
            label_text = f"{key}: {value} \n"
            y_pos +=15
            win_canvas.create_text(750, y_pos, text=label_text, anchor = "center")

        y_pos += 20





        win_canvas.create_text(750, y_pos, text="Sold", font=("Arial", 16), anchor = "center")
        y_pos += 20 

        db, dbfile = open_file('winrate')
        for key, value in db.items():
            label_text = f"{key}: {value} \n"
            y_pos +=15
            win_canvas.create_text(750, y_pos, text=label_text, anchor = "center")

        y_pos += 20
        win_canvas.create_text(750, y_pos, text="Holding", font=("Arial", 16), anchor = "center")
        y_pos += 20




        db, dbfile = open_file('winrate_storage')
        db_sorted = dict(sorted(db.items(), key=lambda x: x[1]["Date"]))
        for key, value in db_sorted.items():
            label_text = f"{key}: {value}\n"
            y_pos +=15
            win_canvas.create_text(750, y_pos, text=label_text, anchor = "center")

        actual_height= y_pos
        win_canvas.configure(yscrollcommand=y_scrollbar.set, scrollregion=(0,0,750, actual_height))





    def ShortFrame(self):
        short_frame = tk.Frame(self.root)
        short_frame.pack(fill = tk.X, expand = True)

        short_canvas = tk.Canvas(short_frame, width=1480, height=380, highlightthickness = 1, highlightbackground = 'black')
        short_canvas.pack(side=tk.LEFT)

        y_scrollbar = tk.Scrollbar(short_frame, orient=tk.VERTICAL, command=short_canvas.yview)
        y_scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        y_pos = 20



        short_canvas.create_text(750, y_pos, text="Potential Sell", font=("Arial", 16), anchor = "center")
        y_pos += 20 
    
        db, dbfile = open_file('shortrate_potential')
        for key, value in db.items():
            label_text = f"{key}: {value} \n"
            y_pos +=15
            short_canvas.create_text(750, y_pos, text=label_text, anchor = "center")

        y_pos += 20




        short_canvas.create_text(750, y_pos, text="Sold", font=("Arial", 16), anchor = "center")
        y_pos += 20

        db, dbfile = open_file('shortrate')
        for key, value in db.items():
            label_text = f"{key}: {value}\n"
            y_pos +=15
            short_canvas.create_text(750, y_pos, text=label_text, anchor = "center")
            print(f"{key}: {value}\n")
        short_canvas.create_text(750, y_pos, text="Holding", font=("Arial", 16), anchor = "center")
        y_pos += 20




        db, dbfile = open_file('shortrate_storage')
        db_sorted = dict(sorted(db.items(), key=lambda x: x[1]["Date"]))
        for key, value in db_sorted.items():
            label_text = f"{key}: {value}\n"
            y_pos +=15
            short_canvas.create_text(750, y_pos, text=label_text, anchor = "center")

        actual_height= y_pos
        short_canvas.configure(yscrollcommand=y_scrollbar.set, scrollregion=(0,0,750, actual_height))

    def run(self):
        self.WinFrame()
        self.ShortFrame()
        self.root.mainloop()

class EditWindow:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title("Database Manager")
        self.root.geometry("800x600+200+100")
        tk.Button(self.root, text="Store", command=self.store).pack(pady=5)
        tk.Button(self.root, text="Load", command=self.load).pack(pady=5)
        tk.Button(self.root, text="Load WinShort", command=self.loadWinShort).pack(pady=5)
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
        #try:
        load_window = LoadWindow(self.root)
        load_window.run()
        #except:
        #    messagebox.showinfo("Sort", "There has been a typo.")

    def loadWinShort(self):
        winshort_window = WinShortWindow(self.root)
        winshort_window.run()

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

    def run(self):
        self.root.mainloop()

class SettingsWindow:       ##should make this resemble a settings screen - auto popup choices of database then switches etc
    def __init__(self,root):
        self.root = tk.Tk()
        self.root.title("Settings")
        self.settings_manager = SettingsManager()
        self.root.geometry("800x600+200+100")
        tk.Button(self.root, text="Startup", command = self.startup).pack(pady=5)
        tk.Button(self.root, text="Back", command = self.startup).pack(pady=5)



    def startup(self):
        self.settings_manager.loadSettings()
        database = simpledialog.askstring("Input", "Name of database:").strip()
        choice = messagebox.askyesno("Y/N", "Would you like this database to update on startup?")
        self.settings_manager.adjustSettings(database, choice)

    def back(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()



class CommandsWindow:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title = "Commands"
        self.root.geometry("800x600+200+100")
        tk.Button(self.root, text="Update", command=self.update).pack(pady=5)
        tk.Button(self.root, text="Update Winrate/Shortrate", command=self.winshort).pack(pady=5)
        tk.Button(self.root, text="RSI", command=self.rsi).pack(pady=5)
        tk.Button(self.root, text="RSI Accuracy", command=self.rsi_acc).pack(pady=5)
        tk.Button(self.root, text="RSI Turnover", command=self.rsi_turn).pack(pady=5)
        tk.Button(self.root, text="Moving Average", command = self.MovingAverage).pack(pady=5)
        tk.Button(self.root, text="Machine Learning Prediction (not working correctly)", command = self.MachineLearning).pack(pady=5)
        tk.Button(self.root, text="Back", command=self.back).pack(pady=10)
        

        self.settings_manager = SettingsManager()
        self.winrate_manager = WinrateManager()
        self.shortrate_manager = ShortrateManager()

    def update(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        updateData(dbname)

    def winshort(self):
        self.winrate_manager.checkWinrate()
        self.winrate_manager.winrate()
        self.winrate_manager.scanWinrate()
        self.winrate_manager.winratePotential()
        self.shortrate_manager.checkShortrate()
        self.shortrate_manager.shortrate()
        self.shortrate_manager.scanShortrate()
        self.shortrate_manager.shortratePotential()

        winshort_window = WinShortWindow(self.root)
        winshort_window.run()

    def rsi(self):
        ticker = simpledialog.askstring("Input", "Name of ticker:").upper()
        graph = messagebox.askyesno("Y/N","Would you like a graph?")

        if graph == False:
            date_q = messagebox.askyesno("Y/N", "Would you like to input a specific date?")
            if date_q == False:
                rsi_value = rsi_calc(ticker, graph, date = None)
                messagebox.showinfo(title = "RSI", message = f"RSI for {ticker}: {rsi_value}")
            else:
                date_q = simpledialog.askstring("Input", "Date in Y-M-D Format:")
                rsi_value = rsi_calc(ticker, graph = False, date = date_q)
                messagebox.showinfo(title = "RSI", message = f"RSI for {ticker} on {date_q}: {rsi_value}")
        else:
            rsi_calc(ticker, graph, date = None)
            

    def rsi_acc(self):
        ticker = simpledialog.askstring("Input", "Name of ticker:").upper()
        cos_accuracy, msd_accuracy = rsi_accuracy(ticker)
        messagebox.showinfo(title = "RSI Accuracy", message = f"RSI Cosine, MSD Accuracy for {ticker}: {round(cos_accuracy,2)}, {round(msd_accuracy,2)}")
    
    def rsi_turn(self):
        ticker = simpledialog.askstring("Input", "Name of ticker:").upper()
        turnover = rsi_turnover(ticker)
        messagebox.showinfo(title = "RSI Turnover", message = f"The average RSI turnover for {ticker} is {round(turnover,0)} days.")
    def MovingAverage(self):
        ticker = simpledialog.askstring("Input", "Name of ticker:").upper()
        MA(ticker, graph = True)
    def MachineLearning(self):
        ticker = simpledialog.askstring("Input", "Name of ticker:").upper()
        ml(ticker)

    def back(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()

#WIP
class PortWindow:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title = "Portfolio Manager"
        self.root.geometry("800x600+200+100")
        tk.Button(self.root, text = "Portfolio", command = self.portfolio).pack(pady=5)
        tk.Button(self.root, text = "Portfolio Update", command = self.updatePortfolio).pack(pady=5)
        tk.Button(self.root, text="Back", command=self.back).pack(pady=50)

    def portfolio(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        mainPortfolio(dbname)

    def back(self):
        self.root.destroy()

    def updatePortfolio(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        updatePortfolio(dbname)

    def run(self):
        self.root.mainloop()


class AppWindow:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title = "Application Manager"
        self.root.geometry("800x600+200+100")
        tk.Button(self.root, text = "Converter", command = self.converter).pack(pady=5)
        tk.Button(self.root, text = "Scraper", command = self.scraper).pack(pady=5)
        tk.Button(self.root, text = "Back", command = self.back).pack(pady=5)

    def scraper(self):
        index = simpledialog.askstring("Input", "Name of index (eg. dowjones, sp500, nasdaq100):")
        filename = simpledialog.askstring("Input", "Output file:")
        choice = simpledialog.askstring("Input", "Add or Overwrite to file?")
        scraper(index, choice, filename)

    def converter(self):
        convert()

    def back(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()






class LoadWindow:
    def __init__(self, root):
        self.root = tk.Tk()
        self.root.title = "Loaded Results"
        self.root.geometry("1400x1000+400+200")

    def load(self):
        dbname = simpledialog.askstring("Input", "Name of database:")
        sort_choice = simpledialog.askstring("Sort", "Sort by over 95% (short), under 95% (normal), RSI (RSI), RSI accuracy (MSD), or RSI turnover (turn)? ('short ', 'normal', 'MSD', 'RSI', 'turn) ").lower().strip()
        sorted_data = loadData(dbname, sort_choice)

        load_frame = tk.Frame(self.root)
        load_frame.pack(fill = tk.X, expand = True)

        load_canvas = tk.Canvas(load_frame, width=1380, height=900)
        load_canvas.pack(side=tk.LEFT)

        y_scrollbar = tk.Scrollbar(load_frame, orient=tk.VERTICAL, command=load_canvas.yview)
        y_scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        y_pos = 10

        for ticker in sorted_data:
            load_canvas.create_text(750, y_pos, text=ticker, anchor = "center")
            y_pos +=15

        actual_height= y_pos
        load_canvas.configure(yscrollcommand=y_scrollbar.set, scrollregion=(0,0,750, actual_height))

    def run(self):
        load_window = LoadWindow(self.root)
        load_window.load()
        self.root.mainloop()













root = tk.Tk()
app = StockTracker(root)
root.geometry("1000x800+200+100")
root.mainloop()

"""
def update_all():
    
    db_w_s, dbfile_w_s = open_file('winrate_storage') #holds
    db_w, dbfile_w = open_file('winrate') #sold
    db_w_p, dbfile_w_p = open_file('winrate_potential') 
    db_s, dbfile_s = open_file('shortrate') #sold
    db_s_s, dbfile_s_s = open_file('shortrate_storage') #holds
    db_s_p, dbfile_s_p = open_file('shortrate_potential')     
    db_ticker, dbfile_ticker = open_file('t_safe')

    for ticker, ticker_data in db_ticker.items():
        if ticker in db_w_s:
            db_w_s[ticker]['MA Converging'] = ticker_data['MA Converging']
            print(f'Updated {ticker}')
    close_file(db_w_s, 'winrate_storage')

    for ticker, ticker_data in db_ticker.items():
        if ticker in db_w:
            db_w[ticker]['MA Converging'] = ticker_data['MA Converging']
            print(f'Updated {ticker}')
    close_file(db_w, 'winrate')

    for ticker, ticker_data in db_ticker.items():
        if ticker in db_w_p:
            db_w_p[ticker]['MA Converging'] = ticker_data['MA Converging']
            print(f'Updated {ticker}')
    close_file(db_w_p, 'winrate_potential')
    

    for ticker, ticker_data in db_ticker.items():
        if ticker in db_s_s:
            db_s_s[ticker]['MA Converging'] = ticker_data['MA Converging']
            print(f'Updated {ticker}')
    close_file(db_s_s, 'shortrate_storage')


update_all()
"""