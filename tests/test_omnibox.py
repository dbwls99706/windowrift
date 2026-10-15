from windowrift.geometry import Rect
from windowrift.omnibox import OmniboxCalibration, looks_like_chrome, portal_position
from windowrift.windows import AppWindow
import pytest


def chrome(x=830, y=105):
    return AppWindow(19, "Google - Google Chrome", Rect(x, y, 745, 690))


def test_chrome_recognition_and_browser_widget_limits():
    assert looks_like_chrome(chrome())
    assert looks_like_chrome(AppWindow(20, "New Tab - Chromium", Rect(0, 0, 750, 600)))
    assert not looks_like_chrome(AppWindow(21, "Chrome profile backup", Rect(0, 0, 800, 600)))
    assert not looks_like_chrome(AppWindow(22, "Rift Arcade", Rect(0, 0, 800, 600)))
    with pytest.raises(ValueError, match="Chrome or Chromium"):
        OmniboxCalibration().anchor(AppWindow(22, "Rift Arcade", Rect(0, 0, 800, 600)))
    with pytest.raises(ValueError, match="too small"):
        OmniboxCalibration().anchor(AppWindow(19, "Chrome - Chromium", Rect(0, 0, 200, 90)))


def test_omnibox_anchor_follows_chrome_window_not_the_webpage():
    calibration = OmniboxCalibration()
    first = calibration.anchor(chrome())
    assert first == Rect(952, 152, 536, 36)
    assert calibration.anchor(chrome(980, 208)) == Rect(1102, 255, 536, 36)


def test_portal_moves_from_source_and_stays_in_toolbar():
    target = OmniboxCalibration().anchor(chrome())
    origin = (300.0, 350.0)
    assert portal_position(origin, target, (34, 34), 0.0) == (300, 350)
    mid = portal_position(origin, target, (34, 34), 0.9)
    assert mid[1] < 250  # visible jump across OS windows
    points = [portal_position(origin, target, (34, 34), t) for t in (1.8, 3, 6, 30)]
    assert all(target.x <= x and x + 34 <= target.right for x, y in points)
    assert all(y == 153 for x, y in points)
    assert len(set(x for x, _ in points)) >= 3
    with pytest.raises(ValueError, match="does not fit"):
        portal_position(origin, target, (900, 34), 2)


def test_portal_negative_time_safe_and_small_valid_window():
    target = OmniboxCalibration(left=10, right=10, top=25, height=30).anchor(
        AppWindow(1, "Tab - Chromium", Rect(0, 0, 200, 110))
    )
    assert target == Rect(10, 25, 180, 30)
    assert portal_position((7, 8), target, (24, 24), -1) == (7, 8)
