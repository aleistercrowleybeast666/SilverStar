"""Explicit TF copy selection. No serial I/O or remote deletion in this view."""
from pathlib import Path
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QCheckBox,QTreeWidget,QTreeWidgetItem,QFileDialog,QProgressBar,QMessageBox,QAbstractItemView
from ui.touch_scroll import TouchScroll_Enable
from ui.diagnostic_labels import Text


def TransferProgress_Render(bar,snapshot,i18n):
    stages = {'synchronizing':('等待维护连接同步/能力核验','Waiting for maintenance synchronization/capabilities'),
        'listing':('等待状态/维护就绪/目录','Waiting for status/maintenance/catalog'),
        'capabilities':('确认文件服务能力（CAPS）','Confirming file service capabilities (CAPS)'),
        'metadata':('等待设备计算文件信息及全文件 CRC（META）','Waiting for device metadata and whole-file CRC (META)'),
        'first_block':('本地临时文件已建立，等待首个数据块','Local partial created; waiting for first data block'),
        'receiving':('接收','Receiving'),'verifying':('校验','Verifying'),
        'verified':('校验通过，正在收尾','Verified; finishing'),'complete':('完成','Complete'),
        'failed':('失败，保留已接收数据','Failed; received data retained'),
        'cancelling':('正在取消并收尾，请等待确认','Cancelling and finishing; waiting for confirmation'),
        'cancelled':('已取消，保留已接收数据','Cancelled; received data retained')}
    stage = Text(i18n,*stages.get(snapshot.stage,(snapshot.stage,snapshot.stage)))
    known = snapshot.total is not None
    terminal = snapshot.stage in {'complete','failed','cancelled'}
    bar.setRange(0,1000 if known or terminal else 0)
    value = min(1000,max(0,snapshot.received*1000//max(1,snapshot.total or 0))) if known else 0
    if known and snapshot.total==0 and snapshot.stage in {'verified','complete'}:value=1000
    bar.setValue(value)
    bar.setFormat(Text(i18n,'%p% 已接收','%p% received') if known else Text(i18n,'总量未知','Total unknown'))
    amount = f'{snapshot.received:,} / {snapshot.total:,} B' if known else Text(i18n,f'已接收 {snapshot.received:,} B（总量未知）',f'{snapshot.received:,} B received (total unknown)')
    files = f' · {snapshot.index}/{snapshot.count}' if snapshot.count else ''
    return stage+' · '+amount+files+(' · '+snapshot.detail if snapshot.detail else '')


class LogExportDialog(QDialog):
    refresh_requested=Signal()
    download_requested=Signal(str,object)
    cancel_requested=Signal()

    def __init__(self,i18n,parent=None):
        super().__init__(parent);self.i18n=i18n;self.connected=False;self.supported=False;self.busy=False;self.operation='';self._sizes={};self._confirming=False
        self.resize(860,620);self.setMinimumSize(650,440)
        layout=QVBoxLayout(self)
        self.explanation=QLabel();self.explanation.setWordWrap(True);layout.addWidget(self.explanation)
        self.verification=QLabel();self.verification.setWordWrap(True);self.verification.setTextFormat(Qt.PlainText)
        self.verification.setStyleSheet('QLabel { color: #9a3412; background: #fff7ed; border: 1px solid #c2410c; padding: 8px; font-weight: bold; }')
        self.verification.hide();layout.addWidget(self.verification)
        self.verification_state=''
        destination=QHBoxLayout();self.path=QLineEdit();self.browse=QPushButton();destination.addWidget(self.path,1);destination.addWidget(self.browse);layout.addLayout(destination)
        controls=QHBoxLayout();self.refresh=QPushButton();self.all=QCheckBox();self.count=QLabel();self.count.setWordWrap(True);controls.addWidget(self.refresh);controls.addWidget(self.all);controls.addWidget(self.count,1);layout.addLayout(controls)
        self.files=QTreeWidget();self.files.setColumnCount(3);self.files.setColumnWidth(0,260);self.files.setColumnWidth(1,130);TouchScroll_Enable(self.files);layout.addWidget(self.files,1)
        self.files.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.progress=QProgressBar();self.progress.setRange(0,1000);layout.addWidget(self.progress)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        actions=QHBoxLayout();self.start=QPushButton();self.cancel=QPushButton();self.close_button=QPushButton();actions.addWidget(self.start);actions.addWidget(self.cancel);actions.addStretch();actions.addWidget(self.close_button);layout.addLayout(actions)
        self.browse.clicked.connect(self._browse);self.path.textChanged.connect(self._buttons)
        self.all.toggled.connect(self._all);self.files.itemChanged.connect(self._selection)
        self.refresh.clicked.connect(self._refresh);self.start.clicked.connect(self._start)
        self.cancel.clicked.connect(self.cancel_requested);self.close_button.clicked.connect(self.close)
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(Text(self.i18n,'导出飞控TF日志（仅复制）','Export FC TF logs (copy only)'))
        self.explanation.setText(Text(self.i18n,'使用独立维护串口，不使用SWD。读取列表或下载会进入维护模式：停止本机日志、阻止START，之后需重启飞控恢复。源日志保留；正式下载重新校验目录、长度与CRC。','Uses the maintenance serial port, not SWD. Listing/downloading enters maintenance: stops logging and blocks START until FC reboot. Sources retained; downloads recheck listing, length and CRC.'))
        self.browse.setText(Text(self.i18n,'选择保存目录…','Choose destination…'));self.path.setPlaceholderText(Text(self.i18n,'选择明确的保存目录','Select an explicit destination'))
        self.refresh.setText(Text(self.i18n,'读取TF列表…','Read TF list…'));self.all.setText(Text(self.i18n,'全选','Select all'))
        self.files.setHeaderLabels([Text(self.i18n,'日志（勾选导出项）','Logs (check to export)'),Text(self.i18n,'大小','Size'),Text(self.i18n,'逐项结果','Result')])
        self.start.setText(Text(self.i18n,'确认下载并校验…','Download and verify…'));self.cancel.setText(Text(self.i18n,'取消当前操作','Cancel operation'));self.close_button.setText(Text(self.i18n,'关闭','Close'))
        labels={'not_exported':('未导出','Not exported'),'pending':('等待下载/校验','Pending download/verification'),'verified':('已下载并校验','Downloaded and verified'),'incomplete':('未完成（取消、失败或尚未处理）','Incomplete (cancelled, failed or pending)')}
        for index in range(self.files.topLevelItemCount()):
            item=self.files.topLevelItem(index);item.setText(2,Text(self.i18n,*labels.get(item.data(2,Qt.UserRole),labels['not_exported'])))
        self._selection()

    def _browse(self):
        selected=QFileDialog.getExistingDirectory(self,self.windowTitle(),self.path.text())
        if selected:self.path.setText(selected)

    def set_catalog(self,records,selected=None):
        checked=set(selected) if selected is not None else set(self.selected_ids())
        self.files.blockSignals(True);self.files.clear();self._sizes={}
        for record in records[:1024]:
            identifier=record['id'];size=record.get('size')
            self._sizes[identifier]=size
            item=QTreeWidgetItem([f'Mission {identifier:06d}',f'{size:,} B' if type(size) is int else Text(self.i18n,'未知','Unknown'),Text(self.i18n,'未导出','Not exported')])
            item.setData(2,Qt.UserRole,'not_exported');item.setData(0,Qt.UserRole,identifier);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(0,Qt.Checked if identifier in checked else Qt.Unchecked);self.files.addTopLevelItem(item)
        self.files.blockSignals(False);self._selection()

    def selected_ids(self):
        return tuple(self.files.topLevelItem(i).data(0,Qt.UserRole) for i in range(self.files.topLevelItemCount()) if self.files.topLevelItem(i).checkState(0)==Qt.Checked)

    def _all(self,checked):
        self.files.blockSignals(True)
        for index in range(self.files.topLevelItemCount()):self.files.topLevelItem(index).setCheckState(0,Qt.Checked if checked else Qt.Unchecked)
        self.files.blockSignals(False);self._selection()

    def _selection(self,*_):
        ids=self.selected_ids();known=sum(self._sizes[i] for i in ids if type(self._sizes.get(i)) is int);unknown=sum(type(self._sizes.get(i)) is not int for i in ids)
        text=Text(self.i18n,f'已选 {len(ids)} / {self.files.topLevelItemCount()} 项 · {known:,} B',f'{len(ids)} / {self.files.topLevelItemCount()} selected · {known:,} B')
        if unknown:text+=Text(self.i18n,f'，另{unknown}项大小未知',f'; {unknown} unknown sizes')
        self.count.setText(text);self.all.blockSignals(True);self.all.setChecked(bool(ids) and len(ids)==self.files.topLevelItemCount());self.all.blockSignals(False);self._buttons()

    def set_connection(self,connected,supported):
        self.connected=bool(connected);self.supported=bool(supported)
        if not connected:
            self.set_catalog([]);self.status.setText(Text(self.i18n,'维护串口已断开；重新连接后读取目录。','Maintenance port disconnected; reconnect and reread catalog.'))
        elif not supported:self.status.setText(Text(self.i18n,'当前固件未确认支持安全文件服务；不允许导出。','Safe file-service support is not confirmed; export unavailable.'))
        self._buttons()

    def Verification_SetState(self,state,detail):
        # Keep the action available so a click can explain and record its refusal.
        self.verification_state=state;self.verification.setText(detail)
        self.verification.setVisible(bool(state))

    def _buttons(self,*_):
        available=self.connected and self.supported and not self.busy and not self._confirming
        self.refresh.setEnabled(available);self.start.setEnabled(available and bool(self.selected_ids()) and bool(self.path.text().strip()))
        self.cancel.setEnabled(self.busy);self.files.setEnabled(not self.busy);self.all.setEnabled(not self.busy);self.browse.setEnabled(not self.busy);self.path.setEnabled(not self.busy)

    def _confirm(self):
        if self._confirming:return False
        self._confirming=True;self._buttons()
        try:
            return QMessageBox.question(self,Text(self.i18n,'确认进入日志维护模式','Confirm log maintenance mode'),self.explanation.text(),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
        finally:
            self._confirming=False;self._buttons()

    def _refresh(self):
        if self.refresh.isEnabled() and self._confirm() and self.refresh.isEnabled():self.refresh_requested.emit()

    def _start(self):
        if self.start.isEnabled() and self._confirm() and self.start.isEnabled():self.download_requested.emit(self.path.text().strip(),self.selected_ids())

    def set_busy(self,busy,operation=''):
        self.busy=bool(busy)
        if busy:
            self.operation=operation;self.progress.setValue(0)
            if operation=='download':
                ids=set(self.selected_ids())
                for index in range(self.files.topLevelItemCount()):
                    item=self.files.topLevelItem(index)
                    if item.data(0,Qt.UserRole) in ids:
                        item.setData(2,Qt.UserRole,'pending');item.setText(2,Text(self.i18n,'等待下载/校验','Pending download/verification'))
        elif self.progress.maximum()==0:
            self.progress.setRange(0,1000);self.progress.setValue(0)
        self._buttons()

    def show_progress(self,done,total,detail):
        self.progress.setValue(min(1000,max(0,int(done*1000//max(1,total)))));self.status.setText(detail)

    def show_byte_progress(self,snapshot):
        self.status.setText(TransferProgress_Render(self.progress,snapshot,self.i18n))

    def show_results(self,files):
        verified={entry['file_id']:entry for entry in files}
        for index in range(self.files.topLevelItemCount()):
            item=self.files.topLevelItem(index);identifier=item.data(0,Qt.UserRole)
            if identifier in verified:
                item.setData(2,Qt.UserRole,'verified');item.setText(2,Text(self.i18n,'已下载并校验','Downloaded and verified'));item.setToolTip(2,str(verified[identifier]))
            elif item.checkState(0)==Qt.Checked:
                item.setData(2,Qt.UserRole,'incomplete');item.setText(2,Text(self.i18n,'未完成（取消、失败或尚未处理）','Incomplete (cancelled, failed or pending)'))

    def reject(self):
        if self.busy:self.cancel_requested.emit()
        super().reject()

    def closeEvent(self,event):
        if self.busy:self.cancel_requested.emit()
        super().closeEvent(event)
