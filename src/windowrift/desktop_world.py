"""A persistent, screen-space block world independent of every browser DOM.

This module never modifies the Minecraft process or a web page.  Its blocks are
rendered in native transparent windows above arbitrary desktop applications.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

WORLD_VERSION = 1
MAX_BLOCKS = 256
MATERIALS = ('stone', 'dirt', 'planks', 'cobblestone', 'sand', 'gravel', 'log', 'leaves')


@dataclass(frozen=True)
class Block:
    x: int
    y: int
    material: str = 'planks'

    def __post_init__(self):
        if self.material not in MATERIALS:
            raise ValueError('Unsupported block material')
        if not (-32768 <= self.x <= 32768 and -32768 <= self.y <= 32768):
            raise ValueError('Block outside supported virtual desktop')


class DesktopWorld:
    """Click-to-place, drag-to-build, mine, undo, redo, and JSON persistence.

    One cell is owned by at most one block.  A stroke is a single undo action.
    Zero and negative coordinates work for multi-monitor virtual desktops.
    """
    def __init__(self, *, size: int = 48, max_blocks: int = MAX_BLOCKS):
        if not 24 <= size <= 128:
            raise ValueError('Block size must be 24..128')
        if not 1 <= max_blocks <= MAX_BLOCKS:
            raise ValueError('Block limit must be 1..256')
        self.size = int(size)
        self.max_blocks = int(max_blocks)
        self._blocks: dict[tuple[int, int], Block] = {}
        self._undo: list[dict[tuple[int, int], Block]] = []
        self._redo: list[dict[tuple[int, int], Block]] = []
        self._stroke_origin: dict[tuple[int, int], Block] | None = None

    @property
    def blocks(self) -> tuple[Block, ...]:
        return tuple(sorted(self._blocks.values(), key=lambda b: (b.y, b.x)))

    def cell(self, x: int | float, y: int | float) -> tuple[int, int]:
        s = self.size
        return int(x // s) * s, int(y // s) * s

    def colliding_blocks(self, x: float, y: float, width: float,
                         height: float) -> tuple[Block, ...]:
        """Return solid blocks overlapping a screen-space actor rectangle.

        The bounds use half-open intervals, so merely touching an edge does
        not count as penetration. This query is independent of window focus,
        browser DOM, and the application's origin.
        """
        import math
        values = (x, y, width, height)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and math.isfinite(v) for v in values):
            raise ValueError('Actor bounds must be finite numbers')
        if width <= 0 or height <= 0:
            raise ValueError('Actor bounds must have positive dimensions')
        right, bottom = x + width, y + height
        if not math.isfinite(right) or not math.isfinite(bottom):
            raise ValueError('Actor bounds overflow')
        return tuple(b for b in self.blocks
                     if b.x < right and b.x + self.size > x
                     and b.y < bottom and b.y + self.size > y)

    def supported_position(self, x: float, y: float, width: float,
                           height: float, *, tolerance: float = 1.0) -> bool:
        """Check whether a desktop actor has block support directly below.

        Callers retain control of game physics; this supplies a deterministic
        collision primitive for actors from multiple application adapters.
        """
        import math
        if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool):
            raise ValueError('Invalid support tolerance')
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError('Invalid support tolerance')
        self.colliding_blocks(x, y, width, height)
        foot = y + height
        return any(b.x < x + width and b.x + self.size > x
                   and abs(b.y - foot) <= tolerance for b in self.blocks)

    def begin(self) -> None:
        if self._stroke_origin is not None:
            raise RuntimeError('A build stroke is already active')
        self._stroke_origin = dict(self._blocks)

    def commit(self) -> bool:
        original = self._stroke_origin
        if original is None:
            return False
        self._stroke_origin = None
        if original == self._blocks:
            return False
        self._undo.append(original)
        self._undo = self._undo[-80:]
        self._redo.clear()
        return True

    def _edit(self, action) -> bool:
        auto = self._stroke_origin is None
        if auto:
            self.begin()
        try:
            changed = action()
        finally:
            if auto:
                self.commit()
        return changed

    def place(self, x: int, y: int, material: str = 'planks') -> bool:
        if material not in MATERIALS:
            raise ValueError('Unsupported material')
        cell = self.cell(x, y)

        def make():
            old = self._blocks.get(cell)
            next_block = Block(*cell, material)
            if old == next_block:
                return False
            if old is None and len(self._blocks) >= self.max_blocks:
                raise ValueError('Desktop block limit reached')
            self._blocks[cell] = next_block
            return True
        return self._edit(make)

    def mine(self, x: int, y: int) -> bool:
        cell = self.cell(x, y)
        return self._edit(lambda: self._blocks.pop(cell, None) is not None)

    def stroke_to(self, previous: tuple[int, int], current: tuple[int, int], *,
                  tool: str, material: str = 'planks') -> int:
        """Rasterize all crossed grid cells so quick mouse drags have no holes."""
        if tool not in ('place', 'mine'):
            raise ValueError('Unknown tool')
        x0, y0 = self.cell(*previous)
        x1, y1 = self.cell(*current)
        size = self.size
        dx, dy = abs((x1-x0)//size), abs((y1-y0)//size)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        modified = 0
        for _ in range(dx + dy + 1):
            if tool == 'place':
                modified += self.place(x0, y0, material)
            else:
                modified += self.mine(x0, y0)
            if x0 == x1 and y0 == y1:
                break
            doubled = 2 * err
            if doubled > -dy:
                err -= dy
                x0 += sx * size
            if doubled < dx:
                err += dx
                y0 += sy * size
        return modified

    def undo(self) -> bool:
        if self._stroke_origin is not None:
            self.commit()
        if not self._undo:
            return False
        self._redo.append(dict(self._blocks))
        self._blocks = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(dict(self._blocks))
        self._blocks = self._redo.pop()
        return True

    def clear(self) -> None:
        self._edit(lambda: self._blocks.clear())

    def to_json(self) -> str:
        payload = {'version': WORLD_VERSION, 'block_size': self.size,
                   'blocks': [{'x': b.x, 'y': b.y, 'material': b.material}
                              for b in self.blocks]}
        return json.dumps(payload, ensure_ascii=False, indent=2) + '\n'

    @classmethod
    def from_json(cls, raw: str) -> 'DesktopWorld':
        obj = json.loads(raw)
        if not isinstance(obj, dict) or obj.get('version') != WORLD_VERSION:
            raise ValueError('Unsupported desktop world format')
        size = obj.get('block_size')
        if not isinstance(size, int) or isinstance(size, bool):
            raise ValueError('Invalid world grid size')
        world = cls(size=size)
        blocks = obj.get('blocks')
        if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
            raise ValueError('Invalid block collection')
        for item in blocks:
            if not isinstance(item, dict):
                raise ValueError('Invalid block record')
            x, y = item.get('x'), item.get('y')
            if (not isinstance(x, int) or isinstance(x, bool) or
                    not isinstance(y, int) or isinstance(y, bool) or
                    (x, y) != world.cell(x, y)):
                raise ValueError('Blocks must be on-grid integer positions')
            b = Block(x, y, item.get('material', ''))
            if (x, y) in world._blocks:
                raise ValueError('Duplicate cell in world file')
            world._blocks[(x, y)] = b
        return world

    def save(self, target: Path) -> None:
        """Save atomically.  The user owns this local visual desktop world."""
        path = Path(target).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.windowrift-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(self.to_json())
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    @classmethod
    def load(cls, target: Path, *, size: int = 48) -> 'DesktopWorld':
        p = Path(target).expanduser()
        return cls.from_json(p.read_text(encoding='utf-8')) if p.exists() else cls(size=size)
