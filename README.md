# WindowRift

**Pull objects out of application windows and let them interact with your desktop.**

WindowRift turns **visible pixels** from a program window into an independent desktop actor. Select a window, draw a box around a character or object, extract its foreground, and drag it across your desktop. Sprites have gravity and can land on other application windows. An optional browser extension lets them collide with real page elements.

WindowRift is an **experimental visual-interaction prototype**, not a universal game-state modder. It does **not** remove characters from their original applications, read game memory, or change hidden game logic.

## Features

| Feature | Behavior |
| --- | --- |
| Window capture | Choose a visible window on Windows or Linux X11 and draw a source rectangle. |
| Foreground extraction | Use local OpenCV GrabCut, optional CPU-based AI (`rembg`), or an unmasked rectangle. |
| Desktop actors | Independent transparent windows with dragging, gravity, screen-edge bouncing, and landing on other window tops. |
| **Live pixels (experimental)** | Refresh a sprite from its original selected rectangle while the source stays visible. The foreground mask stays fixed. |
| Browser DOM bridge | Per-tab, opt-in Chrome extension that nudges page elements through CSS. Elements explicitly marked `data-windowrift-target` also receive a `windowrift:impact` event on actor entry. |
| Local only | No screenshot uploads or external inference API. The bridge listens on `127.0.0.1` and requires a random token generated each run. |

## Quick start

**Requirements:** Python 3.10+, Windows 10/11 or **Linux X11**. Wayland and macOS are not supported in this prototype. The default OpenCV mode works without a downloaded AI model.

```bash
# Linux X11 only
sudo apt install xdotool

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
3. Optionally enable **Live pixels**. This refreshes the sprite's colors from the **same crop** about eight times per second when visible. The original alpha mask is reused; moving outside the rectangle is **not tracked**. Keep selections at most 512 × 512 pixels.
4. Click **Capture window**, drag a box around the object, and confirm. Include some background margin when using GrabCut.
5. Drag the new actor **away from its original source region** so it does not occlude subsequent captures. The actor falls under gravity and lands on window edges. Right-double-click to remove it.

Live pixels is best for a character **animating in place**. It does not reconstruct missing frames, infer unseen body parts, or carry animation/game state out of the process. If the source window is hidden or another window covers the selected region, the sample may be stale; WindowRift refuses to sample its own overlays but cannot detect every other occluder.

### Try a browser collision

1. In Chrome, visit `chrome://extensions`, enable **Developer mode**, and use **Load unpacked** on [`browser-extension/`](browser-extension/).
2. From the repository root run `python -m http.server 8000`.
3. Open [the collision lab](http://127.0.0.1:8000/examples/browser-lab.html) in a Chrome tab.
4. In WindowRift, click **Copy session token**. Open the extension popup in that tab, paste it, then choose **Enable this tab**.
5. Move a sprite into a labeled lab card. The card moves via an actual CSS transform, and the **Rift impacts** counter increases via a real `windowrift:impact` DOM event. **Reset page** restores element styles and disconnects the extension for that tab.

Browser events are emitted only for elements declaring `data-windowrift-target`. Regular page elements receive visual CSS transformations only. No synthetic clicks or arbitrary JavaScript execution are performed. Coordinates are approximate and most reliable at 100% OS scale.

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

- **Visual extraction, not executable or game-state extraction.** Original objects remain in their program. Live mode does not track a moving character outside the selection or transfer physics state from the original game.
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

The tests cover geometry, segmentation, clipped screen coordinates, live source geometry, alpha-mask compositing, the local WebSocket bridge, window enumeration, and browser collision events. Real multi-window capture and end-to-end Chrome/game interactions still require manual verification on Windows or an actual X11 desktop.

See the [Korean setup and demo guide](docs/README_ko.md) for additional details.

## Roadmap

- [ ] Track moving objects beyond a fixed capture rectangle without sampling other windows.
- [ ] Per-platform coordinate calibration for browsers and mixed DPI monitors.
- [ ] Optional per-app adapter protocol for actual source-object state synchronization.
- [ ] Recorded side-by-side demo on a real Windows/X11 desktop.

## License

[MIT](LICENSE). This is an independent project; it does not contain the REA firmware parser or repository code.
