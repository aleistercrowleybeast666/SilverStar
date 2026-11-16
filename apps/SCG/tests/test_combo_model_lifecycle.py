"""Repeated form rebuilds retain model identity, item flags and Qt ownership."""
import gc

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QStandardItemModel
from shiboken6 import isValid
from silverstar_fccg.ui.widgets import StandardComboBox


def test_combo_rebuild_keeps_model_and_disabled_selection(qapp):
    for _ in range(200):
        combo = StandardComboBox()
        combo.addItem('unselected', None)
        combo.addItem('stored unsupported output', 19)
        model = combo.model()
        assert isinstance(model, QStandardItemModel)
        item = model.item(1)
        item.setEnabled(False)
        combo.setCurrentIndex(1)
        gc.collect()
        assert combo.model() is model and combo.currentData() == 19
        assert not model.item(1).isEnabled()
        combo.clear()
        assert combo.count() == 0 and model.rowCount() == 0
        # QStandardItem is not a QObject. Its Python wrapper validity flag is
        # not a reliable deletion witness after Qt removes its native row.
        # Do not dereference the old item; verify the owning model instead.
        del item
        combo.addItem('20 dBm', 20)
        assert combo.model() is model and model.item(0).isEnabled()
        assert combo.currentData() == 20
        combo.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert not isValid(combo) and not isValid(model)
