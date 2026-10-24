"""Compact connection views; ownership decisions remain with their controllers."""
import html
from PySide6.QtCore import Qt
from ui.diagnostic_labels import Text


def HeaderStatus_Set(label, caption, detail):
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(False)
    label.setMinimumWidth(0)
    label.setMaximumWidth(88)
    label.setText(caption)
    label.setToolTip('<qt>'+html.escape(detail).replace('\n','<br>')+'</qt>')


def ConnectionActions_Render(connect, disconnect, i18n, *, owned, cancelling=False, retry=False):
    connect.setVisible(not owned)
    disconnect.setVisible(owned)
    caption = ('重试关闭','Retry close') if retry else (('取消','Cancel') if cancelling else ('断开','Disconnect'))
    disconnect.setText(Text(i18n,*caption))

