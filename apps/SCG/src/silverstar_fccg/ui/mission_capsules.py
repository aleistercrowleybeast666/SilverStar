"""Schema-driven mission rule capsules. Project/controller owns every change."""
from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QSpinBox, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from silverstar_fccg.ui.committed_spin import EnterCommittedDoubleSpinBox, EnterCommittedSpinBox


def _Editor_Create(parameter, value, *, draft=False):
    integer = parameter['type'] == 'integer'
    editor = (QSpinBox() if integer else QDoubleSpinBox()) if draft else (
        EnterCommittedSpinBox() if integer else EnterCommittedDoubleSpinBox())
    if not integer:
        editor.setDecimals(3)
    editor.setRange(parameter['minimum'], parameter['maximum'])
    editor.setSingleStep(1 if integer else 0.1)
    editor.setSuffix(' ' + parameter['unit'])
    editor.setKeyboardTracking(False)
    editor.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus)
    if draft:
        editor.setValue(value)
    else:
        editor.CommittedValue_Set(value)
    return editor


class MissionRuleDialog(QDialog):
    def __init__(self, translator, owner, option, values, available, detail, parent=None):
        super().__init__(parent)
        text = translator.Text_Get
        name = owner.options.get('selection_labels', {}).get(option, option)
        self.setWindowTitle(text('capsule.dialog_title', name=name))
        self.setMinimumWidth(480)
        self.resize(560, 360)
        self.editors = {}
        self._values = {}
        self._original = {}
        self._edited = set()
        self._available = available
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for parameter in owner.options.get('selection_parameters', {}).get(option, ()):
            key = parameter['id']
            value = values.get(key, parameter['default'])
            editor = _Editor_Create(parameter, value, draft=True)
            self._original[key] = value
            editor.valueChanged.connect(lambda _value, name=key: self._edited.add(name))
            editor.lineEdit().textEdited.connect(lambda _text, name=key: self._edited.add(name))
            editor.setEnabled(available)
            editor.setObjectName('capsuleDialog_' + parameter['id'])
            editor.setToolTip(text('mode.parameter_range', minimum=parameter['minimum'], maximum=parameter['maximum'], unit=parameter['unit']))
            form.addRow(str(parameter['display_name']), editor)
            self.editors[parameter['id']] = editor
        layout.addLayout(form)
        semantics = QLabel(text('capsule.template_semantics') if owner.selection_slot == 'deployment' else str(owner.options.get('selection_note', '')))
        semantics.setWordWrap(True)
        layout.addWidget(semantics)
        declaration = QLabel(text('capsule.owner', plugin=owner.component_id, version=owner.version))
        declaration.setTextFormat(Qt.TextFormat.PlainText)
        declaration.setWordWrap(True)
        declaration.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(declaration)
        note = QLabel(detail or owner.description)
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        self.error_label = QLabel()
        layout.addWidget(self.error_label)
        layout.addStretch(1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text('capsule.apply'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(text('capsule.cancel'))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(available)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._invalid_message = text('capsule.invalid')

    def accept(self):
        if not self._available:
            return
        for editor in self.editors.values():
            if not editor.lineEdit().hasAcceptableInput():
                self.error_label.setText(self._invalid_message)
                editor.setFocus()
                return
        for editor in self.editors.values():
            editor.interpretText()
        self._values = {name: editor.value() if name in self._edited else self._original[name]
                        for name, editor in self.editors.items()}
        super().accept()

    def Values_Get(self):
        return dict(self._values)


class MissionCapsuleBoard(QWidget):
    optionsChanged = Signal(object)
    parameterChanged = Signal(str, str, object)

    def __init__(self, translator, owner, selected, values, availability, detail_provider, parent=None):
        super().__init__(parent)
        self._translator = translator
        self._owner = owner
        self._selected = list(selected)
        self._values = deepcopy(values)
        self._availability = availability
        self._detail_provider = detail_provider
        self.cards = {}
        self.parameter_editors = {}
        self._columns = 0
        for option, definitions in owner.options.get('selection_parameters', {}).items():
            for parameter in definitions:
                self._values.setdefault(option, {}).setdefault(parameter['id'], parameter['default'])
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        note = QLabel(translator.Text_Get('capsule.summary'))
        note.setWordWrap(True)
        toolbar.addWidget(note, 1)
        self.add_button = QPushButton(translator.Text_Get('capsule.add'))
        self.add_button.setObjectName('missionCapsuleAdd_' + owner.selection_slot)
        self.add_button.setMinimumHeight(34)
        self.add_menu = QMenu(self.add_button)
        self.add_menu.setToolTipsVisible(True)
        self.add_actions = {}
        for option in owner.selection_options:
            action = self.add_menu.addAction(str(owner.options.get('selection_labels', {}).get(option, option)))
            action.setEnabled(option not in self._selected and self._availability[option].available)
            action.setToolTip(detail_provider(self._availability[option]))
            action.triggered.connect(lambda _checked=False, selected=option: self.Option_Add(selected))
            self.add_actions[option] = action
        self.add_button.setMenu(self.add_menu)
        self.add_button.setEnabled(any(action.isEnabled() for action in self.add_actions.values()))
        toolbar.addWidget(self.add_button)
        root.addLayout(toolbar)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 4, 0, 4)
        self.grid.setSpacing(10)
        root.addLayout(self.grid)
        self.empty_label = QLabel(translator.Text_Get('capsule.empty'))
        self.empty_label.setWordWrap(True)
        self.empty_label.setVisible(not self._selected)
        root.addWidget(self.empty_label)
        labels = owner.options.get('selection_labels', {})
        definitions = owner.options.get('selection_parameters', {})
        for option in owner.selection_options:
            if option not in self._selected:
                continue
            card = QFrame()
            card.setObjectName('missionRuleCapsule')
            card.setStyleSheet('QFrame#missionRuleCapsule { border: 1px solid palette(mid); border-radius: 18px; background: palette(base); }')
            card.setMinimumWidth(320)
            row = QHBoxLayout(card)
            row.setContentsMargins(12, 10, 10, 10)
            title = QToolButton()
            short_key = 'capsule.option.' + option
            title.setText(translator.Text_Get(short_key) if short_key in translator.CatalogKeys_Get() else str(labels.get(option, option)))
            title.setAutoRaise(True)
            title.setToolTip(translator.Text_Get('capsule.configure'))
            title.clicked.connect(lambda _checked=False, selected=option: self.Dialog_Open(selected))
            row.addWidget(title)
            available = self._availability[option].available
            detail = detail_provider(self._availability[option])
            parameters = definitions.get(option, ())
            if parameters:
                parameter = parameters[0]
                value = self._values.get(option, {}).get(parameter['id'], parameter['default'])
                editor = _Editor_Create(parameter, value)
                editor.setObjectName('modeParameter_' + owner.selection_slot + '_' + option + '_' + parameter['id'])
                editor.setMinimumWidth(118)
                editor.setEnabled(available)
                editor.setToolTip(str(parameter['display_name']) + '\n' + detail)
                editor.committed.connect(lambda value, selected=option, key=parameter['id']: self._Parameter_Commit(selected, key, value))
                self.parameter_editors[(option, parameter['id'])] = editor
                row.addWidget(editor, 1)
            else:
                row.addStretch(1)
            more = QToolButton()
            more.setText('…'); more.setAutoRaise(True)
            more.setToolTip(translator.Text_Get('capsule.configure'))
            more.setAccessibleName(translator.Text_Get('capsule.configure'))
            more.clicked.connect(lambda _checked=False, selected=option: self.Dialog_Open(selected))
            row.addWidget(more)
            remove = QToolButton()
            remove.setText('×'); remove.setAutoRaise(True)
            remove.setToolTip(translator.Text_Get('capsule.remove'))
            remove.setAccessibleName(translator.Text_Get('capsule.remove'))
            remove.setEnabled(owner.allow_none or len(self._selected) > 1)
            remove.clicked.connect(lambda _checked=False, selected=option: self.Option_Remove(selected))
            row.addWidget(remove)
            card.setToolTip(detail)
            self.cards[option] = card
        self._Cards_Layout()

    def _Cards_Layout(self):
        columns = max(1, min(3, self.width() // 380))
        if columns == self._columns:
            return
        self._columns = columns
        for card in self.cards.values():
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards.values()):
            self.grid.addWidget(card, index // columns, index % columns)
        for column in range(3):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._Cards_Layout()

    def Option_Add(self, option):
        if option not in self._owner.selection_options or option in self._selected or not self._availability[option].available:
            return
        if not self._owner.allow_multiple:
            self._selected = []
        self._selected.append(option)
        self.optionsChanged.emit([item for item in self._owner.selection_options if item in self._selected])

    def Option_Remove(self, option):
        if option not in self._selected or (not self._owner.allow_none and len(self._selected) == 1):
            return
        self._selected.remove(option)
        self.optionsChanged.emit(list(self._selected))

    def _Parameter_Commit(self, option, parameter, value):
        self._values.setdefault(option, {})[parameter] = value
        self.parameterChanged.emit(option, parameter, value)

    def Dialog_Open(self, option):
        availability = self._availability[option]
        dialog = MissionRuleDialog(self._translator, self._owner, option,
            self._values.get(option, {}), availability.available, self._detail_provider(availability), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            dialog.deleteLater()
            return
        for parameter, value in dialog.Values_Get().items():
            if value != self._values.get(option, {}).get(parameter):
                editor = self.parameter_editors.get((option, parameter))
                if editor is not None:
                    editor.CommittedValue_Set(value)
                self._Parameter_Commit(option, parameter, value)
        dialog.deleteLater()
