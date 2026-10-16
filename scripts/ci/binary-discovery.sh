#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts/binary-discovery
GAME=/usr/games/chocolate-doom
test -r "$GAME"
python -m pytest -q tests/test_binary_probe.py
sha256sum "$GAME" > artifacts/binary-discovery/before.sha256
windowrift-inspect "$GAME" --assembly --output artifacts/binary-discovery/chocolate-doom.json
sha256sum "$GAME" > artifacts/binary-discovery/after.sha256
cmp artifacts/binary-discovery/before.sha256 artifacts/binary-discovery/after.sha256
python - <<'PY'
import json
from pathlib import Path
r = json.loads(Path('artifacts/binary-discovery/chocolate-doom.json').read_text())['report']
assert r['format'] == 'ELF', r['format']
assert r['architecture'] in ('x86_64', 'x86', 'aarch64'), r['architecture']
assert len(r['sha256']) == 64
assert r['portal_ready'] is False
assert r['native_objects_verified'] is False
assert r['disassembly'] and 'file format' in r['disassembly']
print('REAL_PUBLISHED_DOOM_EXECUTABLE_READ_ONLY_INSPECTION=PASS')
print('BINARY_SHA256=' + r['sha256'])
print('NATIVE_GAME_OBJECT_TRANSFER_VERIFIED=false')
PY
