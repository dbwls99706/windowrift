"""Rift Arcade: a small, real, playable Tk game for WindowRift demos.

Controls: left/right to move, space/up to jump, R to reset.  Collect the
floating crystals.  The green Riftling is an ordinary sprite inside a real
separate operating-system window, not a screenshot mock-up.
"""

from __future__ import annotations

import math
import sys
import argparse
import os

from windowrift.demo_handoff import DemoHandoffServer
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk

WIDTH, HEIGHT = 760, 600
BG = "#17243b"
G = 1060


def main() -> None:
    parser = argparse.ArgumentParser(description="Small playable game for WindowRift demonstrations")
    parser.add_argument("--demo-handoff", action="store_true",
                        help="Allow a local opt-in WindowRift demo to hide/restore the actor")
    parser.add_argument("--handoff-port", type=int, default=8973)
    args = parser.parse_args()
    secret = os.environ.get("WINDOWRIFT_DEMO_TOKEN", "")
    handoff = None
    if args.demo_handoff:
        if len(secret) < 12:
            parser.error("Set WINDOWRIFT_DEMO_TOKEN (12+ characters) in both demo processes")
        handoff = DemoHandoffServer(secret, args.handoff_port)
        print(f"DEMO_HANDOFF_PORT={handoff.port}", flush=True)
    root = tk.Tk()
    root.title("Rift Arcade - A WindowRift Playable Demo")
    root.geometry(f"{WIDTH}x{HEIGHT}+65+110")
    root.configure(bg=BG)
    root.resizable(False, False)
    canvas = tk.Canvas(root, width=WIDTH, height=HEIGHT, bg=BG, highlightthickness=0)
    canvas.pack()

    canvas.create_rectangle(0, 0, WIDTH, 76, fill="#10192d", outline="")
    canvas.create_text(36, 26, anchor="w", fill="#b8fcec", text="RIFT ARCADE", font=("DejaVu Sans", 22, "bold"))
    canvas.create_text(38, 57, anchor="w", fill="#94a9c5", text="SIGNAL RUNNER  /  LIVE WINDOW SOURCE", font=("DejaVu Sans", 10))
    canvas.create_text(715, 28, anchor="e", fill="#87e9fa", text="LEVEL  01", font=("DejaVu Sans", 11, "bold"))

    for i in range(29):
        x = (i * 121 + 43) % WIDTH
        y = 91 + ((i * 53) % 258)
        canvas.create_oval(x, y, x + 2 + i % 3, y + 2 + i % 3, fill="#3b5773", outline="")
    # Solid-colored capture zone makes the extracted sprite outline auditable.
    canvas.create_rectangle(147, 141, 568, 433, fill="#19293e", outline="#354d66", width=2)
    canvas.create_text(168, 166, anchor="w", fill="#7e99b7", text="PIXEL ACTOR / PICK ME", font=("DejaVu Sans", 9))
    canvas.create_rectangle(147, 432, 568, 438, fill="#51d5cf", outline="")
    canvas.create_rectangle(0, 495, WIDTH, HEIGHT, fill="#0e1728", outline="")
    canvas.create_rectangle(0, 488, WIDTH, 499, fill="#79c7e6", outline="")
    canvas.create_text(40, 538, anchor="w", fill="#e1eefb", text="ARROW KEYS     MOVE", font=("DejaVu Sans", 11, "bold"))
    canvas.create_text(40, 565, anchor="w", fill="#9db4c7", text="SPACE    JUMP       •       R    RESET", font=("DejaVu Sans", 10))
    canvas.create_text(730, 548, anchor="e", fill="#89e9db", text="Try pulling the Riftling out of this window!", font=("DejaVu Sans", 10))
    canvas.create_text(630, 387, fill="#9db7d1", text="REAL GAME", font=("DejaVu Sans", 10, "bold"))
    canvas.create_text(630, 407, fill="#6e8caa", text="Not a video", font=("DejaVu Sans", 9))
    gem_xs = [220, 400, 500]
    gems = []
    for idx, x in enumerate(gem_xs):
        y = 229 + (idx % 2) * 38
        gems.append(canvas.create_polygon(x, y-15, x+12, y, x, y+15, x-12, y, fill="#b7f2fd", outline="#4dd9ee", width=2))

    path = Path(__file__).parent / "assets" / "riftling.png"
    image = Image.open(path).convert("RGBA").resize((120, 120), Image.Resampling.NEAREST)
    character = ImageTk.PhotoImage(image)
    actor = canvas.create_image(302, 335, image=character)
    canvas._character_image = character
    score = canvas.create_text(714, 58, anchor="e", fill="#f8ce79", text="CRYSTALS 0 / 3", font=("DejaVu Sans", 10, "bold"))

    state = {"x": 302.0, "y": 335.0, "vy": 0.0, "keys": set(), "time": 0.0,
             "points": 0, "remaining": list(zip(gem_xs, gems))}

    def key_down(event):
        key = event.keysym.lower()
        state["keys"].add(key)
        if key == 'r':
            state["x"] = 302.0; state["y"] = 335.0; state["vy"] = 0.0
            for _, g in state["remaining"]: canvas.delete(g)
            state["remaining"] = []
            for idx, x in enumerate(gem_xs):
                y = 229 + (idx % 2) * 38
                gem = canvas.create_polygon(x, y-15, x+12, y, x, y+15, x-12, y,
                                            fill="#b7f2fd", outline="#4dd9ee", width=2)
                state["remaining"].append((x, gem))
            state["points"] = 0
            canvas.itemconfigure(score, text="CRYSTALS 0 / 3")
        if key in ('space', 'up') and state["y"] >= 366:
            state["vy"] = -410.0

    def key_up(event):
        state["keys"].discard(event.keysym.lower())

    root.bind('<KeyPress>', key_down)
    root.bind('<KeyRelease>', key_up)
    root.focus_force()

    def tick():
        dt = 1 / 30
        state["time"] += dt
        controls = state["keys"]
        state["x"] = max(215, min(500, state["x"] + (('right' in controls) - ('left' in controls)) * 140 * dt))
        state["vy"] += G * dt
        state["y"] = min(367, state["y"] + state["vy"] * dt)
        if state["y"] >= 367: state["vy"] = 0
        bob = round(3 * math.sin(state["time"] * 5))
        canvas.coords(actor, round(state["x"]), round(state["y"]) + bob)
        if handoff is not None:
            handoff.poll()
            canvas.itemconfigure(actor, state="hidden" if handoff.state.lifted else "normal")
        for x, gem in list(state["remaining"]):
            if abs(x - state["x"]) < 31 and abs(236 - state["y"]) < 49:
                canvas.delete(gem)
                state["remaining"].remove((x, gem))
                state["points"] += 1
                canvas.itemconfigure(score, text=f'CRYSTALS {state["points"]} / 3')
        root.after(33, tick)

    tick()
    if handoff is not None:
        root.protocol("WM_DELETE_WINDOW", lambda: (handoff.close(), root.destroy()))
    root.mainloop()


if __name__ == '__main__':
    main()
