from PIL import Image, ImageDraw
import pytest

from windowrift.tracking import locate_object


def object_template() -> Image.Image:
    image = Image.new('RGBA', (48, 44), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 4, 40, 36), fill=(65, 240, 145, 255))
    draw.rectangle((16, 18, 21, 23), fill=(9, 18, 38, 255))
    draw.rectangle((29, 18, 34, 23), fill=(9, 18, 38, 255))
    return image


def scene(x: int, y: int, *, present=True) -> Image.Image:
    screen = Image.new('RGB', (210, 150), (14, 22, 39))
    if present:
        screen.paste(object_template(), (x, y), object_template())
    return screen


@pytest.mark.parametrize('x,y', [(0, 0), (42, 51), (130, 84)])
def test_find_object_without_matching_uniform_background(x, y):
    found = locate_object(scene(x, y), object_template())
    assert found is not None
    assert abs(found.x - x) <= 1
    assert abs(found.y - y) <= 1
    assert found.confidence > 0.96


def test_refuse_absent_object_and_low_alpha():
    assert locate_object(scene(0, 0, present=False), object_template()) is None
    assert locate_object(scene(20, 20), Image.new('RGBA', (48, 44))) is None


def test_refuse_smaller_search_area():
    assert locate_object(Image.new('RGB', (20, 20)), object_template()) is None


def test_large_template_downsampling():
    templ = object_template().resize((288, 264), Image.Resampling.NEAREST)
    window = Image.new('RGB', (420, 360), (14, 22, 39))
    window.paste(templ, (66, 48), templ)
    found = locate_object(window, templ)
    assert found is not None
    assert abs(found.x - 66) <= 2
    assert abs(found.y - 48) <= 2
