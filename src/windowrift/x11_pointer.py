"""Explicit X11 build-mode pointer grab for native, site-independent placement.

This is opt-in and local to the user's X session.  While a grab is active web
pages cannot accidentally receive placement clicks. Releasing build mode or
closing the tool restores ordinary pointer behavior immediately.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os

BUTTON_PRESS = 4
BUTTON_RELEASE = 5
MOTION_NOTIFY = 6
GRAB_SUCCESS = 0


class XButtonEvent(ctypes.Structure):
    _fields_ = [
        ('type', ctypes.c_int), ('serial', ctypes.c_ulong),
        ('send_event', ctypes.c_int), ('display', ctypes.c_void_p),
        ('window', ctypes.c_ulong), ('root', ctypes.c_ulong),
        ('subwindow', ctypes.c_ulong), ('time', ctypes.c_ulong),
        ('x', ctypes.c_int), ('y', ctypes.c_int),
        ('x_root', ctypes.c_int), ('y_root', ctypes.c_int),
        ('state', ctypes.c_uint), ('button', ctypes.c_uint),
        ('same_screen', ctypes.c_int),
    ]


class PointerGrab:
    """Separate Xlib connection; Tk keeps its regular GUI connection."""
    def __init__(self):
        if not os.environ.get('DISPLAY'):
            raise RuntimeError('X11 DISPLAY required; Wayland pointer grabs are unsupported')
        self.lib = ctypes.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
        lib = self.lib
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XGrabPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                     ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        lib.XGrabPointer.restype = ctypes.c_int
        lib.XUngrabPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XPending.argtypes = [ctypes.c_void_p]
        lib.XPending.restype = ctypes.c_int
        lib.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.XFlush.argtypes = [ctypes.c_void_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.display = lib.XOpenDisplay(os.environ['DISPLAY'].encode())
        if not self.display:
            raise RuntimeError('Failed to open X11 pointer display')
        self.root = lib.XDefaultRootWindow(self.display)
        self.active = False

    def start(self):
        if self.active:
            return
        mask = (1 << 2) | (1 << 3) | (1 << 6)  # buttons and motion
        result = self.lib.XGrabPointer(self.display, self.root, 0, mask,
                                       1, 1, 0, 0, 0)
        if result != GRAB_SUCCESS:
            raise RuntimeError(f'Cannot capture desktop pointer (XGrabPointer result {result})')
        self.active = True
        self.lib.XFlush(self.display)

    def poll(self, limit: int = 128) -> list[tuple[int, int, int, int]]:
        events = []
        if not self.active:
            return events
        for _ in range(limit):
            if not self.lib.XPending(self.display):
                break
            buffer = ctypes.create_string_buffer(192)  # XEvent union: 24 native longs
            self.lib.XNextEvent(self.display, buffer)
            event = ctypes.cast(buffer, ctypes.POINTER(XButtonEvent)).contents
            if event.type in (BUTTON_PRESS, BUTTON_RELEASE, MOTION_NOTIFY):
                events.append((event.type, event.x_root, event.y_root, event.button))
        return events

    def stop(self):
        if self.active:
            self.lib.XUngrabPointer(self.display, 0)
            self.lib.XFlush(self.display)
            self.active = False

    def close(self):
        self.stop()
        if self.display:
            self.lib.XCloseDisplay(self.display)
            self.display = None
