"""Drive real X11 mouse events across unrelated Chrome + Minecraft windows.

This exercises the same global click path used by a human and checks native
world state independently of any HTML page or Chrome extension.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageGrab


def xdo(*args):
    subprocess.run(['xdotool',*map(str,args)],check=True,timeout=6)


def press(button:int,x:int,y:int):
    xdo('mousemove','--sync',x,y)
    xdo('click',button)
    time.sleep(.17)
    print('X11_MOUSE_BUILD='+json.dumps({'button':button,'x':x,'y':y}),flush=True)


def drag(x0:int,y0:int,x1:int,y1:int, button:int=1):
    xdo('mousemove','--sync',x0,y0)
    xdo('mousedown',button)
    for step in range(1,7):
        x=x0+(x1-x0)*step//6
        y=y0+(y1-y0)*step//6
        xdo('mousemove','--sync',x,y)
        time.sleep(.065)
    xdo('mouseup',button)
    time.sleep(.21)
    print('X11_DRAG_BUILD='+json.dumps({'from':[x0,y0],'to':[x1,y1]}),flush=True)


def key(controller:str,key:str):
    xdo('key','--window',controller,key)
    time.sleep(.2)
    print('X11_KEY_INPUT='+key,flush=True)


def screenshot(path):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    ImageGrab.grab(xdisplay=__import__('os').environ['DISPLAY']).save(p)
    print('REAL_DESKTOP_SCREENSHOT='+str(p),flush=True)


def check_world(path,minimum:int, required=None):
    p=Path(path)
    if not p.exists():raise RuntimeError('Builder did not save the world')
    obj=json.loads(p.read_text())
    blocks=obj['blocks']
    if len(blocks)<minimum:
        raise RuntimeError(f'Expected {minimum} native desktop blocks, got {len(blocks)}')
    if required:
        names={b['material'] for b in blocks}
        if not set(required).issubset(names):
            raise RuntimeError(f'Expected materials {required}, got {names}')
    print('NATIVE_DESKTOP_WORLD_VERIFIED='+json.dumps({'blocks':len(blocks),
        'materials':list(sorted({b['material'] for b in blocks})),
        'left':min(b['x'] for b in blocks),'right':max(b['x'] for b in blocks),
        'version':obj['version']}),flush=True)
    return obj


def do_build(controller,world,out):
    # Build a bridge from the Minecraft browser across the program boundary
    # and onto the native surface of an entirely unrelated Wikipedia browser.
    drag(715,465,1028,465)
    press(1,1085,416)
    press(1,1085,368)
    press(1,1085,320)
    key(controller,'1')  # stone, from actual game hotbar
    drag(1190,500,1375,500)
    key(controller,'7')  # log, also sampled from the visible Minecraft game
    press(1,1240,453)
    press(1,1240,405)
    key(controller,'3')  # planks
    press(1,1135,154)  # on Chrome's *real* address bar
    press(1,1450,305)  # anywhere on the unrelated website
    press(3,1085,320)  # mine one of the placed blocks
    check_world(world,minimum=14,required=('planks','stone','log'))
    screenshot(Path(out)/'minecraft-blocks-on-wikipedia.png')
    key(controller,'Escape')
    print('BLOCKS_REMAIN_IN_BROWSE_MODE=true',flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--drive',default='',help='X11 id of the WindowRift builder controller')
    p.add_argument('--world',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    if args.drive:
        do_build(args.drive,args.world,args.out)
    elif args.check:
        check_world(args.world,minimum=14,required=('planks','stone','log'))
    else:p.error('Use --drive or --check')


if __name__=='__main__':main()
