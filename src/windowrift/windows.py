"""Visible application-window discovery and activation for Windows and Linux X11."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass

from .geometry import Rect


class WindowDiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class AppWindow:
    wid: int
    title: str
    bounds: Rect


def _command(*args: str) -> str:
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=4, check=False
        )
    except FileNotFoundError as exc:
        raise WindowDiscoveryError(
            f"Missing system tool '{args[0]}'. On Ubuntu X11 install xdotool."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise WindowDiscoveryError(f"Window query timed out: {args[0]}") from exc
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()



def _is_own_window_title(title: str) -> bool:
    """Ignore only our desktop windows, not pages about WindowRift in Chrome.

    Browser tab titles can start with ``WindowRift`` (e.g. the real Collision
    Lab tab). A blanket prefix check silently hid Chrome from discovery.
    """
    return title.startswith((
        "WindowRift | Control",
        "WindowRift: chrome omnibox actor",
        "WindowRift cinematic native actor",
    ))


def parse_wmctrl_geometry(output: str) -> list[AppWindow]:
    """Parse `wmctrl -lG` with spaces and non-ASCII titles preserved."""
    windows: list[AppWindow] = []
    for line in output.splitlines():
        fields = line.split(None, 7)
        if len(fields) != 8:
            continue
        raw_id, _desktop, raw_x, raw_y, raw_w, raw_h, _host, title = fields
        try:
            wid = int(raw_id, 16)
            rect = Rect(float(raw_x), float(raw_y), float(raw_w), float(raw_h))
        except ValueError:
            continue
        if title and not _is_own_window_title(title) and rect.width >= 100 and rect.height >= 80:
            windows.append(AppWindow(wid, title, rect))
    return windows


def _x11_xwininfo_windows() -> list[AppWindow]:
    """Fallback for minimal X11 environments without working window utilities."""
    listing = _command("xprop", "-root", "_NET_CLIENT_LIST")
    ids = re.findall(r"0x[0-9a-fA-F]+", listing)
    result: list[AppWindow] = []
    for ident in ids:
        stats = _command("xwininfo", "-id", ident, "-stats")
        title_match = re.search(r'^xwininfo: Window id: 0x[0-9a-fA-F]+ "([^"]+)"', stats, re.M)
        if not title_match:
            continue
        title = title_match.group(1)
        if _is_own_window_title(title) or "Map State: IsViewable" not in stats:
            continue
        fields = {}
        for key, pattern in {
            "x": r"Absolute upper-left X:\s*(-?\d+)",
            "y": r"Absolute upper-left Y:\s*(-?\d+)",
            "width": r"Width:\s*(\d+)",
            "height": r"Height:\s*(\d+)",
        }.items():
            found = re.search(pattern, stats)
            if found is None:
                break
            fields[key] = float(found.group(1))
        if len(fields) != 4 or fields["width"] < 100 or fields["height"] < 80:
            continue
        result.append(AppWindow(int(ident, 16), title, Rect(**fields)))
    return result


def _x11_windows() -> list[AppWindow]:
    if not os.environ.get("DISPLAY"):
        raise WindowDiscoveryError("No X11 DISPLAY. WindowRift supports Linux X11, not Wayland.")
    # One wmctrl query is significantly cheaper than one xdotool subprocess
    # for each visible window, and works even when xdotool is not installed.
    if shutil.which("wmctrl"):
        listing = _command("wmctrl", "-lG")
        if listing:
            return parse_wmctrl_geometry(listing)
    if shutil.which("xprop") and shutil.which("xwininfo"):
        windows = _x11_xwininfo_windows()
        if windows:
            return windows
    if not shutil.which("xdotool"):
        raise WindowDiscoveryError("No supported X11 window discovery tool returned visible windows.")
    ids = _command("xdotool", "search", "--onlyvisible", "--name", ".")
    result: list[AppWindow] = []
    for raw in ids.splitlines():
        try:
            wid = int(raw)
        except ValueError:
            continue
        title = _command("xdotool", "getwindowname", str(wid))
        if not title.strip() or _is_own_window_title(title):
            continue
        fields = dict(re.findall(r"^(X|Y|WIDTH|HEIGHT)=(-?\d+)$", _command(
            "xdotool", "getwindowgeometry", "--shell", str(wid)
        ), flags=re.MULTILINE))
        if len(fields) != 4:
            continue
        rect = Rect(float(fields["X"]), float(fields["Y"]),
                    float(fields["WIDTH"]), float(fields["HEIGHT"]))
        if rect.width >= 100 and rect.height >= 80:
            result.append(AppWindow(wid, title, rect))
    return result


def _win32_windows() -> list[AppWindow]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    result: list[AppWindow] = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL

    def visit(hwnd: int, _param: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if not buf.value or buf.value.startswith("WindowRift"):
            return True
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        box = Rect(float(rect.left), float(rect.top),
                   float(rect.right - rect.left), float(rect.bottom - rect.top))
        if box.width >= 100 and box.height >= 80:
            result.append(AppWindow(hwnd, buf.value, box))
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return result


def list_windows() -> list[AppWindow]:
    system = platform.system()
    if system == "Windows":
        return _win32_windows()
    if system == "Linux":
        return _x11_windows()
    raise WindowDiscoveryError(f"Unsupported OS: {system}. Supported: Windows and Linux X11.")


def activate_window(window: AppWindow) -> None:
    if platform.system() == "Windows":
        import ctypes
        ctypes.windll.user32.SetForegroundWindow(window.wid)
    else:
        if shutil.which("xdotool"):
            _command("xdotool", "windowactivate", "--sync", str(window.wid))
        elif shutil.which("wmctrl"):
            _command("wmctrl", "-ia", hex(window.wid))
