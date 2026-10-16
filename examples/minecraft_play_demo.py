"""Play a real Minecraft Classic window's captured block across the desktop.

This X11 proof uses the official running browser game as its visible source and
an independent shaped OS window as the controllable actor. Key presses control
physics. E removes real DOM elements and F adds them to an explicitly connected
local browser arena. It does not modify the Minecraft game's internal world.
"""
from __future__ import annotations

import argparse
import base64
from io import BytesIO
import os
from pathlib import Path
import time
import tkinter as tk
from PIL import Image, ImageGrab, ImageTk

from chrome_omnibox_demo import XShape, choose_windows
from windowrift.bridge import BrowserBridge
from windowrift.controller import KeyLatch, Player, step
from windowrift.geometry import Rect
from windowrift.proof_capture import ProofRecorder
from windowrift.segmentation import SegmentationError, extract_object
from windowrift.windows import list_windows


def sprite_png(image: Image.Image) -> str:
    """Transmit only the explicitly cropped sprite, not a whole screen image."""
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    if buffer.tell() > 45000:
        raise ValueError("Selected source sprite is too large for browser transfer")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def parse_crop(value: str) -> tuple[int, int, int, int]:
    parts = tuple(int(v.strip()) for v in value.split(','))
    if len(parts) != 4 or min(parts[:2]) < 0 or min(parts[2:]) < 16:
        raise argparse.ArgumentTypeError("Crop must be x,y,width,height with positive dimensions")
    return parts


