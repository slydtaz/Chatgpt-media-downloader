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

def palette_colors(name: str = "cosmic", custom_colors=None) -> tuple[str, ...]:
    """Return a built-in palette or a validated user palette (3–8 HEX colors)."""
    if str(name).strip().lower() == "custom" and isinstance(custom_colors, (list, tuple)):
        cleaned = []
        for value in custom_colors:
            value = str(value or "").strip().upper()
            if len(value) == 7 and value.startswith("#"):
                try:
                    int(value[1:], 16)
                except ValueError:
                    continue
                cleaned.append(value)
        if len(cleaned) >= 3:
            return tuple(cleaned[:8])
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
    custom_colors=None,
    brightness_min: float = 0.10,
    brightness_max: float = 1.0,
    pulse_depth: float = 0.0,
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
    if style not in {"cosmic", "nebula", "aurora", "edge-light", "diagonal", "bottom-up", "bubbles", "pulse"}:
        style = "cosmic"
    try:
        brightness_min = max(0.0, min(1.0, float(brightness_min)))
        brightness_max = max(brightness_min, min(1.0, float(brightness_max)))
        pulse_depth = max(0.0, min(1.0, float(pulse_depth)))
    except (TypeError, ValueError):
        brightness_min, brightness_max, pulse_depth = 0.10, 1.0, 0.0
    if pulse_depth > 0.001:
        wave = (math.sin(phase) + 1.0) / 2.0
        pulse_factor = brightness_min + (brightness_max - brightness_min) * wave
        strength *= (1.0 - pulse_depth) + pulse_depth * pulse_factor

    # Keep the loop cheap at fullscreen sizes; blur at 520 px and upscale.
    render_factor = min(1.0, 520.0 / max(width, height))
    work_w = max(120, round(width * render_factor))
    work_h = max(90, round(height * render_factor))
    base = Image.new("RGBA", (work_w, work_h), (0, 0, 0, 255))
    if strength <= 0.001:
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        return base.resize((width, height), resampling) if base.size != (width, height) else base

    colors = palette_colors(palette, custom_colors)
    glow = Image.new("RGBA", (work_w, work_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    short_side = min(work_w, work_h)
    motion = phase
    if style == "edge-light":
        blobs = (
            (0.00, 0.08, 0.57, 0), (1.00, 0.18, 0.53, 2),
            (0.85, 1.02, 0.51, 1), (0.12, 0.96, 0.44, 4),
        )
    elif style == "diagonal":
        blobs = (
            (0.02, 1.02, 0.48, 0), (0.32, 0.72, 0.42, 4),
            (0.68, 0.30, 0.42, 2), (1.02, -0.02, 0.48, 1),
        )
    elif style == "bottom-up":
        blobs = (
            (0.02, 1.04, 0.52, 0), (0.34, 0.93, 0.48, 4),
            (0.70, 0.99, 0.47, 2), (0.98, 1.03, 0.49, 1),
        )
    elif style == "bubbles":
        blobs = (
            (0.08, 0.86, 0.24, 0), (0.28, 0.24, 0.20, 4),
            (0.54, 0.62, 0.22, 2), (0.78, 0.18, 0.24, 1),
            (0.96, 0.76, 0.20, 3),
        )
    elif style == "aurora":
        blobs = (
            (-0.02, 0.28, 0.52, 0), (0.93, 0.05, 0.52, 2),
            (0.52, 1.04, 0.52, 1), (0.04, 0.80, 0.40, 4),
        )
    elif style == "nebula":
        blobs = (
            (0.02, 0.10, 0.38, 0), (0.98, 0.16, 0.34, 4),
            (0.72, 1.00, 0.39, 2), (0.26, 0.54, 0.32, 1),
        )
    else:
        blobs = (
            (0.01, 0.10, 0.37, 0), (0.97, 0.20, 0.34, 2),
            (0.72, 1.02, 0.39, 1), (0.38, 0.48, 0.28, 4),
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

    if style in {"cosmic", "nebula", "diagonal", "pulse"}:
        # Saturated ribbons add movement without a harsh full-screen color wash.
        for index, color_value in enumerate(colors[:4]):
            ribbon = []
            for step in range(101):
                t = step / 100
                x = work_w * t
                y = work_h * (0.84 - t * 0.62 + (index - 1.5) * 0.13)
                y += math.sin(t * math.tau * 1.15 + motion * (0.65 + index * 0.11) + index) * work_h * 0.045
                ribbon.append((round(x), round(y)))
            draw.line(
                ribbon,
                fill=(*_rgb(color_value), round((34 if style == "nebula" else 42) + 42 * strength)),
                width=max(2, round(short_side * (0.035 if style == "nebula" else 0.025))),
                joint="curve",
            )

    if style == "bottom-up":
        for index, color_value in enumerate(colors[:4]):
            points = []
            for step in range(81):
                t = step / 80
                y = work_h * (0.98 - t * 0.92)
                x = work_w * (0.12 + index * 0.25 + math.sin(t * math.tau + motion * 0.65 + index) * 0.06)
                points.append((round(x), round(y)))
            draw.line(points, fill=(*_rgb(color_value), round(50 + 80 * strength)),
                      width=max(6, round(short_side * 0.07)), joint="curve")

    if style == "bubbles":
        # Additional softly blurred circles behave like luminous bubbles.
        for index in range(9):
            x = (0.08 + (index * 0.137 + 0.10 * math.sin(motion * 0.7 + index)) % 0.84) * work_w
            y = (0.10 + (index * 0.193 - motion * (0.025 + 0.004 * (index % 3))) % 0.82) * work_h
            radius = max(3, round(short_side * (0.035 + 0.015 * (index % 3))))
            color = _rgb(colors[index % len(colors)])
            alpha = round((85 + 90 * strength) * strength)
            draw.ellipse((round(x-radius), round(y-radius), round(x+radius), round(y+radius)),
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

    blurred = glow.filter(ImageFilter.GaussianBlur(radius=max(5, round(short_side * (0.145 if style in {"cosmic", "nebula"} else 0.16)))))
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
    custom_colors=None,
    brightness_min: float = 0.10,
    brightness_max: float = 1.0,
    pulse_depth: float = 0.0,
):
    """Render a reference preview of the same animated light-over-black effect."""
    image = render_ambient_gradient(
        width, height, palette, strength, phase=phase, style=style,
        custom_colors=custom_colors, brightness_min=brightness_min,
        brightness_max=brightness_max, pulse_depth=pulse_depth,
    )
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
    phase: float = 0.0,
    style: str = "cosmic",
):
    """Render a crisp atom/orbit motif on a static generated gradient."""
    if Image is None or ImageDraw is None or ImageFilter is None:
        return None
    width = max(96, min(1200, int(width)))
    height = max(72, min(800, int(height)))
    strength = _clamp_strength(strength)
    colors = palette_colors(palette)
    try:
        phase = float(phase)
        if not math.isfinite(phase):
            phase = 0.0
    except (TypeError, ValueError):
        phase = 0.0
    if background:
        image = render_ambient_gradient(width, height, palette, strength, phase=phase, style=style)
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
        rotation = math.pi * orbit / orbit_count + phase * (0.32 + 0.10 * (orbit + 1)) * (-1 if orbit % 2 else 1)
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
        rotation = math.pi * orbit / orbit_count + phase * (0.32 + 0.10 * (orbit + 1)) * (-1 if orbit % 2 else 1)
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
    # Moving electron-like molecules orbit on each tilted ring. They are drawn as
    # a soft colored halo plus a bright glassy core for the loading-screen reference.
    electron_positions = []
    electron_glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    electron_glow_draw = ImageDraw.Draw(electron_glow)
    electron_radius = max(3, round(min(width, height) * 0.022))
    for orbit in range(orbit_count):
        rotation = math.pi * orbit / orbit_count + phase * (0.32 + 0.10 * (orbit + 1)) * (-1 if orbit % 2 else 1)
        angle = phase * (1.65 + orbit * 0.16) + orbit * 2.13
        x = radius_x * math.cos(angle)
        y = radius_y * math.sin(angle)
        ex = cx + x * math.cos(rotation) - y * math.sin(rotation)
        ey = cy + x * math.sin(rotation) + y * math.cos(rotation)
        color = colors[(orbit + 2) % len(colors)]
        electron_positions.append((ex, ey, color))
        glow_r = electron_radius * 2.8
        electron_glow_draw.ellipse(
            (ex-glow_r, ey-glow_r, ex+glow_r, ey+glow_r),
            fill=(*_rgb(color), round(80 + 85 * strength)),
        )
    electron_glow = electron_glow.filter(
        ImageFilter.GaussianBlur(radius=max(2, round(electron_radius * 1.2)))
    )
    image.alpha_composite(electron_glow)
    draw = ImageDraw.Draw(image)
    for ex, ey, color in electron_positions:
        draw.ellipse(
            (ex-electron_radius*1.45, ey-electron_radius*1.45,
             ex+electron_radius*1.45, ey+electron_radius*1.45),
            fill=(*_rgb(color), 255),
            outline=(244, 240, 255, 255),
            width=max(1, electron_radius // 3),
        )
        draw.ellipse(
            (ex-electron_radius*0.48, ey-electron_radius*0.48,
             ex+electron_radius*0.48, ey+electron_radius*0.48),
            fill=(255, 255, 255, 255),
        )
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
