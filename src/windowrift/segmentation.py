"""Crop a user-selected object and remove background with AI or GrabCut."""

from __future__ import annotations

from PIL import Image, ImageFilter


class SegmentationError(RuntimeError):
    pass


def trim_alpha(image: Image.Image, padding: int = 2) -> Image.Image:
    """Trim transparent edges without cutting off nontransparent pixels."""
    rgba = image.convert("RGBA")
    bounds = rgba.getchannel("A").getbbox()
    if bounds is None:
        raise SegmentationError("No visible object found in the selection.")
    return rgba.crop((max(0, bounds[0] - padding), max(0, bounds[1] - padding),
                      min(rgba.width, bounds[2] + padding),
                      min(rgba.height, bounds[3] + padding)))


def grabcut_foreground(image: Image.Image, *, trim: bool = True) -> Image.Image:
    """CPU-only local foreground estimator; selection should include background margin."""
    import cv2
    import numpy as np

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    if min(width, height) < 20:
        raise SegmentationError("Selection is too small; choose an area at least 20px wide.")

    mask = np.full((height, width), cv2.GC_PR_BGD, dtype=np.uint8)
    border = max(2, min(width, height) // 20)
    mask[:border, :] = cv2.GC_BGD
    mask[-border:, :] = cv2.GC_BGD
    mask[:, :border] = cv2.GC_BGD
    mask[:, -border:] = cv2.GC_BGD
    # A small certain foreground seed prevents the degenerate all-background case.
    sy, ey = height * 2 // 5, height * 3 // 5
    sx, ex = width * 2 // 5, width * 3 // 5
    mask[sy:ey, sx:ex] = cv2.GC_FGD
    mask[border:-border, border:-border] = np.where(
        mask[border:-border, border:-border] == cv2.GC_FGD,
        cv2.GC_FGD, cv2.GC_PR_FGD
    )
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    try:
        bg = np.zeros((1, 65), np.float64)
        fg = np.zeros((1, 65), np.float64)
        cv2.grabCut(bgr, mask, None, bg, fg, 5, cv2.GC_INIT_WITH_MASK)
    except cv2.error as exc:
        raise SegmentationError("Foreground estimation failed. Try a larger crop or AI mode.") from exc

    alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype('uint8')
    if not np.any(alpha):
        raise SegmentationError("No foreground found. Draw a tighter rectangle.")
    rgba = np.dstack((rgb, alpha))
    out = Image.fromarray(rgba, "RGBA")
    blurred = out.getchannel("A").filter(ImageFilter.GaussianBlur(0.65))
    out.putalpha(blurred)
    return trim_alpha(out) if trim else out


def color_key_foreground(image: Image.Image, *, trim: bool = True, tolerance: int = 7) -> Image.Image:
    """Remove an almost-flat background sampled from all four crop corners.

    Designed for pixel art and solid-color app surfaces, not for photographs.
    Never removes pixels from an arbitrary remote source or calls a model.
    """
    import cv2
    import numpy as np

    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    if min(image.size) < 16:
        raise SegmentationError("Color key needs at least a 16 x 16 selection.")
    corners = np.stack([rgb[0,0], rgb[0,-1], rgb[-1,0], rgb[-1,-1]])
    baseline = np.median(corners.astype(np.int16), axis=0)
    if np.max(np.abs(corners.astype(np.int16) - baseline)) > tolerance:
        raise SegmentationError(
            "The corners have different colors. Use GrabCut or select a flat-background region."
        )
    distance = np.max(np.abs(rgb.astype(np.int16) - baseline), axis=2)
    visible = (distance > tolerance).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(visible, connectivity=8)
    if num <= 1:
        raise SegmentationError("No foreground differs from the selected background.")
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    alpha = np.where(labels == largest, 255, 0).astype(np.uint8)
    result = Image.fromarray(np.dstack((rgb, alpha)), "RGBA")
    return trim_alpha(result, padding=2) if trim else result


def extract_object(image: Image.Image, mode: str, *, trim: bool = True) -> Image.Image:
    if mode == "crop":
        return image.convert("RGBA")
    if mode == "grabcut":
        return grabcut_foreground(image, trim=trim)
    if mode == "color-key":
        return color_key_foreground(image, trim=trim)
    if mode == "ai":
        try:
            from rembg import remove
        except ImportError as exc:
            raise SegmentationError(
                "AI segmentation is optional. Install: pip install -e '.[ai]'"
            ) from exc
        try:
            result = remove(image.convert("RGBA"))
        except Exception as exc:
            raise SegmentationError(f"AI segmentation failed: {exc}") from exc
        return trim_alpha(result) if trim else result.convert("RGBA")
    raise ValueError(f"Unknown segmentation mode: {mode}")
