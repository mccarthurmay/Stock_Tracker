import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import sys
import os



def convert():

    f_path = filedialog.askopenfilename(
        filetype = [("Python files", "*.py")],
        title = "Choose a Python file"
    )

    #defines directory of script
    script_dir = os.path.dirname(os.path.abspath(f_path))
    if not f_path:
        messagebox.showinfo("Info", "Please select a Python file first.")
        return

    try:
        messagebox.showinfo("Info", "Converting...")

        subprocess.run([
            sys.executable, '-m', 'PyInstaller', '--onefile',
            '--distpath', script_dir, f_path, '--clean', '--noupx'
        ], check=True)

        messagebox.showinfo("Info", "Successful conversion.")


    except subprocess.CalledProcessError as e:
        messagebox.showinfo("Info", f'Error occurred at {e}')
