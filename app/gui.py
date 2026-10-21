from __future__ import annotations

import os
import re
import math
import io
import queue
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from tkinter import font as tkfont
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
from .brand_assets import load_brand_images
from .media_preview import fetch_thumbnail_bytes, inspect_media_preview
from .visual_effects import PALETTES as EFFECT_PALETTES, render_atom_art, render_gradient_preview, palette_colors

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
except ImportError:  # Source runs without Pillow; the stable Windows build bundles it.
    Image = ImageDraw = ImageFont = ImageTk = None


PALETTES = {
    "dark": {"bg":"#090A18","panel":"#111226","panel2":"#18182F","field":"#0B0C1A","fg":"#F5F3FF","muted":"#9EA3C7","border":"#302A4E","accent":"#8B5CF6","accent2":"#A78BFA","accent_fg":"#FFFFFF","good":"#34D399","warn":"#FBBF24","bad":"#FB7185","button":"#211C3A","button_hover":"#30234F","input_fg":"#F5F3FF","space":"#22D3EE","pink":"#EC4899"},
    "light": {"bg":"#F5F3FF","panel":"#FFFFFF","panel2":"#EEEBFF","field":"#FFFFFF","fg":"#21183D","muted":"#71688E","border":"#D9D1F2","accent":"#7C3AED","accent2":"#8B5CF6","accent_fg":"#FFFFFF","good":"#047857","warn":"#B45309","bad":"#BE123C","button":"#E9E3FA","button_hover":"#DCD2F7","input_fg":"#21183D","space":"#0891B2","pink":"#DB2777"},
    "oled": {"bg":"#000000","panel":"#090814","panel2":"#111022","field":"#05040A","fg":"#F5F3FF","muted":"#A5A0C7","border":"#27213D","accent":"#8B5CF6","accent2":"#A78BFA","accent_fg":"#FFFFFF","good":"#34D399","warn":"#FBBF24","bad":"#FB7185","button":"#100D21","button_hover":"#21173A","input_fg":"#F5F3FF","space":"#22D3EE","pink":"#EC4899"},
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


BUTTON_FILL_GRADIENT = ("#A855F7", "#497BFF", "#20CFE5", "#43DDAE")
BUTTON_OUTER_GRADIENT = ("#C05BFF", "#35D9FF", "#7A7BFF")
BUTTON_INNER_GRADIENT = ("#F472D0", "#6B9CFF", "#48E9B7")


def _cyclic_palette_color(palette: tuple[str, ...], position: float) -> str:
    """Interpolate a cyclic gradient continuously across its wrap point."""
    if not palette:
        return "#FFFFFF"
    if len(palette) == 1:
        return palette[0]
    scaled = (float(position) % 1.0) * len(palette)
    index = int(scaled)
    return _blend_hex(palette[index], palette[(index + 1) % len(palette)], scaled - index)


def _render_nav_icon(root, cache: dict, page_key: str, size: int, color: str):
    """Render crisp 4× supersampled navigation artwork when Pillow is available."""
    if Image is None or ImageDraw is None or ImageTk is None:
        return None
    key = (page_key, int(size), str(color))
    if key in cache:
        return cache[key]
    scale = 4
    icon_size = max(16, int(size))
    extent = icon_size * scale
    center = extent / 2
    art = Image.new("RGBA", (extent, extent), (0, 0, 0, 0))
    draw = ImageDraw.Draw(art)
    stroke = max(1, round(scale * 1.7))

    def point(x, y):
        return (round(center + x * scale), round(center + y * scale))

    def line(points, width=stroke):
        draw.line([point(x, y) for x, y in points], fill=color, width=width, joint="curve")

    def circle(x, y, radius, fill=None, outline=color, width=stroke):
        px, py = point(x, y)
        r = radius * scale
        draw.ellipse((round(px-r), round(py-r), round(px+r), round(py+r)),
                     fill=fill, outline=outline, width=width if outline else 1)

    def rect(left, top, right, bottom, radius=0, fill=None, outline=color, width=stroke):
        box = (round(center + left*scale), round(center + top*scale),
               round(center + right*scale), round(center + bottom*scale))
        if radius:
            draw.rounded_rectangle(box, radius=radius*scale, fill=fill, outline=outline, width=width)
        else:
            draw.rectangle(box, fill=fill, outline=outline, width=width)

    if page_key == "home":
        line([(-10, -1), (0, -10), (10, -1)])
        line([(-7, -3), (-7, 9), (7, 9), (7, -3)])
        line([(-2, 9), (-2, 2), (2, 2), (2, 9)])
    elif page_key == "playlist":
        for y in (-7, 0, 7):
            circle(-8, y, 1.1, fill=color, outline=None, width=1)
            line([(-4, y), (9, y)])
    elif page_key == "settings":
        circle(0, 0, 5.1, fill=None)
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            line([(math.cos(radians)*6.9, math.sin(radians)*6.9),
                  (math.cos(radians)*10.3, math.sin(radians)*10.3)])
        circle(0, 0, 2.4, fill=None, width=max(1, round(scale * 1.4)))
    elif page_key == "dependencies":
        line([(0, -11), (10, 0), (0, 11), (-10, 0), (0, -11)])
        line([(0, -5), (5, 0), (0, 5), (-5, 0), (0, -5)], width=max(1, round(scale * 1.4)))
        circle(0, 0, 1.3, fill=color, outline=None, width=1)
    elif page_key == "updates":
        box = (round(center-9*scale), round(center-9*scale),
               round(center+9*scale), round(center+9*scale))
        draw.arc(box, start=42, end=218, fill=color, width=stroke)
        draw.arc(box, start=222, end=398, fill=color, width=stroke)
        draw.polygon([point(6.8, -8.5), point(11.5, -8.1), point(9.1, -4.0)], fill=color)
        draw.polygon([point(-6.8, 8.5), point(-11.5, 8.1), point(-9.1, 4.0)], fill=color)
    elif page_key == "help":
        circle(0, 0, 10, fill=None)
        font = None
        if ImageFont is not None:
            for candidate in ("segoeui.ttf", "arial.ttf", "C:/Windows/Fonts/arial.ttf"):
                try:
                    font = ImageFont.truetype(candidate, size=15*scale)
                    break
                except OSError:
                    continue
        if font is None:
            font = ImageFont.load_default()
        draw.text(point(0, 0), "?", font=font, fill=color, anchor="mm")
    elif page_key == "developer":
        rect(-10, -8, 10, 6, radius=2, fill=None)
        line([(-5, 10), (5, 10)])
        line([(0, 6), (0, 10)])
        line([(-5, -3), (-2, 0), (-5, 3)])
        line([(0, 3), (5, 3)])
    else:
        return None

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    scaled = art.resize((icon_size, icon_size), resample=resampling)
    photo = ImageTk.PhotoImage(scaled, master=root)
    cache[key] = photo
    return photo


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
    """Scrollable content whose wheel bindings only affect the visible, owning frame."""

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
        # bind_all is application-wide; each frame must ignore events owned by
        # another tab, otherwise every hidden scrollable page moves together.
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")
        self.canvas.bind_all("<Button-4>", self._wheel_global, add="+")
        self.canvas.bind_all("<Button-5>", self._wheel_global, add="+")

    def _event_inside(self, event):
        widget = getattr(event, "widget", None)
        while widget is not None:
            if widget is self.body or widget is self.canvas or widget is self.scrollbar:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _wheel(self, event):
        if not self.winfo_ismapped() or not self._event_inside(event):
            return None
        delta = int(getattr(event, "delta", 0))
        if not delta:
            return None
        units = int(-delta / 120)
        if units == 0:
            units = -1 if delta > 0 else 1
        self.canvas.yview_scroll(units, "units")
        return "break"

    def _wheel_global(self, event):
        if not self.winfo_ismapped() or not self._event_inside(event):
            return None
        button = getattr(event, "num", None)
        if button == 4:
            self.canvas.yview_scroll(-1, "units")
        elif button == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            return self._wheel(event)
        return "break"

def _rounded_polygon(x1: float, y1: float, x2: float, y2: float, radius: float) -> list[float]:
    """Return points sampled along real quarter-circles for a crisp rounded rectangle."""
    r = max(2.0, min(radius, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    points: list[tuple[float, float]] = [(x1 + r, y1), (x2 - r, y1)]

    def arc(cx: float, cy: float, start: float, end: float, increment: float = 6.0):
        steps = max(1, math.ceil((end - start) / increment))
        for step in range(1, steps + 1):
            angle = math.radians(start + (end - start) * step / steps)
            points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    arc(x2 - r, y1 + r, -90, 0)
    points.append((x2, y2 - r))
    arc(x2 - r, y2 - r, 0, 90)
    points.append((x1 + r, y2))
    arc(x1 + r, y2 - r, 90, 180)
    points.append((x1, y1 + r))
    arc(x1 + r, y1 + r, 180, 270)
    return [coordinate for point in points for coordinate in point]


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
                    _rounded_polygon(1, 1, width - 2, height - 2, 15),
                    smooth=False, splinesteps=14, fill=surface,
                    outline=_blend_hex(colors.get("accent", "#8B5CF6"), colors.get("border", surface), 0.70),
                    width=1, tags="surface",
                )
            self._canvas.lower()
        except tk.TclError:
            pass


class IconNavButton(tk.Canvas):
    """Compact launcher-style icon button with a soft active pill and hover scale."""

    def __init__(self, parent, app, key: str, glyph: str, command: Callable[[], None]):
        super().__init__(
            parent, width=184, height=42, bd=0, highlightthickness=0,
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

    def _draw_vector_icon(self, cx: float, cy: float, size: int, color: str):
        """Vector fallback for installations without Pillow."""
        width = max(1.5, size / 10)
        def line(points):
            flattened = [coordinate for point in points for coordinate in point]
            self.create_line(*flattened, fill=color, width=width, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        def oval(x, y, radius, fill="", outline=color):
            self.create_oval(cx+x-radius, cy+y-radius, cx+x+radius, cy+y+radius,
                             fill=fill, outline=outline, width=width)
        def rect(left, top, right, bottom, radius=2):
            self.create_polygon(_rounded_polygon(cx+left, cy+top, cx+right, cy+bottom, radius),
                                smooth=False, outline=color, fill="", width=width)
        if self.page_key == "home":
            line([(cx-size*.48,cy-size*.02),(cx,cy-size*.48),(cx+size*.48,cy-size*.02)])
            line([(cx-size*.35,cy-size*.14),(cx-size*.35,cy+size*.40),(cx+size*.35,cy+size*.40),(cx+size*.35,cy-size*.14)])
            line([(cx-size*.08,cy+size*.40),(cx-size*.08,cy+size*.08),(cx+size*.08,cy+size*.08),(cx+size*.08,cy+size*.40)])
        elif self.page_key == "playlist":
            for y in (-size*.30, 0, size*.30):
                oval(-size*.38, y, max(1.2,size*.055), fill=color, outline=color)
                line([(cx-size*.20,cy+y),(cx+size*.40,cy+y)])
        elif self.page_key == "settings":
            for angle in range(0,360,45):
                a=math.radians(angle)
                line([(cx+math.cos(a)*size*.30,cy+math.sin(a)*size*.30),
                      (cx+math.cos(a)*size*.48,cy+math.sin(a)*size*.48)])
            oval(0,0,size*.30,outline=color)
            oval(0,0,size*.12,outline=color)
        elif self.page_key == "dependencies":
            line([(cx,cy-size*.50),(cx+size*.45,cy),(cx,cy+size*.50),(cx-size*.45,cy),(cx,cy-size*.50)])
            line([(cx,cy-size*.22),(cx+size*.20,cy),(cx,cy+size*.22),(cx-size*.20,cy),(cx,cy-size*.22)])
        elif self.page_key == "updates":
            self.create_arc(cx-size*.42,cy-size*.42,cx+size*.42,cy+size*.42,start=35,extent=245,
                            style=tk.ARC,outline=color,width=width)
            self.create_polygon((cx+size*.28,cy-size*.46,cx+size*.55,cy-size*.43,cx+size*.39,cy-size*.19),
                                fill=color,outline=color)
            self.create_arc(cx-size*.42,cy-size*.42,cx+size*.42,cy+size*.42,start=215,extent=125,
                            style=tk.ARC,outline=color,width=width)
            self.create_polygon((cx-size*.28,cy+size*.46,cx-size*.55,cy+size*.43,cx-size*.39,cy+size*.19),
                                fill=color,outline=color)
        elif self.page_key == "help":
            oval(0,0,size*.45,outline=color)
            self.create_text(cx,cy,text="?",fill=color,font=("Segoe UI",max(10,int(size*.72)),"bold"))
        elif self.page_key == "developer":
            rect(-size*.46,-size*.34,size*.46,size*.26,radius=3)
            line([(cx-size*.22,cy+size*.45),(cx+size*.22,cy+size*.45)])
            line([(cx,cy+size*.26),(cx,cy+size*.45)])
            line([(cx-size*.22,cy-size*.09),(cx-size*.08,cy),(cx-size*.22,cy+size*.09)])
            line([(cx,cy+size*.09),(cx+size*.25,cy+size*.09)])

    def _draw(self):
        try:
            self.delete("all")
            width = max(184, self.winfo_width())
            height = max(42, self.winfo_height())
            colors = self.app.colors
            panel = colors.get("panel2", "#090814")
            accent = colors.get("accent", "#8B5CF6")
            palette = palette_colors(self.app.config.get("visual_palette", "cosmic"))
            if self.active or self.hovered:
                surface = _blend_hex(accent, panel, 0.66 if self.active else 0.86)
                self.create_polygon(_rounded_polygon(2, 1, width - 2, height - 1, 12),
                                    smooth=False, fill=surface,
                                    outline=_blend_hex(palette[1], panel, 0.18 if self.active else 0.58),
                                    width=1.2 if self.active else 1)
                if self.active:
                    self.create_polygon(_rounded_polygon(1, height / 2 - 8, 4, height / 2 + 8, 2),
                                        fill=palette[0], outline="", smooth=False)
            icon_color = palette[0] if self.active else (colors["fg"] if self.hovered else colors["muted"])
            icon_size = max(19, int(21 * self._scale))
            photo = _render_nav_icon(self.app.root, self.app._nav_icon_cache, self.page_key, icon_size, icon_color)
            if photo is not None:
                self._icon_photo = photo
                self.create_image(26, height / 2, image=photo)
            else:
                self._draw_vector_icon(26, height / 2, icon_size, icon_color)
            label = {"home":"Início","playlist":"Playlists","settings":"Aparência",
                     "dependencies":"Dependências","updates":"Atualizações",
                     "help":"Ajuda","developer":"Diagnóstico"}.get(self.page_key, self.page_key)
            self.create_text(51, height / 2, text=label,
                             fill=colors["fg"] if self.active or self.hovered else colors["muted"],
                             font=("Segoe UI", 10, "bold" if self.active else "normal"), anchor="w")
        except tk.TclError:
            pass

class RoundedGlowButton(tk.Canvas):
    """A real clickable rounded button with restrained product styling and keyboard support."""

    def __init__(self, parent, **kwargs):
        self.app = getattr(parent.winfo_toplevel(), "_media_downloader_app", None)
        if self.app is None:
            raise RuntimeError("RoundedGlowButton requires a registered application window.")
        self.text = str(kwargs.pop("text", ""))
        self.command = kwargs.pop("command", None)
        self.style_name = str(kwargs.pop("style", "Secondary.TButton"))
        self._state = str(kwargs.pop("state", "normal"))
        width_units = kwargs.pop("width", None)
        kwargs.pop("padding", None)
        kwargs.pop("default", None)
        kwargs.pop("underline", None)
        self._pressed = False
        self._hovered = False
        self._focused = False
        self._gradient_phase = 0.0
        self._gradient_strength = 0.0
        self._gradient_job = None
        self._textvariable = kwargs.pop("textvariable", None)
        self._font = tkfont.Font(
            root=self.app.root, family="Segoe UI",
            size=9 if self.style_name == "Help.TButton" else 10,
            weight="bold" if self.style_name == "Accent.TButton" else "normal",
        )
        self._height = 28 if self.style_name == "Help.TButton" else (40 if self.style_name == "Accent.TButton" else 36)
        measured = self._font.measure(self.text)
        if self._textvariable is not None:
            try:
                self.text = str(self._textvariable.get())
                measured = self._font.measure(self.text)
                self._textvariable.trace_add("write", self._text_changed)
            except Exception:
                self._textvariable = None
        if width_units is not None and self.style_name == "Help.TButton":
            self._natural_width = 38
        else:
            self._natural_width = max(48, min(420, measured + (28 if self.style_name != "Help.TButton" else 18)))
        bg = self._parent_background(parent)
        super().__init__(
            parent, width=self._natural_width, height=self._height,
            bd=0, borderwidth=0, highlightthickness=0, takefocus=1,
            cursor="hand2" if self._state != "disabled" else "arrow",
            background=bg,
        )
        self.bind("<Configure>", lambda _event: self._draw(), add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<FocusIn>", self._on_focus_in, add="+")
        self.bind("<FocusOut>", self._on_focus_out, add="+")
        self.bind("<Return>", self._on_keyboard_activate, add="+")
        self.bind("<space>", self._on_keyboard_activate, add="+")
        self._draw()

    def _text_changed(self, *_args):
        try:
            self.text = str(self._textvariable.get())
        except Exception:
            pass
        self._recalculate_size()
        self._draw()

    def _parent_background(self, parent):
        colors = self.app.colors
        if isinstance(parent, RoundedCard):
            return colors.get(parent.backdrop_key, colors["bg"])
        try:
            style_name = str(parent.cget("style") or "TFrame")
        except (tk.TclError, TypeError):
            style_name = "TFrame"
        key = {
            "Card.TFrame": "panel",
            "Hero.TFrame": "panel2",
            "Sidebar.TFrame": "panel2",
            "Topbar.TFrame": "bg",
            "RoundedCard.TFrame": "panel",
        }.get(style_name, "bg")
        return colors.get(key, colors["bg"])

    def _recalculate_size(self):
        measured = self._font.measure(self.text)
        self._natural_width = max(48, min(420, measured + (28 if self.style_name != "Help.TButton" else 18)))
        try:
            tk.Canvas.configure(self, width=self._natural_width, height=self._height)
        except tk.TclError:
            pass

    @staticmethod
    def _span(y, top, bottom, left, right, radius):
        center_y = (top + bottom) / 2.0
        half_height = (bottom - top) / 2.0
        depth = abs(y - center_y) - (half_height - radius)
        inset = radius - math.sqrt(max(0.0, radius * radius - depth * depth)) if depth > 0 else 0.0
        return math.ceil(left + inset), math.floor(right - inset)

    def _palette(self):
        c = self.app.colors
        if self.style_name == "Accent.TButton":
            edge = _blend_hex(c["accent"], "#000000", 0.12)
            top = c["accent"]
            bottom = _blend_hex(c["accent"], "#000000", 0.06)
            text_color = c.get("accent_fg", "#FFFFFF")
        elif self.style_name == "Danger.TButton":
            edge = _blend_hex(c["bad"], "#000000", 0.12)
            top = c["bad"]
            bottom = _blend_hex(c["bad"], "#000000", 0.06)
            text_color = "#FFFFFF"
        elif self.style_name == "Help.TButton":
            edge = c["border"]
            top = c["button_hover"] if self._hovered or self._focused else c["button"]
            bottom = top
            text_color = c["fg"]
        else:
            edge = c["border"] if not (self._hovered or self._focused) else c["accent"]
            top = c["button_hover"] if self._hovered or self._focused else c["button"]
            bottom = top
            text_color = c["fg"]
        if self._state == "disabled":
            edge = _blend_hex(edge, c["muted"], 0.56)
            top = _blend_hex(top, c["panel2"], 0.60)
            bottom = _blend_hex(bottom, c["panel2"], 0.64)
            text_color = _blend_hex(c["fg"], c["panel2"], 0.42)
        elif self._pressed:
            top = _blend_hex(top, "#000000", 0.12)
            bottom = top
        return edge, top, bottom, text_color

    def _draw_gradient_outline(self, width, height, inset, radius, palette, phase, line_width):
        points = _rounded_polygon(inset, inset, width - inset, height - inset, radius)
        point_count = len(points) // 2
        if point_count < 3:
            return
        stride = max(1, point_count // 42)
        for index in range(0, point_count, stride):
            next_index = (index + stride) % point_count
            color = _cyclic_palette_color(palette, phase + index / point_count)
            self.create_line(
                points[index * 2], points[index * 2 + 1],
                points[next_index * 2], points[next_index * 2 + 1],
                fill=color, width=max(0.5, line_width), capstyle=tk.ROUND,
            )

    def _gradient_is_available(self):
        return self._state != "disabled" and self.style_name not in {"Danger.TButton", "Help.TButton"}

    def _schedule_gradient_animation(self):
        if self._gradient_job is None:
            try:
                self._gradient_job = self.after(40, self._animate_gradient)
            except tk.TclError:
                self._gradient_job = None

    def _animate_gradient(self):
        self._gradient_job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        animations_enabled = bool(self.app.config.get("animations_enabled", False))
        if self._hovered and self._gradient_is_available():
            self._gradient_strength = min(1.0, self._gradient_strength + 0.22)
            if animations_enabled:
                self._gradient_phase = (self._gradient_phase + 0.016) % 1.0
            else:
                self._gradient_phase = 0.0
        else:
            self._gradient_strength *= 0.76
            if animations_enabled:
                delta = ((-self._gradient_phase + 0.5) % 1.0) - 0.5
                self._gradient_phase = (self._gradient_phase + delta * 0.24) % 1.0
            else:
                self._gradient_phase = 0.0
            if (self._gradient_strength < 0.008
                    and min(self._gradient_phase, 1.0 - self._gradient_phase) < 0.003):
                self._gradient_strength = 0.0
                self._gradient_phase = 0.0
        self._draw()
        still_animating = (
            (self._hovered and self._gradient_is_available() and animations_enabled)
            or self._gradient_strength > 0.0
            or self._gradient_phase != 0.0
        )
        if still_animating:
            self._schedule_gradient_animation()

    def _draw(self):
        """Draw crisp, static dual neon borders; only the button fill changes on hover."""
        try:
            width = max(self._natural_width, self.winfo_width(), 38)
            height = max(self._height, self.winfo_height(), 26)
            c = self.app.colors
            bg = self._parent_background(self.master)
            tk.Canvas.configure(self, background=bg, cursor="arrow" if self._state == "disabled" else "hand2")
            self.delete("all")
            edge, top, bottom, text_color = self._palette()
            has_gradient = self._gradient_is_available()
            hovering = (self._hovered or self._focused) and has_gradient
            strength = 1.0 if hovering else 0.0
            outer_inset, inner_inset = 1.0, 3.0
            outer_radius = max(9, height / 2 - outer_inset)
            inner_radius = max(7, height / 2 - inner_inset)
            self.create_polygon(_rounded_polygon(outer_inset, outer_inset, width-outer_inset, height-outer_inset, outer_radius),
                                fill=_blend_hex(edge, bg, 0.24), outline="", width=1)
            x0, y0, x1, y1 = inner_inset, inner_inset, width-inner_inset, height-inner_inset
            self.create_polygon(_rounded_polygon(x0, y0, x1, y1, inner_radius), fill=bottom, outline="")
            for y in range(int(y0+1), int(y1)):
                left, right = self._span(y, y0+1, y1-1, x0+1, x1-1, inner_radius-1)
                if left <= right:
                    t = (y-y0) / max(1, y1-y0)
                    color = _blend_hex(top, bottom, max(0.0, min(1.0, t)))
                    if strength:
                        tint = _cyclic_palette_color(palette_colors(self.app.config.get("visual_palette", "cosmic")), t*0.36)
                        color = _blend_hex(color, tint, 0.36)
                    self.create_line(left, y, right, y, fill=color, width=1)
            self.create_polygon(_rounded_polygon(outer_inset, outer_inset, width-outer_inset, height-outer_inset, outer_radius),
                                fill="", outline=_blend_hex(edge, "#FFFFFF", 0.20), width=0.8)
            if has_gradient:
                palette = palette_colors(self.app.config.get("visual_palette", "cosmic"))
                inner_palette = tuple(_blend_hex(value, "#D8D5FF", 0.24) for value in reversed(palette))
                # Two continuously colored outlines remain visible even when not hovered.
                self._draw_gradient_outline(width, height, outer_inset, outer_radius, palette, 0.03, 1.55)
                self._draw_gradient_outline(width, height, inner_inset+0.7, inner_radius, inner_palette, 0.39, 0.95)
            else:
                self.create_polygon(_rounded_polygon(outer_inset, outer_inset, width-outer_inset, height-outer_inset, outer_radius),
                                    fill="", outline=edge, width=1.1)
            self.create_text(width/2, height/2 + (0.5 if self._pressed else 0), text=self.text,
                             fill=text_color, font=self._font, anchor="center", width=max(10, width-20))
        except tk.TclError:
            pass

    def _on_enter(self, _event=None):
        self._hovered = True
        self._gradient_strength = 1.0
        self._gradient_phase = 0.0
        self._draw()

    def _on_leave(self, _event=None):
        self._hovered = False
        self._pressed = False
        self._gradient_strength = 0.0
        self._gradient_phase = 0.0
        self._draw()

    def _on_press(self, _event=None):
        if self._state == "disabled":
            return "break"
        self._pressed = True
        self.focus_set()
        self._draw()
        return None

    def _on_release(self, event=None):
        should_invoke = self._pressed and self._state != "disabled"
        if event is not None:
            should_invoke = should_invoke and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self._pressed = False
        self._draw()
        if should_invoke:
            self.invoke()
        return None

    def _on_keyboard_activate(self, _event=None):
        if self._state != "disabled":
            self._pressed = True
            self._draw()
            self.after(75, self._release_keyboard)
            self.invoke()
        return "break"

    def _release_keyboard(self):
        self._pressed = False
        self._draw()

    def _on_focus_in(self, _event=None):
        self._focused = True
        self._draw()

    def _on_focus_out(self, _event=None):
        self._focused = False
        self._draw()

    def refresh_theme(self):
        self._draw()

    def invoke(self):
        if self._state == "disabled" or not callable(self.command):
            return None
        return self.command()

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
        if not kwargs:
            return tk.Canvas.configure(self)
        if "text" in kwargs:
            self.text = str(kwargs.pop("text"))
            self._recalculate_size()
        if "command" in kwargs:
            self.command = kwargs.pop("command")
        if "style" in kwargs:
            self.style_name = str(kwargs.pop("style"))
            self._font.configure(
                size=9 if self.style_name == "Help.TButton" else 10,
                weight="bold" if self.style_name == "Accent.TButton" else "normal",
            )
            self._height = 28 if self.style_name == "Help.TButton" else (40 if self.style_name == "Accent.TButton" else 36)
            self._recalculate_size()
        if "state" in kwargs:
            self._state = str(kwargs.pop("state"))
            self._pressed = False
        if "width" in kwargs:
            value = kwargs.pop("width")
            if isinstance(value, (int, float)) and self.style_name == "Help.TButton":
                self._natural_width = max(34, int(value) * 10 + 18)
                tk.Canvas.configure(self, width=self._natural_width)
        if "padding" in kwargs:
            kwargs.pop("padding")
        allowed = {k: v for k, v in kwargs.items() if k in {"background", "bg", "cursor", "takefocus", "height", "highlightthickness", "highlightbackground", "highlightcolor"}}
        if allowed:
            tk.Canvas.configure(self, **allowed)
        self._draw()

    config = configure

    def cget(self, key):
        if key == "text":
            return self.text
        if key == "state":
            return self._state
        if key == "style":
            return self.style_name
        if key == "command":
            return self.command
        return tk.Canvas.cget(self, key)


class MediaDownloaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root._media_downloader_app = self
        self.system = detect_system()
        self.config = load_config()
        self.install_id = ensure_install_id()
        from .logging_utils import setup_logging
        self.logger = setup_logging(LOG_DIR)
        self.logger.info("Inicialização: %s", self.system.architecture_label)

        self.root.title(f"Media Downloader | v{VERSION}")
        self._window_icon = None
        try:
            icon_path = Path(__file__).resolve().parents[1] / "assets" / "app-icon.png"
            if icon_path.is_file() and Image is not None and ImageTk is not None:
                with Image.open(icon_path) as icon_image:
                    self._window_icon = ImageTk.PhotoImage(icon_image.convert("RGBA").resize((64, 64)))
                self.root.iconphoto(True, self._window_icon)
        except (OSError, tk.TclError) as exc:
            self.logger.debug("Não foi possível carregar o ícone da janela: %s", exc)
        self.root.geometry("1220x820")
        self.root.minsize(1000, 680)

        self.style = ttk.Style(root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.brand_images = load_brand_images(root)
        self.palette_name = "dark"
        self.colors: dict[str, str] = {}
        self._nav_icon_cache: dict[tuple[str, int, str], object] = {}
        self._media_preview_generation = 0
        self._media_preview_after = None
        self._media_preview_visible = False
        self._playlist_thumbnail_cache: dict[str, object] = {}
        self._playlist_thumbnail_requested: set[str] = set()
        self._playlist_thumbnail_loaded: set[str] = set()
        self._playlist_thumbnail_failed: set[str] = set()
        self._thumbnail_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cgmd-thumbnail")
        self.media_preview_photo = None
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
        self.animations_enabled_var = tk.BooleanVar(value=bool(self.config.get("animations_enabled", False)))
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
        self.media_preview_title_var = tk.StringVar(value="A prévia aparecerá aqui")
        self.media_preview_meta_var = tk.StringVar(value="Cole um link de vídeo ou áudio")
        self.media_preview_status_var = tk.StringVar(value="Prévia automática aguardando um link")
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
        # Optional low-motion orbit animation drawn with Canvas; disabled for new profiles.
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
        accent = str(self.config.get("accent_color","#2563EB") or "#2563EB").strip()
        if _valid_hex_color(accent):
            c["accent"] = accent.upper()
            c["accent2"] = _blend_hex(accent.upper(),"#FFFFFF" if self.palette_name!="light" else "#000000",0.18)
            c["accent_fg"] = _contrast_text(accent.upper())
        else:
            self.config["accent_color"] = "#2563EB"
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
        self.style.configure("BrandWordmark.TLabel",background=c["panel2"],foreground=c["fg"],font=("Segoe UI",8,"bold"))
        self.style.configure("PreviewEyebrow.TLabel",background=c["panel"],foreground=c["accent"],font=("Segoe UI",9,"bold"))
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
        self.style.configure(
            "TEntry", padding=10 if not compact else 7, fieldbackground=c["field"],
            foreground=c["input_fg"], bordercolor=c["border"], lightcolor=c["border"],
            darkcolor=c["border"], relief="flat", borderwidth=1, insertcolor=c["fg"],
        )
        self.style.map(
            "TEntry", bordercolor=[("focus", c["accent"]), ("!focus", c["border"])],
            lightcolor=[("focus", c["accent"]), ("!focus", c["border"])],
            darkcolor=[("focus", c["accent"]), ("!focus", c["border"])],
        )
        self.style.configure(
            "TCombobox", padding=8 if not compact else 6, fieldbackground=c["field"],
            foreground=c["input_fg"], arrowcolor=c["accent"], bordercolor=c["border"],
            lightcolor=c["border"], darkcolor=c["border"], relief="flat", borderwidth=1,
            arrowsize=13,
        )
        self.style.map(
            "TCombobox", fieldbackground=[("readonly", c["field"])],
            foreground=[("readonly", c["input_fg"])],
            bordercolor=[("focus", c["accent"]), ("!focus", c["border"])],
            lightcolor=[("focus", c["accent"]), ("!focus", c["border"])],
            darkcolor=[("focus", c["accent"]), ("!focus", c["border"])],
        )
        self.style.configure("TProgressbar",thickness=10 if compact else 12,troughcolor=c["panel2"],background=c["accent"])
        self.style.configure("Treeview",background=c["field"],fieldbackground=c["field"],foreground=c["fg"],rowheight=50 if compact else 58,bordercolor=c["border"])
        self.style.map("Treeview",background=[("selected",c["accent2"])],foreground=[("selected",c["accent_fg"])])
        self.style.configure("Treeview.Heading",background=c["panel2"],foreground=c["fg"],relief="flat",padding=(8,7),font=("Segoe UI",9,"bold"))
        self.style.map("Treeview.Heading",background=[("active",c["button_hover"])])
        self.style.configure("Status.TLabel",background=c["panel2"],foreground=c["fg"],padding=8)
        self.style.configure("SectionBadge.TLabel",background=c["panel2"],foreground=c["accent"],padding=(8,4))
        self.style.configure("Help.TButton",width=2,padding=2,foreground=c["accent"],background=c["panel"],borderwidth=0)
        self.style.configure("Danger.TButton",foreground="#FFFFFF",background=c["bad"])
        self.style.map("Danger.TButton",background=[("active",c["bad"]),("!disabled",c["bad"])])
        self.style.configure(
            "TCheckbutton", background=c["panel"], foreground=c["fg"],
            padding=(2, 4), indicatorcolor=c["field"], indicatorrelief="flat",
            focuscolor=c["bg"], bordercolor=c["border"], lightcolor=c["border"],
            darkcolor=c["border"],
        )
        self.style.map(
            "TCheckbutton", background=[("active", c["panel"])],
            foreground=[("disabled", c["muted"])],
            indicatorcolor=[("selected", c["accent"]), ("pressed", c["accent2"]), ("!selected", c["field"])],
            bordercolor=[("focus", c["accent"]), ("!focus", c["border"])],
        )
        for scrollbar_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            self.style.configure(
                scrollbar_style, background=c["panel2"], troughcolor=c["bg"],
                bordercolor=c["border"], lightcolor=c["panel2"], darkcolor=c["panel"],
                arrowcolor=c["muted"], relief="flat", gripcount=0,
            )
            self.style.map(
                scrollbar_style, background=[("active", c["accent2"]), ("!active", c["panel2"])],
                troughcolor=[("!disabled", c["bg"])],
            )
        if hasattr(self,"log_text"):
            self.log_text.configure(bg=c["field"],fg=c["fg"],insertbackground=c["fg"],selectbackground=c["accent"],selectforeground=c["accent_fg"])
        if hasattr(self,"dep_badge"):
            self.dep_badge.configure(bg=c["panel2"],fg=c["muted"])
        if hasattr(self,"playlist_warning"):
            self.playlist_warning.configure(bg=c["panel2"],fg=c["warn"])
        if hasattr(self, "media_preview_poster"):
            self.media_preview_poster.configure(bg=c["panel2"])
        if hasattr(self, "brand_logo_canvas"):
            self.brand_logo_canvas.configure(background=c["panel2"])
            self._draw_brand_logo()
        if hasattr(self, "media_preview_placeholder") and not self.media_preview_photo:
            self.media_preview_placeholder = self._make_thumbnail_placeholder(220, 124)
            self.media_preview_poster.configure(image=self.media_preview_placeholder)
        if hasattr(self, "playlist_thumbnail_placeholder"):
            self.playlist_thumbnail_placeholder = self._make_thumbnail_placeholder(76, 43)
            self._render_playlist_rows()
        if hasattr(self,"hero_accent_bar"):
            self.hero_accent_bar.configure(bg=c["accent"])
        def tint(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Canvas):
                    try:
                        if getattr(child, "_rounded_card_background", False):
                            child.master.redraw()
                        elif getattr(child, "_brand_logo_canvas", False):
                            child.configure(background=c["panel2"])
                            self._draw_brand_logo()
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
        outer = ttk.Frame(self.root, padding=13)
        outer.pack(fill="both", expand=True)
        self.shell = outer
        sidebar = ttk.Frame(outer, style="Sidebar.TFrame", padding=(10, 13, 10, 12), width=216)
        sidebar.pack(side="left", fill="y", padx=(0, 13))
        sidebar.pack_propagate(False)
        self.sidebar = sidebar
        brand = ttk.Frame(sidebar, style="Sidebar.TFrame")
        brand.pack(fill="x", pady=(3, 17))
        self.brand_logo_canvas = tk.Canvas(brand, width=54, height=54, bg=self.colors["panel2"], bd=0, highlightthickness=0, relief="flat")
        self.brand_logo_canvas._brand_logo_canvas = True
        self.brand_logo_canvas.pack(side="left", padx=(1, 8))
        self._draw_brand_logo()
        brand_copy = ttk.Frame(brand, style="Sidebar.TFrame")
        brand_copy.pack(side="left", fill="x", expand=True, anchor="center")
        ttk.Label(brand_copy, text="ChatGPT Media", style="BrandWordmark.TLabel", anchor="w", font=("Segoe UI", 9, "bold")).pack(fill="x", anchor="w")
        ttk.Label(brand_copy, text="Downloader", style="SidebarMuted.TLabel", anchor="w", font=("Segoe UI", 8)).pack(fill="x", anchor="w", pady=(2, 0))
        ttk.Label(brand_copy, text="Vídeos · áudio", style="SidebarMuted.TLabel", anchor="w", font=("Segoe UI", 7)).pack(fill="x", anchor="w", pady=(2, 0))
        ttk.Separator(sidebar).pack(fill="x", pady=(0, 12))
        self.nav_buttons = {}
        items = [
            ("home", "⌂", "Início", "Baixe vídeo ou áudio, acompanhe progresso e consulte atividade."),
            ("playlist", "▤", "Playlists", "Analise playlists, selecione itens e ajuste opções por mídia."),
            ("settings", "⚙", "Aparência", "Personalize tema, gradientes, pastas e comportamento."),
            ("dependencies", "◈", "Dependências", "Confira yt-dlp, FFmpeg e FFprobe."),
            ("updates", "⟳", "Atualizações", "Atualize ou recupere arquivos oficiais do aplicativo."),
            ("help", "?", "Ajuda", "Guias de uso, qualidade, playlists e segurança."),
            ("developer", "⌘", "Diagnóstico", "Versão, ambiente, logs e desinstalação."),
        ]
        for key, glyph, label, tip in items:
            button = IconNavButton(sidebar, self, key, glyph, lambda k=key: self.show_page(k))
            button.pack(fill="x", padx=0, pady=3)
            self.nav_buttons[key] = button
            Tooltip(button, f"{label}\\n{tip}", delay_ms=500, click_to_pin=False)
        spacer = ttk.Frame(sidebar, style="Sidebar.TFrame")
        spacer.pack(fill="both", expand=True)
        ttk.Separator(sidebar).pack(fill="x", pady=(12, 9))
        self.dep_badge = tk.Label(sidebar, text="●  Dependências", bg=self.colors["panel2"], fg=self.colors["muted"], anchor="w", font=("Segoe UI", 8, "bold"), padx=9, pady=8)
        self.dep_badge.pack(fill="x", pady=(0, 6))
        Tooltip(self.dep_badge, "Veja a aba Dependências para conferir o estado atual.", delay_ms=500, click_to_pin=False)
        ttk.Label(sidebar, text=f"v{VERSION}", style="SidebarMuted.TLabel", anchor="w", font=("Segoe UI", 7)).pack(fill="x", padx=(8, 0))
        content_wrap = ttk.Frame(outer)
        content_wrap.pack(side="left", fill="both", expand=True)
        self.content_wrap = content_wrap
        header = ttk.Frame(content_wrap, style="Topbar.TFrame")
        header.pack(fill="x", pady=(4, 13))
        header_left = ttk.Frame(header, style="Topbar.TFrame")
        header_left.pack(side="left", fill="x", expand=True)
        ttk.Label(header_left, text="CHATGPT MEDIA DOWNLOADER  /  CENTRAL DE MÍDIA", style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 3))
        self.page_title_var = tk.StringVar(value="Início")
        ttk.Label(header_left, textvariable=self.page_title_var, style="PageTitle.TLabel").pack(anchor="w")
        self.page_subtitle_var = tk.StringVar(value="Vídeos, músicas e playlists em um só lugar.")
        ttk.Label(header_left, textvariable=self.page_subtitle_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))
        header_actions = ttk.Frame(header, style="Topbar.TFrame")
        header_actions.pack(side="right", anchor="n", padx=(10, 0), pady=(9, 0))
        ttk.Label(header_actions, text=f"v{VERSION}", style="SectionBadge.TLabel").pack(side="left", padx=(0, 8))
        self.header_update_btn = RoundedGlowButton(header_actions, text="Atualizações  ↗", style="Secondary.TButton", command=lambda: self.show_page("updates"))
        self.header_update_btn.pack(side="left")
        self.pages_area = ttk.Frame(content_wrap)
        self.pages_area.pack(fill="both", expand=True)

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
            hero, width=238, height=154, bg=self.colors["panel2"],
            highlightthickness=0, bd=0,
        )
        self.hero_visual.pack(side="right", fill="y", padx=(12, 0))
        self.hero_visual.bind("<Configure>", lambda _event: self._render_static_visuals(), add="+")
        hero_body=ttk.Frame(hero,style="Hero.TFrame")
        hero_body.pack(side="left",fill="both",expand=True)
        hero_top=ttk.Frame(hero_body,style="Hero.TFrame")
        hero_top.pack(fill="x")
        ttk.Label(hero_top,text="CENTRAL DE DOWNLOADS",style="HeroEyebrow.TLabel").pack(side="left")
        ttk.Label(hero_top,text="VÍDEO  ·  ÁUDIO  ·  PLAYLISTS",style="HeroMuted.TLabel",font=("Segoe UI",8,"bold")).pack(side="right")
        ttk.Label(hero_body,text="Downloads de mídia, com controle.",style="HeroTitle.TLabel").pack(anchor="w",pady=(7,2))
        ttk.Label(hero_body,text="Cole um link, escolha o formato e acompanhe o progresso.",style="HeroMuted.TLabel",wraplength=760).pack(anchor="w",pady=(0,15))
        self.url_entry=ttk.Entry(hero_body,textvariable=self.url_var,font=("Segoe UI",12))
        self.url_entry.pack(fill="x")
        self.url_entry.focus_set()
        self.url_entry.bind("<Return>",lambda _e:self.start_download())
        self.url_var.trace_add("write",self._update_playlist_warning)
        self.url_var.trace_add("write", self._schedule_media_preview)
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
        self.download_btn=RoundedGlowButton(buttons,text="↓  BAIXAR AGORA",style="Accent.TButton",command=self.start_download)
        self.download_btn.pack(side="right")
        self.analyze_playlist_btn=RoundedGlowButton(buttons,text="Analisar playlist",style="Secondary.TButton",command=self._start_playlist_analysis)
        self.analyze_playlist_btn.pack(side="right",padx=(0,8))

        quick_actions = ttk.Frame(frame)
        quick_actions.pack(fill="x", pady=(0, 12))
        quick_specs = [
            ("Vídeos", "MP4 · qualidade configurável", lambda: self._select_download_mode("Vídeo")),
            ("Áudio MP3", "MP3 · bitrate configurável", lambda: self._select_download_mode("Música — MP3")),
            ("Playlists", "Escolha itens individuais", lambda: self.show_page("playlist")),
        ]
        for index, (title, description, action) in enumerate(quick_specs):
            card = self._card(quick_actions, 11)
            left = 0 if index == 0 else 6
            right = 6 if index < len(quick_specs)-1 else 0
            card.pack(side="left", fill="both", expand=True, padx=(left, right))
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, text=description, style="Muted.TLabel", wraplength=220).pack(anchor="w", pady=(4, 8))
            RoundedGlowButton(card, text="Abrir  →", style="Secondary.TButton", command=action).pack(anchor="e")

        self.media_preview_placeholder = self._make_thumbnail_placeholder(220, 124)
        self.playlist_thumbnail_placeholder = self._make_thumbnail_placeholder(76, 43)
        self.media_preview_card = RoundedCard(frame, self, padding=12, surface="panel")
        preview_header = ttk.Frame(self.media_preview_card, style="Card.TFrame")
        preview_header.pack(fill="x", pady=(0, 8))
        ttk.Label(preview_header, text="PRÉVIA AUTOMÁTICA", style="PreviewEyebrow.TLabel").pack(side="left")
        ttk.Label(
            preview_header, textvariable=self.media_preview_status_var,
            style="Muted.TLabel", anchor="e",
        ).pack(side="left", fill="x", expand=True, padx=(10, 8))
        RoundedGlowButton(
            preview_header, text="Atualizar prévia", style="Secondary.TButton",
            command=self._refresh_media_preview,
        ).pack(side="right")
        preview_body = ttk.Frame(self.media_preview_card, style="Card.TFrame")
        preview_body.pack(fill="x")
        self.media_preview_poster = tk.Label(
            preview_body, image=self.media_preview_placeholder,
            bg=self.colors["panel2"], bd=0, highlightthickness=0,
            width=220, height=124, anchor="center",
        )
        self.media_preview_poster.pack(side="left", padx=(0, 14))
        preview_details = ttk.Frame(preview_body, style="Card.TFrame")
        preview_details.pack(side="left", fill="both", expand=True, anchor="n")
        ttk.Label(
            preview_details, textvariable=self.media_preview_title_var,
            style="CardTitle.TLabel", wraplength=650, justify="left",
        ).pack(anchor="w", pady=(4, 5))
        ttk.Label(
            preview_details, textvariable=self.media_preview_meta_var,
            style="Muted.TLabel", wraplength=650, justify="left",
        ).pack(anchor="w")
        ttk.Label(
            preview_details,
            text="A prévia consulta metadados e a capa; não baixa o arquivo de mídia.",
            style="Muted.TLabel", wraplength=650, justify="left",
        ).pack(anchor="w", pady=(12, 0))
        self.media_preview_card.pack_forget()
        self.progress_card = self._card(frame,16)
        self.progress_card.pack(fill="x",pady=(0,13))
        progress_card = self.progress_card
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
        RoundedGlowButton(top_log,text="Limpar",style="Secondary.TButton",command=self._clear_log).pack(side="right")
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
        self.cancel_btn=RoundedGlowButton(footer,text="Cancelar download",style="Secondary.TButton",command=self.cancel_download,state="disabled")
        self.cancel_btn.pack(side="right")
    def _draw_brand_logo(self):
        if not hasattr(self, "brand_logo_canvas"):
            return
        canvas = self.brand_logo_canvas
        try:
            canvas.delete("all")
            width = max(54, canvas.winfo_width(), canvas.winfo_reqwidth())
            height = max(54, canvas.winfo_height(), canvas.winfo_reqheight())
            cx, cy = width / 2, height / 2
            scale = min(width, height) / 62.0
            colors = [
                self.colors.get("accent", "#8B5CF6"),
                self.colors.get("space", "#22D3EE"),
                self.colors.get("pink", "#C026D3"),
            ]
            for orbit_index, rotation in enumerate((0, math.pi / 3, -math.pi / 3)):
                points = []
                for step in range(49):
                    angle = 2 * math.pi * step / 48
                    x = 22 * scale * math.cos(angle)
                    y = 11.5 * scale * math.sin(angle)
                    px = cx + x * math.cos(rotation) - y * math.sin(rotation)
                    py = cy + x * math.sin(rotation) + y * math.cos(rotation)
                    points.extend((px, py))
                canvas.create_line(*points, fill=colors[orbit_index], width=max(1.2, 2.2*scale),
                                   smooth=True, splinesteps=24, capstyle=tk.ROUND, joinstyle=tk.ROUND)
            nucleus = 5 * scale
            canvas.create_oval(cx-nucleus, cy-nucleus, cx+nucleus, cy+nucleus,
                               fill=self.colors.get("accent", "#8B5CF6"),
                               outline=self.colors.get("pink", "#C026D3"), width=max(1, 1.4*scale))
            core = max(1, 1.6*scale)
            canvas.create_oval(cx-core, cy-core, cx+core, cy+core, fill="#FFFFFF", outline="")
        except tk.TclError:
            pass

    def _make_thumbnail_placeholder(self, width: int, height: int):
        """Create a local gradient/play placeholder without any network request."""
        image = tk.PhotoImage(master=self.root, width=width, height=height)
        base = self.colors.get("panel2", "#18182F")
        accent = self.colors.get("accent", "#8B5CF6")
        cyan = self.colors.get("space", "#22D3EE")
        step = max(1, width // 18)
        for x in range(0, width, step):
            amount = x / max(1, width - 1)
            blended = _blend_hex(base, accent, 0.20 + amount * 0.42)
            blended = _blend_hex(blended, cyan, amount * 0.14)
            image.put(blended, to=(x, 0, min(width, x + step), height))
        center_x, center_y = width // 2, height // 2
        radius = max(4, min(width, height) // 4)
        for dy in range(-radius, radius + 1):
            spread = int((radius - abs(dy)) * 0.85)
            left = center_x - max(1, spread // 2)
            right = min(width, center_x + spread + 1)
            image.put("#F8F7FF", to=(left, center_y + dy, right, center_y + dy + 1))
        image.put(accent, to=(0, height - 2, width, height))
        image.put(cyan, to=(0, height - 1, width, height))
        return image

    def _thumbnail_photo_from_bytes(self, data: bytes, width: int, height: int):
        if not data:
            return None
        if Image is not None and ImageTk is not None:
            try:
                with Image.open(io.BytesIO(data)) as source:
                    if source.width < 1 or source.height < 1 or source.width * source.height > 25_000_000:
                        return None
                    rendered = source.convert("RGB")
                resampling = getattr(Image, "Resampling", Image).LANCZOS
                rendered.thumbnail((width, height), resampling)
                background = Image.new(
                    "RGB", (width, height),
                    self.colors.get("panel2", "#18182F"),
                )
                background.paste(
                    rendered,
                    ((width - rendered.width) // 2, (height - rendered.height) // 2),
                )
                return ImageTk.PhotoImage(background, master=self.root)
            except Exception as exc:
                self.logger.debug("Não foi possível renderizar a thumbnail: %s", type(exc).__name__)
                return None
        try:
            # Tk decodes a subset of formats when Pillow is absent (typically PNG/GIF).
            photo = tk.PhotoImage(master=self.root, data=data)
            if photo.width() > width * 3 or photo.height() > height * 3:
                return photo.subsample(
                    max(1, (photo.width() + width - 1) // width),
                    max(1, (photo.height() + height - 1) // height),
                )
            return photo
        except tk.TclError:
            return None

    def _show_media_preview_card(self):
        if not self._media_preview_visible:
            self.media_preview_card.pack(fill="x", before=self.progress_card, pady=(0, 13))
            self._media_preview_visible = True

    def _hide_media_preview_card(self):
        if self._media_preview_visible:
            self.media_preview_card.pack_forget()
            self._media_preview_visible = False

    def _schedule_media_preview(self, *_args):
        self._media_preview_generation += 1
        generation = self._media_preview_generation
        pending = self._media_preview_after
        if pending is not None:
            try:
                self.root.after_cancel(pending)
            except tk.TclError:
                pass
            self._media_preview_after = None
        url = self.url_var.get().strip()
        valid, _message = validate_url(url)
        if not url or not valid or self._looks_like_playlist(url):
            self._hide_media_preview_card()
            return
        self._show_media_preview_card()
        self.media_preview_title_var.set("Procurando a prévia…")
        self.media_preview_meta_var.set("Lendo título, canal, duração e capa — sem baixar o vídeo/áudio.")
        self.media_preview_status_var.set("Consultando metadados")
        self.media_preview_photo = None
        self.media_preview_poster.configure(image=self.media_preview_placeholder)
        self._media_preview_after = self.root.after(
            950, lambda u=url, g=generation: self._start_media_preview(u, g, 0)
        )

    def _refresh_media_preview(self):
        self._schedule_media_preview()

    def _start_media_preview(self, url: str, generation: int, attempt: int = 0):
        self._media_preview_after = None
        if generation != self._media_preview_generation or url != self.url_var.get().strip():
            return
        valid, _message = validate_url(url)
        if not valid or self._looks_like_playlist(url):
            self._hide_media_preview_card()
            return
        self._show_media_preview_card()
        refresh_thread = getattr(self, "_dependency_refresh_thread", None)
        if not self._dependencies_checked or (refresh_thread and refresh_thread.is_alive()):
            if attempt < 10:
                self.media_preview_status_var.set("Aguardando a verificação das dependências…")
                self._media_preview_after = self.root.after(
                    500, lambda u=url, g=generation, a=attempt+1: self._start_media_preview(u, g, a)
                )
                return
            self.media_preview_status_var.set("A verificação de yt-dlp demorou demais")
            self.media_preview_meta_var.set("Abra Dependências e confira se a ferramenta de mídia está pronta.")
            return
        tool = self.dep_infos.get("yt-dlp")
        if not tool or not tool.path or not tool.executable_ok:
            self.media_preview_status_var.set("Prévia indisponível")
            self.media_preview_meta_var.set("A prévia automática precisa do yt-dlp. Abra Dependências para instalar/reparar.")
            return
        self.media_preview_status_var.set("Carregando metadados e capa…")
        threading.Thread(
            target=self._media_preview_worker,
            args=(generation, url, str(tool.path)),
            name="cgmd-media-preview",
            daemon=True,
        ).start()

    def _media_preview_worker(self, generation: int, url: str, yt_dlp_path: str):
        try:
            preview = inspect_media_preview(yt_dlp_path, url)
            self.ui_queue.put(("media_preview_done", (generation, url, preview, None)))
        except Exception as exc:
            self.ui_queue.put(("media_preview_done", (generation, url, None, str(exc))))

    def _playlist_photo_for_item(self, item: dict):
        url = str(item.get("thumbnail_url") or "")
        if not url:
            return self.playlist_thumbnail_placeholder
        cached = self._playlist_thumbnail_cache.get(url)
        if cached is not None:
            return cached
        if url not in self._playlist_thumbnail_requested and len(self._playlist_thumbnail_requested) < 80:
            self._playlist_thumbnail_requested.add(url)
            try:
                self._thumbnail_executor.submit(self._playlist_thumbnail_worker, url)
            except RuntimeError:
                self._playlist_thumbnail_requested.discard(url)
        return self.playlist_thumbnail_placeholder

    def _playlist_thumbnail_worker(self, url: str):
        try:
            data = fetch_thumbnail_bytes(url, timeout=5.5)
        except Exception:
            data = None
        self.ui_queue.put(("playlist_thumbnail_done", (url, data)))

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
        RoundedGlowButton(toolbar, text="Marcar visíveis", style="Secondary.TButton", command=lambda: self._set_visible_playlist_included(True)).pack(side="left", padx=2)
        RoundedGlowButton(toolbar, text="Desmarcar visíveis", style="Secondary.TButton", command=lambda: self._set_visible_playlist_included(False)).pack(side="left", padx=2)
        RoundedGlowButton(toolbar, text="Inverter", style="Secondary.TButton", command=self._invert_visible_playlist_items).pack(side="left", padx=2)
        RoundedGlowButton(toolbar, text="Analisar novamente", style="Secondary.TButton", command=self._reanalyze_playlist).pack(side="right")

        table_card = self._card(frame, 8)
        table_card.pack(fill="both", expand=True, pady=(0, 10))
        table_wrap = ttk.Frame(table_card, style="Card.TFrame")
        table_wrap.pack(fill="both", expand=True)
        columns = ("include", "index", "title", "duration", "mode", "quality", "status")
        self.playlist_tree = ttk.Treeview(table_wrap, columns=columns, show="tree headings", height=12, selectmode="extended")
        self.playlist_tree.heading("#0", text="Prévia")
        self.playlist_tree.column("#0", width=90, minwidth=90, anchor="center", stretch=False)
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
        RoundedGlowButton(controls, text="Aplicar aos selecionados", style="Secondary.TButton", command=self._apply_playlist_item_settings).pack(side="right")

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
        RoundedGlowButton(bottom, text="BAIXAR ITENS MARCADOS", style="Accent.TButton", command=self._start_selected_playlist_download).pack(side="right")
        self._render_playlist_rows()

    # ---------- Settings ----------
    def _setting_row(self, parent, key: str, label: str, description: str, browse: str | None = None, choices: list[str] | None = None):
        card = self._card(parent, 12)
        card.pack(fill="x", pady=5)
        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=label, style="CardTitle.TLabel").pack(side="left")
        q = RoundedGlowButton(head, text="?", style="Help.TButton")
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
            RoundedGlowButton(actions, text="Selecionar pasta" if browse == "dir" else "Selecionar arquivo", style="Secondary.TButton", command=choose).pack(side="left")
        RoundedGlowButton(actions, text="↺ Padrão", style="Secondary.TButton", command=lambda k=key: self.reset_setting(k, "default")).pack(side="right", padx=(7, 0))
        RoundedGlowButton(actions, text="⏮ Inicial", style="Secondary.TButton", command=lambda k=key: self.reset_setting(k, "baseline")).pack(side="right")

    def _build_settings(self):
        frame=ttk.Frame(self.pages_area)
        self.page_frames["settings"]=frame
        scroll=ScrollableFrame(frame)
        scroll.pack(fill="both",expand=True)
        body=scroll.body
        ttk.Label(body,text="Personalize cores, efeitos gerados e comportamento do downloader.",style="Subtitle.TLabel").pack(anchor="w",pady=(0,12))

        effects = self._card(body, 15)
        effects.pack(fill="x", pady=(0, 12))
        ttk.Label(effects, text="Efeitos visuais estáticos", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            effects,
            text="A prévia é gerada localmente pelo mecanismo visual do aplicativo. Nesta versão, o gradiente fica estático; os controles abaixo ajustam as cores e a arte do átomo.",
            style="Card.TLabel", wraplength=780, justify="left",
        ).pack(anchor="w", pady=(4, 12))
        self.visual_effects_var = tk.BooleanVar(value=bool(self.config.get("visual_effects_enabled", True)))
        self.visual_palette_var = tk.StringVar(value=self._display_setting_value("visual_palette", self.config.get("visual_palette", "cosmic")))
        self.visual_strength_var = tk.StringVar(value=self._display_setting_value("visual_strength", self.config.get("visual_strength", 0.55)))
        self.visual_orbits_var = tk.StringVar(value=str(self.config.get("visual_orbits", 3)))
        ttk.Checkbutton(
            effects, text="Usar gradiente ambiente e brilho do átomo",
            variable=self.visual_effects_var, command=self._preview_visual_effect_settings,
        ).pack(anchor="w", pady=(0, 10))
        effect_controls = ttk.Frame(effects, style="Card.TFrame")
        effect_controls.pack(fill="x", pady=(0, 10))
        for title, variable, values in (
            ("PALETA DE CORES", self.visual_palette_var, ["Cósmica · roxo/azul", "Nebulosa violeta", "Aurora", "Oceano"]),
            ("INTENSIDADE", self.visual_strength_var, ["Suave", "Equilibrado", "Vibrante"]),
            ("ÓRBITAS DO ÁTOMO", self.visual_orbits_var, ["2", "3", "4"]),
        ):
            group = ttk.Frame(effect_controls, style="Card.TFrame")
            group.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ttk.Label(group, text=title, style="Muted.TLabel", font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
            ttk.Combobox(group, textvariable=variable, values=values, state="readonly").pack(fill="x")
        ttk.Label(effects, text="PRÉVIA DO GRADIENTE", style="Muted.TLabel", font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 5))
        self.visual_preview_canvas = tk.Canvas(effects, height=86, background=self.colors["panel2"], borderwidth=0, highlightthickness=1, highlightbackground=self.colors["border"])
        self.visual_preview_canvas.pack(fill="x", pady=(0, 9))
        self.visual_palette_var.trace_add("write", lambda *_: self._preview_visual_effect_settings())
        self.visual_strength_var.trace_add("write", lambda *_: self._preview_visual_effect_settings())
        self.visual_orbits_var.trace_add("write", lambda *_: self._preview_visual_effect_settings())
        self.visual_preview_canvas.bind("<Configure>", lambda _event: self._render_static_visuals(), add="+")
        self._preview_visual_effect_settings()
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
        RoundedGlowButton(accent_row,text="Escolher cor…",style="Secondary.TButton",command=self._choose_accent_color).pack(side="left",padx=(10,0),anchor="s")
        RoundedGlowButton(accent_row,text="↺ Padrão",style="Secondary.TButton",command=lambda:self.reset_setting("accent_color","default")).pack(side="left",padx=(7,0),anchor="s")
        presets=ttk.Frame(appearance,style="Card.TFrame")
        presets.pack(fill="x",pady=(10,0))
        ttk.Label(presets,text="PALETAS RÁPIDAS",style="Muted.TLabel",font=("Segoe UI",8,"bold")).pack(side="left",padx=(0,10))
        for name,color in (("Azul","#2563EB"),("Marinho","#1D4ED8"),("Ciano","#0891B2"),("Verde","#15803D"),("Ardósia","#64748B"),("Âmbar","#B45309")):
            RoundedGlowButton(presets,text=name,style="Secondary.TButton",command=lambda c=color:self.settings_vars["accent_color"].set(c)).pack(side="left",padx=(0,5))
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
        RoundedGlowButton(actions,text="Salvar personalização",style="Accent.TButton",command=self.save_settings).pack(side="right")
        RoundedGlowButton(actions,text="Reverter tudo para padrão",style="Secondary.TButton",command=lambda:self.reset_all("default")).pack(side="left")
        RoundedGlowButton(actions,text="Reverter para instalação inicial",style="Secondary.TButton",command=lambda:self.reset_all("baseline")).pack(side="left",padx=(8,0))
        note=self._card(body,12)
        note.pack(fill="x",pady=(0,20))
        ttk.Label(note,text="Como as personalizações são salvas",style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(note,text="Tema, cor principal e espaçamento são aplicados como prévia. Clique em Salvar personalização para gravar tudo. Preferências, pastas e histórico ficam no perfil do usuário.",style="Card.TLabel",wraplength=780,justify="left").pack(anchor="w",pady=(5,0))
    def _preview_visual_effect_settings(self):
        """Apply generator options live; saving to disk is reserved for Save."""
        try:
            palette = self._stored_setting_value("visual_palette", self.visual_palette_var.get())
            strength = self._stored_setting_value("visual_strength", self.visual_strength_var.get())
            orbits = int(self.visual_orbits_var.get())
            self.config["visual_effects_enabled"] = bool(self.visual_effects_var.get())
            self.config["visual_palette"] = palette if palette in EFFECT_PALETTES else "cosmic"
            self.config["visual_strength"] = strength if strength in {0.30, 0.55, 0.80} else 0.55
            self.config["visual_orbits"] = orbits if orbits in {2, 3, 4} else 3
            self._render_static_visuals()
        except (AttributeError, tk.TclError, ValueError, TypeError):
            # Controls are incomplete while the settings form is being constructed.
            return

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
        if hasattr(self, "visual_effects_var"):
            self.visual_effects_var.set(bool(source_config.get("visual_effects_enabled", True)))
            self.visual_palette_var.set(self._display_setting_value("visual_palette", source_config.get("visual_palette", "cosmic")))
            self.visual_strength_var.set(self._display_setting_value("visual_strength", source_config.get("visual_strength", 0.55)))
            self.visual_orbits_var.set(str(source_config.get("visual_orbits", 3)))
            self._preview_visual_effect_settings()
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
        if key=="visual_palette":
            return {"cosmic":"Cósmica · roxo/azul","nebula":"Nebulosa violeta","aurora":"Aurora","ocean":"Oceano"}.get(str(value),"Cósmica · roxo/azul")
        if key=="visual_strength":
            try:
                return {0.30:"Suave",0.55:"Equilibrado",0.80:"Vibrante"}.get(round(float(value), 2),"Equilibrado")
            except (TypeError, ValueError):
                return "Equilibrado"
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
        if key=="visual_palette":
            return {"Cósmica · roxo/azul":"cosmic","Nebulosa violeta":"nebula","Aurora":"aurora","Oceano":"ocean"}.get(str(value),str(value))
        if key=="visual_strength":
            return {"Suave":0.30,"Equilibrado":0.55,"Vibrante":0.80}.get(str(value),0.55)
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
        new_config["visual_effects_enabled"]=bool(self.visual_effects_var.get())
        new_config["visual_palette"]=self._stored_setting_value("visual_palette", self.visual_palette_var.get())
        new_config["visual_strength"]=self._stored_setting_value("visual_strength", self.visual_strength_var.get())
        new_config["visual_orbits"]=int(self.visual_orbits_var.get())
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
        self.install_btn = RoundedGlowButton(actions, text="Instalar/Reparar automaticamente", style="Accent.TButton", command=self.install_dependencies_async)
        self.install_btn.pack(side="left")
        RoundedGlowButton(actions, text="Atualizar informações", style="Secondary.TButton", command=lambda: self._refresh_dependencies(force=True)).pack(side="left", padx=(8, 0))
        RoundedGlowButton(actions, text="Abrir Configurações", style="Secondary.TButton", command=lambda: self.show_page("settings")).pack(side="right")

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
        self.app_update_check_button = RoundedGlowButton(
            buttons, text="Verificar atualizações", style="Accent.TButton",
            command=lambda: self._start_app_update_check(user_initiated=True),
        )
        self.app_update_check_button.pack(side="left")
        self.app_update_install_button = RoundedGlowButton(
            buttons, text="Baixar e instalar", style="Secondary.TButton",
            state="disabled", command=self._show_cached_update_prompt,
        )
        self.app_update_install_button.pack(side="left", padx=(8, 0))
        self.app_uninstall_button = RoundedGlowButton(
            buttons, text="Desinstalar aplicativo", style="Secondary.TButton",
            command=self._start_uninstall,
        )
        self.app_uninstall_button.pack(side="left", padx=(8, 0))
        self.app_update_repair_button = RoundedGlowButton(
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

        RoundedGlowButton(actions, text="Atualizar agora", style="Accent.TButton", command=start_update).pack(side="left")
        RoundedGlowButton(actions, text="Continuar nesta versão", style="Secondary.TButton", command=later).pack(side="right")
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
            ("Temas", "Claro, escuro ou Sistema. A interface usa tons profissionais de azul e cinza, contraste consistente e animações discretas que podem ser desativadas nas Configurações; Sistema consulta a preferência visual do Windows, macOS ou, quando disponível, do ambiente Linux."),
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
        security_card = self._card(body, 13)
        security_card.pack(fill="x", pady=(0, 12))
        ttk.Label(security_card, text="Distribuição e segurança do Windows", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            security_card,
            text=(
                "Esta é uma versão beta. Os metadados do arquivo e o ícone identificam o produto, "
                "mas não substituem uma assinatura digital Authenticode confiável. Baixe apenas "
                "pela página oficial de Releases, confira SHA256SUMS.txt e leia o relatório "
                "VirusTotal-Status.txt antes de executar. O Windows pode exibir avisos de editor "
                "desconhecido/SmartScreen ou bloquear o arquivo conforme a política de segurança."
            ),
            style="Card.TLabel", wraplength=760, justify="left",
        ).pack(anchor="w", pady=(4, 0))
        RoundedGlowButton(body, text="Desinstalar", style="Danger.TButton", command=self._uninstall).pack(anchor="e", pady=(0, 25))
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
        self.root.after(100, self.close)

    def close(self):
        """Cancel transient work before closing the real application window."""
        self._media_preview_generation = getattr(self, "_media_preview_generation", 0) + 1
        for name in ("_media_preview_after", "_hero_animation_job", "_page_animation_job"):
            job = getattr(self, name, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, name, None)

        # A close action should not leave active media subprocesses running.
        try:
            self.cancel_requested.set()
            with self.active_downloaders_lock:
                active_downloaders = list(self.active_downloaders.values())
            current_downloader = getattr(self, "downloader", None)
            if current_downloader is not None and current_downloader not in active_downloaders:
                active_downloaders.append(current_downloader)
            for downloader in active_downloaders:
                try:
                    downloader.cancel()
                except Exception:
                    logger = getattr(self, "logger", None)
                    if logger is not None:
                        logger.debug("Não foi possível cancelar um downloader ao fechar.", exc_info=True)
        except (AttributeError, RuntimeError):
            pass

        executor = getattr(self, "_thumbnail_executor", None)
        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except (RuntimeError, TypeError):
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _render_static_visuals(self):
        """Render settings-driven local artwork without animating gradients."""
        canvas = getattr(self, "hero_visual", None)
        try:
            if canvas is not None and canvas.winfo_exists():
                width = max(canvas.winfo_width(), canvas.winfo_reqwidth(), 150)
                height = max(canvas.winfo_height(), canvas.winfo_reqheight(), 100)
                enabled = bool(self.config.get("visual_effects_enabled", True))
                palette = str(self.config.get("visual_palette", "cosmic"))
                strength = float(self.config.get("visual_strength", 0.55)) if enabled else 0.0
                orbits = int(self.config.get("visual_orbits", 3))
                artwork = render_atom_art(width, height, palette=palette, strength=strength, orbit_count=orbits, background=enabled)
                canvas.delete("all")
                if artwork is not None and ImageTk is not None:
                    photo = ImageTk.PhotoImage(artwork, master=self.root)
                    self.hero_visual_photo = photo
                    canvas.create_image(width/2, height/2, image=photo)
                else:
                    canvas.configure(background=self.colors.get("panel2", "#090814"))
                    cx, cy = width/2, height/2
                    chosen = palette_colors(palette)
                    for index in range(orbits):
                        canvas.create_oval(cx-width*0.31, cy-height*0.20, cx+width*0.31, cy+height*0.20,
                                           outline=chosen[index % len(chosen)], width=2)
                    canvas.create_oval(cx-7, cy-7, cx+7, cy+7, fill=chosen[0], outline="#F4F2FF", width=2)
            preview = getattr(self, "visual_preview_canvas", None)
            if preview is not None and preview.winfo_exists():
                width = max(420, preview.winfo_width(), preview.winfo_reqwidth())
                height = max(72, preview.winfo_height(), 86)
                enabled = bool(self.config.get("visual_effects_enabled", True))
                palette = str(self.config.get("visual_palette", "cosmic"))
                strength = float(self.config.get("visual_strength", 0.55)) if enabled else 0.0
                image = render_gradient_preview(width, height, palette, strength)
                preview.delete("all")
                if image is not None and ImageTk is not None:
                    photo = ImageTk.PhotoImage(image, master=self.root)
                    self.visual_preview_photo = photo
                    preview.create_image(0, 0, image=photo, anchor="nw")
                else:
                    chosen = palette_colors(palette)
                    for x in range(width):
                        color = chosen[min(len(chosen)-1, int(x*len(chosen)/max(1, width)))] if enabled else "#090814"
                        preview.create_line(x, 0, x, height, fill=color)
            for button in getattr(self, "nav_buttons", {}).values():
                if hasattr(button, "refresh_theme"):
                    button.refresh_theme()
            def refresh_buttons(parent):
                for child in parent.winfo_children():
                    if isinstance(child, RoundedGlowButton):
                        child.refresh_theme()
                    if child.winfo_children():
                        refresh_buttons(child)
            if getattr(self, "root", None) is not None:
                refresh_buttons(self.root)
        except (tk.TclError, ValueError, TypeError) as exc:
            try:
                self.logger.debug("Falha ao atualizar efeitos estáticos: %s", type(exc).__name__)
            except Exception:
                pass

    def _animate_hero_visual(self):
        """Compatibility hook: render the atom artwork once; gradients do not animate."""
        self._render_static_visuals()
        self._hero_animation_job = None

    def _select_download_mode(self, mode: str):
        """Select a real download mode from one of the home quick-action cards."""
        if mode not in {"Vídeo", "Música — MP3"}:
            return
        self.mode_var.set(mode)
        self._sync_quality()
        try:
            self.url_entry.focus_set()
        except tk.TclError:
            pass

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
        if hasattr(self, "visual_effects_var"):
            self.visual_effects_var.set(bool(self.config.get("visual_effects_enabled", True)))
            self.visual_palette_var.set(self._display_setting_value("visual_palette", self.config.get("visual_palette", "cosmic")))
            self.visual_strength_var.set(self._display_setting_value("visual_strength", self.config.get("visual_strength", 0.55)))
            self.visual_orbits_var.set(str(self.config.get("visual_orbits", 3)))
            self._preview_visual_effect_settings()
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
                elif kind == "media_preview_done":
                    generation, url, preview, error = data
                    if generation != self._media_preview_generation or url != self.url_var.get().strip():
                        continue
                    if error or preview is None:
                        self.media_preview_title_var.set("Não foi possível carregar esta prévia")
                        self.media_preview_meta_var.set(str(error or "O site não disponibilizou metadados.")[:220])
                        self.media_preview_status_var.set("Prévia indisponível")
                        self.media_preview_photo = None
                        self.media_preview_poster.configure(image=self.media_preview_placeholder)
                    else:
                        self.media_preview_title_var.set(preview.title or "Mídia sem título")
                        details = [preview.creator or "Canal não informado"]
                        if preview.duration is not None:
                            details.append(format_duration(preview.duration))
                        self.media_preview_meta_var.set("  •  ".join(details))
                        photo = self._thumbnail_photo_from_bytes(preview.thumbnail_bytes, 220, 124) if preview.thumbnail_bytes else None
                        self.media_preview_photo = photo
                        self.media_preview_poster.configure(image=photo or self.media_preview_placeholder)
                        self.media_preview_status_var.set(
                            "Capa carregada" if photo else "Metadados carregados · capa indisponível"
                        )
                elif kind == "playlist_thumbnail_done":
                    url, data = data
                    photo = self._thumbnail_photo_from_bytes(data, 76, 43) if data else None
                    if photo is not None:
                        self._playlist_thumbnail_cache[url] = photo
                        self._playlist_thumbnail_loaded.add(url)
                    else:
                        self._playlist_thumbnail_cache[url] = self.playlist_thumbnail_placeholder
                        self._playlist_thumbnail_failed.add(url)
                    self._render_playlist_rows()
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
                "video_id": entry.video_id, "duration": entry.duration,
                "thumbnail_url": getattr(entry, "thumbnail_url", ""),
                "available": entry.available,
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
            thumbnail = self._playlist_photo_for_item(item)
            self.playlist_tree.insert(
                "", "end", iid=iid, image=thumbnail,
                values=(included, item["index"], item["title"], format_duration(item.get("duration")), mode, quality, status),
            )
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
        root.protocol("WM_DELETE_WINDOW", app.close)
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
