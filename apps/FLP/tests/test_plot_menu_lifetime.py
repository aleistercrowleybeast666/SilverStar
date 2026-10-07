"""Native menu ownership and destruction, with worker GC still enabled."""
import gc
from threading import Thread, get_ident

import pyqtgraph as pg
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, Qt

from silverstar_flp.ui.plot_helpers import _Plot_Prepare


def test_plot_menus_are_native_owned_and_destroyed_in_gui_thread(qtbot):
    gui = get_ident()
    plot = pg.PlotWidget()
    qtbot.addWidget(plot)
    _Plot_Prepare(plot, 'light')
    item = plot.getPlotItem()
    menus = (item.ctrlMenu, item.getViewBox().menu)
    destroyed = []
    for index, menu in enumerate(menus):
        assert menu.parent() is plot, 'Plot menus must not await arbitrary-thread Python GC'
        assert not shiboken6.ownedByPython(menu)
        assert menu.isWindow() and menu.windowFlags() & Qt.WindowType.Popup == Qt.WindowType.Popup
        menu.destroyed.connect(lambda *_, index=index: destroyed.append((index, get_ident())),
                               Qt.ConnectionType.DirectConnection)
    _Plot_Prepare(plot, 'dark')
    assert menus == (item.ctrlMenu, item.getViewBox().menu)
    plot.plot([0, 1], [1, 0], name='lifetime')
    plot.clear()
    plot.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not shiboken6.isValid(plot)
    assert all(not shiboken6.isValid(menu) for menu in menus)
    worker = Thread(target=gc.collect)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert sorted(destroyed) == [(0, gui), (1, gui)]
    assert gc.isenabled()
