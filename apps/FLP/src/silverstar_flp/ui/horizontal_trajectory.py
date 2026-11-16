from PySide6.QtWidgets import QVBoxLayout, QWidget

from silverstar_flp.core.horizontal_trajectory import (
    LABEL_IDS,
    HorizontalTrajectory_Build,
    HorizontalTrajectory_Draw,
)


class HorizontalTrajectoryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._figure = None
        self._canvas = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.trajectory = HorizontalTrajectory_Build([], [])
        self.labels = {}
        self.theme = "light"

    def _Canvas_Ensure(self):
        if self._canvas is None:
            # This tab starts hidden. Keep its renderer out of the startup path;
            # plugins, data contracts and the numerical runtime still initialize
            # normally. Import failures retain the existing exception path.
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure

            figure = Figure(figsize=(7, 5))
            canvas = FigureCanvasQTAgg(figure)
            self.layout().addWidget(canvas)
            self._figure, self._canvas = figure, canvas

    @property
    def figure(self):
        self._Canvas_Ensure()
        return self._figure

    @property
    def canvas(self):
        self._Canvas_Ensure()
        return self._canvas

    def Presentation_Set(self, translate, theme):
        self.labels = {key: translate("horizontal." + key) for key in LABEL_IDS}
        self.theme = theme
        self.Trajectory_Set(self.trajectory)

    def Trajectory_Set(self, trajectory):
        self.trajectory = trajectory
        if self.labels and self.isVisible():
            self._Draw()

    def _Draw(self):
        if self.labels:
            HorizontalTrajectory_Draw(self.figure, self.trajectory, self.labels, theme=self.theme)
            self.canvas.draw_idle()

    def showEvent(self, event):
        super().showEvent(event)
        self._Draw()
