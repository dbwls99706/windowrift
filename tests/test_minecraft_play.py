"""The manual Minecraft demo may be imported without a running X server."""
import pytest

pytest.importorskip("PIL")

from PIL import Image


def test_source_sprite_texture_is_a_small_local_png():
    # Import from examples by an explicit repository-local path; the test does
    # not launch an X11 or Chrome application.
    import importlib.util
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "examples"))
    spec = importlib.util.spec_from_file_location("minecraft_play_demo", root / "examples/minecraft_play_demo.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    image = Image.new("RGBA", (30, 30), (90, 100, 30, 255))
    encoded = module.sprite_png(image)
    assert encoded.startswith("data:image/png;base64,")


def test_crop_rejects_out_of_bounds_or_tiny_rectangles():
    import importlib.util
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "examples"))
    spec = importlib.util.spec_from_file_location("minecraft_play_demo", root / "examples/minecraft_play_demo.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.parse_crop("290,636,36,40") == (290,636,36,40)
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        module.parse_crop("-1,10,40,40")
