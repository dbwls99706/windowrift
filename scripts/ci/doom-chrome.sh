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
openbox >artifacts/openbox.log 2>&1 & wm_pid=$!
chrome_pid=""; doom_pid=""
cleanup() {
  [[ -z "$chrome_pid" ]] || kill "$chrome_pid" 2>/dev/null || true
  [[ -z "$doom_pid" ]] || kill "$doom_pid" 2>/dev/null || true
  kill "$wm_pid" "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT
sleep 2
chocolate-doom -iwad "$DOOM_WAD" -window -width 640 -height 480 -warp 1 1 -skill 2 -nosound -nomusic >artifacts/game.log 2>&1 & doom_pid=$!
google-chrome --no-sandbox --disable-gpu --disable-dev-shm-usage --no-first-run --no-default-browser-check \
  --user-data-dir="${RUNNER_TEMP:-/tmp}/wr-doom-browser" --window-size=740,700 --window-position=810,70 \
  'chrome://newtab' >artifacts/chrome.log 2>&1 & chrome_pid=$!
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
# The actor is a decoded actual IWAD patch; game continues unmodified.
timeout 35s python examples/chrome_omnibox_demo.py \
  --source-title Doom --doom-wad "$DOOM_WAD" --doom-lump TROOA1 \
  --actor-height 45 --travel 2 --duration 8 --screenshot-at 5 \
  --screenshot artifacts/doom-chrome.png > artifacts/portal.log 2>&1 || {
    cat artifacts/portal.log; exit 1;
  }
test -s artifacts/doom-chrome.png || { cat artifacts/portal.log; echo 'No captured screenshot'; exit 1; }
python - <<'PY'
import hashlib, json, os
from pathlib import Path
from PIL import Image
p = Path('artifacts/doom-chrome.png')
im = Image.open(p).convert('RGB')
assert im.width >= 1280 and im.height >= 720
# Preserve only hashes and process/provenance evidence, never the WAD itself.
raw = Path(os.environ['DOOM_WAD']).read_bytes()
report = {
    'title': 'Original DOOM shareware 1.9 + Google Chrome',
    'original_game': 'id Software Doom Episode 1 (shareware 1.9)',
    'engine': 'Chocolate Doom (Ubuntu package)',
    'image': str(p),
    'image_size': list(im.size),
    'wad_md5': hashlib.md5(raw).hexdigest(),
    'wad_sha256': hashlib.sha256(raw).hexdigest(),
    'game_process': 'chocolate-doom',
    'browser_process': 'google-chrome',
    'actor_source': 'TROOA1 sprite lump decoded from actual locally downloaded IWAD',
    'source_handoff': False,
    'native_os_overlay': True,
    'game_data_committed': False,
}
Path('artifacts/proof.json').write_text(json.dumps(report, indent=2) + '\n')
print('Actual game demonstration:', json.dumps(report))
PY
