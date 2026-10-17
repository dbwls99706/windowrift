"""Desktop controller for the SAME live Minecraft entity UUID held in server stasis."""
from __future__ import annotations
import argparse
from io import BytesIO
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QLineEdit, QLabel, QPushButton, QComboBox,
                               QFormLayout, QMessageBox)

from .minecraft_mobs import MinecraftMobs, MOB_TYPES, TransferError
from .minecraft_rcon import RconClient
from .minecraft_cli import parse_location
from .mob_render import render_mob
from .controller import Controls, KeyLatch, Player
from .desktop_world import DesktopWorld
from .desktop_physics import desktop_step
from .geometry import Rect


class WorldMob(QWidget):
    def __init__(self, panel, identity):
        super().__init__(None)
        self.panel, self.identity = panel, identity
        self.frames = []
        self.authentic = False
        for step in range(4):
            image, authentic = render_mob(identity.entity_type, panel.jar, step=step)
            data = BytesIO()
            image.save(data, "PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(data.getvalue(), "PNG")
            self.frames.append(pixmap)
            self.authentic |= authentic
        self.step = 0
        self.setFixedSize(self.frames[0].size())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setToolTip(f"Native Minecraft UUID: {identity.native_uuid}\n"
                        f"HP at capture: {identity.health}\n"
                        "The same living server entity remains in world stasis.")
        self.drag_origin = None
        self.move(identity.screen_x, identity.screen_y)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(180)
        self.show()

    def animate(self):
        self.step = (self.step + 1) % len(self.frames)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.frames[self.step])
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_origin is not None:
            self.move(event.globalPosition().toPoint() - self.drag_origin)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_origin is not None:
            self.drag_origin = None
            self.panel.persist(self)
            self.panel.dragged(self)
            event.accept()


