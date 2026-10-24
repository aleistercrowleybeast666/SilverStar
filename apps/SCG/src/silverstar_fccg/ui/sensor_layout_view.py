"""Body-frame installation geometry; only explicitly recorded positions are drawn."""
import hashlib
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QToolTip


class SensorLayoutView(QWidget):
    def __init__(self, translator, parent=None):
        super().__init__(parent)
        self._translator = translator
        self.positions = {}
        self.missing = ()
        self.extent_m = 0.1
        self._hit_points = []
        self.setMouseTracking(True)
        self.setMinimumHeight(260)
        self.setObjectName('sensorInstallationMap')

    def Configuration_Set(self, instances):
        self.positions = {item.instance_id: tuple(item.position_body_m) for item in instances
                          if item.component_class in ('imu', 'gnss') and item.position_body_m is not None}
        self.missing = tuple(item.instance_id for item in instances
                             if item.component_class in ('imu', 'gnss') and item.position_body_m is None)
        largest = max((abs(value) for position in self.positions.values() for value in position), default=0.0)
        if not math.isfinite(largest):
            raise ValueError('Non-finite sensor layout position')
        self.extent_m = max(0.001, largest * 1.25) if self.positions else 0.1
        self.update()

    def Language_Apply(self, translator):
        self._translator = translator
        self.update()

    def Point_Project(self, position, horizontal, vertical, box):
        scale = min(box.width(), box.height()) / (2 * self.extent_m)
        return QPointF(box.center().x() + position[horizontal] * scale,
                       box.center().y() - position[vertical] * scale)

    def paintEvent(self, event):
        self._hit_points = []
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self._translator.Text_Get
        foreground = self.palette().color(self.foregroundRole())
        painter.setPen(foreground)
        painter.drawText(QRectF(0, 0, self.width(), 24), text('installation.map.title'))
        width = self.width() / 3
        height = max(80, self.height() - 76)
        for index, (horizontal, vertical) in enumerate(((0, 1), (0, 2), (1, 2))):
            panel = QRectF(index * width + 4, 28, width - 12, height)
            available = panel.adjusted(32, 16, -25, -28)
            side = min(available.width(), available.height())
            box = QRectF(available.center().x() - side/2, available.center().y() - side/2, side, side)
            painter.setPen(QPen(self.palette().mid().color(), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box)
            origin = self.Point_Project((0, 0, 0), horizontal, vertical, box)
            painter.drawLine(QPointF(box.left(), origin.y()), QPointF(box.right(), origin.y()))
            painter.drawLine(QPointF(origin.x(), box.top()), QPointF(origin.x(), box.bottom()))
            painter.setPen(foreground)
            painter.drawText(QPointF(box.right() - 10, origin.y() - 5), '+' + 'xyz'[horizontal])
            painter.drawText(QPointF(origin.x() + 4, box.top() + 12), '+' + 'xyz'[vertical])
            painter.drawText(QPointF(origin.x() + 4, origin.y() + 14), 'O')
            painter.drawText(QRectF(panel.left(), panel.bottom() - 20, panel.width(), 20),
                Qt.AlignmentFlag.AlignCenter, f"{'xyz'[horizontal]}{'xyz'[vertical]} · ±{self.extent_m:.4g} m")
            for row, (identity, position) in enumerate(self.positions.items()):
                hue = int(hashlib.sha256(identity.encode()).hexdigest()[:4], 16) % 360
                color = QColor.fromHsv(hue, 190, 150 if self.palette().base().color().lightness() > 128 else 245)
                point = self.Point_Project(position, horizontal, vertical, box)
                self._hit_points.append((point, identity, position))
                painter.setPen(QPen(color, 2))
                painter.setBrush(color)
                painter.drawEllipse(point, 4, 4)
                # Stagger collocated labels; the dot always keeps the true position.
                label_box = QRectF(min(point.x() + 6, box.right() - 86),
                                   max(box.top(), min(point.y() - 17 + (row % 3) * 13, box.bottom() - 16)), 90, 18)
                painter.drawText(label_box, identity)
        painter.setPen(foreground)
        painter.drawText(QRectF(0, self.height() - 44, self.width(), 42),
            Qt.TextFlag.TextWordWrap, text('installation.map.missing', devices=', '.join(self.missing) or '—'))

    def mouseMoveEvent(self, event):
        hits = {identity: position for point, identity, position in self._hit_points
                if (point - event.position()).manhattanLength() <= 10}
        if hits:
            lines = [identity + ': (' + ', '.join(f'{value:.10g}' for value in position) + ') m'
                     for identity, position in hits.items()]
            QToolTip.showText(event.globalPosition().toPoint(), '\n'.join(lines), self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)
