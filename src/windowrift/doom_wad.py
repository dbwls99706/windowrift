"""Read a selected sprite from a caller-provided DOOM IWAD.

This intentionally narrow, read-only demo adapter never downloads, ships, or
modifies commercial game data. WindowRift's generic screen capture is separate.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image

MAX_WAD_BYTES = 64 * 1024 * 1024
MAX_LUMPS = 65536
MAX_PATCH_SIDE = 1024


class WadError(ValueError):
    """The caller-provided game archive is missing or malformed."""


def _directory(data: bytes) -> dict[str, bytes]:
    if len(data) < 12 or data[:4] not in (b"IWAD", b"PWAD"):
        raise WadError("Expected an IWAD/PWAD container.")
    count, offset = struct.unpack_from("<II", data, 4)
    if count > MAX_LUMPS or offset > len(data) or count * 16 > len(data) - offset:
        raise WadError("WAD directory is outside the selected file.")
    lumps: dict[str, bytes] = {}
    for index in range(count):
        position, length, raw_name = struct.unpack_from("<II8s", data, offset + index * 16)
        if position > len(data) or length > len(data) - position:
            raise WadError(f"WAD entry {index} points outside the selected file.")
        name = raw_name.rstrip(b"\x00").decode("ascii", "replace").upper()
        lumps[name] = data[position:position + length]
    return lumps


def doom_patch_sprite(path: str | Path, name: str = "TROOA1") -> Image.Image:
    """Decode a DOOM picture patch with PLAYPAL into a transparent RGBA sprite.

    Supports the ordinary 8-bit column posts used by the shareware sprites.
    No WAD bytes or extracted sprites are persisted by this function.
    """
    path = Path(path)
    size = path.stat().st_size
    if size < 12 or size > MAX_WAD_BYTES:
        raise WadError("WAD file must be between 12 bytes and 64 MiB.")
    lumps = _directory(path.read_bytes())
    palette = lumps.get("PLAYPAL")
    if palette is None or len(palette) < 768:
        raise WadError("The WAD has no complete PLAYPAL palette.")
    key = name.upper()
    if not (1 <= len(key) <= 8 and key.isascii() and key.isalnum()):
        raise WadError("Sprite lump name must contain 1-8 ASCII letters or digits.")
    patch = lumps.get(key)
    if patch is None or len(patch) < 12:
        raise WadError(f"No complete sprite patch named {key}.")
    width, height = struct.unpack_from("<HH", patch)
    if not (1 <= width <= MAX_PATCH_SIDE and 1 <= height <= MAX_PATCH_SIDE):
        raise WadError("Sprite dimensions are outside the bounded patch format.")
    if len(patch) < 8 + 4 * width:
        raise WadError("Sprite column offsets are truncated.")
    pixels = bytearray(width * height * 4)
    for x in range(width):
        cursor = struct.unpack_from("<I", patch, 8 + 4 * x)[0]
        if cursor >= len(patch):
            raise WadError(f"Sprite column {x} points outside its patch.")
        posts = 0
        previous_top = -1
        while True:
            if cursor >= len(patch):
                raise WadError(f"Sprite column {x} has no terminator.")
            top = patch[cursor]
            cursor += 1
            if top == 0xff:
                break
            if cursor + 2 > len(patch):
                raise WadError("Sprite column post header is truncated.")
            count = patch[cursor]
            cursor += 2  # length, unused byte
            if cursor + count + 1 > len(patch):
                raise WadError("Sprite column post data is truncated.")
            # DOOM's tall patch extension encodes a relative top when it does
            # not exceed the preceding post's top; reject out-of-bounds rows.
            if previous_top >= 0 and top <= previous_top:
                top += previous_top
            previous_top = top
            if top + count > height:
                raise WadError("Sprite column post extends below the picture.")
            for y in range(top, top + count):
                color = patch[cursor + y - top]
                dest = 4 * (y * width + x)
                pixels[dest:dest + 3] = palette[color * 3:color * 3 + 3]
                pixels[dest + 3] = 255
            cursor += count + 1  # data and trailing unused byte
            posts += 1
            if posts > height + 1:
                raise WadError("Sprite column contains too many posts.")
    sprite = Image.frombytes("RGBA", (width, height), bytes(pixels))
    bounds = sprite.getchannel("A").getbbox()
    if bounds is None:
        raise WadError("Selected sprite is fully transparent.")
    return sprite.crop(bounds)
