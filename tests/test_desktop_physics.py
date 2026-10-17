"""Game-independent solid geometry checks for cross-app desktop actors."""
from windowrift.controller import Controls, Player
from windowrift.desktop_physics import block_surfaces, desktop_step
from windowrift.desktop_world import DesktopWorld
from windowrift.geometry import Rect

SCREEN = Rect(0, 0, 900, 700)


def test_blocks_are_real_collision_surfaces_not_browser_elements():
    world = DesktopWorld(size=48)
    world.place(240, 400, "stone")
    surfaces = block_surfaces(world)
    assert len(surfaces) == 1
    assert surfaces[0].name == "desktop-block:240:384"
    assert surfaces[0].rect.y == 384


def test_player_can_land_on_desktop_block():
    w = DesktopWorld()
    w.place(240, 384, "stone")
    p = Player(242, 300, 30, 32)
    for _ in range(100):
        p = desktop_step(p, Controls(), 1/60, SCREEN, w)
    assert p.y == 384 - 32
    assert p.ground == "desktop-block:240:384"


def test_player_cannot_walk_through_block():
    w = DesktopWorld()
    w.place(288, 384, "stone")
    for x in range(192, 624, 48):
        w.place(x, 432, "planks")
    p = Player(228, 394, 30, 38)
    for _ in range(80):
        p = desktop_step(p, Controls(right=True), 1/60, SCREEN, w)
    assert p.x + p.width <= 288


def test_player_cannot_jump_through_block_ceiling():
    w = DesktopWorld()
    w.place(288, 288, "stone")
    p = Player(292, 336, 30, 38, ground="floor")
    p = desktop_step(p, Controls(jump=True), 1/60, SCREEN, w)
    assert p.y >= 336
    assert p.vy >= 0


def test_negative_monitor_coordinates():
    w = DesktopWorld()
    w.place(-192, 400, "planks")
    stage = Rect(-500, 0, 1400, 700)
    p = Player(-190, 350, 30, 32)
    for _ in range(60):
        p = desktop_step(p, Controls(), 1/60, stage, w)
    assert p.y == 384 - 32
