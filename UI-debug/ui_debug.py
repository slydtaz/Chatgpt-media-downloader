from __future__ import annotations

"""Standalone visual prototype for ChatGPT Media Downloader.

UI-debug intentionally has no dependency on the production app package.
Downloads, playlist processing, dependency installation and repair are mocked.
Only theme/preferences persistence and this prototype's own update checker work.
"""

import base64
import concurrent.futures
import html
import ipaddress
import io
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
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
import tkinter.font as tkfont


APP_NAME = "ChatGPT Media Downloader — UI-debug"
APP_VERSION = "0.1.0-dev.7"
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
    "accent_color": "#895CFA",
    "accent_color_2": "#558FF4",
    "visual_preset_version": 2,
    "ui_density": "comfortable",
    "animations_enabled": True,
    "reduce_motion": False,
    "update_check_on_startup": True,
}

PALETTES = {
    "dark": {
        "bg": "#080711", "panel": "#100E20", "panel2": "#17132A",
        "surface": "#201A36", "field": "#0C0B19", "fg": "#F4F2FF",
        "muted": "#A6A0C3", "border": "#3B3157", "accent": "#986BFA",
        "accent2": "#6EA2FA", "good": "#5BF0A5", "warn": "#F6C66A",
        "bad": "#FF7C97", "button": "#1B1730", "input_fg": "#F4F2FF",
    },
    "light": {
        "bg": "#F2F5FF", "panel": "#FFFFFF", "panel2": "#E7EDFF",
        "surface": "#F8FAFF", "field": "#FFFFFF", "fg": "#1B2442",
        "muted": "#647293", "border": "#D6DDF1", "accent": "#6248DB",
        "accent2": "#287FD0", "good": "#187F67", "warn": "#9A6500",
        "bad": "#B93658", "button": "#E7EBF8", "input_fg": "#1B2442",
    },
    "oled": {
        "bg": "#03050B", "panel": "#080D18", "panel2": "#0D1628",
        "surface": "#101B2F", "field": "#050912", "fg": "#F7FAFF",
        "muted": "#8999BA", "border": "#1C2A45", "accent": "#906CFA",
        "accent2": "#548FF5", "good": "#51D6A5", "warn": "#FFD166",
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


def render_nav_icon_image(key: str, tint: str, accent: str, *, scale: float = 1.18, master=None):
    """Supersample the tiny navigation icons and downsample with Lanczos for smooth edges."""
    try:
        from PIL import Image, ImageDraw, ImageTk
    except ImportError:
        return None
    size = max(24, min(48, int(round(26 * scale))))
    factor = 4
    image = Image.new("RGBA", (size*factor, size*factor), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    center = size * factor / 2
    unit = size * factor / 24.0
    stroke = max(6, int(round(size * factor * .085)))
    fine = max(4, int(round(stroke * .72)))
    def point(x, y):
        return (center + x * unit, center + y * unit)
    def line(*coords, color=tint, width=stroke):
        draw.line([point(x,y) for x,y in zip(coords[0::2],coords[1::2])],
                  fill=color, width=width, joint="curve")
    def outline_ellipse(x1,y1,x2,y2,color=tint,width=stroke):
        a,b=point(x1,y1); c,d=point(x2,y2)
        draw.ellipse((a,b,c,d),outline=color,width=width)
    def filled_ellipse(x1,y1,x2,y2,color=accent):
        a,b=point(x1,y1); c,d=point(x2,y2)
        draw.ellipse((a,b,c,d),fill=color)
    def polygon(*coords, color=accent):
        draw.polygon([point(x,y) for x,y in zip(coords[0::2],coords[1::2])],fill=color)

    if key == "home":
        line(-9,-1,0,-9,9,-1)
        line(-6.5,-2,-6.5,8,6.5,8,6.5,-2)
        line(-1.5,8,-1.5,2,2.5,2,2.5,8,color=accent,width=fine)
    elif key == "playlist":
        for dy,length in ((-6,12),(0,15),(6,10)):
            filled_ellipse(-9,dy-1.2,-6.6,dy+1.2)
            line(-3,dy,-3+length,dy,width=stroke)
    elif key == "settings":
        for dy,knob_x in ((-6,-2.5),(0,3.5),(6,-5.0)):
            line(-9,dy,9,dy,width=fine)
            outline_ellipse(knob_x-2.8,dy-2.8,knob_x+2.8,dy+2.8,tint,width=fine)
            filled_ellipse(knob_x-1.6,dy-1.6,knob_x+1.6,dy+1.6,accent)
    elif key == "dependencies":
        nodes=((0,-7.5),(-7.3,5.5),(7.3,5.5))
        line(*nodes[0],*nodes[1],width=fine)
        line(*nodes[0],*nodes[2],width=fine)
        line(*nodes[1],*nodes[2],color=accent,width=fine)
        for idx,(x,y) in enumerate(nodes):
            radius=3.1 if idx==0 else 2.8
            filled_ellipse(x-radius,y-radius,x+radius,y+radius,accent if idx==0 else tint)
    elif key == "updates":
        a,b=point(-9,-9); c,d=point(9,9)
        draw.arc((a,b,c,d),start=35,end=320,fill=tint,width=stroke)
        polygon(4,-9,10,-9,8.5,-3)
        line(-3,0,4,0,color=accent,width=fine)
    elif key == "help":
        outline_ellipse(-9,-9,9,9,tint,width=fine)
        line(-2,-3,-1,-5,2,-4,3,-2,1,0,-1,2,color=accent,width=fine)
        filled_ellipse(-1,5,1,7,accent)
    else:
        line(-9,0,-5,0,-2,-6,1,6,4,-3,7,0,10,0,width=stroke)
        line(-9,8,9,8,color=accent,width=fine)

    resampling = getattr(Image, "Resampling", Image)
    lanczos = getattr(resampling, "LANCZOS", 1)
    image = image.resize((size, size), resample=lanczos)
    return ImageTk.PhotoImage(image, master=master)


def draw_section_icon(
    canvas: tk.Canvas, cx: float, cy: float, key: str, tint: str, accent: str, *, scale: float = 1.18
) -> str:
    """Draw larger round-capped vector icons so navigation glyphs look less blocky."""
    tag = "nav-icon-" + key
    scale = max(.85, min(1.65, float(scale)))

    def point(x, y):
        return cx + (x-cx)*scale, cy + (y-cy)*scale

    def points(values):
        transformed=[]
        for x,y in zip(values[0::2],values[1::2]):
            transformed.extend(point(x,y))
        return transformed

    def line(*coords,color=tint,weight=2.45):
        return canvas.create_line(*points(coords),fill=color,width=weight*scale,
            capstyle=tk.ROUND,joinstyle=tk.ROUND,smooth=False,tags=(tag,"nav-icon-line"))

    def outline_oval(x1,y1,x2,y2):
        x1,y1=point(x1,y1); x2,y2=point(x2,y2)
        return canvas.create_oval(x1,y1,x2,y2,fill="",outline=tint,width=2.45*scale,
                                  tags=(tag,"nav-icon-outline"))

    def filled_oval(x1,y1,x2,y2,color=accent):
        x1,y1=point(x1,y1); x2,y2=point(x2,y2)
        return canvas.create_oval(x1,y1,x2,y2,fill=color,outline=color,width=1.1*scale,
                                  tags=(tag,"nav-icon-filled"))

    def filled_polygon(*coords):
        return canvas.create_polygon(*points(coords),fill=accent,outline=accent,width=1.1*scale,
                                     smooth=True,splinesteps=16,tags=(tag,"nav-icon-filled"))

    if key == "home":
        line(cx-9,cy-1,cx,cy-9,cx+9,cy-1,weight=2.6)
        line(cx-6.5,cy-2,cx-6.5,cy+8,cx+6.5,cy+8,cx+6.5,cy-2,weight=2.5)
        line(cx-1.5,cy+8,cx-1.5,cy+2,cx+2.5,cy+2,cx+2.5,cy+8,color=accent,weight=2.3)
    elif key == "playlist":
        for dy,length in ((-6,12),(0,15),(6,10)):
            filled_oval(cx-9,cy+dy-1.2,cx-6.6,cy+dy+1.2)
            line(cx-3,cy+dy,cx-3+length,cy+dy,weight=2.6)
    elif key == "settings":
        for dy,knob_x in ((-6,cx-2.5),(0,cx+3.5),(6,cx-5.0)):
            line(cx-9,cy+dy,cx+9,cy+dy,weight=2.4)
            x1,y1=point(knob_x-2.8,cy+dy-2.8); x2,y2=point(knob_x+2.8,cy+dy+2.8)
            canvas.create_oval(x1,y1,x2,y2,fill=accent,outline=tint,width=1.7*scale,
                               tags=(tag,"nav-icon-outline"))
    elif key == "dependencies":
        nodes=((cx,cy-7.5),(cx-7.3,cy+5.5),(cx+7.3,cy+5.5))
        line(*nodes[0],*nodes[1],weight=2.6); line(*nodes[0],*nodes[2],weight=2.6)
        line(*nodes[1],*nodes[2],color=accent,weight=2.1)
        for index,(x,y) in enumerate(nodes):
            radius=3.1 if index==0 else 2.8
            filled_oval(x-radius,y-radius,x+radius,y+radius,accent if index==0 else tint)
    elif key == "updates":
        x1,y1=point(cx-9,cy-9); x2,y2=point(cx+9,cy+9)
        canvas.create_arc(x1,y1,x2,y2,start=35,extent=285,style=tk.ARC,outline=tint,
                          width=2.7*scale,tags=(tag,"nav-icon-outline"))
        filled_polygon(cx+4,cy-9,cx+10,cy-9,cx+8.5,cy-3)
        line(cx-3,cy,cx+4,cy,color=accent,weight=2.4)
    elif key == "help":
        outline_oval(cx-9,cy-9,cx+9,cy+9)
        x,y=point(cx,cy-.7)
        canvas.create_text(x,y,text="?",fill=accent,font=("Segoe UI",max(11,int(15*scale)),"bold"),
                           tags=(tag,"nav-icon-text"))
        filled_oval(cx-1,cy+5,cx+1,cy+7,tint)
    else:
        line(cx-9,cy,cx-5,cy,cx-2,cy-6,cx+1,cy+6,cx+4,cy-3,cx+7,cy,cx+10,cy,weight=2.7)
        line(cx-9,cy+8,cx+9,cy+8,color=accent,weight=1.9)
    # Use a 4x supersampled RGBA asset when Pillow is available. Keep the vector
    # version as a dependency-free fallback.
    photo = render_nav_icon_image(key, tint, accent, scale=scale, master=canvas)
    if photo is not None:
        canvas.itemconfigure(tag, state=tk.HIDDEN)
        item_id = canvas.create_image(cx, cy, image=photo, tags=(tag, "nav-icon-raster"))
        if not hasattr(canvas, "_nav_icon_specs"):
            canvas._nav_icon_specs = {}
            canvas._nav_icon_photos = {}
        canvas._nav_icon_specs[tag] = (key, scale, item_id)
        canvas._nav_icon_photos[tag] = photo
    return tag

def rounded_span(y: int, width: int, height: int, radius: int) -> tuple[int, int]:
    """Horizontal span inside a rounded rectangle at vertical coordinate y."""
    r = max(1, min(radius, width // 2, height // 2))
    center_y = height / 2
    depth = abs(y - center_y) - (height / 2 - r)
    inset = r - (max(0.0, r * r - depth * depth) ** 0.5) if depth > 0 else 0
    return max(0, int(inset)), min(width, int(width - inset))


def validate_preview_url(raw_url: str) -> str:
    """Accept public HTTP(S) media URLs only; reject local names/IPs and credentials."""
    value = str(raw_url or "").strip()
    parts = urllib.parse.urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("Cole um endereço público começando com https:// ou http://.")
    if parts.username or parts.password:
        raise ValueError("Links com credenciais embutidas não são aceitos.")
    hostname = parts.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(
        (".localhost", ".local", ".internal", ".test", ".invalid", ".example")
    ):
        raise ValueError("Endereços locais/de exemplo não podem gerar uma prévia.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        if not address.is_global:
            raise ValueError("Endereços IP privados ou reservados não podem gerar uma prévia.")
    elif "." not in hostname:
        raise ValueError("O endereço precisa apontar para um domínio público.")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("A porta do link não é válida.") from exc
    if (parts.scheme.lower() == "https" and port not in (None, 443)) or (
        parts.scheme.lower() == "http" and port not in (None, 80)
    ):
        raise ValueError("Portas personalizadas não são aceitas para prévias.")
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc, parts.path, parts.query, ""))


def format_media_duration(value) -> str:
    """Format a duration in seconds as mm:ss or h:mm:ss."""
    try:
        seconds = max(0, int(float(value)))
    except (TypeError, ValueError, OverflowError):
        return "Duração desconhecida"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def _thumbnail_from_info(info: dict) -> str:
    """Pick the largest thumbnail URL advertised in extractor metadata."""
    candidates = []
    for image in info.get("thumbnails") or []:
        if not isinstance(image, dict) or not image.get("url"):
            continue
        try:
            area = int(image.get("width") or 0) * int(image.get("height") or 0)
        except (TypeError, ValueError, OverflowError):
            area = 0
        candidates.append((area, image["url"]))
    return str(max(candidates, default=(0, info.get("thumbnail")))[1] or "")


def _normalize_media_item(info: dict, fallback_url: str) -> dict:
    item_url = str(info.get("webpage_url") or info.get("original_url") or info.get("url") or fallback_url)
    if not item_url.startswith(("http://", "https://")) and info.get("id"):
        extractor = str(info.get("ie_key") or info.get("extractor_key") or "").lower()
        if "youtube" in extractor:
            item_url = "https://www.youtube.com/watch?v=" + urllib.parse.quote(str(info["id"]), safe="")
    return {
        "title": html.unescape(str(info.get("title") or info.get("id") or "Mídia sem título")),
        "channel": html.unescape(str(info.get("channel") or info.get("uploader") or info.get("creator") or "Canal não informado")),
        "duration": info.get("duration"),
        "duration_text": format_media_duration(info.get("duration")),
        "thumbnail_url": _thumbnail_from_info(info),
        "url": item_url,
    }


def fetch_preview_metadata(raw_url: str, *, playlist: bool = False, max_items: int = 20) -> dict:
    """Resolve public metadata only. This never downloads a media file or runs a converter."""
    url = validate_preview_url(raw_url)
    try:
        import yt_dlp
    except ImportError:
        yt_dlp = None

    if yt_dlp is not None:
        class QuietPreviewLogger:
            def debug(self, _message): pass
            def warning(self, _message): pass
            def error(self, _message): pass

        options = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": not playlist, "ignoreerrors": True, "logger": QuietPreviewLogger(),
            "socket_timeout": 8, "retries": 0, "extractor_retries": 0,
            "playlist_items": f"1-{max(1, min(int(max_items), 40))}" if playlist else None,
            "extract_flat": "in_playlist" if playlist else False,
            "cachedir": False, "overwrites": False, "nopart": True,
        }
        options = {key: value for key, value in options.items() if value is not None}
        try:
            with yt_dlp.YoutubeDL(options) as extractor:
                info = extractor.extract_info(url, download=False)
        except Exception as exc:
            raise RuntimeError("Não consegui ler os metadados desse link. Confira o endereço e tente novamente.") from exc
        if not isinstance(info, dict):
            raise RuntimeError("A fonte não retornou informações de mídia.")
        entries = info.get("entries")
        if playlist and entries is not None:
            items = [
                _normalize_media_item(entry, url)
                for entry in list(entries)[:max_items] if isinstance(entry, dict)
            ]
            return {
                "title": html.unescape(str(info.get("title") or "Lista de mídia")),
                "channel": "Playlist / lista", "is_playlist": True,
                "items": items, "url": url,
            }
        return {**_normalize_media_item(info, url), "is_playlist": False, "items": []}

    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    is_youtube = host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")
    is_vimeo = host == "vimeo.com" or host.endswith(".vimeo.com")
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    is_playlist_url = bool(query.get("list"))
    if (not playlist or not is_playlist_url) and (is_youtube or is_vimeo):
        endpoint = "https://www.youtube.com/oembed" if is_youtube else "https://vimeo.com/api/oembed.json"
        request_query = urllib.parse.urlencode({"url": url, "format": "json"})
        request = urllib.request.Request(endpoint + "?" + request_query, headers={"User-Agent": "MediaLabPreview/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = response.read(1024 * 1024 + 1)
            if len(payload) > 1024 * 1024:
                raise RuntimeError("A resposta de prévia ultrapassou o limite permitido.")
            info = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("Não consegui gerar a prévia. Instale yt-dlp para ampliar o suporte a fontes.") from exc
        return {
            "title": html.unescape(str(info.get("title") or "Mídia sem título")),
            "channel": html.unescape(str(info.get("author_name") or "Canal não informado")),
            "duration": None, "duration_text": "Duração não fornecida",
            "thumbnail_url": str(info.get("thumbnail_url") or ""),
            "url": url, "is_playlist": False, "items": [],
        }
    requirement = "yt-dlp é necessário para prévias de playlists." if playlist else "Instale yt-dlp para gerar prévias desta fonte."
    raise RuntimeError(requirement + " O protótipo ainda não inicia downloads reais.")


def fetch_thumbnail_bytes(raw_url: str, *, max_bytes: int = 5 * 1024 * 1024) -> bytes | None:
    """Fetch one small HTTPS thumbnail from a public host; never fetch media streams."""
    value = str(raw_url or "").strip()
    if not value:
        return None
    try:
        parts = urllib.parse.urlsplit(value)
        if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
            return None
        if parts.port not in (None, 443):
            return None
        host = parts.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(
            (".localhost", ".local", ".internal", ".test", ".invalid", ".example")
        ):
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            return None
        if address is None and "." not in host:
            return None
        request = urllib.request.Request(value, headers={"User-Agent": "MediaLabPreview/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            final_url = urllib.parse.urlsplit(response.geturl())
            if final_url.scheme.lower() != "https":
                return None
            try:
                validate_preview_url(response.geturl())
            except ValueError:
                return None
            declared_size = response.headers.get("Content-Length")
            if declared_size and int(declared_size) > max_bytes:
                return None
            payload = response.read(max_bytes + 1)
        return payload if 0 < len(payload) <= max_bytes else None
    except (OSError, ValueError, urllib.error.URLError, TimeoutError):
        return None


def adaptive_ui_scale(screen_width: int, screen_height: int) -> float:
    """Scale interface metrics for the display, capped at 125% on 1440p+ monitors."""
    if screen_width <= 0 or screen_height <= 0:
        return 1.0
    return round(min(1.25, max(.82, min(screen_width / 1920.0, screen_height / 1080.0))), 2)


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
        for index in range(96):
            item = self.create_rectangle(0, 0, 1, 1, width=0, tags="gradient")
            self.strips.append(item)
        self.glow_items: list[tuple[int, str, float, str]] = []
        for corner, tint in (("tl", "#8B5CF6"), ("tr", "#6D28D9"), ("bl", "#6D28D9"), ("br", "#2563EB")):
            for level in range(22):
                item = self.create_oval(0, 0, 1, 1, fill="", outline="", tags="corner-glow")
                self.glow_items.append((item, corner, level / 21, tint))
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
            self.itemconfigure(item, fill=blend_hex(colors["bg"], tint, 0.010 + 0.105 * (level ** 1.45)), outline="")
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
        if isinstance(padding, tuple):
            px, py = padding
        else:
            px = py = padding
        self.padding = (app.scale_px(px), app.scale_px(py))
        self.radius = app.scale_px(radius)
        self.canvas = tk.Canvas(self, bg=app.colors[self.backdrop_key], bd=0, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = tk.Frame(self, bg=app.colors[background_key], bd=0, highlightthickness=0)
        self.body.pack(fill="both", expand=True, padx=max(2,self.padding[0]), pady=max(2,self.padding[1]))
        self._shape = self.canvas.create_polygon(
            *rounded_points(1, 1, 4, 4, radius), smooth=True, splinesteps=20,
            fill=app.colors[background_key], outline=app.colors["border"], width=1.8,
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
                outline=self.app.colors["border"], width=1.8,
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
    """Fixed-layout vector button: only its drawing scales, never its widget geometry."""
    def __init__(self, master, app, text, command=None, *, variant="secondary", width=None, height=40):
        self.app, self.text, self.command, self.variant = app, text, command, variant
        self.base_height = app.scale_px(height)
        self.font_size = app.scale_px(9 if height < 36 else 10)
        self.font = tkfont.Font(family="Segoe UI", size=self.font_size,
                                weight="bold" if variant == "primary" else "normal")
        desired = self.font.measure(text) + app.scale_px(34 if variant == "primary" else 30)
        self.base_width = app.scale_px(width) if width is not None else max(app.scale_px(82), min(app.scale_px(300), desired))
        self.gutter_x, self.gutter_y = app.scale_px(5), app.scale_px(4)
        self.widget_width = self.base_width + self.gutter_x * 2
        self.widget_height = self.base_height + self.gutter_y * 2
        self.width, self.height = self.widget_width, self.widget_height
        self.current_scale, self._target_scale, self._scale_after_id = 1.0, 1.0, None
        self.bg_key = background_key_for(master, app, "bg")
        super().__init__(master, width=self.widget_width, height=self.widget_height,
                         bg=app.colors[self.bg_key], bd=0, highlightthickness=0, cursor="hand2")
        self.hovered = self.pressed = False
        self._gradient_ids = []
        self._gradient_rows = 24
        for row in range(self._gradient_rows):
            item = self.create_line(0,0,0,0,fill=app.colors["button"],width=2.0 * app.ui_scale,
                capstyle=tk.ROUND,tags=("button-shape","button-fill"))
            self._gradient_ids.append(item)
        self._glow_ids = []
        for spread, width, strength in ((3.2 * app.ui_scale, 3.4 * app.ui_scale, 0.13),
                                        (1.4 * app.ui_scale, 2.2 * app.ui_scale, 0.20)):
            item = self.create_polygon(0,0,0,0, fill="", outline=app.colors["bg"],
                width=width, smooth=True, splinesteps=20, tags=("button-shape","button-glow"))
            self._glow_ids.append((item, spread, width, strength))
        self._outline_id = self.create_polygon(0,0,0,0, fill="", outline=app.colors["border"],
            width=1.8 * app.ui_scale, smooth=True, splinesteps=20, tags=("button-shape","button-outline"))
        self._text_id = self.create_text(self.widget_width/2,self.widget_height/2,text=text,
            fill=app.colors["fg"],font=self.font,width=self.base_width-app.scale_px(18),tags="button-shape")
        self.bind("<Configure>", self._on_resize, add="+")
        self.bind("<Enter>", self._enter, add="+")
        self.bind("<Leave>", self._leave, add="+")
        self.bind("<ButtonPress-1>", self._press, add="+")
        self.bind("<ButtonRelease-1>", self._release, add="+")
        self.bind("<Return>", self._keyboard, add="+")
        self.bind("<space>", self._keyboard, add="+")
        app.buttons.append(self)
        self._apply_size(1.0)
        self.refresh_theme()

    def _on_resize(self, _event):
        # Canvas geometry is intentionally fixed; Tk must not repack a button on hover.
        pass

    def _apply_size(self, scale):
        self.current_scale = scale
        inner_w, inner_h = self.base_width*scale, self.base_height*scale
        left, top = (self.widget_width-inner_w)/2, (self.widget_height-inner_h)/2
        radius = min(self.app.scale_px(12), inner_h*0.34)
        for index,item in enumerate(self._gradient_ids):
            y = top + (index+0.5)*inner_h/self._gradient_rows
            local_y = round((index+0.5)*inner_h/self._gradient_rows)
            span_l,span_r = rounded_span(local_y,round(inner_w),round(inner_h),round(radius))
            self.coords(item,left+span_l,y,left+max(span_l+0.1,span_r),y)
        for item, spread, _width, _strength in self._glow_ids:
            outer_left, outer_top = max(0, left-spread), max(0, top-spread)
            outer_right = min(self.widget_width, left+inner_w+spread)
            outer_bottom = min(self.widget_height, top+inner_h+spread)
            self.coords(item, *rounded_points(
                outer_left, outer_top, outer_right, outer_bottom, radius+spread, steps=18
            ))
        self.coords(self._outline_id,*rounded_points(left,top,left+inner_w,top+inner_h,radius,steps=18))
        self.coords(self._text_id,self.widget_width/2,self.widget_height/2)

    def _animate_to(self, scale):
        self._target_scale = scale
        if self.app.settings.get("reduce_motion") or not self.app.settings.get("animations_enabled",True):
            if self._scale_after_id is not None:
                try:self.after_cancel(self._scale_after_id)
                except tk.TclError:pass
                self._scale_after_id=None
            self._apply_size(scale)
            return
        if self._scale_after_id is not None:
            try:self.after_cancel(self._scale_after_id)
            except tk.TclError:pass
        start,frames=self.current_scale,4
        def frame(index=1):
            if index>frames:
                self._scale_after_id=None
                self._apply_size(scale)
                return
            progress=index/frames
            eased=1-(1-progress)**3
            self._apply_size(start+(scale-start)*eased)
            self._scale_after_id=self.after(18,lambda:frame(index+1))
        frame()

    def _enter(self,_event=None):
        self.hovered=True
        self._refresh_colors()
        self._animate_to(1.035)

    def _leave(self,_event=None):
        self.hovered=self.pressed=False
        self._refresh_colors()
        self._animate_to(1.0)

    def _press(self,_event=None):
        self.pressed=True
        self._refresh_colors()
        self._animate_to(1.04 if self.hovered else 1.015)
        return "break"

    def _release(self,event=None):
        invoke=self.pressed and event is not None and 0<=event.x<=self.widget_width and 0<=event.y<=self.widget_height
        self.pressed=False
        self._refresh_colors()
        self._animate_to(1.035 if self.hovered else 1.0)
        if invoke and callable(self.command):
            self.command()
        return "break"

    def _keyboard(self,_event=None):
        if callable(self.command):self.command()
        return "break"

    def _refresh_colors(self):
        c=self.app.colors
        if self.variant=="primary":
            start,end=c["accent"],c["accent2"]
            if self.hovered:
                start,end=blend_hex(start,"#FFFFFF",0.10),blend_hex(end,"#FFFFFF",0.08)
            if self.pressed:
                start,end=blend_hex(start,"#000000",0.12),blend_hex(end,"#000000",0.12)
            for row,item in enumerate(self._gradient_ids):
                self.itemconfigure(item,fill=blend_hex(start,end,row/max(1,len(self._gradient_ids)-1)))
            text_color,outline="#FFFFFF",blend_hex(end,"#FFFFFF",0.22)
        elif self.hovered:
            start,end="#D8C7FF","#B9A5FF"
            if self.pressed:
                start,end=blend_hex(start,"#8B5CF6",0.18),blend_hex(end,"#8B5CF6",0.18)
            for row,item in enumerate(self._gradient_ids):
                self.itemconfigure(item,fill=blend_hex(start,end,row/max(1,len(self._gradient_ids)-1)))
            text_color,outline="#2B174E","#E2D5FF"
        else:
            for item in self._gradient_ids:
                self.itemconfigure(item,fill=c["button"])
            text_color,outline=c["fg"],c["border"]
        if self.variant == "primary":
            glow_base = blend_hex(c["accent"], c["accent2"], 0.42)
            for item, _spread, width, strength in self._glow_ids:
                glow_strength = min(0.34, strength + (0.045 if self.hovered else 0.0))
                self.itemconfigure(
                    item,
                    outline=blend_hex(c["bg"], glow_base, glow_strength),
                    width=width * (1.10 if self.hovered else 1.0),
                    state=tk.NORMAL,
                )
        else:
            for item, _spread, _width, _strength in self._glow_ids:
                self.itemconfigure(item, state=tk.HIDDEN, outline=c["bg"])
        self.itemconfigure(self._outline_id,outline=outline,width=1.8 * self.app.ui_scale)
        self.itemconfigure(self._text_id,fill=text_color)
        self.configure(bg=c.get(self.bg_key,c["bg"]))

    def refresh_theme(self):
        self._refresh_colors()


class RoundedField(tk.Frame):
    """Rounded border/background behind a flat native entry."""
    def __init__(self, master, app, *, textvariable=None, placeholder=None, width=None, readonly=False):
        self.bg_key = background_key_for(master, app, "bg")
        super().__init__(master, bg=app.colors[self.bg_key], bd=0, highlightthickness=0, width=app.scale_px(width or 260), height=app.scale_px(42))
        self.app = app
        self.placeholder = placeholder
        self.readonly = readonly
        self.canvas = tk.Canvas(self, bg=app.colors[self.bg_key], bd=0, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.shape = self.canvas.create_polygon(*rounded_points(1, 1, 4, 4, app.scale_px(12)), fill=app.colors["field"], outline=app.colors["border"], width=1.8 * app.ui_scale, smooth=True, splinesteps=18)
        self.entry = tk.Entry(
            self, textvariable=textvariable, bg=app.colors["field"], fg=app.colors["input_fg"],
            insertbackground=app.colors["input_fg"], relief="flat", bd=0, highlightthickness=0,
            font=("Segoe UI", app.scale_px(10)), readonlybackground=app.colors["field"],
            disabledbackground=app.colors["field"], disabledforeground=app.colors["muted"],
        )
        self.entry.place(x=app.scale_px(12), y=app.scale_px(1), relwidth=1, width=-app.scale_px(24), relheight=1, height=-app.scale_px(2))
        if readonly:
            self.entry.configure(state="readonly")
        self.bind("<Configure>", self._resize, add="+")
        self.app.fields.append(self)
        self._resize(None)

    def _resize(self, _event):
        try:
            width, height = max(4, self.winfo_width()), max(4, self.winfo_height())
            self.canvas.coords(self.shape, *rounded_points(1, 1, width - 1, height - 1, min(self.app.scale_px(12), height / 2)))
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
        width, height = app.scale_px(width), app.scale_px(42)
        super().__init__(master, bg=app.colors[self.bg_key], width=width, height=height, bd=0, highlightthickness=0)
        self.app = app
        self.options = list(options)
        self.value = tk.StringVar(value=value)
        self.command = command
        self.canvas = tk.Canvas(self, bg=app.colors[self.bg_key], width=width, height=height, bd=0, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.shape = self.canvas.create_polygon(*rounded_points(1, 1, width - 1, height - 1, app.scale_px(12)), fill=app.colors["field"], outline=app.colors["border"], width=1.5 * app.ui_scale)
        self.label_id = self.canvas.create_text(app.scale_px(14), height / 2, text=value, anchor="w", fill=app.colors["input_fg"], font=("Segoe UI", app.scale_px(10)))
        self.chevron_id = self.canvas.create_text(width - app.scale_px(18), height / 2, text="⌄", fill=app.colors["accent2"], font=("Segoe UI", app.scale_px(13), "bold"))
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
        width, height = app.scale_px(width), app.scale_px(height)
        super().__init__(master, width=width, height=height, bg=app.colors["panel"], bd=0, highlightthickness=0, cursor="hand2")
        self.app = app
        self.variable = variable
        self.command = command
        self.width = width
        self.height = height
        self.track = self.create_polygon(*rounded_points(1, 1, width - 1, height - 1, height / 2), fill=app.colors["border"], outline="")
        inset, knob_size = app.scale_px(4), app.scale_px(18)
        self.knob = self.create_oval(inset, inset, inset + knob_size, inset + knob_size, fill="#FFFFFF", outline="")
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
        inset, knob_size = self.app.scale_px(4), self.app.scale_px(18)
        left = self.width - self.app.scale_px(23) if active else inset
        self.itemconfigure(self.track, fill=track)
        self.coords(self.knob, left, inset, left + knob_size, inset + knob_size)
        self.itemconfigure(self.knob, fill="#FFFFFF")
        self.configure(bg=c["panel"])


class OrbitalAtom(tk.Canvas):
    """Compact smooth vector atom mark; animation sleeps while the splash is active."""
    def __init__(self, master, app, *, size=42):
        super().__init__(master,width=size,height=size,bg=app.colors["panel"],bd=0,highlightthickness=0)
        self.app,self.size,self.phase=app,size,0.0
        self.particles=[]
        self._animation_id=None
        self.app.orbital_marks.append(self)
        self._draw_tracks()
        specs=((0.0,size*.34,size*.15,.3,app.colors["accent2"]),
               (math.pi/3,size*.30,size*.135,2.2,"#E879F9"),
               (-math.pi/3,size*.30,size*.135,4.1,"#A78BFA"))
        for rotation,rx,ry,angle,color in specs:
            rings=[]
            for radius,strength in ((5.8,.20),(3.8,.48),(1.9,.94)):
                rings.append((self.create_oval(0,0,0,0,
                    fill=blend_hex(app.colors["panel"],color,strength),outline="",tags="atom-particle"),radius))
            self.particles.append({"rotation":rotation,"rx":rx,"ry":ry,"angle":angle,
                "speed":.085 if rotation==0 else (.073 if rotation>0 else -.067),"rings":rings})
        self.create_oval(size/2-2,size/2-2,size/2+2,size/2+2,fill=app.colors["accent2"],outline="",tags="atom-nucleus")

    def _draw_tracks(self):
        self.delete("atom-track")
        c=self.app.colors
        cx=cy=self.size/2
        paths=((0,self.size*.34,self.size*.15),(math.pi/3,self.size*.30,self.size*.135),
               (-math.pi/3,self.size*.30,self.size*.135))
        for idx,(rotation,rx,ry) in enumerate(paths):
            points=[ellipse_point(cx,cy,rx,ry,2*math.pi*i/72,rotation) for i in range(73)]
            start,end=((c["accent"],c["accent2"]) if idx==0 else
                (("#E879F9",c["accent"]) if idx==1 else (c["accent2"],"#A78BFA")))
            self.create_line(*[coord for p in points for coord in p],fill=start,width=1.9,
                smooth=True,splinesteps=18,capstyle=tk.ROUND,joinstyle=tk.ROUND,tags="atom-track")
            # A short accent segment gives each orbit a clean, distinct color cue.
            accent_points=points[7:20]
            self.create_line(*[coord for point in accent_points for coord in point],
                fill=end,width=2.4,smooth=True,splinesteps=12,capstyle=tk.ROUND,tags="atom-track-accent")

    def start_animation(self):
        if self._animation_id is None:
            self._tick()

    def stop_animation(self):
        if self._animation_id is not None:
            try:self.after_cancel(self._animation_id)
            except tk.TclError:pass
            self._animation_id=None

    def _tick(self):
        try:
            self.phase+=.08
            cx=cy=self.size/2
            for particle in self.particles:
                particle["angle"]+=particle["speed"]
                x,y=ellipse_point(cx,cy,particle["rx"],particle["ry"],
                    particle["angle"]+self.phase*.07,particle["rotation"])
                for item,radius in particle["rings"]:
                    self.coords(item,x-radius,y-radius,x+radius,y+radius)
            self._animation_id=self.after(64,self._tick)
        except tk.TclError:
            self._animation_id=None

    def refresh_theme(self):
        self.configure(bg=self.app.colors["panel"])
        self._draw_tracks()


SPLASH_BACKGROUND = "#080713"
SPLASH_PALETTES = (
    ("#BCA8FF", "#829DFF"), ("#C4B5FD", "#75B5FF"),
    ("#A78BFA", "#6FC9F2"), ("#C1A4FF", "#8079F5"),
    ("#B4A7FF", "#8ACFFF"), ("#D2C1FF", "#79AFFF"),
    ("#D7BDF8", "#9A91F7"), ("#BDA7FA", "#73B8F8"),
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
        self.scale = adaptive_ui_scale(self.width, self.height)
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
        self._animation_after = self.window.after(34, self._animate)
        self._message_after = self.window.after(690, self._advance_message)
        try:
            self.window.lift()
            self.window.focus_force()
        except tk.TclError:
            pass

    def _draw_scene(self):
        c, w, h = self.canvas, self.width, self.height
        for i in range(112):
            x0, x1 = w * i / 112, w * (i + 1) / 112 + 1
            c.create_rectangle(x0, 0, x1, h, fill=blend_hex(SPLASH_BACKGROUND, "#21143D", .05 + .21*i/111), outline="")
        for cx, cy, tint in ((0, 0, "#8B5CF6"), (w, 0, "#6D28D9"), (0, h, "#7C3AED"), (w, h, "#2563EB")):
            for level in range(18):
                t = level / 17
                rx, ry = w * (.58 - .34*t), h * (.82 - .48*t)
                c.create_oval(cx-rx, cy-ry, cx+rx, cy+ry,
                    fill=blend_hex(SPLASH_BACKGROUND, tint, .012 + .16*t**1.65), outline="")
        rng = random.Random(119 + w + h)
        for _ in range(38):
            x, y = rng.random()*w, rng.random()*h
            radius, tint = rng.choice((1, 1, 1.5, 2)), rng.choice(("#8D86B5", "#8E84D6", "#A58DCB", "#65CBDC"))
            c.create_oval(x-radius, y-radius, x+radius, y+radius,
                fill=blend_hex(SPLASH_BACKGROUND, tint, .60), outline="")

    def _draw_orbit_loader(self):
        """Use a single smooth polyline for each particle trail; no old pixels are left behind."""
        self.scale = adaptive_ui_scale(self.width, self.height)
        cx, cy = self.width / 2, self.height * .315
        rx, ry = min(180 * self.scale, self.width * .145), min(88 * self.scale, self.height * .092)
        self.track_specs = (
            (0.0, rx, ry, ("#A78BFA", "#8BA4FF")),
            (math.pi / 3, rx * .93, ry * .88, ("#B29AFF", "#78BFFF")),
            (-math.pi / 3, rx * .72, ry * 1.22, ("#9B8AF5", "#83B7FF")),
        )
        for rotation, orbit_rx, orbit_ry, palette in self.track_specs:
            points = [ellipse_point(cx, cy, orbit_rx, orbit_ry, 2 * math.pi * i / 96, rotation) for i in range(97)]
            flat_points = [coord for point in points for coord in point]
            self.canvas.create_line(*flat_points, fill=blend_hex(palette[0], palette[1], .42),
                width=2.1 * self.scale, smooth=True, splinesteps=18,
                capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="splash-orbit-track")
            accent_points = points[8:27]
            self.canvas.create_line(*[coord for point in accent_points for coord in point],
                fill=palette[1], width=2.8 * self.scale, smooth=True, splinesteps=16,
                capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="splash-orbit-accent")
        self.particles = []
        for orbit, angle, speed, color in (
            (0, .7, .055, "#B9A4FF"), (1, 2.6, .047, "#9D91FF"), (2, 4.2, -.052, "#78B8FF")
        ):
            trail_glow = self.canvas.create_line(0, 0, 0, 0,
                fill=blend_hex(SPLASH_BACKGROUND, color, .31), width=6 * self.scale,
                capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True, splinesteps=16,
                state=tk.HIDDEN, tags=("splash-trail", "splash-trail-glow"))
            trail = self.canvas.create_line(0, 0, 0, 0,
                fill=blend_hex(SPLASH_BACKGROUND, color, .82), width=2.2 * self.scale,
                capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True, splinesteps=16,
                state=tk.HIDDEN, tags=("splash-trail", "splash-trail-core"))
            glows = [
                (self.canvas.create_oval(0, 0, 0, 0,
                    fill=blend_hex(SPLASH_BACKGROUND, color, strength), outline="",
                    tags="splash-particle"), radius * self.scale, strength)
                for radius, strength in ((12, .20), (7, .42), (3.6, .94))
            ]
            self.particles.append({
                "orbit": orbit, "angle": angle, "speed": speed, "color": color,
                "trail_glow": trail_glow, "trail": trail, "glows": glows, "history": [],
            })
        self.canvas.create_oval(cx - 12*self.scale, cy - 12*self.scale,
            cx + 12*self.scale, cy + 12*self.scale,
            fill=blend_hex(SPLASH_BACKGROUND, "#BCA0FF", .59), outline="", tags="splash-nucleus-glow")
        self.canvas.create_oval(cx - 4*self.scale, cy - 4*self.scale,
            cx + 4*self.scale, cy + 4*self.scale,
            fill="#F5D0FE", outline="", tags="splash-nucleus")

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
        chunk_size=max(1,math.ceil(len(text)/18))
        chunks=[text[i:i+chunk_size] for i in range(0,len(text),chunk_size)]
        widths=[font.measure(chunk) for chunk in chunks]
        x,start_y=(self.width-sum(widths))/2,self.height*.735
        glyphs,colors=[],[]
        for i,chunk in enumerate(chunks):
            fill=blend_hex(palette[0],palette[1],i/max(1,len(chunks)-1))
            item=self.canvas.create_text(x,start_y,text=chunk,anchor="w",fill=fill,font=font,tags=(tag,"splash-status"))
            glyphs.append((item,x));colors.append(fill);x+=widths[i]
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
        if self._closed:
            return
        self.phase += .06
        for particle in self.particles:
            rotation, orbit_rx, orbit_ry, _palette = self.track_specs[particle["orbit"]]
            particle["angle"] += particle["speed"]
            point = ellipse_point(self.width/2, self.height*.315, orbit_rx, orbit_ry, particle["angle"], rotation)
            history = particle["history"]
            history.insert(0, point)
            del history[9:]
            if len(history) >= 2:
                coords = [value for trail_point in history for value in trail_point]
                for trail_id in (particle["trail_glow"], particle["trail"]):
                    self.canvas.coords(trail_id, *coords)
                    self.canvas.itemconfigure(trail_id, state=tk.NORMAL)
                self.canvas.itemconfigure(particle["trail_glow"], width=max(1.5*self.scale, 6*self.scale*len(history)/9))
                self.canvas.itemconfigure(particle["trail"], width=max(1.0*self.scale, 2.2*self.scale*len(history)/9))
            else:
                self.canvas.itemconfigure(particle["trail_glow"], state=tk.HIDDEN)
                self.canvas.itemconfigure(particle["trail"], state=tk.HIDDEN)
            x, y = point
            for glow, radius, _strength in particle["glows"]:
                r = radius * (1 + .045 * math.sin(self.phase*2 + radius))
                self.canvas.coords(glow, x-r, y-r, x+r, y+r)
        for m in list(self.active_texts):
            m["age"] += 34; age = m["age"]
            y = m["start_y"] - self.height*.105*min(1,age/760)
            fade = max(0,min(1,(age-520)/300))
            appear = .10+.90*min(1,age/250)
            for (item,x),original in zip(m["glyphs"],m["colors"]):
                self.canvas.coords(item,x,y)
                self.canvas.itemconfigure(item,fill=blend_hex(SPLASH_BACKGROUND,original,appear*(1-fade)))
            if age > 1080:
                self.canvas.delete(m["tag"]); self.active_texts.remove(m)
                m.pop("font", None)
        try: self._animation_after = self.window.after(34,self._animate)
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
        screen_width = max(800, int(root.winfo_screenwidth()))
        screen_height = max(600, int(root.winfo_screenheight()))
        self.ui_scale = adaptive_ui_scale(screen_width, screen_height)
        self.root.title(APP_NAME + "  •  v" + APP_VERSION)
        start_width, start_height = min(screen_width - 32, self.scale_px(1280)), min(screen_height - 80, self.scale_px(830))
        self.root.geometry("%dx%d+%d+%d" % (start_width, start_height,
            max(0, (screen_width-start_width)//2), max(0, (screen_height-start_height)//2)))
        self.root.minsize(min(screen_width, self.scale_px(960)), min(screen_height, self.scale_px(620)))
        self.root.configure(bg=PALETTES["dark"]["bg"])
        # Respect the actual monitor area instead of rendering at a fixed 1280x830.
        try:
            self.root.state("zoomed")
        except tk.TclError:
            width = max(min(screen_width, self.scale_px(960)), int(screen_width*.94))
            height = max(min(screen_height, self.scale_px(620)), int(screen_height*.92))
            self.root.geometry("%dx%d+%d+%d" % (width,height,max(0,(screen_width-width)//2),max(0,(screen_height-height)//2)))
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
        self.nav_items: dict[str, tuple] = {}
        self.mini_graphs: list[tuple[tk.Canvas, object]] = []
        self.current_page = "home"
        self.toast_after = None
        self._preview_busy = False
        self._playlist_preview_busy = False
        self.current_media_metadata: dict | None = None
        self.media_preview_photo = None
        self.playlist_count_label = None
        self.playlist_selection_label = None
        self._playlist_photo_refs: list = []
        self.update_info: dict | None = None
        self._update_busy = False
        self._stop = threading.Event()
        self.orbital_marks: list[OrbitalAtom] = []
        self.splash: CosmicSplash | None = None
        self.shell = tk.Frame(root, bg=self.colors["bg"], bd=0, highlightthickness=0)
        self.shell.place(x=0, y=0, relwidth=1, relheight=1)
        self._build_shell()
        self._build_pages()
        self.root.bind_all("<MouseWheel>", self._route_wheel, add="+")
        self.root.bind_all("<Button-4>", self._route_wheel, add="+")
        self.root.bind_all("<Button-5>", self._route_wheel, add="+")
        self.show_page("home")
        self.apply_theme(refresh=False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if show_splash:
            self.splash = CosmicSplash(root, mode="startup", looping=False, on_close=self._startup_splash_finished)
        else:
            for mark in self.orbital_marks:
                mark.start_animation()
            if self.settings.get("update_check_on_startup", True):
                self.root.after(1800, self.check_update_async)

    def scale_px(self, value: float) -> int:
        return max(1, int(round(float(value) * self.ui_scale)))

    def _settings_path(self) -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            return base / "ChatGPT" / "MediaDownloader-UI-debug" / "settings.json"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "ChatGPT" / "MediaDownloader-UI-debug" / "settings.json"
        return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "ChatGPT" / "MediaDownloader-UI-debug" / "settings.json"

    def _load_settings(self) -> dict:
        data = dict(DEFAULT_SETTINGS)
        loaded = {}
        settings_found = False
        try:
            loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
            settings_found = isinstance(loaded, dict)
            if settings_found:
                data.update({key: loaded[key] for key in DEFAULT_SETTINGS if key in loaded})
                if "visual_preset_version" not in loaded:
                    data["visual_preset_version"] = 1
        except (OSError, json.JSONDecodeError):
            pass
        if data.get("theme") not in PALETTES:
            data["theme"] = "dark"
        for key, fallback in (("accent_color", DEFAULT_SETTINGS["accent_color"]),
                              ("accent_color_2", DEFAULT_SETTINGS["accent_color_2"])):
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(data.get(key, ""))):
                data[key] = fallback
            data[key] = data[key].upper()
        try:
            preset_version = int(data.get("visual_preset_version", 1 if settings_found else 2))
        except (TypeError, ValueError):
            preset_version = 1
        if preset_version < 2:
            if data["accent_color"] == "#7C5CFF":
                data["accent_color"] = DEFAULT_SETTINGS["accent_color"]
            if data["accent_color_2"] == "#20D8E7":
                data["accent_color_2"] = DEFAULT_SETTINGS["accent_color_2"]
        data["visual_preset_version"] = 2
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
        outer = tk.Frame(self.shell, bg=self.colors["bg"], padx=self.scale_px(18), pady=self.scale_px(16))
        outer.pack(fill="both", expand=True)
        self.backdrop = GradientBackdrop(outer, self)
        self.backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        # Force the decorative canvas behind real controls to prevent the odd
        # purple seam appearing just to the right of the sidebar navigation.
        try:
            self.backdrop.tk.call("lower", self.backdrop._w)
        except tk.TclError:
            pass
        self.sidebar = tk.Frame(outer, bg=self.colors["panel"], width=self.scale_px(220),
                                bd=0, highlightthickness=1, highlightbackground=self.colors["border"])
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        # This opaque spacer masks the decorative glow in the gap; lowering the
        # backdrop alone cannot hide pixels in empty space between packed widgets.
        self.nav_gap = tk.Frame(
            outer, bg=self.colors["bg"], width=self.scale_px(16),
            bd=0, highlightthickness=0,
        )
        self.nav_gap._ui_bg_key = "bg"
        self.nav_gap.pack(side="left", fill="y")
        brand = tk.Frame(self.sidebar, bg=self.colors["panel"], padx=self.scale_px(18), pady=self.scale_px(20))
        brand.pack(fill="x")
        mark = OrbitalAtom(brand, self, size=self.scale_px(58))
        mark.pack(side="left", padx=(0,self.scale_px(11)))
        titlebox = tk.Frame(brand, bg=self.colors["panel"])
        titlebox.pack(side="left", fill="x", expand=True)
        self.label(titlebox, "MEDIA LAB", "fg", "panel", 12, "bold").pack(anchor="w")
        self.label(titlebox, "UI-debug  /  DEV", "muted", "panel", 8, "normal").pack(anchor="w", pady=(self.scale_px(3),0))
        self._divider(self.sidebar, "panel")
        self.label(self.sidebar, "WORKSPACE", "muted", "panel", 8, "bold").pack(anchor="w", padx=self.scale_px(20), pady=(self.scale_px(16),self.scale_px(8)))
        navigation = [
            ("home", "Início"), ("playlist", "Playlists"), ("settings", "Aparência"),
            ("dependencies", "Dependências"), ("updates", "Atualizações"),
            ("help", "Ajuda"), ("diagnostics", "Diagnóstico"),
        ]
        self.nav_container = tk.Frame(self.sidebar, bg=self.colors["panel"])
        self.nav_container.pack(fill="x", padx=self.scale_px(10))
        nav_width, nav_height = self.scale_px(194), self.scale_px(43)
        for key, text in navigation:
            nav = tk.Canvas(self.nav_container, width=nav_width, height=nav_height,
                            bg=self.colors["panel"], bd=0, highlightthickness=0, cursor="hand2")
            nav.pack(fill="x", pady=(0,self.scale_px(4)))
            shape = nav.create_polygon(*rounded_points(1,1,nav_width-2,nav_height-2,self.scale_px(10),steps=18),
                fill=self.colors["panel2"], outline=self.colors["border"], width=max(1.0,self.ui_scale),
                smooth=True, splinesteps=18, tags="nav-surface")
            plate = nav.create_polygon(*rounded_points(self.scale_px(8),self.scale_px(7),self.scale_px(40),
                nav_height-self.scale_px(7),self.scale_px(9),steps=14),
                fill=self.colors["panel"], outline="", smooth=True, splinesteps=16, tags="nav-icon-plate")
            icon = draw_section_icon(nav,self.scale_px(24),nav_height/2,key,self.colors["muted"],self.colors["accent2"],scale=1.18*self.ui_scale)
            label_id = nav.create_text(self.scale_px(48),nav_height/2,text=text,anchor="w",
                fill=self.colors["muted"],font=("Segoe UI",self.scale_px(10)))
            indicator = nav.create_line(self.scale_px(5),self.scale_px(12),self.scale_px(5),nav_height-self.scale_px(12),
                fill=self.colors["accent"],width=self.scale_px(3),capstyle=tk.ROUND,state=tk.HIDDEN,tags="nav-active-indicator")
            nav.bind("<Button-1>",lambda _event,name=key:self.show_page(name))
            nav.bind("<Enter>",lambda _event,name=key:self._nav_hover(name,True))
            nav.bind("<Leave>",lambda _event,name=key:self._nav_hover(name,False))
            self.nav_items[key]=(nav,shape,icon,label_id,indicator,plate)
        spacer = tk.Frame(self.sidebar, bg=self.colors["panel"])
        spacer.pack(fill="both", expand=True)
        self._divider(self.sidebar, "panel")
        version_card = tk.Frame(self.sidebar,bg=self.colors["panel"],padx=self.scale_px(17),pady=self.scale_px(14))
        version_card.pack(fill="x")
        self.label(version_card,"CANAL DE DESENVOLVIMENTO","muted","panel",7,"bold").pack(anchor="w")
        version_row=tk.Frame(version_card,bg=self.colors["panel"])
        version_row.pack(fill="x",pady=(self.scale_px(6),0))
        self.label(version_row,APP_VERSION,"accent2","panel",9,"bold").pack(side="left")
        self.label(version_row,"sem release","muted","panel",8,"normal").pack(side="right")

        self.main=tk.Frame(outer,bg=self.colors["bg"],bd=0,highlightthickness=0)
        self.main.pack(side="left",fill="both",expand=True)
        topbar=tk.Frame(self.main,bg=self.colors["bg"],height=self.scale_px(74))
        topbar.pack(fill="x",pady=(self.scale_px(1),self.scale_px(14)))
        top_left=tk.Frame(topbar,bg=self.colors["bg"])
        top_left.pack(side="left",fill="x",expand=True)
        self.label(top_left,"CHATGPT MEDIA DOWNLOADER  /  ESPAÇO DE TESTES","muted","bg",8,"bold").pack(anchor="w",pady=(self.scale_px(3),self.scale_px(4)))
        self.page_title_label=self.label(top_left,"Início","fg","bg",22,"bold")
        self.page_title_label.pack(anchor="w")
        actions=tk.Frame(topbar,bg=self.colors["bg"])
        actions.pack(side="right",anchor="n",pady=(self.scale_px(8),0))
        self.status_label=self.label(actions,"●  DEMO LOCAL","good","bg",9,"bold")
        self.status_label.pack(side="left",padx=(0,self.scale_px(12)))
        RoundedButton(actions,self,"Atualizar UI-debug",lambda:self.check_update_async(user_initiated=True),
                      variant="secondary",width=145,height=38).pack(side="left")
        self.toast_label=self.label(self.main,"","accent2","bg",9,"normal")
        self.toast_label.pack(anchor="w",pady=(0,self.scale_px(6)))
        self.pages_area=tk.Frame(self.main,bg=self.colors["bg"],bd=0,highlightthickness=0)
        self.pages_area.pack(fill="both",expand=True)

    def _build_pages(self):
        self.page_frames: dict[str, tk.Frame] = {}
        self.page_panes: dict[str, ScrollPane] = {}
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
            self.page_panes[key] = pane
            pane.pack(fill="both", expand=True)
            builder(pane.body)

    def _tint_nav_icon(self, nav, tag, color):
        """Retint supersampled icon images when available, otherwise retint vector strokes."""
        spec = getattr(nav, "_nav_icon_specs", {}).get(tag)
        if spec:
            key, scale, item_id = spec
            photo = render_nav_icon_image(key, color, self.colors["accent2"], scale=scale, master=nav)
            if photo is not None:
                nav.itemconfigure(item_id, image=photo)
                nav._nav_icon_photos[tag] = photo
                return
        for item_tag, options in (
            ("nav-icon-line", {"fill": color, "width": 2.9 * self.ui_scale}),
            ("nav-icon-text", {"fill": color}),
            ("nav-icon-outline", {"outline": color, "width": 2.8 * self.ui_scale}),
            ("nav-icon-filled", {"fill": color, "outline": color}),
        ):
            try:
                nav.itemconfigure(item_tag, **options)
            except tk.TclError:
                pass

    def _route_wheel(self, event):
        pane = getattr(self, "page_panes", {}).get(self.current_page)
        if pane is None or not pane.winfo_ismapped() or not pane._event_inside(event):
            return None
        button = getattr(event, "num", None)
        if button == 4:
            pane.canvas.yview_scroll(-2, "units")
            return "break"
        if button == 5:
            pane.canvas.yview_scroll(2, "units")
            return "break"
        return pane._wheel(event)

    def _startup_splash_finished(self):
        self.splash = None
        try:
            self.root.deiconify(); self.root.lift(); self.root.focus_force()
        except tk.TclError:
            pass
        for mark in self.orbital_marks:
            mark.start_animation()
        if self.settings.get("update_check_on_startup", True):
            try: self.root.after(900, self.check_update_async)
            except tk.TclError: pass

    def label(self, parent, text, fg_key="fg", bg_key="panel", size=10, weight="normal", wraplength=None, **kwargs):
        scaled_size = self.scale_px(size)
        widget = tk.Label(
            parent, text=text, bg=self.colors[bg_key], fg=self.colors[fg_key],
            font=("Segoe UI", scaled_size, weight), anchor=kwargs.pop("anchor", "w"),
            justify=kwargs.pop("justify", "left"), bd=0, highlightthickness=0,
            wraplength=wraplength or 0, **kwargs,
        )
        widget._ui_fg_key = fg_key
        widget._ui_bg_key = bg_key
        # Cap requested text wrapping for small windows. Long labels must not
        # widen a card beyond the visible scroll area on a 960px-wide display.
        if wraplength:
            adaptive_cap = max(self.scale_px(650), int(self.root.winfo_screenwidth() * .56))
            widget.configure(wraplength=min(self.scale_px(wraplength), adaptive_cap))
        self.labels.append((widget, fg_key, bg_key, ("Segoe UI", scaled_size, weight)))
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
        widget = tk.Frame(parent, bg=self.colors["border"], height=self.scale_px(2))
        widget.pack(fill="x", padx=self.scale_px(16))
        widget._ui_bg_key = "border"
        return widget

    def _title_block(self, parent, eyebrow, title, subtitle):
        self.label(parent, eyebrow.upper(), "accent2", "bg", 8, "bold").pack(anchor="w", pady=(0, 6))
        self.label(parent, title, "fg", "bg", 20, "bold").pack(anchor="w")
        self.label(parent, subtitle, "muted", "bg", 10, "normal", wraplength=920).pack(anchor="w", pady=(5, 16))

    def _mock_action(self, label):
        self.toast(label + " — demonstração visual; nenhuma operação real foi iniciada.")

    def _draw_thumbnail_placeholder(self, canvas, title="Prévia da mídia", seed=0):
        """Draw a polished offline thumbnail placeholder until real artwork arrives."""
        canvas.delete("thumbnail-art")
        canvas.delete("thumbnail-image")
        try:
            width = max(self.scale_px(100), canvas.winfo_width(), int(canvas.cget("width")))
            height = max(self.scale_px(56), canvas.winfo_height(), int(canvas.cget("height")))
        except (tk.TclError, ValueError):
            width, height = self.scale_px(220), self.scale_px(124)
        palettes = (
            ("#17112C", "#7542C8", "#56E6D6"),
            ("#101D32", "#3379B9", "#A77AFF"),
            ("#24132B", "#C04D9A", "#65D8E6"),
            ("#11162A", "#4E58BA", "#70E8C0"),
            ("#17142D", "#904DC6", "#FF93C8"),
        )
        base, bright, highlight = palettes[int(seed) % len(palettes)]
        for index in range(28):
            x0 = width * index / 28
            x1 = width * (index + 1) / 28 + 1
            color = blend_hex(base, bright, .07 + .38 * index / 27)
            canvas.create_rectangle(x0, 0, x1, height, fill=color, outline="", tags="thumbnail-art")
        canvas.create_oval(width*.58, -height*.45, width*1.08, height*.78,
                           fill=blend_hex(base, highlight, .23), outline="", tags="thumbnail-art")
        canvas.create_oval(width*.66, -height*.34, width*.99, height*.44,
                           fill=blend_hex(base, highlight, .45), outline="", tags="thumbnail-art")
        canvas.create_polygon(
            0, height*.88, width*.22, height*.42, width*.39, height*.7,
            width*.62, height*.31, width*.85, height*.76, width, height*.58,
            width, height, 0, height,
            fill=blend_hex(base, "#0B0D1C", .62), outline="", smooth=True,
            splinesteps=20, tags="thumbnail-art",
        )
        canvas.create_line(width*.05,height*.86,width*.24,height*.49,width*.40,height*.70,
                           fill=blend_hex(highlight,"#FFFFFF",.08),width=max(1,self.ui_scale),
                           smooth=True,splinesteps=12,tags="thumbnail-art")
        canvas.create_oval(width*.5-self.scale_px(17),height*.42-self.scale_px(17),
                           width*.5+self.scale_px(17),height*.42+self.scale_px(17),
                           fill=blend_hex(base, "#090B18", .15),outline=highlight,
                           width=max(1,self.ui_scale),tags="thumbnail-art")
        canvas.create_polygon(
            width*.5-self.scale_px(4),height*.42-self.scale_px(8),
            width*.5-self.scale_px(4),height*.42+self.scale_px(8),
            width*.5+self.scale_px(9),height*.42,
            fill="#F7F5FF",outline="",smooth=True,splinesteps=12,tags="thumbnail-art",
        )
        canvas.create_rectangle(0,height-self.scale_px(23),width,height,fill="#080A14",outline="",tags="thumbnail-art")
        short_title = (str(title or "PRÉVIA DA MÍDIA").strip() or "PRÉVIA DA MÍDIA")
        if len(short_title) > 34:
            short_title = short_title[:31] + "…"
        canvas.create_text(self.scale_px(9),height-self.scale_px(11),text=short_title,anchor="w",
                           fill="#EAE7FF",font=("Segoe UI",max(7,self.scale_px(8)),"bold"),
                           tags="thumbnail-art")
        canvas.create_rectangle(1,1,width-1,height-1,outline=self.colors["border"],
                                width=max(1,1.2*self.ui_scale),tags="thumbnail-art")

    def _install_thumbnail(self, canvas, image_bytes):
        """Show a fetched poster; Pillow is optional and Tk native formats are tried first."""
        if not image_bytes:
            return False
        width = max(self.scale_px(80), canvas.winfo_width(), int(canvas.cget("width")))
        height = max(self.scale_px(45), canvas.winfo_height(), int(canvas.cget("height")))
        try:
            try:
                from PIL import Image, ImageOps, ImageTk
            except ImportError:
                photo = tk.PhotoImage(master=self.root, data=base64.b64encode(image_bytes).decode("ascii"))
                factor = max(1, math.ceil(photo.width()/width), math.ceil(photo.height()/height))
                if factor > 1:
                    photo = photo.subsample(factor, factor)
            else:
                with Image.open(io.BytesIO(image_bytes)) as source:
                    resampling = getattr(Image, "Resampling", Image)
                    lanczos = getattr(resampling, "LANCZOS", 1)
                    image = ImageOps.fit(source.convert("RGB"), (width, height), method=lanczos)
                photo = ImageTk.PhotoImage(image, master=self.root)
            canvas.delete("thumbnail-art")
            canvas.delete("thumbnail-image")
            canvas.create_image(width/2, height/2, image=photo, anchor="center", tags="thumbnail-image")
            canvas._thumbnail_photo = photo
            return True
        except Exception:
            return False

    def _schedule_ui(self, callback):
        try:
            self.root.after(0, callback)
        except tk.TclError:
            pass

    def preview_media_async(self):
        """Resolve the current URL's title/thumbnail in a worker; no media files are downloaded."""
        if self._preview_busy:
            self.toast("Já existe uma prévia de mídia em andamento.")
            return
        url_widget = getattr(self, "media_url_entry", None)
        url = url_widget.get().strip() if url_widget is not None else ""
        if not url:
            self.toast("Cole um link de vídeo ou áudio antes de pedir a prévia.")
            return
        self._preview_busy = True
        self.media_preview_status.configure(text="Consultando informações e miniatura…")
        self.media_preview_title.configure(text="Buscando mídia…")
        self.media_preview_channel.configure(text="Apenas metadados; nenhum arquivo será baixado.")
        self._draw_thumbnail_placeholder(self.media_preview_canvas, "BUSCANDO PRÉVIA", 0)

        def worker():
            try:
                metadata = fetch_preview_metadata(url, playlist=False)
                image_data = fetch_thumbnail_bytes(metadata.get("thumbnail_url"))
                error = None
            except Exception as exc:
                metadata, image_data, error = None, None, str(exc)
            self._schedule_ui(lambda: self._finish_media_preview(metadata, image_data, error))

        threading.Thread(target=worker, name="ui-debug-media-preview", daemon=True).start()

    def _finish_media_preview(self, metadata, image_data, error=None):
        self._preview_busy = False
        if error or not metadata:
            self.current_media_metadata = None
            self.media_preview_title.configure(text="Não foi possível gerar a prévia")
            self.media_preview_channel.configure(text=(error or "A fonte não retornou metadados."))
            self.media_preview_status.configure(text="Ajuste o link e tente novamente.")
            self._draw_thumbnail_placeholder(self.media_preview_canvas, "PRÉVIA INDISPONÍVEL", 3)
            self.toast("A prévia não foi gerada. Veja a mensagem no cartão de mídia.")
            return
        self.current_media_metadata = metadata
        title = str(metadata.get("title") or "Mídia sem título")
        channel = str(metadata.get("channel") or "Canal não informado")
        duration = str(metadata.get("duration_text") or "Duração desconhecida")
        self.media_preview_title.configure(text=title)
        self.media_preview_channel.configure(text=f"{channel}  •  {duration}")
        if image_data and self._install_thumbnail(self.media_preview_canvas, image_data):
            self.media_preview_status.configure(text="Miniatura real carregada • não iniciou download.")
        else:
            self._draw_thumbnail_placeholder(self.media_preview_canvas, title, 1)
            if image_data:
                self.media_preview_status.configure(text="Metadados prontos. Instale Pillow para exibir miniaturas JPG/WebP.")
            else:
                self.media_preview_status.configure(text="Metadados prontos; a fonte não forneceu miniatura.")
        self.toast("Prévia carregada. Nenhum arquivo de mídia foi baixado.")

    def preview_playlist_async(self):
        """Load playlist entries and thumbnail posters without downloading media."""
        if self._playlist_preview_busy:
            self.toast("Já existe uma análise de lista em andamento.")
            return
        url_widget = getattr(self, "media_url_entry", None)
        url = url_widget.get().strip() if url_widget is not None else ""
        if not url:
            self.toast("Cole o link da playlist no campo da página Início primeiro.")
            return
        self._playlist_preview_busy = True
        if self.playlist_count_label is not None:
            self.playlist_count_label.configure(text="Analisando lista…")
        self.toast("Lendo título, duração e miniaturas dos primeiros itens…")

        def worker():
            try:
                metadata = fetch_preview_metadata(url, playlist=True, max_items=20)
                items = metadata.get("items") or [metadata]
                items = [dict(item) for item in items[:20]]
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    futures = {
                        pool.submit(fetch_thumbnail_bytes, item.get("thumbnail_url")): index
                        for index, item in enumerate(items) if item.get("thumbnail_url")
                    }
                    for future, index in futures.items():
                        try:
                            items[index]["thumbnail_bytes"] = future.result(timeout=11)
                        except Exception:
                            items[index]["thumbnail_bytes"] = None
                error = None
            except Exception as exc:
                metadata, items, error = None, [], str(exc)
            self._schedule_ui(lambda: self._finish_playlist_preview(metadata, items, error))

        threading.Thread(target=worker, name="ui-debug-playlist-preview", daemon=True).start()

    def _finish_playlist_preview(self, metadata, items, error=None):
        self._playlist_preview_busy = False
        if error:
            if self.playlist_count_label is not None:
                self.playlist_count_label.configure(text="Não foi possível analisar")
            self.toast(error)
            return
        self._render_playlist_rows(items)
        selected = sum(1 for index, item in enumerate(items) if item.get("selected", index < 2))
        if self.playlist_count_label is not None:
            self.playlist_count_label.configure(text=f"{len(items)} itens detectados  •  {selected} selecionados")
        if self.playlist_selection_label is not None:
            self.playlist_selection_label.configure(text=f"{selected} itens selecionados")
        self.toast(f"Prévia da lista pronta: {len(items)} itens. Nenhum arquivo foi baixado.")

    def _render_playlist_rows(self, items):
        if not hasattr(self, "playlist_rows_container"):
            return
        self._playlist_photo_refs.clear()
        for child in self.playlist_rows_container.winfo_children():
            child.destroy()
        for index, source in enumerate(items):
            item = dict(source)
            title = str(item.get("title") or "Mídia sem título")
            channel = str(item.get("channel") or "Canal não informado")
            duration = str(item.get("duration_text") or "Duração desconhecida")
            selected = bool(item.get("selected", index < 2))
            row = self.frame(self.playlist_rows_container, "panel2",
                             padx=self.scale_px(10), pady=self.scale_px(8))
            row.pack(fill="x", pady=(0,self.scale_px(7)))
            thumb = tk.Canvas(row, width=self.scale_px(124), height=self.scale_px(70),
                              bg=self.colors["surface"], bd=0, highlightthickness=0, cursor="hand2")
            thumb.pack(side="left", padx=(0,self.scale_px(12)))
            self._draw_thumbnail_placeholder(thumb, title, index)
            if item.get("thumbnail_bytes"):
                self._install_thumbnail(thumb, item.get("thumbnail_bytes"))
                if hasattr(thumb, "_thumbnail_photo"):
                    self._playlist_photo_refs.append(thumb._thumbnail_photo)
            info = self.frame(row, "panel2")
            info.pack(side="left", fill="both", expand=True)
            check = "☑" if selected else "□"
            self.label(info, check + "  " + title, "accent2" if selected else "fg", "panel2", 10, "bold",
                       wraplength=700).pack(anchor="w")
            self.label(info, f"{channel}  •  {duration}", "muted", "panel2", 8).pack(anchor="w", pady=(self.scale_px(4),0))
            status = str(item.get("status") or ("Disponível" if selected else "Ignorado"))
            self.label(row,status,"accent2" if selected else "muted","panel2",8,"bold").pack(side="right",padx=(self.scale_px(10),0))
            if item.get("url"):
                thumb.bind("<Button-1>", lambda _event, media=item: self._select_playlist_item(media))
                info.bind("<Button-1>", lambda _event, media=item: self._select_playlist_item(media))
                row.configure(cursor="hand2")

    def _select_playlist_item(self, item):
        url = str(item.get("url") or "")
        if url and hasattr(self, "media_url_entry"):
            self.media_url_entry.delete(0, "end")
            self.media_url_entry.insert(0, url)
        image_data = item.get("thumbnail_bytes")
        self.show_page("home")
        self._finish_media_preview(dict(item), image_data, None)

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
        url.entry.insert(0, "https://www.youtube.com/watch?v=aqz-KE-bpKQ")
        url.entry.bind("<FocusIn>", lambda _event: self.toast("A miniatura só é buscada quando você pede a prévia."))
        self.media_url_entry = url.entry

        preview_actions = self.frame(inside, "panel2")
        preview_actions.pack(fill="x", pady=(self.scale_px(9), self.scale_px(10)))
        self.button(preview_actions, "Pré-visualizar mídia", self.preview_media_async,
                    "secondary", width=172).pack(side="left", padx=(0,self.scale_px(10)))
        self.label(preview_actions, "Consulta título/miniatura; não baixa o arquivo.", "muted", "panel2", 8).pack(side="left", anchor="center")

        media_preview = self.card(inside, background_key="surface", padding=12)
        media_preview.pack(fill="x", pady=(0,self.scale_px(12)))
        preview_row = self.frame(media_preview.body, "surface")
        preview_row.pack(fill="x")
        self.media_preview_canvas = tk.Canvas(
            preview_row, width=self.scale_px(220), height=self.scale_px(124),
            bg=self.colors["surface"], bd=0, highlightthickness=0,
        )
        self.media_preview_canvas.pack(side="left", padx=(0,self.scale_px(14)))
        self._draw_thumbnail_placeholder(self.media_preview_canvas, "PRÉVIA DO VÍDEO", 0)
        preview_details = self.frame(preview_row, "surface")
        preview_details.pack(side="left", fill="both", expand=True)
        self.media_preview_title = self.label(preview_details, "Nenhuma prévia carregada", "fg", "surface", 13, "bold", wraplength=800)
        self.media_preview_title.pack(anchor="w")
        self.media_preview_channel = self.label(preview_details, "Insira um link e pressione Pré-visualizar.", "muted", "surface", 9, "normal", wraplength=820)
        self.media_preview_channel.pack(anchor="w", pady=(self.scale_px(7),0))
        self.media_preview_status = self.label(preview_details, "Aguardando solicitação • downloads continuam simulados.", "accent2", "surface", 8)
        self.media_preview_status.pack(anchor="w", pady=(self.scale_px(12),0))

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
            actions, "Analisar playlist", self.preview_playlist_async,
            "secondary", width=140,
        ).pack(side="right", padx=(0, 8))

        progress = self.card(body, padding=16)
        progress.pack(fill="x", pady=(0, 12))
        header = self.frame(progress.body, "panel")
        header.pack(fill="x")
        self.label(header, "Sessão de demonstração", "fg", "panel", 12, "bold").pack(side="left")
        self.label(header, "28%", "accent2", "panel", 11, "bold").pack(side="right")
        signal = tk.Canvas(header, width=self.scale_px(132), height=self.scale_px(24),
                           bg=self.colors["panel"], bd=0, highlightthickness=0)
        signal.pack(side="right", padx=(self.scale_px(12),self.scale_px(8)))
        signal._ui_bg_key = "panel"
        def draw_demo_signal(_event=None):
            signal.delete("signal-line")
            width, height = max(24,signal.winfo_width()), max(12,signal.winfo_height())
            levels = (.64,.62,.70,.48,.62,.28,.44,.80,.38,.53,.30,.66,.58,.24,.48,.63)
            coords = []
            for index, level in enumerate(levels):
                coords.extend((4+(width-8)*index/(len(levels)-1), height*level))
            signal.create_line(*coords, fill=blend_hex(self.colors["accent"],self.colors["accent2"],.45),
                width=max(2.2,2.8*self.ui_scale), smooth=True, splinesteps=12,
                capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="signal-line")
            signal.create_line(*coords, fill=self.colors["accent2"], width=max(1.0,1.2*self.ui_scale),
                smooth=True, splinesteps=12, capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="signal-line")
        signal.bind("<Configure>",draw_demo_signal,add="+")
        signal.after_idle(draw_demo_signal)
        self.mini_graphs.append((signal,draw_demo_signal))
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
        self.playlist_count_label = self.label(top, "3 itens de demonstração  ·  2 selecionados", "accent2", "panel", 9, "bold")
        self.playlist_count_label.pack(side="right")
        self.label(intro.body, "Cada item tem miniatura; pressione Analisar playlist na página Início para carregar títulos e imagens reais quando a fonte for compatível.", "muted", "panel", 9, "normal", wraplength=900).pack(anchor="w", pady=(8, 0))
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
        self.label(table.body, "MINIATURA  •  TÍTULO  •  CANAL  •  DURAÇÃO", "muted", "panel", 8, "bold").pack(anchor="w", pady=(0,self.scale_px(8)))
        self.playlist_rows_container = self.frame(table.body, "panel")
        self.playlist_rows_container.pack(fill="x")
        sample_items = [
            {"title":"Aurora — paisagem","channel":"Vídeo demonstrativo","duration_text":"04:32","selected":True,"status":"Disponível","format":"Vídeo","quality":"1080p"},
            {"title":"Noite orbital","channel":"Áudio demonstrativo","duration_text":"03:18","selected":True,"status":"Disponível","format":"MP3","quality":"192 kbps"},
            {"title":"Sinal distante","channel":"Vídeo demonstrativo","duration_text":"05:11","selected":False,"status":"Ignorado","format":"Vídeo","quality":"720p"},
        ]
        self._render_playlist_rows(sample_items)
        footer = self.frame(table.body, "panel")
        footer.pack(fill="x", pady=(8, 0))
        self.playlist_selection_label = self.label(footer, "2 itens selecionados", "muted", "panel", 9, "normal")
        self.playlist_selection_label.pack(side="left")
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
            swatch.create_polygon(*rounded_points(1,1,104,31,10,steps=18),fill="",outline=self.colors["border"],width=1.8,smooth=True,splinesteps=18,tags="swatch-outline")
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
        for key, (nav, shape, icon, label_id, indicator, plate) in self.nav_items.items():
            active = key == name
            c = self.colors
            nav.itemconfigure(shape, fill=blend_hex(c["panel2"], c["accent"], .13) if active else c["panel2"],
                              outline=c["accent"] if active else c["border"],
                              width=(1.5 if active else 1.0) * self.ui_scale)
            nav.itemconfigure(plate, fill=blend_hex(c["panel"], c["accent"], .14) if active else c["panel"])
            nav.itemconfigure(indicator, state=tk.NORMAL if active else tk.HIDDEN, fill=c["accent2"])
            self._tint_nav_icon(nav, icon, c["accent2"] if active else c["muted"])
            nav.itemconfigure(label_id, fill=c["fg"] if active else c["muted"],
                              font=("Segoe UI", self.scale_px(10), "bold" if active else "normal"))
        if name == "settings":
            self._sync_settings_controls()
        self.toast_label.configure(text=subtitle)

    def _nav_hover(self, name, hovered):
        if name == self.current_page:
            return
        nav, shape, icon, label_id, _indicator, plate = self.nav_items[name]
        c = self.colors
        nav.itemconfigure(shape, fill=c["surface"] if hovered else c["panel2"],
                          outline=blend_hex(c["border"], c["accent"], .35) if hovered else c["border"])
        nav.itemconfigure(plate, fill=blend_hex(c["panel"], c["surface"], .7) if hovered else c["panel"])
        self._tint_nav_icon(nav, icon, c["accent2"] if hovered else c["muted"])
        nav.itemconfigure(label_id, fill=c["fg"] if hovered else c["muted"])

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
        self.accent_preview.create_polygon(*rounded_points(1,1,width-1,13,6,steps=18),fill="",outline=self.colors["border"],width=1.8,smooth=True,splinesteps=18,tags="preview-outline")
        self.accent_preview.tag_raise("preview-outline")

    def _apply_scrollbar_style(self):
        """Use the same muted dark surface and accent as the rest of the prototype."""
        c = self.colors
        try:
            self.style.configure(
                "UI.Vertical.TScrollbar",
                gripcount=0,
                arrowsize=0,
                background=c["panel2"],
                darkcolor=c["panel2"],
                lightcolor=c["panel2"],
                troughcolor=c["bg"],
                bordercolor=c["border"],
                arrowcolor=c["accent2"],
                relief="flat",
                width=self.scale_px(8),
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
        for graph, redraw in self.mini_graphs:
            try:
                graph.configure(bg=c["panel"])
                redraw()
            except tk.TclError:
                pass
        try:
            self.backdrop._resize(None)
        except (AttributeError, tk.TclError):
            pass
        if hasattr(self, "nav_items"):
            for key, (nav, shape, icon, label_id, indicator, plate) in self.nav_items.items():
                active = key == self.current_page
                nav.configure(bg=c["panel"])
                nav.itemconfigure(shape, fill=blend_hex(c["panel2"], c["accent"], .13) if active else c["panel2"],
                                  outline=c["accent"] if active else c["border"],
                                  width=(1.5 if active else 1.0) * self.ui_scale)
                nav.itemconfigure(plate, fill=blend_hex(c["panel"], c["accent"], .14) if active else c["panel"])
                nav.itemconfigure(indicator, state=tk.NORMAL if active else tk.HIDDEN, fill=c["accent2"])
                self._tint_nav_icon(nav, icon, c["accent2"] if active else c["muted"])
                nav.itemconfigure(label_id, fill=c["fg"] if active else c["muted"],
                                  font=("Segoe UI", self.scale_px(10), "bold" if active else "normal"))
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
            try: mark.stop_animation(); mark.destroy()
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
