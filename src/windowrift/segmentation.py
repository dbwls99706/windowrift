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


def extract_object(image: Image.Image, mode: str, *, trim: bool = True) -> Image.Image:
    if mode == "crop":
        return image.convert("RGBA")
    if mode == "grabcut":
        return grabcut_foreground(image, trim=trim)
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
