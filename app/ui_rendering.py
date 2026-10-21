"""Antialiased Pillow rendering helpers for rounded desktop UI surfaces.

Tkinter Canvas polygons are not antialiased consistently across platforms. These
helpers render rounded surfaces at 3x resolution and downsample with Lanczos.
They are intentionally static; event handling and text remain native Tk widgets.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
except ImportError:  # The Canvas renderer remains available as a fallback.
    Image = ImageChops = ImageDraw = None


def _rgb(value: str) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return (10, 10, 20)
    try:
        return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return (10, 10, 20)


def _hex(value: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(v))) for v in value))


def _blend(first: str, second: str, amount: float) -> str:
    amount = max(0.0, min(1.0, float(amount)))
    a, b = _rgb(first), _rgb(second)
    return _hex(tuple(round(x * (1.0 - amount) + y * amount) for x, y in zip(a, b)))


def _cyclic_color(palette: Sequence[str], position: float) -> str:
    if not palette:
        return "#FFFFFF"
    if len(palette) == 1:
        return str(palette[0])
    scaled = (float(position) % 1.0) * len(palette)
    index = int(scaled)
    return _blend(str(palette[index]), str(palette[(index + 1) % len(palette)]), scaled - index)


def _dimensions(width: int, height: int) -> tuple[int, int]:
    return max(2, min(1800, int(width))), max(2, min(1100, int(height)))


def render_rounded_panel(
    width: int,
    height: int,
    *,
    backdrop: str,
    surface: str,
    border: str,
    radius: int = 15,
    border_width: float = 1.0,
    fill_palette: Sequence[str] = (),
    scale: int = 3,
):
    """Return an opaque RGB panel whose rounded perimeter is antialiased."""
    if Image is None or ImageDraw is None:
        return None
    width, height = _dimensions(width, height)
    scale = max(2, min(4, int(scale)))
    w, h = width * scale, height * scale
    r = max(0, min(int(radius * scale), w // 2, h // 2))
    edge = max(1, min(round(float(border_width) * scale), 4 * scale))
    box = (scale // 2, scale // 2, w - scale // 2 - 1, h - scale // 2 - 1)
    corner = max(0, min(r, (box[2] - box[0]) // 2, (box[3] - box[1]) // 2))
    image = Image.new("RGB", (w, h), _rgb(backdrop))

    if fill_palette:
        fill = Image.new("RGB", (w, h), _rgb(surface))
        fill_draw = ImageDraw.Draw(fill)
        # Draw a continuous horizontal gradient at supersampled resolution.
        for x in range(w):
            fill_draw.line((x, 0, x, h - 1), fill=_rgb(_cyclic_color(fill_palette, x / max(1, w - 1))))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=corner, fill=255)
        image.paste(fill, mask=mask)
    else:
        ImageDraw.Draw(image).rounded_rectangle(box, radius=corner, fill=_rgb(surface))

    ImageDraw.Draw(image).rounded_rectangle(
        box, radius=corner, outline=_rgb(border), width=edge,
    )
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    return image.resize((width, height), resampling).convert("RGB")


def render_rounded_button(
    width: int,
    height: int,
    *,
    backdrop: str,
    edge: str,
    top: str,
    bottom: str,
    outer_palette: Sequence[str] = (),
    inner_palette: Sequence[str] = (),
    hover_palette: Sequence[str] = (),
    hover: bool = False,
    hover_strength: float = 1.0,
    gradient_phase: float = 0.0,
    radius: int | None = None,
    scale: int = 4,
):
    """Render a transparent button background with smooth double gradient borders."""
    if Image is None or ImageDraw is None or ImageChops is None:
        return None
    width, height = _dimensions(width, height)
    # Buttons are small; 4x supersampling gives the round caps and pill corners
    # enough coverage without using expensive vector polygon approximations.
    scale = max(3, min(4, int(scale)))
    w, h = width * scale, height * scale
    base_radius = max(4, min(int(radius if radius is not None else height / 2 - 1), height // 2, width // 2))
    hover_strength = max(0.0, min(1.0, float(hover_strength)))
    gradient_phase = float(gradient_phase) % 1.0
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    outer_inset = 0.7
    mid_inset = 2.35
    inner_inset = 3.95
    def shape_mask(inset: float):
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        x0, y0 = round(inset * scale), round(inset * scale)
        x1, y1 = w - x0 - 1, h - y0 - 1
        radius_px = max(1, round((base_radius - inset) * scale))
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius_px, fill=255)
        return mask

    # The interior fill is clipped with a high-resolution round mask.
    fill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    fill_draw = ImageDraw.Draw(fill)
    for y in range(h):
        amount = y / max(1, h - 1)
        color = _blend(top, bottom, amount)
        if hover and hover_palette and hover_strength > 0:
            color = _blend(
                color,
                _cyclic_color(hover_palette, amount * 0.36 + gradient_phase),
                0.48 * hover_strength,
            )
        fill_draw.line((0, y, w - 1, y), fill=(*_rgb(color), 255))
    fill.putalpha(shape_mask(inner_inset))
    canvas.alpha_composite(fill)

    outer_mask = shape_mask(outer_inset)
    mid_mask = shape_mask(mid_inset)
    inner_mask = shape_mask(inner_inset)
    outer_ring = ImageChops.subtract(outer_mask, mid_mask)
    inner_ring = ImageChops.subtract(mid_mask, inner_mask)

    if hover and hover_strength > 0 and ImageFilter is not None:
        halo_mask = outer_ring.filter(ImageFilter.GaussianBlur(radius=max(1, round(scale * 2.0))))
        halo_mask = halo_mask.point(lambda value: round(value * hover_strength * 0.52))
        halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        halo_draw = ImageDraw.Draw(halo)
        for x in range(w):
            halo_color = _rgb(_cyclic_color(hover_palette or outer_palette, gradient_phase + x / max(1, w - 1)))
            halo_draw.line((x, 0, x, h - 1), fill=(*halo_color, 255))
        halo.putalpha(halo_mask)
        canvas.alpha_composite(halo)

    def paint_ring(mask, palette: Sequence[str], phase: float, solid: str):
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        if palette:
            # Per-column colors preserve a smooth continuous gradient. The mask
            # supplies fractional edge coverage after Lanczos downsampling.
            for x in range(w):
                col = _rgb(_cyclic_color(palette, phase + x / max(1, w - 1)))
                draw.line((x, 0, x, h - 1), fill=(*col, 255))
        else:
            draw.rectangle((0, 0, w - 1, h - 1), fill=(*_rgb(solid), 255))
        layer.putalpha(mask)
        canvas.alpha_composite(layer)

    paint_ring(outer_ring, outer_palette, 0.03 + gradient_phase, edge)
    if inner_palette:
        paint_ring(inner_ring, inner_palette, 0.39 - gradient_phase * 0.73, edge)
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    return canvas.resize((width, height), resampling)


__all__ = ["render_rounded_panel", "render_rounded_button"]
