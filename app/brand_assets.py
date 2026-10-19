"""Static image assets for the cosmic application theme."""
import math
import tkinter as tk

LOGO_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAMAAABg3Am1AAAAwFBMVEUPYe/k3/xmEOwVEePk2vuaXfJdqP1bqfheqPitpPhtaPmgXPQ5j/4UivYIavGd2v728/2snvcwr/2p2/zPq/jSr/oAErZuxf7Yr/pvxf1uEO9Zqf3/APQUW6uJL/Ggyvni7v11Z/IAAH9ifv6HPfL/f/8AAD8Af388ffoAjeJVVapt2v8AAAD9/f7+/v/09v0qevAqdO8vhfIulPUypfkBAPkoa+5Kpv4A//8ti/P59/5Nh/wtnPlKefzo2fz7+v5Z9xm3AAAAQHRSTlMWniIVYBr5HmggCFb+VEcaMVyFmmOIBO4rn0idAQRKatBJBOopAgQC/gkDBwD5A9MoFjdVcwUS+wFGtfNo+5RrUtmxDwAAA0hJREFUeNq9louS2jgQRVuSjS2DBwgMjzDvJJvNrtrCxg8wDPz/X6VbhlnDZJLdqtmoCttU9dG93W5JBvMfB7wPUCT/o0LCQ2sT/SvgxvcL96CTXyokiYlkFBntCXEYNEq/UFCR7ysP3agHzSxvAokZHDTFC0TheV6N9nBwOqeyFa+AQ615fquVVE9HHTt4rXGyJKUvCx9xSPch6Ving96R6PcvABn5yt9bFPKzv+dwaZQxA8QBp56Y0eikdQJ8ObNkQsgxXfd+IT1/oo2HtXEAKZwBFK8pTuBYChRDKceWVCbGWEwu0jgBqsa92uM1AV3ZpSRqV1tBWQTg3tIZ4KsZWikJ+EgA19aXHlkUBEwCAIq6aQOFP/FwfwIoZyaKyBW3r9ISYHJu6ca/9dB7Aa7vOIWxUgH9uYdlmZZRMZ6ZLy3AOEA0lu66d5JE7BD4TS5ppGWqZ+0cgmCGNQN4TQCNj9ZyJgCCJDIiUmhZWptgTlOOZfeaXZNCV1mrhmjh6p6obNkijmW94TYlU65CXfko0F6F9NvQBTZMlEeiuVJjs+uHsXSNJPiZgXgVorhabZyp23Zr8Ju21s3OLY5D6xRW8QhHDDBRfm0ButBYu9UjqPfEo2qAOEQM41UjUUbt9v6LWpsalmevh4oTZiB/wFGcNwAoaAMJt03hq7HwlHrkPAig8ZDn+Y49gdaQnAHc/E+fpfpDOmcbso84+vAh3+1YAoYefDnbNcwB8TDzZ67pQlhdCQ4nIHfApaUj0WwZWkEGJLDLGeB4AqgHL7YZWiqH2tVWZ8uQ0pjHOWdAluJ/ugPae6S7D2zT4Hjv4vP5dDpdxFxW9WqrZMbpECG4/rtdPJ92qqqzgEuF6LjO3RJW6RIgW21Wq3A+raqq16vCY84vwJqBdaPTj6BcZtlm00xP8UQswm+meOt8gDSl/swg5Ok5vtPpbTuhSc6TXr88rssydUCn6jRju31+3gZs4ccn0KRkDQI6FU+//fP5+eeAAVr46TKj+O2219ty/KfFhaUXP86aAiIgWFTODzn6FP79dtKNRgkpqKAZWvffOBQL2kFMc3rcAlULlDpuYlHxQyBi4HSCFnAbRNHajeL9vgSS5Hd8a7wn8B3tMU9Zx78zAgAAAABJRU5ErkJggg=="

def _mix(a: str, b: str, t: float) -> str:
    av = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
    bv = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(av, bv))

def _paint_round_rect(image, x0, y0, x1, y1, radius, start, end):
    """Draw a round-corner pill into a transparent Tk photo using 1-pixel scanlines."""
    cy = (y0 + y1) / 2
    half_h = (y1 - y0) / 2
    for y in range(y0, y1 + 1):
        inset = 0.0
        corner_depth = abs(y - cy) - (half_h - radius)
        if corner_depth > 0:
            inset = radius - math.sqrt(max(0.0, radius * radius - corner_depth * corner_depth))
        left = max(x0, math.ceil(x0 + inset))
        right = min(x1, math.floor(x1 - inset))
        if left > right:
            continue
        row = []
        for x in range(left, right + 1):
            t = (x - x0) / max(1, x1 - x0) * 0.38 + (y - y0) / max(1, y1 - y0) * 0.62
            row.append(_mix(start, end, max(0.0, min(1.0, t))))
        image.put("{" + " ".join(row) + "}", to=(left, y))

def _button_skin(root, state):
    image = tk.PhotoImage(master=root, width=80, height=38)
    if state == "hover":
        edge_a, edge_b = "#FFB5F8", "#D4C3FF"
        face_a, face_b = "#FF62E9", "#AE92FF"
        gleam = "#FFE9FF"
    elif state == "pressed":
        edge_a, edge_b = "#E06ADD", "#9980EE"
        face_a, face_b = "#C746D2", "#7658E4"
        gleam = "#E7C5FF"
    else:
        edge_a, edge_b = "#FF8AF1", "#C6A8FF"
        face_a, face_b = "#EE4CE0", "#925FF7"
        gleam = "#FFE0FD"
    _paint_round_rect(image, 2, 4, 77, 34, 15, edge_a, edge_b)
    _paint_round_rect(image, 4, 6, 75, 32, 13, face_a, face_b)
    image.put("{" + " ".join([gleam] * 46) + "}", to=(17, 7))
    return image

def load_brand_images(root: tk.Misc) -> dict[str, tk.PhotoImage]:
    """Load one static logo and generate rounded button states once at startup."""
    return {
        "logo": tk.PhotoImage(master=root, data=LOGO_PNG_BASE64),
        "button_normal": _button_skin(root, "normal"),
        "button_hover": _button_skin(root, "hover"),
        "button_pressed": _button_skin(root, "pressed"),
    }
