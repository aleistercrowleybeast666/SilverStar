"""Protocol-guided and editable commands; the maintenance owner performs I/O."""
from PySide6.QtCore import Signal,Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QComboBox,
    QLineEdit,QLabel,QPushButton,QPlainTextEdit,QCheckBox,QMessageBox)
from services.maintenance_commands import ConsoleCatalog_Get,ConsoleCommand_Validate,ConsoleCommand_IsKnown
from ui.diagnostic_labels import Text,ConsoleResponse_Summary
from ui.touch_scroll import TouchScroll_Enable


class MaintenanceConsole(QWidget):
    send_requested=Signal(str)
    declaration_changed=Signal()

    def __init__(self,i18n,parent=None):
        super().__init__(parent)
        self.i18n=i18n;self.connected=False;self.busy=False
        self._manual=False;self._updating=False;self._last_instance='0'
        self._declaration={};self._runtime_caps={}
        self.declaration_loading=False;self._verification_note=''
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        title_row=QHBoxLayout();self.title=QLabel();self.protocol_status=QLabel();self.clear_display=QPushButton()
        self.protocol_status.setTextFormat(Qt.PlainText)
        self.protocol_status.setWordWrap(True)
        title_row.addWidget(self.title);title_row.addWidget(self.clear_display);title_row.addStretch();title_row.addWidget(self.protocol_status)
        layout.addLayout(title_row)
        self.category=QComboBox();self.category.setMaximumWidth(150)
        self.instance=QLineEdit();self.instance.setValidator(QIntValidator(0,255,self));self.instance.setMaximumWidth(65)
        self.choice=QComboBox();self.choice.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);self.choice.setMinimumContentsLength(9)
        self.parameters=QLineEdit();self.raw=QLineEdit();self.raw.setMaxLength(191)
        self.send=QPushButton();self.hint=QLabel();self.hint.setWordWrap(True)
        self.raw_mode=QCheckBox(self);self.raw_mode.hide()
        self.category_label=QLabel();self.instance_label=QLabel();self.command_label=QLabel();self.parameters_label=QLabel()
        selectors=QGridLayout()
        for column,(label,widget) in enumerate(((self.category_label,self.category),(self.instance_label,self.instance),(self.command_label,self.choice))):
            selectors.addWidget(label,0,column);selectors.addWidget(widget,1,column)
        selectors.setColumnStretch(2,1);layout.addLayout(selectors)
        args=QHBoxLayout();args.addWidget(self.parameters_label);args.addWidget(self.parameters,1);layout.addLayout(args)
        command=QHBoxLayout();command.addWidget(self.raw,1);command.addWidget(self.send);layout.addLayout(command)
        layout.addWidget(self.hint)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setMaximumBlockCount(500);self.output.setMinimumHeight(130)
        layout.addWidget(self.output);TouchScroll_Enable(self.output)
        for combo in (self.category,self.choice):TouchScroll_Enable(combo.view())
        self.category.currentIndexChanged.connect(self._module_changed)
        self.choice.currentIndexChanged.connect(self._command_changed)
        self.instance.textChanged.connect(self._controls_changed);self.parameters.textChanged.connect(self._controls_changed)
        self.raw.textChanged.connect(self._raw_changed);self.send.clicked.connect(self._send);self.raw.returnPressed.connect(self._send)
        self.clear_display.clicked.connect(self.output.clear)
        self.retranslate()

    def _spec(self):
        key=self.choice.currentData()
        return next((row for row in self._catalog if row.module+' '+row.verb==key),None)

    @property
    def expected_uart(self):
        from copy import deepcopy
        declaration = self._declaration.get('maintenance')
        return deepcopy(declaration.get('uart')) if isinstance(declaration, dict) else None

    def _rebuild(self):
        manual=self.raw.text() if self._manual else None
        module=self.category.currentData();verb=self.choice.currentData()
        self._catalog=ConsoleCatalog_Get(self._runtime_caps.get('file_service_version')=='1' and self._runtime_caps.get('supported')=='1')
        order=('SYSTEM','GNSS','IMU','BARO','MAG','ATTITUDE','TELEMETRY','POWER','CAL','ALIGN','ESTIMATOR','INS','LOG','LOGFILE','TIME')
        modules={row.module for row in self._catalog}
        self._updating=True;self.category.clear()
        for name in order:
            if name in modules:self.category.addItem(name,name)
        self.category.setCurrentIndex(max(0,self.category.findData(module)))
        self._updating=False;self._module_changed()
        if self.choice.findData(verb)>=0:self.choice.setCurrentIndex(self.choice.findData(verb))
        if manual is not None:
            self._updating=True;self.raw.setText(manual);self._updating=False;self._manual=True
        self._changed()

    def retranslate(self):
        self.title.setText(Text(self.i18n,'命令输入','Command input'))
        self.clear_display.setText(Text(self.i18n,'清空响应显示','Clear response display'))
        self.clear_display.setToolTip(Text(self.i18n,'仅清空下方显示；不清理串口缓冲、解析器或正在执行的事务。','Clear displayed text only; keep serial buffers, parser and active transactions unchanged.'))
        self.category_label.setText(Text(self.i18n,'类别','Category'));self.instance_label.setText(Text(self.i18n,'实例','Instance'))
        self.command_label.setText(Text(self.i18n,'命令','Command'));self.parameters_label.setText(Text(self.i18n,'参数','Arguments'))
        self.send.setText(Text(self.i18n,'发送','Send'));self.raw.setPlaceholderText(Text(self.i18n,'可直接输入完整命令','Or enter a complete command'))
        self._rebuild();self._protocol_render()

    def set_protocol_declaration(self,metadata,*,loading=False):
        self._declaration=dict(metadata or {});self.declaration_loading=bool(loading)
        self._protocol_render();self.declaration_changed.emit()

    def Verification_SetNote(self,note):
        self._verification_note=note;self._protocol_render()

    def set_runtime_capabilities(self,caps):
        caps=dict(caps or {})
        if caps==self._runtime_caps:return
        self._runtime_caps=caps;self._rebuild();self._protocol_render()

    def _protocol_render(self):
        declared=self._declaration.get('maintenance','absent')
        profile=declared.get('profile','') if isinstance(declared,dict) else ''
        expected={'maintenance.serial.0_0':'0.0','maintenance.serial.0_1':'0.1'}.get(profile)
        if declared=='absent':label=Text(self.i18n,'协议未声明','Protocol undeclared')
        elif declared is None:label=Text(self.i18n,'工程未启用维护协议','Maintenance disabled in project')
        else:label=Text(self.i18n,'声明 '+(expected or '未识别'),'Declared '+(expected or 'unrecognized'))
        file_v1=self._runtime_caps.get('file_service_version')=='1' and self._runtime_caps.get('supported')=='1'
        actual=self._runtime_caps.get('maintenance')
        if actual:label+=Text(self.i18n,' · 设备 '+actual,' · Device '+actual)
        elif expected:label+=Text(self.i18n,' · 版本待确认',' · Version unconfirmed')
        if file_v1:label+=Text(self.i18n,' · 文件服务已确认',' · File service confirmed')
        elif self._runtime_caps.get('legacy_response'):label+=Text(self.i18n,' · 旧接口已响应',' · Legacy interface responded')
        else:label+=Text(self.i18n,' · 等待设备确认',' · Awaiting device response')
        mismatch=(actual and expected and expected not in (actual,self._runtime_caps.get('compatible')) or
                  self._runtime_caps and declared is None)
        if mismatch:label+=Text(self.i18n,' · 声明与能力不同',' · Declaration/capability differ')
        if self._verification_note:label+=' · '+self._verification_note
        self.protocol_status.setText(label)
        self.protocol_status.setToolTip(str(self._declaration)+'\n'+str(self._runtime_caps))

    def _module_changed(self,*_):
        if self._updating:return
        self._updating=True;self.choice.clear()
        for row in self._catalog:
            if row.module==self.category.currentData():self.choice.addItem(row.verb,row.module+' '+row.verb)
        self._updating=False;self._command_changed()

    def _command_changed(self,*_):
        if self._updating:return
        row=self._spec();self._updating=True
        self.parameters.setText(row.default if row else '')
        self.parameters.setPlaceholderText(row.parameters if row else '')
        self.instance.setText(self._last_instance if row and row.indexed else '')
        self._updating=False;self._controls_changed()

    def _controls_changed(self,*_):
        if self._updating:return
        row=self._spec()
        if row and row.indexed and self.instance.hasAcceptableInput():self._last_instance=self.instance.text()
        parts=[row.module] if row else []
        if row and row.indexed:parts.append(self.instance.text().strip())
        if row:parts.append(row.verb)
        if self.parameters.text().strip():parts.append(self.parameters.text().strip())
        self._updating=True;self.raw.setText(' '.join(parts));self._updating=False;self._manual=False;self._changed()

    def _raw_changed(self,*_):
        if not self._updating:self._manual=True;self._changed()

    def _command(self):return self.raw.text()

    def _changed(self,*_):
        row=self._spec()
        for widget in (self.category,self.choice,self.raw):widget.setEnabled(not self.busy)
        self.instance.setEnabled(bool(row and row.indexed and not self.busy))
        self.parameters.setEnabled(bool(row and row.parameters and not self.busy))
        self.parameters.setVisible(bool(row and row.parameters))
        self.parameters_label.setVisible(bool(row and row.parameters))
        try:
            command=ConsoleCommand_Validate(self._command(),allow_raw=True);valid=True
            if not self._manual and row:
                valid=bool((not row.indexed or self.instance.hasAcceptableInput()) and
                           (not row.required or self.parameters.text().strip()))
            note=Text(self.i18n,'响应显示在下方。','Responses appear below.')
            if not ConsoleCommand_IsKnown(command):note=Text(self.i18n,'此命令未在目录核实，发送前将确认。','Unlisted command; confirmation required before sending.')
            if command.startswith('LOGFILE READ'):note=Text(self.i18n,'token 使用 META 返回值；读取响应显示在下方。','Use the token from META; read responses appear below.')
        except ValueError as exc:valid=False;note=str(exc)
        self.send.setEnabled(bool(valid and self.connected and not self.busy))
        self.hint.setText((Text(self.i18n,'维护串口未连接。','Maintenance port disconnected. ') if not self.connected else '')+note)

    def _send(self):
        if not self.send.isEnabled():return
        command=ConsoleCommand_Validate(self._command(),allow_raw=True)
        if command.upper()=='LOGFILE ENTER':
            question=Text(self.i18n,'进入维护模式将停止记录并阻止 START，需重启恢复。继续？','Maintenance stops logging and blocks START until reboot. Continue?')
        elif not ConsoleCommand_IsKnown(command):
            question=Text(self.i18n,'此命令尚未核实，将原样发送一个命令。继续？','This command is unverified and will be sent as one line. Continue?')
        else:question=''
        if question and QMessageBox.question(self,self.title.text(),question,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.send_requested.emit(command)

    def set_connection(self,connected,busy=False):
        previous=self.connected;self.connected=bool(connected);self.busy=bool(busy)
        if not connected:self.set_runtime_capabilities({})
        self._changed()
        if previous and not connected and self.output.toPlainText():
            self.output.appendPlainText(Text(self.i18n,'[已断开；以上为历史响应]','[Disconnected; preceding responses are historical]'))

    def show_response(self,command,response,error=''):
        text='> '+command+'\n'+response
        if error:text+='\n'+Text(self.i18n,'错误：','Error: ')+error
        self.output.appendPlainText(text.rstrip())
        if not error:
            summary=ConsoleResponse_Summary(command,response,self.i18n)
            if summary:self.output.appendPlainText(summary)
