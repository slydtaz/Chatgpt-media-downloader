from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import ctypes
from ctypes import wintypes
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageGrab

# Ensure app configuration/logs are isolated from a real user profile.
ISOLATED_PROFILE = tempfile.mkdtemp(prefix="cgmd-ui-preview-")
os.environ["LOCALAPPDATA"] = ISOLATED_PROFILE
os.environ.setdefault("CGMD_PREVIEW_MODE", "1")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.config import VERSION  # noqa: E402
from app.gui import MediaDownloaderApp  # noqa: E402


class _POINTL(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD), ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD), ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD), ("dmPosition", _POINTL),
        ("dmDisplayOrientation", wintypes.DWORD), ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", wintypes.SHORT), ("dmDuplex", wintypes.SHORT),
        ("dmYResolution", wintypes.SHORT), ("dmTTOption", wintypes.SHORT),
        ("dmCollate", wintypes.SHORT), ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD),
    ]


def _set_capture_resolution(width: int = 1440, height: int = 900) -> bytes | None:
    """Ask the Windows CI desktop for the target capture size; keep the original mode."""
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    current = _DEVMODEW()
    current.dmSize = ctypes.sizeof(_DEVMODEW)
    if not user32.EnumDisplaySettingsW(None, -1, ctypes.byref(current)):
        raise RuntimeError("Não foi possível consultar a resolução de tela do runner Windows.")
    snapshot = bytes(current)
    if current.dmPelsWidth == width and current.dmPelsHeight == height:
        return None
    desired = _DEVMODEW.from_buffer_copy(snapshot)
    desired.dmFields = 0x00080000 | 0x00100000  # DM_PELSWIDTH | DM_PELSHEIGHT
    desired.dmPelsWidth = width
    desired.dmPelsHeight = height
    result = user32.ChangeDisplaySettingsW(ctypes.byref(desired), 0)
    if result != 0:
        raise RuntimeError(f"O runner não aceitou a resolução de captura {width}x{height} (código {result}).")
    return snapshot


def _restore_capture_resolution(snapshot: bytes | None) -> None:
    if os.name != "nt" or snapshot is None:
        return
    try:
        original = _DEVMODEW.from_buffer_copy(snapshot)
        ctypes.windll.user32.ChangeDisplaySettingsW(ctypes.byref(original), 0)
    except Exception:
        pass


PAGES = [
    ("home", "01-inicio.png", "Início"),
    ("playlist", "02-playlists.png", "Playlists"),
    ("settings", "03-configuracoes.png", "Configurações"),
    ("dependencies", "04-dependencias.png", "Dependências"),
    ("updates", "05-atualizacoes.png", "Atualizações"),
    ("help", "06-ajuda.png", "Ajuda"),
    ("developer", "07-diagnostico.png", "Diagnóstico"),
]


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in ("arial.ttf", "segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _capture_window(root, *, width_limit: int = 1440) -> Image.Image:
    root.update_idletasks()
    root.update()
    x = root.winfo_rootx()
    y = root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    if width < 400 or height < 300:
        raise RuntimeError(f"Janela pequena ou ainda não renderizada: {width}x{height}")
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True).convert("RGB")
    if image.width > width_limit:
        new_height = round(image.height * width_limit / image.width)
        image = image.resize((width_limit, new_height), Image.Resampling.LANCZOS)
    return image


def _wait_for_page(root, app, page_name: str, timeout: float = 4.0) -> None:
    app.show_page(page_name)
    deadline = time.monotonic() + timeout
    while (
        app._visible_page != page_name
        or app._page_animation_job is not None
    ) and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    root.update_idletasks()
    if (
        app.current_page != page_name
        or app._visible_page != page_name
        or app._page_animation_job is not None
    ):
        raise RuntimeError(f"A transição para a página {page_name!r} não terminou.")


