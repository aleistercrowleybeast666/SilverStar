"""One function row per shared instance; cells open that owner's transaction."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from silverstar_fccg.project.mission_functions import FunctionCoverage_Get
from silverstar_fccg.ui.touch_scroll import TouchScroll_Enable


class MissionCoverageTable(QTableWidget):
    stageRequested = Signal(str)
    functionRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('missionCoverage')
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setMinimumSectionSize(92)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._stages = []
        self._functions = []
        self.horizontalHeader().sectionClicked.connect(self._Header_Open)
        self.cellClicked.connect(self._Cell_Open)
        self.cellActivated.connect(self._Cell_Open)
        TouchScroll_Enable(self)

    def _Header_Open(self, column):
        if 0 < column <= len(self._stages):
            self.stageRequested.emit(self._stages[column - 1])

    def _Cell_Open(self, row, _column):
        if 0 <= row < len(self._functions):
            self.functionRequested.emit(self._functions[row])

    def Function_Select(self, identity):
        if identity in self._functions:
            self.setCurrentCell(self._functions.index(identity), 0)

    def Configuration_Set(self, functions, process, translator, name_getter):
        text = translator.Text_Get
        stages = process['stages']
        self._stages = [stage['stage_id'] for stage in stages]
        self._functions = [function['instance_id'] for function in functions]
        self.setColumnCount(len(stages) + 1)
        self.setRowCount(len(functions))
        self.setHorizontalHeaderLabels([text('workflow.shared_function')] +
            [name_getter(stage) for stage in stages])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for row_index, function in enumerate(functions):
            role_key = 'workflow.role.' + function['instance_id']
            role = text(role_key)
            if role == role_key:
                role = function['instance_id']
            identity = QTableWidgetItem(role)
            identity.setToolTip(function['instance_id'] + '\n' + function['plugin_id'])
            self.setItem(row_index, 0, identity)
            coverage = FunctionCoverage_Get(function, self._stages, process)
            for column, stage_id in enumerate(self._stages, 1):
                status = coverage.get(stage_id, '')
                item = QTableWidgetItem(text('workflow.map.' + status) if status else '—')
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(text('workflow.configure_function', name=role))
                if status:
                    color = self.palette().highlight().color()
                    color.setAlpha(36)
                    item.setBackground(QBrush(color))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.setItem(row_index, column, item)
        row_height = max(32, self.fontMetrics().height() + 18)
        self.verticalHeader().setDefaultSectionSize(row_height)
        self.setMinimumHeight(90)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedHeight(self.horizontalHeader().sizeHint().height() +
            row_height * max(1, len(functions)) + 24)
