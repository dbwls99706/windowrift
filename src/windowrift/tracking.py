"""Bounded, mask-aware template tracking for visible source-window pixels.

The tracker makes no attempt to read process memory, infer occluded pixels, or
claim an identity match when the appearance has changed too far.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class TrackingMatch:
    x: int
    y: int
    confidence: float


MAX_TEMPLATE_SIDE = 144
MIN_OPAQUE_PIXELS = 25


def locate_object(
    search: Image.Image,
    template: Image.Image,
    *,
    min_confidence: float = 0.83,
) -> TrackingMatch | None:
    """Find the known foreground within an already-bounded source-region search.

    Coordinates are relative to *search*. The caller limits the search rectangle
    to the selected application and applies a maximum movement radius. Masked
    squared pixel differences are used rather than matching the background.
    """
    foreground = template.convert("RGBA")
    if search.width < foreground.width or search.height < foreground.height:
        return None
    alpha = np.asarray(foreground.getchannel("A"), dtype=np.uint8)
    if np.count_nonzero(alpha >= 128) < MIN_OPAQUE_PIXELS:
        return None

    scale = min(1.0, MAX_TEMPLATE_SIDE / max(foreground.size))
    if scale < 1:
        tw = max(1, round(foreground.width * scale))
        th = max(1, round(foreground.height * scale))
        sw = max(tw, round(search.width * scale))
        sh = max(th, round(search.height * scale))
        templ = cv2.resize(np.asarray(foreground.convert("RGB")), (tw, th), interpolation=cv2.INTER_AREA)
        frame = cv2.resize(np.asarray(search.convert("RGB")), (sw, sh), interpolation=cv2.INTER_AREA)
        mask = cv2.resize(alpha, (tw, th), interpolation=cv2.INTER_NEAREST)
    else:
        templ = np.asarray(foreground.convert("RGB"))
        frame = np.asarray(search.convert("RGB"))
        mask = alpha

    # OpenCV accepts a single-channel alpha mask for RGB SQDIFF matching.
    mask = np.where(mask >= 128, 255, 0).astype(np.uint8)
    if np.count_nonzero(mask) < max(4, int(MIN_OPAQUE_PIXELS * scale * scale)):
        return None
    try:
        scores = cv2.matchTemplate(frame, templ, cv2.TM_SQDIFF_NORMED, mask=mask)
    except cv2.error:
        return None
    finite = np.isfinite(scores)
    if not finite.any():
        return None
    minimum = np.where(finite, scores, 1.0)
    flat = int(np.argmin(minimum))
    y, x = np.unravel_index(flat, minimum.shape)
    confidence = max(0.0, min(1.0, 1.0 - float(minimum[y, x])))
    if confidence < min_confidence:
        return None
    return TrackingMatch(
        x=min(search.width - foreground.width, max(0, round(int(x) / scale))),
        y=min(search.height - foreground.height, max(0, round(int(y) / scale))),
        confidence=confidence,
    )
