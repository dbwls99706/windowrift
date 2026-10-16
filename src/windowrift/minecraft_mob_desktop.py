"""Desktop controller for the SAME live Minecraft entity UUID held in server stasis."""
from __future__ import annotations
import argparse
from io import BytesIO
import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QLineEdit, QLabel, QPushButton, QComboBox,
                               QFormLayout, QMessageBox)

from .minecraft_mobs import MinecraftMobs, MOB_TYPES, TransferError
from .minecraft_rcon import RconClient
from .minecraft_cli import parse_location
from .mob_render import render_mob


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
            event.accept()


class MobPanel(QWidget):
    def __init__(self, engine: MinecraftMobs, game_jar: Path | None = None):
        super().__init__()
        self.engine, self.jar = engine, game_jar
        self.actors = {}
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
        self.status = QLabel("Ready. Operator-owned local Minecraft RCON server only.")
        layout.addWidget(self.status)
        self.setStyleSheet("QWidget{background:#171d23;color:#e4eaf1}"
                           "QLineEdit,QComboBox,QPushButton{padding:8px;background:#303b48;"
                           "border-radius:5px}")
        self.refresh()

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

    def closeEvent(self, event):
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
    args = parser.parse_args()
    secret = os.environ.get("WINDOWRIFT_RCON_PASSWORD")
    if not secret:
        parser.error("Set WINDOWRIFT_RCON_PASSWORD as an environment variable")
    backend = RconClient(secret, port=args.port)
    backend.command("list")
    engine = MinecraftMobs(backend, args.ledger, vault_base=parse_location(args.vault))
    app = QApplication(sys.argv[:1])
    panel = MobPanel(engine, args.game_jar)
    panel.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
