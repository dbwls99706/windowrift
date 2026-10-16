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
