import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from windowrift.capture import capture_region, clipped_region
from windowrift.geometry import Rect
from windowrift.live import MAX_LIVE_PIXELS, SourceCrop, composite_live_frame, overlaps
from windowrift.windows import AppWindow


def test_live_mask_preserves_alpha_and_updates_color():
    matte = Image.new('RGBA', (3, 2), (255, 0, 0, 0))
    matte.putpixel((1, 1), (1, 2, 3, 255))
    frame = Image.new('RGB', (3, 2), (3, 90, 150))
    result = composite_live_frame(frame, matte)
    assert result.size == matte.size
    assert result.getpixel((1, 1)) == (3, 90, 150, 255)
    assert result.getpixel((0, 0)) == (3, 90, 150, 0)
    assert np.array_equal(np.asarray(result.getchannel('A')), np.asarray(matte.getchannel('A')))


def test_live_refuses_wrong_source_frame_dimensions():
    with pytest.raises(ValueError, match='sizes differ'):
        composite_live_frame(Image.new('RGB', (1, 1)), Image.new('RGBA', (2, 2)))


def test_live_source_follows_moved_window_and_refuses_resize():
    source = SourceCrop(14, 45, 80, 200, 110)
    window = AppWindow(14, 'Game', Rect(-30, 40, 400, 300))
    assert source.bounds(window) == Rect(15, 120, 200, 110)
    moved = AppWindow(14, 'Game', Rect(400, 200, 400, 300))
    assert source.bounds(moved) == Rect(445, 280, 200, 110)
    with pytest.raises(ValueError, match='no longer fits'):
        source.bounds(AppWindow(14, 'Game', Rect(0, 0, 220, 150)))
    with pytest.raises(ValueError, match='no longer available'):
        source.bounds(AppWindow(15, 'Different', Rect(0, 0, 400, 300)))


def test_live_budget_and_overlay_intersection():
    assert SourceCrop(1, 0, 0, 512, 512).affordable
    assert not SourceCrop(1, 0, 0, 1024, 256).affordable
    assert overlaps(Rect(0, 0, 100, 100), Rect(90, 90, 10, 10))
    assert not overlaps(Rect(0, 0, 100, 100), Rect(100, 100, 10, 10))


def test_capture_coordinates_clip_to_visible_desktop():
    desktop = Rect(-100, 10, 500, 400)
    assert clipped_region(Rect(-200, -100, 300, 300), desktop) == (-100, 10, 200, 190)
    with pytest.raises(ValueError, match='outside'):
        clipped_region(Rect(1000, 1000, 25, 25), desktop)


def test_screen_capture_origin_and_live_clipping(monkeypatch):
    class FakeMSS:
        monitors = [{"left": -100, "top": 0, "width": 400, "height": 200}]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def grab(self, box):
            return SimpleNamespace(
                size=(box["width"], box["height"]),
                rgb=bytes([20, 40, 60]) * (box["width"] * box["height"]),
            )

    monkeypatch.setitem(sys.modules, 'mss', SimpleNamespace(mss=FakeMSS))
    frame = capture_region(Rect(-120, 10, 40, 30))
    assert (frame.x, frame.y, frame.image.size) == (-100, 10, (20, 30))
    assert frame.image.getpixel((0, 0)) == (20, 40, 60)
    with pytest.raises(ValueError, match='partially off-screen'):
        capture_region(Rect(-120, 10, 40, 30), exact=True)
