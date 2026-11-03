"""Edit build environment settings in a private project draft."""
from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout)

from silverstar_fccg.build.toolchain import ArmGnuSubtoolPaths_Derive


class BuildOptionsDialog(QDialog):
    def __init__(self, translator, model, tools, parent=None):
        super().__init__(parent)
        self.setObjectName('buildOptionsDialog')
        self.setWindowTitle(translator.Text_Get('build.options.title'))
        self.resize(680, 350)
        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)
        self._original = dict(model.build.tool_paths)
        self.fields = {}
        by_id = {item.tool_id: item for item in tools}
        for key in ('compiler', 'make', 'host_gcc'):
            row = QHBoxLayout()
            field = QLineEdit(self._original.get(key, ''), self)
            detected = by_id.get(key)
            field.setPlaceholderText(detected.path if detected and detected.path else translator.Text_Get('build.options.auto'))
            if detected:
                field.setToolTip('\n'.join(str(value) for value in
                    (detected.path, getattr(detected, 'version', '')) if value))
            browse = QPushButton('…', self)
            browse.setAccessibleName(translator.Text_Get('dialog.select_tool', tool=translator.Text_Get('tool.' + key)))
            browse.clicked.connect(lambda _checked=False, widget=field: self._Browse(widget))
            row.addWidget(field, 1)
            row.addWidget(browse)
            form.addRow(translator.Text_Get('tool.' + key), row)
            self.fields[key] = field
        self.memory = QComboBox(self)
        for option in dict.fromkeys((model.build.memory_layout, 'auto', 'eskf_window_sram')):
            self.memory.addItem(translator.Text_Get('memory.layout.' + option), option)
        form.addRow(translator.Text_Get('field.memory_layout'), self.memory)
        self.error = QLabel(self)
        self.error.setWordWrap(True)
        root.addWidget(self.error)
        root.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(translator.Text_Get('capsule.apply'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(translator.Text_Get('capsule.cancel'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._invalid = translator.Text_Get('build.options.invalid')

    def _Browse(self, field):
        selected, _ = QFileDialog.getOpenFileName(self, self.windowTitle(), field.text())
        if selected:
            field.setText(selected)

    def accept(self):
        paths = dict(self._original)
        for key, field in self.fields.items():
            value = field.text().strip()
            if value == self._original.get(key, ''):
                continue
            if value and (not Path(value).is_absolute() or not Path(value).is_file()):
                self.error.setText(self._invalid)
                field.setFocus()
                return
            paths.pop(key, None)
            if value:
                paths[key] = value
            if key == 'compiler':
                paths.pop('objcopy', None)
                paths.pop('size', None)
                if value:
                    paths.update(ArmGnuSubtoolPaths_Derive(value))
        self.paths = paths
        super().accept()
