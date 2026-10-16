"""Wait for the actual visible Minecraft Classic world, not just its canvas.

Minecraft Classic exposes a WebGL canvas before its level-generation screen
has finished. This X11 read-only check inspects visible sky/terrain pixels in
the genuine browser window and never fabricates the source screenshot.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageGrab
from windowrift.windows import list_windows


def visible_world_colors(image: Image.Image) -> dict:
    """Coarse outside-visible evidence that the level is no longer a brown load screen."""
    rgb = np.asarray(image.convert('RGB').resize((210, 115)), dtype=np.float32)
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    sky = ((blue > 115) & (blue > red * 1.14) & (blue > green * 1.035))
    grass = ((green > 48) & (green > red * 1.13) & (green > blue * 1.04))
    return {'sky': round(float(sky.mean()), 3), 'green': round(float(grass.mean()), 3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--screenshot',type=Path,required=True)
    parser.add_argument('--timeout',type=float,default=95)
    args=parser.parse_args()
    if not os.environ.get('DISPLAY'):
        parser.error('Actual X11 display required')
    deadline=time.monotonic()+args.timeout
    last=None
    while time.monotonic()<deadline:
        candidates=[w for w in list_windows() if 'Minecraft Classic' in w.title]
        if len(candidates)==1:
            w=candidates[0]
            bounds=w.bounds
            region=(round(bounds.x+45),round(bounds.y+150),
                    round(bounds.x+bounds.width-35),round(bounds.y+bounds.height-110))
            if region[2]>region[0] and region[3]>region[1]:
                screen=ImageGrab.grab(xdisplay=os.environ['DISPLAY'])
                observed=visible_world_colors(screen.crop(region))
                last=observed
                if observed['sky']>0.05 and observed['green']>0.045:
                    args.screenshot.parent.mkdir(parents=True,exist_ok=True)
                    screen.save(args.screenshot)
                    print('MINECRAFT_ACTUAL_WORLD_RENDERED='+json.dumps(observed),flush=True)
                    print('MINECRAFT_SOURCE_SCREENSHOT='+str(args.screenshot),flush=True)
                    return
        time.sleep(.65)
    raise SystemExit('Minecraft Classic was not visibly in a playable level: '+json.dumps(last))

if __name__=='__main__':
    main()
