"""Run after installing: python -m pip install -e ./ui_library"""
import tkinter as tk
from reusable_neon_ui import BorderConfig, GradientConfig, NeonButton, NeonSurface, NeonTabBar, UIConfig

root = tk.Tk()
root.title("Reusable Neon UI")
root.geometry("900x560")
settings = UIConfig()
settings.background.gradient = GradientConfig(
    mode="bubbles", colors=("#EC4899", "#8B5CF6", "#2563EB", "#22D3EE"),
    intensity=.88, pulse_strength=.5, pulse_speed=1.1, speed=.65, bubble_count=8)
settings.background.border = BorderConfig(
    enabled=True, colors=("#EC4899", "#8B5CF6", "#2563EB", "#22D3EE"),
    thickness=2, intensity=.95, glow=5, speed=.8)
surface = NeonSurface(root, style=settings)
surface.pack(fill="both", expand=True, padx=14, pady=14)
heading = tk.Label(surface, text="NEON UI", bg="#090814", fg="#FFFFFF",
                   font=("Segoe UI", 25, "bold"))
surface.add_widget(heading, x=28, y=24)
status = tk.Label(surface, text="Clique no botão ou escolha uma aba.",
                  bg="#090814", fg="#FFFFFF")
surface.add_widget(status, x=30, y=178)
button = NeonButton(surface, "Botão configurável",
                    command=lambda: status.configure(text="Ação executada"), style=settings)
surface.add_widget(button, x=30, y=122)
tabs = NeonTabBar(surface, [("home", "Início"), ("effects", "Efeitos"), ("about", "Sobre")],
                  lambda key: status.configure(text=f"Aba selecionada: {key}"), style=settings)
surface.add_widget(tabs, x=30, y=228)
root.mainloop()
