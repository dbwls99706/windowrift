# WindowRift

**Pull objects out of application windows and let them interact with your desktop.**

WindowRift turns **visible pixels** from a program window into an independent desktop actor. Select a window, draw a box around a character or object, extract its foreground, and drag it across your desktop. Sprites have gravity and can land on other application windows. An optional browser extension lets them collide with real page elements.

WindowRift is an **experimental visual-interaction prototype**, not a universal game-state modder. It does **not** remove characters from their original applications, read game memory, or change hidden game logic.

## Actual X11 demonstration

![An actual X11 desktop: the playable Rift Arcade source window, an extracted actor
in a separate shaped X11 window, and a Chromium page that received an impact.](docs/media/actual-x11-demo.png)

**Reproduced on 2026-10-15 with Xvfb, Openbox, Chromium, Python Tk and WindowRift's
GrabCut/color-key extraction and WebSocket bridge.** This is an authentic cropped
desktop screenshot, not an illustration or image composite. Because this test
environment lacked PySide6, the actor was drawn by the included
[`examples/x11_proof.py`](examples/x11_proof.py) Tk/XShape integration harness,
not by the production Qt control panel. The original game character remains
in the running game; no game-memory modifications are claimed.

## Features

| Feature | Behavior |
| --- | --- |
| Window capture | Choose a visible window on Windows or Linux X11 and draw a source rectangle. |
| Foreground extraction | Local OpenCV GrabCut, fast flat-background color key for pixel art, optional CPU-based AI (`rembg`), or an unmasked rectangle. |
| Desktop actors | Independent transparent windows with dragging, gravity, screen-edge bouncing, and landing on other window tops. |
| **Live pixels (experimental)** | Refresh pixels using the original foreground mask; optional bounded template tracking follows a moving object within its visible source window (72 px per sample). This does not read game state. |
| Browser DOM bridge | Per-tab Chrome extension for webpages, or a direct token-based connection from the included local collision lab. Opted-in targets receive real `windowrift:impact` events. |
| Local only | No screenshot uploads or external inference API. The bridge listens on `127.0.0.1` and requires a random token generated each run. |

## Quick start

**Requirements:** Python 3.10+, Windows 10/11 or **Linux X11**. Wayland and macOS are not supported in this prototype. The default OpenCV mode works without a downloaded AI model.

```bash
# Linux X11 only; either utility works (xprop/xwininfo is a fallback)
sudo apt install wmctrl

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .
windowrift
```

For optional AI foreground removal, run `python -m pip install -e '.[ai]'`. The `rembg` model is downloaded on its first use and can be large. Model segmentation may be inaccurate on game sprites; try GrabCut with background margin as an alternative.

### Pull an object out of a window

1. Open a game, animation or drawing in a **visible, unobstructed window**. Games using protected fullscreen or exclusive rendering may not be capturable.
2. Launch `windowrift`, choose the source window, and select an extraction method.
3. Optionally enable **Live pixels** to refresh the sprite about eight times per second. Enable **Track motion** to search a 72 px neighborhood for the same foreground inside its original window. The alpha mask is still fixed; fast movement, animation changes or occlusion can cause the tracker to freeze its last good frame. Keep selections at most 512 × 512 pixels.
4. Click **Capture window**, drag a box around the object, and confirm. Include some background margin when using GrabCut.
5. Drag the new actor **away from its original source region** so it does not occlude subsequent captures. The actor falls under gravity and lands on window edges. Right-double-click to remove it.

Live pixels works best with objects that retain their appearance. Tracking is deliberately bounded, and a low-confidence match freezes the last good frame rather than silently switching objects. It does not reconstruct occluded frames, infer unseen body parts, or transfer animation/game state. If other windows obscure the source, visible-pixel capture can be stale; WindowRift detects its own overlays but not every external occluder.

### Run a real playable game

The repository includes a small **Rift Arcade** game. It is intentionally a
real window with keyboard controls (arrow keys to move, space to jump, R to
reset), rather than a static image fixture.

```bash
python examples/rift_arcade.py
# In another terminal:
windowrift
```

Select the **Rift Arcade** source window, choose **Pixel art / flat background
color key**, draw a rectangle around the green Riftling with empty dark margin,
and release it onto the desktop. Color-key selection requires the crop's four
corners to have approximately the same background color. For other programs,
use GrabCut or AI removal.

