import pytest

from windowrift.choreography import cinematic_pose, scene_duration
from windowrift.geometry import Rect


BAR = Rect(930, 140, 440, 35)
BROWSER = Rect(810, 90, 730, 700)
ORIGIN = (220, 340)
SIZE = (58, 58)


def test_cinematic_has_distinct_phases_and_returns_to_game():
    moments = {time: cinematic_pose(ORIGIN, BAR, BROWSER, SIZE, time)
               for time in (0.0, 0.7, 1.8, 2.8, 3.72, 4.8, 6.8, 8.4)}
    assert [pose.phase for pose in moments.values()] == [
        'escape', 'escape', 'perch', 'pounce', 'impact', 'rebound', 'return', 'returned'
    ]
    assert moments[0].x == ORIGIN[0]
    assert moments[0].y == ORIGIN[1]
    assert (moments[8.4].x, moments[8.4].y) == ORIGIN
    assert moments[3.72].impact
    assert not moments[4.8].impact
    assert scene_duration() > 8


def test_jump_moves_actor_above_interpolated_route():
    early = cinematic_pose(ORIGIN, BAR, BROWSER, SIZE, 0.0)
    middle = cinematic_pose(ORIGIN, BAR, BROWSER, SIZE, 0.775)
    landed = cinematic_pose(ORIGIN, BAR, BROWSER, SIZE, 1.55)
    assert middle.y < min(early.y, landed.y)
    assert middle.x > early.x
    assert landed.x > middle.x


def test_actor_hits_explicit_page_target_and_browser_move_reprojects():
    target = (1202, 553)
    at = cinematic_pose(ORIGIN, BAR, BROWSER, SIZE, 3.65, impact_target=target)
    assert abs(at.x + SIZE[0]/2 - target[0]) <= 1
    assert abs(at.y + SIZE[1]/2 - target[1]) <= 1
    moved = cinematic_pose(ORIGIN, Rect(BAR.x + 80, BAR.y + 25, BAR.width, BAR.height),
                           Rect(BROWSER.x + 80, BROWSER.y + 25, BROWSER.width, BROWSER.height),
                           SIZE, 3.65)
    original = cinematic_pose(ORIGIN, BAR, BROWSER, SIZE, 3.65)
    assert moved.x - original.x == 80
    assert moved.y - original.y == 25


def test_bad_geometry_is_rejected():
    with pytest.raises(ValueError):
        cinematic_pose(ORIGIN, Rect(2, 3, 3, 5), BROWSER, SIZE, 2.5)


def test_no_teleporting_at_scene_boundaries():
    for boundary in (1.55, 2.35, 3.65, 4.45, 6.15, 7.95):
        before = cinematic_pose(ORIGIN, BAR, BROWSER, SIZE, boundary - 0.001)
        after = cinematic_pose(ORIGIN, BAR, BROWSER, SIZE, boundary + 0.001)
        assert abs(before.x - after.x) < 25, boundary
        assert abs(before.y - after.y) < 25, boundary
