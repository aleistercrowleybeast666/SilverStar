"""Normal maintenance entry for the bounded, shared-owner installation workflow."""
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QSpinBox, QComboBox, QFileDialog)

from services.installation_calibration_backend import InstallationBackend, InstallationResult
from services.installation_calibration_worker import InstallationWorker, InstallationJob
from transport.installation_owner import InstallationOwnerProvider


class InstallationDialog(QDialog):
    sessionClosed = Signal()

    def __init__(self, owner, data_directory, parent=None, *, backend=None):
        super().__init__(parent)
        self.setWindowTitle('安装标定 / Installation calibration')
        self.setMinimumSize(650, 500)
        self.resize(780, 620)
        self.directory = Path(data_directory)
        self.backend = backend or InstallationBackend(InstallationOwnerProvider(owner, enabled=True))
        self.worker = InstallationWorker(self.backend)
        self._pending = None
        self._closing = False
        self._closed = False
        self._session = False
        self._candidate = False
        self._candidate_path = None
        self._attempts = {face: 0 for face in ('XP', 'XN', 'YP', 'YN', 'ZP', 'ZN')}
        root = QVBoxLayout(self)
        note = QLabel('复用已连接的维护接口。每面只开始一次，由目标连续采集 TRAIN → HOLDOUT。\n'
                      '应用、保存和重启加载需要目标分别声明并实现；软件候选不代表已应用校正。', self)
        note.setWordWrap(True); root.addWidget(note)
        source = QGroupBox('01 连接与来源 / Connection and sources', self)
        source_layout = QGridLayout(source)
        self.imu, self.mag = QSpinBox(source), QSpinBox(source)
        for control in (self.imu, self.mag): control.setRange(0, 255)
        source_layout.addWidget(QLabel('IMU 实例'), 0, 0); source_layout.addWidget(self.imu, 0, 1)
        source_layout.addWidget(QLabel('MAG 实例'), 0, 2); source_layout.addWidget(self.mag, 0, 3)
        self.probe = QPushButton('核对目标能力 / Check capabilities', source)
        self.probe.clicked.connect(lambda: self.Job_Submit('probe'))
        source_layout.addWidget(self.probe, 1, 0, 1, 4)
        self.capabilities = QLabel('合同 / 采集 / 应用 / 保存：尚未查询', source)
        self.capabilities.setWordWrap(True); source_layout.addWidget(self.capabilities, 2, 0, 1, 4)
        self.begin = QPushButton('建立采集会话并选择原始归档…', source)
        self.begin.clicked.connect(self.Session_Begin)
        source_layout.addWidget(self.begin, 3, 0, 1, 4); root.addWidget(source)
        capture = QGroupBox('02 六面采集 / Six-face capture', self)
        capture_layout = QGridLayout(capture)
        self.mode = QComboBox(capture)
        self.mode.addItem('拟合 + 留出采集 / TRAIN then HOLDOUT', 'FIT_CHECK')
        self.mode.addItem('新鲜验证 / CHECK_ONLY', 'CHECK_ONLY')
        capture_layout.addWidget(self.mode, 0, 0, 1, 3)
        self.faces = {}
        for index, face in enumerate(self._attempts):
            button = QPushButton(face + '  未采集', capture)
            button.clicked.connect(lambda checked=False, value=face: self.Face_Begin(value))
            capture_layout.addWidget(button, 1 + index//3, index%3)
            self.faces[face] = button
        hint = QLabel('补采 TRAIN 后，需要覆盖全部六面的新鲜 HOLDOUT。已观察的旧验证保留为历史，不回填为训练数据。', capture)
        hint.setWordWrap(True); capture_layout.addWidget(hint, 3, 0, 1, 3); root.addWidget(capture)
        evaluate = QGroupBox('03 求解与候选 / Fit and candidate', self)
        actions = QHBoxLayout(evaluate)
        self.fit = QPushButton('求解并验证', evaluate)
        self.fit.clicked.connect(lambda: self.Job_Submit('fit'))
        self.export = QPushButton('导出完整候选…', evaluate)
        self.export.clicked.connect(self.Candidate_Export)
        actions.addWidget(self.fit); actions.addWidget(self.export); root.addWidget(evaluate)
        active = QGroupBox('04 应用与保存 / Active correction', self)
        active_layout = QVBoxLayout(active)
        active_actions = QHBoxLayout()
        self.apply = QPushButton('应用并核对 RAM', active)
        self.save = QPushButton('保存并读回核对', active)
        self.verify_saved = QPushButton('核对已保存 / 重启加载…', active)
        self.apply.clicked.connect(lambda: self.Job_Submit('apply',candidate_path=self._candidate_path))
        self.save.clicked.connect(lambda: self.Job_Submit('save'))
        self.verify_saved.clicked.connect(self.Saved_Verify)
        for button in (self.apply,self.save,self.verify_saved): active_actions.addWidget(button)
        active_layout.addLayout(active_actions)
        self.active_status = QLabel('未应用到 RAM · 未保存活动校正 · 未核对重启加载', active)
        self.active_status.setWordWrap(True);active_layout.addWidget(self.active_status);root.addWidget(active)
        self.status = QLabel('先核对目标能力；实际不合格来源会显示具体阻塞原因。', self)
        self.status.setWordWrap(True); root.addWidget(self.status, 1)
        footer = QHBoxLayout()
        self.cancel = QPushButton('取消当前操作', self); self.cancel.clicked.connect(self.worker.Cancel)
        self.finish = QPushButton('结束会话 / Close', self); self.finish.clicked.connect(self.reject)
        footer.addWidget(self.cancel); footer.addStretch(1); footer.addWidget(self.finish); root.addLayout(footer)
        self.timer = QTimer(self); self.timer.setInterval(50); self.timer.timeout.connect(self.Worker_Poll); self.timer.start()
        self.Controls_Update()

    def Job_Submit(self, action, **arguments):
        if self._closing or self._pending is not None: return
        result = self.worker.Submit(InstallationJob(action, tuple(arguments.items())))
        self.status.setText(result.reason)
        if result.result is InstallationResult.Ok: self._pending = (action, arguments)
        self.Controls_Update()

    def Session_Begin(self):
        path, _ = QFileDialog.getSaveFileName(self, '保留原始采集 / Raw archive',
            str(self.directory / ('installation-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.jsonl')),
            'Raw archive (*.jsonl)')
        if path: self.Job_Submit('begin', archive_path=path, imu_instance=self.imu.value(), mag_instance=self.mag.value())

    def Face_Begin(self, face):
        attempt = self._attempts[face] + 1
        self.Job_Submit('face', face=face, attempt=attempt,
            stage='SIX_FACE' if attempt == 1 else 'SUPPLEMENT', mode=self.mode.currentData())

    def Candidate_Export(self):
        path, _ = QFileDialog.getSaveFileName(self, '完整软件候选 / Complete software candidate',
            str(self.directory / 'installation-candidate.ssic'), 'Candidate (*.ssic)')
        if path: self.Job_Submit('export', path=path)

    def Controls_Update(self):
        idle = self._pending is None and not self._closing
        caps = self.backend.capabilities
        self.probe.setEnabled(idle and not self._session)
        self.begin.setEnabled(idle and not self._session and caps is not None and caps.capture_available)
        for control in (self.imu, self.mag): control.setEnabled(idle and not self._session)
        for button in self.faces.values(): button.setEnabled(idle and self._session)
        self.mode.setEnabled(idle and self._session)
        self.fit.setEnabled(idle and self._session)
        self.export.setEnabled(idle and self._candidate)
        self.apply.setEnabled(idle and self._candidate_path is not None and not self._session
            and caps is not None and caps.apply_supported and self.backend.lease is None)
        self.save.setEnabled(idle and caps is not None and caps.save_supported
            and self.backend.status=='APPLIED_NOT_SAVED')
        self.verify_saved.setEnabled(idle and not self._session and caps is not None and caps.active_record==3
            and self.backend.lease is None)
        for button in (self.apply,self.save):
            button.setToolTip('需要完整冻结候选、目标来源资格、当前依赖和实际读回；不满足时保持关闭。')
        self.cancel.setEnabled(self._pending is not None and not self._closing)

    def Worker_Poll(self):
        for progress in self.worker.TakeProgress():
            self.status.setText(' · '.join(str(value) for value in progress))
        result = self.worker.TakeResult()
        if result is not None:
            action, arguments = self._pending or ('', {})
            self._pending = None
            self.status.setText(result.result.value + ' · ' + result.reason)
            if action == 'begin': self._session = result.result is InstallationResult.Ok
            if action == 'face' and result.result is InstallationResult.Ok:
                face = arguments['face']; self._attempts[face] = arguments['attempt']
                self.faces[face].setText(face + '  已采集 / captured')
                self._candidate = False
            if action == 'fit': self._candidate = result.result is InstallationResult.CandidateOnly
            if action == 'export' and result.result is InstallationResult.CandidateOnly:
                self._session = False
                self._candidate_path = arguments['path']
            if action in ('apply','save','verify_saved'):
                detail=result.detail if isinstance(result.detail,dict) else {}
                if result.result is InstallationResult.Ok:
                    self.active_status.setText('RAM 代次：'+detail.get('applied_generation','—')
                        +' · 保存代次：'+detail.get('saved_generation','—')
                        +' · '+('已确认重启加载' if detail.get('loaded')=='1' else '未观察到重启加载'))
                else: self.active_status.setText('目标结果未确认，请核对当前记录；'+result.reason)
            if self.backend.status in ('CLOSED', 'UNKNOWN'): self._session = False
            caps = self.backend.capabilities
            if caps is not None:
                values = (caps.contract_supported, caps.capture_available, caps.apply_supported, caps.save_supported)
                self.capabilities.setText(' · '.join(name + ('：可用' if value else '：不可用')
                    for name, value in zip(('合同', '采集', '目标应用', '目标保存'), values)) + '\n' + caps.blocking_reason)
            self.Controls_Update()
        if self._closing and self.worker.Stopped_Get() and not self._closed:
            self._closed = True; self.timer.stop()
            self.sessionClosed.emit(); super().reject()

    def Saved_Verify(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择对应的完整候选以核对稳定身份',
            self._candidate_path or str(self.directory), 'Candidate (*.ssic)')
        if path: self.Job_Submit('verify_saved',candidate_path=path)

    def Close_Request(self):
        if self._closed: return True
        self._closing = True; self.worker.Stop_Request()
        self.status.setText('停止采集并等待唯一维护 owner 完成清理…')
        self.Controls_Update(); self.Worker_Poll()
        return self._closed

    def reject(self):
        self.Close_Request()

    def closeEvent(self, event):
        if self.Close_Request(): event.accept()
        else: event.ignore()
