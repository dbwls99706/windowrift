"""Keyboard-controlled DOOM sprite beyond its *real* X11 game window.

Uses an authentic picture patch from an operator-supplied shareware IWAD;
the original Chocolate Doom process is neither injected nor modified.
The represented Imp is NOT the same living DOOM entity.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

from PIL import Image, ImageGrab
from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from .controller import KeyLatch, Player
from .desktop_physics import desktop_step
from .desktop_world import DesktopWorld
from .doom_wad import WadError, doom_patch_sprite
from .geometry import Rect
from .proof_capture import ProofRecorder
from .windows import list_windows


class DoomSprite(QWidget):
    def __init__(self, frames, start):
        super().__init__()
        self.frames = []
        for frame in frames:
            height = 92
            width = max(12, round(frame.width * height / frame.height))
            frame = frame.resize((width, height), Image.Resampling.NEAREST)
            from io import BytesIO
            memory = BytesIO()
            frame.save(memory, format="PNG")
            pixmap = QPixmap()
            if not pixmap.loadFromData(memory.getvalue(), "PNG"):
                raise RuntimeError("Could not load original DOOM sprite")
            self.frames.append(pixmap)
        width = max(f.width() for f in self.frames)
        self.setFixedSize(width, 92)
        self.index = 0
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.Tool |
                            Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.move(round(start[0]), round(start[1]))
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        pix = self.frames[self.index]
        painter.drawPixmap((self.width() - pix.width()) // 2, 0, pix)
        painter.end()


class DoomDesktop(QWidget):
    def __init__(self, wad: Path, world_file: Path, *, record: Path | None = None):
        super().__init__()
        if not os.environ.get("DISPLAY"):
            raise RuntimeError("This native demo requires a Linux X11 display")
        games = [w for w in list_windows()
                 if "doom" in w.title.casefold() and "windowrift" not in w.title.casefold()]
        if not games:
            raise RuntimeError("Launch the real Chocolate Doom window first")
        game = games[0]
        frames = []
        for lump in ("TROOA1", "TROOB1", "TROOC1", "TROOD1"):
            try:
                frames.append(doom_patch_sprite(wad, lump))
            except WadError:
                continue
        if not frames:
            raise WadError("Original IWAD has no supported Doom Imp frames")
        self.actor = DoomSprite(frames, (game.bounds.x + game.bounds.width - 90,
                                        game.bounds.y + game.bounds.height - 150))
        self.player = Player(float(self.actor.x()), float(self.actor.y()),
                             float(self.actor.width()), float(self.actor.height()))
        self.keys = KeyLatch()
        self.world_file = world_file
        self.world = DesktopWorld.load(world_file)
        self.world_stamp = None
        self.last_poll = 0.0
        self.last_time = time.monotonic()
        self.frame_count = 0
        self.recorder = ProofRecorder(interval=0.15, max_frames=50) if record else None
        self.record_path = record
        self.started = self.last_time
        self.record_elapsed = 0.
        self.setWindowTitle("WindowRift | DOOM desktop play")
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)
        heading = QLabel("DOOM Imp → outside the game window")
        heading.setStyleSheet("font-size:19px;font-weight:bold")
        layout.addWidget(heading)
        explanation = QLabel(
            "A/D or arrows: move  |  W/Space: jump  |  Shift: sprint  | "
            "S+Space: drop through a block. The sprite is extracted from your "
            "own WAD and rendered above unrelated application windows. "
            "It has desktop collision and is keyboard-controlled, but it is "
            "NOT the original game enemy or its native AI.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.play_button = QPushButton("Play on desktop")
        self.play_button.setCheckable(True)
        self.play_button.setChecked(True)
        self.play_button.toggled.connect(self.toggle)
        layout.addWidget(self.play_button)
        self.status = QLabel("Click this control window, then use the keyboard.")
        layout.addWidget(self.status)
        self.setStyleSheet("QWidget{background:#1c1b20;color:#f8eee4}"
                           "QPushButton{background:#493437;padding:10px}")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.move(850, 585)
        self.show()
        self.setFocus()
        QApplication.instance().installEventFilter(self)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.record_timer = None
        if record:
            # Deterministic user-input replay, NOT a prerecorded animation path.
            # It sends the same key events as an actual user and records X11.
            from PySide6.QtTest import QTest
            self.record_timer = QTimer(self)
            self.record_timer.setInterval(800)
            self.sequence = 0
            self.record_timer.timeout.connect(lambda: self.replay(QTest))
            self.record_timer.start()
            self.replay(QTest)

    def toggle(self, enabled):
        self.keys.clear()
        if enabled:
            self.setFocus()

    def eventFilter(self, watched, event):
        if (self.play_button.isChecked() and self.isActiveWindow()
                and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
                and not event.isAutoRepeat()):
            key_map = {Qt.Key.Key_A:"a", Qt.Key.Key_D:"d",
                       Qt.Key.Key_Left:"left", Qt.Key.Key_Right:"right",
                       Qt.Key.Key_W:"w", Qt.Key.Key_Up:"up",
                       Qt.Key.Key_Space:"space", Qt.Key.Key_S:"s",
                       Qt.Key.Key_Down:"down", Qt.Key.Key_Shift:"shift"}
            name = key_map.get(event.key())
            if name:
                if event.type() == QEvent.Type.KeyPress:
                    self.keys.press(name)
                else:
                    self.keys.release(name)
                return True
            if event.key() == Qt.Key.Key_Escape and event.type() == QEvent.Type.KeyPress:
                self.play_button.setChecked(False)
                return True
        return super().eventFilter(watched, event)

    def replay(self, QTest):
        """Automated demo drives the actual Qt event input path."""
        if self.sequence == 0:
            self.activateWindow()
            self.setFocus()
            QTest.keyPress(self, Qt.Key.Key_D)
        elif self.sequence == 1:
            QTest.keyPress(self, Qt.Key.Key_Space)
        elif self.sequence == 2:
            QTest.keyRelease(self, Qt.Key.Key_Space)
        elif self.sequence == 3:
            QTest.keyRelease(self, Qt.Key.Key_D)
            QTest.keyPress(self, Qt.Key.Key_A)
        elif self.sequence == 4:
            QTest.keyRelease(self, Qt.Key.Key_A)
        elif self.sequence == 5:
            self.close()
        self.sequence += 1

    def tick(self):
        now = time.monotonic()
        dt = min(.05, now - self.last_time)
        self.last_time = now
        if now - self.last_poll > .6:
            self.last_poll = now
            try:
                stamp = self.world_file.stat().st_mtime_ns if self.world_file.exists() else None
                if stamp != self.world_stamp:
                    self.world = DesktopWorld.load(self.world_file)
                    self.world_stamp = stamp
            except (OSError, ValueError) as exc:
                self.status.setText("Cannot reload desktop blocks: " + str(exc))
        if self.play_button.isChecked():
            rect = QApplication.primaryScreen().virtualGeometry()
            bounds = Rect(rect.x(), rect.y(), rect.width(), rect.height())
            self.player = desktop_step(self.player, self.keys.snapshot(), dt, bounds, self.world)
            self.actor.move(round(self.player.x), round(self.player.y))
            self.frame_count += 1
            if self.frame_count % 10 == 0:
                self.actor.index = (self.actor.index + 1) % len(self.actor.frames)
                self.actor.update()
        if self.recorder is not None:
            self.recorder.add_frame(now - self.started,
                                    ImageGrab.grab(xdisplay=os.environ["DISPLAY"]))

    def closeEvent(self, event):
        self.timer.stop()
        if self.record_timer:
            self.record_timer.stop()
        if self.recorder is not None and self.recorder.frames:
            count = self.recorder.save(self.record_path)
            print(f"ACTUAL_DOOM_KEYBOARD_GIF={self.record_path};frames={count}", flush=True)
        self.actor.close()
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doom-wad", required=True, type=Path,
                        help="Path to your legally acquired DOOM shareware IWAD")
    parser.add_argument("--desktop-world", type=Path,
                        default=Path.home() / ".local/share/windowrift/desktop-world.json")
    parser.add_argument("--record-gif", type=Path,
                        help="Record a short actual-X11 keyboard-input playback demo")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    try:
        panel = DoomDesktop(args.doom_wad, args.desktop_world, record=args.record_gif)
    except (RuntimeError, WadError, OSError, ValueError) as exc:
        parser.error(str(exc))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
