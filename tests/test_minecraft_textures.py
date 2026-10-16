import io
from zipfile import ZipFile
from PIL import Image
from windowrift.minecraft_textures import render_cube,game_texture

def test_placeholder_is_not_misrepresented_as_game_texture():
    img,real=render_cube('minecraft:stone')
    assert not real and img.width==128 and img.getbbox()

def test_owned_minecraft_jar_texture_is_used(tmp_path):
    raw=io.BytesIO()
    Image.new('RGB',(16,16),(233,71,39)).save(raw,'PNG')
    jar=tmp_path/'client.jar'
    with ZipFile(jar,'w') as z:
        z.writestr('assets/minecraft/textures/block/stone.png',raw.getvalue())
    tex,real=game_texture('minecraft:stone',jar)
    assert real and tex.getpixel((1,1))[:3]==(233,71,39)
    _,is_original=render_cube('minecraft:stone',jar)
    assert is_original
