"""OS-level visual portal to a Chromium/Chrome browser's native address bar.

The omnibox belongs to browser chrome, not the web page DOM. Browser extensions
cannot insert into it; this module only positions WindowRift's own transparent
window *above* that native UI. It never types, reads the URL, or changes Chrome.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .geometry import Rect
from .windows import AppWindow


@dataclass(frozen=True)
class OmniboxCalibration:
    """Approximate browser-toolbar inset in OS logical pixels at 100% scale.

    Nonstandard toolbars, display scaling and browser versions can need manual
    calibration. Values are intentionally visible instead of claiming access
    to an inaccessible internal browser-widget bounding rectangle.
    """

    left: int = 122
    top: int = 47
    right: int = 87
    height: int = 36

    def anchor(self, window: AppWindow) -> Rect:
        if not looks_like_chrome(window):
            raise ValueError("Select a Google Chrome or Chromium window.")
        bounds = window.bounds
        width = round(bounds.width) - self.left - self.right
        if width < 100 or bounds.height < self.top + self.height:
            raise ValueError("The browser window is too small for an address-bar portal.")
        return Rect(
            round(bounds.x) + self.left,
            round(bounds.y) + self.top,
            width,
            self.height,
        )


def looks_like_chrome(window: AppWindow) -> bool:
    """Recognize common title suffixes; callers choose the exact window ID."""
    title = window.title.casefold()
    return (
        title.endswith(" - chromium")
        or title.endswith(" - google chrome")
        or title == "chromium"
        or title == "google chrome"
    )


def portal_position(
    origin: tuple[float, float],
    target: Rect,
    size: tuple[int, int],
    elapsed: float,
    *,
    travel_seconds: float = 1.8,
    speed: float = 95.0,
) -> tuple[int, int]:
    """Fly into the browser toolbar, then run along the real omnibox bounds.

    Deterministic and independent of UI toolkit, so desktop integration can be
    tested without a live browser, GPU, or Qt event loop.
    """
    width, height = size
    if width <= 0 or height <= 0 or target.width < width:
        raise ValueError("Actor does not fit the omnibox target.")
    elapsed = max(0.0, elapsed)
    destination_y = target.y + (target.height - height) / 2
    left, right = target.x + 4, target.right - width - 4
    if right < left:
        left, right = target.x, target.right - width
    if elapsed < travel_seconds:
        t = elapsed / travel_seconds
        smooth = t * t * (3 - 2 * t)
        end_x = left + min(42.0, max(0.0, right - left))
        x = origin[0] + (end_x - origin[0]) * smooth
        y = origin[1] + (destination_y - origin[1]) * smooth
        # An arc is visible in the *desktop*, not inside a fake website canvas.
        y -= 110.0 * math.sin(math.pi * t)
        return round(x), round(y)
    span = right - left
    if span <= 0:
        return round(left), round(destination_y)
    distance = (elapsed - travel_seconds) * speed
    bounce = distance % (2 * span)
    x = left + (bounce if bounce <= span else 2 * span - bounce)
    return round(x), round(destination_y)