class MobPanel(QWidget):
    def __init__(self, engine: MinecraftMobs, game_jar: Path | None = None,
                 desktop_world: Path | None = None):
        super().__init__()
        self.engine, self.jar = engine, game_jar
        self.actors = {}
        self.world_file = desktop_world or Path.home() / '.local/share/windowrift/desktop-world.json'
        self.world = DesktopWorld.load(self.world_file)
        self.world_stamp = None
        self.keys = KeyLatch()
        self.player = None
        self.play_id = None
        self.last_tick = time.monotonic()
        self.last_saved = self.last_tick
        self.last_world_poll = 0.0
        self.setWindowTitle("WindowRift | Living Minecraft Mobs")
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        title = QLabel("Native Minecraft mob  /  game world → desktop → world")
        title.setStyleSheet("font-size:16px;font-weight:600")
        layout.addWidget(title)
        note = QLabel("Only one explicitly tagged mob. Its original UUID, health and "
                      "native state remain owned by the server. The image is a desktop "
                      "projection; leaving this panel does not release a stashed mob.")
        note.setWordWrap(True)
        layout.addWidget(note)
        gameplay = QLabel("Desktop play: select a transferred mob, press Play, then use A/D or arrows "
                         "to walk, Space/W to jump, Shift to sprint, and S+Space to drop "
                         "through a block. Blocks are shared with the Minecraft Classic "
                         "desktop builder through its saved world file. The live mob remains "
                         "in server stasis until you press Return SAME mob.")
        gameplay.setWordWrap(True)
        layout.addWidget(gameplay)
        form = QFormLayout()
        self.tag = QLineEdit("windowrift_demo")
        form.addRow("In-game entity tag", self.tag)
        self.kind = QComboBox()
        for kind in sorted(MOB_TYPES):
            self.kind.addItem(kind)
        self.kind.setCurrentText("minecraft:zombie")
        form.addRow("Mob type", self.kind)
        self.destination = QLineEdit("20,70,20")
        form.addRow("Return X,Y,Z", self.destination)
        self.selected = QComboBox()
        form.addRow("Tracked native UUID", self.selected)
        layout.addLayout(form)
        controls = QHBoxLayout()
        for name, action in (("Lift real mob", self.take), ("Return SAME mob", self.put),
                             ("Recover pending", self.recover)):
            button = QPushButton(name)
            button.clicked.connect(action)
            controls.addWidget(button)
        layout.addLayout(controls)
        self.play_button = QPushButton("Play selected mob on desktop")
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self.toggle_play)
        layout.addWidget(self.play_button)
        self.status = QLabel("Ready. Operator-owned local Minecraft RCON server only.")
        layout.addWidget(self.status)
        self.setStyleSheet("QWidget{background:#171d23;color:#e4eaf1}"
                           "QLineEdit,QComboBox,QPushButton{padding:8px;background:#303b48;"
                           "border-radius:5px}")
        self.refresh()
        QApplication.instance().installEventFilter(self)
        self.selected.currentIndexChanged.connect(self.selection_changed)
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.tick_desktop)
        self.frame_timer.start(16)

    def selection_changed(self, _index):
        if self.play_id != self.selected.currentData():
            self.play_button.setChecked(False)

    def toggle_play(self, active):
        self.keys.clear()
        self.player = None
        self.play_id = self.selected.currentData() if active else None
        if active:
            actor = self.actors.get(self.play_id)
            if actor is None:
                self.play_button.setChecked(False)
                self.status.setText("Take an actual Minecraft mob outside before desktop play")
                return
            self.player = Player(float(actor.x()), float(actor.y()),
                                 float(actor.width()), float(actor.height()))
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setFocus()
            self.status.setText("Playing the same-UUID mob projection; server AI is paused")
        else:
            self.status.setText("Desktop controls released. The original mob remains recoverable")

    def eventFilter(self, watched, event):
        if (self.play_button.isChecked() and self.isActiveWindow()
                and not isinstance(QApplication.focusWidget(), (QLineEdit, QComboBox))
                and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
                and not event.isAutoRepeat()):
            names = {Qt.Key.Key_A: "a", Qt.Key.Key_D: "d",
                     Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right",
                     Qt.Key.Key_W: "w", Qt.Key.Key_Up: "up",
                     Qt.Key.Key_S: "s", Qt.Key.Key_Down: "down",
                     Qt.Key.Key_Space: "space", Qt.Key.Key_Shift: "shift"}
            name = names.get(event.key())
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

    def dragged(self, actor):
        if self.play_id == actor.identity.id and self.player is not None:
            self.player = Player(float(actor.x()), float(actor.y()),
                                 float(actor.width()), float(actor.height()))

    def tick_desktop(self):
        now = time.monotonic()
        dt = min(0.05, now - self.last_tick)
        self.last_tick = now
        if not self.play_button.isChecked() or self.player is None:
            return
        actor = self.actors.get(self.play_id)
        if actor is None:
            self.play_button.setChecked(False)
            return
        if actor.drag_origin is not None:
            return
        if now - self.last_world_poll >= 0.5:
            self.last_world_poll = now
            try:
                stamp = self.world_file.stat().st_mtime_ns if self.world_file.exists() else None
                if stamp != self.world_stamp:
                    self.world = DesktopWorld.load(self.world_file)
                    self.world_stamp = stamp
            except (OSError, ValueError) as exc:
                self.status.setText("Desktop block world reload failed: " + str(exc))
        screen = QApplication.primaryScreen().virtualGeometry()
        bounds = Rect(screen.x(), screen.y(), screen.width(), screen.height())
        self.player = desktop_step(self.player, self.keys.snapshot(), dt, bounds, self.world)
        actor.move(round(self.player.x), round(self.player.y))
        if now - self.last_saved >= 0.4:
            self.last_saved = now
            self.persist(actor)

    def perform(self, fn):
        try:
            result = fn()
            self.status.setText("Verified native state: " + str(result))
        except (TransferError, OSError, ValueError, RuntimeError) as exc:
            self.status.setText(str(exc))
            QMessageBox.warning(self, "Native entity integrity", str(exc))
        self.refresh()

    def take(self):
        self.perform(lambda: self.engine.take(
            self.tag.text(), self.kind.currentText()).native_uuid)

    def put(self):
        self.perform(lambda: self.engine.put(
            self.selected.currentData(),
            parse_location(self.destination.text())).native_uuid)

    def recover(self):
        self.perform(self.engine.recover)

    def persist(self, actor):
        try:
            self.engine.move_desktop(actor.identity.id, actor.x(), actor.y())
        except (TransferError, ValueError) as exc:
            self.status.setText(str(exc))

    def refresh(self):
        previous = self.selected.currentData()
        self.selected.blockSignals(True)
        self.selected.clear()
        outside = set()
        for record in self.engine.snapshot():
            self.selected.addItem(
                f"{record.entity_type} [{record.phase}] {record.native_uuid[:8]}",
                record.id)
            if record.phase == "outside":
                outside.add(record.id)
                if record.id not in self.actors:
                    self.actors[record.id] = WorldMob(self, record)
        for ident in list(self.actors):
            if ident not in outside:
                self.actors.pop(ident).close()
        if previous:
            index = self.selected.findData(previous)
            if index >= 0:
                self.selected.setCurrentIndex(index)
        self.selected.blockSignals(False)
        if self.play_id not in outside:
            self.play_button.setChecked(False)

    def closeEvent(self, event):
        self.play_button.setChecked(False)
        QApplication.instance().removeEventFilter(self)
        for actor in list(self.actors.values()):
            actor.close()
        self.actors.clear()
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path,
                        default=Path.home() / ".local/share/windowrift/real-mobs.json")
    parser.add_argument("--vault", default="10300,300,10300")
    parser.add_argument("--port", type=int, default=25575)
    parser.add_argument("--game-jar", type=Path)
    parser.add_argument("--desktop-world", type=Path,
                        help="Minecraft Classic desktop blocks JSON, shared across windows")
    args = parser.parse_args()
    secret = os.environ.get("WINDOWRIFT_RCON_PASSWORD")
    if not secret:
        parser.error("Set WINDOWRIFT_RCON_PASSWORD as an environment variable")
    backend = RconClient(secret, port=args.port)
    backend.command("list")
    engine = MinecraftMobs(backend, args.ledger, vault_base=parse_location(args.vault))
    app = QApplication(sys.argv[:1])
    panel = MobPanel(engine, args.game_jar, desktop_world=args.desktop_world)
    panel.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
