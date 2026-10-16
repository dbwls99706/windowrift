"""WindowRift control panel and desktop physics runtime."""

from __future__ import annotations

import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace

from PIL import Image
from PySide6.QtCore import QObject, QThreadPool, QTimer, QRunnable, Signal, Qt, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from .bridge import BrowserBridge
from .capture import capture_region, capture_window_with_origin
from .crop_dialog import CropDialog
from .geometry import Rect, ActorState, advance
from .controller import KeyLatch, Player, step, surfaces_for_windows
from .omnibox import OmniboxCalibration, looks_like_chrome
from .choreography import cinematic_pose, scene_duration
from .live import SourceCrop, composite_live_frame, overlaps, tracking_region
from .tracking import locate_object
from .segmentation import extract_object
from .sprites import Sprite
from .windows import AppWindow, WindowDiscoveryError, activate_window, list_windows


class ExtractionSignals(QObject):
    success = Signal(object)
    failure = Signal(str)


class ExtractionJob(QRunnable):
    def __init__(self, image: Image.Image, mode: str, *, trim: bool = True):
        super().__init__()
        self.image = image
        self.mode = mode
        self.trim = trim
        self.signals = ExtractionSignals()

    def run(self):
        try:
            result = extract_object(self.image, self.mode, trim=self.trim)
        except Exception as exc:
            self.signals.failure.emit(str(exc))
        else:
            self.signals.success.emit(result)


@dataclass
class LiveBinding:
    sprite: Sprite
    crop: SourceCrop
    matte: Image.Image
    tracking: bool


@dataclass
class BrowserDock:
    sprite: Sprite
    target_id: int
    started_at: float
    source_position: tuple[float, float]
    original_height: int


