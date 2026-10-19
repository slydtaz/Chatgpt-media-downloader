from __future__ import annotations

import os
import re
import math
import queue
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Callable

from .config import (
    APP_DATA, BASELINE_CONFIG_PATH, CONFIG_PATH, INSTALL_ID_PATH, INSTALL_ROOT, LOG_DIR,
    PRODUCT_ID, TEMP_DIR, TOOLS_DIR, VENDOR, VERSION, DEFAULT_CONFIG, IS_FROZEN,
    ensure_install_id, load_config, load_installation_baseline, save_config,
)
from .dependencies import inspect_tool
from .downloader import Downloader, validate_bitrate, validate_quality
from .platform import detect_system, detect_system_theme, is_supported
from .security import safe_filename_part, validate_url
from .playlist import PlaylistInfo, format_duration, inspect_playlist
from .updater import UpdateError, check_latest, install_tool_from_release
from .app_update import (
    AppUpdate, AppUpdateError, check_for_update, check_repair_candidate,
    prepare_update, schedule_apply_update,
)
from .uninstall import launch_uninstaller


PALETTES = {
    "dark": {"bg":"#090B18","panel":"#121629","panel2":"#191F38","field":"#0C1122","fg":"#F4F5FF","muted":"#A0A9C3","border":"#2B3150","accent":"#8B5CF6","accent2":"#D946EF","accent_fg":"#FFFFFF","good":"#34D399","warn":"#FBBF24","bad":"#FB7185","button":"#202744","button_hover":"#30385D","input_fg":"#F8FAFF","space":"#60A5FA","pink":"#F472B6"},
    "light": {"bg":"#F3F5FA","panel":"#FFFFFF","panel2":"#E8EDF6","field":"#F8FAFD","fg":"#12182A","muted":"#63718A","border":"#D7DFEB","accent":"#6D5DFB","accent2":"#EC4899","accent_fg":"#FFFFFF","good":"#047857","warn":"#B45309","bad":"#BE123C","button":"#E8EDF6","button_hover":"#D7DFEB","input_fg":"#12182A","space":"#3B82F6","pink":"#DB2777"},
    "oled": {"bg":"#000000","panel":"#08090D","panel2":"#111318","field":"#050608","fg":"#F5F7FA","muted":"#9AA1AD","border":"#24262D","accent":"#8B5CF6","accent2":"#D946EF","accent_fg":"#FFFFFF","good":"#34D399","warn":"#FBBF24","bad":"#FB7185","button":"#191B21","button_hover":"#252831","input_fg":"#FFFFFF","space":"#60A5FA","pink":"#F472B6"},
}


def _valid_hex_color(value: str) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", str(value or "").strip()))


def _blend_hex(color: str, toward: str, amount: float = 0.18) -> str:
    try:
        a = tuple(int(color[i:i+2], 16) for i in (1,3,5))
        b = tuple(int(toward[i:i+2], 16) for i in (1,3,5))
        return "#%02X%02X%02X" % tuple(round(x*(1-amount)+y*amount) for x,y in zip(a,b))
    except (ValueError, TypeError, IndexError):
        return color


def _contrast_text(value: str) -> str:
    try:
        rgb=[int(value[i:i+2],16)/255 for i in (1,3,5)]
        lin=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
        return "#11131A" if 0.2126*lin[0]+0.7152*lin[1]+0.0722*lin[2] > 0.42 else "#FFFFFF"
    except (ValueError, TypeError, IndexError):
        return "#FFFFFF"


class Tooltip:
    _instances = weakref.WeakSet()

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 2000, click_to_pin: bool = True):
        self.widget = widget
        self._instances.add(self)
        self.text = text
        self.delay_ms = delay_ms
        self._job = None
        self._window = None
        self._pinned = False
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        if click_to_pin:
            widget.bind("<Button-1>", self._toggle, add="+")

    @classmethod
    def dismiss_all(cls):
        """Hide both hover and pinned tooltips when the user changes pages."""
        for tooltip in tuple(cls._instances):
            tooltip._cancel()
            tooltip._pinned = False
            tooltip.hide()

    def _enter(self, _event=None):
        self._cancel()
        self._job = self.widget.after(self.delay_ms, self.show)

    def _leave(self, _event=None):
        self._cancel()
        if not self._pinned:
            self.hide()

    def _toggle(self, _event=None):
        if self._window and self._window.winfo_exists():
            self._pinned = not self._pinned
            if not self._pinned:
                self.hide()
        else:
            self._pinned = True
            self.show()

    def _cancel(self):
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def show(self):
        self._job = None
        if self._window and self._window.winfo_exists():
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
            y = self.widget.winfo_rooty() + 2
            top = tk.Toplevel(self.widget)
            top.wm_overrideredirect(True)
            top.wm_geometry(f"+{x}+{y}")
            label = tk.Label(top, text=self.text, justify="left", wraplength=330,
                             bg="#0B1220", fg="#FFFFFF", relief="solid", bd=1,
                             padx=10, pady=8, font=("Segoe UI", 9))
            label.pack()
            self._window = top
        except tk.TclError:
            pass

    def hide(self):
        if self._window:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
        self._window = None


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")
        self.canvas.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"), add="+")
        self.canvas.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(1, "units"), add="+")

    def _wheel(self, event):
        try:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except (tk.TclError, ZeroDivisionError):
            pass


