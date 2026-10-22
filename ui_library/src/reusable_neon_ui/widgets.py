"""Tkinter widgets with animated gradients and configurable neon borders."""
from __future__ import annotations
import math, tkinter as tk
from typing import Callable, Iterable
from .config import ElementStyle, GradientConfig, UIConfig
from .effects import blend, sample_gradient

def _style(value):
    if isinstance(value,UIConfig): return value.background
    if isinstance(value,ElementStyle): return value
    if isinstance(value,GradientConfig): return ElementStyle(gradient=value)
    return ElementStyle()

def _rounded_points(x0,y0,x1,y1,radius,steps=5):
    radius=max(0,min(radius,(x1-x0)/2,(y1-y0)/2))
    if radius<=0: return [x0,y0,x1,y0,x1,y1,x0,y1,x0,y0]
    points=[]
    for cx,cy,start,end in [(x1-radius,y0+radius,-90,0),(x1-radius,y1-radius,0,90),
                            (x0+radius,y1-radius,90,180),(x0+radius,y0+radius,180,270)]:
        for step in range(steps+1):
            a=math.radians(start+(end-start)*step/steps)
            points.extend((cx+radius*math.cos(a),cy+radius*math.sin(a)))
    points.extend(points[:2]); return points

def _draw_border(canvas,width,height,style,phase,selected=False):
    b=style.border
    if not b.enabled or b.thickness<=0 or width<8 or height<8: return
    if b.animation=="static": phase=0
    elif b.animation=="flow": phase*=b.speed
    else: phase=(math.sin(phase*b.speed)+1)/2
    colors=b.colors; index=int((phase%1)*len(colors))
    color=colors[(index+1)%len(colors)] if selected else colors[index]
    inset=max(1,b.glow+b.thickness/2)
    points=_rounded_points(inset,inset,width-inset,height-inset,style.radius)
    layers=max(1,min(5,int(b.glow)))
    for layer in range(layers,0,-1):
        strength=b.intensity*(layer/layers)*(.38 if selected else .24)
        canvas.create_line(*points,fill=blend(style.surface,color,strength),
                           width=b.thickness+layer*1.6,joinstyle="round",capstyle="round",
                           tags=("neon-border",))
    canvas.create_line(*points,fill=blend(style.surface,color,b.intensity),
                       width=max(1,b.thickness),joinstyle="round",capstyle="round",
                       tags=("neon-border",))

