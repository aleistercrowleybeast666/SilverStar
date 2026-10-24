"""Body-frame installation geometry; only explicitly recorded positions are drawn."""
import hashlib
import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
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
        self._label_boxes = []
        self._plot_boxes = []
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
        self._MinimumHeight_Update()
        self.update()

    def Language_Apply(self, translator):
        self._translator = translator
        self._MinimumHeight_Update()
        self.update()

    def _TextHeights_Get(self):
        metrics = self.fontMetrics()
        text = self._translator.Text_Get
        values = (text('installation.map.title'),
                  text('installation.map.missing', devices=', '.join(self.missing) or '—'))
        return tuple(metrics.boundingRect(0, 0, max(1, self.width() - 8), 4096,
                     Qt.TextFlag.TextWordWrap, value).height() + 8 for value in values)

    def _MinimumHeight_Update(self):
        title_height, footer_height = self._TextHeights_Get()
        minimum = title_height + footer_height + max(180, self.fontMetrics().height() * 9)
        if self.minimumHeight() != minimum:
            self.setMinimumHeight(minimum)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._MinimumHeight_Update()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and hasattr(self, '_translator'):
            self._MinimumHeight_Update()

    def Point_Project(self, position, horizontal, vertical, box):
        scale = min(box.width(), box.height()) / (2 * self.extent_m)
        return QPointF(box.center().x() + position[horizontal] * scale,
                       box.center().y() - position[vertical] * scale)

    def paintEvent(self, event):
        self._hit_points = []
        self._label_boxes = []
        self._plot_boxes = []
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = self._translator.Text_Get
        foreground = self.palette().color(self.foregroundRole())
        metrics = painter.fontMetrics()
        line_height = metrics.height()
        title = text('installation.map.title')
        footer = text('installation.map.missing', devices=', '.join(self.missing) or '—')
        title_height, footer_height = self._TextHeights_Get()
        painter.setPen(foreground)
        painter.drawText(QRectF(4, 2, self.width() - 8, title_height), Qt.TextFlag.TextWordWrap, title)
        width = self.width() / 3
        height = max(80, self.height() - title_height - footer_height)
        for index, (horizontal, vertical) in enumerate(((0, 1), (0, 2), (1, 2))):
            panel = QRectF(index * width + 4, title_height, width - 12, height)
            available = panel.adjusted(8, 6, -8, -line_height - 8)
            side = min(available.width(), available.height())
            box = QRectF(available.center().x() - side/2, available.center().y() - side/2, side, side)
            self._plot_boxes.append(box)
            painter.setPen(QPen(self.palette().mid().color(), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box)
            origin = self.Point_Project((0, 0, 0), horizontal, vertical, box)
            painter.drawLine(QPointF(box.left(), origin.y()), QPointF(box.right(), origin.y()))
            painter.drawLine(QPointF(origin.x(), box.top()), QPointF(origin.x(), box.bottom()))
            painter.setPen(foreground)
            axis_labels = [
                (QRectF(box.right() - metrics.horizontalAdvance('+x') - 5, origin.y() - line_height - 4,
                        metrics.horizontalAdvance('+x') + 2, line_height), '+' + 'xyz'[horizontal]),
                (QRectF(origin.x() + 5, box.top() + 3, metrics.horizontalAdvance('+z') + 2, line_height), '+' + 'xyz'[vertical]),
                (QRectF(origin.x() + 6, origin.y() + 6, metrics.horizontalAdvance('O') + 2, line_height), 'O')]
            blocked = [rect.adjusted(-3, -3, 3, 3) for rect, _label in axis_labels]
            for rect, label in axis_labels:
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
            painter.drawText(QRectF(panel.left(), panel.bottom() - line_height - 4, panel.width(), line_height + 4),
                Qt.AlignmentFlag.AlignCenter, f"{'xyz'[horizontal]}{'xyz'[vertical]} · ±{self.extent_m:.4g} m")
            points = [(identity, position, self.Point_Project(position, horizontal, vertical, box))
                      for identity, position in self.positions.items()]
            blocked.extend(QRectF(point.x()-6, point.y()-6, 12, 12) for _identity, _position, point in points)
            blocked.extend((QRectF(box.left(), origin.y()-1, box.width(), 2),
                            QRectF(origin.x()-1, box.top(), 2, box.height())))
            for identity, position, point in points:
                hue = int(hashlib.sha256(identity.encode()).hexdigest()[:4], 16) % 360
                color = QColor.fromHsv(hue, 190, 150 if self.palette().base().color().lightness() > 128 else 245)
                self._hit_points.append((point, identity, position))
                painter.setPen(QPen(color, 2))
                painter.setBrush(color)
                painter.drawEllipse(point, 4, 4)
                label = metrics.elidedText(identity, Qt.TextElideMode.ElideRight, max(12, int(box.width() - 12)))
                label_box = self._LabelBox_Find(point, metrics.horizontalAdvance(label) + 4, line_height + 2, box, blocked)
                if label_box is not None:
                    blocked.append(label_box.adjusted(-3, -3, 3, 3))
                    self._label_boxes.append((index, identity, label_box))
                    painter.setPen(QPen(color, 1))
                    painter.drawLine(point, QPointF(
                        min(max(point.x(), label_box.left()), label_box.right()),
                        min(max(point.y(), label_box.top()), label_box.bottom())))
                    painter.fillRect(label_box, self.palette().base())
                    painter.drawText(label_box, Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(foreground)
        painter.drawText(QRectF(4, self.height() - footer_height + 2, self.width() - 8, footer_height),
            Qt.TextFlag.TextWordWrap, footer)

    @staticmethod
    def _LabelBox_Find(point, width, height, bounds, blocked):
        # Bounded placement moves only text; the projected measurement stays fixed.
        for ring in range(8):
            gap = 8 + ring * (height + 3)
            for x, y in ((point.x()+gap, point.y()-height-gap), (point.x()+gap, point.y()+gap),
                         (point.x()-width-gap, point.y()-height-gap), (point.x()-width-gap, point.y()+gap),
                         (point.x()-width/2, point.y()-height-gap), (point.x()-width/2, point.y()+gap)):
                x = min(max(x, bounds.left() + 3), bounds.right() - width - 3)
                y = min(max(y, bounds.top() + 3), bounds.bottom() - height - 3)
                rect = QRectF(x, y, width, height)
                if bounds.adjusted(3, 3, -3, -3).contains(rect) and not any(rect.intersects(other) for other in blocked):
                    return rect
        return None  # Dense layouts retain their exact dots and full hover coordinates.

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