class MinecraftPlay:
    def __init__(self, root: tk.Tk, args: argparse.Namespace) -> None:
        self.root, self.args = root, args
        self.source, self.browser = choose_windows(args.source_title, args.browser_title)
        self.keys = KeyLatch()
        self.pressed_actions: set[str] = set()
        self.pending: list[str] = []
        self.events = 0
        self.last = time.monotonic()
        self.started = self.last
        self.last_sample = 0.0
        self.last_publish = 0.0
        self.last_texture_sent = 0.0
        self.last_record = 0.0
        self.last_lookup = 0.0
        self.finished = False
        self.inside_browser = False
        self.recorder = ProofRecorder(interval=0.17, max_frames=90, max_width=1280)

        x, y, w, h = args.crop
        origin = (round(self.source.bounds.x) + x, round(self.source.bounds.y) + y)
        image = ImageGrab.grab(bbox=(*origin, origin[0] + w, origin[1] + h),
                               xdisplay=os.environ["DISPLAY"])
        picture = extract_object(image, args.mode)
        scaled_width = max(22, round(picture.width * args.actor_height / picture.height))
        self.picture = picture.resize((scaled_width, args.actor_height), Image.Resampling.NEAREST)
        self.desktop_size = (root.winfo_screenwidth(), root.winfo_screenheight())
        self.texture = sprite_png(self.picture)
        self.photo: ImageTk.PhotoImage | None = None
        self.size = (self.picture.width, self.picture.height)
        self.player = Player(
            x=round(self.source.bounds.right - 108),
            y=round(self.source.bounds.bottom - 175),
            width=float(self.size[0]), height=float(self.size[1]),
        )

        self.bridge = BrowserBridge(token=args.token)
        self.bridge.start()
        if self.bridge.error:
            raise RuntimeError(f"Local browser bridge failed: {self.bridge.error}")
        print("BROWSER_BRIDGE_READY=127.0.0.1", flush=True)
        print("ACTUAL_MINECRAFT_SOURCE=" + self.source.title, flush=True)

        self.actor = tk.Toplevel(root)
        self.actor.title("WindowRift Minecraft playable actor")
        self.actor.overrideredirect(True)
        self.actor.wm_attributes("-topmost", True)
        self.actor.geometry(f"{self.size[0]}x{self.size[1]}+{int(self.player.x)}+{int(self.player.y)}")
        self.canvas = tk.Canvas(self.actor, width=self.size[0], height=self.size[1],
                                bg="#FFFFFF", highlightthickness=0)
        self.canvas.pack()
        self.sprite_id = self.canvas.create_image(0, 0, anchor="nw")
        self.photo = ImageTk.PhotoImage(self.picture)
        self.canvas.itemconfigure(self.sprite_id, image=self.photo)
        self.actor.update()
        self.shape = XShape(self.actor)
        self.shape.apply(self.picture)

        root.title("WindowRift Play Controller")
        root.geometry("540x156+540+14")
        root.configure(bg="#1b2626")
        root.attributes("-topmost", True)
        title = tk.Label(root, text="MINECRAFT  /  CROSS-WINDOW PLAY", font=("DejaVu Sans Mono", 14, "bold"),
                         fg="#d9e3c5", bg="#1b2626")
        title.pack(anchor="w", padx=15, pady=(12, 6))
        hints = tk.Label(root, text="A / D move     SPACE jump     SHIFT sprint     E mine     F place     ESC quit",
                         font=("DejaVu Sans Mono", 9), fg="#d6d7be", bg="#1b2626")
        hints.pack(anchor="w", padx=16)
        self.status = tk.Label(root, text="Walk the Minecraft block into Chrome. Mine or build actual HTML.",
                               font=("DejaVu Sans Mono", 9), fg="#a8cbb4", bg="#1b2626")
        self.status.pack(anchor="w", padx=16, pady=9)
        token_label = tk.Label(root, text="Browser session token: " + args.token,
                               font=("DejaVu Sans Mono", 8), fg="#c4bda4", bg="#1b2626")
        token_label.pack(anchor="w", padx=16)

        root.bind_all("<KeyPress>", self.key_press)
        root.bind_all("<KeyRelease>", self.key_release)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(90, lambda: (root.lift(), root.focus_force()))
        root.after(18, self.tick)

    def key_press(self, event) -> None:
        key = event.keysym.lower()
        if key == "escape":
            self.close()
            return
        if key in ("e", "f"):
            if key not in self.pressed_actions:
                self.pressed_actions.add(key)
                self.pending.append("mine" if key == "e" else "place")
                self.status.config(text="E: mining an HTML block" if key == "e"
                                   else "F: building an HTML block")
                print("PLAYER_ACTION=" + ("mine" if key == "e" else "place"), flush=True)
        else:
            self.keys.press(key)

    def key_release(self, event) -> None:
        key = event.keysym.lower()
        if key in self.pressed_actions:
            self.pressed_actions.remove(key)
        self.keys.release(key)

    def tick(self) -> None:
        if self.finished:
            return
        now = time.monotonic()
        elapsed = now - self.started
        if self.args.duration and elapsed >= self.args.duration:
            self.close()
            return
        dt = max(0.0, min(.045, now - self.last))
        self.last = now
        if now - self.last_lookup > .75:
            self.last_lookup = now
            known = {w.wid: w for w in list_windows()}
            if self.source.wid not in known or self.browser.wid not in known:
                print("PLAY_STOPPED=source_or_browser_closed", flush=True)
                self.close()
                return
            self.source, self.browser = known[self.source.wid], known[self.browser.wid]
        size = self.desktop_size
        screen = Rect(0, 0, float(size[0]), min(float(size[1]), self.browser.bounds.bottom - 30))
        self.player = step(self.player, self.keys.snapshot(), dt, screen, [])
        self.actor.geometry(f"+{round(self.player.x)}+{round(self.player.y)}")
        self.actor.lift()
        entered = self.player.center[0] >= self.browser.bounds.x
        if entered != self.inside_browser:
            self.inside_browser = entered
            print("ACTOR_IN_BROWSER=" + str(entered).lower(), flush=True)
        if now - self.last_publish >= .045:
            self.last_publish = now
            payload = {"id": 1, "x": round(self.player.x), "y": round(self.player.y),
                       "width": self.size[0], "height": self.size[1]}
            if self.pending:
                payload["action"] = self.pending.pop(0)
                self.events += 1
                payload["event_id"] = self.events
            if now - self.last_texture_sent > 1.4 or "action" in payload:
                payload["texture"] = self.texture
                self.last_texture_sent = now
            self.bridge.publish_actors([payload])
        if now - self.last_record >= .19:
            self.last_record = now
            if self.args.gif:
                frame = ImageGrab.grab(xdisplay=os.environ["DISPLAY"])
                self.recorder.add_frame(elapsed, frame)
        self.root.after(25, self.tick)

    def close(self) -> None:
        if self.finished:
            return
        self.finished = True
        try:
            if self.args.gif and self.recorder.frames:
                n = self.recorder.save(self.args.gif)
                print(f"REAL_KEYBOARD_PLAY_GIF={self.args.gif};frames={n}", flush=True)
        finally:
            self.bridge.stop()
            self.shape.close()
            self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-title", default="Minecraft Classic")
    parser.add_argument("--browser-title", default="WindowRift Block Arena")
    parser.add_argument("--crop", type=parse_crop, default=(290, 636, 36, 40))
    parser.add_argument("--mode", choices=("grabcut", "color-key", "ai", "crop"), default="grabcut")
    parser.add_argument("--actor-height", type=int, default=62)
    parser.add_argument("--token", required=True)
    parser.add_argument("--gif", type=Path)
    parser.add_argument("--duration", type=float, default=0,
                        help="End after N seconds, or 0 to play until Esc")
    args = parser.parse_args()
    if len(args.token) < 16 or not 25 <= args.actor_height <= 120:
        parser.error("Use a 16+ character session token and actor height 25..120")
    if not os.environ.get("DISPLAY"):
        parser.error("This native live-window proof requires Linux X11")
    root = tk.Tk()
    instance = None
    try:
        instance = MinecraftPlay(root, args)
        root.mainloop()
    finally:
        if instance is not None and not instance.finished:
            instance.close()
        else:
            try:
                root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    main()
