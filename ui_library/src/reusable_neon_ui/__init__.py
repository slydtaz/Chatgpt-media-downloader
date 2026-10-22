"""Reusable neon-gradient Tkinter UI components and image renderers."""
from .config import BorderConfig, ElementStyle, GradientConfig, UIConfig, load_config, save_config
from .effects import PALETTES, effect_names, register_effect, sample_gradient, unregister_effect
from .widgets import NeonButton, NeonSurface, NeonTabBar
from .pillow_effects import render_ambient_gradient, render_gradient_preview, render_atom_art
from .rounded_rendering import render_rounded_panel, render_rounded_button

__version__ = "0.1.0"
__all__ = [
    "BorderConfig", "ElementStyle", "GradientConfig", "UIConfig", "load_config",
    "save_config", "PALETTES", "effect_names", "register_effect", "unregister_effect",
    "sample_gradient", "NeonButton", "NeonSurface", "NeonTabBar",
    "render_ambient_gradient", "render_gradient_preview", "render_atom_art",
    "render_rounded_panel", "render_rounded_button",
]
