"""Test the CI visual readiness detector without importing an uninstalled scripts package."""
import importlib.util
from pathlib import Path

from PIL import Image


def classifier():
    path = Path(__file__).resolve().parents[1] / "scripts/ci/minecraft_world_ready.py"
    spec = importlib.util.spec_from_file_location("minecraft_world_ready", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.visible_world_colors


def test_generation_screen_is_not_accepted_as_loaded_minecraft_world():
    result = classifier()(Image.new("RGB", (400, 200), (75, 52, 40)))
    assert result["sky"] < .05 and result["green"] < .045


def test_world_ready_requires_both_sky_and_terrain_colors():
    world = Image.new("RGB", (420, 240), (115, 190, 245))
    world.paste((55, 140, 45), (0, 110, 420, 240))
    result = classifier()(world)
    assert result["sky"] > .05 and result["green"] > .045
