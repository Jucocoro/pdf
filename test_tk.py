# test_tk.py

import tkinter as tk
root = tk.Tk()
root.title("Tk Test")
root.geometry("300x100")
tk.Label(root, text="Tkinter is working!").pack(padx=20, pady=20)
root.mainloop()