def _rounded_polygon(x1: float, y1: float, x2: float, y2: float, radius: float) -> list[float]:
    """Coordinates for a smooth rounded rectangle drawn on a Tk canvas."""
    r = max(2.0, min(radius, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    return [
        x1 + r, y1, x2 - r, y1,
        x2 - r / 2, y1, x2, y1 + r / 2,
        x2, y1 + r, x2, y2 - r,
        x2, y2 - r / 2, x2 - r / 2, y2,
        x2 - r, y2, x1 + r, y2,
        x1 + r / 2, y2, x1, y2 - r / 2,
        x1, y2 - r, x1, y1 + r,
        x1, y1 + r / 2, x1 + r / 2, y1,
    ]


class RoundedCard(ttk.Frame):
    """Rounded panel painted on a Canvas, keeping native ttk widgets for content."""

    def __init__(self, parent, app, padding=16, surface="panel", backdrop="bg"):
        super().__init__(parent, style="RoundedCard.TFrame", padding=padding)
        self.app = app
        self.surface_key = surface
        self.backdrop_key = backdrop
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._canvas._rounded_card_background = True
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bind("<Configure>", lambda _event: self.redraw(), add="+")
        self.app.rounded_cards.append(self)
        self.redraw()

    def redraw(self):
        try:
            width = max(2, self.winfo_width())
            height = max(2, self.winfo_height())
            colors = self.app.colors
            backdrop = colors.get(self.backdrop_key, colors["bg"])
            surface = colors.get(self.surface_key, colors["panel"])
            self._canvas.configure(background=backdrop)
            self._canvas.delete("surface")
            if width > 8 and height > 8:
                self._canvas.create_polygon(
                    _rounded_polygon(1, 1, width - 2, height - 2, 30),
                    smooth=True, splinesteps=14, fill=surface,
                    outline=colors.get("border", surface), width=1, tags="surface",
                )
            self._canvas.lower()
        except tk.TclError:
            pass


class IconNavButton(tk.Canvas):
    """Compact launcher-style icon button with a soft active pill and hover scale."""

    def __init__(self, parent, app, key: str, glyph: str, command: Callable[[], None]):
        super().__init__(
            parent, width=48, height=44, bd=0, highlightthickness=0,
            background=app.colors["panel2"], cursor="hand2",
        )
        self.app = app
        self.page_key = key
        self.glyph = glyph
        self.command = command
        self.active = False
        self.hovered = False
        self._scale = 1.0
        self._target_scale = 1.0
        self._scale_job = None
        self.bind("<Configure>", lambda _event: self._draw(), add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<Button-1>", self._on_click, add="+")
        self._draw()

    def set_active(self, active: bool):
        self.active = bool(active)
        self._target_scale = 1.06 if self.active else (1.03 if self.hovered else 1.0)
        self._draw()
        self._animate_scale()

    def refresh_theme(self):
        self.configure(background=self.app.colors["panel2"])
        self._draw()

    def _on_enter(self, _event=None):
        self.hovered = True
        self._target_scale = 1.10 if not self.active else 1.08
        self._animate_scale()
        self._draw()

    def _on_leave(self, _event=None):
        self.hovered = False
        self._target_scale = 1.06 if self.active else 1.0
        self._animate_scale()
        self._draw()

    def _on_click(self, _event=None):
        self.command()

    def _animate_scale(self):
        if self._scale_job is not None:
            try:
                self.after_cancel(self._scale_job)
            except tk.TclError:
                pass
        if not self.app.config.get("animations_enabled", True):
            self._scale = self._target_scale
            self._scale_job = None
            self._draw()
            return
        delta = self._target_scale - self._scale
        if abs(delta) < 0.012:
            self._scale = self._target_scale
            self._scale_job = None
            self._draw()
            return
        self._scale += delta * 0.34
        self._draw()
        self._scale_job = self.after(16, self._animate_scale)

    def _draw(self):
        try:
            self.delete("all")
            width = max(48, self.winfo_width())
            height = max(42, self.winfo_height())
            colors = self.app.colors
            panel = colors.get("panel2", "#191F38")
            accent = colors.get("accent", "#8B5CF6")
            if self.active or self.hovered:
                fill = _blend_hex(accent, panel, 0.68 if self.active else 0.84)
                self.create_polygon(
                    _rounded_polygon(5, 2, width - 5, height - 2, 13),
                    smooth=True, splinesteps=12, fill=fill, outline="",
                )
            if self.active:
                self.create_polygon(
                    _rounded_polygon(1, height / 2 - 8, 4, height / 2 + 8, 2),
                    fill=colors.get("pink", accent), outline="",
                )
            icon_color = accent if self.active else (colors["fg"] if self.hovered else colors["muted"])
            size = max(15, int(18 * self._scale))
            self.create_text(
                width / 2, height / 2, text=self.glyph,
                fill=icon_color, font=("Segoe UI Symbol", size, "bold"),
            )
        except tk.TclError:
            pass


class MediaDownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.system = detect_system()
        self.config = load_config()
        self.install_id = ensure_install_id()
        from .logging_utils import setup_logging
        self.logger = setup_logging(LOG_DIR)
        self.logger.info("Inicialização: %s", self.system.architecture_label)

        self.root.title(f"ChatGPT Media Downloader v{VERSION}")
        self.root.geometry("1220x820")
        self.root.minsize(1000, 680)

        self.style = ttk.Style(root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.palette_name = "light"
        self.colors: dict[str, str] = {}
        self._apply_theme(self.config.get("theme", "system"))

        self.ui_queue: queue.Queue = queue.Queue()
        self.download_thread: threading.Thread | None = None
        self.downloader: Downloader | None = None
        self.install_thread: threading.Thread | None = None
        self.current_page = "home"
        self._visible_page: str | None = None
        self._page_animation_job = None
        self._page_animation_target: str | None = None
        self._hero_visual_phase = 0.0
        self.page_frames: dict[str, ttk.Frame] = {}
        self.settings_vars: dict[str, tk.StringVar] = {}
        self.nav_buttons: dict[str, tk.Widget] = {}
        self.rounded_cards: list[RoundedCard] = []
        self.log_history: list[tuple[str, bool]] = []
        self._developer_mode_active = bool(self.config.get("developer_mode", False))
        self.developer_mode_var = tk.BooleanVar(value=self._developer_mode_active)
        self.animations_enabled_var = tk.BooleanVar(value=bool(self.config.get("animations_enabled", True)))
        self.log_mode_var = tk.StringVar(value="CONSOLE TÉCNICO" if self._developer_mode_active else "RESUMO DE ATIVIDADE")
        self.dep_infos = {}
        self._dependencies_checked = False
        self._dependency_refresh_thread: threading.Thread | None = None
        self._dependency_refresh_pending = False
        self._last_dependency_refresh = 0.0
        self.playlist_info: PlaylistInfo | None = None
        self.playlist_items: list[dict] = []
        self.playlist_iid_to_position: dict[str, int] = {}
        self.playlist_analysis_thread: threading.Thread | None = None
        self.playlist_progress_by_position: dict[int, float] = {}
        self.playlist_completed_positions: set[int] = set()
        self.active_downloaders: dict[str, Downloader] = {}
        self.active_downloaders_lock = threading.Lock()
        self.cancel_requested = threading.Event()
        self._playlist_title = "Playlist"
        self._app_update_info: AppUpdate | None = None
        self._app_update_checking = False
        self._app_update_busy = False
        self._app_update_prompt_open = False
        self._app_update_show_current = False
        self.update_open_after_var = tk.BooleanVar(value=bool(self.config.get("update_open_after", True)))
        self.update_check_on_startup_var = tk.BooleanVar(value=bool(self.config.get("update_check_on_startup", True)))

        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="Automático — vídeo")
        self.quality_var = tk.StringVar(value=f"{self.config['auto_video_quality']}p")
        self.status_var = tk.StringVar(value="Pronto para baixar")
        self.percent_var = tk.DoubleVar(value=0)
        self.speed_var = tk.StringVar(value="—")
        self.size_var = tk.StringVar(value="—")
        self.eta_var = tk.StringVar(value="—")
        self.stage_var = tk.StringVar(value="Aguardando")
        self.dependency_state_var = tk.StringVar(value="Verificando dependências")
        self.playlist_strategy_var = tk.StringVar(value=self._strategy_label(self.config.get("playlist_strategy", "sequential")))
        self.playlist_parallelism_var = tk.StringVar(value=str(self.config.get("playlist_parallelism", 3)))
        self.playlist_search_var = tk.StringVar(value="")
        self.playlist_editor_mode_var = tk.StringVar(value="Vídeo")
        self.playlist_editor_quality_var = tk.StringVar(value=f"{self.config['auto_video_quality']}p")
        self.playlist_editor_include_var = tk.BooleanVar(value=True)
        self.playlist_summary_var = tk.StringVar(value="Nenhuma playlist analisada")
        self.playlist_selected_summary_var = tk.StringVar(value="0 selecionados")
        self.playlist_editor_hint_var = tk.StringVar(value="Selecione um item para editar suas opções.")

        self._build_shell()
        self._build_home()
        self._build_playlist_page()
        self._build_settings()
        self._build_dependencies()
        self._build_updates()
        self._build_help()
        self._build_developer()
        self.show_page("home")
        self._apply_theme(self.config.get("theme", "dark"))
        self._refresh_dependencies()
        self.root.report_callback_exception = self._report_callback_exception
        self._poll_queue()
        # Small GPU-free Canvas animation inspired by SKlauncher 4.0's cosmic theme.
        self._hero_animation_job = self.root.after(180, self._animate_hero_visual)
        self.root.after(2200, self._maybe_start_update_check)

    # ---------- Theme ----------
    def _resolve_theme(self, requested: str) -> str:
        if requested == "system":
            return detect_system_theme()
        return requested if requested in PALETTES else "dark"

    def _apply_theme(self, requested: str):
        self.config["theme"] = requested if requested in {"system","dark","light","oled"} else "dark"
        self.palette_name = self._resolve_theme(self.config["theme"])
        c = dict(PALETTES[self.palette_name])
        accent = str(self.config.get("accent_color","#8B5CF6") or "#8B5CF6").strip()
        if _valid_hex_color(accent):
            c["accent"] = accent.upper()
            c["accent2"] = _blend_hex(accent.upper(),"#FFFFFF" if self.palette_name!="light" else "#000000",0.18)
            c["accent_fg"] = _contrast_text(accent.upper())
        else:
            self.config["accent_color"] = "#8B5CF6"
        self.colors = c
        compact = self.config.get("ui_density","comfortable") == "compact"
        nav_pad = (11,7) if compact else (14,10)
        self.root.configure(bg=c["bg"])
        self.style.configure(".",font=("Segoe UI",9 if compact else 10),background=c["bg"],foreground=c["fg"])
        self.style.configure("TFrame",background=c["bg"])
        self.style.configure("Card.TFrame",background=c["panel"],bordercolor=c["panel"],relief="flat",borderwidth=0)
        self.style.configure("Hero.TFrame",background=c["panel2"],bordercolor=c["panel2"],relief="flat",borderwidth=0)
        self.style.configure("Sidebar.TFrame",background=c["panel2"],bordercolor=c["border"],relief="flat",borderwidth=0)
        self.style.configure("RoundedCard.TFrame",background=c["bg"],borderwidth=0,relief="flat")
        self.style.configure("Topbar.TFrame",background=c["bg"])
        self.style.configure("MiniCard.TFrame",background=c["panel2"],bordercolor=c["panel2"],relief="flat",borderwidth=0)
        self.style.configure("TLabel",background=c["bg"],foreground=c["fg"])
        self.style.configure("Muted.TLabel",background=c["bg"],foreground=c["muted"])
        self.style.configure("Card.TLabel",background=c["panel"],foreground=c["fg"])
        self.style.configure("Hero.TLabel",background=c["panel2"],foreground=c["fg"])
        self.style.configure("HeroMuted.TLabel",background=c["panel2"],foreground=c["muted"])
        self.style.configure("Eyebrow.TLabel",background=c["bg"],foreground=c["accent"],font=("Segoe UI",9,"bold"))
        self.style.configure("HeroEyebrow.TLabel",background=c["panel2"],foreground=c["accent"],font=("Segoe UI",9,"bold"))
        self.style.configure("SidebarTitle.TLabel",background=c["panel2"],foreground=c["fg"],font=("Segoe UI",13,"bold"))
        self.style.configure("SidebarMuted.TLabel",background=c["panel2"],foreground=c["muted"],font=("Segoe UI",8,"bold"))
        self.style.configure("Title.TLabel",background=c["bg"],foreground=c["fg"],font=("Segoe UI",25,"bold"))
        self.style.configure("PageTitle.TLabel",background=c["bg"],foreground=c["fg"],font=("Segoe UI",22,"bold"))
        self.style.configure("Subtitle.TLabel",background=c["bg"],foreground=c["muted"],font=("Segoe UI",9))
        self.style.configure("CardTitle.TLabel",background=c["panel"],foreground=c["fg"],font=("Segoe UI",11 if compact else 12,"bold"))
        self.style.configure("HeroTitle.TLabel",background=c["panel2"],foreground=c["fg"],font=("Segoe UI",20 if compact else 23,"bold"))
        self.style.configure("MiniLabel.TLabel",background=c["panel2"],foreground=c["muted"],font=("Segoe UI",8 if compact else 9,"bold"))
        self.style.configure("MiniValue.TLabel",background=c["panel2"],foreground=c["fg"],font=("Segoe UI",11 if compact else 12,"bold"))
        self.style.configure("Accent.TButton",font=("Segoe UI",10,"bold"),padding=(17,10 if compact else 12),foreground=c["accent_fg"],background=c["accent"])
        self.style.map("Accent.TButton",background=[("active",c["accent2"]),("disabled",c["border"]),("!disabled",c["accent"])],foreground=[("disabled",c["muted"]),("!disabled",c["accent_fg"])])
        self.style.configure("Secondary.TButton",padding=(11,7 if compact else 9),foreground=c["fg"],background=c["button"])
        self.style.map("Secondary.TButton",background=[("active",c["button_hover"]),("!disabled",c["button"])])
        self.style.configure("Nav.TButton",padding=nav_pad,anchor="w",foreground=c["muted"],background=c["panel2"],borderwidth=0)
        self.style.map("Nav.TButton",background=[("active",c["button_hover"]),("!disabled",c["panel2"])],foreground=[("active",c["fg"]),("!disabled",c["muted"])])
        self.style.configure("Selected.Nav.TButton",padding=nav_pad,anchor="w",foreground=c["accent"],background=c["button"],borderwidth=1,relief="flat",font=("Segoe UI",10,"bold"))
        self.style.map("Selected.Nav.TButton",background=[("active",c["button_hover"]),("!disabled",c["button"])],foreground=[("!disabled",c["accent"])])
        self.style.configure("TEntry",padding=10 if not compact else 7,fieldbackground=c["field"],foreground=c["input_fg"],bordercolor=c["border"])
        self.style.configure("TCombobox",padding=8 if not compact else 6,fieldbackground=c["field"],foreground=c["input_fg"],arrowcolor=c["accent"])
        self.style.map("TCombobox",fieldbackground=[("readonly",c["field"])],foreground=[("readonly",c["input_fg"])])
        self.style.configure("TProgressbar",thickness=10 if compact else 12,troughcolor=c["panel2"],background=c["accent"])
        self.style.configure("Treeview",background=c["field"],fieldbackground=c["field"],foreground=c["fg"],rowheight=24 if compact else 31,bordercolor=c["border"])
        self.style.map("Treeview",background=[("selected",c["accent2"])],foreground=[("selected",c["accent_fg"])])
        self.style.configure("Treeview.Heading",background=c["panel2"],foreground=c["fg"],relief="flat",padding=(8,7),font=("Segoe UI",9,"bold"))
        self.style.map("Treeview.Heading",background=[("active",c["button_hover"])])
        self.style.configure("Status.TLabel",background=c["panel2"],foreground=c["fg"],padding=8)
        self.style.configure("SectionBadge.TLabel",background=c["panel2"],foreground=c["accent"],padding=(8,4))
        self.style.configure("Help.TButton",width=2,padding=2,foreground=c["accent"],background=c["panel"],borderwidth=0)
        self.style.configure("Danger.TButton",foreground="#FFFFFF",background=c["bad"])
        self.style.map("Danger.TButton",background=[("active",c["bad"]),("!disabled",c["bad"])])
        self.style.configure("TCheckbutton",background=c["panel"],foreground=c["fg"],padding=(2,3))
        self.style.map("TCheckbutton",background=[("active",c["panel"])],foreground=[("disabled",c["muted"])])
        if hasattr(self,"log_text"):
            self.log_text.configure(bg=c["field"],fg=c["fg"],insertbackground=c["fg"],selectbackground=c["accent"],selectforeground=c["accent_fg"])
        if hasattr(self,"dep_badge"):
            self.dep_badge.configure(bg=c["panel2"],fg=c["muted"])
        if hasattr(self,"playlist_warning"):
            self.playlist_warning.configure(bg=c["panel2"],fg=c["warn"])
        if hasattr(self,"hero_accent_bar"):
            self.hero_accent_bar.configure(bg=c["accent"])
        def tint(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Canvas):
                    try:
                        if getattr(child, "_rounded_card_background", False):
                            child.master.redraw()
                        elif hasattr(child, "refresh_theme"):
                            child.refresh_theme()
                        elif child is getattr(self, "hero_visual", None):
                            child.configure(background=c["panel2"], highlightbackground=c["panel2"], highlightcolor=c["panel2"])
                        else:
                            child.configure(background=c["bg"], highlightbackground=c["bg"], highlightcolor=c["bg"])
                    except tk.TclError:
                        pass
                tint(child)
        try:
            tint(self.root)
        except tk.TclError:
            pass

    # ---------- Shell ----------
    def _build_shell(self):
        outer=ttk.Frame(self.root,padding=13)
        outer.pack(fill="both",expand=True)
        self.shell=outer
        sidebar=ttk.Frame(outer,style="Sidebar.TFrame",padding=(8,13,8,12),width=76)
        sidebar.pack(side="left",fill="y",padx=(0,12))
        sidebar.pack_propagate(False)
        self.sidebar=sidebar
        brand=ttk.Frame(sidebar,style="Sidebar.TFrame")
        brand.pack(fill="x",pady=(0,20))
        mark=tk.Label(brand,text="✦",bg=self.colors["accent"],fg=self.colors["accent_fg"],font=("Segoe UI Symbol",19,"bold"),width=2,height=1,padx=2,pady=4)
        mark.pack(anchor="center")
        ttk.Separator(sidebar).pack(fill="x",pady=(0,12))
        for key,glyph,label,tip in [
            ("home","⌂","Início","Baixe vídeo ou áudio, acompanhe o progresso e consulte o resumo da atividade."),
            ("playlist","▤","Playlists","Analise uma playlist, escolha itens e personalize formato e qualidade por mídia."),
            ("settings","⚙","Aparência","Personalize as cores espaciais, o tema, as pastas e o desempenho."),
            ("dependencies","◈","Dependências","Confira e configure yt-dlp, FFmpeg e FFprobe."),
            ("updates","⟳","Atualizações","Confira versões, atualize o aplicativo ou restaure arquivos oficiais."),
            ("help","?","Ajuda","Guias rápidos, opções de qualidade, playlists e segurança."),
            ("developer","⌘","Diagnóstico","Versão, caminhos, dados técnicos e desinstalação."),
        ]:
            button=IconNavButton(sidebar,self,key,glyph,lambda k=key:self.show_page(k))
            button.pack(anchor="center",pady=3)
            self.nav_buttons[key]=button
            Tooltip(button,f"{label}\n{tip}",delay_ms=450,click_to_pin=False)
        spacer=ttk.Frame(sidebar,style="Sidebar.TFrame")
        spacer.pack(fill="both",expand=True)
        ttk.Separator(sidebar).pack(fill="x",pady=(12,9))
        self.dep_badge=tk.Label(sidebar,text="●",bg=self.colors["panel2"],fg=self.colors["muted"],anchor="center",font=("Segoe UI",10,"bold"),padx=7,pady=7)
        self.dep_badge.pack(fill="x",pady=(0,5))
        Tooltip(self.dep_badge,"Veja a aba Dependências para conferir o estado atual.",delay_ms=450,click_to_pin=False)
        ttk.Label(sidebar,text=f"v{VERSION}",style="SidebarMuted.TLabel",anchor="center",font=("Segoe UI",7)).pack(fill="x")
        content_wrap=ttk.Frame(outer)
        content_wrap.pack(side="left",fill="both",expand=True)
        self.content_wrap=content_wrap
        header=ttk.Frame(content_wrap,style="Topbar.TFrame")
        header.pack(fill="x",pady=(4,16))
        header_left=ttk.Frame(header,style="Topbar.TFrame")
        header_left.pack(side="left",fill="x",expand=True)
        ttk.Label(header_left,text="MEDIA WORKSPACE  /  DOWNLOADS",style="Eyebrow.TLabel").pack(anchor="w",pady=(0,3))
        self.page_title_var=tk.StringVar(value="Início")
        ttk.Label(header_left,textvariable=self.page_title_var,style="PageTitle.TLabel").pack(anchor="w")
        self.page_subtitle_var=tk.StringVar(value="Seu espaço para vídeos, músicas e playlists.")
        ttk.Label(header_left,textvariable=self.page_subtitle_var,style="Muted.TLabel").pack(anchor="w",pady=(2,0))
        header_actions=ttk.Frame(header,style="Topbar.TFrame")
        header_actions.pack(side="right",anchor="n",padx=(10,0),pady=(9,0))
        ttk.Label(header_actions,text=f"v{VERSION}",style="SectionBadge.TLabel").pack(side="left",padx=(0,8))
        self.header_update_btn=ttk.Button(header_actions,text="Atualizações  ↗",style="Secondary.TButton",command=lambda:self.show_page("updates"))
        self.header_update_btn.pack(side="left")
        self.pages_area=ttk.Frame(content_wrap)
        self.pages_area.pack(fill="both",expand=True)
    def _card(self, parent, padding=16):
        return RoundedCard(parent, self, padding=padding)

    def _build_home(self):
        frame=ttk.Frame(self.pages_area)
        self.page_frames["home"]=frame
        hero=RoundedCard(frame,self,padding=(22,20),surface="panel2")
        hero.pack(fill="x",pady=(0,13))
        self.hero_accent_bar=tk.Frame(hero,bg=self.colors["accent"],width=4,bd=0,highlightthickness=0)
        self.hero_accent_bar.pack(side="left",fill="y",padx=(0,18))
        self.hero_visual = tk.Canvas(
            hero, width=108, height=112, bg=self.colors["panel2"],
            highlightthickness=0, bd=0,
        )
        self.hero_visual.pack(side="right", fill="y", padx=(12, 0))
        hero_body=ttk.Frame(hero,style="Hero.TFrame")
        hero_body.pack(side="left",fill="both",expand=True)
        hero_top=ttk.Frame(hero_body,style="Hero.TFrame")
        hero_top.pack(fill="x")
        ttk.Label(hero_top,text="DOWNLOAD WORKSPACE",style="HeroEyebrow.TLabel").pack(side="left")
        ttk.Label(hero_top,text="VÍDEO  ·  ÁUDIO  ·  PLAYLISTS",style="HeroMuted.TLabel",font=("Segoe UI",8,"bold")).pack(side="right")
        ttk.Label(hero_body,text="Sua mídia. Do seu jeito.",style="HeroTitle.TLabel").pack(anchor="w",pady=(7,2))
        ttk.Label(hero_body,text="Cole um link, personalize a saída e acompanhe tudo em um só lugar.",style="HeroMuted.TLabel",wraplength=760).pack(anchor="w",pady=(0,15))
        self.url_entry=ttk.Entry(hero_body,textvariable=self.url_var,font=("Segoe UI",12))
        self.url_entry.pack(fill="x")
        self.url_entry.focus_set()
        self.url_entry.bind("<Return>",lambda _e:self.start_download())
        self.url_var.trace_add("write",self._update_playlist_warning)
        self.playlist_warning=tk.Label(hero_body,text="⚠  Link de playlist detectado — analise os itens antes de baixar.",bg=self.colors["panel2"],fg=self.colors["warn"],anchor="w",font=("Segoe UI",9,"bold"),padx=3)
        self.playlist_warning.pack(fill="x",pady=(7,0))
        self.playlist_warning.pack_forget()
        controls=ttk.Frame(hero_body,style="Hero.TFrame")
        controls.pack(fill="x",pady=(13,0))
        mode_box=ttk.Frame(controls,style="Hero.TFrame")
        mode_box.pack(side="left",fill="x",expand=True)
        ttk.Label(mode_box,text="FORMATO",style="MiniLabel.TLabel").pack(anchor="w",pady=(0,4))
        self.mode=ttk.Combobox(mode_box,textvariable=self.mode_var,state="readonly",values=["Automático — vídeo","Vídeo","Música — MP3"],width=23)
        self.mode.pack(anchor="w")
        self.mode.bind("<<ComboboxSelected>>",lambda _e:self._sync_quality())
        quality_box=ttk.Frame(controls,style="Hero.TFrame")
        quality_box.pack(side="left",fill="x",expand=True,padx=(14,0))
        ttk.Label(quality_box,text="QUALIDADE / BITRATE",style="MiniLabel.TLabel").pack(anchor="w",pady=(0,4))
        self.quality=ttk.Combobox(quality_box,textvariable=self.quality_var,state="readonly",width=19)
        self.quality.pack(anchor="w")
        self._sync_quality()
        buttons=ttk.Frame(controls,style="Hero.TFrame")
        buttons.pack(side="right",anchor="s",padx=(12,0))
        self.download_btn=ttk.Button(buttons,text="↓  BAIXAR AGORA",style="Accent.TButton",command=self.start_download)
        self.download_btn.pack(side="right")
        self.analyze_playlist_btn=ttk.Button(buttons,text="Analisar playlist",style="Secondary.TButton",command=self._start_playlist_analysis)
        self.analyze_playlist_btn.pack(side="right",padx=(0,8))
        progress_card=self._card(frame,16)
        progress_card.pack(fill="x",pady=(0,13))
        pr=ttk.Frame(progress_card,style="Card.TFrame")
        pr.pack(fill="x")
        ttk.Label(pr,text="Sessão atual",style="CardTitle.TLabel").pack(side="left")
        self.percent_label=ttk.Label(pr,text="0%",style="CardTitle.TLabel")
        self.percent_label.pack(side="right")
        self.progress=ttk.Progressbar(progress_card,maximum=100,variable=self.percent_var)
        self.progress.pack(fill="x",pady=(10,14))
        metrics=ttk.Frame(progress_card,style="Card.TFrame")
        metrics.pack(fill="x")
        for label,var in (("STATUS",self.status_var),("VELOCIDADE",self.speed_var),("TAMANHO",self.size_var),("TEMPO RESTANTE",self.eta_var),("ETAPA",self.stage_var)):
            box=RoundedCard(metrics,self,padding=(10,9),surface="panel2",backdrop="panel")
            box.pack(side="left",fill="both",expand=True,padx=(0,7))
            ttk.Label(box,text=label,style="MiniLabel.TLabel").pack(anchor="w")
            ttk.Label(box,textvariable=var,style="MiniValue.TLabel",wraplength=140).pack(anchor="w",pady=(4,0))
        log_card=self._card(frame,13)
        log_card.pack(fill="both",expand=True)
        top_log=ttk.Frame(log_card,style="Card.TFrame")
        top_log.pack(fill="x")
        ttk.Label(top_log,text="Console de atividade",style="CardTitle.TLabel").pack(side="left")
        ttk.Label(top_log,textvariable=self.log_mode_var,style="Muted.TLabel",font=("Segoe UI",8,"bold")).pack(side="left",padx=(9,0),pady=(2,0))
        ttk.Button(top_log,text="Limpar",style="Secondary.TButton",command=self._clear_log).pack(side="right")
        log_frame=ttk.Frame(log_card,style="Card.TFrame")
        log_frame.pack(fill="both",expand=True,pady=(9,0))
        self.log_text=tk.Text(log_frame,bg=self.colors["field"],fg=self.colors["fg"],insertbackground=self.colors["fg"],selectbackground=self.colors["accent"],selectforeground=self.colors["accent_fg"],relief="flat",wrap="word",font=("Cascadia Code",9),padx=12,pady=10,borderwidth=0)
        self.log_text.pack(side="left",fill="both",expand=True)
        scroll=ttk.Scrollbar(log_frame,orient="vertical",command=self.log_text.yview)
        scroll.pack(side="right",fill="y")
        self.log_text.configure(yscrollcommand=scroll.set,state="disabled")
        footer=ttk.Frame(frame)
        footer.pack(fill="x",pady=(9,0))
        ttk.Label(footer,text="Dica: use o gerenciador de playlists para escolher itens individualmente.",style="Muted.TLabel").pack(side="left")
        self.cancel_btn=ttk.Button(footer,text="Cancelar download",style="Secondary.TButton",command=self.cancel_download,state="disabled")
        self.cancel_btn.pack(side="right")
    @staticmethod
    def _strategy_label(value: str) -> str:
        """Format the stored playlist strategy; callable through class or instance."""
        return "Paralelo (mais rápido)" if value == "parallel" else "Um por vez (recomendado)"

    @staticmethod
    def _strategy_value(label: str) -> str:
        return "parallel" if str(label).startswith("Paralelo") else "sequential"

    def _downloader_options(self) -> dict:
        return {
            "video_container": self.config.get("video_container", "mp4"),
            "retries": int(self.config.get("retries", 5)),
            "concurrent_fragments": int(self.config.get("concurrent_fragments", 4)),
            "subtitle_mode": self.config.get("subtitle_mode", "off"),
        }

    def _build_playlist_page(self):
        frame = ttk.Frame(self.pages_area)
        self.page_frames["playlist"] = frame

        intro = self._card(frame, 14)
        intro.pack(fill="x", pady=(0, 10))
        head = ttk.Frame(intro, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Central de playlists", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(head, textvariable=self.playlist_summary_var, style="Muted.TLabel").pack(side="right")
        ttk.Label(intro, text="Escolha o que baixar e configure vídeo/MP3 separadamente para cada item. Itens sem URL disponível ficam desmarcados.", style="Card.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(6, 0))

        toolbar = self._card(frame, 10)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="Buscar", style="Card.TLabel").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.playlist_search_var, width=24)
        search.pack(side="left", padx=(7, 10))
        self.playlist_search_var.trace_add("write", lambda *_: self._render_playlist_rows())
        ttk.Button(toolbar, text="Marcar visíveis", style="Secondary.TButton", command=lambda: self._set_visible_playlist_included(True)).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Desmarcar visíveis", style="Secondary.TButton", command=lambda: self._set_visible_playlist_included(False)).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Inverter", style="Secondary.TButton", command=self._invert_visible_playlist_items).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Analisar novamente", style="Secondary.TButton", command=self._reanalyze_playlist).pack(side="right")

        table_card = self._card(frame, 8)
        table_card.pack(fill="both", expand=True, pady=(0, 10))
        table_wrap = ttk.Frame(table_card, style="Card.TFrame")
        table_wrap.pack(fill="both", expand=True)
        columns = ("include", "index", "title", "duration", "mode", "quality", "status")
        self.playlist_tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=12, selectmode="extended")
        headings = {"include": "Baixar", "index": "#", "title": "Título", "duration": "Duração", "mode": "Formato", "quality": "Qualidade", "status": "Estado"}
        widths = {"include": 64, "index": 48, "title": 330, "duration": 82, "mode": 90, "quality": 92, "status": 108}
        for column in columns:
            self.playlist_tree.heading(column, text=headings[column])
            self.playlist_tree.column(column, width=widths[column], minwidth=44, anchor="w" if column == "title" else "center", stretch=(column == "title"))
        tree_y = ttk.Scrollbar(table_wrap, orient="vertical", command=self.playlist_tree.yview)
        tree_x = ttk.Scrollbar(table_card, orient="horizontal", command=self.playlist_tree.xview)
        self.playlist_tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)
        self.playlist_tree.pack(side="left", fill="both", expand=True)
        tree_y.pack(side="right", fill="y")
        tree_x.pack(fill="x")
        self.playlist_tree.bind("<<TreeviewSelect>>", self._on_playlist_tree_select)
        self.playlist_tree.bind("<Double-1>", self._on_playlist_tree_double_click)

        editor = self._card(frame, 12)
        editor.pack(fill="x", pady=(0, 8))
        ttk.Label(editor, text="Opções do item selecionado", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(editor, textvariable=self.playlist_editor_hint_var, style="Muted.TLabel", wraplength=760).pack(anchor="w", pady=(3, 8))
        controls = ttk.Frame(editor, style="Card.TFrame")
        controls.pack(fill="x")
        self.playlist_include_check = ttk.Checkbutton(controls, text="Incluir no download", variable=self.playlist_editor_include_var, command=self._apply_playlist_include_toggle)
        self.playlist_include_check.pack(side="left", padx=(0, 14))
        ttk.Label(controls, text="Salvar como", style="Card.TLabel").pack(side="left")
        self.playlist_editor_mode = ttk.Combobox(controls, textvariable=self.playlist_editor_mode_var, values=["Vídeo", "Música — MP3"], state="readonly", width=15)
        self.playlist_editor_mode.pack(side="left", padx=(5, 12))
        self.playlist_editor_mode.bind("<<ComboboxSelected>>", lambda _e: self._sync_playlist_editor_quality())
        ttk.Label(controls, text="Qualidade", style="Card.TLabel").pack(side="left")
        self.playlist_editor_quality = ttk.Combobox(controls, textvariable=self.playlist_editor_quality_var, state="readonly", width=15)
        self.playlist_editor_quality.pack(side="left", padx=(5, 12))
        self._sync_playlist_editor_quality()
        ttk.Button(controls, text="Aplicar aos selecionados", style="Secondary.TButton", command=self._apply_playlist_item_settings).pack(side="right")

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x")
        strategy = ttk.Frame(bottom)
        strategy.pack(side="left", fill="x", expand=True)
        ttk.Label(strategy, text="Execução", style="Muted.TLabel").pack(side="left")
        self.playlist_strategy_combo = ttk.Combobox(strategy, textvariable=self.playlist_strategy_var, values=["Um por vez (recomendado)", "Paralelo (mais rápido)"], state="readonly", width=24)
        self.playlist_strategy_combo.pack(side="left", padx=(6, 6))
        ttk.Label(strategy, text="Simultâneos", style="Muted.TLabel").pack(side="left")
        self.playlist_parallelism_combo = ttk.Combobox(strategy, textvariable=self.playlist_parallelism_var, values=["2", "3", "4", "6"], state="readonly", width=4)
        self.playlist_parallelism_combo.pack(side="left", padx=6)
        ttk.Button(bottom, text="BAIXAR ITENS MARCADOS", style="Accent.TButton", command=self._start_selected_playlist_download).pack(side="right")
        self._render_playlist_rows()

    # ---------- Settings ----------
    def _setting_row(self, parent, key: str, label: str, description: str, browse: str | None = None, choices: list[str] | None = None):
        card = self._card(parent, 12)
        card.pack(fill="x", pady=5)
        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=label, style="CardTitle.TLabel").pack(side="left")
        q = ttk.Button(head, text="?", style="Help.TButton")
        q.pack(side="left", padx=(7, 0))
        Tooltip(q, description)
        self.settings_vars[key] = tk.StringVar(value=str(self.config.get(key, "")))
        if choices:
            editor = ttk.Combobox(card, textvariable=self.settings_vars[key], values=choices, state="readonly")
        else:
            editor = ttk.Entry(card, textvariable=self.settings_vars[key])
        editor.pack(fill="x", pady=(8, 8))
        actions = ttk.Frame(card, style="Card.TFrame")
        actions.pack(fill="x")
        if browse:
            def choose():
                if browse == "dir":
                    value = filedialog.askdirectory(parent=self.root)
                else:
                    value = filedialog.askopenfilename(parent=self.root, filetypes=[("Executáveis", "*.exe" if os.name == "nt" else "*"), ("Todos os arquivos", "*.*")])
                if value:
                    self.settings_vars[key].set(value)
            ttk.Button(actions, text="Selecionar pasta" if browse == "dir" else "Selecionar arquivo", style="Secondary.TButton", command=choose).pack(side="left")
        ttk.Button(actions, text="↺ Padrão", style="Secondary.TButton", command=lambda k=key: self.reset_setting(k, "default")).pack(side="right", padx=(7, 0))
        ttk.Button(actions, text="⏮ Inicial", style="Secondary.TButton", command=lambda k=key: self.reset_setting(k, "baseline")).pack(side="right")

    def _build_settings(self):
        frame=ttk.Frame(self.pages_area)
        self.page_frames["settings"]=frame
        scroll=ScrollableFrame(frame)
        scroll.pack(fill="both",expand=True)
        body=scroll.body
        ttk.Label(body,text="Personalize a experiência e configure o comportamento do downloader.",style="Subtitle.TLabel").pack(anchor="w",pady=(0,12))
        appearance=self._card(body,15)
        appearance.pack(fill="x",pady=(0,12))
        ttk.Label(appearance,text="Aparência",style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(appearance,text="Tema, cor de destaque e densidade da interface ficam salvos no seu perfil.",style="Card.TLabel",wraplength=780,justify="left").pack(anchor="w",pady=(4,11))
        self.settings_vars["theme"]=tk.StringVar(value=self._display_setting_value("theme",self.config.get("theme","dark")))
        self.settings_vars["ui_density"]=tk.StringVar(value=self._display_setting_value("ui_density",self.config.get("ui_density","comfortable")))
        theme_density=ttk.Frame(appearance,style="Card.TFrame")
        theme_density.pack(fill="x")
        theme_box=ttk.Frame(theme_density,style="Card.TFrame")
        theme_box.pack(side="left",fill="x",expand=True,padx=(0,12))
        ttk.Label(theme_box,text="TEMA",style="Muted.TLabel",font=("Segoe UI",8,"bold")).pack(anchor="w",pady=(0,4))
        ttk.Combobox(theme_box,textvariable=self.settings_vars["theme"],values=["Sistema","Escuro","Claro","Preto OLED"],state="readonly").pack(fill="x")
        density_box=ttk.Frame(theme_density,style="Card.TFrame")
        density_box.pack(side="left",fill="x",expand=True)
        ttk.Label(density_box,text="ESPAÇAMENTO",style="Muted.TLabel",font=("Segoe UI",8,"bold")).pack(anchor="w",pady=(0,4))
        ttk.Combobox(density_box,textvariable=self.settings_vars["ui_density"],values=["Confortável","Compacto"],state="readonly").pack(fill="x")
        self.settings_vars["accent_color"]=tk.StringVar(value=str(self.config.get("accent_color","#8B5CF6")))
        accent_row=ttk.Frame(appearance,style="Card.TFrame")
        accent_row.pack(fill="x",pady=(13,0))
        accent_entry_wrap=ttk.Frame(accent_row,style="Card.TFrame")
        accent_entry_wrap.pack(side="left",fill="x",expand=True)
        ttk.Label(accent_entry_wrap,text="COR DE DESTAQUE · HEX",style="Muted.TLabel",font=("Segoe UI",8,"bold")).pack(anchor="w",pady=(0,4))
        ttk.Entry(accent_entry_wrap,textvariable=self.settings_vars["accent_color"]).pack(fill="x")
        ttk.Button(accent_row,text="Escolher cor…",style="Secondary.TButton",command=self._choose_accent_color).pack(side="left",padx=(10,0),anchor="s")
        ttk.Button(accent_row,text="↺ Padrão",style="Secondary.TButton",command=lambda:self.reset_setting("accent_color","default")).pack(side="left",padx=(7,0),anchor="s")
        presets=ttk.Frame(appearance,style="Card.TFrame")
        presets.pack(fill="x",pady=(10,0))
        ttk.Label(presets,text="PALETAS RÁPIDAS",style="Muted.TLabel",font=("Segoe UI",8,"bold")).pack(side="left",padx=(0,10))
        for name,color in (("Violeta","#8B5CF6"),("Azul","#3B82F6"),("Ciano","#06B6D4"),("Verde","#10B981"),("Rosa","#EC4899"),("Âmbar","#F59E0B")):
            ttk.Button(presets,text=name,style="Secondary.TButton",command=lambda c=color:self.settings_vars["accent_color"].set(c)).pack(side="left",padx=(0,5))
        dev_mode_row=ttk.Frame(appearance,style="Card.TFrame")
        dev_mode_row.pack(fill="x",pady=(14,0))
        ttk.Checkbutton(
            dev_mode_row,text="Modo desenvolvedor · saída bruta dos comandos",
            variable=self.developer_mode_var,command=self._preview_developer_mode,
        ).pack(anchor="w")
        ttk.Label(
            dev_mode_row,
            text="Desativado: o painel mostra só o resumo. Ativado: exibe linhas técnicas completas do yt-dlp/FFmpeg e detalhes de diagnóstico.",
            style="Card.TLabel",wraplength=760,justify="left",
        ).pack(anchor="w",padx=(24,0),pady=(2,0))
        ttk.Checkbutton(
            appearance,text="Animações espaciais e transições suaves",
            variable=self.animations_enabled_var,command=self._preview_animations,
        ).pack(anchor="w",pady=(12,0))
        ttk.Label(
            appearance,text="Desative para reduzir movimento e economizar recursos gráficos.",
            style="Card.TLabel",wraplength=760,justify="left",
        ).pack(anchor="w",padx=(24,0),pady=(2,0))
        self.settings_vars["theme"].trace_add("write",lambda *_:self._preview_theme_from_setting())
        self.settings_vars["ui_density"].trace_add("write",lambda *_:self._preview_theme_from_setting())
        self.settings_vars["accent_color"].trace_add("write",lambda *_:self._preview_theme_from_setting())
        self._setting_row(body,"music_dir","Pasta de músicas","Define onde os arquivos MP3 são salvos.",browse="dir")
        self._setting_row(body,"video_dir","Pasta de vídeos","Define onde os vídeos são salvos.",browse="dir")
        self._setting_row(body,"auto_video_quality","Qualidade automática","Resolução alvo do modo Automático/Vídeo.",choices=["480","720","1080","1440","2160"])
        self._setting_row(body,"audio_bitrate","Bitrate de áudio","Qualidade alvo do MP3.",choices=["128","192","320"])
        self._setting_row(body,"yt_dlp_path","Caminho do yt-dlp","Caminho opcional do executável.",browse="file")
        self._setting_row(body,"ffmpeg_path","Caminho do FFmpeg","Executável para mesclar vídeo e converter áudio.",browse="file")
        self._setting_row(body,"ffprobe_path","Caminho do FFprobe","Executável para inspecionar mídia.",browse="file")
        self._setting_row(body,"playlist_strategy","Execução de playlists","Sequencial usa menos recursos; paralelo processa itens simultaneamente.",choices=["Um por vez (recomendado)","Paralelo (mais rápido)"])
        self._setting_row(body,"playlist_parallelism","Downloads simultâneos","Quantidade máxima de itens em paralelo.",choices=["2","3","4","6"])
        self._setting_row(body,"concurrent_fragments","Fragmentos por mídia","Fragmentos baixados simultaneamente.",choices=["1","2","4","8","16"])
        self._setting_row(body,"retries","Tentativas em falhas de rede","Número de tentativas em falhas de rede.",choices=["2","3","5","10"])
        self._setting_row(body,"video_container","Contêiner de vídeo","Formato de contêiner para vídeos.",choices=["mp4","mkv"])
        self._setting_row(body,"subtitle_mode","Legendas de vídeo","Selecione quais legendas salvar.",choices=["Desativadas","Legendas manuais","Manuais + automáticas"])
        actions=ttk.Frame(body)
        actions.pack(fill="x",pady=(12,24))
        ttk.Button(actions,text="Salvar personalização",style="Accent.TButton",command=self.save_settings).pack(side="right")
        ttk.Button(actions,text="Reverter tudo para padrão",style="Secondary.TButton",command=lambda:self.reset_all("default")).pack(side="left")
        ttk.Button(actions,text="Reverter para instalação inicial",style="Secondary.TButton",command=lambda:self.reset_all("baseline")).pack(side="left",padx=(8,0))
        note=self._card(body,12)
        note.pack(fill="x",pady=(0,20))
        ttk.Label(note,text="Como as personalizações são salvas",style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(note,text="Tema, cor principal e espaçamento são aplicados como prévia. Clique em Salvar personalização para gravar tudo. Preferências, pastas e histórico ficam no perfil do usuário.",style="Card.TLabel",wraplength=780,justify="left").pack(anchor="w",pady=(5,0))
    def _choose_accent_color(self):
        current=self.settings_vars.get("accent_color",tk.StringVar(value="#8B5CF6")).get()
        initial=current if _valid_hex_color(current) else "#8B5CF6"
        chosen=colorchooser.askcolor(color=initial,parent=self.root,title="Escolher cor de destaque")[1]
        if chosen and _valid_hex_color(chosen):
            self.settings_vars["accent_color"].set(chosen.upper())

    def _preview_theme_from_setting(self):
        if not hasattr(self,"settings_vars"):
            return
        self.config["theme"]=self._stored_setting_value("theme",self.settings_vars.get("theme",tk.StringVar(value="Escuro")).get())
        self.config["ui_density"]=self._stored_setting_value("ui_density",self.settings_vars.get("ui_density",tk.StringVar(value="Confortável")).get())
        accent=self.settings_vars.get("accent_color",tk.StringVar(value="#8B5CF6")).get()
        if _valid_hex_color(accent):
            self.config["accent_color"]=accent.upper()
        self._apply_theme(self.config.get("theme","dark"))
    def reset_setting(self,key: str,source: str):
        source_config=DEFAULT_CONFIG if source=="default" else load_installation_baseline()
        value=source_config.get(key,DEFAULT_CONFIG.get(key,""))
        self.settings_vars[key].set(self._display_setting_value(key,value))
        if key in {"theme","ui_density","accent_color"}:
            self._preview_theme_from_setting()
    def reset_all(self,source: str):
        source_config=DEFAULT_CONFIG if source=="default" else load_installation_baseline()
        for key in self.settings_vars:
            self.settings_vars[key].set(self._display_setting_value(key,source_config.get(key,DEFAULT_CONFIG.get(key,""))))
        self.developer_mode_var.set(bool(source_config.get("developer_mode",False)))
        self._preview_developer_mode()
        self.animations_enabled_var.set(bool(source_config.get("animations_enabled", True)))
        self._preview_animations()
        self._preview_theme_from_setting()
        messagebox.showinfo("Configurações","Os valores foram revertidos nesta tela. Clique em Salvar personalização para gravá-los.")
    @staticmethod
    def _display_setting_value(key: str,value):
        if key=="playlist_strategy":
            return "Paralelo (mais rápido)" if value=="parallel" else "Um por vez (recomendado)"
        if key=="subtitle_mode":
            return {"off":"Desativadas","manual":"Legendas manuais","all":"Manuais + automáticas"}.get(str(value),"Desativadas")
        if key=="theme":
            return {"system":"Sistema","dark":"Escuro","light":"Claro","oled":"Preto OLED"}.get(str(value),"Escuro")
        if key=="ui_density":
            return {"comfortable":"Confortável","compact":"Compacto"}.get(str(value),"Confortável")
        return str(value)
    @staticmethod
    def _stored_setting_value(key: str,value):
        if key=="playlist_strategy":
            return "parallel" if str(value).startswith("Paralelo") else "sequential"
        if key=="subtitle_mode":
            return {"Desativadas":"off","Legendas manuais":"manual","Manuais + automáticas":"all"}.get(str(value),"off")
        if key=="theme":
            return {"Sistema":"system","Escuro":"dark","Claro":"light","Preto OLED":"oled"}.get(str(value),str(value))
        if key=="ui_density":
            return {"Confortável":"comfortable","Compacto":"compact"}.get(str(value),str(value))
        if key in {"auto_video_quality","audio_bitrate","playlist_parallelism","concurrent_fragments","retries"}:
            try:
                return int(value)
            except (ValueError,TypeError):
                return DEFAULT_CONFIG.get(key)
        return str(value).strip() if isinstance(value,str) else value
    def save_settings(self):
        try:
            q=int(self.settings_vars["auto_video_quality"].get())
            b=int(self.settings_vars["audio_bitrate"].get())
            parallelism=int(self.settings_vars["playlist_parallelism"].get())
            fragments=int(self.settings_vars["concurrent_fragments"].get())
            retries=int(self.settings_vars["retries"].get())
        except ValueError:
            messagebox.showerror("Configuração","Qualidade, bitrate, concorrência, fragmentos e tentativas precisam ser numéricos.")
            return
        if not validate_quality(q) or not validate_bitrate(b) or parallelism not in {2,3,4,6} or fragments not in {1,2,4,8,16} or retries not in {2,3,5,10}:
            messagebox.showerror("Configuração","Verifique os valores permitidos nas listas: qualidade, bitrate, downloads simultâneos, fragmentos e tentativas.")
            return
        accent=str(self.settings_vars.get("accent_color",tk.StringVar(value="#8B5CF6")).get()).strip()
        if not _valid_hex_color(accent):
            messagebox.showerror("Aparência","Informe a cor como HEX de seis dígitos, por exemplo #8B5CF6.")
            return
        new_config=dict(self.config)
        for key in self.settings_vars:
            new_config[key]=self._stored_setting_value(key,self.settings_vars[key].get())
        new_config["accent_color"]=accent.upper()
        new_config["auto_video_quality"]=q
        new_config["developer_mode"]=bool(self.developer_mode_var.get())
        new_config["animations_enabled"]=bool(self.animations_enabled_var.get())
        new_config["audio_bitrate"]=b
        try:
            save_config(new_config)
            self.config=load_config()
            self.developer_mode_var.set(bool(self.config.get("developer_mode",False)))
            self._preview_developer_mode()
            self.animations_enabled_var.set(bool(self.config.get("animations_enabled", True)))
            self._preview_animations()
            self.playlist_strategy_var.set(self._strategy_label(self.config.get("playlist_strategy","sequential")))
            self.playlist_parallelism_var.set(str(self.config.get("playlist_parallelism",3)))
            self._apply_theme(self.config.get("theme","dark"))
            self._sync_quality()
            self._refresh_dependencies(force=True)
            self._append_log("Configurações e aparência salvas.")
            messagebox.showinfo("Configuração","Personalização salva com sucesso.")
        except OSError as exc:
            messagebox.showerror("Configuração",f"Não foi possível salvar: {exc}")
    def _build_dependencies(self):
        frame = ttk.Frame(self.pages_area)
        self.page_frames["dependencies"] = frame
        scroll = ScrollableFrame(frame)
        scroll.pack(fill="both", expand=True)
        body = scroll.body
        ttk.Label(body, text="Dependências locais", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(body, text="A inicialização tenta preparar automaticamente os executáveis compatíveis antes da tela principal. Esta página permite repetir a tentativa ou selecionar arquivos manualmente.", style="TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(0, 15))
        self.dep_cards: dict[str, dict[str, tk.StringVar]] = {}
        for name in ("yt-dlp", "ffmpeg", "ffprobe"):
            card = self._card(body, 14)
            card.pack(fill="x", pady=6)
            head = ttk.Frame(card, style="Card.TFrame")
            head.pack(fill="x")
            ttk.Label(head, text=name.upper(), style="CardTitle.TLabel").pack(side="left")
            status = tk.StringVar(value="Verificando...")
            ttk.Label(head, textvariable=status, style="SectionBadge.TLabel").pack(side="right")
            vars_map = {k: tk.StringVar(value="—") for k in ("path", "version", "arch", "source", "error")}
            self.dep_cards[name] = {"status": status, **vars_map}
            for key, label in (("path", "Caminho"), ("version", "Versão"), ("arch", "Arquitetura"), ("source", "Origem"), ("error", "Detalhes")):
                row = ttk.Frame(card, style="Card.TFrame")
                row.pack(fill="x", pady=1)
                ttk.Label(row, text=f"{label}:", style="Muted.TLabel", width=14).pack(side="left")
                ttk.Label(row, textvariable=vars_map[key], style="Card.TLabel", wraplength=650).pack(side="left", fill="x", expand=True)

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(14, 24))
        self.install_btn = ttk.Button(actions, text="Instalar/Reparar automaticamente", style="Accent.TButton", command=self.install_dependencies_async)
        self.install_btn.pack(side="left")
        ttk.Button(actions, text="Atualizar informações", style="Secondary.TButton", command=lambda: self._refresh_dependencies(force=True)).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Abrir Configurações", style="Secondary.TButton", command=lambda: self.show_page("settings")).pack(side="right")

        info = self._card(body, 12)
        info.pack(fill="x")
        ttk.Label(info, text="Arquitetura primeiro", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(info, text=f"Sistema detectado: {self.system.architecture_label}. O aplicativo não troca para x64/x86 apenas por existir um binário mais novo: ele procura uma build compatível com a arquitetura real.", style="Card.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(4, 0))

    def _refresh_dependencies(self, force: bool = False):
        """Scan tools off the UI thread so opening pages stays responsive."""
        now = time.monotonic()
        current_thread = self._dependency_refresh_thread
        if current_thread and current_thread.is_alive():
            # If settings changed during a scan, repeat with a fresh config once
            # that scan returns instead of applying stale tool paths indefinitely.
            if force:
                self._dependency_refresh_pending = True
            return
        if self._dependencies_checked and not force and now - self._last_dependency_refresh < 10.0:
            return

        system = detect_system()
        config_snapshot = dict(self.config)
        if hasattr(self, "dep_cards"):
            for card in self.dep_cards.values():
                card["status"].set("Verificando...")
        self.dep_badge.configure(text="●", fg=self.colors["muted"])

        def worker():
            infos = {
                "yt-dlp": inspect_tool("yt-dlp", config_snapshot.get("yt_dlp_path", ""), system),
                "ffmpeg": inspect_tool("ffmpeg", config_snapshot.get("ffmpeg_path", ""), system),
                "ffprobe": inspect_tool("ffprobe", config_snapshot.get("ffprobe_path", ""), system),
            }
            self.ui_queue.put(("dep_refresh_done", (system, infos, time.monotonic())))

        self._dependency_refresh_thread = threading.Thread(
            target=worker, name="CGMD-DependencyScan", daemon=True
        )
        self._dependency_refresh_thread.start()

    def _apply_dependency_results(self, payload):
        system, infos, timestamp = payload
        self.system = system
        self.dep_infos = infos
        self._last_dependency_refresh = timestamp
        self._dependencies_checked = True
        count = 0
        for name, info in self.dep_infos.items():
            good = bool(info.path and info.executable_ok and not info.error)
            count += int(good)
            if name in self.dep_cards:
                card = self.dep_cards[name]
                card["status"].set("Pronto" if good else "Não encontrado")
                card["path"].set(str(info.path) if info.path else "—")
                card["version"].set(info.version or "—")
                card["arch"].set(info.architecture or "unknown")
                card["source"].set(info.source or "—")
                card["error"].set(info.error or "—")
        self.dependency_state_var.set(f"Dependências {count}/3")
        if count == 3:
            self.dep_badge.configure(text="●", fg=self.colors["good"])
        else:
            color = self.colors["warn"] if count else self.colors["bad"]
            self.dep_badge.configure(text="●", fg=color)
        if self._dependency_refresh_pending:
            self._dependency_refresh_pending = False
            self._refresh_dependencies(force=True)

    def install_dependencies_async(self):
        if self.download_thread and self.download_thread.is_alive():
            self._append_log("Aguarde o download terminar ou cancele-o antes de atualizar as dependências. Isso evita substituir uma ferramenta em uso.")
            return
        if self.install_thread and self.install_thread.is_alive():
            return
        if not self._dependencies_checked or (self._dependency_refresh_thread and self._dependency_refresh_thread.is_alive()):
            self._append_log("Aguarde a verificação das dependências terminar e tente novamente.")
            return
        self.install_btn.configure(state="disabled")
        self.ui_queue.put(("log", "Iniciando preparação automática das dependências..."))
        self.install_thread = threading.Thread(target=self._install_dependencies_worker, daemon=True)
        self.install_thread.start()

    def _install_dependencies_worker(self):
        for name in ("yt-dlp", "ffmpeg"):
            info = self.dep_infos.get(name)
            if info and info.path and info.executable_ok and not info.error:
                continue
            try:
                def progress(stage, done, total, tool=name):
                    self.ui_queue.put(("dep_progress", (tool, stage, done, total)))
                target, version = install_tool_from_release(name, self.system, progress=progress)
                self.ui_queue.put(("log", f"{name} instalado: {version or target.name}"))
                self.config = load_config()
            except Exception as exc:
                self.ui_queue.put(("log", f"Falha ao instalar {name}: {exc}"))
                self.ui_queue.put(("dep_error", str(exc)))
                break
        self.ui_queue.put(("dep_done", None))

    # ---------- Help / Developer ----------
    # ---------- Application updates / repair ----------
    def _build_updates(self):
        frame = ttk.Frame(self.pages_area)
        self.page_frames["updates"] = frame
        scroll = ScrollableFrame(frame)
        scroll.pack(fill="both", expand=True)
        body = scroll.body

        current = self._card(body, 16)
        current.pack(fill="x", pady=(0, 12))
        ttk.Label(current, text="Atualizações do aplicativo", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            current,
            text="O aplicativo consulta o repositório oficial do GitHub. Ele só baixa uma atualização depois que você confirmar.",
            style="Card.TLabel", wraplength=740, justify="left",
        ).pack(anchor="w", pady=(5, 10))
        self.app_update_status_var = tk.StringVar(value=f"Versão instalada: {VERSION}")
        self.app_update_latest_var = tk.StringVar(value="Ainda não verificado")
        self.app_update_notes_var = tk.StringVar(value="As notas da versão aparecem aqui quando o GitHub disponibilizar uma atualização.")
        ttk.Label(current, textvariable=self.app_update_status_var, style="CardTitle.TLabel", wraplength=740).pack(anchor="w", pady=(2, 6))
        ttk.Label(current, textvariable=self.app_update_latest_var, style="Muted.TLabel", wraplength=740).pack(anchor="w", pady=(0, 9))
        ttk.Label(current, text="Notas da versão", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(current, textvariable=self.app_update_notes_var, style="Card.TLabel", wraplength=740, justify="left").pack(anchor="w", pady=(4, 8))

        options = self._card(body, 14)
        options.pack(fill="x", pady=(0, 12))
        ttk.Label(options, text="Preferências", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 7))
        ttk.Checkbutton(
            options, text="Abrir o aplicativo automaticamente depois de atualizar (recomendado)",
            variable=self.update_open_after_var, command=self._save_update_preferences,
        ).pack(anchor="w", pady=3)
        ttk.Checkbutton(
            options, text="Verificar novas versões automaticamente ao abrir o aplicativo",
            variable=self.update_check_on_startup_var, command=self._save_update_preferences,
        ).pack(anchor="w", pady=3)

        actions = self._card(body, 14)
        actions.pack(fill="x", pady=(0, 12))
        buttons = ttk.Frame(actions, style="Card.TFrame")
        buttons.pack(fill="x")
        self.app_update_check_button = ttk.Button(
            buttons, text="Verificar atualizações", style="Accent.TButton",
            command=lambda: self._start_app_update_check(user_initiated=True),
        )
        self.app_update_check_button.pack(side="left")
        self.app_update_install_button = ttk.Button(
            buttons, text="Baixar e instalar", style="Secondary.TButton",
            state="disabled", command=self._show_cached_update_prompt,
        )
        self.app_update_install_button.pack(side="left", padx=(8, 0))
        self.app_uninstall_button = ttk.Button(
            buttons, text="Desinstalar aplicativo", style="Secondary.TButton",
            command=self._start_uninstall,
        )
        self.app_uninstall_button.pack(side="left", padx=(8, 0))
        self.app_update_repair_button = ttk.Button(
            buttons, text="Reparar todos os arquivos", style="Secondary.TButton",
            command=self._start_app_repair,
        )
        self.app_update_repair_button.pack(side="right")
        self.app_update_progress = ttk.Progressbar(actions, mode="determinate", maximum=100)
        self.app_update_progress.pack(fill="x", pady=(12, 0))
        self.app_update_progress_label_var = tk.StringVar(value="Nenhuma atualização em andamento.")
        ttk.Label(actions, textvariable=self.app_update_progress_label_var, style="Muted.TLabel", wraplength=740).pack(anchor="w", pady=(6, 0))

        safety = self._card(body, 14)
        safety.pack(fill="x", pady=(0, 20))
        ttk.Label(safety, text="Como funciona a reparação", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            safety,
            text=("No modo código-fonte, o aplicativo baixa novamente o pacote completo da branch/release oficial e substitui os arquivos da instalação de forma transacional. "
                  "No modo executável, baixa o EXE inteiro e exige verificação SHA-256. Preferências, pastas de destino, logs e mídias já baixadas ficam fora da pasta substituída. "
                  "Se a conexão falhar ou a validação não passar, a instalação atual permanece intacta."),
            style="Card.TLabel", wraplength=740, justify="left",
        ).pack(anchor="w", pady=(4, 0))

    def _save_update_preferences(self):
        try:
            updated = dict(self.config)
            updated["update_open_after"] = bool(self.update_open_after_var.get())
            updated["update_check_on_startup"] = bool(self.update_check_on_startup_var.get())
            save_config(updated)
            self.config = updated
        except Exception as exc:
            self._append_log(f"Não foi possível salvar as preferências de atualização: {exc}")

    def _maybe_start_update_check(self):
        if bool(self.update_check_on_startup_var.get()):
            self._start_app_update_check(user_initiated=False)

    def _start_app_update_check(self, *, user_initiated: bool):
        if self._app_update_checking or self._app_update_busy:
            if user_initiated:
                messagebox.showinfo("Atualizações", "Já existe uma verificação ou atualização em andamento.", parent=self.root)
            return
        self._app_update_checking = True
        self._app_update_show_current = user_initiated
        if hasattr(self, "app_update_check_button"):
            self.app_update_check_button.configure(state="disabled")
        self.app_update_status_var.set("Consultando o GitHub…")
        self.app_update_progress_label_var.set("Verificando a versão do aplicativo.")

        def worker():
            try:
                update = check_for_update(VERSION, frozen=IS_FROZEN)
                self.ui_queue.put(("app_update_check_done", (update, None, user_initiated)))
            except Exception as exc:
                self.ui_queue.put(("app_update_check_done", (None, exc, user_initiated)))

        threading.Thread(target=worker, name="CGMD-AppUpdateCheck", daemon=True).start()

    def _handle_app_update_check(self, data):
        update, error, user_initiated = data
        self._app_update_checking = False
        if hasattr(self, "app_update_check_button"):
            self.app_update_check_button.configure(state="normal")
        if error:
            self.app_update_status_var.set("Não foi possível consultar as atualizações.")
            self.app_update_latest_var.set(str(error))
            self.app_update_progress_label_var.set("Confira a conexão e tente novamente mais tarde.")
            self._append_log(f"Verificação de atualização falhou: {error}")
            if user_initiated:
                messagebox.showwarning("Atualizações", str(error), parent=self.root)
            return
        if update is None:
            self._app_update_info = None
            self.app_update_install_button.configure(state="disabled")
            self.app_update_status_var.set(f"Você está usando a versão {VERSION}.")
            self.app_update_latest_var.set("Não foi encontrada uma versão mais recente disponível para este tipo de instalação.")
            self.app_update_notes_var.set("Consulte as Releases do GitHub para ver o histórico publicado. Antes da primeira Release estável, builds executáveis não podem ser atualizados automaticamente.")
            self.app_update_progress_label_var.set("Nenhum download foi iniciado.")
            if user_initiated:
                messagebox.showinfo("Atualizações", "Nenhuma versão mais recente foi encontrada.\n\nSe ainda não houver uma Release estável publicada, o atualizador do executável ficará aguardando a primeira Release.", parent=self.root)
            return
        self._app_update_info = update
        self.app_update_status_var.set(f"Nova versão disponível: {update.version}")
        channel = "Release oficial" if update.kind == "executable" or update.tag_name not in {"", "main"} else "Código-fonte da branch main"
        self.app_update_latest_var.set(f"Versão instalada: {VERSION}  •  Disponível: {update.version}  •  Origem: {channel}")
        notes = update.notes.strip() or "Sem notas de versão publicadas."
        self.app_update_notes_var.set(notes[:1800])
        self.app_update_progress_label_var.set("Aguardando sua confirmação antes de baixar os arquivos.")
        self.app_update_install_button.configure(state="normal")
        if not self._app_update_prompt_open:
            self._show_update_prompt(update)

    def _show_cached_update_prompt(self):
        if self._app_update_info:
            self._show_update_prompt(self._app_update_info)
        else:
            self._start_app_update_check(user_initiated=True)

    def _show_update_prompt(self, update: AppUpdate):
        if self._app_update_prompt_open or self._app_update_busy:
            return
        self._app_update_prompt_open = True
        dialog = tk.Toplevel(self.root)
        dialog.title("Atualização disponível")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(bg=self.colors["bg"])
        box = self._card(dialog, 18)
        box.pack(fill="both", expand=True, padx=14, pady=14)
        ttk.Label(box, text=f"Nova versão {update.version} disponível", style="CardTitle.TLabel", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(box, text=f"Versão instalada: {VERSION}\nOrigem: {'Release oficial' if update.kind == 'executable' or update.tag_name not in {'', 'main'} else 'repositório main'}", style="Card.TLabel", justify="left").pack(anchor="w", pady=(8, 10))
        notes = update.notes.strip() or "Esta versão contém mudanças no repositório oficial."
        ttk.Label(box, text=notes[:1000], style="Card.TLabel", wraplength=470, justify="left").pack(anchor="w", pady=(0, 10))
        ttk.Checkbutton(
            box, text="Abrir o aplicativo automaticamente depois de atualizar",
            variable=self.update_open_after_var, command=self._save_update_preferences,
        ).pack(anchor="w", pady=(2, 12))
        actions = ttk.Frame(box, style="Card.TFrame")
        actions.pack(fill="x")

        def later():
            self._save_update_preferences()
            self._app_update_prompt_open = False
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass

        def start_update():
            self._save_update_preferences()
            self._app_update_prompt_open = False
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass
            self._start_app_update(update, repair=False)

        ttk.Button(actions, text="Atualizar agora", style="Accent.TButton", command=start_update).pack(side="left")
        ttk.Button(actions, text="Continuar nesta versão", style="Secondary.TButton", command=later).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", later)
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()

    def _start_uninstall(self):
        if self._app_update_busy or self._app_update_checking:
            messagebox.showwarning(
                "Desinstalar aplicativo",
                "Aguarde a atualização ou reparação terminar antes de desinstalar.",
                parent=self.root,
            )
            return
        confirmed = messagebox.askyesno(
            "Desinstalar ChatGPT Media Downloader",
            "Deseja desinstalar o aplicativo?\n\n"
            "Isso remove a instalação e os dados locais do aplicativo (configurações, logs e ferramentas). "
            "As pastas de músicas e vídeos configuradas para os downloads não serão removidas.\n\n"
            "Se a instalação estiver em Program Files, o Windows poderá pedir permissão de administrador.",
            parent=self.root,
        )
        if not confirmed:
            return
        try:
            launch_uninstaller(APP_DATA, INSTALL_ROOT)
        except Exception as exc:
            messagebox.showerror(
                "Falha ao desinstalar",
                f"Não foi possível iniciar o desinstalador.\n\nDetalhes: {exc}",
                parent=self.root,
            )
            return
        messagebox.showinfo(
            "Desinstalação iniciada",
            "Feche o aplicativo quando esta mensagem desaparecer. O desinstalador terminará a limpeza depois que o processo fechar.",
            parent=self.root,
        )
        self.root.destroy()

    def _start_app_repair(self, *, confirmed: bool = False):
        if self._app_update_busy or self._app_update_checking:
            messagebox.showwarning("Reparar arquivos", "Aguarde a operação de atualização terminar.", parent=self.root)
            return
        if not confirmed and not messagebox.askyesno(
            "Reparar todos os arquivos",
            "O aplicativo vai baixar novamente o pacote completo da fonte oficial do GitHub e substituir os arquivos do programa.\n\n"
            "Suas preferências, ferramentas e mídias baixadas serão preservadas quando estiverem nas pastas de dados separadas. Continuar?",
            parent=self.root,
        ):
            return
        self._start_app_update(None, repair=True)

    def _start_app_update(self, update: AppUpdate | None, *, repair: bool):
        if self._app_update_busy:
            return
        if ((self.download_thread and self.download_thread.is_alive()) or
                (self.playlist_analysis_thread and self.playlist_analysis_thread.is_alive()) or
                (self.install_thread and self.install_thread.is_alive())):
            messagebox.showwarning("Atualização", "Termine ou cancele downloads e instalações antes de atualizar o aplicativo.", parent=self.root)
            return
        self._app_update_busy = True
        for name in ("app_update_check_button", "app_update_install_button", "app_update_repair_button"):
            if hasattr(self, name):
                getattr(self, name).configure(state="disabled")
        self.app_update_progress.configure(mode="indeterminate")
        self.app_update_progress.start(12)
        self.app_update_progress_label_var.set("Preparando download seguro…")
        self.app_update_status_var.set("Baixando e validando arquivos. A versão atual não foi alterada.")
        launch_after = bool(self.update_open_after_var.get())

        def worker():
            try:
                candidate = check_repair_candidate(VERSION, frozen=IS_FROZEN) if repair else update
                if candidate is None:
                    raise AppUpdateError("Nenhuma atualização válida foi selecionada.")
                prepared = prepare_update(
                    candidate,
                    progress=lambda label, done, total: self.ui_queue.put(("app_update_progress", (label, done, total))),
                )
                self.ui_queue.put(("app_update_prepared", (candidate, prepared, launch_after, repair, None)))
            except Exception as exc:
                self.ui_queue.put(("app_update_prepared", (update, None, launch_after, repair, exc)))

        threading.Thread(target=worker, name="CGMD-AppUpdateDownload", daemon=True).start()

    def _handle_app_update_prepared(self, data):
        update, prepared, launch_after, repair, error = data
        self.app_update_progress.stop()
        self.app_update_progress.configure(mode="determinate", value=0)
        self._app_update_busy = False
        for name in ("app_update_check_button", "app_update_repair_button"):
            if hasattr(self, name):
                getattr(self, name).configure(state="normal")
        if error or prepared is None:
            self.app_update_install_button.configure(state="normal" if self._app_update_info else "disabled")
            self.app_update_status_var.set("Não foi possível preparar a atualização/reparação.")
            self.app_update_progress_label_var.set(str(error))
            self._append_log(f"Atualização/reparação não aplicada: {error}")
            messagebox.showerror("Atualização", str(error), parent=self.root)
            return
        try:
            schedule_apply_update(prepared, launch_after=launch_after)
        except Exception as exc:
            self.app_update_status_var.set("Não foi possível aplicar os arquivos preparados.")
            self.app_update_progress_label_var.set(str(exc))
            self._append_log(f"Não foi possível iniciar a troca segura dos arquivos: {exc}")
            messagebox.showerror("Atualização", str(exc), parent=self.root)
            return
        self.app_update_status_var.set(f"Versão {prepared.version} preparada; concluindo a troca de arquivos…")
        self.app_update_progress_label_var.set("O aplicativo vai fechar para substituir os arquivos. Não desligue o PC durante alguns segundos.")
        self._append_log(f"Troca de arquivos programada: versão {prepared.version}; abrir depois={launch_after}.")
        self.root.after(500, self.root.destroy)

    def _report_callback_exception(self, exc_type, exc_value, exc_traceback):
        """Log Tk callback failures and offer full repair for serious runtime exceptions."""
        try:
            self.logger.error("Erro não tratado na interface", exc_info=(exc_type, exc_value, exc_traceback))
        except Exception:
            pass
        critical = issubclass(exc_type, (ImportError, ModuleNotFoundError, SystemError, MemoryError))
        message = "Uma ação da interface falhou. Consulte o painel de mensagens e os logs."
        if critical:
            message += "\n\nO erro parece crítico. Deseja baixar novamente todos os arquivos do aplicativo e tentar reparar a instalação?"
            try:
                if messagebox.askyesno("Erro crítico — reparo", message, parent=self.root):
                    self._start_app_repair(confirmed=True)
                    return
            except Exception:
                pass
        messagebox.showerror("Erro do aplicativo", f"{message}\n\nDetalhes: {exc_value}\n\nSe os erros continuarem, abra Atualizações → Reparar todos os arquivos.", parent=self.root)

    def _build_help(self):
        frame = ttk.Frame(self.pages_area)
        self.page_frames["help"] = frame
        scroll = ScrollableFrame(frame)
        scroll.pack(fill="both", expand=True)
        body = scroll.body
        ttk.Label(body, text="Como usar", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))
        items = [
            ("Modo automático", "Aceita uma URL HTTP/HTTPS e trata o conteúdo como vídeo. A resolução usa a qualidade configurada."),
            ("Vídeo", "Escolha 480p, 720p, 1080p, 1440p ou 2160p/4K. Se a resolução exata não existir, o aplicativo tenta a melhor opção compatível e informa o fallback."),
            ("Música", "Baixa em MP3 usando 128, 192 ou 320 kbps e o FFmpeg. Metadados e thumbnail são incorporados quando o site os fornece."),
            ("Gerenciador de playlists", "Cole a URL e use Analisar playlist. O aplicativo mostra a quantidade total e os itens disponíveis. Marque os itens que deseja baixar, use a busca e configure vídeo/MP3 e a qualidade individualmente. Itens indisponíveis ficam desmarcados."),
            ("Modo de playlist: um por vez ou paralelo", "Um por vez é a opção recomendada para reduzir consumo de recursos. Paralelo executa vários itens simultaneamente; aumente a quantidade com cuidado, pois pode usar muita CPU, memória, disco e banda. Downloads simultâneos são diferentes de fragmentos paralelos dentro de cada mídia."),
            ("Como mostrar a capa no ícone do arquivo", "A capa é incorporada ao MP3/vídeo quando está disponível, mas o Explorador pode não mostrar a arte em miniatura para todos os formatos. No Windows 10, abra Exibir → Ícones grandes; em Opções do Explorador → Exibir, desmarque 'Sempre mostrar ícones, nunca miniaturas'; depois abra Configurações avançadas do sistema → Desempenho e marque 'Mostrar miniaturas em vez de ícones'. Se players mostram a capa mas o Explorer não, atualize o cache de miniaturas e confirme suporte do handler de mídia/codec instalado. Não é possível garantir que toda versão do Windows renderize a capa embutida como ícone."),
            ("Contêiner e legendas", "MP4 é o mais compatível; MKV é flexível para faixas. Legendas são opcionais e podem vir do criador ou serem geradas automaticamente conforme o site. Legendas e capas não estarão disponíveis em todas as fontes."),
            ("Pastas", "As pastas de saída podem ser alteradas em Configurações. Elas ficam fora da área de instalação e são preservadas na desinstalação."),
            ("Dependências", "yt-dlp, FFmpeg e FFprobe são detectados por caminho manual, área privada da instalação e PATH. Na primeira execução, o bootstrap tenta instalar versões compatíveis automaticamente."),
            ("Arquitetura", "Windows x86/x64/ARM64, Linux x86/x64/ARM64/ARMv7 e macOS Intel/Apple Silicon são identificados. A build compatível é priorizada."),
            ("Temas", "Claro, escuro ou Sistema. O tema escuro usa tons de azul espacial, violeta e rosa; Sistema consulta a preferência visual do Windows, macOS ou, quando disponível, do ambiente Linux."),
            ("Erros", "A interface mostra uma explicação simples. Para conferir a saída bruta de yt-dlp/FFmpeg, ative o Modo desenvolvedor nas Configurações."),
            ("Segurança e privacidade", "O app usa listas de argumentos, valida URLs HTTP/HTTPS, redige dados sensíveis nos logs e não tenta burlar DRM, paywall ou controles de acesso. Nenhum programa pode garantir 100% de segurança ou ausência de falsos positivos em antivírus. Baixe builds de fontes oficiais e verifique o hash do artefato distribuído."),
            ("Sites", "O suporte é o que o yt-dlp oferecer na versão instalada. O aplicativo não tenta burlar DRM, autenticação, paywall ou conteúdo privado."),
        ]
        for title, text in items:
            card = self._card(body, 13)
            card.pack(fill="x", pady=5)
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, text=text, style="Card.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(4, 0))

    def _build_developer(self):
        frame = ttk.Frame(self.pages_area)
        self.page_frames["developer"] = frame
        scroll = ScrollableFrame(frame)
        scroll.pack(fill="both", expand=True)
        body = scroll.body
        ttk.Label(body, text="Informações técnicas", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
        self.dev_vars = {}
        fields = [
            ("Vendor", "vendor", VENDOR), ("Product ID", "product_id", PRODUCT_ID), ("Install ID", "install_id", self.install_id),
            ("Sistema", "system", self.system.os_label), ("Arquitetura", "architecture", self.system.architecture_label),
            ("Versão", "app_version", VERSION), ("yt-dlp", "yt", "—"), ("FFmpeg", "ffmpeg", "—"),
            ("FFprobe", "ffprobe", "—"), ("Diretório da aplicação", "install_root", str(INSTALL_ROOT)),
            ("Configuração", "config", str(CONFIG_PATH)), ("Baseline de instalação", "baseline", str(BASELINE_CONFIG_PATH)),
            ("Temporários", "temp", str(TEMP_DIR)), ("Ferramentas", "tools", str(TOOLS_DIR)), ("Logs", "logs", str(LOG_DIR)),
        ]
        for label, key, value in fields:
            row = self._card(body, 10)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, style="Muted.TLabel", width=22).pack(side="left")
            var = tk.StringVar(value=value)
            self.dev_vars[key] = var
            ttk.Label(row, textvariable=var, style="Card.TLabel", wraplength=620).pack(side="left", fill="x", expand=True)
        info = self._card(body, 13)
        info.pack(fill="x", pady=(12, 10))
        ttk.Label(info, text="O que o aplicativo executa localmente", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(info, text="A interface executa apenas processos locais necessários para yt-dlp e FFmpeg/FFprobe, usando listas de argumentos em vez de comandos concatenados. URL, senhas, tokens e cookies não são gravados nos logs.", style="Card.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=(4, 0))
        ttk.Button(body, text="Desinstalar", style="Danger.TButton", command=self._uninstall).pack(anchor="e", pady=(0, 25))
        self._update_developer_vars()

    def _update_developer_vars(self):
        if not hasattr(self, "dev_vars"):
            return
        values = {
            "vendor": VENDOR, "product_id": PRODUCT_ID, "install_id": self.install_id,
            "system": self.system.os_label, "architecture": self.system.architecture_label, "app_version": VERSION,
            "yt": getattr(self.dep_infos.get("yt-dlp"), "version", "—") if self.dep_infos else "—",
            "ffmpeg": getattr(self.dep_infos.get("ffmpeg"), "version", "—") if self.dep_infos else "—",
            "ffprobe": getattr(self.dep_infos.get("ffprobe"), "version", "—") if self.dep_infos else "—",
            "install_root": str(INSTALL_ROOT), "config": str(CONFIG_PATH), "baseline": str(BASELINE_CONFIG_PATH),
            "temp": str(TEMP_DIR), "tools": str(TOOLS_DIR), "logs": str(LOG_DIR),
        }
        for key, value in values.items():
            if key in self.dev_vars:
                self.dev_vars[key].set(value)

    def _uninstall(self):
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showwarning("Download em andamento", "Cancele o download antes de desinstalar.")
            return
        if not messagebox.askyesno("Desinstalar", "Desinstalar o aplicativo sem apagar músicas e vídeos baixados?", parent=self.root):
            return
        launch_uninstaller(APP_DATA, INSTALL_ROOT)
        # The cleanup helper waits for this process before removing the installed EXE.
        self.root.after(100, self.root.destroy)

    def _animate_hero_visual(self):
        """Render lightweight space particles and deforming orb shapes on the home hero."""
        canvas = getattr(self, "hero_visual", None)
        if canvas is None:
            return
        try:
            if not self.root.winfo_exists() or not canvas.winfo_exists():
                return
            canvas.delete("all")
            width = max(canvas.winfo_width(), 108)
            height = max(canvas.winfo_height(), 112)
            cx, cy = width / 2.0, height / 2.0
            phase = self._hero_visual_phase
            panel = self.colors.get("panel2", "#191F38")
            accent = self.colors.get("accent", "#8B5CF6")
            pink = self.colors.get("pink", "#F472B6")
            blue = self.colors.get("space", "#60A5FA")
            violet_glow = _blend_hex(accent, panel, 0.36)
            pink_glow = _blend_hex(pink, panel, 0.42)
            blue_glow = _blend_hex(blue, panel, 0.42)

            for index, radius in enumerate((25, 37, 45)):
                wobble = math.sin(phase * 0.8 + index * 0.9) * 1.8
                canvas.create_oval(
                    cx - radius - wobble, cy - radius * 0.78,
                    cx + radius + wobble, cy + radius * 0.78,
                    outline=(violet_glow if index == 0 else pink_glow if index == 1 else blue_glow),
                    width=2 if index == 0 else 1,
                )

            # Soft, smoothed polygons mimic liquid orbs, morphing with every frame.
            for blob_index, (offset_x, offset_y, base, color, outline) in enumerate((
                (-19, -12, 15, blue_glow, blue),
                (18, -7, 17, pink_glow, pink),
                (0, 13, 20, violet_glow, accent),
            )):
                points = []
                blob_phase = phase * (0.78 + blob_index * 0.11) + blob_index * 1.9
                for index in range(36):
                    angle = math.tau * index / 36.0
                    wave = (
                        math.sin(angle * 3 + blob_phase) * 0.16
                        + math.cos(angle * 2 - blob_phase * 0.7) * 0.10
                        + math.sin(angle * 5 + phase * 0.55) * 0.045
                    )
                    rx = base * (1.0 + wave)
                    ry = base * (0.77 + wave * 0.7)
                    points.extend((
                        cx + offset_x + math.cos(angle) * rx,
                        cy + offset_y + math.sin(angle) * ry,
                    ))
                canvas.create_polygon(
                    points, smooth=True, splinesteps=10, fill=color, outline=outline, width=1,
                )

            for index in range(11):
                angle = phase * (0.55 + (index % 3) * 0.12) + index * (math.tau / 11.0)
                radius = 39 + 4 * math.sin(phase * 1.2 + index * 0.8)
                x = cx + math.cos(angle) * radius
                y = cy + math.sin(angle) * radius * 0.75
                size = 1.2 if index % 3 else 2.2
                color = (pink if index % 3 == 0 else blue if index % 3 == 1 else accent)
                canvas.create_oval(x-size, y-size, x+size, y+size, fill=color, outline="")
            canvas.create_text(
                cx, cy, text="↓", fill=self.colors.get("fg", "#F4F5FF"),
                font=("Segoe UI", 27, "bold"),
            )
            self._hero_visual_phase = (phase + 0.13) % math.tau
            if self.config.get("animations_enabled", True):
                self._hero_animation_job = self.root.after(72, self._animate_hero_visual)
            else:
                self._hero_animation_job = None
        except tk.TclError:
            return

    # ---------- Page navigation and transitions ----------
    def _finish_page_animation(self):
        """Normalize the current transition before another navigation request."""
        if self._page_animation_job is not None:
            try:
                self.root.after_cancel(self._page_animation_job)
            except tk.TclError:
                pass
            self._page_animation_job = None
        target = self._page_animation_target
        if target in self.page_frames:
            for frame in self.page_frames.values():
                try:
                    frame.place_forget()
                    frame.pack_forget()
                except tk.TclError:
                    pass
            self.page_frames[target].pack(fill="both", expand=True)
            self._visible_page = target
            self.current_page = target
        self._page_animation_target = None

    def show_page(self, name: str):
        if name not in self.page_frames:
            return
        if self._page_animation_job is not None:
            self._finish_page_animation()

        Tooltip.dismiss_all()
        old_name = self._visible_page
        new_frame = self.page_frames[name]
        self.current_page = name
        title = {
            "home": "Início", "playlist": "Playlists", "settings": "Aparência e ajustes",
            "dependencies": "Dependências", "updates": "Atualizações", "help": "Central de ajuda",
            "developer": "Diagnóstico",
        }[name]
        subtitle = {
            "home": "Seu espaço para vídeos, músicas e playlists.",
            "playlist": "Escolha exatamente o que baixar e defina opções por item.",
            "settings": "Personalize o visual e ajuste o comportamento do downloader.",
            "dependencies": "Ferramentas locais e estado da instalação.",
            "updates": "Atualizações verificadas, reparação e recuperação da instalação.",
            "help": "Orientações rápidas para tirar o melhor do aplicativo.",
            "developer": "Informações úteis para diagnóstico técnico.",
        }[name]
        self.page_title_var.set(title)
        self.page_subtitle_var.set(subtitle)
        for key, button in self.nav_buttons.items():
            if isinstance(button, IconNavButton):
                button.set_active(key == name)
            else:
                button.configure(style="Selected.Nav.TButton" if key == name else "Nav.TButton")

        if name == "settings":
            self._sync_settings_form()
        elif name == "dependencies":
            self._refresh_dependencies()
        elif name == "developer":
            self._update_developer_vars()

        width = self.pages_area.winfo_width()
        if old_name is None or old_name == name or width < 180 or not self.config.get("animations_enabled", True):
            for frame in self.page_frames.values():
                frame.place_forget()
                frame.pack_forget()
            new_frame.pack(fill="both", expand=True)
            self._visible_page = name
            return

        old_frame = self.page_frames[old_name]
        for frame in self.page_frames.values():
            frame.place_forget()
            frame.pack_forget()
        old_frame.place(x=0, y=0, relwidth=1, relheight=1)
        new_frame.place(x=28, y=0, relwidth=1, relheight=1)
        new_frame.lift()
        self._page_animation_target = name

        # Slide a short distance, keeping the previous page beneath the new one.
        # Eight small steps avoid expensive alpha effects and remain smooth on older PCs.
        def animate(step: int = 0):
            if self._page_animation_target != name:
                return
            try:
                if not self.root.winfo_exists():
                    return
                progress = min(1.0, step / 10.0)
                eased = 1.0 - (1.0 - progress) ** 3
                new_frame.place_configure(x=round(34 * (1.0 - eased)))
                old_frame.place_configure(x=-round(14 * eased))
                if step >= 10:
                    for frame in self.page_frames.values():
                        frame.place_forget()
                        frame.pack_forget()
                    new_frame.pack(fill="both", expand=True)
                    self._visible_page = name
                    self._page_animation_target = None
                    self._page_animation_job = None
                    return
                self._page_animation_job = self.root.after(14, lambda: animate(step + 1))
            except tk.TclError:
                self._page_animation_job = None
                self._page_animation_target = None

        self._page_animation_job = self.root.after(0, animate)
    def _sync_settings_form(self):
        for key,var in self.settings_vars.items():
            var.set(self._display_setting_value(key,self.config.get(key,DEFAULT_CONFIG.get(key,""))))
        self.developer_mode_var.set(bool(self.config.get("developer_mode",False)))
        self._preview_developer_mode()
        self.animations_enabled_var.set(bool(self.config.get("animations_enabled", True)))
        self._preview_animations()
        self._apply_theme(self.config.get("theme","dark"))
        if hasattr(self,"playlist_strategy_var"):
            self.playlist_strategy_var.set(self._strategy_label(self.config.get("playlist_strategy","sequential")))
            self.playlist_parallelism_var.set(str(self.config.get("playlist_parallelism",3)))
    def _sync_quality(self):
        if "Música" in self.mode_var.get():
            values = ["128 kbps", "192 kbps", "320 kbps"]
            current = f"{self.config['audio_bitrate']} kbps"
        else:
            values = ["480p", "720p", "1080p", "1440p", "2160p / 4K"]
            current = f"{self.config['auto_video_quality']}p"
        self.quality["values"] = values
        self.quality_var.set(current if current in values else values[0])

    def _append_log(self, message: str, raw: bool = False):
        """Append user-facing activity or preserve raw command output for developer mode."""
        message = str(message).rstrip()
        if not message:
            return
        self.log_history.append((message, bool(raw)))
        if len(self.log_history) > 600:
            del self.log_history[:len(self.log_history) - 600]
        if raw and not self._developer_mode_active:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _render_log_history(self):
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        for message, raw in self.log_history:
            if raw and not self._developer_mode_active:
                continue
            self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _preview_developer_mode(self):
        self._developer_mode_active = bool(self.developer_mode_var.get())
        self.log_mode_var.set("CONSOLE TÉCNICO" if self._developer_mode_active else "RESUMO DE ATIVIDADE")
        if hasattr(self, "log_text"):
            self._render_log_history()

    def _preview_animations(self):
        enabled = bool(self.animations_enabled_var.get())
        self.config["animations_enabled"] = enabled
        job = getattr(self, "_hero_animation_job", None)
        if not enabled and job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
            self._hero_animation_job = None
        elif enabled and getattr(self, "hero_visual", None) is not None and job is None:
            self._hero_animation_job = self.root.after(0, self._animate_hero_visual)

    def _clear_log(self):
        self.log_history.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _poll_queue(self):
        processed = 0
        try:
            while processed < 250:
                kind, data = self.ui_queue.get_nowait()
                processed += 1
                if kind == "log":
                    self._append_log(str(data))
                elif kind == "raw_log":
                    self._append_log(str(data), raw=True)
                elif kind == "progress":
                    percent = data.get("percent")
                    if percent is not None:
                        self.percent_var.set(percent)
                        self.percent_label.configure(text=f"{percent:.0f}%")
                    self.stage_var.set(str(data.get("stage") or "—"))
                    if data.get("speed"):
                        self.speed_var.set(str(data["speed"]))
                    if data.get("total"):
                        self.size_var.set(str(data["total"]))
                    if data.get("eta"):
                        self.eta_var.set(str(data["eta"]))
                elif kind == "result":
                    self._finish_download(data)
                elif kind == "playlist_analysis_done":
                    self.playlist_analysis_thread = None
                    self.analyze_playlist_btn.configure(state="normal")
                    info, error = data
                    if error:
                        self.status_var.set("Não foi possível analisar a playlist")
                        self._append_log("Falha ao analisar playlist: " + str(error))
                        messagebox.showerror("Análise da playlist", str(error), parent=self.root)
                    else:
                        self._apply_playlist_info(info)
                elif kind == "playlist_item_progress":
                    position, progress_data = data
                    percent = progress_data.get("percent")
                    if percent is not None:
                        self.playlist_progress_by_position[position] = float(percent)
                    if 0 <= position < len(self.playlist_items):
                        item = self.playlist_items[position]
                        stage = str(progress_data.get("stage") or "Baixando")
                        item["status"] = f"{stage} {percent:.0f}%" if percent is not None else stage
                        self._update_playlist_row(position)
                    relevant = [self.playlist_progress_by_position.get(pos, 0.0) for pos in self._playlist_job_positions]
                    average = sum(relevant) / max(1, len(relevant))
                    self.percent_var.set(average)
                    self.percent_label.configure(text=f"{average:.0f}%")
                    self.stage_var.set(str(progress_data.get("stage") or "Playlist em andamento"))
                    self.status_var.set(f"Playlist: {len(self.playlist_completed_positions)}/{len(self._playlist_job_positions)} itens finalizados")
                    if progress_data.get("speed"):
                        self.speed_var.set(str(progress_data["speed"]))
                    if progress_data.get("eta"):
                        self.eta_var.set(str(progress_data["eta"]))
                    if progress_data.get("total"):
                        self.size_var.set(str(progress_data["total"]))
                elif kind == "playlist_item_done":
                    position, status, success, message = data
                    if 0 <= position < len(self.playlist_items):
                        self.playlist_items[position]["status"] = status
                        self.playlist_items[position]["success"] = bool(success)
                        self._update_playlist_row(position)
                    self.playlist_completed_positions.add(position)
                    self.playlist_progress_by_position[position] = 100.0
                    if message:
                        title = self.playlist_items[position]["title"] if 0 <= position < len(self.playlist_items) else f"Item {position + 1}"
                        self._append_log(f"[{position + 1}] {title}: {message}")
                    relevant = [self.playlist_progress_by_position.get(pos, 0.0) for pos in self._playlist_job_positions]
                    average = sum(relevant) / max(1, len(relevant))
                    self.percent_var.set(average)
                    self.percent_label.configure(text=f"{average:.0f}%")
                elif kind == "playlist_download_done":
                    self._finish_playlist_download(data)
                elif kind == "dep_refresh_done":
                    self._dependency_refresh_thread = None
                    self._apply_dependency_results(data)
                elif kind == "dep_done":
                    self.install_btn.configure(state="normal")
                    self.config = load_config()
                    self._sync_settings_form()
                    self._refresh_dependencies(force=True)
                elif kind == "dep_error":
                    messagebox.showerror("Dependências", str(data), parent=self.root)
                elif kind == "dep_progress":
                    tool, stage, done, total = data
                    self.status_var.set(f"Instalando {tool}: {stage}")
                elif kind == "app_update_check_done":
                    self._handle_app_update_check(data)
                elif kind == "app_update_progress":
                    label, done, total = data
                    self.app_update_progress_label_var.set(str(label))
                    if total and total > 0:
                        self.app_update_progress.stop()
                        self.app_update_progress.configure(mode="determinate", maximum=total, value=done)
                    else:
                        self.app_update_progress.configure(mode="indeterminate")
                        self.app_update_progress.start(12)
                elif kind == "app_update_prepared":
                    self._handle_app_update_prepared(data)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _apply_playlist_info(self, info: PlaylistInfo):
        self.playlist_info = info
        self._playlist_title = info.title or "Playlist"
        default_mode = "music" if "Música" in self.mode_var.get() else "video"
        default_value = self._parse_quality()
        self.playlist_items = []
        self.playlist_progress_by_position.clear()
        self.playlist_completed_positions.clear()
        for position, entry in enumerate(info.entries):
            mode = default_mode
            value = default_value
            if mode == "music" and not validate_bitrate(value):
                value = int(self.config.get("audio_bitrate", 192))
            if mode == "video" and not validate_quality(value):
                value = int(self.config.get("auto_video_quality", 1080))
            self.playlist_items.append({
                "position": position, "index": entry.index, "title": entry.title, "url": entry.url,
                "video_id": entry.video_id, "duration": entry.duration, "available": entry.available,
                "note": entry.note, "included": bool(entry.available), "mode": mode, "value": value,
                "status": "Disponível" if entry.available else "Indisponível", "success": None,
            })
        count = len(self.playlist_items)
        available = sum(1 for item in self.playlist_items if item["available"])
        missing = max(info.unavailable_count, count - available)
        self.playlist_summary_var.set(f"{count} itens · {available} disponíveis" + (f" · {missing} indisponíveis" if missing else ""))
        self.playlist_editor_hint_var.set(f"Playlist: {self._playlist_title}. Clique em um item para alterar seu formato e qualidade. Dê duplo clique na coluna Baixar para incluir/excluir rapidamente.")
        self._render_playlist_rows()
        self.show_page("playlist")
        self.status_var.set(f"Playlist analisada: {count} itens")
        self._append_log(f"Playlist analisada: {self._playlist_title} — {count} itens, {available} disponíveis, {missing} indisponíveis.")

    def _render_playlist_rows(self):
        if not hasattr(self, "playlist_tree"):
            return
        try:
            prior_selection = self.playlist_tree.selection()
        except tk.TclError:
            prior_selection = ()
        query = self.playlist_search_var.get().strip().casefold()
        self.playlist_tree.delete(*self.playlist_tree.get_children())
        self.playlist_iid_to_position.clear()
        visible = 0
        for item in self.playlist_items:
            searchable = f"{item['index']} {item['title']} {item['video_id']}".casefold()
            if query and query not in searchable:
                continue
            position = int(item["position"])
            iid = str(position)
            self.playlist_iid_to_position[iid] = position
            included = "✓" if item["included"] and item["available"] else "—"
            mode = "Música / MP3" if item["mode"] == "music" else "Vídeo"
            quality = f"{item['value']} kbps" if item["mode"] == "music" else f"{item['value']}p"
            status = str(item.get("status") or ("Disponível" if item["available"] else "Indisponível"))
            self.playlist_tree.insert("", "end", iid=iid, values=(included, item["index"], item["title"], format_duration(item.get("duration")), mode, quality, status))
            visible += 1
        restore = [iid for iid in prior_selection if iid in self.playlist_iid_to_position]
        if restore:
            self.playlist_tree.selection_set(restore)
        if not visible and self.playlist_items:
            self.playlist_editor_hint_var.set("Nenhum item corresponde à busca. Limpe a busca para mostrar a playlist inteira.")
        self._update_playlist_summary()

    def _update_playlist_row(self, position: int):
        if not hasattr(self, "playlist_tree"):
            return
        iid = str(position)
        if not self.playlist_tree.exists(iid) or not (0 <= position < len(self.playlist_items)):
            return
        item = self.playlist_items[position]
        included = "✓" if item["included"] and item["available"] else "—"
        mode = "Música / MP3" if item["mode"] == "music" else "Vídeo"
        quality = f"{item['value']} kbps" if item["mode"] == "music" else f"{item['value']}p"
        self.playlist_tree.item(iid, values=(included, item["index"], item["title"], format_duration(item.get("duration")), mode, quality, item.get("status", "Disponível")))
        self._update_playlist_summary()

    def _update_playlist_summary(self):
        if not hasattr(self, "playlist_selected_summary_var"):
            return
        total = len(self.playlist_items)
        available = sum(1 for item in self.playlist_items if item["available"])
        included = sum(1 for item in self.playlist_items if item["included"] and item["available"])
        self.playlist_selected_summary_var.set(f"{included} de {available} itens marcados")
        if self.playlist_info:
            missing = max(self.playlist_info.unavailable_count, total - available)
            self.playlist_summary_var.set(f"{total} itens · {available} disponíveis · {included} marcados" + (f" · {missing} indisponíveis" if missing else ""))

    def _on_playlist_tree_select(self, _event=None):
        selection = self.playlist_tree.selection()
        if not selection:
            return
        position = self.playlist_iid_to_position.get(selection[0])
        if position is None or not (0 <= position < len(self.playlist_items)):
            return
        item = self.playlist_items[position]
        self.playlist_editor_include_var.set(bool(item["included"]))
        self.playlist_editor_mode_var.set("Música — MP3" if item["mode"] == "music" else "Vídeo")
        self.playlist_editor_quality_var.set(f"{item['value']} kbps" if item["mode"] == "music" else f"{item['value']}p")
        self._sync_playlist_editor_quality(preserve=True)
        self.playlist_editor_hint_var.set(f"Item {item['index']}: {item['title']}" + (f" — {item['note']}" if item["note"] else "") + (". Aplicar aos selecionados altera todas as linhas realçadas." if len(selection) > 1 else ". Edite e clique em Aplicar aos selecionados para salvar as opções."))

    def _on_playlist_tree_double_click(self, event):
        row = self.playlist_tree.identify_row(event.y)
        column = self.playlist_tree.identify_column(event.x)
        if row and column == "#1":
            position = self.playlist_iid_to_position.get(row)
            if position is not None:
                item = self.playlist_items[position]
                if item["available"]:
                    item["included"] = not item["included"]
                    if self.playlist_tree.selection() and row in self.playlist_tree.selection():
                        self.playlist_editor_include_var.set(bool(item["included"]))
                    self._update_playlist_row(position)
            return "break"
        return None

    def _sync_playlist_editor_quality(self, preserve: bool = False):
        if not hasattr(self, "playlist_editor_quality"):
            return
        if "Música" in self.playlist_editor_mode_var.get():
            values = ["128 kbps", "192 kbps", "320 kbps"]
            default = f"{self.config.get('audio_bitrate', 192)} kbps"
        else:
            values = ["480p", "720p", "1080p", "1440p", "2160p / 4K"]
            default = f"{self.config.get('auto_video_quality', 1080)}p"
        current = self.playlist_editor_quality_var.get() if preserve else ""
        if current not in values:
            current = default if default in values else values[0]
        self.playlist_editor_quality.configure(values=values)
        self.playlist_editor_quality_var.set(current)

    @staticmethod
    def _parse_playlist_quality(mode: str, text: str) -> int:
        try:
            return int(str(text).split()[0].replace("p", ""))
        except (ValueError, IndexError):
            return 192 if mode == "music" else 1080

    def _apply_playlist_include_toggle(self):
        selected = self.playlist_tree.selection()
        if not selected:
            focus = self.playlist_tree.focus()
            selected = (focus,) if focus else ()
        positions = [self.playlist_iid_to_position[iid] for iid in selected if iid in self.playlist_iid_to_position]
        included = bool(self.playlist_editor_include_var.get())
        for position in positions:
            item = self.playlist_items[position]
            item["included"] = included and bool(item["available"])
        self._render_playlist_rows()
        for position in positions:
            iid = str(position)
            if self.playlist_tree.exists(iid):
                self.playlist_tree.selection_add(iid)
        self._update_playlist_summary()

    def _apply_playlist_item_settings(self):
        selected = self.playlist_tree.selection()
        if not selected:
            focus = self.playlist_tree.focus()
            selected = (focus,) if focus else ()
        positions = [self.playlist_iid_to_position[iid] for iid in selected if iid in self.playlist_iid_to_position]
        if not positions:
            messagebox.showinfo("Playlist", "Selecione um ou mais itens na tabela primeiro.", parent=self.root)
            return
        mode = "music" if "Música" in self.playlist_editor_mode_var.get() else "video"
        value = self._parse_playlist_quality(mode, self.playlist_editor_quality_var.get())
        if mode == "music" and not validate_bitrate(value):
            messagebox.showerror("Qualidade", "Selecione 128, 192 ou 320 kbps.", parent=self.root)
            return
        if mode == "video" and not validate_quality(value):
            messagebox.showerror("Qualidade", "Selecione 480p, 720p, 1080p, 1440p ou 2160p.", parent=self.root)
            return
        for position in positions:
            item = self.playlist_items[position]
            item["mode"] = mode
            item["value"] = value
            if not item["available"]:
                item["status"] = "Indisponível"
        self._render_playlist_rows()
        for position in positions:
            iid = str(position)
            if self.playlist_tree.exists(iid):
                self.playlist_tree.selection_add(iid)
        self._append_log(f"Aplicadas opções a {len(positions)} item(ns) da playlist.")

    def _set_visible_playlist_included(self, included: bool):
        for position in self.playlist_iid_to_position.values():
            item = self.playlist_items[position]
            item["included"] = bool(included and item["available"])
        self._render_playlist_rows()

    def _invert_visible_playlist_items(self):
        for position in self.playlist_iid_to_position.values():
            item = self.playlist_items[position]
            if item["available"]:
                item["included"] = not item["included"]
        self._render_playlist_rows()

    def _start_playlist_analysis(self, url: str | None = None):
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showwarning("Download em andamento", "Aguarde ou cancele o download atual antes de analisar outra playlist.", parent=self.root)
            return
        if self.playlist_analysis_thread and self.playlist_analysis_thread.is_alive():
            return
        url = (url or self.url_var.get()).strip()
        valid, message = validate_url(url)
        if not valid:
            messagebox.showerror("URL inválida", message, parent=self.root)
            return
        if not self._dependencies_checked or (self._dependency_refresh_thread and self._dependency_refresh_thread.is_alive()):
            messagebox.showinfo("Verificação em andamento", "Aguarde a verificação das dependências terminar e tente novamente.", parent=self.root)
            return
        yt = self.dep_infos.get("yt-dlp")
        if not yt or not yt.path or not yt.executable_ok:
            messagebox.showerror("Dependência ausente", "yt-dlp não está disponível. Abra Dependências e use Instalar/Reparar automaticamente.", parent=self.root)
            return
        self.url_var.set(url)
        self.analyze_playlist_btn.configure(state="disabled")
        self.status_var.set("Analisando playlist e contando itens…")
        self.stage_var.set("Lendo metadados")
        self.show_page("playlist")
        self.playlist_summary_var.set("Analisando…")
        self.playlist_analysis_thread = threading.Thread(target=self._playlist_analysis_worker, args=(yt.path, url), daemon=True)
        self.playlist_analysis_thread.start()

    def _playlist_analysis_worker(self, yt_dlp_path, url):
        try:
            info = inspect_playlist(yt_dlp_path, url)
            self.ui_queue.put(("playlist_analysis_done", (info, None)))
        except Exception as exc:
            self.logger.exception("Falha ao analisar playlist.")
            self.ui_queue.put(("playlist_analysis_done", (None, str(exc))))

    def _reanalyze_playlist(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo("Playlist", "Cole a URL da playlist na página Início primeiro.", parent=self.root)
            return
        self._start_playlist_analysis(url)

    def _start_selected_playlist_download(self):
        if self.download_thread and self.download_thread.is_alive():
            return
        selected_items = [dict(item) for item in self.playlist_items if item["included"] and item["available"] and item["url"]]
        if not selected_items:
            messagebox.showinfo("Playlist", "Marque pelo menos um item disponível para baixar.", parent=self.root)
            return
        if not self._dependencies_checked or (self._dependency_refresh_thread and self._dependency_refresh_thread.is_alive()):
            messagebox.showinfo("Dependências", "Aguarde a verificação de dependências terminar.", parent=self.root)
            return
        for key in ("yt-dlp", "ffmpeg"):
            info = self.dep_infos.get(key)
            if not info or not info.path or not info.executable_ok or info.error:
                messagebox.showerror("Dependência ausente", f"{key} não está disponível ou é incompatível. Abra Dependências para reparar.", parent=self.root)
                return
        strategy = self._strategy_value(self.playlist_strategy_var.get())
        try:
            parallelism = int(self.playlist_parallelism_var.get())
        except ValueError:
            parallelism = 3
        if parallelism not in {2, 3, 4, 6}:
            parallelism = 3
        if strategy == "parallel":
            approved = messagebox.askyesno(
                "Modo paralelo — consumo de recursos",
                f"Serão baixados até {parallelism} itens ao mesmo tempo. Isso pode aumentar bastante o uso de CPU, memória, disco e rede.\n\nPara playlists grandes, 2–4 simultâneos é mais equilibrado. Continuar?",
                parent=self.root,
            )
            if not approved:
                return
        self.config["playlist_strategy"] = strategy
        self.config["playlist_parallelism"] = parallelism
        try:
            save_config(self.config)
        except OSError:
            self.logger.warning("Não foi possível persistir as preferências de playlist.")
        self.cancel_requested.clear()
        self.playlist_progress_by_position = {int(item["position"]): 0.0 for item in selected_items}
        self.playlist_completed_positions.clear()
        self._playlist_job_positions = [int(item["position"]) for item in selected_items]
        for item in selected_items:
            item_pos = int(item["position"])
            self.playlist_items[item_pos]["status"] = "Na fila"
            self.playlist_items[item_pos]["success"] = None
        self._render_playlist_rows()
        self._clear_log()
        self._append_log(f"Playlist: {self._playlist_title}")
        self._append_log(f"Itens selecionados: {len(selected_items)}")
        self._append_log(f"Execução: {'Paralela' if strategy == 'parallel' else 'um por vez'}")
        self.download_btn.configure(state="disabled")
        self.analyze_playlist_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.percent_var.set(0)
        self.percent_label.configure(text="0%")
        self.status_var.set(f"Preparando {len(selected_items)} itens…")
        self.stage_var.set("Na fila")
        cfg = dict(self.config)
        deps = dict(self.dep_infos)
        self.download_thread = threading.Thread(
            target=self._playlist_download_worker,
            args=(selected_items, strategy, parallelism, self._playlist_title, cfg, deps),
            daemon=True,
        )
        self.download_thread.start()

    def _playlist_download_worker(self, items: list[dict], strategy: str, parallelism: int, playlist_title: str, config_snapshot: dict, dep_infos: dict):
        results: list[dict] = []
        playlist_folder = safe_filename_part(playlist_title, max_bytes=100)
        options = {
            "video_container": config_snapshot.get("video_container", "mp4"),
            "retries": int(config_snapshot.get("retries", 5)),
            "concurrent_fragments": int(config_snapshot.get("concurrent_fragments", 4)),
            "subtitle_mode": config_snapshot.get("subtitle_mode", "off"),
        }

        def run_one(item: dict) -> dict:
            position = int(item["position"])
            title = str(item["title"])
            if self.cancel_requested.is_set():
                self.ui_queue.put(("playlist_item_done", (position, "Cancelado", False, "Cancelado antes de iniciar.")))
                return {"position": position, "state": "cancelled", "result": None}
            valid, reason = validate_url(str(item.get("url") or ""))
            if not valid:
                self.ui_queue.put(("playlist_item_done", (position, "URL inválida", False, reason)))
                return {"position": position, "state": "failed", "result": None}
            downloader = Downloader(
                dep_infos["yt-dlp"], dep_infos["ffmpeg"], dep_infos["ffprobe"], self.logger,
                progress=lambda data, pos=position: self.ui_queue.put(("playlist_item_progress", (pos, data))),
                output=lambda line, pos=position, name=title: self.ui_queue.put(("raw_log", f"[{pos + 1}/{len(items)}] {name}: {line}")),
                options=options,
            )
            key = f"playlist-{position}"
            with self.active_downloaders_lock:
                self.active_downloaders[key] = downloader
            try:
                if self.cancel_requested.is_set():
                    downloader.cancel()
                if item["mode"] == "music":
                    output_root = Path(config_snapshot["music_dir"]) / playlist_folder
                    result = downloader.download_audio(str(item["url"]), int(item["value"]), output_root, playlist=False)
                else:
                    output_root = Path(config_snapshot["video_dir"]) / playlist_folder
                    result = downloader.download_video(str(item["url"]), int(item["value"]), output_root, playlist=False)
                success = result.returncode == 0
                state = "Concluído" if success else ("Cancelado" if result.returncode == 130 or self.cancel_requested.is_set() else "Falhou")
                self.ui_queue.put(("playlist_item_done", (position, state, success, result.message)))
                return {"position": position, "state": state.lower(), "result": result}
            except Exception as exc:
                self.logger.exception("Falha ao baixar item da playlist.")
                self.ui_queue.put(("playlist_item_done", (position, "Falhou", False, str(exc))))
                return {"position": position, "state": "failed", "result": None, "error": str(exc)}
            finally:
                with self.active_downloaders_lock:
                    self.active_downloaders.pop(key, None)

        if strategy == "parallel":
            with ThreadPoolExecutor(max_workers=min(max(1, parallelism), 6), thread_name_prefix="cgmd-item") as executor:
                futures = [executor.submit(run_one, item) for item in items]
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        self.logger.exception("Falha inesperada no worker de playlist.")
                        results.append({"state": "failed", "error": str(exc)})
        else:
            for item in items:
                if self.cancel_requested.is_set():
                    break
                results.append(run_one(item))

        processed_positions = {int(result["position"]) for result in results if result.get("position") is not None}
        if self.cancel_requested.is_set():
            for item in items:
                position = int(item["position"])
                if position not in processed_positions:
                    self.ui_queue.put(("playlist_item_done", (position, "Não iniciado", False, "Interrompido antes de começar.")))
                    results.append({"position": position, "state": "cancelled", "result": None})
        states = [result.get("state", "failed") for result in results]
        success_count = sum(state == "concluído" for state in states)
        failed_count = sum(state == "failed" or state == "falhou" for state in states)
        cancelled_count = sum(state == "cancelled" or state == "cancelado" for state in states)
        not_started = max(0, len(items) - len(results))
        self.ui_queue.put(("playlist_download_done", {
            "total": len(items), "success": success_count, "failed": failed_count,
            "cancelled": cancelled_count + not_started, "strategy": strategy,
            "cancel_requested": self.cancel_requested.is_set(),
        }))

    def _finish_playlist_download(self, summary: dict):
        self.download_thread = None
        self.downloader = None
        with self.active_downloaders_lock:
            self.active_downloaders.clear()
        self.download_btn.configure(state="normal")
        self.analyze_playlist_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        total = int(summary.get("total", 0))
        success = int(summary.get("success", 0))
        failed = int(summary.get("failed", 0))
        cancelled = int(summary.get("cancelled", 0))
        self.percent_var.set(100.0 if total and success + failed + cancelled >= total else self.percent_var.get())
        self.percent_label.configure(text=f"{self.percent_var.get():.0f}%")
        message = f"Playlist finalizada: {success} concluído(s), {failed} falha(s), {cancelled} cancelado(s)/não iniciado(s)."
        self._append_log(message)
        if summary.get("cancel_requested"):
            self.status_var.set("Playlist cancelada")
            self.stage_var.set("Cancelado")
        elif failed or cancelled or success != total:
            self.status_var.set("Playlist concluída com avisos")
            self.stage_var.set("Revise os itens com falha ou indisponíveis")
        else:
            self.status_var.set("Playlist concluída")
            self.stage_var.set("Concluído")
        self._render_playlist_rows()
        if failed or cancelled or success != total:
            messagebox.showwarning("Playlist finalizada", message, parent=self.root)
        else:
            messagebox.showinfo("Playlist finalizada", message, parent=self.root)

    @staticmethod
    def _looks_like_playlist(url: str) -> bool:
        from urllib.parse import urlsplit, parse_qs
        try:
            parts = urlsplit(url.strip())
            host = (parts.hostname or "").lower()
            query = parse_qs(parts.query)
            path = parts.path.lower()
            if host.endswith(("youtube.com", "youtube-nocookie.com")) and (
                path.startswith("/playlist") or ("list" in query and bool(query["list"]))
            ):
                return True
            if host.endswith("youtu.be") and "list" in query:
                return True
            return any(token in path for token in ("/playlist/", "/playlists/", "/sets/")) or "playlist" in query
        except (ValueError, AttributeError):
            return False

    def _update_playlist_warning(self, *_args):
        if not hasattr(self, "playlist_warning"):
            return
        if self._looks_like_playlist(self.url_var.get()):
            self.playlist_warning.pack(fill="x", pady=(5, 0))
        else:
            self.playlist_warning.pack_forget()

    def _parse_quality(self) -> int:
        return int(self.quality_var.get().split()[0].replace("p", ""))

    def _download_worker(self, mode: str, url: str, value: int, playlist: bool = False):
        downloader = Downloader(self.dep_infos["yt-dlp"], self.dep_infos["ffmpeg"], self.dep_infos["ffprobe"],
                                self.logger, progress=lambda data: self.ui_queue.put(("progress", data)),
                                output=lambda line: self.ui_queue.put(("raw_log", line)), options=self._downloader_options())
        self.downloader = downloader
        if self.cancel_requested.is_set():
            downloader.cancel()
        try:
            if mode == "music":
                result = downloader.download_audio(url, value, Path(self.config["music_dir"]), playlist=playlist)
            else:
                result = downloader.download_video(url, value, Path(self.config["video_dir"]), playlist=playlist)
            self.ui_queue.put(("result", result))
        except Exception as exc:
            self.logger.exception("Falha no download.")
            self.ui_queue.put(("result", {"exception": str(exc)}))

    def start_download(self):
        if self.download_thread and self.download_thread.is_alive():
            return
        if self.playlist_analysis_thread and self.playlist_analysis_thread.is_alive():
            messagebox.showinfo("Análise em andamento", "Aguarde a análise da playlist terminar.", parent=self.root)
            return
        url = self.url_var.get().strip()
        valid, message = validate_url(url)
        if not valid:
            messagebox.showerror("URL inválida", message)
            return
        if not self._dependencies_checked or (self._dependency_refresh_thread and self._dependency_refresh_thread.is_alive()):
            messagebox.showinfo("Verificação em andamento", "Aguarde a verificação das dependências terminar e tente novamente.", parent=self.root)
            return
        for key in ("yt-dlp", "ffmpeg"):
            info = self.dep_infos[key]
            if not info.path or not info.executable_ok:
                messagebox.showerror("Dependência ausente", f"{key} não está disponível. Use Dependências → Instalar/Reparar automaticamente.")
                return
            if info.error:
                messagebox.showerror("Arquitetura incompatível", info.error)
                return
        playlist = self._looks_like_playlist(url)
        if playlist:
            choice = messagebox.askyesno(
                "Playlist detectada",
                "Esta URL parece ser uma playlist. Deseja abrir o gerenciador para ver quantos itens existem, escolher itens específicos e definir vídeo/MP3 e qualidade por item?",
                parent=self.root,
            )
            if choice:
                self._start_playlist_analysis(url)
            else:
                self.status_var.set("Análise da playlist cancelada; nenhum download iniciado.")
            return
        mode_text = self.mode_var.get()
        mode = "music" if "Música" in mode_text else "video"
        value = self._parse_quality()
        if mode == "music" and not validate_bitrate(value):
            messagebox.showerror("Bitrate inválido", "Escolha 128, 192 ou 320 kbps.")
            return
        if mode == "video" and not validate_quality(value):
            messagebox.showerror("Qualidade inválida", "Escolha 480p, 720p, 1080p, 1440p ou 2160p.")
            return
        self.cancel_requested.clear()
        self.download_btn.configure(state="disabled")
        self.analyze_playlist_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        # Start each job with a clean in-app console/log so old output cannot distract.
        self._clear_log()
        self.percent_var.set(0)
        self.percent_label.configure(text="0%")
        self.status_var.set("Consultando formatos..." if mode == "video" else "Baixando música...")
        self.stage_var.set("Preparando")
        self._append_log(f"Domínio: {self._safe_domain(url)}")
        self._append_log(f"Modo: {'música / MP3' if mode == 'music' else f'vídeo / {value}p'}")
        self._append_log("Playlist: todos os itens" if playlist else "Download individual")
        self.download_thread = threading.Thread(target=self._download_worker, args=(mode, url, value, playlist), daemon=True)
        self.download_thread.start()

    @staticmethod
    def _safe_domain(url: str) -> str:
        from urllib.parse import urlsplit
        try:
            return urlsplit(url).netloc or "<domínio desconhecido>"
        except ValueError:
            return "<URL inválida>"

    def cancel_download(self):
        self.cancel_requested.set()
        cancelled_any = False
        with self.active_downloaders_lock:
            active = list(self.active_downloaders.values())
        for downloader in active:
            try:
                downloader.cancel()
                cancelled_any = True
            except Exception:
                self.logger.debug("Falha ao cancelar item de playlist.", exc_info=True)
        if self.downloader:
            self.status_var.set("Cancelando...")
            self.downloader.cancel()
            cancelled_any = True
        if cancelled_any or (self.download_thread and self.download_thread.is_alive()):
            self.status_var.set("Cancelando downloads…")
            self.stage_var.set("Cancelando")

    def _finish_download(self, result):
        self.download_thread = None
        self.download_btn.configure(state="normal")
        self.analyze_playlist_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.downloader = None
        if isinstance(result, dict) and "exception" in result:
            self.status_var.set("Falha")
            self.stage_var.set("Erro")
            self._append_log("ERRO: " + result["exception"])
            messagebox.showerror("Erro no download", result["exception"])
            return
        self._append_log(result.message)
        if result.details:
            self._append_log("Detalhes:\n" + result.details[-6000:], raw=True)
        if getattr(result, "completed_with_warnings", False):
            self.status_var.set("Concluído com avisos")
            self.stage_var.set("Playlist processada; verifique os avisos")
            messagebox.showwarning(
                "Playlist processada com avisos",
                result.message + "\n\nAtive o Modo desenvolvedor nas Configurações para consultar os detalhes técnicos dos itens indisponíveis.",
            )
        elif result.returncode == 0:
            self.status_var.set(result.message)
            self.stage_var.set("Concluído")
            messagebox.showinfo("Download concluído", result.message)
        elif result.returncode == 130:
            self.status_var.set("Download cancelado")
            self.stage_var.set("Cancelado")
        else:
            self.status_var.set("Falha no download")
            self.stage_var.set("Erro")
            messagebox.showerror("Download", result.message + "\n\nAtive o Modo desenvolvedor nas Configurações para consultar os detalhes técnicos.")


def run() -> None:
    root = tk.Tk()
    try:
        # Do not expose Tk's empty default window while the fairly large UI is built.
        # If construction fails, destroy that hidden root and let bootstrap show recovery.
        root.withdraw()
        app = MediaDownloaderApp(root)
        # The helper keeps the previous install until the actual GUI has been built.
        try:
            from .config import clear_startup_repair_pending
            if not clear_startup_repair_pending():
                app.logger.warning("Não foi possível limpar o marcador de reparo após abrir a interface.")
        except Exception:
            app.logger.warning("Falha ao confirmar a abertura após reparo.", exc_info=True)
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.update_idletasks()
        root.deiconify()
        try:
            root.lift()
            root.focus_force()
        except tk.TclError:
            pass
        root.mainloop()
    except Exception:
        # Log the original GUI exception; a windowed EXE has no console to show it.
        try:
            from .config import LOG_DIR
            from .logging_utils import setup_logging
            setup_logging(LOG_DIR).exception("Falha grave ao construir ou executar a interface")
        except Exception:
            pass
        try:
            root.destroy()
        except tk.TclError:
            pass
        raise
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