class _AnimatedCanvas(tk.Canvas):
    def __init__(self,master,*,style,reduced_motion=False,**kwargs):
        self.element_style=style; self.reduced_motion=bool(reduced_motion)
        self.phase=0.0; self._animation_job=None; self._hovered=False
        self._selected=False; self._destroyed=False
        super().__init__(master,background=style.surface,highlightthickness=0,borderwidth=0,
                         takefocus=1,**kwargs)
        self.bind("<Configure>",self._on_resize,add="+")
        self.bind("<Enter>",self._on_enter,add="+"); self.bind("<Leave>",self._on_leave,add="+")
        self.bind("<Destroy>",self._on_destroy,add="+")
        self._draw(); self._schedule_if_needed()
    def _on_resize(self,_event=None): self._draw()
    def _on_enter(self,_event=None): self._hovered=True; self._draw()
    def _on_leave(self,_event=None): self._hovered=False; self._draw()
    def _on_destroy(self,event=None):
        if event is not None and event.widget is not self: return
        self._destroyed=True
        if self._animation_job is not None:
            try: self.after_cancel(self._animation_job)
            except tk.TclError: pass
            self._animation_job=None
    def _schedule_if_needed(self):
        if self._destroyed or self.reduced_motion: return
        g,b=self.element_style.gradient,self.element_style.border
        animated=g.enabled and (g.speed>0 or g.pulse_strength>0)
        animated=animated or (b.enabled and b.speed>0 and b.animation!="static")
        if animated and self._animation_job is None:
            try: self._animation_job=self.after(60,self._tick)
            except tk.TclError: self._animation_job=None
    def _tick(self):
        self._animation_job=None
        if self._destroyed or not self.winfo_exists(): return
        self.phase+=.075; self._draw(); self._schedule_if_needed()
    def set_style(self,style,*,reduced_motion=None):
        self.element_style=style
        if reduced_motion is not None: self.reduced_motion=bool(reduced_motion)
        if self.reduced_motion and self._animation_job is not None:
            try: self.after_cancel(self._animation_job)
            except tk.TclError: pass
            self._animation_job=None
        self.configure(background=style.surface); self._draw(); self._schedule_if_needed()
    def set_selected(self,selected): self._selected=bool(selected); self._draw()
    def _draw_bubbles(self,width,height,cfg):
        for i in range(cfg.bubble_count):
            angle=self.phase*cfg.speed*cfg.direction+i*math.tau/cfg.bubble_count
            x=width*(.5+.4*math.cos(angle*.71+i*.9))
            y=height*(.5+.4*math.sin(angle*.83+i*1.3))
            radius=min(width,height)*cfg.bubble_size*(.68+.22*math.sin(angle*1.2))
            color=cfg.colors[i%len(cfg.colors)]
            rings=max(2,min(6,int(cfg.intensity*6)))
            for ring in range(rings,0,-1):
                ratio=ring/rings; fill=blend(cfg.base_color,color,cfg.intensity*(1-ratio*.72))
                r=radius*ratio
                self.create_oval(x-r,y-r,x+r,y+r,fill=fill,outline="",tags=("gradient",))
    def _draw_gradient(self,width,height):
        cfg=self.element_style.gradient; mode=cfg.mode
        if not cfg.enabled:
            self.configure(background=cfg.base_color)
            _draw_border(self,width,height,self.element_style,self.phase,self._selected)
            return
        self.configure(background=self.element_style.surface)
        if mode in {"horizontal","vertical","bottom-up","pulse"}:
            count=56 if mode in {"horizontal","pulse"} else 36
            if mode in {"horizontal","pulse"}:
                for i in range(count):
                    c=sample_gradient(cfg,(i+.5)/count,.5,self.phase)
                    self.create_rectangle(width*i/count,0,width*(i+1)/count+1,height,
                                          fill=c,outline="",tags=("gradient",))
            else:
                for i in range(count):
                    c=sample_gradient(cfg,.5,(i+.5)/count,self.phase)
                    self.create_rectangle(0,height*i/count,width,height*(i+1)/count+1,
                                          fill=c,outline="",tags=("gradient",))
        else:
            cols,rows=(20,12) if mode!="bubbles" else (12,7)
            for row in range(rows):
                for col in range(cols):
                    c=sample_gradient(cfg,(col+.5)/cols,(row+.5)/rows,self.phase)
                    self.create_rectangle(width*col/cols,height*row/rows,
                                          width*(col+1)/cols+1,height*(row+1)/rows+1,
                                          fill=c,outline="",tags=("gradient",))
        if mode=="bubbles": self._draw_bubbles(width,height,cfg)
        _draw_border(self,width,height,self.element_style,self.phase,self._selected)
    def _draw(self):
        if not self.winfo_exists(): return
        w,h=max(8,self.winfo_width()),max(8,self.winfo_height())
        self.delete("gradient"); self.delete("neon-border"); self._draw_gradient(w,h)

class NeonSurface(_AnimatedCanvas):
    """Gradient canvas that hosts regular Tk widgets through add_widget()."""
    def __init__(self,master,*,style=None,reduced_motion=False,**kwargs):
        if isinstance(style,UIConfig): reduced_motion=style.reduced_motion; style=style.background
        super().__init__(master,style=_style(style),reduced_motion=reduced_motion,**kwargs)
    def add_widget(self,widget:tk.Widget,*,x=12,y=12,anchor="nw",**kwargs):
        return self.create_window(x,y,anchor=anchor,window=widget,**kwargs)

