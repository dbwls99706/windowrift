"""Capture visible screen regions and preserve their actual desktop coordinates."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from .geometry import Rect
from .windows import AppWindow


@dataclass(frozen=True)
class ScreenCapture:
    image: Image.Image
    x: int
    y: int


def clipped_region(request: Rect, desktop: Rect) -> tuple[int, int, int, int]:
    """Return an MSS rectangle intersected with a desktop, or refuse empty results."""
    left = max(round(request.x), round(desktop.x))
    top = max(round(request.y), round(desktop.y))
    right = min(round(request.right), round(desktop.right))
    bottom = min(round(request.bottom), round(desktop.bottom))
    if right <= left or bottom <= top:
        raise ValueError("The requested region is outside the visible desktop.")
    return left, top, right - left, bottom - top


def capture_region(bounds: Rect, *, exact: bool = False) -> ScreenCapture:
    """Screenshot visible pixels. An exact live region must not be clipped off-screen."""
    import mss

    with mss.mss() as session:
        desktop = session.monitors[0]
        monitor = Rect(
            float(desktop["left"]),
            float(desktop["top"]),
            float(desktop["width"]),
            float(desktop["height"]),
        )
        left, top, width, height = clipped_region(bounds, monitor)
        if exact and (
            left != round(bounds.x)
            or top != round(bounds.y)
            or width != round(bounds.width)
            or height != round(bounds.height)
        ):
            raise ValueError("The live source region is partially off-screen.")
        frame = session.grab({"left": left, "top": top, "width": width, "height": height})
    return ScreenCapture(Image.frombytes("RGB", frame.size, frame.rgb), left, top)


def capture_window_with_origin(window: AppWindow) -> ScreenCapture:
    return capture_region(window.bounds)


def capture_window(window: AppWindow) -> Image.Image:
    """Original image-only interface for callers not interested in positioning."""
    return capture_window_with_origin(window).image
