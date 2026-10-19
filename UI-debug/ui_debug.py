from __future__ import annotations

"""Standalone visual prototype for ChatGPT Media Downloader.

UI-debug intentionally has no dependency on the production app package.
Downloads, playlist processing, dependency installation and repair are mocked.
Only theme/preferences persistence and this prototype's own update checker work.
"""

import json
import math
import os
import random
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
import tkinter.font as tkfont


APP_NAME = "ChatGPT Media Downloader — UI-debug"
APP_VERSION = "0.1.0-dev.4"
CHANNEL = "development"
REPO_OWNER = "slydtaz"
REPO_NAME = "Chatgpt-media-downloader"
UPDATE_BRANCH = "ui-debug"
VERSION_URL = (
    "https://raw.githubusercontent.com/"
    + REPO_OWNER + "/" + REPO_NAME + "/" + UPDATE_BRANCH + "/UI-debug/version.json"
)
ARCHIVE_URL = (
    "https://github.com/" + REPO_OWNER + "/" + REPO_NAME
    + "/archive/refs/heads/" + UPDATE_BRANCH + ".zip"
)
TRUSTED_UPDATE_HOSTS = frozenset({
    "raw.githubusercontent.com", "github.com", "codeload.github.com",
    "objects.githubusercontent.com", "release-assets.githubusercontent.com",
})
MAX_VERSION_BYTES = 64 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_UNPACKED_BYTES = 12 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 250
UPDATE_FILES = frozenset({
    "ui_debug.py", "version.json", "README.md", "run_ui_debug.bat", "run_ui_debug.sh",
})

DEFAULT_SETTINGS = {
    "theme": "dark",
    "accent_color": "#7C5CFF",
    "accent_color_2": "#20D8E7",
    "ui_density": "comfortable",
    "animations_enabled": True,
    "reduce_motion": False,
    "update_check_on_startup": True,
}

PALETTES = {
    "dark": {
        "bg": "#090D1B", "panel": "#11182D", "panel2": "#151F39",
        "surface": "#192540", "field": "#0D1427", "fg": "#F3F6FF",
        "muted": "#9BA9C8", "border": "#2A385A", "accent": "#7C5CFF",
        "accent2": "#20D8E7", "good": "#51D6A5", "warn": "#F6C66A",
        "bad": "#FF7C97", "button": "#1B2947", "input_fg": "#F3F6FF",
    },
    "light": {
        "bg": "#F2F5FF", "panel": "#FFFFFF", "panel2": "#E7EDFF",
        "surface": "#F8FAFF", "field": "#FFFFFF", "fg": "#1B2442",
        "muted": "#647293", "border": "#D6DDF1", "accent": "#6449E9",
        "accent2": "#009EBD", "good": "#187F67", "warn": "#9A6500",
        "bad": "#B93658", "button": "#E7EBF8", "input_fg": "#1B2442",
    },
    "oled": {
        "bg": "#03050B", "panel": "#080D18", "panel2": "#0D1628",
        "surface": "#101B2F", "field": "#050912", "fg": "#F7FAFF",
        "muted": "#8999BA", "border": "#1C2A45", "accent": "#946EFF",
        "accent2": "#36E2F0", "good": "#51D6A5", "warn": "#FFD166",
        "bad": "#FF7294", "button": "#0E192C", "input_fg": "#F7FAFF",
    },
}


