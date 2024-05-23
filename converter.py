import subprocess
import tkinter as tk
from tkinter import filedialog
import sys
import os

def convert():
    #retrieves file path from entry widget
    s_path = entry_script_path.get()
    #defines directory of script
    script_dir = os.path.dirname(os.path.abspath(s_path))
    
    try:
        subprocess.run([
            sys.executable, '-m', 'PyInstaller', '--onefile',
            '--clean', '--distpath', script_dir, s_path
        ], check=True)
        print('Done')
    except subprocess.CalledProcessError as e:
        print(f"Failed at: {e}")


#create main application window
root = tk.Tk()
root.title(".py to .exe converter")

#customization
entry_script_path = tk.Entry(root, width=100)
entry_script_path.pack(padx=10, pady=5)

btn_convert = tk.Button(root, text="Convert to EXE", command=convert)
btn_convert.pack(padx=10, pady=5)

lbl_status = tk.Label(root, text="")
lbl_status.pack(padx=10, pady=5)

root.mainloop()
