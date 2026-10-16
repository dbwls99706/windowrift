"""Evidence-first, read-only executable reconnaissance for WindowRift portals.

An executable's instruction stream is evidence, not a portable game-object API.
This module never loads, executes, patches or attaches to the inspected binary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
import platform
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zipfile

MAX_SIZE = 128 * 1024 * 1024
MAX_SECTIONS = 1024
MAX_SYMBOLS = 8000
MAX_JAR_ENTRIES = 30000
MAX_DISASM_CHARS = 16000
ENGINE_PATTERN = re.compile(r"(?:entity|actor|object|player|monster|mob|spawn|destroy|update|tick|render|transform|position|health|damage|scene|serialize|block|level)", re.IGNORECASE)
ARCH_ELF = {3: "x86", 40: "arm", 62: "x86_64", 183: "aarch64", 243: "riscv"}
ARCH_PE = {0x14c: "x86", 0x8664: "x86_64", 0xaa64: "aarch64", 0x1c0: "arm"}


class ProbeError(ValueError):
    """Target could not be interpreted without unsafe guesses."""


@dataclass(frozen=True)
class Evidence:
    source: str
    detail: str
    confidence: str = "observed"


@dataclass(frozen=True)
class EngineHint:
    name: str
    confidence: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class SymbolHint:
    name: str
    address: str
    kind: str
    source: str


@dataclass(frozen=True)
class ProbeReport:
    schema: int
    target: str
    size_bytes: int
    sha256: str
    format: str
    architecture: str
    sections: tuple[str, ...]
    modules: tuple[str, ...]
    engines: tuple[EngineHint, ...]
    object_symbols: tuple[SymbolHint, ...]
    evidence: tuple[Evidence, ...]
    disassembly: str | None
    limitations: tuple[str, ...]
    native_objects_verified: bool = False
    portal_ready: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _range(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ProbeError(f"{label} extends beyond the file")
    return data[offset:offset + size]


def _zstring(data: bytes, index: int, *, limit: int = 256) -> str:
    if index < 0 or index >= len(data):
        return ""
    end = data.find(b"\0", index, min(len(data), index + limit))
    if end == -1:
        return ""
    return data[index:end].decode("utf-8", "replace")


def _elf(data: bytes) -> tuple[str, list[str], list[str], list[SymbolHint]]:
    if len(data) < 52 or data[:4] != b"\x7fELF" or data[4] not in (1, 2) or data[5] not in (1, 2):
        raise ProbeError("Invalid ELF header")
    is64 = data[4] == 2
    endian = "<" if data[5] == 1 else ">"
    header_fmt = endian + ("16sHHIQQQIHHHHHH" if is64 else "16sHHIIIIIHHHHHH")
    if len(data) < struct.calcsize(header_fmt):
        raise ProbeError("Truncated ELF header")
    hdr = struct.unpack_from(header_fmt, data)
    machine = hdr[2]
    shoff, shentsize, shnum, names_idx = hdr[6], hdr[11], hdr[12], hdr[13]
    arch = ARCH_ELF.get(machine, f"machine-{machine}")
    section_fmt = endian + ("IIQQQQIIQQ" if is64 else "IIIIIIIIII")
    entry_size = struct.calcsize(section_fmt)
    if not shnum:  # A valid ELF may omit its section table.
        return arch, [], [], []
    if shnum > MAX_SECTIONS or shentsize < entry_size or names_idx >= shnum:
        raise ProbeError("Unsupported or malformed ELF section table")
    _range(data, shoff, shentsize * shnum, "ELF sections")
    sections = [struct.unpack_from(section_fmt, data, shoff + i * shentsize) for i in range(shnum)]
    for sec in sections:
        _range(data, sec[4], 0 if sec[1] == 8 else sec[5], "ELF section")
    shstr = sections[names_idx]
    shnames = _range(data, shstr[4], shstr[5], "ELF section names")
    names = [_zstring(shnames, sec[0]) for sec in sections]
    modules = []
    symbols = []
    for sec, secname in zip(sections, names):
        sectype, offset, length, strtabid, entry = sec[1], sec[4], sec[5], sec[6], sec[9]
        if sectype not in (2, 6, 11) or strtabid >= shnum:
            continue
        strsec = sections[strtabid]
        st = _range(data, strsec[4], strsec[5], "ELF names")
        raw = _range(data, offset, length, f"ELF {secname}")
        if sectype == 6:
            fmt = endian + ("qQ" if is64 else "iI")
            minimum = struct.calcsize(fmt)
            stride = entry or minimum
            if stride < minimum:
                continue
            for i in range(min(len(raw) // stride, MAX_SYMBOLS)):
                tag, value = struct.unpack_from(fmt, raw, i * stride)
                if tag == 1:
                    name = _zstring(st, value)
                    if name:
                        modules.append(name)
        elif sectype in (2, 11):
            fmt = endian + ("IBBHQQ" if is64 else "IIIBBH")
            minimum = struct.calcsize(fmt)
            stride = entry or minimum
            if stride < minimum:
                continue
            for i in range(min(len(raw) // stride, MAX_SYMBOLS)):
                row = struct.unpack_from(fmt, raw, i * stride)
                nameidx, info, address = (row[0], row[1], row[4]) if is64 else (row[0], row[3], row[1])
                kind = info & 0x0f
                if kind not in (1, 2):
                    continue
                name = _zstring(st, nameidx)
                if name and ENGINE_PATTERN.search(name):
                    symbols.append(SymbolHint(name[:200], hex(address), "function" if kind == 2 else "data", secname))
    return arch, names, sorted(set(modules)), symbols[:100]


def _pe(data: bytes) -> tuple[str, list[str], list[str], list[SymbolHint]]:
    if len(data) < 64 or data[:2] != b"MZ":
        raise ProbeError("Invalid PE DOS header")
    peoff = struct.unpack_from("<I", data, 0x3c)[0]
    if _range(data, peoff, 4, "PE signature") != b"PE\x00\x00":
        raise ProbeError("Invalid PE signature")
    header = _range(data, peoff + 4, 20, "PE COFF header")
    machine, number, _, _, _, opt_size, _ = struct.unpack("<HHIIIHH", header)
    if number > MAX_SECTIONS:
        raise ProbeError("Too many PE sections")
    raw = _range(data, peoff + 24 + opt_size, number * 40, "PE sections")
    names = []
    for i in range(number):
        offset = i * 40
        name = raw[offset:offset + 8].split(b"\0")[0].decode("ascii", "replace")
        names.append(name)
        _, _, rawsize, rawpos = struct.unpack_from("<IIII", raw, offset + 8)
        if rawsize:  # Some PE images have uninitialized / zero-raw sections.
            _range(data, rawpos, rawsize, f"PE section {name}")
    return ARCH_PE.get(machine, f"machine-{machine}"), names, [], []


def _jar(path: Path) -> tuple[str, list[str], list[str], list[SymbolHint]]:
    try:
        with zipfile.ZipFile(path) as z:
            if len(z.infolist()) > MAX_JAR_ENTRIES:
                raise ProbeError("Archive has too many entries")
            entries = [item.filename for item in z.infolist()]
    except (zipfile.BadZipFile, OSError) as exc:
        raise ProbeError("Invalid ZIP/JAR") from exc
    return ("jvm" if path.suffix.lower() in (".jar", ".jmod") else "archive"), entries[:80], [], []


def _neighbors(path: Path) -> list[str]:
    try:
        neighbors = sorted(item.name for item in path.parent.iterdir())
    except OSError:
        return []
    recognized = ("UnityPlayer.dll", "GameAssembly.dll", "global-metadata.dat", "data.win", "libil2cpp.so", "libunity.so")
    matches = [f for f in neighbors if f in recognized or f.endswith(("_Data", ".pck"))]
    return matches[:50]


def _engine_hints(data: bytes, fmt: str, entries: list[str], modules: list[str], neighbors: list[str]) -> tuple[EngineHint, ...]:
    # Byte matches are weak evidence. Neighboring engine files are stronger but
    # may still belong to unrelated software in the same directory.
    sample = data[:8 * 1024 * 1024] + data[-min(len(data), 1024 * 1024):]
    observed = set(neighbors)
    observed.update(modules)
    names = "\n".join(entries[:400])
    candidates = []
    checks = (
        ("Unity IL2CPP", ("GameAssembly.dll", "libil2cpp.so", "global-metadata.dat"), (b"il2cpp_init", b"UnityPlayer")),
        ("Unity Mono", ("UnityPlayer.dll", "libmono.so"), (b"mono_jit_init", b"UnityEngine")),
        ("Unreal Engine", ("UE4Game", "UnrealEditor", "UE5"), (b"/Script/Engine", b"FEngineVersion")),
        ("Godot", tuple(x for x in neighbors if x.endswith(".pck")), (b"Godot Engine", b"GodotSharp")),
        ("GameMaker", ("data.win",), (b"GameMaker", b"YoYoGames")),
        ("Java / JVM", ("jvm.dll", "libjvm.so",), (b"java/lang/Object", b"JNI_CreateJavaVM")),
    )
    if fmt == "java-archive":
        candidates.append(EngineHint("Java / JVM", "high", (Evidence("format", "JAR bytecode classes"),)))
    for engine, strong_names, weak_signatures in checks:
        ev = []
        for name in strong_names:
            if name in observed or any(name in value for value in entries):
                ev.append(Evidence("nearby-file-or-module", name))
        for literal in weak_signatures:
            if literal in sample or literal.decode("ascii", "replace") in names:
                ev.append(Evidence("embedded-marker", literal.decode("ascii", "replace"), "heuristic"))
        if not ev:
            continue
        confidence = "medium" if any(x.source == "nearby-file-or-module" for x in ev) else "low"
        candidates.append(EngineHint(engine, confidence, tuple(ev)))
    # Preserve evidence without inventing an engine conclusion.
    distinct = {x.name: x for x in candidates}
    return tuple(distinct.values())


def _objdump(path: Path) -> str | None:
    exe = shutil.which("objdump")
    if not exe:
        return None
    try:
        done = subprocess.run([exe, "-d", "-M", "intel", "--", str(path)],
                              capture_output=True, text=True, errors="replace", timeout=6, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode:
        return None
    return done.stdout[:MAX_DISASM_CHARS]


def inspect_binary(path: str | Path, *, disassemble: bool = False,
                   mapped_modules: tuple[str, ...] = ()) -> ProbeReport:
    target = Path(path).expanduser().resolve(strict=True)
    if not target.is_file():
        raise ProbeError("Choose one regular executable or archive file")
    size = target.stat().st_size
    if not 16 <= size <= MAX_SIZE:
        raise ProbeError("File size is outside the bounded 16-byte to 128-MiB analysis range")
    data = target.read_bytes()
    sections: list[str] = []
    modules: list[str] = []
    symbols: list[SymbolHint] = []
    if data.startswith(b"\x7fELF"):
        fmt, arch = "ELF", "unknown"
        arch, sections, modules, symbols = _elf(data)
    elif data.startswith(b"MZ"):
        fmt = "PE"
        arch, sections, modules, symbols = _pe(data)
    elif data.startswith(b"PK\x03\x04"):
        fmt = "java-archive" if target.suffix.lower() in (".jar", ".jmod") else "ZIP"
        arch, sections, modules, symbols = _jar(target)
    else:
        raise ProbeError("Unrecognized file type; no patching or execution attempted")
    neighbors = _neighbors(target)
    loaded = [Path(x).name for x in mapped_modules if x.startswith("/")]
    engine = _engine_hints(data, fmt, sections, modules + loaded, neighbors)
    modules = sorted(set(modules + loaded))[:100]
    evidence = [Evidence("file-signature", fmt), Evidence("sha256", hashlib.sha256(data).hexdigest())]
    evidence.extend(Evidence("adjacent-file", x, "heuristic") for x in neighbors)
    evidence.extend(Evidence("process-module", x) for x in loaded[:30])
    # No portable game object semantics can be established by executable metadata.
    limitations = (
        "Executable inspection cannot identify a live entity or prove object identity.",
        "Native-state extraction requires validated, target-specific runtime instrumentation or an authorized application API.",
        "No binary modification, process attachment, or anti-cheat bypass is performed.",
    )
    asm = _objdump(target) if disassemble and fmt in ("ELF", "PE") else None
    return ProbeReport(1, str(target), size, hashlib.sha256(data).hexdigest(), fmt, arch,
                       tuple(sections[:100]), tuple(modules[:100]), engine, tuple(symbols),
                       tuple(evidence), asm, limitations)


def inspect_linux_process(pid: int) -> dict:
    """Read *mapping names*, not memory contents; Linux permissions still apply."""
    if not isinstance(pid, int) or pid <= 0:
        raise ProbeError("PID must be a positive integer")
    base = Path("/proc") / str(pid)
    try:
        executable = os.readlink(base / "exe")
        lines = (base / "maps").read_text(encoding="utf-8").splitlines()
    except (PermissionError, OSError) as exc:
        raise ProbeError("Cannot inspect Linux process metadata") from exc
    names = sorted({s.rsplit(None, 1)[-1] for s in lines if "/" in s and len(s.split()) >= 6})
    names = [n for n in names if n.startswith("/")]
    return {"pid": pid, "executable": executable, "mapped_files": names[:200],
            "scope": "read-only /proc process metadata; no injection or memory reads"}


def inspect_process(pid: int) -> dict:
    """Get a process executable path without reading or altering its memory."""
    system = platform.system()
    if system == "Linux":
        return inspect_linux_process(pid)
    if system != "Windows":
        raise ProbeError("Running-process discovery currently supports Windows and Linux")
    if not isinstance(pid, int) or pid <= 0:
        raise ProbeError("PID must be a positive integer")
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.windll.kernel32
    # PROCESS_QUERY_LIMITED_INFORMATION, not VM_READ/WRITE or DEBUG privileges.
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                  wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ProbeError("Windows process is inaccessible for read-only metadata query")
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        capacity = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
            raise ProbeError("Cannot query Windows executable path")
        return {"pid": pid, "executable": buffer.value, "mapped_files": [],
                "scope": "read-only process path; no DLL injection or memory reads"}
    finally:
        kernel.CloseHandle(handle)
