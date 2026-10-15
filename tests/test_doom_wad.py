"""Synthetic WAD fixtures only: no id Software game data in the repository."""

import struct

import pytest

from windowrift.doom_wad import WadError, doom_patch_sprite


def make_wad(*, palette=True, corrupt_directory=False, missing_end=False):
    # Small independently generated DOOM column-post patch, no game assets.
    colors = bytearray(768)
    for index in range(256):
        colors[3 * index:3 * index + 3] = bytes((index, 2 * index % 256, 255 - index))
    post0 = bytes((0, 2, 0, 1, 2, 0, 255))
    post1 = bytes((1, 1, 0, 3, 0)) + (b"" if missing_end else b"\xff")
    patch = struct.pack("<HHhhII", 2, 3, 0, 0, 16, 16 + len(post0)) + post0 + post1
    lumps = ([('PLAYPAL', bytes(colors))] if palette else []) + [('TROOA1', patch)]
    content = bytearray(b'IWAD' + b'\x00' * 8)
    listing = []
    for name, data in lumps:
        off = len(content)
        content.extend(data)
        listing.append((off, len(data), name))
    directory = len(content)
    for off, size, name in listing:
        content.extend(struct.pack('<II8s', off, size, name.encode().ljust(8, b'\x00')))
    struct.pack_into('<II', content, 4, len(lumps), len(content) + 10 if corrupt_directory else directory)
    return bytes(content)


def test_decode_selected_genuine_wad_patch_format(tmp_path):
    path = tmp_path / 'fixture.wad'
    path.write_bytes(make_wad())
    image = doom_patch_sprite(path)
    assert image.mode == 'RGBA'
    assert image.size == (2, 2)
    assert image.getpixel((0, 0)) == (1, 2, 254, 255)
    assert image.getpixel((1, 0)) == (0, 0, 0, 0)
    assert image.getpixel((1, 1)) == (3, 6, 252, 255)


@pytest.mark.parametrize('options,expected', [
    ({'palette': False}, 'PLAYPAL'),
    ({'corrupt_directory': True}, 'directory'),
    ({'missing_end': True}, 'terminator'),
])
def test_refuse_incomplete_or_corrupt_wads(tmp_path, options, expected):
    path = tmp_path / 'bad.wad'
    path.write_bytes(make_wad(**options))
    with pytest.raises(WadError, match=expected):
        doom_patch_sprite(path)


def test_refuse_wrong_magic_and_missing_lump(tmp_path):
    path = tmp_path / 'bad.wad'
    path.write_bytes(b'NOTWAD' + b'\x00' * 20)
    with pytest.raises(WadError, match='IWAD/PWAD'):
        doom_patch_sprite(path)
    path.write_bytes(make_wad())
    with pytest.raises(WadError, match='no complete sprite|No complete sprite'):
        doom_patch_sprite(path, 'UNKNOWN')
    with pytest.raises(WadError, match='name'):
        doom_patch_sprite(path, '../../foo')
