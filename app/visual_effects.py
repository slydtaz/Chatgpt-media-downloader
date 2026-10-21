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
):
    """Return a deterministic dark image with soft static, space-like color blooms."""
    if Image is None or ImageDraw is None or ImageFilter is None:
        return None
    width = max(1, min(2400, int(width)))
    height = max(1, min(1600, int(height)))
    strength = _clamp_strength(strength)
    base = Image.new("RGBA", (width, height), (5, 5, 16, 255))
    if strength <= 0.001:
        return base
    colors = palette_colors(palette)
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    scale = min(width, height)
    blobs = (
        (0.04, 0.14, 0.58, 0),
        (0.91, 0.18, 0.50, 2),
        (0.66, 0.93, 0.50, 1),
        (0.38, 0.48, 0.30, 3),
    )
    for x_ratio, y_ratio, radius_ratio, color_index in blobs:
        cx, cy = round(width * x_ratio), round(height * y_ratio)
        radius = max(8, round(scale * radius_ratio))
        color = _rgb(colors[color_index % len(colors)])
        alpha = round((55 + 100 * strength) * strength)
        draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=(*color, alpha))
    blurred = glow.filter(ImageFilter.GaussianBlur(radius=max(4, round(scale * 0.20))))
    base.alpha_composite(blurred)
    # A subtle vertical shade preserves readability in the central content area.
    shade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    for y in range(height):
        edge_distance = abs((y / max(1, height - 1)) - 0.5) * 2.0
        alpha = round((4 + 17 * edge_distance) * strength)
        shade_draw.line((0, y, width, y), fill=(0, 0, 10, alpha))
    base.alpha_composite(shade)
    return base

def render_gradient_preview(
    width: int = 520,
    height: int = 120,
    palette: str = "cosmic",
    strength: float = 0.55,
):
    """Create the exact static background-style preview used by Appearance settings."""
    image = render_ambient_gradient(width, height, palette, strength)
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
