#!/usr/bin/env bash
# Actual commercial-game pilot: original DOOM shareware data, read-only.
set -euo pipefail
mkdir -p artifacts
export DISPLAY=:99
export SDL_VIDEODRIVER=x11 SDL_AUDIODRIVER=dummy
export XDG_RUNTIME_DIR="${RUNNER_TEMP:-/tmp}/wr-doom-runtime"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
Xvfb :99 -screen 0 1600x900x24 -nolisten tcp >artifacts/xvfb.log 2>&1 & xvfb_pid=$!
for i in $(seq 1 40); do
  if xprop -root >/dev/null 2>&1; then break; fi
  if ! kill -0 "$xvfb_pid" 2>/dev/null; then cat artifacts/xvfb.log; exit 1; fi
  sleep 0.25
done
xprop -root >/dev/null 2>&1 || { echo 'X11 server failed'; exit 1; }
openbox >artifacts/openbox.log 2>&1 & wm_pid=$!
for i in $(seq 1 40); do
  if xprop -root _NET_SUPPORTED 2>/dev/null | grep -q _NET_CLIENT_LIST; then break; fi
  if ! kill -0 "$wm_pid" 2>/dev/null; then cat artifacts/openbox.log; exit 1; fi
  sleep 0.25
done
chrome_pid=""; doom_pid=""; http_pid=""; demo_pid=""
cleanup() {
  [[ -z "$chrome_pid" ]] || kill "$chrome_pid" 2>/dev/null || true
  [[ -z "$doom_pid" ]] || kill "$doom_pid" 2>/dev/null || true
  [[ -z "$http_pid" ]] || kill "$http_pid" 2>/dev/null || true
  [[ -z "$demo_pid" ]] || kill "$demo_pid" 2>/dev/null || true
  kill "$wm_pid" "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT
sleep 2
chocolate-doom -iwad "$DOOM_WAD" -window -width 640 -height 480 -warp 1 1 -skill 2 -nosound -nomusic >artifacts/game.log 2>&1 & doom_pid=$!
python -m http.server 8811 --bind 127.0.0.1 --directory examples >artifacts/http.log 2>&1 & http_pid=$!
google-chrome --no-sandbox --disable-gpu --disable-dev-shm-usage --no-first-run --no-default-browser-check \
  --remote-debugging-port=9222 --remote-allow-origins=http://localhost \
  --user-data-dir="${RUNNER_TEMP:-/tmp}/wr-doom-browser" --window-size=740,700 --window-position=810,70 \
  'http://127.0.0.1:8811/browser-lab.html' >artifacts/chrome.log 2>&1 & chrome_pid=$!
for i in $(seq 1 40); do
  if wmctrl -l | grep -Eiq 'doom' && wmctrl -l | grep -Eiq 'chrome'; then break; fi
  sleep 1
done
wmctrl -l | tee artifacts/windows.txt
if ! kill -0 "$doom_pid" 2>/dev/null; then echo 'DOOM process exited'; cat artifacts/game.log; exit 1; fi
if ! wmctrl -l | grep -Eiq 'doom'; then echo 'DOOM window not visible'; exit 1; fi
if ! wmctrl -l | grep -Eiq 'chrome'; then echo 'Chrome window not visible'; exit 1; fi
# Move both actual OS windows apart; do not synthesize their content.
doom_win=$(wmctrl -l | awk 'tolower($0) ~ /doom/ {print $1;exit}')
chrome_win=$(wmctrl -l | awk 'tolower($0) ~ /chrome/ && tolower($0) !~ /doom/ {print $1;exit}')
wmctrl -ir "$doom_win" -b remove,maximized_vert,maximized_horz || true
wmctrl -ir "$chrome_win" -b remove,maximized_vert,maximized_horz || true
wmctrl -ir "$doom_win" -e 0,35,95,750,670
wmctrl -ir "$chrome_win" -e 0,820,95,740,670
sleep 2
# Measure actual DOM target in live Chrome, not an invented screenshot coordinate.
export WINDOWRIFT_BRIDGE_TOKEN="$(openssl rand -hex 24)"
for i in $(seq 1 30); do
  if python scripts/ci/browser_probe.py --port 9222 --token "$WINDOWRIFT_BRIDGE_TOKEN" \
      --target-file artifacts/browser-target.json >artifacts/probe.log 2>&1; then break; fi
  sleep 0.4
done
test -s artifacts/browser-target.json || { cat artifacts/probe.log; exit 1; }
# The decoded IWAD frames are animated in the native, input-transparent X11 window.
# They are not extracted from a live actor or removed from the DOOM engine.
python examples/cinematic_omnibox_demo.py \
  --source-title Doom --browser-title 'WindowRift Collision Lab' \
  --doom-wad "$DOOM_WAD" --actor-height 66 \
  --token "$WINDOWRIFT_BRIDGE_TOKEN" \
  --target-file artifacts/browser-target.json \
  --screenshot artifacts/doom-chrome.png \
  --gif artifacts/doom-chrome.gif >artifacts/portal.log 2>&1 & demo_pid=$!
# Wait for the actual bridge handshake rather than assuming 0.8 seconds is
# sufficient to decode the original game assets and start the event listener.
for i in $(seq 1 60); do
  if grep -q 'BROWSER_BRIDGE_READY=' artifacts/portal.log; then break; fi
  if ! kill -0 "$demo_pid" 2>/dev/null; then cat artifacts/portal.log; exit 1; fi
  sleep 0.10
done
grep -q 'BROWSER_BRIDGE_READY=' artifacts/portal.log || {
  cat artifacts/portal.log; echo 'Browser bridge never started'; exit 1;
}
connected=0
for i in $(seq 1 5); do
  if python scripts/ci/browser_probe.py --port 9222 --token "$WINDOWRIFT_BRIDGE_TOKEN" \
    --target-file artifacts/browser-target.json --wait-connected \
      >>artifacts/probe.log 2>&1; then connected=1; break; fi
  sleep 0.15
done
if [[ "$connected" != 1 ]]; then tail -n 40 artifacts/probe.log; exit 1; fi
wait "$demo_pid" || { cat artifacts/portal.log; exit 1; }
demo_pid=""
python scripts/ci/browser_probe.py --port 9222 --check | tee artifacts/browser-impact.log
test -s artifacts/doom-chrome.png || { cat artifacts/portal.log; echo 'No capture'; exit 1; }
test -s artifacts/doom-chrome.gif || { echo 'No real desktop GIF'; exit 1; }
python - <<'PY'
import hashlib, json, os
from pathlib import Path
from PIL import Image
p = Path('artifacts/doom-chrome.png')
im = Image.open(p).convert('RGB')
assert im.width >= 1280 and im.height >= 720
assert Path('artifacts/doom-chrome.gif').stat().st_size > 1000
# Preserve only hashes and process/provenance evidence, never the WAD itself.
raw = Path(os.environ['DOOM_WAD']).read_bytes()
report = {
    'title': 'Original DOOM shareware 1.9 + Google Chrome',
    'original_game': 'id Software Doom Episode 1 (shareware 1.9)',
    'engine': 'Chocolate Doom (Ubuntu package)',
    'image': str(p),
    'gif': 'artifacts/doom-chrome.gif',
    'image_size': list(im.size),
    'wad_md5': hashlib.md5(raw).hexdigest(),
    'wad_sha256': hashlib.sha256(raw).hexdigest(),
    'game_process': 'chocolate-doom',
    'browser_process': 'google-chrome',
    'actor_source': 'TROOA1 sprite lump decoded from actual locally downloaded IWAD',
    'source_handoff': False,
    'native_os_overlay': True,
    'motion': 'jump, perch, pounce, impact, rebound, return',
    'browser_page_state_confirmed': True,
    'game_data_committed': False,
}
Path('artifacts/proof.json').write_text(json.dumps(report, indent=2) + '\n')
print('Actual game demonstration:', json.dumps(report))
PY

# The playable mode is a separate, REAL keyboard-event-controlled X11 actor.
# Chocolate Doom and Chrome remain running during this recording.
QT_QPA_PLATFORM=xcb python -m windowrift.doom_desktop \
  --doom-wad "$DOOM_WAD" \
  --record-gif artifacts/doom-keyboard-x11.gif >artifacts/doom-play.log 2>&1 || {
    cat artifacts/doom-play.log
    exit 1
  }
grep -q 'ACTUAL_DOOM_KEYBOARD_GIF=' artifacts/doom-play.log
test -s artifacts/doom-keyboard-x11.gif
