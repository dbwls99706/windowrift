"""Shared desktop collision physics for native-state and visual-only actors.

All coordinates are absolute virtual-desktop pixels. Browser pages never need
a WindowRift script and the source application is not patched.
"""
from __future__ import annotations

from dataclasses import replace

from .controller import Controls, Player, Surface, step
from .desktop_world import DesktopWorld
from .geometry import Rect


def block_surfaces(world: DesktopWorld) -> list[Surface]:
    return [Surface(f"desktop-block:{b.x}:{b.y}",
                    Rect(b.x, b.y, world.size, world.size))
            for b in world.blocks]


def desktop_step(player: Player, keys: Controls, dt: float,
                 desktop: Rect, world: DesktopWorld) -> Player:
    """Step a keyboard-controlled actor with solid desktop block collisions.

    The existing platform controller handles grounded jumps, landings, and
    one-way drop-through. This layer additionally prevents walking through
    the sides of blocks and jumping upward through their undersides.
    """
    next_player = step(player, keys, dt, desktop, block_surfaces(world))
    x, y, vx, vy = (next_player.x, next_player.y,
                     next_player.vx, next_player.vy)
    for b in world.blocks:
        left, right = b.x, b.x + world.size
        top, bottom = b.y, b.y + world.size
        old_r = player.x + player.width
        new_r = x + player.width
        intersects_y = (y + player.height > top and y < bottom)
        if intersects_y:
            if old_r <= left and new_r > left:
                x = min(x, left - player.width)
                vx = min(vx, 0.0)
            elif player.x >= right and x < right:
                x = max(x, right)
                vx = max(vx, 0.0)
        if (vy < 0 and player.y >= bottom and y < bottom
                and x + player.width > left and x < right):
            y = bottom
            vy = 0.0
    return replace(next_player, x=x, y=y, vx=vx, vy=vy)