def _make_contact_sheet(items: list[tuple[str, Image.Image]], target: Path) -> None:
    thumb_w, thumb_h = 480, 300
    label_h, margin, gap = 38, 24, 22
    columns = 2
    rows = (len(items) + columns - 1) // columns
    canvas = Image.new(
        "RGB",
        (margin * 2 + columns * thumb_w + gap * (columns - 1),
         50 + margin + rows * (thumb_h + label_h + gap)),
        "#0A0F1B",
    )
    draw = ImageDraw.Draw(canvas)
    title_font = _font(25)
    label_font = _font(17)
    draw.text((margin, 10), f"ChatGPT Media Downloader {VERSION} — prévia real da interface", font=title_font, fill="#F3F6FC")
    top_offset = 50
    for index, (label, image) in enumerate(items):
        col, row = index % columns, index // columns
        x = margin + col * (thumb_w + gap)
        y = top_offset + row * (thumb_h + label_h + gap)
        thumbnail = image.copy()
        thumbnail.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        canvas.paste(thumbnail, (x, y))
        draw.rectangle((x, y, x + thumbnail.width - 1, y + thumbnail.height - 1), outline="#3B4964", width=2)
        draw.text((x, y + thumb_h + 7), label, font=label_font, fill="#DCE6FC")
    canvas.save(target, format="PNG", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture real GUI screenshots for review.")
    parser.add_argument("--output", default="ui-preview-output", help="Directory for real PNG screenshots and report.")
    args = parser.parse_args()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    original_refresh = MediaDownloaderApp._refresh_dependencies
    original_update_check = MediaDownloaderApp._maybe_start_update_check
    original_uninstall = MediaDownloaderApp._uninstall

    root = None
    original_display_mode = None
    captured: list[tuple[str, Image.Image]] = []
    try:
        original_display_mode = _set_capture_resolution(1440, 900)
        # Never scan/install media tools, check for updates or trigger uninstall/downloads.
        MediaDownloaderApp._refresh_dependencies = lambda self, force=False: None
        MediaDownloaderApp._maybe_start_update_check = lambda self: None
        MediaDownloaderApp._uninstall = lambda self: None

        import tkinter as tk

        root = tk.Tk()
        root.title(f"ChatGPT Media Downloader {VERSION} — prévia da interface")
        # Match the requested review canvas using the real Windows desktop mode.
        desktop_width, desktop_height = ImageGrab.grab().size
        if (desktop_width, desktop_height) != (1440, 900):
            raise RuntimeError(f"Resolução física inesperada do desktop: {desktop_width}x{desktop_height}; esperado 1440x900.")
        capture_width, capture_height = 1440, 900
        root.geometry(f"{capture_width}x{capture_height}+0+0")
        app = MediaDownloaderApp(root)
        # MediaDownloaderApp sets its normal 1220x820 default during construction;
        # override it after initialization only for this bounded screenshot harness.
        root.geometry(f"{capture_width}x{capture_height}+0+0")
        root.attributes("-fullscreen", True)
        root.update_idletasks()
        root.deiconify()
        root.lift()
        try:
            root.focus_force()
        except tk.TclError:
            pass
        root.update()
        time.sleep(0.6)
        root.update()

        # Capture the application's actual animated loading screen before it dismisses.
        loading_image = _capture_window(root)
        loading_file = "00-tela-carregamento.png"
        loading_image.save(output_dir / loading_file, format="PNG", optimize=True)
        captured.append(("Tela de carregamento animada", loading_image))
        print(f"CAPTURED {loading_file} {loading_image.width}x{loading_image.height}", flush=True)
        app._dismiss_loading_splash(immediate=True)
        root.update()

        # Capture the actual preview widget with an offline fixture: no URLs are
        # submitted, no external host is contacted, and no media is downloaded.
        app._show_media_preview_card()
        app.media_preview_title_var.set("Big Buck Bunny — prévia demonstrativa")
        app.media_preview_meta_var.set("Blender Foundation  •  9:56  •  exemplo local")
        app.media_preview_status_var.set("DEMONSTRAÇÃO OFFLINE · sem acessar a internet")
        demo_image = _capture_window(root)
        demo_file = "00-preview-automatica.png"
        demo_image.save(output_dir / demo_file, format="PNG", optimize=True)
        captured.append(("Prévia automática (demonstração offline)", demo_image))
        print(f"CAPTURED {demo_file} {demo_image.width}x{demo_image.height}", flush=True)
        app._hide_media_preview_card()

        for page_name, filename, label in PAGES:
            _wait_for_page(root, app, page_name)
            time.sleep(0.18)
            root.update()
            image = _capture_window(root)
            image.save(output_dir / filename, format="PNG", optimize=True)
            captured.append((label, image))
            print(f"CAPTURED {filename} {image.width}x{image.height}", flush=True)

        _make_contact_sheet(captured, output_dir / "visao-geral.png")

        report = {
            "application_version": VERSION,
            "media_preview_demo_file": "00-preview-automatica.png",
            "media_preview_demo_network_requests": 0,
            "capture_method": "Pillow ImageGrab from the real fullscreen Tk window at 1440x900 on a Windows GitHub Actions runner",
            "capture_resolution": "1440x900",
            "loading_screen_file": "00-tela-carregamento.png",
            "pages": [{"key": key, "file": filename, "label": label} for key, filename, label in PAGES],
            "media_downloads_started": False,
            "dependency_scans_started": False,
            "update_checks_started": False,
            "note": "As capturas mostram a interface real renderizada em CI; escala/fontes podem variar em PCs diferentes.",
        }
        (output_dir / "LEIA-ME.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("PREVIEW CAPTURE SUCCESS", flush=True)
        return 0
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        MediaDownloaderApp._refresh_dependencies = original_refresh
        MediaDownloaderApp._maybe_start_update_check = original_update_check
        MediaDownloaderApp._uninstall = original_uninstall
        _restore_capture_resolution(original_display_mode)
        # We intentionally do not delete ISOLATED_PROFILE during the process lifetime:
        # the application logger may still hold an open file handle on Windows.


if __name__ == "__main__":
    raise SystemExit(main())