class NeonButton(_AnimatedCanvas):
    """Clickable, keyboard-focusable button with configurable neon styling."""
    def __init__(self,master,text,command:Callable[[],None]|None=None,*,style=None,
                 reduced_motion=False,foreground="#FFFFFF",font=("Segoe UI",10,"bold"),
                 width=164,height=42,**kwargs):
        self.text=str(text); self.command=command; self.foreground=foreground
        self.font=font; self._enabled=True
        if isinstance(style,UIConfig): reduced_motion=style.reduced_motion; style=style.button
        super().__init__(master,style=_style(style),reduced_motion=reduced_motion,
                         width=width,height=height,cursor="hand2",**kwargs)
        self.bind("<Button-1>",self._invoke,add="+")
        self.bind("<KeyPress-Return>",self._invoke,add="+")
        self.bind("<KeyPress-space>",self._invoke,add="+")
        self.bind("<FocusIn>",lambda _e:self._draw(),add="+")
        self.bind("<FocusOut>",lambda _e:self._draw(),add="+")
    def _invoke(self,_event=None):
        if self._enabled and callable(self.command): self.command()
        return "break"
    def set_text(self,text): self.text=str(text); self._draw()
    def set_enabled(self,enabled):
        self._enabled=bool(enabled); self.configure(cursor="hand2" if self._enabled else "arrow"); self._draw()
    def _draw(self):
        if not self.winfo_exists(): return
        w,h=max(8,self.winfo_width()),max(8,self.winfo_height())
        for tag in ("gradient","neon-border","button-text","focus"): self.delete(tag)
        cfg=self.element_style.gradient; mode=cfg.mode
        if cfg.enabled:
            if mode in {"horizontal","vertical","bottom-up","pulse"}:
                count=28 if mode in {"horizontal","pulse"} else 18
                for i in range(count):
                    if mode in {"horizontal","pulse"}:
                        c=sample_gradient(cfg,(i+.5)/count,.5,self.phase)
                        self.create_rectangle(w*i/count,0,w*(i+1)/count+1,h,fill=c,outline="",tags=("gradient",))
                    else:
                        c=sample_gradient(cfg,.5,(i+.5)/count,self.phase)
                        self.create_rectangle(0,h*i/count,w,h*(i+1)/count+1,fill=c,outline="",tags=("gradient",))
            else:
                cols,rows=16,7
                for row in range(rows):
                    for col in range(cols):
                        c=sample_gradient(cfg,(col+.5)/cols,(row+.5)/rows,self.phase)
                        self.create_rectangle(w*col/cols,h*row/rows,w*(col+1)/cols+1,h*(row+1)/rows+1,
                                              fill=c,outline="",tags=("gradient",))
            if mode=="bubbles": self._draw_bubbles(w,h,cfg)
        else:
            self.configure(background=self.element_style.surface)
            self.create_rectangle(0,0,w,h,fill=self.element_style.surface,outline="",tags=("gradient",))
        _draw_border(self,w,h,self.element_style,self.phase,self._selected or self._hovered)
        fg=self.foreground if self._enabled else blend(self.foreground,self.element_style.surface,.6)
        self.create_text(w/2,h/2,text=self.text,fill=fg,font=self.font,tags=("button-text",))
        if self.focus_get() is self:
            self.create_rectangle(4,4,w-4,h-4,outline="#FFFFFF",dash=(2,3),tags=("focus",))

class NeonTabBar(tk.Frame):
    """Tab strip whose buttons share a style and mark the selected tab."""
    def __init__(self,master,tabs:Iterable[tuple[str,str]],on_change:Callable[[str],None],*,
                 style=None,reduced_motion=False,**kwargs):
        super().__init__(master,bd=0,highlightthickness=0,**kwargs)
        self.on_change=on_change; self.selected_key=""; self.buttons={}
        if isinstance(style,UIConfig): reduced_motion=style.reduced_motion; style=style.tab
        element_style=_style(style)
        for key,label in tabs:
            button=NeonButton(self,label,command=lambda selected=key:self.select(selected),
                              style=element_style,reduced_motion=reduced_motion,height=38)
            button.pack(side="left",padx=(0,6),pady=2); self.buttons[str(key)]=button
        if self.buttons: self.select(next(iter(self.buttons)),notify=False)
    def select(self,key,*,notify=True):
        if key not in self.buttons: return
        self.selected_key=key
        for item_key,button in self.buttons.items(): button.set_selected(item_key==key)
        if notify and callable(self.on_change): self.on_change(key)
    def set_style(self,style,*,reduced_motion=False):
        for button in self.buttons.values(): button.set_style(style,reduced_motion=reduced_motion)
