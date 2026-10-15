"""Optional X11 desktop screenshot harness for the Rift Arcade example.

Run Rift Arcade first in a visible X11 session. This harness grabs actual
pixels from the game and extracts the foreground via WindowRift's GrabCut
implementation, then renders the extracted image in a shaped Tk window.
The production app remains PySide6; this script is a small, dependency-light
visual integration proof, not a test of the production Qt control panel.

No image compositing is done to the saved desktop screenshot.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tkinter as tk

from PIL import ImageGrab, ImageTk

from windowrift.bridge import BrowserBridge
from windowrift.segmentation import extract_object
from windowrift.windows import list_windows


def shape_window(window: tk.Toplevel, image) -> bool:
    """Shape an X11 window to the sprite's visible pixels via the X Shape extension."""
    try:
        x11 = ctypes.CDLL('libX11.so.6')
        ext = ctypes.CDLL('libXext.so.6')
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XCreateBitmapFromData.restype = ctypes.c_ulong
        x11.XCreateBitmapFromData.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        ext.XShapeCombineMask.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong, ctypes.c_int]
        x11.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        display = x11.XOpenDisplay(os.environ.get('DISPLAY','').encode())
        if not display:
            return False
        width, height = image.size
        alpha = image.getchannel('A')
        pitch = (width + 7) // 8
        data = bytearray(pitch * height)
        pixels = alpha.load()
        for y in range(height):
            for x in range(width):
                if pixels[x,y] >= 32:
                    data[y*pitch + x//8] |= 1 << (x%8)
        bitmap = ctypes.create_string_buffer(bytes(data))
        x11.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                   ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                                   ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
        x11.XQueryTree.restype = ctypes.c_int
        x11.XFree.argtypes = [ctypes.c_void_p]
        outer = window.winfo_id()
        for _ in range(4):
            root = ctypes.c_ulong()
            parent = ctypes.c_ulong()
            children = ctypes.c_void_p()
            count = ctypes.c_uint()
            if not x11.XQueryTree(display, outer, ctypes.byref(root), ctypes.byref(parent),
                                   ctypes.byref(children), ctypes.byref(count)):
                break
            if children.value: x11.XFree(children)
            if not parent.value or parent.value == root.value:
                break
            outer = parent.value
        pixmap = x11.XCreateBitmapFromData(display, outer, bitmap, width, height)
        ext.XShapeCombineMask(display, outer, 0, 0, 0, pixmap, 0)
        x11.XFreePixmap(display, pixmap)
        x11.XFlush(display)
        x11.XCloseDisplay(display)
        return True
    except (OSError, ValueError, AttributeError):
        return False


def main():
    candidates = [w for w in list_windows() if w.title.startswith('Rift Arcade')]
    if not candidates:
        raise SystemExit('Run `python examples/rift_arcade.py` first in X11.')
    source = candidates[0]
    screenshot = ImageGrab.grab(xdisplay=os.environ.get('DISPLAY'))
    x = round(source.bounds.x) + 238
    y = round(source.bounds.y) + 310
    roi = screenshot.crop((x, y, x + 130, y + 121))
    extracted = extract_object(roi, 'color-key')
    scaled = extracted.resize((172, 190), resample=0)

    root = tk.Tk()
    root.withdraw()
    actor = tk.Toplevel(root)
    actor.overrideredirect(True)
    actor.wm_attributes('-topmost', True)
    actor.geometry(f'{scaled.width}x{scaled.height}+900+472')
    canvas = tk.Canvas(actor, width=scaled.width, height=scaled.height, bg='#142239', highlightthickness=0)
    canvas.pack()
    pix = ImageTk.PhotoImage(scaled)
    canvas.create_image(0, 0, image=pix, anchor='nw')
    canvas.image = pix
    actor.update()
    mask_ok = shape_window(actor, scaled)
    print('X11_SHAPED_WINDOW:', mask_ok, flush=True)

    bridge = BrowserBridge()
    bridge.start()
    token_path = Path('/tmp/windowrift_demo_session')
    token_path.write_text(bridge.token, encoding='utf-8')
    token_path.chmod(0o600)
    print('TOKEN_FILE:', token_path, ' BRIDGE_ERROR:', bridge.error, flush=True)

    def publish():
        bridge.publish_actors([{'id': 1, 'x': actor.winfo_x(), 'y': actor.winfo_y(),
                                'width': scaled.width, 'height': scaled.height}])
        root.after(100, publish)

    def cleanup():
        bridge.stop()
        token_path.unlink(missing_ok=True)
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', cleanup)
    root.after(100, publish)
    root.mainloop()


if __name__ == '__main__':
    main()