def blend_hex(first: str, second: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    a = tuple(int(first[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(second[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join("%02X" % round(x + (y - x) * amount) for x, y in zip(a, b))


def background_key_for(widget, app, default="bg") -> str:
    """Map a container's current background to the matching theme role."""
    try:
        actual = str(widget.cget("bg")).lower()
    except (tk.TclError, TypeError, AttributeError):
        return default
    for key in ("bg", "panel", "panel2", "surface", "field", "button", "muted", "border", "accent", "accent2"):
        if str(app.colors.get(key, "")).lower() == actual:
            return key
    return default


def rounded_points(x1: float, y1: float, x2: float, y2: float, radius: float, steps: int = 14) -> list[float]:
    """Approximate a rounded rectangle with evenly sampled quarter circles."""
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    r = max(2.0, min(radius, width / 2.0, height / 2.0))
    points: list[tuple[float, float]] = []
    corners = (
        (x2 - r, y1 + r, -90, 0),
        (x2 - r, y2 - r, 0, 90),
        (x1 + r, y2 - r, 90, 180),
        (x1 + r, y1 + r, 180, 270),
    )
    for cx, cy, start, end in corners:
        for index in range(steps + 1):
            angle = (start + (end - start) * index / steps) * 3.141592653589793 / 180
            points.append((cx + r * __import__("math").cos(angle), cy + r * __import__("math").sin(angle)))
    return [value for point in points for value in point]


def ellipse_point(cx: float, cy: float, rx: float, ry: float, angle: float, rotation: float = 0.0) -> tuple[float, float]:
    """Return a point on a rotated ellipse."""
    x, y = rx * math.cos(angle), ry * math.sin(angle)
    cosine, sine = math.cos(rotation), math.sin(rotation)
    return cx + x * cosine - y * sine, cy + x * sine + y * cosine


def ellipse_line_points(cx: float, cy: float, rx: float, ry: float, rotation: float, steps: int = 48) -> list[float]:
    points: list[float] = []
    for step in range(steps + 1):
        points.extend(ellipse_point(cx, cy, rx, ry, 2 * math.pi * step / steps, rotation))
    return points


def draw_orbit_icon(canvas: tk.Canvas, cx: float, cy: float, tint: str, variant: int = 0) -> str:
    """Minimal orbit mark used in tabs without an external asset."""
    tag = "orbit-icon"
    rotations = (0.0, math.pi / 3, -math.pi / 3)
    for idx, rotation in enumerate(rotations):
        points = ellipse_line_points(cx, cy, 7.2 if idx else 8.0, 3.6 if idx else 3.1,
                                     rotation + variant * 0.11, steps=28)
        canvas.create_line(*points, fill=tint, width=1.45, smooth=True, splinesteps=10,
                           tags=(tag, "orbit-track"))
    canvas.create_oval(cx - 2.1, cy - 2.1, cx + 2.1, cy + 2.1,
                       fill=tint, outline="", tags=(tag, "orbit-core"))
    angle = 0.6 + variant * 0.7
    px, py = ellipse_point(cx, cy, 7.1, 3.6, angle, rotations[variant % len(rotations)])
    canvas.create_oval(px - 1.5, py - 1.5, px + 1.5, py + 1.5,
                       fill=tint, outline="", tags=(tag, "orbit-node"))
    return tag


def rounded_span(y: int, width: int, height: int, radius: int) -> tuple[int, int]:
    """Horizontal span inside a rounded rectangle at vertical coordinate y."""
    r = max(1, min(radius, width // 2, height // 2))
    center_y = height / 2
    depth = abs(y - center_y) - (height / 2 - r)
    inset = r - (max(0.0, r * r - depth * depth) ** 0.5) if depth > 0 else 0
    return max(0, int(inset)), min(width, int(width - inset))


def version_key(value: str) -> tuple:
    """Compare simple semantic versions, including increasing -dev.N suffixes."""
    match = re.fullmatch(r"\s*v?(\d+(?:\.\d+){0,4})(?:[-.]([0-9A-Za-z.-]+))?\s*", str(value or ""))
    if not match:
        return (0, 0, 0, 0, 0)
    numbers = [int(part) for part in match.group(1).split(".")]
    numbers += [0] * (5 - len(numbers))
    suffix = (match.group(2) or "").lower()
    if not suffix:
        return (*numbers, 1, 0)
    dev_match = re.search(r"dev[.-]?(\d+)", suffix)
    return (*numbers, 0, int(dev_match.group(1)) if dev_match else 0)


def validate_update_url(url: str) -> bool:
    try:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        return (
            parts.scheme.lower() == "https"
            and (parts.hostname or "").lower() in TRUSTED_UPDATE_HOSTS
            and parts.username is None
            and parts.password is None
            and parts.port in (None, 443)
        )
    except (TypeError, ValueError):
        return False


class RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not validate_update_url(newurl):
            raise urllib.error.HTTPError(
                req.full_url, code, "Redirect destination is not allowed", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_update_bytes(url: str, maximum: int) -> bytes:
    """HTTPS-only updater transport with host allowlisting, redirect checks and size caps."""
    if not validate_update_url(url):
        raise RuntimeError("Endereço do atualizador fora da lista permitida.")
    request = urllib.request.Request(
        url, headers={"User-Agent": "ChatGPT-Media-Downloader-UI-debug/" + APP_VERSION}
    )
    opener = urllib.request.build_opener(RestrictedRedirectHandler())
    with opener.open(request, timeout=12) as response:
        if not validate_update_url(response.geturl()):
            raise RuntimeError("O servidor redirecionou para um endereço não autorizado.")
        declared = int(response.headers.get("Content-Length", "0") or 0)
        if declared < 0 or declared > maximum:
            raise RuntimeError("O pacote de atualização excede o limite permitido.")
        payload = response.read(maximum + 1)
        if len(payload) > maximum:
            raise RuntimeError("O conteúdo excede o limite permitido.")
        return payload


def fetch_latest_version() -> dict:
    payload = read_update_bytes(VERSION_URL, MAX_VERSION_BYTES)
    result = json.loads(payload.decode("utf-8"))
    if not isinstance(result, dict) or not re.fullmatch(r"\d+(?:\.\d+){1,3}(?:-dev\.\d+)?", str(result.get("version", ""))):
        raise RuntimeError("O manifesto de versão do UI-debug é inválido.")
    if result.get("channel") != CHANNEL:
        raise RuntimeError("A origem respondeu com um canal inesperado.")
    return result


def install_self_update(app_dir: Path, archive_bytes: bytes) -> None:
    """Stage and validate the UI-debug subtree, then replace only its own files."""
    app_dir = app_dir.resolve()
    temp_root = Path(tempfile.mkdtemp(prefix="ui-debug-update-"))
    stage = temp_root / "stage"
    stage.mkdir()
    backups: list[tuple[Path, Path]] = []
    replaced: list[Path] = []
    try:
        archive_path = temp_root / "update.zip"
        archive_path.write_bytes(archive_bytes)
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                raise RuntimeError("O ZIP de atualização tem uma estrutura inesperada.")
            unpacked = sum(max(0, int(item.file_size)) for item in members)
            if unpacked > MAX_UNPACKED_BYTES:
                raise RuntimeError("O ZIP de atualização excede o limite após extração.")
            seen: set[str] = set()
            extracted_files: dict[str, Path] = {}
            for item in members:
                raw = item.filename.replace("\\", "/")
                pure = PurePosixPath(raw)
                if pure.is_absolute() or ".." in pure.parts or "\x00" in raw or "\\" in item.filename:
                    raise RuntimeError("O ZIP contém um caminho inseguro.")
                if len(pure.parts) < 2 or pure.parts[-2] != "UI-debug":
                    continue
                name = pure.parts[-1]
                canonical_name = next(
                    (allowed for allowed in UPDATE_FILES if allowed.casefold() == name.casefold()),
                    None,
                )
                if canonical_name is None:
                    continue
                mode = (item.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type and file_type not in {stat.S_IFREG, stat.S_IFDIR}:
                    raise RuntimeError("O ZIP contém um link ou arquivo especial.")
                key = canonical_name.casefold()
                if key in seen:
                    raise RuntimeError("O ZIP contém caminhos duplicados ou ambíguos.")
                seen.add(key)
                target = stage / canonical_name
                target.write_bytes(archive.read(item))
                extracted_files[canonical_name] = target
            if "ui_debug.py" not in extracted_files or "version.json" not in extracted_files:
                raise RuntimeError("O ZIP não contém os arquivos essenciais do UI-debug.")
        version_data = json.loads(extracted_files["version.json"].read_text(encoding="utf-8"))
        if version_data.get("channel") != CHANNEL:
            raise RuntimeError("O pacote não é um build do canal UI-debug.")
        targets = [name for name in extracted_files if name in UPDATE_FILES]
        for name in targets:
            target = app_dir / name
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise RuntimeError("Destino de atualização inseguro: " + name)
        backup_dir = temp_root / "backup"
        backup_dir.mkdir()
        try:
            for name in targets:
                target = app_dir / name
                if target.exists():
                    backup = backup_dir / name
                    shutil.copy2(target, backup)
                    backups.append((backup, target))
            for name in targets:
                target = app_dir / name
                replacement = stage / name
                os.replace(replacement, target)
                replaced.append(target)
        except OSError:
            for target in reversed(replaced):
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            for backup, target in reversed(backups):
                try:
                    if backup.exists():
                        os.replace(backup, target)
                except OSError:
                    pass
            raise
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


class GradientBackdrop(tk.Canvas):
    """Fixed set of gradient strips updated in place to avoid full-window redraw flashes."""
    def __init__(self, master, app, **kwargs):
        super().__init__(master, highlightthickness=0, bd=0, **kwargs)
        self.app = app
        self.strips: list[int] = []
        self.star_items: list[tuple[int, float, float]] = []
        self._last_size = (0, 0)
        for index in range(160):
            item = self.create_rectangle(0, 0, 1, 1, width=0, tags="gradient")
            self.strips.append(item)
        self.glow_items: list[tuple[int, str, float, str]] = []
        for corner, tint in (("tl", "#D946EF"), ("tr", "#7C3AED"), ("bl", "#BE185D"), ("br", "#6D28D9")):
            for level in range(34):
                item = self.create_oval(0, 0, 1, 1, fill="", outline="", tags="corner-glow")
                self.glow_items.append((item, corner, level / 33, tint))
        # Deterministic, subtle star specks; static unless reduced-motion is disabled.
        stars = [(0.13, 0.16), (0.31, 0.08), (0.46, 0.22), (0.69, 0.11),
                 (0.88, 0.27), (0.76, 0.42), (0.19, 0.56), (0.93, 0.68),
                 (0.58, 0.79), (0.36, 0.9), (0.08, 0.83), (0.82, 0.91)]
        for index, (rx, ry) in enumerate(stars):
            radius = 1 if index % 4 else 2
            item = self.create_oval(0, 0, 0, 0, width=0, tags="stars")
            self.star_items.append((item, rx, ry))
        self.bind("<Configure>", self._resize, add="+")
        self._resize(None)

    def _resize(self, _event):
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        if (width, height) == self._last_size:
            return
        self._last_size = (width, height)
        colors = self.app.colors if self.app.colors else PALETTES["dark"]
        for index, item in enumerate(self.strips):
            x0 = width * index / len(self.strips)
            x1 = width * (index + 1) / len(self.strips) + 1
            color = blend_hex(colors["bg"], colors["panel2"], index / max(1, len(self.strips) - 1) * 0.42)
            self.coords(item, x0, 0, x1, height)
            self.itemconfigure(item, fill=color, outline=color)
        for item, corner, level, tint in self.glow_items:
            cx = 0 if corner.endswith("l") else width
            cy = 0 if corner.startswith("t") else height
            rx, ry = width * (0.60 - 0.38 * level), height * (0.88 - 0.54 * level)
            self.coords(item, cx - rx, cy - ry, cx + rx, cy + ry)
            self.itemconfigure(item, fill=blend_hex(colors["bg"], tint, 0.018 + 0.17 * (level ** 1.65)), outline="")
        for index, (item, rx, ry) in enumerate(self.star_items):
            x, y = width * rx, height * ry
            r = 1.5 if index % 4 else 2.3
            self.coords(item, x - r, y - r, x + r, y + r)
            self.itemconfigure(item, fill=blend_hex(colors["muted"], colors["accent2"], 0.3), outline="")


class RoundedCard(tk.Frame):
    """Rounded canvas underlay with a normal frame for native, accessible controls."""
    def __init__(self, master, app, *, background_key="panel", padding=16, radius=18):
        self.backdrop_key = background_key_for(master, app, "bg")
        super().__init__(master, bg=app.colors[self.backdrop_key], bd=0, highlightthickness=0)
        self.app = app
        self.background_key = background_key
        self.padding = padding
        self.radius = radius
        self.canvas = tk.Canvas(self, bg=app.colors[self.backdrop_key], bd=0, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = tk.Frame(self, bg=app.colors[background_key], bd=0, highlightthickness=0)
        if isinstance(padding, tuple):
            px, py = padding
        else:
            px = py = padding
        self.body.pack(fill="both", expand=True, padx=max(2, int(px)), pady=max(2, int(py)))
        self._shape = self.canvas.create_polygon(
            *rounded_points(1, 1, 4, 4, radius), smooth=False,
            fill=app.colors[background_key], outline=app.colors["border"], width=1.5,
            tags="surface",
        )
        self.bind("<Configure>", self._resize, add="+")
        self.app.cards.append(self)
        self._resize(None)

    def _resize(self, _event):
        try:
            width, height = max(4, self.winfo_width()), max(4, self.winfo_height())
            self.canvas.coords(self._shape, *rounded_points(1, 1, width - 1, height - 1, self.radius))
            self.canvas.itemconfigure(
                self._shape, fill=self.app.colors[self.background_key],
                outline=self.app.colors["border"], width=1.5,
            )
            self.configure(bg=self.app.colors[self.backdrop_key])
            self.canvas.configure(bg=self.app.colors[self.backdrop_key])
            self.body.configure(bg=self.app.colors[self.background_key])
        except tk.TclError:
            pass

    def refresh_theme(self):
        self.configure(bg=self.app.colors["bg"])
        self._resize(None)


class RoundedButton(tk.Canvas):
    """Rounded button with a subtle animated hover scale and lavender hover fill."""
    def __init__(self, master, app, text, command=None, *, variant="secondary", width=None, height=40):
        self.app, self.text, self.command, self.variant = app, text, command, variant
        self.base_height = self.height = int(height)
        self.font_size = 9 if height < 36 else 10
        self.font = tkfont.Font(family="Segoe UI", size=self.font_size,
                                weight="bold" if variant == "primary" else "normal")
        desired = self.font.measure(text) + (34 if variant == "primary" else 30)
        self.base_width = self.width = int(width or max(82, min(300, desired)))
        self.current_scale, self._target_scale, self._scale_after_id = 1.0, 1.0, None
        self.bg_key = background_key_for(master, app, "bg")
        super().__init__(master, width=self.width, height=self.height, bg=app.colors[self.bg_key], bd=0, highlightthickness=0, cursor="hand2")
        self.hovered = self.pressed = False
        self._gradient_ids = []
        for row in range(height):
            left, right = rounded_span(row, self.width, height, height // 2)
            color = app.colors["accent"] if variant == "primary" else app.colors["button"]
            self._gradient_ids.append(self.create_line(left, row, max(left, right), row,
                fill=color, width=2, tags=("button-shape", "button-fill")))
        self._outline_id = self.create_polygon(
            *rounded_points(1, 1, self.width - 1, height - 1, height // 2, steps=16),
            fill="", outline=app.colors["accent"] if variant == "primary" else app.colors["border"],
            width=1.6, tags=("button-shape", "button-outline"))
        self._text_id = self.create_text(self.width / 2, height / 2, text=text, fill=app.colors["fg"],
                                         font=self.font, width=self.width - 18, tags="button-shape")
        self.bind("<Configure>", self._on_resize, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<ButtonPress-1>", self._press, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<Return>", self._keyboard, add="+")
        self.bind("<space>", self._keyboard, add="+")
        app.buttons.append(self)
        self.refresh_theme()

    def _on_resize(self, _event):
        pass

    def _apply_size(self, scale):
        self.current_scale = scale
        self.width, self.height = max(1, round(self.base_width * scale)), max(1, round(self.base_height * scale))
        try:
            self.configure(width=self.width, height=self.height)
            denominator = max(1, len(self._gradient_ids) - 1)
            for index, item in enumerate(self._gradient_ids):
                row = (self.height - 1) * index / denominator
                left, right = rounded_span(round(row), self.width, self.height, self.height // 2)
                self.coords(item, left, row, max(left, right), row)
                self.itemconfigure(item, width=2)
            self.coords(self._outline_id, *rounded_points(1, 1, self.width - 1, self.height - 1, self.height / 2, steps=16))
            self.itemconfigure(self._outline_id, width=1.6)
            self.coords(self._text_id, self.width / 2, self.height / 2)
            self.itemconfigure(self._text_id, width=self.width - 18)
            self.font.configure(size=max(8, round(self.font_size * (1.04 if scale > 1.01 else 1.0))))
            self._refresh_colors()
        except tk.TclError:
            pass

    def _animate_to(self, scale):
        self._target_scale = scale
        if self.app.settings.get("reduce_motion") or not self.app.settings.get("animations_enabled", True):
            if self._scale_after_id is not None:
                try: self.after_cancel(self._scale_after_id)
                except tk.TclError: pass
                self._scale_after_id = None
            self._apply_size(scale)
            return
        if self._scale_after_id is not None:
            try: self.after_cancel(self._scale_after_id)
            except tk.TclError: pass
        start, frames = self.current_scale, 5
        def frame(index=1):
            if index > frames:
                self._scale_after_id = None
                self._apply_size(scale)
                return
            progress = index / frames
            eased = 1 - (1 - progress) ** 3
            self._apply_size(start + (scale - start) * eased)
            self._scale_after_id = self.after(14, lambda: frame(index + 1))
        frame()

    def _enter(self, _event=None):
        self.hovered = True
        self._refresh_colors()
        self._animate_to(1.055)

    def _leave(self, _event=None):
        self.hovered = self.pressed = False
        self._refresh_colors()
        self._animate_to(1.0)

    def _press(self, _event=None):
        self.pressed = True
        self._refresh_colors()
        self._animate_to(1.075 if self.hovered else 1.025)
        return "break"

    def _release(self, event=None):
        invoke = self.pressed and event is not None and 0 <= event.x <= self.width and 0 <= event.y <= self.height
        self.pressed = False
        self._refresh_colors()
        self._animate_to(1.055 if self.hovered else 1.0)
        if invoke and callable(self.command):
            self.command()
        return "break"

    def _keyboard(self, _event=None):
        if callable(self.command): self.command()
        return "break"

    def _refresh_colors(self):
        c = self.app.colors
        if self.variant == "primary":
            start, end = c["accent"], c["accent2"]
            if self.hovered: start, end = blend_hex(start, "#FFFFFF", 0.10), blend_hex(end, "#FFFFFF", 0.08)
            if self.pressed: start, end = blend_hex(start, "#000000", 0.12), blend_hex(end, "#000000", 0.12)
            for row, item in enumerate(self._gradient_ids):
                self.itemconfigure(item, fill=blend_hex(start, end, row / max(1, len(self._gradient_ids) - 1)))
            text_color, outline = "#FFFFFF", blend_hex(end, "#FFFFFF", 0.20)
        elif self.hovered:
            start, end = "#D8C7FF", "#B9A5FF"
            if self.pressed: start, end = blend_hex(start, "#8B5CF6", 0.18), blend_hex(end, "#8B5CF6", 0.18)
            for row, item in enumerate(self._gradient_ids):
                self.itemconfigure(item, fill=blend_hex(start, end, row / max(1, len(self._gradient_ids) - 1)))
            text_color, outline = "#2B174E", "#D8C7FF"
        else:
            for item in self._gradient_ids: self.itemconfigure(item, fill=c["button"])
            text_color, outline = c["fg"], c["border"]
        self.itemconfigure(self._outline_id, outline=outline)
        self.itemconfigure(self._text_id, fill=text_color)
        self.configure(bg=c.get(self.bg_key, c["bg"]))

    def refresh_theme(self):
        self._refresh_colors()


class RoundedField(tk.Frame):
    """Rounded border/background behind a flat native entry."""
    def __init__(self, master, app, *, textvariable=None, placeholder=None, width=None, readonly=False):
        self.bg_key = background_key_for(master, app, "bg")
        super().__init__(master, bg=app.colors[self.bg_key], bd=0, highlightthickness=0, width=width or 260, height=42)
        self.app = app
        self.placeholder = placeholder
        self.readonly = readonly
        self.canvas = tk.Canvas(self, bg=app.colors[self.bg_key], bd=0, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.shape = self.canvas.create_polygon(*rounded_points(1, 1, 4, 4, 12), fill=app.colors["field"], outline=app.colors["border"], width=1.5)
        self.entry = tk.Entry(
            self, textvariable=textvariable, bg=app.colors["field"], fg=app.colors["input_fg"],
            insertbackground=app.colors["input_fg"], relief="flat", bd=0, highlightthickness=0,
            font=("Segoe UI", 10), readonlybackground=app.colors["field"],
            disabledbackground=app.colors["field"], disabledforeground=app.colors["muted"],
        )
        self.entry.place(x=12, y=1, relwidth=1, width=-24, relheight=1, height=-2)
        if readonly:
            self.entry.configure(state="readonly")
        self.bind("<Configure>", self._resize, add="+")
        self.app.fields.append(self)
        self._resize(None)

    def _resize(self, _event):
        try:
            width, height = max(4, self.winfo_width()), max(4, self.winfo_height())
            self.canvas.coords(self.shape, *rounded_points(1, 1, width - 1, height - 1, min(12, height / 2)))
            self.canvas.itemconfigure(self.shape, fill=self.app.colors["field"], outline=self.app.colors["border"])
            self.canvas.configure(bg=self.app.colors[self.bg_key])
            self.configure(bg=self.app.colors[self.bg_key])
            self.entry.configure(
                bg=self.app.colors["field"], fg=self.app.colors["input_fg"],
                insertbackground=self.app.colors["input_fg"],
                readonlybackground=self.app.colors["field"], disabledbackground=self.app.colors["field"],
                disabledforeground=self.app.colors["muted"],
            )
        except tk.TclError:
            pass

    def refresh_theme(self):
        self._resize(None)


class Dropdown(tk.Frame):
    """Compact custom dropdown that visually fits the rounded field system."""
    def __init__(self, master, app, options, value, command=None, *, width=220):
        self.bg_key = background_key_for(master, app, "bg")
        super().__init__(master, bg=app.colors[self.bg_key], width=width, height=42, bd=0, highlightthickness=0)
        self.app = app
        self.options = list(options)
        self.value = tk.StringVar(value=value)
        self.command = command
        self.canvas = tk.Canvas(self, bg=app.colors[self.bg_key], width=width, height=42, bd=0, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.shape = self.canvas.create_polygon(*rounded_points(1, 1, width - 1, 41, 12), fill=app.colors["field"], outline=app.colors["border"], width=1.5)
        self.label_id = self.canvas.create_text(14, 21, text=value, anchor="w", fill=app.colors["input_fg"], font=("Segoe UI", 10))
        self.chevron_id = self.canvas.create_text(width - 18, 21, text="⌄", fill=app.colors["accent2"], font=("Segoe UI", 13, "bold"))
        self.canvas.bind("<Button-1>", self._open)
        self.canvas.bind("<Enter>", self._hover)
        self.canvas.bind("<Leave>", self._unhover)
        app.dropdowns.append(self)

    def _open(self, _event=None):
        menu = tk.Menu(self, tearoff=0, bg=self.app.colors["panel"], fg=self.app.colors["fg"],
                       activebackground=self.app.colors["accent"], activeforeground="#FFFFFF",
                       bd=0, relief="flat", font=("Segoe UI", 10))
        for option in self.options:
            menu.add_command(label=option, command=lambda value=option: self.set(value))
        try:
            menu.tk_popup(self.winfo_rootx() + 6, self.winfo_rooty() + self.winfo_height() - 2)
        finally:
            menu.grab_release()

    def _hover(self, _event=None):
        self.canvas.itemconfigure(self.shape, outline=self.app.colors["accent"])

    def _unhover(self, _event=None):
        self.canvas.itemconfigure(self.shape, outline=self.app.colors["border"])

    def set(self, value):
        self.value.set(value)
        self.canvas.itemconfigure(self.label_id, text=value)
        if callable(self.command):
            self.command(value)

    def get(self):
        return self.value.get()

    def refresh_theme(self):
        c = self.app.colors
        self.configure(bg=c.get(self.bg_key, c["bg"]))
        self.canvas.configure(bg=c.get(self.bg_key, c["bg"]))
        self.canvas.itemconfigure(self.shape, fill=c["field"], outline=c["border"])
        self.canvas.itemconfigure(self.label_id, fill=c["input_fg"])
        self.canvas.itemconfigure(self.chevron_id, fill=c["accent2"])


class ToggleSwitch(tk.Canvas):
    def __init__(self, master, app, variable, command=None, *, width=48, height=26):
        super().__init__(master, width=width, height=height, bg=app.colors["panel"], bd=0, highlightthickness=0, cursor="hand2")
        self.app = app
        self.variable = variable
        self.command = command
        self.width = width
        self.height = height
        self.track = self.create_polygon(*rounded_points(1, 1, width - 1, height - 1, height / 2), fill=app.colors["border"], outline="")
        self.knob = self.create_oval(4, 4, 22, 22, fill="#FFFFFF", outline="")
        self.bind("<Button-1>", self._toggle)
        self.refresh_theme()

    def _toggle(self, _event=None):
        self.variable.set(not bool(self.variable.get()))
        self.refresh_theme()
        if callable(self.command):
            self.command()

    def refresh_theme(self):
        active = bool(self.variable.get())
        c = self.app.colors
        track = blend_hex(c["accent"], c["accent2"], 0.45) if active else c["border"]
        left = self.width - 23 if active else 4
        self.itemconfigure(self.track, fill=track)
        self.coords(self.knob, left, 4, left + 18, 22)
        self.itemconfigure(self.knob, fill="#FFFFFF")
        self.configure(bg=c["panel"])


class OrbitalAtom(tk.Canvas):
    """Animated atom mark with moving light points and a soft gradient trail."""
    def __init__(self, master, app, *, size=42):
        super().__init__(master, width=size, height=size, bg=app.colors["panel"], bd=0, highlightthickness=0)
        self.app, self.size, self.phase = app, size, 0.0
        self.particles = []
        self.app.orbital_marks.append(self)
        self._draw_tracks()
        specs = ((0.0, size * .34, size * .15, .3, app.colors["accent2"]),
                 (math.pi / 3, size * .30, size * .135, 2.2, "#E879F9"),
                 (-math.pi / 3, size * .30, size * .135, 4.1, "#A78BFA"))
        for rotation, rx, ry, angle, color in specs:
            rings = []
            for radius, strength in ((5.7, .22), (4.1, .42), (2.8, .74), (1.55, 1.0)):
                rings.append((self.create_oval(0, 0, 0, 0,
                    fill=blend_hex(app.colors["panel"], color, strength), outline="", tags="atom-particle"), radius))
            self.particles.append({"rotation": rotation, "rx": rx, "ry": ry, "angle": angle,
                                   "speed": .085 if rotation == 0 else (.073 if rotation > 0 else -.067),
                                   "rings": rings})
        self.create_oval(size/2 - 2, size/2 - 2, size/2 + 2, size/2 + 2,
                         fill=app.colors["accent2"], outline="", tags="atom-nucleus")
        self._tick()

    def _draw_tracks(self):
        self.delete("atom-track")
        c = self.app.colors
        cx = cy = self.size / 2
        for idx, (rotation, rx, ry) in enumerate(((0, self.size*.34, self.size*.15),
            (math.pi/3, self.size*.30, self.size*.135), (-math.pi/3, self.size*.30, self.size*.135))):
            points = [ellipse_point(cx, cy, rx, ry, 2 * math.pi * i / 48, rotation) for i in range(49)]
            start, end = ((c["accent"], c["accent2"]) if idx == 0 else
                          (("#E879F9", c["accent"]) if idx == 1 else (c["accent2"], "#A78BFA")))
            for i in range(48):
                self.create_line(*points[i], *points[i+1], fill=blend_hex(start, end, i/47),
                                 width=1.35, tags="atom-track")

    def _tick(self):
        try:
            self.phase += .08
            cx = cy = self.size / 2
            rotations = (0.0, math.pi / 3, -math.pi / 3)
            for particle in self.particles:
                particle["angle"] += particle["speed"]
                x, y = ellipse_point(cx, cy, particle["rx"], particle["ry"],
                    particle["angle"] + self.phase * .07, particle["rotation"])
                for item, radius in particle["rings"]:
                    self.coords(item, x-radius, y-radius, x+radius, y+radius)
            self.after(34, self._tick)
        except tk.TclError:
            return

    def refresh_theme(self):
        self.configure(bg=self.app.colors["panel"])
        self._draw_tracks()


SPLASH_BACKGROUND = "#080713"
SPLASH_PALETTES = (
    ("#F9A8D4", "#A78BFA"), ("#C4B5FD", "#67E8F9"),
    ("#F0ABFC", "#818CF8"), ("#FDA4AF", "#C084FC"),
    ("#A5B4FC", "#F5D0FE"), ("#D8B4FE", "#7DD3FC"),
    ("#FBCFE8", "#DDD6FE"), ("#E9D5FF", "#F0ABFC"),
)
STARTUP_MESSAGES = (
    "Acendendo o núcleo visual", "Preparando seu espaço de trabalho",
    "Carregando as preferências locais", "Alinhando cartões, contornos e órbitas",
    "Polindo os detalhes da interface", "Conferindo o canal de desenvolvimento",
    "Quase pronto — abrindo seu espaço de mídia",
)
UPDATE_MESSAGES = (
    "Conectando ao canal de desenvolvimento", "Consultando o manifesto de versão",
    "Preparando o pacote de atualização", "Conferindo os arquivos do protótipo",
    "Validando os caminhos permitidos", "Preservando suas preferências locais",
    "Finalizando os detalhes da nova órbita",
)


class CosmicSplash:
    """Full-screen orbital loader, glowing particles, and gradient-only status text."""
    def __init__(self, root, *, mode="startup", looping=False, on_close=None):
        self.root, self.mode, self.looping, self.on_close = root, mode, looping, on_close
        self._finish_callback = self._animation_after = self._message_after = self._finish_after = None
        self._closed = False
        self.width = max(800, int(root.winfo_screenwidth()))
        self.height = max(600, int(root.winfo_screenheight()))
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        try:
            self.window.attributes("-fullscreen", True)
            self.window.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.window.geometry("%dx%d+0+0" % (self.width, self.height))
        self.window.configure(bg=SPLASH_BACKGROUND)
        self.canvas = tk.Canvas(self.window, bg=SPLASH_BACKGROUND, bd=0, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.active_texts, self._status_serial, self._palette_bag = [], 0, []
        self.phase = 0.0
        self._draw_scene()
        self._draw_orbit_loader()
        self._draw_brand()
        self.messages = STARTUP_MESSAGES if mode == "startup" else UPDATE_MESSAGES
        self.message_index = 0
        self._add_status(self.messages[0])
        self.window.bind("<Escape>", lambda _event: "break", add="+")
        self._animation_after = self.window.after(30, self._animate)
        self._message_after = self.window.after(690, self._advance_message)
        try:
            self.window.lift()
            self.window.focus_force()
        except tk.TclError:
            pass

    def _draw_scene(self):
        c, w, h = self.canvas, self.width, self.height
        for i in range(160):
            x0, x1 = w * i / 160, w * (i + 1) / 160 + 1
            c.create_rectangle(x0, 0, x1, h, fill=blend_hex(SPLASH_BACKGROUND, "#20113B", .05 + .20*i/159), outline="")
        for cx, cy, tint in ((0, 0, "#D946EF"), (w, 0, "#7C3AED"), (0, h, "#BE185D"), (w, h, "#6D28D9")):
            for level in range(38):
                t = level / 37
                rx, ry = w * (.58 - .34*t), h * (.82 - .48*t)
                c.create_oval(cx-rx, cy-ry, cx+rx, cy+ry,
                    fill=blend_hex(SPLASH_BACKGROUND, tint, .012 + .20*t**1.7), outline="")
        rng = random.Random(119 + w + h)
        for _ in range(38):
            x, y = rng.random()*w, rng.random()*h
            radius, tint = rng.choice((1, 1, 1.5, 2)), rng.choice(("#8D86B5", "#8E84D6", "#A58DCB", "#65CBDC"))
            c.create_oval(x-radius, y-radius, x+radius, y+radius,
                fill=blend_hex(SPLASH_BACKGROUND, tint, .55), outline="")

    def _draw_orbit_loader(self):
        cx, cy = self.width/2, self.height*.315
        rx, ry = min(180, self.width*.145), min(88, self.height*.092)
        self.track_specs = ((0.0, rx, ry, ("#E879F9", "#A78BFA")),
            (math.pi/3, rx*.93, ry*.88, ("#C084FC", "#67E8F9")),
            (-math.pi/3, rx*.72, ry*1.22, ("#F472B6", "#A78BFA")))
        for rotation, orbit_rx, orbit_ry, palette in self.track_specs:
            points = [ellipse_point(cx, cy, orbit_rx, orbit_ry, 2*math.pi*i/84, rotation) for i in range(85)]
            for i in range(84):
                self.canvas.create_line(*points[i], *points[i+1], fill=blend_hex(palette[0], palette[1], i/83),
                                        width=2.4, tags="splash-orbit-track")
        self.particles = []
        for orbit, angle, speed, color in ((0, .7, .055, "#F9A8D4"), (1, 2.6, .047, "#A78BFA"), (2, 4.2, -.052, "#67E8F9")):
            trail = [self.canvas.create_line(0, 0, 0, 0, fill=SPLASH_BACKGROUND, width=1,
                     capstyle=tk.ROUND, tags="splash-trail") for _ in range(16)]
            glows = [(self.canvas.create_oval(0, 0, 0, 0,
                     fill=blend_hex(SPLASH_BACKGROUND, color, strength), outline="", tags="splash-particle"), radius, strength)
                     for radius, strength in ((15, .16), (10, .27), (6.5, .52), (3.6, .93))]
            self.particles.append({"orbit": orbit, "angle": angle, "speed": speed, "color": color, "trail": trail, "glows": glows, "history": []})
        self.canvas.create_oval(cx-4, cy-4, cx+4, cy+4, fill="#F5D0FE", outline="")
        self.canvas.create_oval(cx-12, cy-12, cx+12, cy+12, fill=blend_hex(SPLASH_BACKGROUND, "#C084FC", .55), outline="")

    def _draw_brand(self):
        self.canvas.create_text(self.width/2, self.height*.135, text="CHATGPT MEDIA DOWNLOADER",
            fill="#AAA7C8", font=("Segoe UI", max(9, int(min(self.width,self.height)*.012)), "bold"))
        subtitle = "UI-DEBUG  /  CANAL DE DESENVOLVIMENTO" if self.mode == "startup" else "ATUALIZAÇÃO VISUAL  /  CANAL UI-DEBUG"
        self.canvas.create_text(self.width/2, self.height*.16, text=subtitle,
            fill="#7E789F", font=("Segoe UI", max(8, int(min(self.width,self.height)*.009)), "normal"))
        self.canvas.create_text(self.width/2, self.height*.92, text="UMA ÓRBITA DE CADA VEZ",
            fill="#77718F", font=("Segoe UI", max(8, int(min(self.width,self.height)*.009)), "bold"))

    def _next_palette(self):
        if not self._palette_bag:
            self._palette_bag = list(range(len(SPLASH_PALETTES)))
            random.shuffle(self._palette_bag)
        return SPLASH_PALETTES[self._palette_bag.pop()]

    def _add_status(self, text):
        self._status_serial += 1
        tag = "splash-status-%d" % self._status_serial
        palette = self._next_palette()
        font = tkfont.Font(root=self.window, family="Segoe UI",
                           size=max(15, int(min(self.width,self.height)*.018)), weight="bold")
        widths = [font.measure(ch) for ch in text]
        x, start_y = (self.width-sum(widths))/2, self.height*.735
        glyphs, colors = [], []
        for i, character in enumerate(text):
            fill = blend_hex(palette[0], palette[1], i/max(1,len(text)-1))
            item = self.canvas.create_text(x, start_y, text=character, anchor="w", fill=fill, font=font, tags=(tag,"splash-status"))
            glyphs.append((item,x)); colors.append(fill); x += widths[i]
        self.active_texts.append({"tag":tag,"glyphs":glyphs,"colors":colors,"start_y":start_y,"age":0,"font":font})

    def set_stage(self, text):
        if self._closed: return
        if self._message_after is not None:
            try: self.window.after_cancel(self._message_after)
            except tk.TclError: pass
        self._add_status(text)
        self._message_after = self.window.after(760 if not self.looping else 900, self._advance_message)

    def _advance_message(self):
        if self._closed: return
        if self.looping:
            self.message_index = (self.message_index+1) % len(self.messages)
            self._add_status(self.messages[self.message_index])
            self._message_after = self.window.after(900, self._advance_message)
        else:
            self.message_index += 1
            if self.message_index < len(self.messages):
                self._add_status(self.messages[self.message_index])
                self._message_after = self.window.after(760, self._advance_message)
            else:
                self._finish_after = self.window.after(950, self.close)

    def _animate(self):
        if self._closed: return
        self.phase += .055
        for p in self.particles:
            rotation, orbit_rx, orbit_ry, _palette = self.track_specs[p["orbit"]]
            p["angle"] += p["speed"]
            point = ellipse_point(self.width/2, self.height*.315, orbit_rx, orbit_ry, p["angle"], rotation)
            history = p["history"]; history.insert(0, point); del history[16:]
            for i, line in enumerate(p["trail"]):
                if i+1 < len(history):
                    a,b = history[i],history[i+1]
                    self.canvas.coords(line,a[0],a[1],b[0],b[1])
                    strength = .84*(1-i/len(p["trail"]))+.08
                    self.canvas.itemconfigure(line,fill=blend_hex(SPLASH_BACKGROUND,p["color"],strength),width=max(1,3.2-i*.13))
                else: self.canvas.coords(line,-5,-5,-5,-5)
            x,y = point
            for glow,radius,strength in p["glows"]:
                r = radius*(1+.045*math.sin(self.phase*2+radius))
                self.canvas.coords(glow,x-r,y-r,x+r,y+r)
                self.canvas.itemconfigure(glow,fill=blend_hex(SPLASH_BACKGROUND,p["color"],strength))
        for m in list(self.active_texts):
            m["age"] += 30; age = m["age"]
            y = m["start_y"] - self.height*.105*min(1,age/760)
            fade = max(0,min(1,(age-520)/300))
            appear = .10+.90*min(1,age/250)
            for (item,x),original in zip(m["glyphs"],m["colors"]):
                self.canvas.coords(item,x,y)
                self.canvas.itemconfigure(item,fill=blend_hex(SPLASH_BACKGROUND,original,appear*(1-fade)))
            if age > 1080:
                self.canvas.delete(m["tag"]); self.active_texts.remove(m)
                m.pop("font", None)
        try: self._animation_after = self.window.after(30,self._animate)
        except tk.TclError: self.close()

    def finish(self, final_message, callback=None, *, hold_ms=1450):
        if self._closed:
            if callable(callback): callback()
            return
        self.looping = False; self._finish_callback = callback
        if self._message_after is not None:
            try: self.window.after_cancel(self._message_after)
            except tk.TclError: pass
            self._message_after = None
        self._add_status(final_message)
        if self._finish_after is not None:
            try: self.window.after_cancel(self._finish_after)
            except tk.TclError: pass
        self._finish_after = self.window.after(hold_ms,self.close)

    def close(self):
        if self._closed: return
        self._closed = True
        for identifier in (self._animation_after,self._message_after,self._finish_after):
            if identifier is not None:
                try: self.window.after_cancel(identifier)
                except tk.TclError: pass
        try: self.window.destroy()
        except tk.TclError: pass
        for callback in (self.on_close,self._finish_callback):
            if callable(callback):
                try: callback()
                except tk.TclError: pass


class SpaceUIPrototype:
    def __init__(self, root: tk.Tk, *, show_splash=True):
        self.root = root
        self.root.title(APP_NAME + "  •  v" + APP_VERSION)
        self.root.geometry("1280x830")
        self.root.minsize(960, 620)
        self.root.configure(bg=PALETTES["dark"]["bg"])
        # Keep the native root hidden behind the immersive Toplevel until the
        # startup sequence ends; otherwise Windows can lift the root over it.
        if show_splash:
            self.root.withdraw()
        self.root.option_add("*tearOff", False)
        self.style = ttk.Style(root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.app_dir = Path(__file__).resolve().parent
        self.settings_path = self._settings_path()
        self.settings = self._load_settings()
        self.colors = dict(PALETTES.get(self.settings["theme"], PALETTES["dark"]))
        self.colors["accent"] = self.settings["accent_color"]
        self.colors["accent2"] = self.settings["accent_color_2"]
        self._apply_scrollbar_style()
        self.cards: list[RoundedCard] = []
        self.buttons: list[RoundedButton] = []
        self.fields: list[RoundedField] = []
        self.dropdowns: list[Dropdown] = []
        self.toggles: list[ToggleSwitch] = []
        self.scroll_panes: list[ScrollPane] = []
        self.labels: list[tuple[tk.Widget, str, str, tuple]] = []
        self.nav_items: dict[str, tuple[tk.Canvas, str, str, str]] = {}
        self.current_page = "home"
        self.toast_after = None
        self.update_info: dict | None = None
        self._update_busy = False
        self._stop = threading.Event()

        self.orbital_marks: list[OrbitalAtom] = []
        self.splash: CosmicSplash | None = None
        self.shell = tk.Frame(root, bg=self.colors["bg"], bd=0, highlightthickness=0)
        self.shell.place(x=0, y=0, relwidth=1, relheight=1)
        self._build_shell()
        self._build_pages()
        self.show_page("home")
        self.apply_theme(refresh=False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if show_splash:
            self.splash = CosmicSplash(root, mode="startup", looping=False, on_close=self._startup_splash_finished)
        elif self.settings.get("update_check_on_startup", True):
            self.root.after(1800, self.check_update_async)

    def _settings_path(self) -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            return base / "ChatGPT" / "MediaDownloader-UI-debug" / "settings.json"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "ChatGPT" / "MediaDownloader-UI-debug" / "settings.json"
        return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "ChatGPT" / "MediaDownloader-UI-debug" / "settings.json"

    def _load_settings(self) -> dict:
        data = dict(DEFAULT_SETTINGS)
        try:
            loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update({key: loaded[key] for key in DEFAULT_SETTINGS if key in loaded})
        except (OSError, json.JSONDecodeError):
            pass
        if data.get("theme") not in PALETTES:
            data["theme"] = "dark"
        for key, fallback in (("accent_color", "#7C5CFF"), ("accent_color_2", "#20D8E7")):
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(data.get(key, ""))):
                data[key] = fallback
            data[key] = data[key].upper()
        if data.get("ui_density") not in {"comfortable", "compact"}:
            data["ui_density"] = "comfortable"
        return data

    def save_settings(self, show_toast=True):
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=str(self.settings_path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(self.settings, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.settings_path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        if show_toast:
            self.toast("Preferências do UI-debug salvas localmente.")

    def _load_settings_defaults(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.apply_theme()
        self.save_settings(show_toast=False)
        self._sync_settings_controls()
        self.toast("Preferências de demonstração restauradas.")

    def _build_shell(self):
        outer = tk.Frame(self.shell, bg=self.colors["bg"], padx=18, pady=16)
        outer.pack(fill="both", expand=True)
        self.backdrop = GradientBackdrop(outer, self)
        self.backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        self.sidebar = tk.Frame(outer, bg=self.colors["panel"], width=220, bd=0, highlightthickness=0)
        self.sidebar.pack(side="left", fill="y", padx=(0, 16))
        self.sidebar.pack_propagate(False)

        brand = tk.Frame(self.sidebar, bg=self.colors["panel"], padx=18, pady=20)
        brand.pack(fill="x")
        mark = OrbitalAtom(brand, self, size=42)
        mark.pack(side="left", padx=(0, 11))
        titlebox = tk.Frame(brand, bg=self.colors["panel"])
        titlebox.pack(side="left", fill="x", expand=True)
        self.label(titlebox, "MEDIA LAB", "fg", "panel", 10, "bold").pack(anchor="w")
        self.label(titlebox, "UI-debug  /  DEV", "muted", "panel", 8, "normal").pack(anchor="w", pady=(3, 0))
        self._divider(self.sidebar, "panel")
        self.label(self.sidebar, "WORKSPACE", "muted", "panel", 8, "bold").pack(anchor="w", padx=20, pady=(16, 8))

        navigation = [
            ("home", "⌂", "Início"),
            ("playlist", "≋", "Playlists"),
            ("settings", "⚙", "Aparência"),
            ("dependencies", "◈", "Dependências"),
            ("updates", "↻", "Atualizações"),
            ("help", "?", "Ajuda"),
            ("diagnostics", "⌘", "Diagnóstico"),
        ]
        self.nav_container = tk.Frame(self.sidebar, bg=self.colors["panel"])
        self.nav_container.pack(fill="x", padx=10)
        for nav_index, (key, glyph, text) in enumerate(navigation):
            nav = tk.Canvas(self.nav_container, width=194, height=43, bg=self.colors["panel"], bd=0, highlightthickness=0, cursor="hand2")
            nav.pack(fill="x", pady=2)
            shape = nav.create_polygon(*rounded_points(1, 1, 192, 42, 12, steps=14), fill=self.colors["panel"], outline="")
            icon = draw_orbit_icon(nav, 24, 21, self.colors["muted"], variant=nav_index)
            label = nav.create_text(48, 21, text=text, anchor="w", fill=self.colors["muted"], font=("Segoe UI", 10))
            nav.bind("<Button-1>", lambda _event, name=key: self.show_page(name))
            nav.bind("<Enter>", lambda _event, name=key: self._nav_hover(name, True))
            nav.bind("<Leave>", lambda _event, name=key: self._nav_hover(name, False))
            self.nav_items[key] = (nav, shape, icon, label)

        spacer = tk.Frame(self.sidebar, bg=self.colors["panel"])
        spacer.pack(fill="both", expand=True)
        self._divider(self.sidebar, "panel")
        version_card = tk.Frame(self.sidebar, bg=self.colors["panel"], padx=17, pady=14)
        version_card.pack(fill="x")
        self.label(version_card, "CANAL DE DESENVOLVIMENTO", "muted", "panel", 7, "bold").pack(anchor="w")
        version_row = tk.Frame(version_card, bg=self.colors["panel"])
        version_row.pack(fill="x", pady=(6, 0))
        self.label(version_row, APP_VERSION, "accent2", "panel", 9, "bold").pack(side="left")
        self.label(version_row, "sem release", "muted", "panel", 8, "normal").pack(side="right")

        self.main = tk.Frame(outer, bg=self.colors["bg"], bd=0, highlightthickness=0)
        self.main.pack(side="left", fill="both", expand=True)
        topbar = tk.Frame(self.main, bg=self.colors["bg"], height=74)
        topbar.pack(fill="x", pady=(1, 14))
        top_left = tk.Frame(topbar, bg=self.colors["bg"])
        top_left.pack(side="left", fill="x", expand=True)
        self.label(top_left, "CHATGPT MEDIA DOWNLOADER  /  ESPAÇO DE TESTES", "muted", "bg", 8, "bold").pack(anchor="w", pady=(3, 4))
        self.page_title_label = self.label(top_left, "Início", "fg", "bg", 22, "bold")
        self.page_title_label.pack(anchor="w")
        actions = tk.Frame(topbar, bg=self.colors["bg"])
        actions.pack(side="right", anchor="n", pady=(8, 0))
        self.status_label = self.label(actions, "●  UI DEMO", "good", "bg", 9, "bold")
        self.status_label.pack(side="left", padx=(0, 12))
        RoundedButton(actions, self, "Atualizar UI-debug", lambda: self.check_update_async(user_initiated=True), variant="secondary", width=145, height=38).pack(side="left")

        self.toast_label = self.label(self.main, "", "accent2", "bg", 9, "normal")
        self.toast_label.pack(anchor="w", pady=(0, 6))
        self.pages_area = tk.Frame(self.main, bg=self.colors["bg"], bd=0, highlightthickness=0)
        self.pages_area.pack(fill="both", expand=True)

    def _build_pages(self):
        self.page_frames: dict[str, tk.Frame] = {}
        builders = {
            "home": self._build_home,
            "playlist": self._build_playlist,
            "settings": self._build_settings,
            "dependencies": self._build_dependencies,
            "updates": self._build_updates,
            "help": self._build_help,
            "diagnostics": self._build_diagnostics,
        }
        for key, builder in builders.items():
            page = tk.Frame(self.pages_area, bg=self.colors["bg"], bd=0, highlightthickness=0)
            self.page_frames[key] = page
            pane = ScrollPane(page, self)
            pane.pack(fill="both", expand=True)
            builder(pane.body)

    def _startup_splash_finished(self):
        self.splash = None
        try:
            self.root.deiconify(); self.root.lift(); self.root.focus_force()
        except tk.TclError:
            pass
        if self.settings.get("update_check_on_startup", True):
            try: self.root.after(900, self.check_update_async)
            except tk.TclError: pass

    def label(self, parent, text, fg_key="fg", bg_key="panel", size=10, weight="normal", wraplength=None, **kwargs):
        widget = tk.Label(
            parent, text=text, bg=self.colors[bg_key], fg=self.colors[fg_key],
            font=("Segoe UI", size, weight), anchor=kwargs.pop("anchor", "w"),
            justify=kwargs.pop("justify", "left"), bd=0, highlightthickness=0,
            wraplength=wraplength or 0, **kwargs,
        )
        widget._ui_fg_key = fg_key
        widget._ui_bg_key = bg_key
        # Cap requested text wrapping for small windows. Long labels must not
        # widen a card beyond the visible scroll area on a 960px-wide display.
        if wraplength:
            widget.configure(wraplength=min(int(wraplength), 650))
        self.labels.append((widget, fg_key, bg_key, ("Segoe UI", size, weight)))
        return widget

    def frame(self, parent, bg_key="panel", **kwargs):
        widget = tk.Frame(parent, bg=self.colors[bg_key], bd=0, highlightthickness=0, **kwargs)
        widget._ui_bg_key = bg_key
        return widget

    def card(self, parent, *, background_key="panel", padding=16):
        return RoundedCard(parent, self, background_key=background_key, padding=padding)

    def button(self, parent, text, command=None, variant="secondary", width=None):
        return RoundedButton(parent, self, text, command, variant=variant, width=width)

    def _divider(self, parent, bg_key):
        widget = tk.Frame(parent, bg=self.colors["border"], height=2)
        widget.pack(fill="x", padx=16)
        widget._ui_bg_key = "border"
        return widget

    def _title_block(self, parent, eyebrow, title, subtitle):
        self.label(parent, eyebrow.upper(), "accent2", "bg", 8, "bold").pack(anchor="w", pady=(0, 6))
        self.label(parent, title, "fg", "bg", 20, "bold").pack(anchor="w")
        self.label(parent, subtitle, "muted", "bg", 10, "normal", wraplength=920).pack(anchor="w", pady=(5, 16))

    def _mock_action(self, label):
        self.toast(label + " — demonstração visual; nenhuma operação real foi iniciada.")

    def _build_home(self, body):
        self._title_block(body, "Painel principal", "Seu espaço de mídia, em órbita.", "Uma interface de demonstração para revisar cartões, hierarquia, cantos, cores e navegação antes de mexer no aplicativo real.")
        hero = self.card(body, background_key="panel2", padding=22)
        hero.pack(fill="x", pady=(0, 12))
        inside = hero.body
        head = self.frame(inside, "panel2")
        head.pack(fill="x")
        self.label(head, "CENTRAL DE DOWNLOADS", "accent2", "panel2", 8, "bold").pack(side="left")
        self.label(head, "VÍDEO   ·   ÁUDIO   ·   PLAYLISTAS", "muted", "panel2", 8, "bold").pack(side="right")
        self.label(inside, "Tudo organizado. Nada baixado.", "fg", "panel2", 21, "bold").pack(anchor="w", pady=(12, 4))
        self.label(inside, "Os campos parecem reais para avaliar o layout; os botões de download são apenas uma simulação.", "muted", "panel2", 9, "normal", wraplength=900).pack(anchor="w", pady=(0, 14))
        self.label(inside, "LINK DE MÍDIA", "muted", "panel2", 8, "bold").pack(anchor="w", pady=(0, 5))
        url = RoundedField(inside, self, width=500)
        url.pack(fill="x")
        url.entry.insert(0, "https://exemplo.com/video-ou-playlist")
        url.entry.bind("<FocusIn>", lambda _event: self.toast("Entrada de exemplo — o protótipo não acessa este link."))
        controls = self.frame(inside, "panel2")
        controls.pack(fill="x", pady=(14, 0))
        select_row = self.frame(controls, "panel2")
        select_row.pack(fill="x")
        modes = self.frame(select_row, "panel2")
        modes.pack(side="left", fill="x", expand=True)
        self.label(modes, "FORMATO", "muted", "panel2", 8, "bold").pack(anchor="w", pady=(0, 5))
        Dropdown(
            modes, self, ["Automático — vídeo", "Vídeo", "Música — MP3"],
            "Automático — vídeo", width=220,
        ).pack(anchor="w")
        qualities = self.frame(select_row, "panel2")
        qualities.pack(side="left", fill="x", expand=True, padx=(14, 0))
        self.label(qualities, "QUALIDADE", "muted", "panel2", 8, "bold").pack(anchor="w", pady=(0, 5))
        Dropdown(
            qualities, self, ["720p", "1080p", "1440p", "2160p / 4K", "192 kbps", "320 kbps"],
            "1080p", width=180,
        ).pack(anchor="w")
        actions = self.frame(controls, "panel2")
        actions.pack(fill="x", pady=(12, 0))
        self.button(
            actions, "↓  Baixar agora", lambda: self._mock_action("Download"),
            "primary", width=150,
        ).pack(side="right")
        self.button(
            actions, "Analisar playlist", lambda: self._mock_action("Analisar playlist"),
            "secondary", width=140,
        ).pack(side="right", padx=(0, 8))

        progress = self.card(body, padding=16)
        progress.pack(fill="x", pady=(0, 12))
        header = self.frame(progress.body, "panel")
        header.pack(fill="x")
        self.label(header, "Sessão de demonstração", "fg", "panel", 12, "bold").pack(side="left")
        self.label(header, "28%", "accent2", "panel", 11, "bold").pack(side="right")
        meter_bg = tk.Canvas(progress.body, height=10, bg=self.colors["panel"], highlightthickness=0, bd=0)
        meter_bg.pack(fill="x", pady=(12, 14))
        def draw_demo_meter(_event=None):
            width = max(1, meter_bg.winfo_width())
            meter_bg.delete("all")
            meter_bg.create_polygon(
                *rounded_points(0, 0, width, 10, 5),
                fill=self.colors["surface"], outline="",
            )
            meter_bg.create_polygon(
                *rounded_points(0, 0, width * 0.28, 10, 5),
                fill=self.colors["accent"], outline="",
            )
        meter_bg.bind("<Configure>", draw_demo_meter, add="+")
        meter_bg.after_idle(draw_demo_meter)
        self.label(progress.body, "STATUS", "muted", "panel", 8, "bold").pack(anchor="w")
        stats = self.frame(progress.body, "panel")
        stats.pack(fill="x", pady=(8, 0))
        for title, value in (("STATUS", "Aguardando"), ("VELOCIDADE", "—"), ("TAMANHO", "—"), ("TEMPO RESTANTE", "—"), ("ETAPA", "Prévia de interface")):
            metric = self.card(stats, background_key="surface", padding=11)
            metric.pack(side="left", fill="both", expand=True, padx=(0, 8))
            self.label(metric.body, title, "muted", "surface", 7, "bold").pack(anchor="w")
            self.label(metric.body, value, "fg", "surface", 10, "bold").pack(anchor="w", pady=(5, 0))

        recent = self.card(body, padding=15)
        recent.pack(fill="x", pady=(0, 10))
        row = self.frame(recent.body, "panel")
        row.pack(fill="x")
        self.label(row, "Atividade recente", "fg", "panel", 12, "bold").pack(side="left")
        self.button(row, "Limpar", lambda: self._mock_action("Limpar atividade"), "secondary", width=90).pack(side="right")
        for name, details, status in (
            ("Interface iniciada", "Nenhuma rede ou processo de download foi utilizado.", "PRONTO"),
            ("Dependências", "Valores ilustrativos para avaliar cartões de estado.", "SIMULADO"),
        ):
            item = self.frame(recent.body, "panel2", padx=12, pady=10)
            item.pack(fill="x", pady=(9, 0))
            self.label(item, name, "fg", "panel2", 10, "bold").pack(side="left")
            self.label(item, details, "muted", "panel2", 9, "normal").pack(side="left", padx=(12, 8), fill="x", expand=True)
            self.label(item, status, "accent2", "panel2", 8, "bold").pack(side="right")

    def _build_playlist(self, body):
        self._title_block(body, "Biblioteca", "Central de playlists", "A estrutura da página original foi preservada como maquete. Seleção e pesquisa são locais e não iniciam downloads.")
        intro = self.card(body, padding=16)
        intro.pack(fill="x", pady=(0, 12))
        top = self.frame(intro.body, "panel")
        top.pack(fill="x")
        self.label(top, "Itens detectados na amostra", "fg", "panel", 12, "bold").pack(side="left")
        self.label(top, "3 itens  ·  2 selecionados", "accent2", "panel", 9, "bold").pack(side="right")
        self.label(intro.body, "Escolha o que entraria na fila. Botões de processamento estão desativados como operações reais.", "muted", "panel", 9, "normal").pack(anchor="w", pady=(8, 0))
        toolbar = self.card(body, padding=10)
        toolbar.pack(fill="x", pady=(0, 12))
        self.label(toolbar.body, "Buscar itens", "muted", "panel", 8, "bold").pack(anchor="w", pady=(0, 5))
        search = RoundedField(toolbar.body, self, width=400)
        search.pack(fill="x")
        search.entry.insert(0, "")
        self.button(toolbar.body, "Marcar visíveis", lambda: self._mock_action("Marcar visíveis"), "secondary", width=130).pack(side="left", pady=(10, 0), padx=(0, 8))
        self.button(toolbar.body, "Desmarcar visíveis", lambda: self._mock_action("Desmarcar visíveis"), "secondary", width=145).pack(side="left", pady=(10, 0))

        table = self.card(body, padding=12)
        table.pack(fill="x", pady=(0, 12))
        self.label(table.body, "Fila de exemplo", "fg", "panel", 12, "bold").pack(anchor="w", pady=(0, 8))
        columns = self.frame(table.body, "panel2", padx=10, pady=10)
        columns.pack(fill="x")
        for text in ("OK", "TÍTULO", "DURAÇÃO", "FORMATO", "QUALIDADE", "ESTADO"):
            self.label(columns, text, "muted", "panel2", 7, "bold").pack(side="left", padx=(4, 12))
        self._divider(table.body, "panel")
        sample_rows = [
            ("☑", "Aurora — paisagem", "04:32", "Vídeo", "1080p", "Disponível"),
            ("☑", "Noite orbital", "03:18", "MP3", "192 kbps", "Disponível"),
            ("□", "Sinal distante", "05:11", "Vídeo", "720p", "Ignorado"),
        ]
        for idx, row_data in enumerate(sample_rows):
            row = self.frame(table.body, "panel")
            row.pack(fill="x", pady=2)
            values = list(row_data)
            for index, value in enumerate(values):
                fg = "accent2" if index == 0 else ("fg" if index == 1 else "muted")
                self.label(row, value, fg, "panel", 9, "bold" if index in (0, 1) else "normal").pack(side="left", padx=(4, 12), pady=10)
        footer = self.frame(table.body, "panel")
        footer.pack(fill="x", pady=(8, 0))
        self.label(footer, "2 itens selecionados", "muted", "panel", 9, "normal").pack(side="left")
        self.button(footer, "↓  Baixar itens marcados", lambda: self._mock_action("Baixar itens marcados"), "primary", width=205).pack(side="right")

        editor = self.card(body, padding=14)
        editor.pack(fill="x")
        self.label(editor.body, "Opções do item selecionado", "fg", "panel", 12, "bold").pack(anchor="w")
        self.label(editor.body, "Formato, qualidade e inclusão seriam ajustáveis aqui na versão funcional.", "muted", "panel", 9, "normal").pack(anchor="w", pady=(5, 10))
        opts = self.frame(editor.body, "panel")
        opts.pack(fill="x")
        Dropdown(opts, self, ["Vídeo", "Música — MP3"], "Vídeo", width=190).pack(side="left", padx=(0, 10))
        Dropdown(opts, self, ["720p", "1080p", "1440p", "2160p / 4K"], "1080p", width=180).pack(side="left")
        self.button(opts, "Aplicar opções", lambda: self._mock_action("Aplicar opções"), "secondary", width=135).pack(side="right")

    def _build_settings(self, body):
        self._title_block(body, "Personalização", "Aparência e preferências", "Estas configurações funcionam no UI-debug e são salvas em uma pasta própria, separada das preferências do aplicativo real.")
        appearance = self.card(body, padding=18)
        appearance.pack(fill="x", pady=(0, 12))
        self.label(appearance.body, "Tema do espaço", "fg", "panel", 13, "bold").pack(anchor="w")
        self.label(appearance.body, "Alterna entre um espaço profundo, uma versão clara e um tema OLED.", "muted", "panel", 9).pack(anchor="w", pady=(4, 12))
        theme_row = self.frame(appearance.body, "panel")
        theme_row.pack(fill="x")
        self.theme_buttons = {}
        for theme, text in (("dark", "Escuro"), ("light", "Claro"), ("oled", "OLED")):
            btn = self.button(theme_row, text, lambda value=theme: self._set_theme(value), "secondary", width=116)
            btn.pack(side="left", padx=(0, 8))
            self.theme_buttons[theme] = btn

        accent = self.card(body, padding=18)
        accent.pack(fill="x", pady=(0, 12))
        self.label(accent.body, "Gradiente de destaque", "fg", "panel", 13, "bold").pack(anchor="w")
        self.label(accent.body, "A cor principal e a secundária são usadas em botões e estados selecionados.", "muted", "panel", 9).pack(anchor="w", pady=(4, 13))
        self.accent_swatches = self.frame(accent.body, "panel")
        self.accent_swatches.pack(fill="x")
        swatches = [
            ("Nebulosa", "#7C5CFF", "#20D8E7"),
            ("Aurora", "#4D6FFF", "#57E6B1"),
            ("Supernova", "#F05CC5", "#7C5CFF"),
            ("Pulso solar", "#FB923C", "#F472B6"),
        ]
        for title, first, second in swatches:
            holder = self.frame(self.accent_swatches, "panel")
            holder.pack(side="left", padx=(0, 10))
            swatch = tk.Canvas(holder, width=105, height=32, bg=self.colors["panel"], bd=0, highlightthickness=0, cursor="hand2")
            swatch.pack()
            for step in range(40):
                x0 = step * 105 / 40
                x1 = (step + 1) * 105 / 40 + 1
                swatch.create_rectangle(x0, 0, x1, 32, fill=blend_hex(first, second, step / 39), outline="")
            swatch.create_polygon(*rounded_points(1, 1, 104, 31, 10), fill="", outline=self.colors["border"], width=1.5)
            swatch.bind("<Button-1>", lambda _event, a=first, b=second: self._set_accent(a, b))
            self.label(holder, title, "muted", "panel", 8, "normal").pack(anchor="center", pady=(5, 0))
        custom_row = self.frame(accent.body, "panel")
        custom_row.pack(fill="x", pady=(14, 0))
        self.button(custom_row, "Escolher cor principal…", self._choose_primary_accent, "secondary", width=185).pack(side="left", padx=(0, 8))
        self.button(custom_row, "Escolher cor secundária…", self._choose_secondary_accent, "secondary", width=195).pack(side="left")
        self.accent_preview = tk.Canvas(accent.body, height=14, bg=self.colors["panel"], bd=0, highlightthickness=0)
        self.accent_preview.pack(fill="x", pady=(14, 0))

        preferences = self.card(body, padding=18)
        preferences.pack(fill="x", pady=(0, 12))
        self.label(preferences.body, "Preferências de interface", "fg", "panel", 13, "bold").pack(anchor="w", pady=(0, 12))
        self.density_var = tk.StringVar(value=self.settings["ui_density"])
        density_row = self.frame(preferences.body, "panel")
        density_row.pack(fill="x", pady=5)
        self.label(density_row, "Densidade", "fg", "panel", 10, "normal").pack(side="left")
        self.density_combo = Dropdown(density_row, self, ["Confortável", "Compacta"], "Confortável" if self.settings["ui_density"] == "comfortable" else "Compacta", command=self._set_density, width=160)
        self.density_combo.pack(side="right")
        self.anim_var = tk.BooleanVar(value=bool(self.settings["animations_enabled"]))
        self.motion_var = tk.BooleanVar(value=bool(self.settings["reduce_motion"]))
        self.update_check_var = tk.BooleanVar(value=bool(self.settings["update_check_on_startup"]))
        for title, desc, var, command in (
            ("Animações sutis", "Somente estados locais de hover; sem transição da janela inteira.", self.anim_var, self._set_animation_pref),
            ("Reduzir movimento", "Evita mudanças animadas e prioriza estabilidade visual.", self.motion_var, self._set_motion_pref),
            ("Verificar atualizações ao iniciar", "Consulta o manifesto desta branch de desenvolvimento.", self.update_check_var, self._set_update_pref),
        ):
            row = self.frame(preferences.body, "panel")
            row.pack(fill="x", pady=8)
            box = self.frame(row, "panel")
            box.pack(side="left", fill="x", expand=True)
            self.label(box, title, "fg", "panel", 10, "bold").pack(anchor="w")
            self.label(box, desc, "muted", "panel", 8).pack(anchor="w", pady=(3, 0))
            toggle = ToggleSwitch(row, self, var, command)
            toggle.pack(side="right", padx=(12, 0))
            self.toggles.append(toggle)
        buttons = self.frame(preferences.body, "panel")
        buttons.pack(fill="x", pady=(14, 0))
        self.button(buttons, "Restaurar padrão", self._load_settings_defaults, "secondary", width=150).pack(side="left")
        self.button(buttons, "Salvar preferências", self.save_settings, "primary", width=165).pack(side="right")

        self._set_density(self.density_combo.get(), notify=False)
        self._draw_accent_preview()

    def _build_dependencies(self, body):
        self._title_block(body, "Ferramentas locais", "Dependências", "Prévia de cartões e estados. Esta versão não baixa, instala nem executa dependências.")
        for name, description, state, status in (
            ("yt-dlp", "Análise de formatos e fontes de mídia", "Aguardando integração", "MOCK"),
            ("FFmpeg", "Conversão, áudio, contêineres e metadados", "Não verificado nesta demo", "MOCK"),
            ("FFprobe", "Leitura de informações dos arquivos", "Não verificado nesta demo", "MOCK"),
        ):
            card = self.card(body, padding=18)
            card.pack(fill="x", pady=(0, 10))
            row = self.frame(card.body, "panel")
            row.pack(fill="x")
            icon = self.label(row, "◈", "accent2", "panel", 18, "bold")
            icon.pack(side="left", padx=(0, 12))
            text_box = self.frame(row, "panel")
            text_box.pack(side="left", fill="x", expand=True)
            self.label(text_box, name, "fg", "panel", 12, "bold").pack(anchor="w")
            self.label(text_box, description, "muted", "panel", 9).pack(anchor="w", pady=(4, 0))
            self.label(row, status, "accent2", "panel", 8, "bold").pack(side="right")
            self.label(card.body, state, "muted", "panel", 9).pack(anchor="w", pady=(12, 0))
            self.button(card.body, "Configurar…", lambda value=name: self._mock_action("Configurar " + value), "secondary", width=120).pack(anchor="e", pady=(8, 0))

    def _build_updates(self, body):
        self._title_block(body, "Canal independente", "Atualizações do UI-debug", "O protótipo tem versão e atualizador próprios. Ele consulta a branch ui-debug, nunca a versão publicada do downloader.")
        card = self.card(body, background_key="panel2", padding=22)
        card.pack(fill="x", pady=(0, 12))
        row = self.frame(card.body, "panel2")
        row.pack(fill="x")
        self.label(row, "UI-debug", "fg", "panel2", 18, "bold").pack(side="left")
        self.label(row, "DESENVOLVIMENTO  •  SEM RELEASE", "accent2", "panel2", 8, "bold").pack(side="right")
        self.label(card.body, "Versão instalada: " + APP_VERSION, "muted", "panel2", 10).pack(anchor="w", pady=(12, 5))
        self.label(card.body, "Fonte de atualização: branch " + UPDATE_BRANCH, "muted", "panel2", 9).pack(anchor="w")
        self.update_status_label = self.label(card.body, "Última verificação: ainda não consultada", "muted", "panel2", 9, wraplength=850)
        self.update_status_label.pack(anchor="w", pady=(12, 12))
        row_buttons = self.frame(card.body, "panel2")
        row_buttons.pack(fill="x")
        self.button(row_buttons, "Verificar agora", lambda: self.check_update_async(user_initiated=True), "primary", width=150).pack(side="left")
        self.install_update_button = self.button(row_buttons, "Instalar versão de desenvolvimento", self._install_update_if_available, "secondary", width=250)
        self.install_update_button.pack(side="left", padx=(10, 0))
        self.label(body, "Não será criada uma Release do GitHub. O código ficará em uma branch/PR para revisão visual.", "muted", "bg", 9, wraplength=900).pack(anchor="w", pady=(0, 14))
        note = self.card(body, padding=16)
        note.pack(fill="x")
        self.label(note.body, "Política de atualização", "fg", "panel", 12, "bold").pack(anchor="w")
        for text in (
            "Somente HTTPS e hosts GitHub explicitamente permitidos.",
            "Tamanho máximo e validação de caminhos do ZIP antes de substituir arquivos.",
            "Backup temporário e tentativa de rollback em caso de erro.",
            "As configurações ficam em MediaDownloader-UI-debug e não são alteradas pela atualização.",
        ):
            self.label(note.body, "•  " + text, "muted", "panel", 9, wraplength=900).pack(anchor="w", pady=(8, 0))

    def _build_help(self, body):
        self._title_block(body, "Referência", "Ajuda e escopo", "A organização segue a navegação atual do projeto, com um visual espacial mais limpo e simplificado.")
        groups = [
            ("O que está ativo?", "Navegação entre páginas, configurações visuais, salvar preferências e verificar/instalar atualizações deste protótipo."),
            ("O que está desativado?", "Downloads, análise real de playlists, execução de yt-dlp/FFmpeg, instalação de dependências e reparação da instalação real."),
            ("Como enviar feedback?", "Abra a aba que deseja revisar, tire uma captura de tela e diga o que quer ajustar. Ícones animados finais serão adicionados somente após aprovação."),
            ("O que acontece com o aplicativo atual?", "Nada nesta versão: usa outro diretório de configurações e não importa ou executa módulos da pasta app do projeto real."),
        ]
        for title, text in groups:
            card = self.card(body, padding=18)
            card.pack(fill="x", pady=(0, 10))
            self.label(card.body, title, "fg", "panel", 12, "bold").pack(anchor="w")
            self.label(card.body, text, "muted", "panel", 9, wraplength=920).pack(anchor="w", pady=(7, 0))
        foot = self.card(body, background_key="panel2", padding=16)
        foot.pack(fill="x", pady=(0, 12))
        self.label(foot.body, "Observação: os links share.google enviados não puderam ser abertos diretamente neste ambiente; esta primeira proposta usa a organização do aplicativo atual e referências públicas do SKlauncher 4.0.", "muted", "panel2", 9, wraplength=900).pack(anchor="w")

    def _build_diagnostics(self, body):
        self._title_block(body, "Somente leitura", "Diagnóstico do UI-debug", "As informações abaixo pertencem ao protótipo e não leem o estado do downloader real.")
        info = [
            ("Aplicativo", APP_NAME),
            ("Versão independente", APP_VERSION),
            ("Canal", CHANNEL),
            ("Branch de atualização", UPDATE_BRANCH),
            ("Python", platform.python_version()),
            ("Sistema", platform.platform()),
            ("Pasta do protótipo", str(self.app_dir)),
            ("Preferências separadas", str(self.settings_path)),
        ]
        card = self.card(body, padding=18)
        card.pack(fill="x", pady=(0, 12))
        for title, value in info:
            row = self.frame(card.body, "panel")
            row.pack(fill="x", pady=6)
            self.label(row, title, "muted", "panel", 9, "normal").pack(side="left", padx=(0, 20))
            self.label(row, value, "fg", "panel", 9, "bold", wraplength=620).pack(side="right", anchor="e")
            self._divider(card.body, "panel")
        self.button(card.body, "Abrir página de Atualizações", lambda: self.show_page("updates"), "secondary", width=210).pack(anchor="e", pady=(10, 0))

    def show_page(self, name):
        if name not in self.page_frames:
            return
        # No whole-window slide/fade. Swapping already-built pages avoids the flash
        # caused by repeatedly placing, lifting and repacking entire Tk containers.
        for key, frame in self.page_frames.items():
            if key == name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        self.current_page = name
        names = {
            "home": ("Início", "Painel principal / demonstração"),
            "playlist": ("Playlists", "Biblioteca / demonstração"),
            "settings": ("Aparência", "Preferências locais do UI-debug"),
            "dependencies": ("Dependências", "Estados ilustrativos"),
            "updates": ("Atualizações", "Canal independente de desenvolvimento"),
            "help": ("Ajuda", "Como revisar esta proposta"),
            "diagnostics": ("Diagnóstico", "Informações do protótipo"),
        }
        title, subtitle = names[name]
        self.page_title_label.configure(text=title)
        for key, (nav, shape, icon, label_id) in self.nav_items.items():
            active = key == name
            c = self.colors
            nav.itemconfigure(shape, fill=blend_hex(c["accent"], c["accent2"], 0.20) if active else c["panel"], outline=c["border"] if active else "")
            nav.itemconfigure(icon, fill=c["accent2"] if active else c["muted"])
            nav.itemconfigure(label_id, fill=c["fg"] if active else c["muted"], font=("Segoe UI", 10, "bold" if active else "normal"))
        if name == "settings":
            self._sync_settings_controls()
        self.toast_label.configure(text=subtitle)

    def _nav_hover(self, name, hovered):
        if name == self.current_page:
            return
        nav, shape, icon, _label = self.nav_items[name]
        color = self.colors["surface"] if hovered else self.colors["panel"]
        nav.itemconfigure(shape, fill=color)

    def _set_theme(self, theme):
        if theme not in PALETTES:
            return
        self.settings["theme"] = theme
        self.apply_theme()
        self.toast("Tema aplicado. Salve as preferências para mantê-lo.")

    def _set_accent(self, first, second):
        self.settings["accent_color"] = first.upper()
        self.settings["accent_color_2"] = second.upper()
        self.apply_theme()
        self._draw_accent_preview()
        self.toast("Gradiente de destaque atualizado.")

    def _choose_primary_accent(self):
        color = colorchooser.askcolor(color=self.settings["accent_color"], parent=self.root, title="Cor principal")
        if color and color[1]:
            self._set_accent(color[1], self.settings["accent_color_2"])

    def _choose_secondary_accent(self):
        color = colorchooser.askcolor(color=self.settings["accent_color_2"], parent=self.root, title="Cor secundária")
        if color and color[1]:
            self._set_accent(self.settings["accent_color"], color[1])

    def _set_density(self, value, notify=True):
        self.settings["ui_density"] = "compact" if str(value).lower().startswith("compact") else "comfortable"
        if hasattr(self, "density_combo") and self.density_combo.get() != ("Compacta" if self.settings["ui_density"] == "compact" else "Confortável"):
            self.density_combo.set("Compacta" if self.settings["ui_density"] == "compact" else "Confortável")
        if hasattr(self, "shell"):
            # Density is intentionally a mild spacing preset, not a full-window animation.
            self.shell.configure(padx=12 if self.settings["ui_density"] == "compact" else 18, pady=11 if self.settings["ui_density"] == "compact" else 16)
        if notify:
            self.toast("Densidade atualizada. Salve para manter a escolha.")

    def _set_animation_pref(self):
        self.settings["animations_enabled"] = bool(self.anim_var.get())
        for toggle in self.toggles:
            toggle.refresh_theme()
        self.toast("Animações sutis " + ("ativadas." if self.settings["animations_enabled"] else "desativadas."))

    def _set_motion_pref(self):
        self.settings["reduce_motion"] = bool(self.motion_var.get())
        if self.settings["reduce_motion"]:
            self.settings["animations_enabled"] = False
            self.anim_var.set(False)
        for toggle in self.toggles:
            toggle.refresh_theme()
        self.toast("Preferência de movimento atualizada.")

    def _set_update_pref(self):
        self.settings["update_check_on_startup"] = bool(self.update_check_var.get())
        self.toast("Verificação automática " + ("ativada." if self.settings["update_check_on_startup"] else "desativada."))

    def _sync_settings_controls(self):
        if not hasattr(self, "density_combo"):
            return
        self.density_combo.set("Compacta" if self.settings["ui_density"] == "compact" else "Confortável")
        for toggle in self.toggles:
            toggle.refresh_theme()

    def _draw_accent_preview(self):
        if not hasattr(self, "accent_preview"):
            return
        self.accent_preview.delete("gradient")
        width = max(1, self.accent_preview.winfo_width())
        for index in range(60):
            x0, x1 = width * index / 60, width * (index + 1) / 60 + 1
            self.accent_preview.create_rectangle(x0, 0, x1, 14, fill=blend_hex(self.settings["accent_color"], self.settings["accent_color_2"], index / 59), outline="", tags="gradient")
        self.accent_preview.create_polygon(*rounded_points(1, 1, width - 1, 13, 6), fill="", outline=self.colors["border"], width=1.5)
        self.accent_preview.tag_raise("gradient")

    def _apply_scrollbar_style(self):
        """Use the same muted dark surface and accent as the rest of the prototype."""
        c = self.colors
        try:
            self.style.configure(
                "UI.Vertical.TScrollbar",
                gripcount=0,
                background=c["panel2"],
                darkcolor=c["panel2"],
                lightcolor=c["panel2"],
                troughcolor=c["bg"],
                bordercolor=c["border"],
                arrowcolor=c["accent2"],
                relief="flat",
                width=9,
            )
            self.style.map(
                "UI.Vertical.TScrollbar",
                background=[("active", c["accent"]), ("!disabled", c["panel2"])],
                arrowcolor=[("active", c["accent2"])],
            )
        except tk.TclError:
            pass

    def apply_theme(self, refresh=True):
        old_colors = dict(self.colors or PALETTES["dark"])
        c = dict(PALETTES.get(self.settings.get("theme"), PALETTES["dark"]))
        c["accent"] = self.settings.get("accent_color", DEFAULT_SETTINGS["accent_color"])
        c["accent2"] = self.settings.get("accent_color_2", DEFAULT_SETTINGS["accent_color_2"])

        # Recolor existing widgets in place instead of destroying/rebuilding the view.
        # This avoids the full-window flash when theme settings change.
        def recolor_tree(widget):
            for child in widget.winfo_children():
                try:
                    old_bg = str(child.cget("bg")).lower()
                    explicit_key = getattr(child, "_ui_bg_key", None)
                    old_key = explicit_key or next(
                        (key for key, value in old_colors.items() if str(value).lower() == old_bg),
                        None,
                    )
                    if old_key in c:
                        child.configure(bg=c[old_key])
                except (tk.TclError, TypeError):
                    pass
                recolor_tree(child)

        if hasattr(self, "shell"):
            recolor_tree(self.shell)
        self.colors = c
        self._apply_scrollbar_style()
        self.root.configure(bg=c["bg"])
        if hasattr(self, "shell"):
            self.shell.configure(bg=c["bg"])
        if hasattr(self, "main"):
            self.main.configure(bg=c["bg"])
        for widget, fg_key, bg_key, font in self.labels:
            try:
                widget.configure(bg=c.get(bg_key, c["panel"]), fg=c.get(fg_key, c["fg"]), font=font)
            except tk.TclError:
                pass
        for card in self.cards:
            card.refresh_theme()
        for field in self.fields:
            field.refresh_theme()
        for dropdown in self.dropdowns:
            dropdown.refresh_theme()
        for button in self.buttons:
            button.refresh_theme()
        for toggle in self.toggles:
            toggle.refresh_theme()
        for mark in self.orbital_marks:
            mark.refresh_theme()
        for pane in self.scroll_panes:
            pane.refresh_theme()
        try:
            self.backdrop._resize(None)
        except (AttributeError, tk.TclError):
            pass
        if hasattr(self, "nav_items"):
            for key, (nav, shape, icon, label_id) in self.nav_items.items():
                active = key == self.current_page
                nav.configure(bg=c["panel"])
                nav.itemconfigure(shape, fill=blend_hex(c["accent"], c["accent2"], 0.20) if active else c["panel"], outline=c["border"] if active else "")
                nav.itemconfigure(icon, fill=c["accent2"] if active else c["muted"])
                nav.itemconfigure(label_id, fill=c["fg"] if active else c["muted"])
        if hasattr(self, "accent_preview"):
            self._draw_accent_preview()
        self.style.configure("TCombobox", fieldbackground=c["field"], background=c["panel"], foreground=c["fg"], arrowcolor=c["accent2"])
        if refresh and hasattr(self, "page_frames"):
            self._sync_settings_controls()

    def toast(self, text):
        try:
            self.toast_label.configure(text=text)
            if self.toast_after is not None:
                self.root.after_cancel(self.toast_after)
            self.toast_after = self.root.after(4300, lambda: self.toast_label.configure(text=""))
        except tk.TclError:
            pass

    def check_update_async(self, user_initiated=False):
        if self._update_busy:
            self.toast("Já existe uma verificação em andamento.")
            return
        self._update_busy = True
        if hasattr(self, "update_status_label"):
            self.update_status_label.configure(text="Consultando o manifesto da branch ui-debug…")
        self.toast("Verificando atualizações do canal de desenvolvimento…")
        if user_initiated and self.splash is None:
            self.splash = CosmicSplash(self.root, mode="update", looping=True)

        def worker():
            try:
                info = fetch_latest_version()
                error = None
            except Exception as exc:
                info, error = None, str(exc)
            def done():
                latest = str((info or {}).get("version", ""))
                newer = bool(info) and version_key(latest) > version_key(APP_VERSION)
                final_message = ("Não foi possível verificar a atualização" if error else
                    ("Nova versão disponível — pronta para sua confirmação" if newer else
                     "Seu UI-debug já está na versão mais recente"))
                def apply_result():
                    self._update_busy = False
                    if error:
                        text = "Não foi possível consultar a branch: " + error
                        if hasattr(self, "update_status_label"):
                            self.update_status_label.configure(text=text)
                        if user_initiated:
                            self.toast("Falha ao verificar atualização. Confira a conexão.")
                        return
                    self.update_info = info
                    if hasattr(self, "update_status_label"):
                        if newer:
                            self.update_status_label.configure(text="Nova versão disponível: " + latest + ". A instalação só começa após sua confirmação.")
                        else:
                            self.update_status_label.configure(text="Você já está na versão de desenvolvimento mais recente consultada: " + latest)
                    self.toast("Há uma atualização do UI-debug." if newer else "UI-debug consultado; nenhuma versão mais nova encontrada.")
                splash = self.splash if user_initiated else None
                if splash is not None:
                    splash.finish(final_message, callback=lambda: self._finish_splash_then(apply_result, splash))
                else:
                    apply_result()
            try: self.root.after(0, done)
            except tk.TclError: pass
        threading.Thread(target=worker, name="ui-debug-update-check", daemon=True).start()

    def _finish_splash_then(self, callback, splash):
        if self.splash is splash:
            self.splash = None
        callback()

    def _install_update_if_available(self):
        if not self.update_info:
            self.toast("Verifique primeiro se há uma versão mais recente.")
            return
        latest = str(self.update_info.get("version", ""))
        if version_key(latest) <= version_key(APP_VERSION):
            self.toast("Nenhuma atualização mais recente foi encontrada.")
            return
        if messagebox.askyesno(
            "Atualizar UI-debug",
            "Instalar a versão de desenvolvimento " + latest + "?\n\n"
            "Somente a pasta UI-debug será atualizada. As preferências locais serão preservadas.",
            parent=self.root,
        ):
            self.install_update_async()

    def install_update_async(self):
        if not self.update_info:
            self._install_update_if_available()
            return
        latest = str(self.update_info.get("version", ""))
        if version_key(latest) <= version_key(APP_VERSION):
            self.toast("Nenhuma atualização para instalar.")
            return
        self._update_busy = True
        if hasattr(self, "update_status_label"):
            self.update_status_label.configure(text="Baixando e validando o pacote de desenvolvimento…")
        if self.splash is None:
            self.splash = CosmicSplash(self.root, mode="update", looping=True)

        def worker():
            try:
                payload = read_update_bytes(ARCHIVE_URL, MAX_ARCHIVE_BYTES)
                try:
                    self.root.after(0, lambda: self.splash.set_stage("Pacote recebido — validando os arquivos com segurança") if self.splash else None)
                except tk.TclError:
                    pass
                install_self_update(self.app_dir, payload)
                error = None
            except Exception as exc:
                error = str(exc)
            def done():
                def finish_install():
                    self._update_busy = False
                    if error:
                        self.toast("Atualização cancelada: " + error)
                        if hasattr(self, "update_status_label"):
                            self.update_status_label.configure(text="Atualização não instalada: " + error)
                        return
                    if hasattr(self, "update_status_label"):
                        self.update_status_label.configure(text="Arquivos atualizados com segurança. Reinicie para carregar a nova versão.")
                    if messagebox.askyesno(
                        "Atualização preparada",
                        "Os arquivos foram atualizados. Reiniciar agora para carregar a nova versão?",
                        parent=self.root,
                    ):
                        try:
                            subprocess.Popen([sys.executable, str(self.app_dir / "ui_debug.py")], cwd=str(self.app_dir))
                            self.root.destroy()
                        except OSError as exc:
                            self.toast("Atualizado, mas não foi possível reiniciar automaticamente: " + str(exc))
                    else:
                        self.toast("Atualização instalada. Feche e abra o UI-debug para usar a versão nova.")
                splash = self.splash
                if splash is not None:
                    splash.finish("Atualização interrompida com segurança" if error else
                        "Nova órbita pronta — atualização preparada",
                        callback=lambda: self._finish_splash_then(finish_install, splash))
                else:
                    finish_install()
            try: self.root.after(0, done)
            except tk.TclError: pass
        threading.Thread(target=worker, name="ui-debug-update-install", daemon=True).start()

    def close(self):
        self._stop.set()
        if self.splash is not None:
            self.splash.close()
            self.splash = None
        for mark in getattr(self, "orbital_marks", []):
            try: mark.destroy()
            except tk.TclError: pass
        self.root.destroy()


class ScrollPane(tk.Frame):
    """Scrollable container that handles wheel events only while the pointer is inside it."""
    def __init__(self, master, app):
        super().__init__(master, bg=app.colors["bg"], bd=0, highlightthickness=0)
        self.app = app
        self.canvas = tk.Canvas(self, bg=app.colors["bg"], bd=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview,
            style="UI.Vertical.TScrollbar",
        )
        self.body = tk.Frame(self.canvas, bg=app.colors["bg"], bd=0, highlightthickness=0)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.body.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.window, width=event.width))
        # Global bindings are scoped by _event_inside, so hidden pages and other
        # panels never consume the same wheel event.
        self.bind_all("<MouseWheel>", self._wheel_global, add="+")
        self.bind_all("<Button-4>", self._wheel_global, add="+")
        self.bind_all("<Button-5>", self._wheel_global, add="+")
        self._scroll_body_bg = app.colors["bg"]
        self.app.scroll_panes.append(self)

    def _event_inside(self, event):
        widget = getattr(event, "widget", None)
        while widget is not None:
            if widget is self.body or widget is self.canvas or widget is self.scrollbar:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _wheel(self, event):
        if not self._event_inside(event):
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

    def refresh_theme(self):
        self.configure(bg=self.app.colors["bg"])
        self.canvas.configure(bg=self.app.colors["bg"])
        self.body.configure(bg=self.app.colors["bg"])


def run():
    root = tk.Tk()
    SpaceUIPrototype(root)
    root.mainloop()


if __name__ == "__main__":
    run()
