#!/usr/bin/env bash
# Real keyboard input against a running Minecraft Classic source and a live Chrome DOM.
# Source game, web page, physical X11 key events, and GIF are all independently checked.
set -euo pipefail
mkdir -p artifacts/minecraft-play
export DISPLAY=:97
export XDG_RUNTIME_DIR="${RUNNER_TEMP:-/tmp}/wr-play-runtime"
mkdir -p "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"
Xvfb :97 -screen 0 1600x900x24 -nolisten tcp >artifacts/minecraft-play/xvfb.log 2>&1 & xvfb_pid=$!
for i in $(seq 1 40); do xprop -root >/dev/null 2>&1 && break; sleep .25; done
xprop -root >/dev/null 2>&1 || { cat artifacts/minecraft-play/xvfb.log; exit 1; }
openbox >artifacts/minecraft-play/openbox.log 2>&1 & wm_pid=$!
for i in $(seq 1 40); do
  xprop -root _NET_SUPPORTED 2>/dev/null | grep -q _NET_CLIENT_LIST && break
  sleep .25
done
httppid=''; gamepid=''; labpid=''; actorpid=''
cleanup() {
  for pid in "$actorpid" "$labpid" "$gamepid" "$httppid" "$wm_pid" "$xvfb_pid"; do
    [[ -z "$pid" ]] || kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
python -m http.server 8811 --bind 127.0.0.1 --directory examples >artifacts/minecraft-play/http.log 2>&1 & httppid=$!
google-chrome --no-sandbox --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage --use-gl=angle --use-angle=swiftshader \
  --enable-unsafe-swiftshader --remote-debugging-port=9223 \
  --remote-allow-origins=http://localhost \
  --user-data-dir="${RUNNER_TEMP:-/tmp}/wr-play-game" \
  --window-size=760,680 --window-position=25,90 \
  'https://classic.minecraft.net/' >artifacts/minecraft-play/game.log 2>&1 & gamepid=$!
google-chrome --no-sandbox --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage --remote-debugging-port=9222 \
  --remote-allow-origins=http://localhost \
  --user-data-dir="${RUNNER_TEMP:-/tmp}/wr-play-lab" \
  --window-size=735,680 --window-position=825,90 \
  'http://127.0.0.1:8811/minecraft-rift.html' >artifacts/minecraft-play/lab.log 2>&1 & labpid=$!
python scripts/ci/minecraft_check.py | tee artifacts/minecraft-play/game-proof.log
# A visible canvas can still be the level-generation loading screen. Wait for
# actual sky and terrain before choosing an item from the Minecraft hotbar.
python scripts/ci/minecraft_world_ready.py \
  --screenshot artifacts/minecraft-play/minecraft-world-ready.png \
  | tee artifacts/minecraft-play/world-proof.log
export WINDOWRIFT_BRIDGE_TOKEN="$(openssl rand -hex 24)"
python examples/minecraft_play_demo.py \
  --token "$WINDOWRIFT_BRIDGE_TOKEN" --duration 14 \
  --gif artifacts/minecraft-play/keyboard-minecraft-chrome.gif \
  >artifacts/minecraft-play/actor.log 2>&1 & actorpid=$!
for i in $(seq 1 80); do
  if grep -q BROWSER_BRIDGE_READY artifacts/minecraft-play/actor.log; then break; fi
  if ! kill -0 "$actorpid" 2>/dev/null; then cat artifacts/minecraft-play/actor.log; exit 1; fi
  sleep .15
done
grep -q BROWSER_BRIDGE_READY artifacts/minecraft-play/actor.log || {
  cat artifacts/minecraft-play/actor.log; echo 'Bridge failed to start'; exit 1;
}
python scripts/ci/block_arena_check.py --reset --token "$WINDOWRIFT_BRIDGE_TOKEN" --connect \
  | tee artifacts/minecraft-play/connect.log
# Use actual X11 KeyPress/KeyRelease events to the same Tk controller used by a human.
for i in $(seq 1 30); do
  controller=$(xdotool search --name 'WindowRift Play Controller' 2>/dev/null | head -1 || true)
  [[ -n "$controller" ]] && break
  sleep .2
done
[[ -n "$controller" ]] || { cat artifacts/minecraft-play/actor.log; echo 'Keyboard controller not visible'; exit 1; }
# The controller receives real KeyPress/KeyRelease events; we steer using
# the actual observed actor position rather than teleporting it in software.
python scripts/ci/block_arena_check.py --drive "$controller"   | tee artifacts/minecraft-play/keyboard-input.log
sleep .6
python scripts/ci/block_arena_check.py --status | tee artifacts/minecraft-play/play-status.log
python scripts/ci/block_arena_check.py --verify | tee artifacts/minecraft-play/play-result.log
wait "$actorpid" || { cat artifacts/minecraft-play/actor.log; exit 1; }
actorpid=''
python scripts/ci/block_arena_check.py --reload-verify | tee artifacts/minecraft-play/reload-proof.log
test -s artifacts/minecraft-play/keyboard-minecraft-chrome.gif
python - <<'PY'
from PIL import Image
im=Image.open('artifacts/minecraft-play/keyboard-minecraft-chrome.gif')
assert im.n_frames >= 16, f'Expected real recorded game play, got {im.n_frames} frames'
print('KEYBOARD_PLAY_REAL_DESKTOP_GIF_FRAMES=', im.n_frames)
PY
# No source Minecraft assets, cookies, profile data or credentials are uploaded.
