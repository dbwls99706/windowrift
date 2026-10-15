"""Screenshot preview with an exact pixel-coordinate rectangle selector."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget


def to_pixmap(pil_image: Image.Image) -> QPixmap:
    rgba = pil_image.convert("RGBA")
    raw = rgba.tobytes()
    qimage = QImage(raw, rgba.width, rgba.height,
                    rgba.width * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage)


class CropCanvas(QWidget):
    def __init__(self, image: Image.Image):
        super().__init__()
        self.original = image
        self.pixmap = to_pixmap(image)
        self.setMinimumSize(580, 350)
        self.a: QPoint | None = None
        self.b: QPoint | None = None

    def image_rect(self) -> QRect:
        scale = min(self.width() / self.pixmap.width(),
                    self.height() / self.pixmap.height())
        w = max(1, round(self.pixmap.width() * scale))
        h = max(1, round(self.pixmap.height() * scale))
        return QRect((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def _screen_to_image(self, point: QPoint) -> QPoint:
        rect = self.image_rect()
        x = max(0, min(self.original.width, round(
            (point.x() - rect.x()) * self.original.width / rect.width()
        )))
        y = max(0, min(self.original.height, round(
            (point.y() - rect.y()) * self.original.height / rect.height()
        )))
        return QPoint(x, y)

    def selection(self) -> tuple[int, int, int, int] | None:
        if self.a is None or self.b is None:
            return None
        x0, x1 = sorted((self.a.x(), self.b.x()))
        y0, y1 = sorted((self.a.y(), self.b.y()))
        if x1 - x0 < 20 or y1 - y0 < 20:
            return None
        return x0, y0, x1, y1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.a = self._screen_to_image(event.position().toPoint())
            self.b = self.a
            self.update()

    def mouseMoveEvent(self, event):
        if self.a is not None:
            self.b = self._screen_to_image(event.position().toPoint())
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#171b25"))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.image_rect()
        painter.drawPixmap(rect, self.pixmap)
        selection = self.selection()
        if selection:
            x0, y0, x1, y1 = selection
            sx = rect.x() + round(x0 * rect.width() / self.original.width)
            sy = rect.y() + round(y0 * rect.height() / self.original.height)
            sw = round((x1 - x0) * rect.width() / self.original.width)
            sh = round((y1 - y0) * rect.height() / self.original.height)
            painter.fillRect(QRect(sx, sy, sw, sh), QColor(60, 210, 244, 35))
            painter.setPen(QPen(QColor("#35d6ef"), 2))
            painter.drawRect(QRect(sx, sy, sw, sh))
        painter.end()


class CropDialog(QDialog):
    def __init__(self, image: Image.Image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("WindowRift: Select an object")
        self.resize(900, 650)
        self.canvas = CropCanvas(image)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Drag a rectangle around the object, with some background margin."))
        layout.addWidget(self.canvas, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.image = image

    def _try_accept(self):
        if self.canvas.selection():
            self.accept()
        else:
            self.setWindowTitle("WindowRift: Select at least 20 x 20 pixels")

    def cropped(self) -> tuple[Image.Image, tuple[int, int]]:
        selection = self.canvas.selection()
        if selection is None:
            raise ValueError("No selection")
        x0, y0, x1, y1 = selection
        return self.image.crop((x0, y0, x1, y1)), (x0, y0)
