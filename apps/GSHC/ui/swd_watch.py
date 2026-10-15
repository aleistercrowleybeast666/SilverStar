"""Lightweight bounded watch list; no I/O or debugger expressions in widgets."""
import time
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QComboBox,
                              QPushButton,QTreeWidget,QTreeWidgetItem,QLabel,QCheckBox)
from ui.touch_scroll import TouchScroll_Enable


class SwdWatchPanel(QWidget):
    selection_changed = Signal(object, float, bool)

    def __init__(self, i18n, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.firmware = None
        self.selected = []
        self.rows = {}
        self.active = False
        self.search = QLineEdit()
        self.catalog = QComboBox()
        self.catalog.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.catalog.setMinimumContentsLength(24)
        self.add = QPushButton()
        self.remove = QPushButton()
        self.pause = QCheckBox()
        self.interval = QComboBox()
        for value in (1,2,5): self.interval.addItem(f'{value} s',float(value))
        self.note = QLabel()
        self.note.setTextFormat(Qt.PlainText)
        self.note.setWordWrap(True)
        self.table = QTreeWidget()
        self.table.setColumnCount(5)
        for column,width in enumerate((260,190,100,160,300)):
            self.table.setColumnWidth(column,width)
        self.table.setMaximumHeight(190)
        for view in (self.table,self.catalog.view(),self.interval.view()):
            TouchScroll_Enable(view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        controls = QHBoxLayout()
        controls.addWidget(self.search,1)
        controls.addWidget(self.catalog,2)
        controls.addWidget(self.add)
        controls.addWidget(self.remove)
        controls.addWidget(self.interval)
        controls.addWidget(self.pause)
        layout.addLayout(controls)
        layout.addWidget(self.note)
        layout.addWidget(self.table)
        self.search.textChanged.connect(self._filter)
        self.catalog.currentIndexChanged.connect(self._buttons)
        self.add.clicked.connect(self._add)
        self.remove.clicked.connect(self._remove)
        self.pause.toggled.connect(self._changed)
        self.interval.currentIndexChanged.connect(self._changed)
        self.table.itemSelectionChanged.connect(self._buttons)
        self.retranslate()

    def retranslate(self):
        tr = self.i18n.tr
        self.search.setPlaceholderText(tr('watch.search'))
        self.add.setText(tr('watch.add'))
        self.remove.setText(tr('watch.remove'))
        self.pause.setText(tr('watch.pause'))
        self.table.setHeaderLabels([tr('watch.variable'),tr('watch.type_address'),tr('watch.value'),
                                   tr('maintenance.state_reason'),tr('watch.read_time')])
        self._filter()
        self.render()

    def set_firmware(self, firmware):
        if firmware is self.firmware: return
        self.firmware = firmware
        self.selected = []
        self.rows = {}
        self._filter()
        self._changed()

    def _filter(self, *_):
        needle = self.search.text().casefold()
        values = self.firmware.watches if self.firmware else ()
        matches = [item for item in values if needle in item.id.casefold()]
        previous = self.catalog.currentData()
        self.catalog.blockSignals(True)
        self.catalog.clear()
        for item in matches[:200]:
            self.catalog.addItem(item.id,item.id)
            self.catalog.setItemData(self.catalog.count()-1,item.unavailable or item.type_name,Qt.ToolTipRole)
        index = self.catalog.findData(previous)
        if index >= 0: self.catalog.setCurrentIndex(index)
        self.catalog.blockSignals(False)
        tr = self.i18n.tr
        detail = (tr('watch.no_elf') if not self.firmware else
                  tr('watch.no_dwarf') if not self.firmware.dwarf else
                  tr('watch.catalog_count').format(total=len(matches),shown=min(200,len(matches))))
        self.note.setText(detail+'\n'+tr('watch.scope'))
        self._buttons()

    def _buttons(self, *_):
        identifier = self.catalog.currentData()
        field = next((item for item in self.firmware.watches if item.id == identifier),None) if self.firmware else None
        self.add.setEnabled(bool(field and not field.unavailable and identifier not in self.selected and len(self.selected)<16))
        self.remove.setEnabled(bool(self.table.selectedItems()))
        self.pause.setEnabled(self.active)
        if field and field.unavailable: self.catalog.setToolTip(field.unavailable)
        else: self.catalog.setToolTip('')

    def _add(self):
        identifier = self.catalog.currentData()
        if self.add.isEnabled() and identifier:
            self.selected.append(identifier)
            self._changed()

    def _remove(self):
        removed = {item.data(0,Qt.UserRole) for item in self.table.selectedItems()}
        self.selected = [identifier for identifier in self.selected if identifier not in removed]
        self._changed()

    def _changed(self, *_):
        self.rows = {}
        self.render()
        self.selection_changed.emit(tuple(self.selected),self.interval.currentData(),self.pause.isChecked())

    def update_rows(self, rows, active):
        self.active = active
        self.rows = {row['id']:row for row in rows if row['id'] in self.selected}
        self.render()

    def render(self):
        chosen = {item.data(0,Qt.UserRole) for item in self.table.selectedItems()}
        self.table.clear()
        catalog = {item.id:item for item in self.firmware.watches} if self.firmware else {}
        tr = self.i18n.tr
        for identifier in self.selected:
            field = catalog[identifier]
            row = self.rows.get(identifier)
            value, state, stamp = '—',tr('watch.waiting') if self.active else tr('watch.disconnected'),'—'
            if row:
                age = max(0,(time.monotonic_ns()-row['received_ns'])/1e9)
                value = str(row['value'])
                state = (tr('maintenance.stale')+': ' if age>3 else '')+row['state']
                stamp = f"{row['captured_utc']} | RX {age:.1f}s"
            item = QTreeWidgetItem([identifier,f'{field.type_name} | 0x{field.address:08X}',value,state,stamp])
            item.setData(0,Qt.UserRole,identifier)
            for column in range(5): item.setToolTip(column,item.text(column))
            if row: item.setToolTip(3,row['reason']+'; '+row['consistency'])
            self.table.addTopLevelItem(item)
            item.setSelected(identifier in chosen)
        self._buttons()
