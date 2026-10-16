#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts/real-minecraft
# This server world is isolated in a disposable GitHub Actions runner.
TEMP_WORLD="$RUNNER_TEMP/windowrift-vanilla"
mkdir -p "$TEMP_WORLD"
cd "$TEMP_WORLD"
printf 'eula=true\n' > eula.txt
cat > server.properties <<'EOF'
enable-rcon=true
rcon.port=25575
rcon.password=windowrift-ci-only-no-external-access-2026
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
java -Xms256M -Xmx1800M -jar "$WR_MINECRAFT_SERVER" nogui \
  > "$GITHUB_WORKSPACE/artifacts/real-minecraft/server.log" 2>&1 &
server_pid=$!
cleanup() {
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT
cd "$GITHUB_WORKSPACE"
export WINDOWRIFT_RCON_PASSWORD='windowrift-ci-only-no-external-access-2026'
PYTHONPATH=src python scripts/ci/real_minecraft_roundtrip.py | tee artifacts/real-minecraft/results.log
test -s artifacts/real-minecraft/proof.json

# Show the live, game-backed object in a *real* X11 native Qt desktop window.
# The Minecraft client JAR is read from a temporary runner path for textures.
export DISPLAY=:96
Xvfb :96 -screen 0 1600x900x24 -nolisten tcp \
  > artifacts/real-minecraft/xvfb.log 2>&1 &
xpid=$!
for i in $(seq 1 40); do
  if xprop -root >/dev/null 2>&1; then break; fi
  sleep 0.2
done
xprop -root >/dev/null 2>&1 || { echo 'Xvfb did not start'; exit 1; }
openbox > artifacts/real-minecraft/openbox.log 2>&1 &
wpid=$!
for i in $(seq 1 40); do
  if xprop -root _NET_SUPPORTED 2>/dev/null | grep -q _NET_CLIENT_LIST; then break; fi
  sleep 0.2
done
xprop -root _NET_SUPPORTED 2>/dev/null | grep -q _NET_CLIENT_LIST || { echo 'No window manager'; exit 1; }
export QT_QPA_PLATFORM=xcb
python scripts/ci/real_minecraft_gui_proof.py \
  | tee artifacts/real-minecraft/gui.log
test -s artifacts/real-minecraft/live-block-outside.png
test -s artifacts/real-minecraft/live-block-returned.png
kill "$wpid" "$xpid" 2>/dev/null || true
