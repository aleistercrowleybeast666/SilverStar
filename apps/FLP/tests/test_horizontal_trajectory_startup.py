"""A hidden tab defers only its renderer, preserving current data and styling."""
import os
from pathlib import Path
import subprocess
import sys

from silverstar_flp.core.horizontal_trajectory import HorizontalTrajectory_Build
from silverstar_flp.core.i18n import Translator
from silverstar_flp.ui.horizontal_trajectory import HorizontalTrajectoryWidget


def test_hidden_widget_does_not_import_matplotlib_in_fresh_process():
    source = Path(__file__).parents[1] / 'src'
    code = '''
import sys
from PySide6.QtWidgets import QApplication
from silverstar_flp.ui.horizontal_trajectory import HorizontalTrajectoryWidget
app = QApplication([])
widget = HorizontalTrajectoryWidget()
assert widget._canvas is None
assert not any(name == 'matplotlib' or name.startswith('matplotlib.') for name in sys.modules)
widget.close()
'''
    result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True,
                            text=True, timeout=30,
                            env=dict(os.environ, PYTHONPATH=str(source), QT_QPA_PLATFORM='offscreen'))
    assert result.returncode == 0, result.stdout + result.stderr


def test_first_show_draws_latest_hidden_data_then_reuses_canvas(qtbot, qapp):
    widget = HorizontalTrajectoryWidget()
    qtbot.addWidget(widget)
    widget.Presentation_Set(Translator('zh_CN').Text_Get, 'dark')
    widget.Trajectory_Set(HorizontalTrajectory_Build([0, .1], [(0, 0, 0), (1, 2, 3)]))
    latest = HorizontalTrajectory_Build([0, .1], [(0, 0, 0), (3, 4, 5)])
    widget.Trajectory_Set(latest)
    widget.Presentation_Set(Translator('en_US').Text_Get, 'light')
    assert widget._canvas is None and widget._figure is None
    widget.show()
    qapp.processEvents()
    assert widget.trajectory is latest
    canvas, figure = widget.canvas, widget.figure
    assert canvas.parentWidget() is widget and len(figure.axes) == 2
    assert figure.axes[0].get_title() == widget.labels['title']
    assert figure.axes[1].get_ylabel() == widget.labels['height']
    assert figure.axes[0].get_aspect() == 1
    widget.hide()
    widget.Presentation_Set(Translator('zh_CN').Text_Get, 'dark')
    widget.show()
    qapp.processEvents()
    assert widget.canvas is canvas and widget.figure is figure
    assert figure.axes[0].get_title() == widget.labels['title']


def test_explicit_canvas_access_before_show_remains_supported(qtbot):
    widget = HorizontalTrajectoryWidget()
    qtbot.addWidget(widget)
    canvas = widget.canvas
    assert canvas.figure is widget.figure
    assert widget.layout().count() == 1
    widget.show()
    assert widget.canvas is canvas
