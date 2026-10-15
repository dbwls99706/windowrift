"""Independent borderless sprite windows with drag controls."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from .crop_dialog import to_pixmap
from .geometry import ActorState


class Sprite(QWidget):
    removed = Signal(object)

    def __init__(self, picture: Image.Image, x: int, y: int, size: int = 180):
        super().__init__(None)
        pix = to_pixmap(picture)
        self._source = pix
        self.pixmap = pix.scaled(300, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.Tool)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFixedSize(self.pixmap.size())
        self.state = ActorState(float(x), float(y), float(self.width()), float(self.height()))
        self.dragging = False
        self.actor_id = -1
        self.drag_offset = QPoint()
        self.move(x, y)
        self.show()

    def update_picture(self, picture: Image.Image) -> None:
        """Change pixels in place without moving or resizing the desktop actor."""
        self._source = to_pixmap(picture)
        self.pixmap = self._source.scaled(
            self.size(), Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.update()

    def set_actor_height(self, height: int) -> None:
        """Resize the desktop actor from its source image, without cumulative blur."""
        if not 16 <= height <= 512:
            raise ValueError("Actor height must be between 16 and 512 pixels.")
        self.pixmap = self._source.scaled(
            512, height, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setFixedSize(self.pixmap.size())
        self.state.width = float(self.width())
        self.state.height = float(self.height())
        self.update()

    def set_input_passthrough(self, enabled: bool) -> None:
        """Keep the browser address bar clickable while the portal crosses it."""
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, enabled)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, self.pixmap)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            point = event.globalPosition().toPoint() - self.drag_offset
            self.move(point)
            self.state.x, self.state.y = point.x(), point.y()
            self.state.vx = self.state.vy = 0.0
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.state.vy = -70.0
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.removed.emit(self)
            self.close()
            event.accept()
