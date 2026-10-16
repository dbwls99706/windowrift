"""Input-driven desktop platformer: real window ledges, jumps and drops.

Calls are pure; no process injection, global keyboard hook or game-state access.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from .geometry import Rect

@dataclass(frozen=True)
class Controls:
    left: bool = False
    right: bool = False
    jump: bool = False
    down: bool = False
    sprint: bool = False

class KeyLatch:
    MAP = {"a":"left", "left":"left", "d":"right", "right":"right",
           "w":"jump", "up":"jump", "space":"jump", "s":"down",
           "down":"down", "shift":"sprint", "shift_l":"sprint", "shift_r":"sprint"}
    def __init__(self): self.down: set[str] = set()
    def press(self, key: str) -> bool:
        key = key.lower()
        if key not in self.MAP: return False
        self.down.add(key)
        return True
    def release(self, key: str) -> bool:
        key = key.lower()
        if key not in self.MAP: return False
        self.down.discard(key)
        return True
    def clear(self): self.down.clear()
    def snapshot(self) -> Controls:
        a={self.MAP[k] for k in self.down}
        return Controls(**{key:key in a for key in ("left","right","jump","down","sprint")})

@dataclass(frozen=True)
class Surface:
    name: str
    rect: Rect

@dataclass(frozen=True)
class Player:
    x: float
    y: float
    width: float
    height: float
    vx: float = 0.
    vy: float = 0.
    ground: str | None = None
    facing: int = 1
    jump_held: bool = False
    coyote: float = 0.
    jump_buffer: float = 0.
    ignore: str | None = None
    ignore_time: float = 0.
    jumps: int = 0
    drops: int = 0
    landings: int = 0

    @property
    def center(self): return self.x+self.width/2, self.y+self.height/2

def step(p: Player, c: Controls, dt: float, screen: Rect, surfaces: list[Surface]) -> Player:
    """Simulate one key state; no preset animation trajectory exists."""
    dt = max(0.,min(dt,.05))
    if dt == 0: return p
    direction=int(c.right)-int(c.left)
    speed=540. if c.sprint else 390.
    accel=16. if p.ground else 9.
    vx=p.vx+(direction*speed-p.vx)*min(1,dt*accel)
    face=direction or p.facing
    pressed=c.jump and not p.jump_held
    buffer=.12 if pressed else max(0.,p.jump_buffer-dt)
    coyote=.10 if p.ground else max(0.,p.coyote-dt)
    ignore_time=max(0.,p.ignore_time-dt)
    ignore=p.ignore if ignore_time else None
    x,y,vy=p.x,p.y,p.vy
    ground=p.ground
    jumps,drops,landings=p.jumps,p.drops,p.landings
    if pressed and c.down and ground:
        ignore=ground;ignore_time=.26;ground=None;coyote=0;buffer=0;y+=4.;vy=max(140.,vy);drops+=1
    elif buffer and coyote:
        vy=-650.;ground=None;coyote=0;buffer=0;jumps+=1
    old_bottom=y+p.height
    vy=min(1200.,vy+1700.*dt)
    x=max(screen.x,min(screen.right-p.width,x+vx*dt))
    y+=vy*dt
    if vy>=0:
        crossed=[s for s in surfaces if s.name!=ignore and
                 x+p.width>s.rect.x+2 and x<s.rect.right-2 and
                 old_bottom<=s.rect.y+2 and y+p.height>=s.rect.y]
        if crossed:
            landed=min(crossed,key=lambda s:s.rect.y)
            y=landed.rect.y-p.height;vy=0.
            if ground!=landed.name:landings+=1
            ground=landed.name;coyote=.10
        else:ground=None
    else:ground=None
    if y+p.height>=screen.bottom:
        y=screen.bottom-p.height;vy=0.
        if ground!='floor':landings+=1
        ground='floor';coyote=.10
    if y<screen.y:y=screen.y;vy=max(0,vy)
    return replace(p,x=x,y=y,vx=vx,vy=vy,ground=ground,facing=face,
                   jump_held=c.jump,coyote=coyote,jump_buffer=buffer,
                   ignore=ignore,ignore_time=ignore_time,jumps=jumps,drops=drops,landings=landings)

def surfaces_for_windows(windows) -> list[Surface]:
    """Visible window roofs and Chrome's genuine address-bar shelf."""
    from .omnibox import OmniboxCalibration, looks_like_chrome
    result=[Surface(f'window:{w.wid}',w.bounds) for w in windows]
    cal=OmniboxCalibration()
    for w in windows:
        if looks_like_chrome(w):
            try:
                bar=cal.anchor(w)
            except ValueError:continue
            result.append(Surface(f'omnibox:{w.wid}', Rect(bar.x,bar.bottom,bar.width,4)))
    return result
