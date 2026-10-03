from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from processing.horizontal_trajectory import (
    LABEL_IDS,
    HorizontalTrajectory_Build,
    HorizontalTrajectory_Draw,
)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget


class HorizontalTrajectoryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(7, 5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)
        self.trajectory = HorizontalTrajectory_Build([], [])
        self.labels = {}
        self.theme = "light"
        self.omitted_samples = 0
        self.history_trimmed_label = ""
        self.redraw_timer = QTimer(self)
        self.redraw_timer.setSingleShot(True)
        self.redraw_timer.setInterval(500)
        self.redraw_timer.timeout.connect(self._Draw)

    def Presentation_Set(self, translate, theme):
        self.labels = {key: translate("horizontal." + key) for key in LABEL_IDS}
        self.theme = theme
        self.history_trimmed_label = translate("horizontal.history_trimmed")
        if self.isVisible():
            self._Draw()

    def Trajectory_Set(self, trajectory, *, omitted_samples=0):
        self.trajectory = trajectory
        self.omitted_samples = omitted_samples
        if self.labels and self.isVisible() and not self.redraw_timer.isActive():
            # Coalesce the full bounded task graph to at most two stream draws
            # per second, independent of the existing six-curve refresh timer.
            self.redraw_timer.start()

    def _Draw(self):
        self.redraw_timer.stop()
        if self.labels:
            title = self.labels["title"]
            if self.omitted_samples:
                title += "\n" + self.history_trimmed_label.format(count=self.omitted_samples)
            HorizontalTrajectory_Draw(
                self.figure, self.trajectory, self.labels, theme=self.theme, title=title)
            self.canvas.draw_idle()

    def showEvent(self, event):
        super().showEvent(event)
        self._Draw()
