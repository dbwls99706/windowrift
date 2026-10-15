"""Real X11 jump / impact / rebound demo across a running game and Chrome.

An independent alpha-shaped OS window is animated above real applications;
this is not a game memory modification or a Chrome toolbar injection.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageGrab, ImageTk

from chrome_omnibox_demo import XShape, choose_windows
from windowrift.bridge import BrowserBridge
from windowrift.choreography import cinematic_pose, scene_duration
from windowrift.doom_wad import WadError, doom_patch_sprite
from windowrift.omnibox import OmniboxCalibration
from windowrift.proof_capture import ProofRecorder
from windowrift.segmentation import SegmentationError, extract_object


class NativeDemo:
    def __init__(self, root: tk.Tk, args: argparse.Namespace):
        self.root, self.args = root, args
        self.source, self.browser = choose_windows(args.source_title, args.browser_title)
        self.origin = (self.source.bounds.x + self.source.bounds.width / 2,
                       self.source.bounds.y + self.source.bounds.height / 2)
        self.target = json.loads(Path(args.target_file).read_text())["impact_point"]
        self.start = time.monotonic()
        self.last_discovery = 0.0
        self.last_sprite_sample = 0.0
        self.frames = []
        if args.doom_wad:
            for lump in ("TROOA1", "TROOB1", "TROOC1", "TROOD1"):
                try:
                    self.frames.append(doom_patch_sprite(args.doom_wad, lump))
                except WadError:
                    continue
            if not self.frames:
                raise RuntimeError("No supported DOOM sprite patches found in selected IWAD")
        else:
            self.sample_source()
        self.bridge = BrowserBridge(token=args.token, port=args.port)
        self.bridge.start()
        if self.bridge.error:
            raise RuntimeError(self.bridge.error)
        print('BROWSER_BRIDGE_READY=127.0.0.1', flush=True)
        self.recorder = ProofRecorder(interval=0.17, max_frames=75)
        self.box = max(80, int(args.actor_height * 1.65))
        root.withdraw()
        self.actor = tk.Toplevel(root)
        self.actor.title("WindowRift cinematic native actor")
        self.actor.overrideredirect(True)
        self.actor.wm_attributes("-topmost", True)
        self.actor.geometry(f"{self.box}x{self.box}+30+30")
        self.canvas = tk.Canvas(self.actor, width=self.box, height=self.box,
                                bg="white", highlightthickness=0)
        self.canvas.pack()
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        self.actor.update()
        self.shape = XShape(self.actor)
        self.photo = None
        self.done = False
        self.screenshot_saved = False
        self.actor.after(15, self.tick)

    def sample_source(self) -> None:
        x, y, w, h = self.args.crop
        screen = ImageGrab.grab(bbox=(int(self.source.bounds.x+x), int(self.source.bounds.y+y),
                                      int(self.source.bounds.x+x+w), int(self.source.bounds.y+y+h)),
                                xdisplay=os.environ["DISPLAY"])
        try:
            image = extract_object(screen, self.args.mode)
        except SegmentationError:
            if self.frames:
                return
            raise
        self.frames = [image]

    def draw(self, t, pose):
        source = self.frames[int(t / 0.17) % len(self.frames)].convert("RGBA")
        height = max(12, round(self.args.actor_height * pose.squash))
        width = max(12, round(source.width * height / max(source.height, 1) / pose.squash))
        image = source.resize((min(self.box-8, width), min(self.box-8, height)), Image.Resampling.NEAREST)
        if abs(pose.tilt) > .2:
            image = image.rotate(-pose.tilt, Image.Resampling.BICUBIC, expand=True)
        view = Image.new('RGBA', (self.box, self.box))
        view.alpha_composite(image, ((self.box-image.width)//2, (self.box-image.height)//2))
        if pose.impact:
            draw = ImageDraw.Draw(view)
            for i in range(8):
                angle = i * math.pi / 4
                cx = cy = self.box/2
                radius = self.args.actor_height*.55
                draw.line((cx+math.cos(angle)*(radius+4), cy+math.sin(angle)*(radius+4),
                           cx+math.cos(angle)*(radius+18),cy+math.sin(angle)*(radius+18)),
                          fill=(250,193,37,255),width=3)
        self.photo = ImageTk.PhotoImage(view)
        self.canvas.itemconfigure(self.item, image=self.photo)
        self.shape.apply(view)

    def tick(self):
        t = time.monotonic() - self.start
        if t >= scene_duration()+.2:
            self.close()
            return
        if time.monotonic()-self.last_discovery >= .65:
            self.last_discovery = time.monotonic()
            from windowrift.windows import list_windows
            known={w.wid:w for w in list_windows()}
            if self.browser.wid not in known or self.source.wid not in known:
                self.close()
                return
            self.browser,self.source=known[self.browser.wid],known[self.source.wid]
        if not self.args.doom_wad and t-self.last_sprite_sample >= .16:
            self.last_sprite_sample=t
            try:
                self.sample_source()
            except (SegmentationError, OSError, ValueError):
                pass
        bar = OmniboxCalibration().anchor(self.browser)
        pose = cinematic_pose(self.origin, bar, self.browser.bounds,
                              (self.box,self.box),t,impact_target=tuple(self.target))
        self.draw(t,pose)
        self.actor.geometry(f"+{pose.x}+{pose.y}")
        self.actor.lift()
        self.bridge.publish_actors([{'id':1,'x':pose.x,'y':pose.y,
                                     'width':self.box,'height':self.box}])
        capture = ImageGrab.grab(xdisplay=os.environ["DISPLAY"])
        self.recorder.add_frame(t, capture)
        if pose.impact and self.args.screenshot and not self.screenshot_saved:
            self.screenshot_saved = True
            self.args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            capture.save(self.args.screenshot)
            print(f'ACTUAL_X11_IMPACT_SCREENSHOT={self.args.screenshot}',flush=True)
        if pose.impact:
            print('NATIVE_ACTOR_IMPACT='+str(round(t,3)),flush=True)
        self.actor.after(33,self.tick)

    def close(self):
        if self.done:return
        self.done=True
        try:
            if self.recorder.frames:
                count=self.recorder.save(self.args.gif)
                print(f'ACTUAL_X11_GIF={self.args.gif};frames={count}',flush=True)
        finally:
            self.bridge.stop()
            self.shape.close()
            self.root.destroy()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-title',required=True)
    parser.add_argument('--browser-title',default='WindowRift Collision Lab')
    parser.add_argument('--target-file',type=Path,required=True)
    parser.add_argument('--gif',type=Path,required=True)
    parser.add_argument('--screenshot',type=Path)
    parser.add_argument('--token',required=True)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--doom-wad',type=Path)
    parser.add_argument('--actor-height',type=int,default=66)
    parser.add_argument('--crop',default='230,300,130,130')
    parser.add_argument('--mode',choices=('color-key','grabcut','ai','crop'),default='grabcut')
    args=parser.parse_args()
    if len(args.token)<16:
        parser.error('--token must be 16 characters or longer')
    args.crop=tuple(int(v) for v in args.crop.split(','))
    if len(args.crop)!=4 or min(args.crop[2:])<16:
        parser.error('--crop must be x,y,width,height')
    if not os.environ.get('DISPLAY'):
        parser.error('An actual X11 DISPLAY is required')
    root=tk.Tk()
    demo=None
    try:
        demo=NativeDemo(root,args)
        root.mainloop()
    finally:
        if demo is not None and not demo.done:
            demo.close()
        else:
            try:root.destroy()
            except tk.TclError:pass

if __name__=='__main__':
    main()
