#!/usr/bin/env bash
# Vanilla Mojang 1.21.1: same-UUID living entity escrow and return, not sprite copying.
set -euo pipefail
mkdir -p artifacts/real-mob
WORLD="$RUNNER_TEMP/windowrift-mobs-vanilla"
mkdir -p "$WORLD"
printf 'eula=true\n' > "$WORLD/eula.txt"
cat > "$WORLD/server.properties" <<'EOF'
enable-rcon=true
rcon.port=25575
rcon.password=windowrift-temporary-mob-ci-only-2026
server-port=25566
server-ip=127.0.0.1
online-mode=false
white-list=true
spawn-protection=0
max-players=1
view-distance=3
simulation-distance=3
level-type=minecraft:flat
spawn-monsters=false
spawn-animals=false
allow-flight=true
EOF
(cd "$WORLD"; exec java -Xms256M -Xmx1800M -jar "$WR_MINECRAFT_SERVER" nogui) \
  > artifacts/real-mob/server.log 2>&1 & pid=$!
cleanup(){ kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }
trap cleanup EXIT
export WINDOWRIFT_RCON_PASSWORD='windowrift-temporary-mob-ci-only-2026'
python scripts/ci/real_mob_roundtrip.py | tee artifacts/real-mob/roundtrip.log
test -s artifacts/real-mob/mob-proof.json

# The real server remains running during this GUI proof. Show a projection
# backed by the live stashed mob's UUID, never claim graphical client footage.
export DISPLAY=:97
Xvfb :97 -screen 0 1600x900x24 -nolisten tcp > artifacts/real-mob/xvfb.log 2>&1 & xpid=$!
for i in $(seq 1 40); do
  xprop -root >/dev/null 2>&1 && break
  sleep .2
done
xprop -root >/dev/null 2>&1 || { echo 'Xvfb failed'; exit 1; }
openbox > artifacts/real-mob/openbox.log 2>&1 & wpid=$!
for i in $(seq 1 40); do
  xprop -root _NET_SUPPORTED 2>/dev/null | grep -q _NET_CLIENT_LIST && break
  sleep .2
done
xprop -root _NET_SUPPORTED 2>/dev/null | grep -q _NET_CLIENT_LIST || {
  echo 'Window manager failed'; exit 1;
}
# Show the native Minecraft-backed projection over an actual unrelated
# application window rather than a mocked/synthesized browser screenshot.
google-chrome --no-sandbox --disable-gpu --disable-dev-shm-usage --no-first-run \
  --no-default-browser-check --user-data-dir="$RUNNER_TEMP/wr-mob-browser" \
  --window-size=850,740 --window-position=30,90 \
  'https://example.com/' > artifacts/real-mob/chrome.log 2>&1 & cpid=$!
sleep 2
kill -0 "$cpid" 2>/dev/null || { echo 'Chrome could not start'; cat artifacts/real-mob/chrome.log; exit 1; }
export QT_QPA_PLATFORM=xcb
python scripts/ci/real_mob_gui_proof.py | tee artifacts/real-mob/gui.log
test -s artifacts/real-mob/living-mob-outside.png
test -s artifacts/real-mob/living-mob-returned.png
test -s artifacts/real-mob/living-mob-keyboard-x11.gif
kill "$cpid" 2>/dev/null || true
kill "$wpid" "$xpid" 2>/dev/null || true

