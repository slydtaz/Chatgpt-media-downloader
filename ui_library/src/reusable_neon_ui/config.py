"""Validated JSON configuration for reusable neon UI."""
from __future__ import annotations
from dataclasses import dataclass, field
import json, math, os, re, tempfile
from pathlib import Path
_HEX=re.compile(r"^#[0-9A-Fa-f]{6}$")
_MODE=re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
def _color(v,default):
    s=str(v or "").strip().upper()
    return s if _HEX.fullmatch(s) else default
def _num(v,lo,hi,default):
    try:
        n=float(v)
        return max(lo,min(hi,n)) if math.isfinite(n) else default
    except (ValueError,TypeError): return default
def _colors(v,default):
    if not isinstance(v,(list,tuple)): v=default
    out=[_color(x,"") for x in v]; out=[x for x in out if x]
    return tuple(out[:8]) if len(out)>=2 else tuple(default)
@dataclass
class GradientConfig:
    mode:str="diagonal"
    colors:tuple=("#A855F7","#4F46E5","#1687F8","#22D3EE","#EC4899")
    base_color:str="#05040A"
    intensity:float=.82
    brightness_min:float=.18
    brightness_max:float=1
    pulse_strength:float=.35
    pulse_speed:float=1
    speed:float=.55
    direction:int=1
    bubble_count:int=7
    bubble_size:float=.22
    enabled:bool=True
    def __post_init__(self): self.normalize()
    def normalize(self):
        m=str(self.mode or "diagonal").lower()
        self.mode=m if _MODE.fullmatch(m) else "diagonal"
        self.colors=_colors(self.colors,("#A855F7","#4F46E5","#22D3EE"))
        self.base_color=_color(self.base_color,"#05040A")
        self.intensity=_num(self.intensity,0,1,.82)
        self.brightness_min=_num(self.brightness_min,0,1,.18)
        self.brightness_max=max(self.brightness_min,_num(self.brightness_max,0,1,1))
        self.pulse_strength=_num(self.pulse_strength,0,1,.35)
        self.pulse_speed=_num(self.pulse_speed,0,4,1)
        self.speed=_num(self.speed,0,4,.55)
        try:self.direction=-1 if int(self.direction)<0 else 1
        except (ValueError,TypeError):self.direction=1
        try:self.bubble_count=max(1,min(20,int(self.bubble_count)))
        except (ValueError,TypeError):self.bubble_count=7
        self.bubble_size=_num(self.bubble_size,.05,.48,.22); self.enabled=bool(self.enabled)
        return self
    def to_dict(self):
        d=dict(self.__dict__); d["colors"]=list(self.colors); return d
    @classmethod
    def from_dict(cls,d):
        d=d if isinstance(d,dict) else {}
        return cls(**{k:v for k,v in d.items() if k in cls.__dataclass_fields__})
@dataclass
class BorderConfig:
    enabled:bool=True
    colors:tuple=("#EC4899","#8B5CF6","#2563EB","#22D3EE")
    thickness:float=2
    intensity:float=.9
    glow:float=4
    speed:float=.8
    animation:str="flow"
    def __post_init__(self):
        self.colors=_colors(self.colors,("#EC4899","#8B5CF6","#22D3EE"))
        self.thickness=_num(self.thickness,0,12,2); self.intensity=_num(self.intensity,0,1,.9)
        self.glow=_num(self.glow,0,12,4); self.speed=_num(self.speed,0,4,.8)
        self.animation=str(self.animation or "flow").lower()
        if self.animation not in {"flow","pulse","static"}:self.animation="flow"
        self.enabled=bool(self.enabled)
    def to_dict(self):
        d=dict(self.__dict__); d["colors"]=list(self.colors); return d
    @classmethod
    def from_dict(cls,d):
        d=d if isinstance(d,dict) else {}
        return cls(**{k:v for k,v in d.items() if k in cls.__dataclass_fields__})
@dataclass
class ElementStyle:
    gradient:GradientConfig=field(default_factory=GradientConfig)
    border:BorderConfig=field(default_factory=BorderConfig)
    surface:str="#090814"
    radius:int=14
    def __post_init__(self):
        if not isinstance(self.gradient,GradientConfig):self.gradient=GradientConfig.from_dict(self.gradient)
        if not isinstance(self.border,BorderConfig):self.border=BorderConfig.from_dict(self.border)
        self.surface=_color(self.surface,"#090814")
        try:self.radius=max(0,min(48,int(self.radius)))
        except (ValueError,TypeError):self.radius=14
    def to_dict(self):return {"gradient":self.gradient.to_dict(),"border":self.border.to_dict(),"surface":self.surface,"radius":self.radius}
    @classmethod
    def from_dict(cls,d):
        d=d if isinstance(d,dict) else {}
        return cls(gradient=GradientConfig.from_dict(d.get("gradient",{})),border=BorderConfig.from_dict(d.get("border",{})),surface=d.get("surface","#090814"),radius=d.get("radius",14))
@dataclass
class UIConfig:
    background:ElementStyle=field(default_factory=ElementStyle)
    button:ElementStyle=field(default_factory=lambda:ElementStyle(gradient=GradientConfig(mode="horizontal",intensity=.45,pulse_strength=.12),surface="#111022",radius=10))
    tab:ElementStyle=field(default_factory=lambda:ElementStyle(gradient=GradientConfig(mode="diagonal",intensity=.58,pulse_strength=.22),surface="#111022",radius=10))
    reduced_motion:bool=False
    schema:int=1
    def __post_init__(self):
        if not isinstance(self.background,ElementStyle):self.background=ElementStyle.from_dict(self.background)
        if not isinstance(self.button,ElementStyle):self.button=ElementStyle.from_dict(self.button)
        if not isinstance(self.tab,ElementStyle):self.tab=ElementStyle.from_dict(self.tab)
        self.reduced_motion=bool(self.reduced_motion); self.schema=1
    def to_dict(self):return {"schema":1,"reduced_motion":self.reduced_motion,"background":self.background.to_dict(),"button":self.button.to_dict(),"tab":self.tab.to_dict()}
    @classmethod
    def from_dict(cls,d):
        d=d if isinstance(d,dict) else {}
        return cls(background=ElementStyle.from_dict(d.get("background",{})),button=ElementStyle.from_dict(d.get("button",{})),tab=ElementStyle.from_dict(d.get("tab",{})),reduced_motion=d.get("reduced_motion",False))
def save_config(path,config):
    target=Path(path).expanduser(); target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_symlink():raise ValueError("Refusing to write through a symbolic link.")
    fd,tmp=tempfile.mkstemp(prefix=".neon-ui-",suffix=".tmp",dir=target.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(config.to_dict(),f,ensure_ascii=False,indent=2);f.write("\n");f.flush();os.fsync(f.fileno())
        try:os.chmod(tmp,0o600)
        except OSError:pass
        os.replace(tmp,target)
    finally:
        try:os.unlink(tmp)
        except FileNotFoundError:pass
def load_config(path):
    target=Path(path).expanduser()
    if target.is_symlink():raise ValueError("Refusing to read through a symbolic link.")
    try:d=json.loads(target.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:raise ValueError(f"Could not load settings: {exc}") from exc
    if not isinstance(d,dict) or d.get("schema",1)!=1:raise ValueError("Unsupported UI settings schema.")
    return UIConfig.from_dict(d)
