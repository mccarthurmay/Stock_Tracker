import tkinter as tk
from main import StockTracker

root = tk.Tk()
app = StockTracker(root)
root.geometry("1000x800+200+100")
root.mainloop()