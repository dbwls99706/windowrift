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
