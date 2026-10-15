"""Run a *live* X11 WindowRift actor over Chromium's actual address/search bar.

This is a reproducible integration harness for real X11/Chromium windows, not a
screenshot compositor and not a Chrome extension. The existing playable Rift
Arcade example is the default source. Any visible source window and flat-color
object crop can be selected with --source-title and --crop.

Run on Linux X11:
  python examples/rift_arcade.py
  chromium --new-window chrome://newtab
  python examples/chrome_omnibox_demo.py --screenshot /tmp/actual.png

The actor is drawn by a shaped *OS window* atop Chromium's own UI. It does not
become part of Chrome's omnibox or change the original game's internal state.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import time
from pathlib import Path
import tkinter as tk

from PIL import Image, ImageGrab, ImageTk

from windowrift.omnibox import OmniboxCalibration, looks_like_chrome, portal_position
from windowrift.demo_handoff import request_handoff
from windowrift.segmentation import SegmentationError, extract_object
from windowrift.windows import AppWindow, list_windows


def choose_windows(
    source_title: str,
    browser_title: str = "",
    browser_id: int | None = None,
) -> tuple[AppWindow, AppWindow]:
    windows = list_windows()
    source = next((w for w in windows if source_title.casefold() in w.title.casefold()), None)
    browsers = [w for w in windows if looks_like_chrome(w)
                and (source is None or w.wid != source.wid)
                and (browser_id is None or w.wid == browser_id)
                and (not browser_title or browser_title.casefold() in w.title.casefold())]
    if source is None or not browsers:
        titles = ", ".join(f"{w.wid:#x}: {w.title[:48]}" for w in windows)
        raise RuntimeError(
            f"Source or Chrome window not found. Visible: {titles}; "
            "start the game and a normal Chrome/Chromium window first."
        )
    if len(browsers) != 1:
        candidates = ", ".join(f"{w.wid:#x} {w.title}" for w in browsers)
        raise RuntimeError(f"Multiple browsers found: {candidates}; choose --browser-id 0x... ")
    return source, browsers[0]


class XShape:
    """Use the X Shape extension for real transparent *and input-free* sprites."""

    SHAPE_BOUNDING = 0
    SHAPE_INPUT = 2
    SHAPE_SET = 0

    def __init__(self, window: tk.Toplevel):
        self.window = window
        self.x11 = ctypes.CDLL("libX11.so.6")
        self.ext = ctypes.CDLL("libXext.so.6")
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.x11.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                       ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
        self.x11.XQueryTree.restype = ctypes.c_int
        self.x11.XCreateBitmapFromData.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                                   ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        self.x11.XCreateBitmapFromData.restype = ctypes.c_ulong
        self.x11.XFree.argtypes = [ctypes.c_void_p]
        self.x11.XFreePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.ext.XShapeCombineMask.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                              ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                              ctypes.c_ulong, ctypes.c_int]
        self.display = self.x11.XOpenDisplay(os.environ.get("DISPLAY", "").encode())
        if not self.display:
            raise RuntimeError("Cannot open the X11 display for shaped sprites")
        self.xid = self._outer_window(window.winfo_id())

    def _outer_window(self, xid: int) -> int:
        for _ in range(6):
            root, parent = ctypes.c_ulong(), ctypes.c_ulong()
            children, count = ctypes.c_void_p(), ctypes.c_uint()
            if not self.x11.XQueryTree(self.display, xid, ctypes.byref(root),
                                       ctypes.byref(parent), ctypes.byref(children), ctypes.byref(count)):
                break
            if children.value:
                self.x11.XFree(children)
            if not parent.value or parent.value == root.value:
                break
            xid = parent.value
        return xid

    def apply(self, image: Image.Image) -> None:
        width, height = image.size
        pitch = (width + 7) // 8
        bits = bytearray(pitch * height)
        alpha = image.getchannel("A")
        values = alpha.load()
        for y in range(height):
            for x in range(width):
                if values[x, y] >= 48:
                    bits[y * pitch + x // 8] |= 1 << (x % 8)
        bitmap = ctypes.create_string_buffer(bytes(bits))
        mask = self.x11.XCreateBitmapFromData(
            self.display, self.xid, bitmap, width, height
        )
        if not mask:
            raise RuntimeError("Failed to create an X11 shape mask")
        try:
            self.ext.XShapeCombineMask(self.display, self.xid,
                                       self.SHAPE_BOUNDING, 0, 0, mask, self.SHAPE_SET)
            # Empty input region: Chrome remains fully clickable/typable.
            self.ext.XShapeCombineMask(self.display, self.xid,
                                       self.SHAPE_INPUT, 0, 0, 0, self.SHAPE_SET)
            self.x11.XFlush(self.display)
        finally:
            self.x11.XFreePixmap(self.display, mask)

    def close(self) -> None:
        self.x11.XCloseDisplay(self.display)


class LiveOmniboxDemo:
    def __init__(self, root: tk.Tk, args: argparse.Namespace):
        self.root = root
        self.args = args
        self.source, self.browser = choose_windows(args.source_title, args.browser_title, args.browser_id)
        self.calibration = OmniboxCalibration(args.left, args.top, args.right, args.height)
        self.calibration.anchor(self.browser)
        self.original_start = None
        self.start = time.monotonic()
        self.last_frame = 0.0
        self.game_lifted = False
        self.last_handoff = 0.0
        self.last_windows = 0.0
        self.photo = None
        self.sprite_size = (args.actor_height, args.actor_height)
        self.root.withdraw()
        self.window = tk.Toplevel(root)
        self.window.title("WindowRift: chrome omnibox actor")
        self.window.overrideredirect(True)
        self.window.wm_attributes("-topmost", True)
        self.window.geometry(f'{args.actor_height}x{args.actor_height}+30+30')
        self.canvas = tk.Canvas(self.window, bg="#ffffff", width=args.actor_height,
                                height=args.actor_height, highlightthickness=0)
        self.canvas.pack()
        self.image_id = self.canvas.create_image(0, 0, anchor="nw")
        self.window.update()
        self.shape = XShape(self.window)
        self.refresh_frame(force=True)
        self.window.after(16, self.tick)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def refresh_frame(self, *, force=False) -> None:
        if self.game_lifted and not force:
            return  # The opted-in source game intentionally hides its sprite.
        if not force and time.monotonic() - self.last_frame < 0.13:
            return
        self.last_frame = time.monotonic()
        x, y, width, height = self.args.crop
        left = round(self.source.bounds.x) + x
        top = round(self.source.bounds.y) + y
        image = ImageGrab.grab(bbox=(left, top, left + width, top + height),
                              xdisplay=os.environ.get("DISPLAY"))
        try:
            sprite = extract_object(image, self.args.mode)
        except SegmentationError:
            return  # Source temporarily occluded or visually changed.
        if max(sprite.size) > 0:
            target_height = self.args.actor_height
            target_width = max(12, round(sprite.width * target_height / sprite.height))
            if target_width > 100:
                target_width = 100
            sprite = sprite.resize((target_width, target_height), Image.Resampling.NEAREST)
        self.sprite_size = sprite.size
        if self.canvas.winfo_width() != sprite.width or self.canvas.winfo_height() != sprite.height:
            self.canvas.config(width=sprite.width, height=sprite.height)
            self.window.geometry(f'{sprite.width}x{sprite.height}+{self.window.winfo_x()}+{self.window.winfo_y()}')
            self.window.update_idletasks()
        self.photo = ImageTk.PhotoImage(sprite)
        self.canvas.itemconfigure(self.image_id, image=self.photo)
        self.canvas.image = self.photo
        self.shape.apply(sprite)
        if self.original_start is None:
            self.original_start = (left + width / 2, top + height / 2)

    def tick(self) -> None:
        now = time.monotonic()
        elapsed = now - self.start
        if self.args.duration and elapsed > self.args.duration:
            self.close()
            return
        if self.args.handoff and not self.game_lifted and elapsed >= 0.65:
            self.game_lifted = request_handoff(
                "lift", self.args.handoff, port=self.args.handoff_port,
                timeout=0.06,
            )
            self.last_handoff = elapsed
            if self.game_lifted:
                print("SOURCE_GAME_HANDOFF=lifted", flush=True)
        if self.game_lifted and elapsed - self.last_handoff > 0.6:
            # A missed UDP reply is not proof that the game restored its actor.
            # The game has its own lease timeout if this harness is killed.
            request_handoff(
                "keepalive", self.args.handoff, port=self.args.handoff_port,
                timeout=0.12,
            )
            self.last_handoff = elapsed
        if now - self.last_windows > 0.7:
            self.last_windows = now
            known = {w.wid: w for w in list_windows()}
            if self.source.wid not in known or self.browser.wid not in known:
                self.close()
                return
            self.source, self.browser = known[self.source.wid], known[self.browser.wid]
        if self.original_start:
            try:
                target = self.calibration.anchor(self.browser)
                x, y = portal_position(self.original_start, target, self.sprite_size,
                                       elapsed, travel_seconds=self.args.travel)
                self.window.geometry(f'+{x}+{y}')
                self.window.lift()
            except ValueError:
                pass
        self.refresh_frame()
        if self.args.screenshot and elapsed >= self.args.screenshot_at and not self.args._saved:
            self.args._saved = True
            self.root.update_idletasks()
            self.root.after(75, self.save_screenshot)
        self.window.after(33, self.tick)

    def save_screenshot(self) -> None:
        image = ImageGrab.grab(xdisplay=os.environ.get("DISPLAY"))
        path = Path(self.args.screenshot)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        print(f"ACTUAL_DESKTOP_CAPTURE={path}", flush=True)

    def close(self) -> None:
        if self.game_lifted and self.args.handoff:
            if request_handoff("return", self.args.handoff,
                               port=self.args.handoff_port, timeout=0.4):
                print("SOURCE_GAME_HANDOFF=restored", flush=True)
        try:
            self.shape.close()
        finally:
            self.root.destroy()


def parse_crop(value: str) -> tuple[int, int, int, int]:
    try:
        pieces = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as e:
        raise argparse.ArgumentTypeError("Crop must be x,y,width,height") from e
    if len(pieces) != 4 or min(pieces[2:]) < 16 or min(pieces[:2]) < 0:
        raise argparse.ArgumentTypeError("Crop must be nonnegative x,y and width,height >= 16")
    return pieces


def cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-title", default="Rift Arcade", help="Visible running game window title substring")
    parser.add_argument("--browser-title", default="", help="Optional Chrome window title substring")
    parser.add_argument("--browser-id", type=lambda s: int(s, 0), default=None,
                        help="Specific Chrome window id (e.g. 0x140003) when several are open")
    parser.add_argument("--crop", type=parse_crop, default=parse_crop("238,310,130,121"),
                        help="Object crop relative to game window: x,y,width,height")
    parser.add_argument("--mode", choices=("color-key", "grabcut", "ai"), default="color-key")
    parser.add_argument("--actor-height", type=int, default=34)
    parser.add_argument("--left", type=int, default=122)
    parser.add_argument("--top", type=int, default=47)
    parser.add_argument("--right", type=int, default=87)
    parser.add_argument("--height", type=int, default=36)
    parser.add_argument("--travel", type=float, default=1.8)
    parser.add_argument("--handoff", default=os.environ.get("WINDOWRIFT_DEMO_TOKEN", ""),
                        help="Optional token for a first-party Rift Arcade visibility handoff")
    parser.add_argument("--handoff-port", type=int, default=8973)
    parser.add_argument("--duration", type=float, default=8.0,
                        help="0 runs until the window is closed")
    parser.add_argument("--screenshot", default=None)
    parser.add_argument("--screenshot-at", type=float, default=3.7)
    args = parser.parse_args()
    args._saved = False
    if not 20 <= args.actor_height <= 70 or args.travel <= 0:
        parser.error("actor-height must be 20–70 and travel must be positive")
    if args.handoff and len(args.handoff) < 12:
        parser.error("Demo handoff token must be at least 12 characters")
    return args


def main() -> None:
    if not os.environ.get("DISPLAY"):
        raise SystemExit("An X11 DISPLAY is required for the native Chrome omnibox demo")
    args = cli_args()
    root = tk.Tk()
    try:
        demo = LiveOmniboxDemo(root, args)
        root.mainloop()
    except Exception:
        root.destroy()
        raise


if __name__ == "__main__":
    main()
