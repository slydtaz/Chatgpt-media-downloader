"""Static, settings-driven neon effects for the desktop UI.

Pillow is already used by the application's packaged build. This module generates
local artwork only: it performs no network requests and never downloads media.
The output is static by design; motion is intentionally not implemented here.
"""
from __future__ import annotations

import math
import random

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:  # Tkinter/vector fallback is maintained by the GUI layer.
    Image = ImageDraw = ImageFilter = None


PALETTES: dict[str, tuple[str, ...]] = {
    "cosmic": ("#743BEB", "#4F46E5", "#1687F8", "#21B6EB", "#B52CE3"),
    "nebula": ("#6526D9", "#8429E8", "#4338CA", "#A72ACD", "#D946EF"),
    "aurora": ("#6D28D9", "#2563EB", "#0891B2", "#10B981", "#6366F1"),
    "ocean": ("#4338CA", "#2563EB", "#0284C7", "#06B6D4", "#6366F1"),
}

def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

def palette_colors(name: str = "cosmic") -> tuple[str, ...]:
    return PALETTES.get(str(name).strip().lower(), PALETTES["cosmic"])

def _clamp_strength(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.55

def render_ambient_gradient(
    width: int,
    height: int,
    palette: str = "cosmic",
    strength: float = 0.55,
    *,
    phase: float = 0.0,
    style: str = "cosmic",
):
    """Render moving translucent light over a true OLED-black base.

    Most drawing happens on a downsampled work image, then Lanczos scales it to
    the widget/window size. Phase is continuous, so repeated calls animate the
    same light field smoothly without random flicker.
    """
    if Image is None or ImageDraw is None or ImageFilter is None:
        return None
    width = max(1, min(2400, int(width)))
    height = max(1, min(1600, int(height)))
    strength = _clamp_strength(strength)
    try:
        phase = float(phase)
        if not math.isfinite(phase):
            phase = 0.0
    except (TypeError, ValueError):
        phase = 0.0
    style = str(style or "cosmic").strip().lower()
    if style not in {"cosmic", "nebula", "aurora", "edge-light"}:
        style = "cosmic"

    # Keep the loop cheap at fullscreen sizes; blur at 520 px and upscale.
    render_factor = min(1.0, 520.0 / max(width, height))
    work_w = max(120, round(width * render_factor))
    work_h = max(90, round(height * render_factor))
    base = Image.new("RGBA", (work_w, work_h), (0, 0, 0, 255))
    if strength <= 0.001:
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        return base.resize((width, height), resampling) if base.size != (width, height) else base

    colors = palette_colors(palette)
    glow = Image.new("RGBA", (work_w, work_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    short_side = min(work_w, work_h)
    motion = phase
    if style == "edge-light":
        blobs = (
            (0.00, 0.08, 0.57, 0), (1.00, 0.18, 0.53, 2),
            (0.85, 1.02, 0.51, 1), (0.12, 0.96, 0.44, 4),
        )
    elif style == "aurora":
        blobs = (
            (-0.02, 0.28, 0.52, 0), (0.93, 0.05, 0.52, 2),
            (0.52, 1.04, 0.52, 1), (0.04, 0.80, 0.40, 4),
        )
    elif style == "nebula":
        blobs = (
            (0.04, 0.12, 0.63, 0), (0.95, 0.17, 0.56, 4),
            (0.67, 0.97, 0.58, 2), (0.26, 0.55, 0.45, 1),
        )
    else:
        blobs = (
            (0.01, 0.10, 0.60, 0), (0.97, 0.20, 0.54, 2),
            (0.72, 1.02, 0.56, 1), (0.38, 0.48, 0.36, 4),
        )

    # The strongest light stays near the perimeter; the center retains contrast.
    for index, (x_ratio, y_ratio, radius_ratio, color_index) in enumerate(blobs):
        drift_x = math.sin(motion + index * 1.71) * work_w * (0.045 if style == "edge-light" else 0.085)
        drift_y = math.cos(motion * 0.78 + index * 1.13) * work_h * 0.105
        cx = round(work_w * x_ratio + drift_x)
        cy = round(work_h * y_ratio + drift_y)
        radius = max(10, round(short_side * radius_ratio))
        color = _rgb(colors[color_index % len(colors)])
        alpha = round((95 + 88 * strength) * strength)
        draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius),
                     fill=(*color, min(220, alpha)))

    if style == "aurora":
        # A few wide, saturated ribbons add a more ribbon-like alternative.
        for index, color_value in enumerate(colors[:4]):
            ribbon = []
            for step in range(81):
                x = work_w * step / 80
                y = work_h * (0.22 + index * 0.16)
                y += math.sin(step * 0.085 + motion * (0.75 + index * 0.08) + index) * work_h * 0.13
                y += math.cos(step * 0.04 - motion) * work_h * 0.035
                ribbon.append((round(x), round(y)))
            draw.line(ribbon, fill=(*_rgb(color_value), round(65 + 85 * strength)),
                      width=max(7, round(short_side * 0.085)), joint="curve")

    blurred = glow.filter(ImageFilter.GaussianBlur(radius=max(5, round(short_side * 0.19))))
    base.alpha_composite(blurred)

    # A gentle black vignette is another layer above the glows, not a colored fill.
    shade = Image.new("RGBA", (work_w, work_h), (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for y in range(work_h):
        vertical_edge = abs((y / max(1, work_h - 1)) - 0.5) * 2.0
        center_dark = max(0.0, 1.0 - vertical_edge * 1.3)
        alpha = round((5 + 31 * center_dark) * strength)
        if alpha:
            shade_draw.line((0, y, work_w, y), fill=(0, 0, 5, alpha))
    base.alpha_composite(shade)

    resampling = getattr(Image, "Resampling", Image).LANCZOS
    return base.resize((width, height), resampling) if base.size != (width, height) else base


def render_gradient_preview(
    width: int = 520,
    height: int = 120,
    palette: str = "cosmic",
    strength: float = 0.55,
    *,
    phase: float = 0.0,
    style: str = "cosmic",
):
    """Render a reference preview of the same animated light-over-black effect."""
    image = render_ambient_gradient(width, height, palette, strength, phase=phase, style=style)
    if image is None:
        return None
    return image.convert("RGB")


def render_atom_art(
    width: int = 280,
    height: int = 190,
    palette: str = "cosmic",
    strength: float = 0.55,
    orbit_count: int = 3,
    background: bool = True,
):
    """Render a crisp atom/orbit motif on a static generated gradient."""
    if Image is None or ImageDraw is None or ImageFilter is None:
        return None
    width = max(96, min(1200, int(width)))
    height = max(72, min(800, int(height)))
    strength = _clamp_strength(strength)
    colors = palette_colors(palette)
    if background:
        image = render_ambient_gradient(width, height, palette, strength)
    else:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if image is None:
        return None
    image = image.convert("RGBA")
    cx, cy = width / 2, height / 2
    radius_x = min(width * 0.31, height * 0.47)
    radius_y = min(height * 0.25, width * 0.19)
    orbit_count = max(2, min(5, int(orbit_count)))
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_colors = [_rgb(c) for c in colors]
    for orbit in range(orbit_count):
        rotation = math.pi * orbit / orbit_count
        points = []
        for step in range(241):
            angle = math.tau * step / 240
            x = radius_x * math.cos(angle)
            y = radius_y * math.sin(angle)
            px = cx + x * math.cos(rotation) - y * math.sin(rotation)
            py = cy + x * math.sin(rotation) + y * math.cos(rotation)
            points.append((round(px, 2), round(py, 2)))
        color = glow_colors[orbit % len(glow_colors)]
        glow_draw.line(points, fill=(*color, round(42 + 55 * strength)), width=max(3, round(min(width, height) * 0.027)), joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(radius=max(2, round(min(width, height) * 0.035))))
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image)
    for orbit in range(orbit_count):
        rotation = math.pi * orbit / orbit_count
        points = []
        for step in range(241):
            angle = math.tau * step / 240
            x = radius_x * math.cos(angle)
            y = radius_y * math.sin(angle)
            points.append((
                round(cx + x * math.cos(rotation) - y * math.sin(rotation), 2),
                round(cy + x * math.sin(rotation) + y * math.cos(rotation), 2),
            ))
        color = colors[(orbit * 2) % len(colors)]
        draw.line(points, fill=(*_rgb(color), 235), width=max(1, round(min(width, height) * 0.009)), joint="curve")
    nucleus_radius = max(4, round(min(width, height) * 0.034))
    nucleus = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    nucleus_draw = ImageDraw.Draw(nucleus)
    core_color = _rgb(colors[0])
    nucleus_draw.ellipse((cx-nucleus_radius*2.2, cy-nucleus_radius*2.2,
                          cx+nucleus_radius*2.2, cy+nucleus_radius*2.2),
                         fill=(*core_color, round(55 * strength)))
    nucleus = nucleus.filter(ImageFilter.GaussianBlur(radius=max(2, nucleus_radius)))
    image.alpha_composite(nucleus)
    draw = ImageDraw.Draw(image)
    draw.ellipse((cx-nucleus_radius, cy-nucleus_radius, cx+nucleus_radius, cy+nucleus_radius),
                 fill=(*core_color, 255), outline=(245, 241, 255, 255), width=max(1, nucleus_radius // 3))
    draw.ellipse((cx-nucleus_radius*0.30, cy-nucleus_radius*0.30,
                  cx+nucleus_radius*0.30, cy+nucleus_radius*0.30), fill=(255, 255, 255, 255))
    # Sparse deterministic stars make the artwork feel cosmic without introducing motion.
    rng = random.Random(14073 + width * 7 + height)
    for _ in range(max(12, min(90, (width * height) // 2300))):
        x, y = rng.randrange(width), rng.randrange(height)
        r = rng.choice((1, 1, 1, 2))
        tint = colors[rng.randrange(len(colors))]
        draw.ellipse((x-r, y-r, x+r, y+r), fill=(*_rgb(tint), rng.randrange(65, 155)))
    return image

__all__ = ["PALETTES", "palette_colors", "render_ambient_gradient", "render_gradient_preview", "render_atom_art"]
