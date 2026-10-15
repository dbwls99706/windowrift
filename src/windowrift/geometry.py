"""Pure, testable desktop physics and collision primitives."""

from __future__ import annotations

from dataclasses import dataclass

GRAVITY = 1050.0
BOUNCE = 0.33
FRICTION = 0.985


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def intersects_horizontally(self, other: "Rect", margin: float = 5) -> bool:
        return self.right > other.x + margin and self.x < other.right - margin


@dataclass
class ActorState:
    x: float
    y: float
    width: float
    height: float
    vx: float = 80.0
    vy: float = -130.0

    @property
    def bounds(self) -> Rect:
        return Rect(self.x, self.y, self.width, self.height)

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2


def advance(
    state: ActorState,
    dt: float,
    desktop: Rect,
    platforms: list[Rect],
) -> ActorState:
    """Gravity plus one-way window-top supports; never modifies the actual windows."""
    dt = max(0.0, min(dt, 0.05))
    x = state.x + state.vx * dt
    vy = min(state.vy + GRAVITY * dt, 1800.0)
    y = state.y + vy * dt
    vx = state.vx * (FRICTION ** (dt * 60))

    left = desktop.x
    right = desktop.right - state.width
    if x < left:
        x = left
        vx = abs(vx) * BOUNCE
    elif x > right:
        x = max(left, right)
        vx = -abs(vx) * BOUNCE

    previous_bottom = state.y + state.height
    next_bottom = y + state.height
    if vy >= 0:
        tops = [
            p.y
            for p in platforms
            if desktop.y <= p.y <= desktop.bottom
            and previous_bottom <= p.y + 2
            and next_bottom >= p.y
            and Rect(x, y, state.width, state.height).intersects_horizontally(p)
        ]
        if tops:
            y = min(tops) - state.height
            vy = 0.0

    floor = desktop.bottom - state.height
    if y >= floor:
        y = floor
        vy = -abs(vy) * BOUNCE if abs(vy) > 35 else 0.0
        if vy == 0:
            vx *= 0.96
    if y < desktop.y:
        y = desktop.y
        vy = abs(vy) * BOUNCE

    return ActorState(x=x, y=y, width=state.width, height=state.height, vx=vx, vy=vy)
