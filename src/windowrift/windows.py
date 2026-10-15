"""Visible application-window discovery and activation for Windows and Linux X11."""

from __future__ import annotations

import os
import platform
import re
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


def _x11_windows() -> list[AppWindow]:
    if not os.environ.get("DISPLAY"):
        raise WindowDiscoveryError(
            "No X11 DISPLAY found. WindowRift v0.1 supports Linux X11, not Wayland."
        )
    ids = _command("xdotool", "search", "--onlyvisible", "--name", ".")
    result: list[AppWindow] = []
    for raw in ids.splitlines():
        try:
            wid = int(raw)
        except ValueError:
            continue
        title = _command("xdotool", "getwindowname", str(wid))
        if not title.strip() or title.startswith("WindowRift"):
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
        _command("xdotool", "windowactivate", "--sync", str(window.wid))
