from io import BytesIO
from zipfile import ZipFile
from PIL import Image
from windowrift.mob_render import render_mob


def test_mob_texture_is_loaded_only_from_caller_supplied_jar(tmp_path):
    jar = tmp_path / "client.jar"
    tex = Image.new("RGBA", (64, 64), (30, 180, 60, 255))
    with ZipFile(jar, "w") as zipfile:
        data = BytesIO()
        tex.save(data, format="PNG")
        zipfile.writestr("assets/minecraft/textures/entity/zombie/zombie.png",
                         data.getvalue())
    image, real = render_mob("minecraft:zombie", jar)
    assert real and image.mode == "RGBA" and image.size == (104, 144)
    assert image.getchannel("A").getbbox()
    alternate, real2 = render_mob("minecraft:zombie", jar, step=1)
    assert real2 and alternate.tobytes() != image.tobytes()


def test_fallback_is_not_credited_as_real_texture():
    image, real = render_mob("minecraft:zombie", None)
    assert not real and image.getchannel("A").getbbox()
    other, real = render_mob("minecraft:cow", None)
    assert not real and other.getbbox()
