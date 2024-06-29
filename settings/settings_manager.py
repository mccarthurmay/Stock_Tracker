import os
import pickle
from data.database import updateData, updatePortfolio, find_s_buy

class SettingsManager:
    def __init__(self, settings_file = './storage/settings/settings.pickle'):
        self.settings_file = settings_file
        self.settings = self.open_settings()


    def makeSettings(self):
        self.settings = {}
        print("Settings file created.")
        self.close_settings()


        self.settings = self.open_settings()

        for database in os.listdir('./storage/databases'):
            if database.startswith('t_') or database.startswith('tickers_') or database.startswith('ticker_'):
                database = os.path.splitext(database)[0]
                self.settings[database] = {'AutoUpdate': False}

        self.close_settings()


    def open_settings(self):
        try:
            with open(self.settings_file, 'rb') as settingsFile:
                settings = pickle.load(settingsFile)
        except FileNotFoundError:
            self.makeSettings()
            self.open_settings()
        return settings


    def close_settings(self):
        with open(self.settings_file, 'wb') as settingsFile:
            pickle.dump(self.settings, settingsFile)
        settingsFile.close()


    def checkSettings(self):
        self.open_settings()
        print("Settings loaded.")
        for database, values in self.settings.items():
            if values.get('AutoUpdate', True):
                updateData(database)
                find_s_buy(database)

        for database in os.listdir('./storage/databases'):
            if database.startswith('p_') or database.startswith('portfolio_'):
                database = os.path.splitext(database)[0]
                updatePortfolio(database)

        self.close_settings()


    def adjustSettings(self, database, choice):

        self.open_settings()

        if database in self.settings:
            self.settings[database]['AutoUpdate'] = choice
            print(f"Updated 'AutoUpdate' for '{database}' to {choice}")
        else:
            print(f"Database '{database}' not found")

        self.close_settings()


    def loadSettings(self):
        for database, values in self.settings.items():
            print(f"{database}: {values}")
