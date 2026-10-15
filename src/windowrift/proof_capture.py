"""Bounded capture of *real* desktop frames for reproducible demonstration videos."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


class ProofRecorder:
    """Accumulate screenshots without synthesizing any application content."""

    def __init__(self, *, interval: float = 0.2, max_frames: int = 45, max_width: int = 1120):
        if not (0.1 <= interval <= 2) or not (1 <= max_frames <= 120):
            raise ValueError("Invalid recording interval or frame budget.")
        if not 320 <= max_width <= 1600:
            raise ValueError("Recording width must be between 320 and 1600.")
        self.interval = interval
        self.max_frames = max_frames
        self.max_width = max_width
        self.frames: list[Image.Image] = []
        self._last_at: float | None = None

    def add_frame(self, elapsed: float, screenshot: Image.Image) -> bool:
        """Record one real capture when its sampling interval and bound permit."""
        if len(self.frames) >= self.max_frames:
            return False
        if self._last_at is not None and elapsed - self._last_at < self.interval:
            return False
        frame = screenshot.convert("RGB")
        if frame.width > self.max_width:
            size = (self.max_width, max(1, round(frame.height * self.max_width / frame.width)))
            frame = frame.resize(size, Image.Resampling.BILINEAR)
        if frame.width < 1 or frame.height < 1:
            raise ValueError("Cannot record an empty desktop screenshot.")
        self.frames.append(frame)
        self._last_at = elapsed
        return True

    def save(self, path: str | Path) -> int:
        if not self.frames:
            raise ValueError("No desktop frames were captured.")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Every source image comes from a real screen capture, not a synthetic
        # recreation of the game/browser output.
        frames = [f.quantize(colors=128, method=Image.Quantize.FASTOCTREE)
                  for f in self.frames]
        frames[0].save(destination, save_all=True, append_images=frames[1:],
                       duration=int(round(1000 * self.interval)), loop=0,
                       optimize=False, disposal=2)
        return len(frames)
