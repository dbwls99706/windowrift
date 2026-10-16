"""Native isometric block visualization, optionally using *user-owned* game jar textures.

This renderer does not represent Minecraft block physics or replace real world
state checks. Textures are read locally in memory and never redistributed.
"""
from __future__ import annotations
import hashlib,io
from pathlib import Path
from zipfile import ZipFile,BadZipFile
from PIL import Image,ImageDraw

TEXTURES={
 'minecraft:stone':('stone','stone'),
 'minecraft:dirt':('dirt','dirt'),
 'minecraft:grass_block':('grass_block_top','grass_block_side'),
 'minecraft:oak_planks':('oak_planks','oak_planks'),
 'minecraft:spruce_planks':('spruce_planks','spruce_planks'),
 'minecraft:birch_planks':('birch_planks','birch_planks'),
 'minecraft:cobblestone':('cobblestone','cobblestone'),
 'minecraft:bricks':('bricks','bricks'),
 'minecraft:glass':('glass','glass'),
 'minecraft:oak_stairs':('oak_planks','oak_planks'),
 'minecraft:spruce_stairs':('spruce_planks','spruce_planks'),
 'minecraft:oak_log':('oak_log_top','oak_log'),
 'minecraft:birch_log':('birch_log_top','birch_log'),
 'minecraft:sand':('sand','sand'),
 'minecraft:deepslate':('deepslate_top','deepslate'),
 'minecraft:polished_andesite':('polished_andesite','polished_andesite'),
}
COLORS={
 'stone':(116,116,119),'dirt':(119,83,55),'grass_block':(101,142,64),
 'oak_planks':(172,131,76),'spruce_planks':(93,67,46),
 'birch_planks':(211,193,145),'cobblestone':(117,116,118),
 'bricks':(150,80,68),'glass':(167,209,223),'oak_log':(116,86,53),
 'birch_log':(203,191,149),'sand':(218,209,157),
 'deepslate':(77,76,78),'polished_andesite':(143,143,143)
}

def placeholder(material:str)->Image.Image:
    key=material.split(':')[-1]
    if key.endswith('_stairs'):
        key=key[:-7]+'_planks'
    color=COLORS.get(key,(156,135,107))
    img=Image.new('RGBA',(16,16))
    digest=hashlib.sha256(material.encode()).digest()
    pixels=img.load()
    for y in range(16):
        for x in range(16):
            delta=digest[(x+y*7)%32]%28-14
            pixels[x,y]=(*(max(0,min(255,c+delta)) for c in color),255)
    return img

def game_texture(material:str,game_jar:Path|None,*,side:bool=False)->tuple[Image.Image,bool]:
    names=TEXTURES.get(material)
    if game_jar is not None and names is not None:
        name=names[int(side)]
        member=f'assets/minecraft/textures/block/{name}.png'
        try:
            with ZipFile(game_jar) as jar:
                meta=jar.getinfo(member)
                if meta.file_size>1024*1024:
                    raise ValueError('Excessively large texture')
                texture=Image.open(io.BytesIO(jar.read(member))).convert('RGBA')
                if max(texture.size)>512:
                    raise ValueError('Invalid texture dimensions')
                return texture.resize((16,16),Image.Resampling.NEAREST),True
        except (FileNotFoundError,BadZipFile,KeyError,OSError,ValueError):
            pass
    return placeholder(material),False

def draw_face(paint:ImageDraw.ImageDraw,texture:Image.Image,corners,shade=1.0):
    px=texture.resize((16,16),Image.Resampling.NEAREST).convert('RGBA').load()
    def interpolate(u,v):
        p0,p1,p2,p3=corners
        return (p0[0]*(1-u)*(1-v)+p1[0]*u*(1-v)+p2[0]*u*v+p3[0]*(1-u)*v,
                p0[1]*(1-u)*(1-v)+p1[1]*u*(1-v)+p2[1]*u*v+p3[1]*(1-u)*v)
    for y in range(16):
        for x in range(16):
            r,g,b,a=px[x,y]
            if a<20:continue
            u=x/16;v=y/16;du=1/16;dv=1/16
            paint.polygon([interpolate(u,v),interpolate(u+du,v),interpolate(u+du,v+dv),interpolate(u,v+dv)],
                          fill=(int(r*shade),int(g*shade),int(b*shade),a))

def render_cube(material:str,game_jar:Path|None=None,*,size:int=128)->tuple[Image.Image,bool]:
    """Return (isometric image, is texture authentic?). Stairs geometry approximated."""
    if not 48<=size<=384:
        raise ValueError('Cube render size outside 48–384')
    top,real_top=game_texture(material,game_jar)
    side,real_side=game_texture(material,game_jar,side=True)
    art=Image.new('RGBA',(112,120))
    d=ImageDraw.Draw(art)
    draw_face(d,side,((10,38),(56,62),(56,112),(10,88)),.67)
    draw_face(d,side,((56,62),(102,38),(102,88),(56,112)),.85)
    draw_face(d,top,((56,11),(102,38),(56,62),(10,38)),1.0)
    return art.resize((size,round(size*120/112)),Image.Resampling.NEAREST),real_top and real_side
