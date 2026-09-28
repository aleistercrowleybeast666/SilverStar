"""Plot styling and reset helpers shared by independent GUI pages."""
from __future__ import annotations

from collections.abc import Iterable

import pyqtgraph as pg

from silverstar_flp.ui.theme import Plot_Colors


def _Plot_Prepare(plot: pg.PlotWidget, theme: str) -> None:
    background, foreground = Plot_Colors(theme)
    plot.setBackground(background)
    plot.getAxis("bottom").setTextPen(foreground)
    plot.getAxis("left").setTextPen(foreground)
    plot.getAxis("bottom").setPen(foreground)
    plot.getAxis("left").setPen(foreground)
    plot.showGrid(x=True, y=True, alpha=0.2)


def _Plot_Reset(plots: Iterable[pg.PlotWidget]) -> None:
    for plot in plots:
        plot.clear()
        plot.addLegend()


def _PlotViews_Reset(plots: Iterable[pg.PlotWidget]) -> None:
    for plot in plots:
        view_box = plot.getViewBox()
        view_box.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        view_box.updateAutoRange()
        legend = plot.getPlotItem().legend
        if legend is not None:
            legend.anchor(itemPos=(0, 0), parentPos=(0, 0), offset=(30, 30))