The optional X11 `examples/x11_proof.py` harness reproduces the screenshot
workflow without Qt, using the same source game, foreground extraction and
WebSocket bridge. It requires X11, Tk, PIL and the X Shape extension, and assumes
Rift Arcade is already running:

```bash
python examples/x11_proof.py
```

It is a **demo proof tool**, not the general-purpose WindowRift GUI. It extracts
the game's sprite from a known crop for reproducibility. You can capture the
resulting desktop with your OS screenshot utility.

### Try a browser collision

1. In Chrome, visit `chrome://extensions`, enable **Developer mode**, and use **Load unpacked** on [`browser-extension/`](browser-extension/).
2. From the repository root run `python -m http.server 8000`.
3. Open [the collision lab](http://127.0.0.1:8000/examples/browser-lab.html) in a Chrome tab.
4. In WindowRift, click **Copy session token**. Paste it into the **Connect local lab** field and click the button. (Alternatively, enable the optional Chrome extension in this tab.)
5. Move a sprite into a labeled lab card. The card moves via an actual CSS transform, and the **Rift impacts** counter increases through a real `windowrift:impact` DOM event. Refresh the page to reset the local lab, or use the extension's **Reset page** control if using the extension.

When connected directly, the local demo handles only elements declaring `data-windowrift-target`. The Chrome extension can nudge other eligible DOM elements using CSS. Neither mode synthesizes clicks or submits forms. No synthetic clicks or arbitrary JavaScript execution are performed. Coordinates are approximate and most reliable at 100% OS scale.

## Architecture

```text
Visible application window ─── screen capture ─── selection rectangle
                                               │
                               GrabCut / optional rembg matte
                                               │
                                 PySide6 transparent actor
                               ┌───────────────┴───────────────┐
                      window-top physics             optional live refresh
                                               (same source ROI + alpha mask)
                               │
                    localhost WebSocket bridge
                               │
                    opted-in Chrome extension
                               │
                   CSS collision + explicit DOM event
```

## Scope and boundaries

- **Visual extraction, not executable or game-state extraction.** Original objects remain in their program. Motion tracking searches nearby visible pixels but does not change the source process or transfer physics state from the original game.
- **Capture of visible pixels.** Minimized, obscured, protected or exclusive fullscreen windows cannot be reliably captured. Mixed-DPI and decorated windows may have coordinate drift; especially on Linux X11 and Chrome.
- **No arbitrary modification.** WindowRift does not inject code into other processes, flash firmware, bypass game protections, control anti-cheat or automate unknown APIs.
- **Privacy.** Screenshots are processed locally; the optional AI model may be downloaded by `rembg` during setup. Use only windows and content you are permitted to capture. Keep the local bridge token private.
- **Browser interaction.** Per-tab opt-in is required. Page DOM mutations are cosmetic unless the site explicitly responds to the `windowrift:impact` custom event. No persistent storage mutations are performed by the extension itself.

## Development and verification

```bash
python -m pip install -e '.[dev]' pytest-asyncio
pytest -q
python -m compileall -q src
node --check browser-extension/content.js
node --check browser-extension/popup.js
node --test tests/js/*.test.cjs
```

The tests cover geometry, color-key and GrabCut segmentation, bounded template tracking, clipped screen coordinates, alpha compositing, WebSocket bridge validation, X11 window discovery, and browser-extension collision events. A real X11 proof run with Rift Arcade and Chromium confirmed foreground extraction, a shaped desktop actor, and an opt-in DOM event. The production PySide6 control panel and Windows behavior still require end-to-end verification on suitable hosts.

See the [Korean setup and demo guide](docs/README_ko.md) for additional details.

## Roadmap

- [x] Experimental bounded motion tracking within the source window; broader and occlusion-robust tracking remains future work.
- [ ] Per-platform coordinate calibration for browsers and mixed DPI monitors.
- [ ] Optional per-app adapter protocol for actual source-object state synchronization.
- [x] Captured X11 game + desktop actor + browser event using the lightweight proof harness.
- [ ] Verify the production Qt control panel on Windows and X11 with manual GUI tests and recorded evidence.

## License

[MIT](LICENSE). This is an independent project; it does not contain the REA firmware parser or repository code.
