"""Stateless live-sampling helpers for a selected region in a moving window."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from .geometry import Rect
from .windows import AppWindow

MAX_LIVE_PIXELS = 512 * 512


@dataclass(frozen=True)
class SourceCrop:
    window_id: int
    offset_x: int
    offset_y: int
    width: int
    height: int

    def bounds(self, window: AppWindow) -> Rect:
        if window.wid != self.window_id:
            raise ValueError("The selected source window is no longer available.")
        if (
            self.offset_x < 0
            or self.offset_y < 0
            or self.offset_x + self.width > window.bounds.width
            or self.offset_y + self.height > window.bounds.height
        ):
            raise ValueError("The original selection no longer fits the source window.")
        return Rect(
            round(window.bounds.x) + self.offset_x,
            round(window.bounds.y) + self.offset_y,
            self.width,
            self.height,
        )

    @property
    def affordable(self) -> bool:
        return (
            0 < self.width <= 512
            and 0 < self.height <= 512
            and self.width * self.height <= MAX_LIVE_PIXELS
        )


def overlaps(first: Rect, second: Rect) -> bool:
    return (
        first.x < second.right
        and second.x < first.right
        and first.y < second.bottom
        and second.y < first.bottom
    )


def composite_live_frame(frame: Image.Image, matte: Image.Image) -> Image.Image:
    """Apply one user-approved alpha mask to new pixels from the same source region.

    This is *not* object tracking or AI segmentation of every video frame. It
    preserves the original crop's geometry and does not fill occluded pixels.
    """
    if frame.size != matte.size:
        raise ValueError("Live frame and source mask sizes differ.")
    result = frame.convert("RGBA")
    result.putalpha(matte.convert("RGBA").getchannel("A"))
    return result


TRACKING_RADIUS = 72


def tracking_region(source: SourceCrop, window: AppWindow, radius: int = TRACKING_RADIUS) -> Rect:
    """Limit a neighborhood search to the source window's bounds.

    Never track pixels that belong to another application window by expanding
    outside the original source. This does not detect overlapping windows.
    """
    current = source.bounds(window)
    left = max(round(window.bounds.x), round(current.x) - radius)
    top = max(round(window.bounds.y), round(current.y) - radius)
    right = min(round(window.bounds.right), round(current.right) + radius)
    bottom = min(round(window.bounds.bottom), round(current.bottom) + radius)
    return Rect(left, top, right - left, bottom - top)
