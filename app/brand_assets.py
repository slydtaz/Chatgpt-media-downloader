"""Embedded static brand art and a rounded glossy button skin.
The white ChatGPT mark is still artwork; the blue cloud and sparkles are not animated.
"""
import tkinter as tk

LOGO_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAPS0lEQVR42u1ZeXRW5Zn/vctdviX5SAIhIbIIsoXCqIhIEJ"

def load_brand_images(root: tk.Misc) -> dict[str, tk.PhotoImage]:
    return {"logo": tk.PhotoImage(master=root, data=LOGO_PNG_BASE64)}
