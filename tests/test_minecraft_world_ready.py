from PIL import Image
from scripts.ci.minecraft_world_ready import visible_world_colors


def test_generation_screen_is_not_accepted_as_a_loaded_minecraft_world():
    result=visible_world_colors(Image.new('RGB',(400,200),(75,52,40)))
    assert result['sky']<.05 and result['green']<.045


def test_world_ready_requires_both_sky_and_terrain_colors():
    world=Image.new('RGB',(420,240),(115,190,245))
    world.paste((55,140,45),(0,110,420,240))
    result=visible_world_colors(world)
    assert result['sky']>.05 and result['green']>.045
