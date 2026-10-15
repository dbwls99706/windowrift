"""Deterministic multi-stage cross-window movement for the native overlay.

This is visual animation in an OS-owned transparent window.  It never purports
 to modify the source game or Chrome's private browser UI.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .geometry import Rect


@dataclass(frozen=True)
class RiftPose:
    """Top-left position of an actor plus its frame styling and scene phase."""

    x: int
    y: int
    phase: str
    tilt: float = 0.0
    squash: float = 1.0
    jump: float = 0.0
    impact: bool = False


def _smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _arc(y: float, t: float, height: float) -> float:
    return y - height * math.sin(math.pi * max(0.0, min(t, 1.0)))


def scene_duration() -> float:
    return 8.5


def cinematic_pose(
    origin: tuple[float, float],
    address_bar: Rect,
    browser: Rect,
    size: tuple[int, int],
    elapsed: float,
    *,
    impact_target: tuple[float, float] | None = None,
) -> RiftPose:
    """Escape, land on Chrome, jump into a web page, bounce, return.

    Positions are screen-space and reprojected from the current browser bounds
    on each tick; the target is not a fake HTML rendering of the Chrome toolbar.
    """
    w, h = size
    if w <= 0 or h <= 0 or address_bar.width < w or browser.width < w:
        raise ValueError("Actor does not fit the selected browser window")
    t = max(0.0, elapsed)
    bar_x = address_bar.x + min(72, max(2, (address_bar.width - w) * 0.35))
    bar_y = address_bar.y + address_bar.height - h + 2
    # Users can specify a real DOM target measured through Chrome DevTools.
    if impact_target is None:
        impact_target = (browser.x + browser.width * 0.54, browser.y + browser.height * 0.66)
    hit_x = max(browser.x + 4, min(impact_target[0] - w / 2, browser.right - w - 4))
    hit_y = max(browser.y + 110, min(impact_target[1] - h / 2, browser.bottom - h - 8))
    if t < 1.55:
        s = _smooth(t / 1.55)
        return RiftPose(round(_mix(origin[0], bar_x, s)),
                        round(_arc(_mix(origin[1], bar_y, s), s, 155)),
                        "escape", tilt=25 * math.sin(math.pi * s),
                        squash=1 + 0.13 * math.sin(2 * math.pi * s), jump=1-s)
    if t < 2.35:
        s = t - 1.55
        landing = 7 * math.exp(-5 * s) * math.cos(23 * s)
        return RiftPose(round(bar_x + 10 * s), round(bar_y - abs(landing)),
                        "perch", tilt=-8 * math.exp(-4 * s) * math.sin(18 * s),
                        squash=1 + 0.22 * math.exp(-7 * s) * math.cos(18 * s))
    launch_x = bar_x + 8
    if t < 3.65:
        s = _smooth((t - 2.35) / 1.30)
        return RiftPose(round(_mix(launch_x, hit_x, s)),
                        round(_arc(_mix(bar_y, hit_y, s), s, 125)),
                        "pounce", tilt=-23 * math.sin(math.pi * s),
                        squash=1 - 0.11 * math.sin(math.pi * s), jump=1)
    if t < 4.45:
        s = t - 3.65
        wobble = math.exp(-3 * s)
        return RiftPose(round(hit_x + 10 * wobble * math.sin(s * 17)),
                        round(hit_y - 16 * abs(math.sin(12 * s)) * wobble),
                        "impact", tilt=23 * wobble * math.cos(s * 19),
                        squash=1.30 - 0.30 * min(1, s * 4),
                        impact=s < 0.28)
    if t < 6.15:
        s = (t - 4.45) / 1.70
        # Two visible rebounds, not a constant-speed crawl along the omnibox.
        bounce = 55 * (1-s) * abs(math.sin(3 * math.pi * s))
        x = hit_x + 105 * s
        x = min(x, browser.right - w - 4)
        return RiftPose(round(x), round(hit_y - bounce), "rebound",
                        tilt=12 * math.sin(6 * math.pi * s),
                        squash=1 + 0.08 * math.cos(6 * math.pi * s))
    rest_x = min(hit_x + 105, browser.right - w - 4)
    if t < 7.95:
        s = _smooth((t - 6.15) / 1.80)
        return RiftPose(round(_mix(rest_x, origin[0], s)),
                        round(_arc(_mix(hit_y, origin[1], s), s, 180)),
                        "return", tilt=-28 * math.sin(math.pi * s), jump=1-s)
    return RiftPose(round(origin[0]), round(origin[1]), "returned")
