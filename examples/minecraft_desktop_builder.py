"""Place blocks captured from *running Minecraft Classic* anywhere on X11.

Actual desktop mouse clicks, not a browser game or site extension.  Any web
site, Chrome toolbar, terminal or desktop background can appear underneath the
native overlay. Block placement stays at screen coordinates when a tab changes.

The public Minecraft Classic site is the game source, not modified by this
utility. No game assets are bundled or installed in this repository.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageGrab, ImageStat, ImageTk

from chrome_omnibox_demo import XShape
from windowrift.desktop_world import DesktopWorld, MATERIALS
from windowrift.proof_capture import ProofRecorder
from windowrift.segmentation import SegmentationError, extract_object
from windowrift.windows import list_windows
from windowrift.x11_pointer import BUTTON_PRESS, BUTTON_RELEASE, MOTION_NOTIFY, PointerGrab

# Each crop is relative to the real Minecraft Classic Chrome window at
# 760x680, 100% scale. Different DPI/browser toolbars need --crop-adjust.
HOTBAR_SAMPLES = {
    'stone': (195, 636, 36, 40),
    'dirt': (243, 636, 36, 40),
    'planks': (290, 636, 36, 40),
    'cobblestone': (338, 636, 36, 40),
    'sand': (386, 636, 36, 40),
    'gravel': (434, 636, 36, 40),
    'log': (482, 636, 36, 40),
    'leaves': (529, 636, 36, 40),
}


@dataclass
class ToolState:
    material: str = 'planks'
    builds: int = 0
    mines: int = 0
    drag: str | None = None
    last_position: tuple[int, int] | None = None


def hotbar_images(source, *, crop_adjust=(0,0)) -> dict[str, Image.Image]:
    """Read only pixels from an actual *visible* Minecraft Classic game window."""
    images = {}
    ax,ay = crop_adjust
    for name, (x,y,w,h) in HOTBAR_SAMPLES.items():
        left = round(source.bounds.x) + x + ax
        top = round(source.bounds.y) + y + ay
        crop = ImageGrab.grab(bbox=(left, top, left+w, top+h),
                              xdisplay=os.environ['DISPLAY'])
        # GrabCut can invent a foreground in a uniform blank screenshot.
        # Reject such crops rather than showing a black square as Minecraft.
        variability = ImageStat.Stat(crop.convert('RGB')).stddev
        if max(variability) < 9:
            continue
        try:
            rgba = extract_object(crop, 'grabcut')
        except SegmentationError:
            continue
        if rgba.getchannel('A').getbbox() is None:
            continue
        images[name] = rgba
    if 'planks' not in images:
        raise RuntimeError('Could not extract Minecraft hotbar. Keep its window visible at 100% scale.')
    return images


def material_image(source: Image.Image, size: int, *, opacity: float=1.0) -> Image.Image:
    """Preserve pixel-art aspect ratio; the icon itself comes from Minecraft."""
    art = source.convert('RGBA')
    pad = 2
    scale = min((size-2*pad)/max(1,art.width), (size-2*pad)/max(1,art.height))
    res = art.resize((max(1,round(art.width*scale)), max(1,round(art.height*scale))),
                     Image.Resampling.NEAREST)
    if opacity != 1.0:
        res.putalpha(res.getchannel('A').point(lambda a: int(a*opacity)))
    result = Image.new('RGBA',(size,size))
    result.alpha_composite(res, ((size-res.width)//2,(size-res.height)//2))
    return result


class DesktopBuilder:
    def __init__(self, root: tk.Tk, args: argparse.Namespace):
        self.root, self.args = root, args
        matches = [w for w in list_windows() if args.source_title.casefold() in w.title.casefold()]
        if len(matches) != 1:
            raise RuntimeError('Choose one visible running Minecraft Classic window; found '+str(len(matches)))
        self.source = matches[0]
        self.materials = hotbar_images(self.source, crop_adjust=args.crop_adjust)
        self.world = DesktopWorld.load(args.world_file, size=args.block_size)
        self.state = ToolState()
        self.closed = False
        self.pointer = PointerGrab()
        self.started = time.monotonic()
        self.last_record = 0.0
        self.recorder = ProofRecorder(interval=0.22, max_frames=120, max_width=1280) if args.gif else None
        self.icons = {name:material_image(image,self.world.size) for name,image in self.materials.items()}
        self.photo = None
        self.preview_photo = None
        self.rift_region = None
        self.shaped = None
        self.make_controller()
        self.make_block_overlay()
        self.make_cursor_preview()
        self.render_blocks()
        self.set_material('planks')
        root.bind_all('<KeyPress>', self.on_key)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(120, self.activate)
        self.root.after(20,self.tick)
        print('ACTUAL_GAME_SOURCE='+self.source.title,flush=True)
        print('MINECRAFT_HOTBAR_MATERIALS='+','.join(self.materials),flush=True)
        print('DESKTOP_WORLD_FILE='+str(self.args.world_file),flush=True)

    def make_controller(self):
        root = self.root
        root.title('WindowRift | Desktop Builder')
        root.overrideredirect(True)
        root.geometry('632x154+938+716')
        root.configure(bg='#172025')
        root.attributes('-topmost',True)
        title = tk.Label(root,text='WINDOWRIFT   /   MINECRAFT BEYOND THE WINDOW',
                         font=('DejaVu Sans Mono',12,'bold'),fg='#d4e4d1',bg='#172025')
        title.pack(anchor='w',padx=16,pady=(11,7))
        self.state_label = tk.Label(root,text='Starting...',font=('DejaVu Sans Mono',10,'bold'),
                                    fg='#c7e3ad',bg='#172025')
        self.state_label.pack(anchor='w',padx=16)
        self.instructions = tk.Label(root,
            text='LEFT  place / paint    RIGHT  mine    1-8  material    Z undo    Y redo',
            font=('DejaVu Sans Mono',9),fg='#b9c5c4',bg='#172025')
        self.instructions.pack(anchor='w',padx=16,pady=(6,0))
        self.toggle_label = tk.Label(root,
            text='ESC = browse normally     B = build again     blocks stay above every app',
            font=('DejaVu Sans Mono',9),fg='#7fa7a3',bg='#172025')
        self.toggle_label.pack(anchor='w',padx=16,pady=(5,0))
        control = tk.Frame(root,bg='#172025')
        control.pack(fill='x',padx=12,pady=(6,0))
        tk.Button(control,text='BUILD / PAUSE',command=self.toggle,relief='flat',
                  bg='#9ed181',fg='#101a15',font=('DejaVu Sans Mono',9,'bold')).pack(side='left',padx=2)
        tk.Button(control,text='UNDO',command=self.undo,bg='#2e4240',fg='#fff',relief='flat').pack(side='left',padx=3)
        tk.Button(control,text='SAVE',command=self.save,bg='#2e4240',fg='#fff',relief='flat').pack(side='left',padx=3)
        tk.Button(control,text='CLOSE',command=self.close,bg='#2e4240',fg='#fff',relief='flat').pack(side='left',padx=3)
        self.status = tk.Label(control,text='',bg='#172025',fg='#d4e4d1',font=('DejaVu Sans Mono',9))
        self.status.pack(side='right',padx=6)

    def make_block_overlay(self):
        self.stage = tk.Toplevel(self.root)
        self.stage.title('WindowRift native desktop blocks')
        self.stage.overrideredirect(True)
        self.stage.wm_attributes('-topmost', True)
        self.stage.geometry('2x2+0+0')
        self.stage_canvas=tk.Canvas(self.stage,bg='white',width=2,height=2,highlightthickness=0)
        self.stage_canvas.pack()
        self.stage_image=self.stage_canvas.create_image(0,0,anchor='nw')
        self.stage.update()
        self.shaped=XShape(self.stage)

    def make_cursor_preview(self):
        self.cursor_window=tk.Toplevel(self.root)
        self.cursor_window.title('WindowRift block preview')
        self.cursor_window.overrideredirect(True)
        self.cursor_window.wm_attributes('-topmost',True)
        self.cursor_window.geometry(f'{self.world.size}x{self.world.size}+0+0')
        self.cursor_canvas=tk.Canvas(self.cursor_window,bg='white',width=self.world.size,
                                     height=self.world.size,highlightthickness=0)
        self.cursor_canvas.pack()
        self.cursor_item=self.cursor_canvas.create_image(0,0,anchor='nw')
        self.cursor_window.update()
        self.cursor_shape=XShape(self.cursor_window)
        self.cursor_window.withdraw()

    def render_blocks(self):
        blocks=self.world.blocks
        if not blocks:
            self.stage.withdraw()
            return
        s=self.world.size
        left=min(b.x for b in blocks); top=min(b.y for b in blocks)
        right=max(b.x for b in blocks)+s; bottom=max(b.y for b in blocks)+s
        view=Image.new('RGBA',(right-left,bottom-top))
        for block in blocks:
            icon=self.icons.get(block.material) or self.icons['planks']
            view.alpha_composite(icon,(block.x-left,block.y-top))
        self.stage_canvas.config(width=view.width,height=view.height)
        self.stage.geometry(f'{view.width}x{view.height}{left:+d}{top:+d}')
        self.photo=ImageTk.PhotoImage(view)
        self.stage_canvas.itemconfigure(self.stage_image,image=self.photo)
        self.stage_canvas.image=self.photo
        self.stage.deiconify()
        self.stage.update_idletasks()
        self.shaped.apply(view)
        self.stage.lift()
        self.root.lift()
        print(f'DESKTOP_BLOCKS_RENDERED={len(blocks)};bounds={left},{top},{right},{bottom}',flush=True)

    def set_material(self,name):
        if name not in self.icons:
            return
        self.state.material=name
        s=self.world.size
        icon=self.icons[name]
        dim=Image.new('RGBA',(s,s))
        dim.alpha_composite(icon)
        alpha=dim.getchannel('A')
        dim.putalpha(alpha.point(lambda x:round(x*0.65)))
        outline=ImageDraw.Draw(dim)
        outline.rectangle((0,0,s-1,s-1),outline=(179,236,163,200),width=2)
        self.preview_photo=ImageTk.PhotoImage(dim)
        self.cursor_canvas.itemconfigure(self.cursor_item,image=self.preview_photo)
        self.cursor_shape.apply(dim)
        self.status.config(text=name.upper())
        self.update_state()
        print('MATERIAL_SELECTED='+name,flush=True)

    def update_state(self):
        state='BUILD MODE · CLICK ANYWHERE' if self.pointer.active else 'BROWSE MODE · BLOCKS REMAIN'
        self.state_label.config(text=state)
        self.status.config(text=f'{self.state.material.upper()}  |  {len(self.world.blocks)} blocks')

    def activate(self):
        if self.pointer.active or self.closed:
            return
        self.root.lift()
        self.root.focus_force()
        self.pointer.start()
        self.cursor_window.deiconify()
        self.cursor_window.lift()
        self.root.lift()
        self.update_state()
        print('DESKTOP_BUILD_MODE=active',flush=True)

    def deactivate(self):
        self.pointer.stop()
        self.cursor_window.withdraw()
        if self.state.drag:
            self.finish_stroke()
        self.update_state()
        print('DESKTOP_BUILD_MODE=pass-through',flush=True)

    def toggle(self):
        if self.pointer.active:self.deactivate()
        else:self.activate()

    def finish_stroke(self):
        self.world.commit()
        self.state.drag=None
        self.state.last_position=None
        self.save()

    def on_event(self,etype,x,y,button):
        if self.closed:
            return
        cell=self.world.cell(x,y)
        if etype==MOTION_NOTIFY:
            self.cursor_window.geometry(f'+{cell[0]}+{cell[1]}')
            if self.state.drag is not None and self.state.last_position is not None:
                n=self.world.stroke_to(self.state.last_position,(x,y),tool=self.state.drag,
                                         material=self.state.material)
                self.state.last_position=(x,y)
                if n:
                    if self.state.drag=='place':self.state.builds+=n
                    else:self.state.mines+=n
                    self.render_blocks()
                    self.update_state()
        elif etype==BUTTON_PRESS:
            if button in (4,5):
                options=[s for s in MATERIALS if s in self.icons]
                index=options.index(self.state.material)
                self.set_material(options[(index+(1 if button==5 else -1))%len(options)])
            elif button in (1,3) and self.state.drag is None:
                self.world.begin()
                self.state.drag='place' if button==1 else 'mine'
                self.state.last_position=(x,y)
                try:
                    modified=self.world.place(x,y,self.state.material) if button==1 else self.world.mine(x,y)
                except ValueError as exc:
                    print('BLOCK_LIMIT='+str(exc),flush=True)
                    self.finish_stroke()
                    return
                if modified:
                    if button==1:self.state.builds+=1
                    else:self.state.mines+=1
                    self.render_blocks()
                    self.update_state()
                    print(f'DESKTOP_BLOCK_{"PLACED" if button==1 else "MINED"}={cell[0]},{cell[1]}',flush=True)
        elif etype==BUTTON_RELEASE and button in (1,3):
            if self.state.drag is not None:
                self.finish_stroke()

    def on_key(self,event):
        key=event.keysym.lower()
        if key=='escape':
            self.deactivate()
        elif key=='b':
            self.toggle()
        elif key=='z':
            self.undo()
        elif key=='y':
            self.redo()
        elif key=='q':
            self.close()
        elif key.isdigit() and 1<=int(key)<=8:
            name=MATERIALS[int(key)-1]
            self.set_material(name)
        elif key=='p':
            self.save()

    def undo(self):
        if self.world.undo():
            self.render_blocks();self.save();self.update_state()

    def redo(self):
        if self.world.redo():
            self.render_blocks();self.save();self.update_state()

    def save(self):
        self.world.save(self.args.world_file)
        print(f'DESKTOP_WORLD_SAVED={len(self.world.blocks)}',flush=True)

    def tick(self):
        if self.closed:return
        for event in self.pointer.poll():
            try:self.on_event(*event)
            except Exception as exc:
                print('POINTER_EVENT_ERROR='+repr(exc),flush=True)
                self.deactivate()
                raise
        now=time.monotonic()
        if self.args.duration and now-self.started>=self.args.duration:
            self.close();return
        if self.recorder and now-self.last_record>.24:
            self.last_record=now
            self.recorder.add_frame(now-self.started,
                                    ImageGrab.grab(xdisplay=os.environ['DISPLAY']))
        self.root.after(18,self.tick)

    def close(self):
        if self.closed:return
        self.closed=True
        self.pointer.stop()
        if self.state.drag:self.finish_stroke()
        self.save()
        try:
            if self.recorder and self.recorder.frames:
                n=self.recorder.save(self.args.gif)
                print(f'ACTUAL_DESKTOP_BUILD_GIF={self.args.gif};frames={n}',flush=True)
            print(f'BUILD_SESSION_RESULT=placed:{self.state.builds};mined:{self.state.mines};blocks:{len(self.world.blocks)}',flush=True)
        finally:
            self.shaped.close();self.cursor_shape.close();self.pointer.close()
            self.root.destroy()


def parse_crop_adjust(value:str)->tuple[int,int]:
    try:
        x,y=(int(v.strip()) for v in value.split(','))
        return x,y
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('Crop adjustment is dx,dy') from exc


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-title',default='Minecraft Classic',help='Running, visible game window title')
    parser.add_argument('--crop-adjust',type=parse_crop_adjust,default=(0,0),
                        help='Pixel offset for Minecraft hotbar icons at nonstandard scaling')
    parser.add_argument('--block-size',type=int,default=48)
    parser.add_argument('--world-file',type=Path,
                        default=Path.home()/'.local/share/windowrift/desktop-world.json')
    parser.add_argument('--gif',type=Path,help='Record actual desktop video frames as a GIF')
    parser.add_argument('--duration',type=float,default=0,help='Seconds to run (0 runs until quit)')
    args=parser.parse_args()
    if not os.environ.get('DISPLAY'):
        parser.error('Linux X11 required for native desktop pointer grab')
    root=tk.Tk()
    instance=None
    try:
        instance=DesktopBuilder(root,args)
        root.mainloop()
    finally:
        if instance and not instance.closed:
            instance.close()
        else:
            try:root.destroy()
            except tk.TclError:pass


if __name__=='__main__':main()
