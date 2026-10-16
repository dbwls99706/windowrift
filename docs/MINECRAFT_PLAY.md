# Minecraft Classic: playable cross-window experiment

![Actual keyboard-driven Minecraft Classic to Chrome DOM interactions](media/minecraft-keyboard-play.gif)


This experiment uses the **official Minecraft Classic website running in a
real Chrome/Chromium window** and a separately hosted HTML playground in a
second browser window. WindowRift selects a block from Minecraft's visible
hotbar; the block is a separate input-transparent OS sprite under human
keyboard control. It does **not** remove a block from Minecraft's world or
modify the game's private state.

Unlike the older auto-jump demo, this example does not follow a scripted
animation path. A/D or the arrow keys move the block; Space jumps; Shift runs;
E mines the nearest reachable HTML block; F places a new DOM block bearing
the captured Minecraft image. The new page is opt-in, local and visibly
changes its real DOM nodes, including persisted block state after reload.

## Live play on Linux X11

Open two Chrome windows (not browser tabs inside the same window). Put the
official <https://classic.minecraft.net/> in one and serve the included
playground with `python -m http.server 8811 --bind 127.0.0.1 --directory examples`.
Open <http://127.0.0.1:8811/minecraft-rift.html> in the second window.

Install the application with `pip install -e .`; also install `python3-tk`,
`wmctrl` and `x11-utils` as needed. Run:

```bash
python examples/minecraft_play_demo.py --token your-local-session-token-at-least-16-characters
```

Copy the same session token into the playground's **CONNECT** control. Keep
the WindowRift Play Controller focused while moving the character with
A/D, Space, Shift, E and F. Escape closes the controller. No global keyboard
hook or write access to a target game is used. The program only captures the
user-selected visible crop and forwards it to the explicitly connected local
page. Chrome's native toolbar is not modified.

The default `--crop 290,636,36,40` is calibrated for the 760×680 Chrome
Minecraft Classic demo window in CI. Select another visible object with
`--crop X,Y,W,H`. Press **RESET ARENA** in the playground to restore its
original four HTML blocks.

## Evidence and limitations

The GitHub Actions `Minecraft playable cross-window demo` runs Chrome with
Minecraft Classic, waits for actual sky/terrain rather than a level-generation
loading screen, injects **real X11 key events** into the same Tk controller,
checks actual DOM nodes have been deleted and created, reloads the page to
check persistence, and records a real-desktop GIF. This is scripted **human
input emulation** for repeatable CI, not a claim that a human manually operated
the automated test. A local human plays with the same keyboard controls.

The source world remains read-only. The browser interactions apply to the
cooperating local HTML arena, not every website and not Chrome's omnibox. The
source block sprite is extracted from visible pixels, not via a Minecraft mod
or reverse-engineered memory. This is one genuine step beyond a floating
sprite, but is **not** a general-purpose cross-engine game-object transfer.
