# Real commercial-game test: Doom shareware

This pilot is deliberately about an **actual published commercial game's
shareware edition**, not the bundled Rift Arcade exercise or a recreation.
It uses **id Software Doom 1.9 shareware** and the packaged **Chocolate Doom**
source port. The WAD is acquired at runtime by the GitHub Actions job and
checked against MD5 `f0cefca49926d00903cf57551d901abe` before use.
The `doom1.wad` archive is never included in this repository, a release,
or a CI upload artifact. Do not treat the WAD's shareware terms as an MIT license.

## The test, exactly

1. Download the original shareware IWAD into an ephemeral runner directory.
2. Verify its checksum and launch Chocolate Doom on an X11 desktop.
3. Launch a second, genuine Google Chrome window.
4. Read the `TROOA1` picture patch and `PLAYPAL` palette from the temporary
   WAD, decoding the original Doom sprite **in memory**. This is a
   **game-specific asset-assisted adapter**, not AI image extraction.
5. Move the transparent, mouse-pass-through X11 sprite window from the Doom
   window to the **real** Chrome omnibox region. Preserve keyboard input.
6. Capture an actual X11 desktop screenshot, short recorded GIF, and machine-readable proof
   with the WAD checksum and provenance. Only those limited outputs and logs
   are eligible for the seven-day CI artifact.

The original Doom process continues running unmodified, and no Doom enemy
state is transferred or deleted. This pilot does **not** establish that an
arbitrary commercial game supports actor handoff, automatic motion tracking,
complex 3D silhouette extraction, or game-process mutation.

## GitHub Actions

The workflow [commercial-game-demo.yml](../.github/workflows/commercial-game-demo.yml)
executes on its own integration changes (and is also manually dispatchable).
**A green workflow with `doom-chrome.png`, `doom-chrome.gif` and `proof.json` is required
before claiming a successful live commercial-game run.** If the source-port
package, browser binary, WAD mirror or display cannot be started, the job
should fail rather than fake a screenshot.

## Manual reproduction on Linux X11

Acquire a lawful Doom shareware `doom1.wad` file yourself, verify its MD5
value above, and install Chocolate Doom, a window manager and Python
WindowRift dependencies. Run the real Doom game in a window:

```bash
chocolate-doom -iwad /path/to/doom1.wad -window -warp 1 1 -skill 2 -nosound -nomusic
```

Open a normal Chrome window, then in a second terminal:

```bash
python examples/chrome_omnibox_demo.py \
  --source-title Doom --doom-wad /path/to/doom1.wad --doom-lump TROOA1 \
  --screenshot /tmp/doom-chrome.png
```

`--doom-wad` never downloads game data, writes an extracted sprite, or
changes the running game. It only reads the named picture patch from the
file you supplied. The non-WAD path of this same script instead uses the
visible-window screenshot plus optional GrabCut, color-key or rembg.

## Licenses and attribution

Doom: © id Software. Chocolate Doom is a third-party GPL project; this
repository neither vendors it nor links to its engine. This project
contains no Doom source, IWAD, patch sprites, extracted lump data, or
license grant for proprietary game assets. Reuse of screenshots is subject
to the applicable rights of their owners.

## Verified baseline

The first successful GitHub Actions run is
[commercial game proof #38692731397](https://github.com/dbwls99706/windowrift/actions/runs/38692731397).
The original game archive matched the published DOOM 1.9 shareware MD5;
Chocolate Doom and Chrome ran simultaneously in X11, and the result is
shown at [this authentic screenshot](media/doom-shareware-chrome-x11.png).
The verification does not establish an in-game actor state handoff.

## Actual animated commercial-game recording

A later [**successful GitHub Actions run #38693889712**](https://github.com/dbwls99706/windowrift/actions/runs/38693889712)
started the original Doom 1.9 shareware game under Chocolate Doom and Google
Chrome on X11, then recorded 35 consecutive desktop frames to
`artifacts/doom-chrome.gif`. The workflow's downloadable
`doom-shareware-chrome-x11` artifact also includes its screenshot,
`proof.json`, and executable logs (seven-day artifact retention).
The native overlay comes from the original `TROOA1` sprite patch in the
locally acquired shareware data. It is **not** a live transferred Doom enemy,
source-process patch, or AI-generated game art.

