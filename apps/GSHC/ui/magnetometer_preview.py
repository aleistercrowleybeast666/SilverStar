"""Bounded visual projections; these never decide calibration acceptance."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from services.magnetometer_calibration import MAG_CALIBRATION_MAX_SAMPLES
from ui.diagnostic_labels import Text


@dataclass(frozen=True)
class MagProjectionSnapshot:
    raw: tuple = ()
    corrected: tuple = ()
    total: int = 0
    reference: float = 50.0
    axis_limit: float = 60.0
    error: str = ''


class MagProjectionPreview(QWidget):
    """Coalesce display work at 10 Hz; retain the complete collection for fitting."""
    DISPLAY_LIMIT = 1024
    PLANES = ((0, 1, 'XY'), (0, 2, 'XZ'), (1, 2, 'YZ'))

    def __init__(self, i18n, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.snapshot = MagProjectionSnapshot()
        self._pending = ((), None, 50.0)
        self._key = None
        self.setMinimumSize(420, 190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._refresh)
        self.retranslate()

    def retranslate(self):
        self.setAccessibleName('XY / XZ / YZ · µT')
        self.setToolTip(Text(self.i18n,
            '蓝：原始；绿：拟合校正（非设备回读）；虚线：参考场强。三图等比例，最多显示1024个抽样点；完整样本仍用于拟合。预览不代表校准通过。',
            'Blue: raw; green: fit correction (not device readback); dashed: reference field. Equal scales; at most 1024 display samples. Fitting retains all samples. Preview is not calibration acceptance.'))
        self.update()

    def set_samples(self, points, fit, reference):
        key = (id(points), len(points), id(fit), reference)
        if key == self._key:
            return
        self._key = key
        self._pending = (points, fit, reference)
        if not len(points):
            self.timer.stop()
            self._refresh()
        elif not self.timer.isActive():
            self.timer.start()

    def _refresh(self):
        points, fit, reference = self._pending
        try:
            reference = float(reference)
            raw = np.asarray(points, dtype=float).reshape((-1, 3))
            if (len(raw) > MAG_CALIBRATION_MAX_SAMPLES or not np.isfinite(raw).all()
                    or not math.isfinite(reference) or not 10 <= reference <= 100):
                raise ValueError('Invalid preview data')
            total = len(raw)
            # Evenly spread visual samples only; never mutate or trim collection.
            if total > self.DISPLAY_LIMIT:
                raw = raw[np.linspace(0, total - 1, self.DISPLAY_LIMIT, dtype=int)]
            corrected = np.empty((0, 3))
            if fit is not None and fit.hard_iron_uT is not None and fit.soft_iron is not None:
                bias = np.asarray(fit.hard_iron_uT, dtype=float)
                matrix = np.asarray(fit.soft_iron, dtype=float)
                if bias.shape != (3,) or matrix.shape != (3, 3):
                    raise ValueError('Invalid fit dimensions')
                corrected = (raw - bias) @ matrix.T
                if not np.isfinite(corrected).all():
                    raise ValueError('Invalid fit coordinates')
            maximum = max(reference, float(np.max(np.abs(raw))) if total else 0,
                          float(np.max(np.abs(corrected))) if len(corrected) else 0)
            limit = maximum * 1.1
            if not math.isfinite(limit):
                raise ValueError('Invalid preview range')
            self.snapshot = MagProjectionSnapshot(tuple(map(tuple, raw)), tuple(map(tuple, corrected)),
                                                  total, reference, limit)
        except (ValueError, TypeError, OverflowError):
            self.snapshot = MagProjectionSnapshot(error=Text(self.i18n, '预览数据无效', 'Invalid preview data'))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        data = self.snapshot
        cell = self.width() / 3
        side = max(20.0, min(cell - 24, self.height() - 58))
        for index, (a, b, name) in enumerate(self.PLANES):
            square = QRectF(index * cell + (cell - side) / 2, 26, side, side)
            center = square.center()
            scale = side / (2 * data.axis_limit)
            painter.setPen(self.palette().text().color())
            painter.drawText(QRectF(index * cell, 0, cell, 24), Qt.AlignCenter, name + ' · µT')
            painter.setPen(QPen(self.palette().mid().color(), 1))
            painter.drawRect(square)
            painter.drawLine(QPointF(square.left(), center.y()), QPointF(square.right(), center.y()))
            painter.drawLine(QPointF(center.x(), square.top()), QPointF(center.x(), square.bottom()))
            painter.setPen(QPen(self.palette().mid().color(), 1, Qt.DashLine))
            radius = data.reference * scale
            painter.drawEllipse(center, radius, radius)
            for points, color in ((data.raw, '#3182ce'), (data.corrected, '#14946f')):
                painter.setPen(QPen(QColor(color), 2))
                projected = QPolygonF([QPointF(center.x() + point[a] * scale,
                                             center.y() - point[b] * scale) for point in points])
                painter.drawPoints(projected)
            painter.setPen(self.palette().text().color())
            painter.drawText(QRectF(index * cell, square.bottom() + 2, cell, 24), Qt.AlignCenter,
                             f'±{data.axis_limit:.1f} µT')
        if data.error or not data.total:
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignCenter,
                             data.error or Text(self.i18n, '等待采样', 'Awaiting samples'))
