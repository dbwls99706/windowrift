"""Binary probes must never turn assembly/strings into false state claims."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

import pytest

from windowrift.binary_probe import ProbeError, inspect_binary, inspect_linux_process, inspect_process
from windowrift.binary_cli import main


@pytest.fixture
def native_game(tmp_path):
    cc = shutil.which("cc") or shutil.which("gcc")
    if not cc:
        pytest.skip("C compiler unavailable")
    src = tmp_path / "game.c"
    src.write_text("""
#include <stdio.h>
int EntityHealth = 17;
__attribute__((noinline)) int UpdateMonster(int value) { return EntityHealth + value; }
int main(void) { printf("%d\\n", UpdateMonster(5)); return 0; }
""")
    out = tmp_path / "game"
    subprocess.run([cc, "-g", "-O0", "-o", str(out), str(src)], check=True, timeout=20)
    return out


def test_compiled_native_app_yields_evidence_but_not_live_object(native_game):
    r = inspect_binary(native_game, disassemble=True)
    assert r.format == "ELF" and r.architecture in ("x86_64", "aarch64")
    assert len(r.sha256) == 64 and r.sha256
    assert any("UpdateMonster" in s.name for s in r.object_symbols)
    assert any("EntityHealth" in s.name for s in r.object_symbols)
    assert r.disassembly is not None and "file format" in r.disassembly
    assert not r.portal_ready and not r.native_objects_verified
    assert native_game.read_bytes().startswith(b"\x7fELF")


def test_real_program_inspection_never_executes_input(native_game, tmp_path):
    marker = tmp_path / "should-not-run"
    # A file beginning with a shebang is not a supported native binary.
    executable = tmp_path / "danger.sh"
    executable.write_text(f"#!/bin/sh\ntouch {marker}\n")
    executable.chmod(0o755)
    with pytest.raises(ProbeError):
        inspect_binary(executable)
    assert not marker.exists()
    original = native_game.read_bytes()
    inspect_binary(native_game)
    assert native_game.read_bytes() == original


def test_jvm_archive_gives_structural_evidence(tmp_path):
    p = tmp_path / "example.jar"
    with zipfile.ZipFile(p, "w") as archive:
        archive.writestr("com/example/Monster.class", b"CAFEBABE")
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
    r = inspect_binary(p)
    assert r.format == "java-archive"
    assert r.architecture == "jvm"
    assert any(e.name == "Java / JVM" for e in r.engines)
    assert not r.portal_ready


def test_pe_64bit_sections(tmp_path):
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 0x80)
    data[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, 0, 0, 0, 0xF0, 0)
    data[0x84 + 20:0x84+20+2] = b"\x0b\x02"
    offset = 0x80 + 24 + 0xF0
    data[offset:offset+8] = b".text\0\0\0"
    struct.pack_into("<IIII", data, offset+8, 128, 0x1000, 100, 0x300)
    p = tmp_path / "game.exe"
    p.write_bytes(data)
    r = inspect_binary(p)
    assert r.format == "PE" and r.architecture == "x86_64" and ".text" in r.sections
    assert not r.engines and not r.portal_ready


def test_invalid_pe_bounds_rejected(tmp_path):
    p = tmp_path / "wrong.exe"
    data = bytearray(100)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 0xFFFFFFFE)
    p.write_bytes(data)
    with pytest.raises(ProbeError, match="beyond"):
        inspect_binary(p)


def test_game_engine_neighbor_is_heuristic(tmp_path):
    p = tmp_path / "UnityGame.exe"
    # A structurally valid 64-bit PE with no actual engine functions.
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 0, 0, 0, 0, 0, 0)
    p.write_bytes(data)
    (tmp_path / "GameAssembly.dll").write_bytes(b"dummy")
    r = inspect_binary(p)
    assert any(e.name == "Unity IL2CPP" and e.confidence == "medium" for e in r.engines)
    assert not r.portal_ready


def test_process_metadata_readonly(native_game):
    r = inspect_linux_process(os.getpid())
    assert r["pid"] == os.getpid()
    assert r["executable"]
    assert "read-only" in r["scope"]
    with pytest.raises(ProbeError):
        inspect_linux_process(0)


def test_cli_json_report(native_game, tmp_path):
    dst = tmp_path / "report.json"
    assert main([str(native_game), "--assembly", "--output", str(dst)]) == 0
    import json
    data = json.loads(dst.read_text())
    assert data["report"]["format"] == "ELF"
    assert data["report"]["portal_ready"] is False
    assert "adapter" in data["recommended_action"]


def test_mapped_module_does_not_claim_a_native_portal(native_game):
    r = inspect_binary(native_game, mapped_modules=("/games/libil2cpp.so",))
    assert any(h.name == "Unity IL2CPP" for h in r.engines)
    assert "libil2cpp.so" in r.modules
    assert not r.portal_ready and not r.native_objects_verified


def test_process_dispatch_uses_local_readonly_path(monkeypatch):
    monkeypatch.setattr('windowrift.binary_probe.platform.system', lambda: 'Linux')
    r = inspect_process(os.getpid())
    assert r['pid'] == os.getpid() and 'read-only' in r['scope']
