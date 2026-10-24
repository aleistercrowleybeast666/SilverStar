"""Lightweight bounded watch list; no I/O or debugger expressions in widgets."""
import time
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QGridLayout,QLineEdit,QComboBox,
                              QPushButton,QTreeWidget,QTreeWidgetItem,QLabel,QCheckBox,QDialog)
from ui.touch_scroll import TouchScroll_Enable
from ui.diagnostic_labels import WatchValue_Format, Text


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
        self.candidate_help = QLabel()
        self.candidate_help.setTextFormat(Qt.PlainText)
        self.candidate_help.setWordWrap(True)
        self.candidate_help.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.empty_hint = QLabel()
        self.empty_hint.setWordWrap(True)
        self._readable_examples = ()
        self.table = QTreeWidget()
        self.table.setColumnCount(5)
        for column,width in enumerate((260,190,100,160,300)):
            self.table.setColumnWidth(column,width)
        self.table.setMinimumHeight(160)
        for view in (self.table,self.catalog.view(),self.interval.view()):
            TouchScroll_Enable(view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        controls = QGridLayout()
        self.search_label = QLabel()
        self.catalog_label = QLabel()
        self.interval_label = QLabel()
        self.search_label.setBuddy(self.search)
        self.catalog_label.setBuddy(self.catalog)
        self.interval_label.setBuddy(self.interval)
        controls.addWidget(self.search_label,0,0)
        controls.addWidget(self.search,0,1,1,3)
        controls.addWidget(self.interval_label,0,4)
        controls.addWidget(self.interval,0,5)
        controls.addWidget(self.pause,0,6)
        controls.addWidget(self.catalog_label,1,0)
        controls.addWidget(self.catalog,1,1,1,4)
        controls.addWidget(self.add,1,5)
        controls.addWidget(self.remove,1,6)
        controls.setColumnStretch(1,1)
        layout.addLayout(controls)
        layout.addWidget(self.note)
        layout.addWidget(self.candidate_help)
        layout.addWidget(self.empty_hint)
        layout.addWidget(self.table,1)
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
        self.search_label.setText(tr('watch.search_label'))
        self.catalog_label.setText(tr('watch.catalog_label'))
        self.interval_label.setText(tr('watch.interval_label'))
        self.search.setPlaceholderText(tr('watch.search'))
        self.add.setText(tr('watch.add'))
        self.remove.setText(tr('watch.remove'))
        self.pause.setText(tr('watch.pause'))
        self.empty_hint.setText(Text(self.i18n,'关注列表为空：请选择可读标量或结构成员，再点击“添加关注”。','The watch list is empty: select a readable scalar or member, then Add watch.'))
        self.table.setHeaderLabels([tr('watch.variable'),tr('watch.type_address'),tr('watch.value'),
                                   tr('maintenance.state_reason'),tr('watch.read_time')])
        self._filter()
        self.render()

    def set_firmware(self, firmware):
        if firmware is self.firmware: return
        self.firmware = firmware
        readable = [item.id for item in firmware.watches if not item.unavailable] if firmware else []
        scalars = [identifier for identifier in readable if '.' not in identifier.rsplit('::',1)[-1]]
        self._readable_examples = tuple((scalars or readable)[:2])
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
            caption = item.id + (Text(self.i18n,' [不可关注]',' [unavailable]') if item.unavailable else '')
            self.catalog.addItem(caption,item.id)
            self.catalog.setItemData(self.catalog.count()-1,item.unavailable or item.type_name,Qt.ToolTipRole)
        index = self.catalog.findData(previous)
        if index >= 0: self.catalog.setCurrentIndex(index)
        self.catalog.blockSignals(False)
        tr = self.i18n.tr
        detail = (tr('watch.no_elf') if not self.firmware else
                  tr('watch.no_dwarf') if not self.firmware.dwarf else
                  tr('watch.catalog_count').format(total=len(matches),shown=min(200,len(matches))))
        readable = sum(not item.unavailable for item in matches)
        self.note.setText(detail+Text(self.i18n,f'；其中 {readable} 项可关注',f'; {readable} readable')+'\n'+tr('watch.scope'))
        self._buttons()


    def _buttons(self, *_):
        identifier = self.catalog.currentData()
        field = next((item for item in self.firmware.watches if item.id == identifier),None) if self.firmware else None
        self.add.setEnabled(bool(field and not field.unavailable and identifier not in self.selected and len(self.selected)<16))
        self.remove.setEnabled(bool(self.table.selectedItems()))
        self.pause.setEnabled(self.active)
        if field and field.unavailable: self.catalog.setToolTip(field.unavailable)
        else: self.catalog.setToolTip('')
        if field and field.unavailable:
            reason = field.unavailable
            if reason == 'Missing/invalid DWARF size':
                reason = Text(self.i18n,'DWARF缺少可读大小信息；数组等对象不支持直接关注。','DWARF has no readable object size; arrays and other unsupported objects cannot be watched directly.')
            examples = '\n'+Text(self.i18n,'可搜索其他可读标量，例如：','Search for another readable scalar, for example: ')+' · '.join(self._readable_examples) if self._readable_examples else ''
            self.candidate_help.setText(Text(self.i18n,'此候选不可关注：','This candidate cannot be watched: ')+reason+examples)
            self.candidate_help.setToolTip(field.unavailable)
        elif field:
            self.candidate_help.setText(Text(self.i18n,'可关注RAM只读标量/成员：','Readable RAM scalar/member: ')+field.type_name+f' · 0x{field.address:08X}')
            self.candidate_help.setToolTip(field.id)
        else:
            self.candidate_help.setText('')
        self.empty_hint.setVisible(not self.selected)

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
        self.rows = {row['id']:row for row in rows if row['id'] in self.selected} if active else {}
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
                value = WatchValue_Format(identifier,row['value'],self.i18n)
                if age>3:value = Text(self.i18n,'历史观测：','Previous observation: ')+value
                state = (tr('maintenance.stale')+': ' if age>3 else '')+row['state']
                stamp = f"{row['captured_utc']} | RX {age:.1f}s"
            item = QTreeWidgetItem([identifier,f'{field.type_name} | 0x{field.address:08X}',value,state,stamp])
            item.setData(0,Qt.UserRole,identifier)
            for column in range(5): item.setToolTip(column,item.text(column))
            if row: item.setToolTip(3,row['reason']+'; '+row['consistency'])
            self.table.addTopLevelItem(item)
            item.setSelected(identifier in chosen)
        self._buttons()


class SwdWatchDialog(QDialog):
    """A view only. Hiding it stops optional watches through the owner signal."""
    visibility_changed = Signal(bool)

    def __init__(self,i18n,parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self.resize(1080,580)
        self.setMinimumSize(720,400)
        self.panel = SwdWatchPanel(i18n,self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.panel)
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(self.i18n.tr('watch.window'))
        self.panel.retranslate()

    def showEvent(self,event):
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self,event):
        super().hideEvent(event)
        self.visibility_changed.emit(False)

