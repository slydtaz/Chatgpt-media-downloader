"""Color math and a trusted-code effect registry."""
from __future__ import annotations
import math, re
from .config import GradientConfig

PALETTES = {
    "cosmic": ("#743BEB", "#4F46E5", "#1687F8", "#21B6EB", "#B52CE3"),
    "nebula": ("#6526D9", "#8429E8", "#4338CA", "#A72ACD", "#D946EF"),
    "aurora": ("#6D28D9", "#2563EB", "#0891B2", "#10B981", "#6366F1"),
    "ocean": ("#4338CA", "#2563EB", "#0284C7", "#06B6D4", "#6366F1"),
    "sunset": ("#F97316", "#EC4899", "#8B5CF6", "#312E81"),
}
_COLOR = re.compile(r"^#[0-9A-F]{6}$")
_REGISTRY = {}

def _rgb(value):
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6 or not re.fullmatch(r"[0-9A-Fa-f]{6}", text): return (0,0,0)
    return tuple(int(text[i:i+2],16) for i in (0,2,4))

def hex_color(rgb):
    return "#{:02X}{:02X}{:02X}".format(*(max(0,min(255,int(v))) for v in rgb))

def blend(first, second, amount):
    amount=max(0.0,min(1.0,float(amount))); a,b=_rgb(first),_rgb(second)
    return hex_color(tuple(round(x*(1-amount)+y*amount) for x,y in zip(a,b)))

def palette_colors(name="cosmic", custom_colors=None):
    if str(name).lower()=="custom" and isinstance(custom_colors,(list,tuple)):
        cleaned=tuple(str(c).upper() for c in custom_colors if _COLOR.fullmatch(str(c).upper()))
        if len(cleaned)>=2: return cleaned[:8]
    return PALETTES.get(str(name).lower(),PALETTES["cosmic"])

def _cyclic(colors, position):
    scaled=(position%1.0)*len(colors); i=int(scaled)
    return blend(colors[i],colors[(i+1)%len(colors)],scaled-i)

def _linear(cfg,x,y,phase):
    if cfg.mode=="horizontal": p=x
    elif cfg.mode=="vertical": p=y
    elif cfg.mode=="bottom-up": p=1-y
    elif cfg.mode=="diagonal": p=(x+y)/2
    elif cfg.mode=="radial": p=min(1,math.hypot(x-.5,y-.5)/.7072)
    else: p=x
    return _cyclic(cfg.colors,(p+phase*cfg.speed*cfg.direction*.08)%1)

def _pulse(cfg,x,y,phase):
    return _cyclic(cfg.colors,(x+phase*cfg.speed*.08)%1)

def _bubbles(cfg,_x,_y,_phase):
    return cfg.base_color

def register_effect(name, renderer, *, replace=False):
    """Register trusted Python code. Never load effect code from media or URLs."""
    key=str(name or "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}",key): raise ValueError("Invalid effect name.")
    if not callable(renderer): raise TypeError("renderer must be callable.")
    if key in _REGISTRY and not replace: raise ValueError(f"Effect already registered: {key}")
    _REGISTRY[key]=renderer

def unregister_effect(name):
    key=str(name or "").strip().lower()
    if key in {"horizontal","vertical","bottom-up","diagonal","radial","pulse","bubbles"}:
        raise ValueError("Built-in effects cannot be removed.")
    _REGISTRY.pop(key,None)

def effect_names(): return tuple(sorted(_REGISTRY))

def sample_gradient(config: GradientConfig,x: float,y: float,phase: float=0.0) -> str:
    """Sample one HEX color using normalized x/y coordinates in [0, 1]."""
    config.normalize(); x=max(0,min(1,float(x))); y=max(0,min(1,float(y)))
    try:
        phase=float(phase)
        if not math.isfinite(phase): phase=0.0
    except (TypeError,ValueError): phase=0.0
    if not config.enabled: return config.base_color
    renderer=_REGISTRY.get(config.mode,_linear)
    target=str(renderer(config,x,y,phase) or config.base_color).upper()
    if not _COLOR.fullmatch(target): target=config.base_color
    wave=(math.sin(phase*config.pulse_speed)+1)/2
    brightness=config.brightness_min+(config.brightness_max-config.brightness_min)*wave
    pulse=(1-config.pulse_strength)+config.pulse_strength*brightness
    return blend(config.base_color,target,config.intensity*pulse)

for _name,_renderer in (
    ("horizontal",_linear),("vertical",_linear),("bottom-up",_linear),
    ("diagonal",_linear),("radial",_linear),("pulse",_pulse),("bubbles",_bubbles),
):
    register_effect(_name,_renderer)