class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WindowRift | Control")
        self.setMinimumWidth(470)
        self.setObjectName("panel")
        self.windows: list[AppWindow] = []
        self.sprites: list[Sprite] = []
        self._next_actor_id = 1
        self._live_sources: dict[int, LiveBinding] = {}
        self._browser_docks: dict[int, BrowserDock] = {}
        self._play_id: int | None = None
        self._player: Player | None = None
        self._keys = KeyLatch()
        self._omnibox = OmniboxCalibration()
        self._live_executor = ThreadPoolExecutor(max_workers=1)
        self._live_future: Future[tuple[int, Image.Image | None, SourceCrop | None]] | None = None
        self._last_live = 0.0
        self._live_cursor = 0
        self.jobs: list[ExtractionJob] = []
        self.pool = QThreadPool.globalInstance()
        self.selected: AppWindow | None = None
        self.paused = False
        self.bridge = BrowserBridge()
        self.bridge.start()
        self._last = time.monotonic()
        self._last_windows = 0.0
        self._last_broadcast = 0.0
        self._platforms: list[Rect] = []
        self._known_windows: dict[int, AppWindow] = {}
        self._window_executor = ThreadPoolExecutor(max_workers=1)
        self._platform_future = None

        root = QVBoxLayout(self)
        root.setSpacing(13)
        title = QLabel("WindowRift")
        title.setObjectName("title")
        root.addWidget(title)
        tagline = QLabel("Pull an object out of a live application window.")
        tagline.setObjectName("muted")
        root.addWidget(tagline)

        root.addWidget(QLabel("1. Source window"))
        row = QHBoxLayout()
        self.targets = QComboBox()
        self.targets.setMinimumWidth(335)
        row.addWidget(self.targets, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_windows)
        row.addWidget(refresh)
        root.addLayout(row)

        root.addWidget(QLabel("2. Foreground extraction"))
        self.method = QComboBox()
        self.method.addItem("Fast local GrabCut (CPU)", "grabcut")
        self.method.addItem("Pixel art / flat background color key", "color-key")
        self.method.addItem("AI foreground removal (rembg, optional)", "ai")
        self.method.addItem("Rectangle only (debug)", "crop")
        root.addWidget(self.method)
        self.live_mode = QCheckBox("Live pixels: refresh the captured object while its source is visible")
        self.live_mode.setChecked(False)
        root.addWidget(self.live_mode)
        self.track_motion = QCheckBox("Track motion in source (experimental, ±72 px per sample)")
        self.track_motion.setEnabled(False)
        self.live_mode.toggled.connect(self.track_motion.setEnabled)
        root.addWidget(self.track_motion)
        live_note = QLabel(
            "Live pixels reuses the selected alpha mask. Tracking searches nearby visible "
            "pixels; it does not read or change the original program state."
        )
        live_note.setWordWrap(True)
        live_note.setObjectName("muted")
        root.addWidget(live_note)
        self.extract_button = QPushButton("Capture window → select object → release")
        self.extract_button.setObjectName("primary")
        self.extract_button.clicked.connect(self.extract_from_target)
        root.addWidget(self.extract_button)

        row2 = QHBoxLayout()
        self.control_button = QPushButton("Take control of latest actor")
        self.control_button.setObjectName("primary")
        self.control_button.clicked.connect(self.toggle_control)
        root.addWidget(self.control_button)
        hint = QLabel("PLAY: A/D or arrows move · Space/W jump · Shift sprint · S+Space drop · Esc release")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.pause_button = QPushButton("Pause physics")
        self.pause_button.clicked.connect(self.toggle_pause)
        clear_button = QPushButton("Remove all objects")
        clear_button.clicked.connect(self.clear_sprites)
        row2.addWidget(self.pause_button)
        row2.addWidget(clear_button)
        root.addLayout(row2)

        root.addWidget(QLabel("3. Chrome address bar (visual portal)"))
        browser_row = QHBoxLayout()
        self.chrome_targets = QComboBox()
        self.chrome_targets.setMinimumWidth(320)
        browser_row.addWidget(self.chrome_targets, 1)
        dock_button = QPushButton("Jump out → Chrome → impact → return")
        dock_button.clicked.connect(self.dock_in_chrome)
        browser_row.addWidget(dock_button)
        root.addLayout(browser_row)
        release_button = QPushButton("Release from Chrome")
        release_button.clicked.connect(self.release_from_chrome)
        root.addWidget(release_button)
        note = QLabel(
            "The extracted sprite makes a timed leap into Chrome, rebounds into the "
            "page and returns. This is an OS overlay, not a browser UI modification. "
            "Keep browser zoom and display scaling near 100%."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        root.addWidget(note)

        root.addWidget(QLabel("4. Browser DOM bridge (optional)"))
        description = QLabel(
            "Install browser-extension/ in Chrome, copy this session token into the "
            "extension popup, and enable the chosen tab."
        )
        description.setWordWrap(True)
        description.setObjectName("muted")
        root.addWidget(description)
        row3 = QHBoxLayout()
        self.token_label = QLabel(self.bridge.token[:11] + "…")
        self.token_label.setToolTip("A new token is generated on every run.")
        copy_button = QPushButton("Copy session token")
        copy_button.clicked.connect(self.copy_token)
        row3.addWidget(self.token_label, 1)
        row3.addWidget(copy_button)
        root.addLayout(row3)
        self.status = QLabel("Select a visible window. Drag sprites to move them; right double-click removes one.")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        root.addWidget(self.status)
        if self.bridge.error:
            self.status.setText(f"Browser bridge unavailable: {self.bridge.error}")

        self.setStyleSheet("""
            QWidget#panel { background: #121824; color: #e8f0fa; }
            QLabel { color: #e8f0fa; font-size: 12px; }
            QLabel#title { font-size: 29px; font-weight: bold; color: #75e4e5; }
            QLabel#muted { color: #98acc2; font-size: 11px; }
            QPushButton, QComboBox { background: #263347; border: 1px solid #40536c;
                border-radius: 6px; padding: 9px; color: #f5faff; }
            QPushButton:hover { border-color: #75e4e5; }
            QPushButton#primary { background: #159da5; color: #ffffff; font-weight: bold; }
        """)
        self.refresh_windows()
        QApplication.instance().installEventFilter(self)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def refresh_windows(self):
        current = self.targets.currentData()
        try:
            self.windows = list_windows()
        except WindowDiscoveryError as exc:
            self.windows = []
            self.status.setText(str(exc))
        self.targets.clear()
        for win in self.windows:
            text = f"{win.title[:66]}  [{int(win.bounds.width)}x{int(win.bounds.height)}]"
            self.targets.addItem(text, win.wid)
        if current is not None:
            idx = self.targets.findData(current)
            if idx >= 0:
                self.targets.setCurrentIndex(idx)
        self._platforms = [w.bounds for w in self.windows]
        self._known_windows = {w.wid: w for w in self.windows}
        selected_chrome = self.chrome_targets.currentData()
        self.chrome_targets.clear()
        for win in self.windows:
            if looks_like_chrome(win):
                self.chrome_targets.addItem(win.title[:75], win.wid)
        if selected_chrome is not None:
            index = self.chrome_targets.findData(selected_chrome)
            if index >= 0:
                self.chrome_targets.setCurrentIndex(index)

    def extract_from_target(self):
        target = next((w for w in self.windows if w.wid == self.targets.currentData()), None)
        if target is None:
            QMessageBox.warning(self, "No source", "Select a visible application window first.")
            return
        self.selected = target
        self.extract_button.setEnabled(False)
        self.status.setText("Switching to target window to capture visible pixels…")
        self.hide()
        try:
            activate_window(target)
        except Exception:
            pass
        QTimer.singleShot(500, self._finish_capture)

    def _finish_capture(self):
        target = self.selected
        if target is None:
            self.show()
            self.extract_button.setEnabled(True)
            return
        try:
            shot = capture_window_with_origin(target)
        except Exception as exc:
            self.show()
            self.extract_button.setEnabled(True)
            QMessageBox.critical(self, "Capture failed", str(exc))
            return
        self.show()
        dialog = CropDialog(shot.image, self)
        if dialog.exec() != CropDialog.DialogCode.Accepted:
            self.extract_button.setEnabled(True)
            self.status.setText("Selection cancelled.")
            return
        cropped, (dx, dy) = dialog.cropped()
        origin = (shot.x + dx, shot.y + dy)
        mode = self.method.currentData()
        live = self.live_mode.isChecked()
        crop = SourceCrop(
            target.wid,
            origin[0] - round(target.bounds.x),
            origin[1] - round(target.bounds.y),
            cropped.width,
            cropped.height,
        )
        if live and not crop.affordable:
            self.extract_button.setEnabled(True)
            self.status.setText("Live pixels requires a selection no larger than 512×512 pixels.")
            return
        self.status.setText(f"Extracting {cropped.width}×{cropped.height} object with {mode}…")
        job = ExtractionJob(cropped, mode, trim=not live)
        self.jobs.append(job)
        job.signals.success.connect(
            lambda image, j=job, p=origin, c=crop if live else None, t=self.track_motion.isChecked(): self._extracted(j, image, p, c, t)
        )
        job.signals.failure.connect(lambda error, j=job: self._extract_failed(j, error))
        self.pool.start(job)

    def _extracted(
        self,
        job: ExtractionJob,
        image: Image.Image,
        position: tuple[int, int],
        crop: SourceCrop | None,
        tracking: bool = False,
    ):
        if job in self.jobs:
            self.jobs.remove(job)
        # Prevent an enormous captured object from hiding the whole desktop.
        size = min(230, image.height)
        sprite = Sprite(image, position[0], position[1], size=max(32, size))
        sprite.actor_id = self._next_actor_id
        self._next_actor_id += 1
        sprite.removed.connect(self.remove_sprite)
        self.sprites.append(sprite)
        if crop is not None:
            self._live_sources[sprite.actor_id] = LiveBinding(sprite, crop, image.copy(), tracking)
        self.extract_button.setEnabled(True)
        state = "Live tracking enabled" if crop is not None and tracking else ("Live pixels enabled" if crop is not None else "Static sprite")
        self.status.setText(f"Released object #{sprite.actor_id}. {state}; drag it across windows.")

    def _extract_failed(self, job: ExtractionJob, error: str):
        if job in self.jobs:
            self.jobs.remove(job)
        self.extract_button.setEnabled(True)
        self.status.setText("Object extraction failed.")
        QMessageBox.warning(self, "Extraction failed", error)

    def copy_token(self):
        QGuiApplication.clipboard().setText(self.bridge.token)
        self.status.setText("Session token copied. Paste it into the Chrome extension popup.")

    def dock_in_chrome(self) -> None:
        """Fly the latest actor into Chrome's actual toolbar as a visual overlay."""
        if not self.sprites:
            self.status.setText("Extract an object from a running game first.")
            return
        target_id = self.chrome_targets.currentData()
        target = self._known_windows.get(target_id)
        if target is None or not looks_like_chrome(target):
            self.status.setText("Select a visible Chrome or Chromium window and refresh.")
            return
        try:
            self._omnibox.anchor(target)
        except ValueError as error:
            self.status.setText(str(error))
            return
        sprite = self.sprites[-1]
        if self._play_id is not None:
            self.stop_control()
        if sprite.actor_id in self._browser_docks:
            self.release_from_chrome()
        original_height = sprite.height()
        source_position = (sprite.state.x, sprite.state.y)
        sprite.set_actor_height(58)
        sprite.set_input_passthrough(True)
        self._browser_docks[sprite.actor_id] = BrowserDock(
            sprite, target.wid, time.monotonic(), source_position, original_height,
        )
        self.status.setText(
            "Actor launched: jump → address bar → webpage impact → return. "
            "This is a native overlay, not an in-game object transfer."
        )

    def release_from_chrome(self) -> None:
        """Restore ordinary desktop physics without stealing Chrome's input."""
        for dock in tuple(self._browser_docks.values()):
            sprite = dock.sprite
            self._browser_docks.pop(sprite.actor_id, None)
            sprite.set_input_passthrough(False)
            sprite.set_visual_pose(0.0, 1.0)
            sprite.set_actor_height(min(512, max(16, dock.original_height)))
            sprite.state.vx = 80.0
            sprite.state.vy = 40.0
        self.status.setText("Released browser actors back to desktop physics.")

    def toggle_control(self) -> None:
        """Direct keyboard control, with a visible opt-in and no global hook."""
        if self._play_id is not None:
            self.stop_control()
            return
        if not self.sprites:
            self.status.setText("Capture a character first.")
            return
        if self._browser_docks:
            self.release_from_chrome()
        sprite = self.sprites[-1]
        target = self._known_windows.get(self.selected.wid) if self.selected else None
        x, y, ground = sprite.state.x, sprite.state.y, None
        if target is not None:
            x = max(target.bounds.x + 4, min(x, target.bounds.right - sprite.width() - 4))
            y = target.bounds.y - sprite.height()
            ground = f"window:{target.wid}"
        self._play_id = sprite.actor_id
        self._player = Player(x,y,float(sprite.width()),float(sprite.height()),ground=ground)
        self._keys.clear()
        self.paused = False
        self.pause_button.setText("Pause physics")
        sprite.set_input_passthrough(True)
        sprite.state = ActorState(x,y,float(sprite.width()),float(sprite.height()),0,0)
        sprite.move(round(x),round(y))
        self.control_button.setText("Stop playing (Esc)")
        self.status.setText("Controls active. Focus this panel: A/D walk, Space jump, Shift run, S+Space drop, Esc exit.")
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def stop_control(self) -> None:
        if self._play_id is None:
            return
        for sprite in self.sprites:
            if sprite.actor_id == self._play_id:
                sprite.set_input_passthrough(False)
                sprite.set_visual_pose(0.0, 1.0)
                sprite.state.vx = sprite.state.vy = 0
        self._play_id = None
        self._player = None
        self._keys.clear()
        self.control_button.setText("Take control of latest actor")
        self.status.setText("Play mode off. Normal desktop input restored.")

    def eventFilter(self, watched, event):
        if self._play_id is not None:
            typ = event.type()
            if typ in (QEvent.Type.KeyPress,QEvent.Type.KeyRelease):
                mapping = {
                    Qt.Key.Key_A: "a", Qt.Key.Key_Left: "left", Qt.Key.Key_D: "d",
                    Qt.Key.Key_Right: "right", Qt.Key.Key_S: "s", Qt.Key.Key_Down: "down",
                    Qt.Key.Key_Space: "space", Qt.Key.Key_W: "w", Qt.Key.Key_Up: "up",
                    Qt.Key.Key_Shift: "shift",
                }
                if typ == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                    self.stop_control()
                    return True
                name = mapping.get(event.key())
                if name is not None:
                    if not event.isAutoRepeat():
                        if typ == QEvent.Type.KeyPress:self._keys.press(name)
                        else:self._keys.release(name)
                    return True
            if typ == QEvent.Type.WindowDeactivate:self._keys.clear()
        return super().eventFilter(watched,event)

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.setText("Resume physics" if self.paused else "Pause physics")

    def remove_sprite(self, sprite: Sprite):
        if sprite.actor_id == self._play_id:
            self.stop_control()
        self._browser_docks.pop(sprite.actor_id, None)
        self._live_sources.pop(sprite.actor_id, None)
        if sprite in self.sprites:
            self.sprites.remove(sprite)
        sprite.close()

    def clear_sprites(self):
        for sprite in tuple(self.sprites):
            self.remove_sprite(sprite)
        self.status.setText("Removed all extracted objects.")

    def _desktop(self) -> Rect:
        screens = QGuiApplication.screens()
        x0 = min(s.geometry().left() for s in screens)
        y0 = min(s.geometry().top() for s in screens)
        x1 = max(s.geometry().right() + 1 for s in screens)
        y1 = max(s.geometry().bottom() + 1 for s in screens)
        return Rect(float(x0), float(y0), float(x1 - x0), float(y1 - y0))

    def tick(self):
        now = time.monotonic()
        dt = min(0.05, now - self._last)
        self._last = now
        if not self.sprites:
            return
        if self._platform_future is not None and self._platform_future.done():
            try:
                windows = self._platform_future.result()
                self._platforms = [w.bounds for w in windows]
                self._known_windows = {w.wid: w for w in windows}
            except Exception:
                self._platforms = []
            self._platform_future = None
        if now - self._last_windows > 1.0 and self._platform_future is None:
            self._last_windows = now
            self._platform_future = self._window_executor.submit(list_windows)
        self._update_live(now)
        if not self.paused:
            desktop = self._desktop()
            for sprite in self.sprites:
                dock = self._browser_docks.get(sprite.actor_id)
                if dock is not None:
                    browser = self._known_windows.get(dock.target_id)
                    if browser is not None:
                        try:
                            destination = self._omnibox.anchor(browser)
                            elapsed = now - dock.started_at
                            if elapsed >= scene_duration():
                                self._browser_docks.pop(sprite.actor_id, None)
                                sprite.set_visual_pose(0.0, 1.0)
                                sprite.set_input_passthrough(False)
                                sprite.set_actor_height(dock.original_height)
                                sprite.state.x, sprite.state.y = dock.source_position
                                sprite.move(round(sprite.state.x), round(sprite.state.y))
                                sprite.state.vx, sprite.state.vy = 60.0, -80.0
                                continue
                            pose = cinematic_pose(
                                dock.source_position, destination, browser.bounds,
                                (sprite.width(), sprite.height()), elapsed,
                            )
                            x, y = pose.x, pose.y
                            sprite.set_visual_pose(pose.tilt, pose.squash)
                        except ValueError:
                            continue
                        sprite.state.x, sprite.state.y = float(x), float(y)
                        sprite.move(x, y)
                    continue
                if sprite.actor_id == self._play_id and self._player is not None:
                    self._player = replace(self._player,width=float(sprite.width()),height=float(sprite.height()))
                    self._player = step(self._player,self._keys.snapshot(),dt,desktop,
                                        surfaces_for_windows(list(self._known_windows.values())))
                    sprite.state = ActorState(self._player.x,self._player.y,
                                              self._player.width,self._player.height,
                                              self._player.vx,self._player.vy)
                    sprite.set_visual_pose(max(-8,min(8,self._player.vx*.018)),1.)
                    sprite.move(round(self._player.x),round(self._player.y))
                    continue
                if sprite.dragging:
                    continue
                sprite.state = advance(sprite.state, dt, desktop, self._platforms)
                sprite.move(round(sprite.state.x), round(sprite.state.y))
        if now - self._last_broadcast > 0.09:
            self._last_broadcast = now
            self.bridge.publish_actors([
                {"id": sprite.actor_id, "x": round(sprite.state.x), "y": round(sprite.state.y),
                 "width": sprite.width(), "height": sprite.height()}
                for sprite in self.sprites
            ])

    def _update_live(self, now: float) -> None:
        """Sample visible pixels off the GUI thread, optionally following an object."""
        future = self._live_future
        if future is not None:
            if not future.done():
                return
            self._live_future = None
            try:
                actor_id, frame, new_crop = future.result()
            except Exception:
                pass  # Keep the last frame when the source is unavailable.
            else:
                binding = self._live_sources.get(actor_id)
                if binding is not None and frame is not None:
                    binding.sprite.update_picture(frame)
                    if new_crop is not None:
                        binding.crop = new_crop
        if now - self._last_live < 0.125 or not self._live_sources:
            return
        self._last_live = now
        entries = list(self._live_sources.items())
        for step in range(len(entries)):
            index = (self._live_cursor + step) % len(entries)
            actor_id, binding = entries[index]
            window = self._known_windows.get(binding.crop.window_id)
            if window is None:
                continue
            try:
                region = tracking_region(binding.crop, window) if binding.tracking else binding.crop.bounds(window)
            except ValueError:
                continue
            # Live capture samples visible screen pixels, not process memory.
            # Our own actors/panel must not be painted into their source sample.
            if any(overlaps(region, obj.state.bounds) for obj in self.sprites):
                continue
            if self.isVisible() and overlaps(region, Rect(
                float(self.frameGeometry().x()), float(self.frameGeometry().y()),
                float(self.frameGeometry().width()), float(self.frameGeometry().height()),
            )):
                continue
            self._live_cursor = (index + 1) % len(entries)
            self._live_future = self._live_executor.submit(
                self._sample_live, actor_id, region, binding.crop,
                binding.matte, binding.tracking, window,
            )
            return

    @staticmethod
    def _sample_live(
        actor_id: int,
        region: Rect,
        crop: SourceCrop,
        matte: Image.Image,
        tracking: bool,
        window: AppWindow,
    ) -> tuple[int, Image.Image | None, SourceCrop | None]:
        shot = capture_region(region, exact=True)
        if not tracking:
            return actor_id, composite_live_frame(shot.image, matte), None
        found = locate_object(shot.image, matte)
        if found is None:
            return actor_id, None, None
        new_crop = SourceCrop(
            crop.window_id,
            round(region.x + found.x - window.bounds.x),
            round(region.y + found.y - window.bounds.y),
            crop.width, crop.height,
        )
        # The search region was bounded to the same original window.
        new_crop.bounds(window)
        frame = shot.image.crop((found.x, found.y, found.x + crop.width, found.y + crop.height))
        return actor_id, composite_live_frame(frame, matte), new_crop

    def closeEvent(self, event):
        self.stop_control()
        QApplication.instance().removeEventFilter(self)
        self.timer.stop()
        self.clear_sprites()
        self.bridge.stop()
        self._window_executor.shutdown(wait=False, cancel_futures=True)
        self._live_executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def main() -> None:
    if sys.platform == "linux":
        import os
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            print("WindowRift v0.1 requires an X11 session. Log into Ubuntu on Xorg.", file=sys.stderr)
            raise SystemExit(2)
    app = QApplication(sys.argv)
    app.setApplicationName("WindowRift")
    panel = ControlPanel()
    panel.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
