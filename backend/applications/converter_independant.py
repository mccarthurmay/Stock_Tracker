import subprocess
import tkinter as tk
from tkinter import filedialog
import sys
import os



def select_file():
    #opens file dialog to select .py file
    f_path = filedialog.askopenfilename(
        filetype = [("Python files", "*.py")],
        title = "Choose a Python file"
    )
    if f_path:
        #clears text in entry widget
        entry_s_path.delete(0, tk.END)
        #inserts file path into entry widget
        entry_s_path.insert(0, f_path)


def convert():
    #retrieves file path from entry widget
    s_path = entry_s_path.get()
    #defines directory of script
    script_dir = os.path.dirname(os.path.abspath(s_path))
    if not s_path:
        lbl_status.config(text="Please select a Python file first.", fg="red")
        return

    try:
        lbl_status.config(text = 'Converting...', fg = 'blue')
        #update GUI to show text
        root.update_idletasks()

        subprocess.run([
            sys.executable, '-m', 'PyInstaller', '--onefile',
            '--distpath', script_dir, s_path, '--clean', '--noupx'
        ], check=True)

        lbl_status.config(text = 'Successful conversion.', fg = 'green')


    except subprocess.CalledProcessError as e:
        lbl_status.config(text= f'Error occurred at {e}', fg = 'red')

#create main application window
root = tk.Tk()
root.title("Python to Executable Converter")

#customization

lbl_entry= tk.Label(root, text="Script Path")
entry_s_path = tk.Entry(root, width=50)
entry_s_path.pack(padx=20, pady=30)

btn_browse = tk.Button(root, text="Browse Scripts", command=select_file)
btn_browse.pack(padx=10, pady=10)

btn_convert = tk.Button(root, text="Convert to EXE", command=convert)
btn_convert.pack(padx=10, pady=10)

lbl_status = tk.Label(root, text="")
lbl_status.pack(padx=10, pady=20)


#run
root.mainloop()
