#!/usr/bin/env bash
# Real Minecraft Classic in one Chrome window; real UNRELATED web in another.
# OS-level block placement with mouse events; no game source/code or web DOM edits.
set -euo pipefail
mkdir -p artifacts/desktop-world
export DISPLAY=:95
export XDG_RUNTIME_DIR="${RUNNER_TEMP:-/tmp}/windowrift-world-x11"
mkdir -p "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"
Xvfb :95 -screen 0 1600x900x24 -nolisten tcp >artifacts/desktop-world/xvfb.log 2>&1 & xpid=$!
for i in $(seq 1 40); do
  xprop -root >/dev/null 2>&1 && break
  kill -0 "$xpid" 2>/dev/null || { cat artifacts/desktop-world/xvfb.log;exit 1; }
  sleep .25
done
xprop -root >/dev/null 2>&1 || { echo 'No X display'; exit 1; }
openbox >artifacts/desktop-world/openbox.log 2>&1 & wpid=$!
for i in $(seq 1 40); do
  xprop -root _NET_SUPPORTED 2>/dev/null | grep -q _NET_CLIENT_LIST && break
  sleep .25
done
xprop -root _NET_SUPPORTED 2>/dev/null | grep -q _NET_CLIENT_LIST || {
  cat artifacts/desktop-world/openbox.log;echo 'Window manager failed';exit 1;
}
gamepid='';webpid='';builderpid=''
cleanup() {
  for pid in "$builderpid" "$webpid" "$gamepid" "$wpid" "$xpid"; do
    [[ -z "$pid" ]] || kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
# Separate Chrome profiles -> separate genuine OS windows. No bundled assets.
google-chrome --no-sandbox --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage --use-gl=angle --use-angle=swiftshader \
  --enable-unsafe-swiftshader --remote-debugging-port=9223 \
  --remote-allow-origins=http://localhost \
  --user-data-dir="${RUNNER_TEMP:-/tmp}/wr-world-minecraft" \
  --window-size=760,680 --window-position=25,90 \
  'https://classic.minecraft.net/' >artifacts/desktop-world/minecraft.log 2>&1 & gamepid=$!
google-chrome --no-sandbox --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage --remote-debugging-port=9222 \
  --remote-allow-origins=http://localhost \
  --user-data-dir="${RUNNER_TEMP:-/tmp}/wr-world-other" \
  --window-size=735,680 --window-position=825,90 \
  'https://en.wikipedia.org/wiki/Art' >artifacts/desktop-world/website.log 2>&1 & webpid=$!
python scripts/ci/minecraft_check.py | tee artifacts/desktop-world/game-ready.log
python scripts/ci/minecraft_world_ready.py \
  --screenshot artifacts/desktop-world/real-minecraft-world.png \
  | tee artifacts/desktop-world/terrain-ready.log
python scripts/ci/real_site_probe.py --timeout 40 \
  | tee artifacts/desktop-world/external-website.log
wmctrl -lG | tee artifacts/desktop-world/windows.txt
# Explicitly isolate the game from the unrelated website before picking a block.
python examples/minecraft_desktop_builder.py \
  --world-file artifacts/desktop-world/desktop-world.json \
  --duration 23 --gif artifacts/desktop-world/real-game-desktop-build.gif \
  >artifacts/desktop-world/builder.log 2>&1 & builderpid=$!
for i in $(seq 1 80); do
  grep -q '^DESKTOP_BUILD_MODE=active' artifacts/desktop-world/builder.log && break
  if ! kill -0 "$builderpid" 2>/dev/null; then cat artifacts/desktop-world/builder.log;exit 1;fi
  sleep .15
done
grep -q '^DESKTOP_BUILD_MODE=active' artifacts/desktop-world/builder.log || { cat artifacts/desktop-world/builder.log;exit 1; }
controller=''
for i in $(seq 1 30); do
  controller=$(xdotool search --name 'WindowRift | Desktop Builder' 2>/dev/null | head -1 || true)
  [[ -n "$controller" ]] && break
  sleep .1
done
[[ -n "$controller" ]] || { echo 'Controller not found';cat artifacts/desktop-world/builder.log;exit 1; }
python scripts/ci/desktop_world_check.py \
  --drive "$controller" --world artifacts/desktop-world/desktop-world.json \
  --out artifacts/desktop-world | tee artifacts/desktop-world/mouse-input.log
# Switching to an unrelated site must not affect the native desktop blocks.
python scripts/ci/real_site_probe.py --navigate 'https://example.com' --timeout 40 \
  | tee artifacts/desktop-world/second-website.log
python - <<'PY'
from pathlib import Path
from PIL import ImageGrab
ImageGrab.grab(xdisplay=':95').save('artifacts/desktop-world/minecraft-blocks-on-example-com.png')
PY
python scripts/ci/desktop_world_check.py \
  --check --world artifacts/desktop-world/desktop-world.json \
  --out artifacts/desktop-world | tee artifacts/desktop-world/world-persistence.log
wait "$builderpid" || { tail -n 100 artifacts/desktop-world/builder.log;exit 1; }
builderpid=''
python - <<'PY'
from pathlib import Path
from PIL import Image
p=Path('artifacts/desktop-world/real-game-desktop-build.gif')
assert p.stat().st_size>15000,'Missing genuine recorded desktop frames'
im=Image.open(p)
assert im.n_frames>=12,f'Expected real build sequence; only {im.n_frames} GIF frames'
for shot in ('minecraft-blocks-on-wikipedia.png','minecraft-blocks-on-example-com.png'):
    pic=Image.open('artifacts/desktop-world/'+shot)
    assert pic.size==(1600,900)
print(f'REAL_CROSS_WEBSITE_BUILD_GIF_FRAMES={im.n_frames}',flush=True)
print('OS_LEVEL_DESKTOP_BLOCK_WORLD_CONFIRMED=true',flush=True)
PY
