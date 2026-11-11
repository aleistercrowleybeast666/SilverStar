"""Register self-destroying MainWindow instances with pytest-qt 4.5.

That version retains Python weakrefs after native WA_DeleteOnClose destruction.
Remove only the exact registration on QObject.destroyed; live windows still use
its original cleanup and before-close callback. No Qt exceptions are intercepted.
"""
import weakref

from silverstar_flp.ui.main_window import MainWindow


def MainWindow_Register(qtbot, window, *, before_close_func=None):
    if not isinstance(window, MainWindow):
        raise TypeError('MainWindow lifecycle registration requires a MainWindow')
    qtbot.addWidget(window, before_close_func=before_close_func)
    item = qtbot._request.node
    registration = item.qt_widgets[-1]
    assert registration[0]() is window
    owner = weakref.ref(item)

    def destroyed(_object=None):
        current = owner()
        if current is not None and hasattr(current, 'qt_widgets'):
            # Replace the list, never mutate a list the original teardown may
            # already be iterating. Other registrations and callbacks survive.
            current.qt_widgets = [entry for entry in current.qt_widgets
                                  if entry is not registration]

    window.destroyed.connect(destroyed)
