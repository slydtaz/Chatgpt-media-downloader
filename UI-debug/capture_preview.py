from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, ImageGrab

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "UI-debug"

# Isolate the screenshot session from any real downloader or prototype preferences.
PROFILE = tempfile.mkdtemp(prefix="ui-debug-preview-")
os.environ["LOCALAPPDATA"] = PROFILE
os.environ["XDG_CONFIG_HOME"] = PROFILE
sys.path.insert(0, str(APP_DIR))

import ui_debug  # noqa: E402

PAGES = [
    ("home", "01-home.png", "Início"),
    ("playlist", "02-playlists.png", "Playlists"),
    ("settings", "03-aparencia.png", "Aparência"),
    ("dependencies", "04-dependencias.png", "Dependências"),
    ("updates", "05-atualizacoes.png", "Atualizações"),
    ("help", "06-ajuda.png", "Ajuda"),
    ("diagnostics", "07-diagnostico.png", "Diagnóstico"),
]


def _font(size: int):
    for candidate in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def capture_window(root, max_width=1280):
    root.update_idletasks()
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    width, height = root.winfo_width(), root.winfo_height()
    if width < 800 or height < 600:
        raise RuntimeError("A janela do UI-debug não foi renderizada no tamanho esperado: %sx%s" % (width, height))
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True).convert("RGB")
    if image.width > max_width:
        new_height = round(image.height * max_width / image.width)
        image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
    return image


def make_contact_sheet(items, target: Path):
    thumb_w, thumb_h, label_h = 540, 350, 34
    margin, gap, columns = 24, 18, 2
    rows = (len(items) + columns - 1) // columns
    canvas = Image.new(
        "RGB",
        (margin * 2 + columns * thumb_w + gap * (columns - 1),
         64 + margin + rows * (thumb_h + label_h + gap)),
        "#080D19",
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 16), "UI-debug 0.1.0-dev.3  —  prévia da interface espacial", font=_font(24), fill="#F3F6FF")
    for index, (label, image) in enumerate(items):
        col, row = index % columns, index // columns
        x = margin + col * (thumb_w + gap)
        y = 64 + row * (thumb_h + label_h + gap)
        thumb = image.copy()
        thumb.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        canvas.paste(thumb, (x, y))
        draw.rounded_rectangle((x, y, x + thumb.width - 1, y + thumb.height - 1), radius=9, outline="#354466", width=2)
        draw.text((x, y + thumb_h + 7), label, font=_font(17), fill="#C9D5F2")
    canvas.save(target, format="PNG", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the real, standalone UI-debug screens.")
    parser.add_argument("--output", default="ui-debug-preview", help="Directory for screenshots and report.")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)

    # Disable startup network checks in the isolated preview profile.
    settings_path = object.__new__(ui_debug.SpaceUIPrototype)._settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = dict(ui_debug.DEFAULT_SETTINGS)
    settings["update_check_on_startup"] = False
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    import tkinter as tk

    root = tk.Tk()
    captures = []
    try:
        root.title("UI-debug 0.1.0-dev.3 — prévia")
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        desktop_w, desktop_h = ImageGrab.grab().size
        width = max(960, min(1200, screen_w - 40, desktop_w - 32))
        # Leave room for the Windows title bar and taskbar; the full client area
        # still fits the prototype's minimum size on the hosted screenshot runner.
        height = max(620, min(700, screen_h - 120, desktop_h - 120))
        root.geometry("%sx%s+4+4" % (width, height))
        root.update_idletasks()

        app = ui_debug.SpaceUIPrototype(root)
        root.geometry("%sx%s+4+4" % (width, height))
        root.deiconify()
        root.lift()
        try:
            root.focus_force()
        except tk.TclError:
            pass
        root.update()
        time.sleep(0.35)
        root.update()

        for page_key, filename, label in PAGES:
            app.show_page(page_key)
            root.update_idletasks()
            root.update()
            time.sleep(0.12)
            image = capture_window(root)
            image.save(output / filename, format="PNG", optimize=True)
            captures.append((label, image))
            print("CAPTURED %s %sx%s" % (filename, image.width, image.height), flush=True)

        make_contact_sheet(captures, output / "visao-geral-ui-debug.png")
        report = {
            "version": ui_debug.APP_VERSION,
            "channel": ui_debug.CHANNEL,
            "pages": [{"key": key, "file": filename, "label": label} for key, filename, label in PAGES],
            "production_modules_imported": False,
            "media_downloads_started": False,
            "dependency_installations_started": False,
            "network_update_checks_started": False,
            "github_release_created": False,
            "note": "Capturas reais da janela Tk do protótipo em CI; escala e fontes podem variar entre computadores.",
        }
        (output / "LEIA-ME.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("UI-DEBUG PREVIEW CAPTURE SUCCESS", flush=True)
        return 0
    finally:
        try:
            root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
