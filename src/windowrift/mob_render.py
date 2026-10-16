"""Opt-in native pixel-model representation using owner's Minecraft client JAR.

Actual game data is never shipped with WindowRift. This desktop representation
does not run Minecraft's AI or renderer; the native UUID lives on the server.
"""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from PIL import Image, ImageDraw

ZOMBIE_TEXTURE = "assets/minecraft/textures/entity/zombie/zombie.png"


def _part(atlas, box, scale=4):
    image = atlas.crop(box)
    return image.resize((image.width * scale, image.height * scale),
                        Image.Resampling.NEAREST)


def _zombie_skin(game_jar):
    if game_jar is None:
        return None
    try:
        with ZipFile(game_jar) as z:
            info = z.getinfo(ZOMBIE_TEXTURE)
            if info.file_size > 1_000_000:
                raise ValueError("Oversized Minecraft texture")
            image = Image.open(BytesIO(z.read(info))).convert("RGBA")
            if image.width < 64 or image.height < 64:
                raise ValueError("Unexpected Minecraft skin size")
            return image
    except (FileNotFoundError, KeyError, BadZipFile, ValueError, OSError):
        return None


def render_mob(entity_type: str, game_jar: Path | None, *,
               step: int = 0) -> tuple[Image.Image, bool]:
    if entity_type != "minecraft:zombie":
        image = Image.new("RGBA", (72, 116))
        draw = ImageDraw.Draw(image)
        draw.ellipse((10, 6, 62, 50), fill=(110, 133, 115))
        draw.rectangle((17, 42, 54, 87), fill=(77, 96, 105))
        draw.rectangle((20, 78, 32, 111), fill=(54, 61, 75))
        draw.rectangle((40, 78, 52, 111), fill=(54, 61, 75))
        return image, False
    skin = _zombie_skin(game_jar)
    authentic = skin is not None
    if skin is None:
        skin = Image.new("RGBA", (64, 64))
        draw = ImageDraw.Draw(skin)
        draw.rectangle((8, 8, 15, 15), fill=(83, 157, 72))
        draw.rectangle((20, 20, 27, 31), fill=(62, 100, 110))
        draw.rectangle((44, 20, 47, 31), fill=(80, 142, 72))
        draw.rectangle((4, 20, 7, 31), fill=(56, 73, 101))
        draw.rectangle((9, 11, 10, 12), fill=(26, 26, 31))
        draw.rectangle((13, 11, 14, 12), fill=(26, 26, 31))
    view = Image.new("RGBA", (104, 144))
    swing = 6 if step % 4 in (1, 2) else -6
    arm = _part(skin, (44, 20, 48, 32))
    leg = _part(skin, (4, 20, 8, 32))
    view.alpha_composite(arm, (11, 39 + swing))
    view.alpha_composite(arm, (76, 39 - swing))
    view.alpha_composite(leg, (34, 87 + max(0, swing)))
    view.alpha_composite(leg, (54, 87 + max(0, -swing)))
    view.alpha_composite(_part(skin, (20, 20, 28, 32)), (36, 38))
    view.alpha_composite(_part(skin, (8, 8, 16, 16)), (36, 4))
    return view, authentic
