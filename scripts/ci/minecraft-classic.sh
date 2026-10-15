#!/usr/bin/env bash
# Optional official Minecraft Classic proof. Never downloads or distributes game assets.
set -euo pipefail
mkdir -p artifacts/minecraft
export DISPLAY=:98
export XDG_RUNTIME_DIR="${RUNNER_TEMP:-/tmp}/wr-classic-runtime"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
Xvfb :98 -screen 0 1600x900x24 -nolisten tcp >artifacts/minecraft/xvfb.log 2>&1 & xpid=$!
for i in $(seq 1 40); do
  xprop -root >/dev/null 2>&1 && break
  sleep 0.25
done
openbox >artifacts/minecraft/openbox.log 2>&1 & wpid=$!
gamepid=""; labpid=""; httppid=""; demopid=""
cleanup() {
  for x in "$demopid" "$gamepid" "$labpid" "$httppid" "$wpid" "$xpid"; do
    [[ -z "$x" ]] || kill "$x" 2>/dev/null || true
  done
}
trap cleanup EXIT
sleep 2
python -m http.server 8811 --bind 127.0.0.1 --directory examples >artifacts/minecraft/http.log 2>&1 & httppid=$!
# Different browser profiles deliberately create two *real* separate OS windows.
google-chrome --no-sandbox --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage --use-gl=angle --use-angle=swiftshader \
  --enable-unsafe-swiftshader --remote-debugging-port=9223 \
  --remote-allow-origins=http://localhost \
  --user-data-dir="${RUNNER_TEMP:-/tmp}/wr-mc-game" \
  --window-size=760,680 --window-position=25,90 \
  'https://classic.minecraft.net/' >artifacts/minecraft/game-browser.log 2>&1 & gamepid=$!
google-chrome --no-sandbox --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage --remote-debugging-port=9222 \
  --remote-allow-origins=http://localhost \
  --user-data-dir="${RUNNER_TEMP:-/tmp}/wr-mc-lab" \
  --window-size=735,680 --window-position=825,90 \
  'http://127.0.0.1:8811/browser-lab.html' >artifacts/minecraft/lab-browser.log 2>&1 & labpid=$!
python scripts/ci/minecraft_check.py | tee artifacts/minecraft/classic-verification.log
wmctrl -lG >artifacts/minecraft/windows.txt
cat artifacts/minecraft/windows.txt
export WINDOWRIFT_BRIDGE_TOKEN="$(openssl rand -hex 24)"
for i in $(seq 1 25); do
  if python scripts/ci/browser_probe.py --port 9222 --token "$WINDOWRIFT_BRIDGE_TOKEN" \
    --target-file artifacts/minecraft/browser-target.json >artifacts/minecraft/probe.log 2>&1; then break; fi
  sleep 0.4
done
test -s artifacts/minecraft/browser-target.json || { cat artifacts/minecraft/probe.log; exit 1; }
# Source is a live screenshot crop from the *official Classic* browser window.
# Do not claim internal block state is removed or altered by the overlay.
python examples/cinematic_omnibox_demo.py \
  --source-title 'Minecraft Classic' --browser-title 'WindowRift Collision Lab' \
  --crop 290,636,36,40 --mode grabcut \
  --token "$WINDOWRIFT_BRIDGE_TOKEN" \
  --target-file artifacts/minecraft/browser-target.json \
  --gif artifacts/minecraft/minecraft-chrome.gif \
  --screenshot artifacts/minecraft/minecraft-impact.png >artifacts/minecraft/portal.log 2>&1 & demopid=$!
# The original game crop may take longer than 0.8 seconds to segment.
# Wait until the native overlay's WebSocket server is ready before connecting.
for i in $(seq 1 60); do
  if grep -q 'BROWSER_BRIDGE_READY=' artifacts/minecraft/portal.log; then break; fi
  if ! kill -0 "$demopid" 2>/dev/null; then cat artifacts/minecraft/portal.log; exit 1; fi
  sleep 0.10
done
grep -q 'BROWSER_BRIDGE_READY=' artifacts/minecraft/portal.log || {
  cat artifacts/minecraft/portal.log; echo 'Browser bridge never started'; exit 1;
}
connected=0
for i in $(seq 1 5); do
  if python scripts/ci/browser_probe.py --port 9222 --token "$WINDOWRIFT_BRIDGE_TOKEN" \
    --target-file artifacts/minecraft/browser-target.json --wait-connected \
      >>artifacts/minecraft/probe.log 2>&1; then connected=1; break; fi
  sleep 0.15
done
if [[ "$connected" != 1 ]]; then tail -n 40 artifacts/minecraft/probe.log; exit 1; fi
wait "$demopid" || { cat artifacts/minecraft/portal.log; exit 1; }
demopid=""
python scripts/ci/browser_probe.py --port 9222 --check | tee artifacts/minecraft/impact.log
test -s artifacts/minecraft/minecraft-chrome.gif
test -s artifacts/minecraft/minecraft-impact.png
