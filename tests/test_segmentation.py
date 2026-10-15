import numpy as np
import pytest
from PIL import Image

from windowrift.segmentation import (
    SegmentationError, extract_object, grabcut_foreground, trim_alpha
)


def test_grabcut_extracts_centered_colored_object():
    data = np.full((100, 100, 3), (40, 55, 70), dtype=np.uint8)
    data[25:75, 30:70] = (230, 95, 55)
    image = Image.fromarray(data, 'RGB')
    result = grabcut_foreground(image)
    assert result.mode == 'RGBA'
    assert 30 <= result.width <= 90
    assert 45 <= result.height <= 90
    assert np.asarray(result.getchannel('A')).max() == 255


def test_alpha_trim_preserves_nontransparent_content():
    image = Image.new('RGBA', (50, 50), (10, 10, 10, 0))
    for y in range(15, 30):
        for x in range(10, 30):
            image.putpixel((x, y), (255, 0, 0, 255))
    result = trim_alpha(image, padding=0)
    assert result.size == (20, 15)
    assert result.getpixel((0, 0)) == (255, 0, 0, 255)


def test_transparent_image_is_refused():
    with pytest.raises(SegmentationError, match='No visible object'):
        trim_alpha(Image.new('RGBA', (20, 20), (0, 0, 0, 0)))


def test_rectangle_fallback_needs_no_ml_model():
    image = Image.new('RGB', (31, 35), (255, 0, 0))
    result = extract_object(image, 'crop')
    assert result.size == image.size
    assert result.mode == 'RGBA'


def test_invalid_mode_refused():
    with pytest.raises(ValueError, match='Unknown segmentation mode'):
        extract_object(Image.new('RGB', (40, 40)), 'magic')


def test_live_extract_retains_crop_size_and_alpha_mask():
    data = np.full((100, 100, 3), (40, 55, 70), dtype=np.uint8)
    data[25:75, 30:70] = (230, 95, 55)
    image = Image.fromarray(data, 'RGB')
    result = extract_object(image, 'grabcut', trim=False)
    assert result.size == (100, 100)
    alpha = np.asarray(result.getchannel('A'))
    assert np.any(alpha == 255) and np.any(alpha == 0)
