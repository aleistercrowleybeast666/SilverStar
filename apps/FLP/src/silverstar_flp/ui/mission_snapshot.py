"""Read-only, structured presentation of the verified recorded SSMS snapshot."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout


_LABELS = {
    'mission_id': '任务编号', 'snapshot_sequence': '快照序号', 'commit_generation': '提交代次',
    'configuration_digest': '配置摘要', 'firmware_version': '固件版本', 'build_tag': '构建标识',
    'imu_rate_hz': 'IMU 频率 / Hz', 'navigation_rate_hz': '导航频率 / Hz',
    'mechanization_subsamples': '惯导子样本数', 'frequency_hz': '无线频率 / Hz',
    'bandwidth_hz': '带宽 / Hz', 'spreading_factor': '扩频因子', 'coding_rate': '编码率',
    'preamble_symbols': '前导符号数', 'packet_mtu': 'MTU / bytes', 'tx_power_dbm': '发射功率 / dBm',
    'family': '无线系列', 'module': '模块', 'historical_only': '历史配置', 'algorithm': '算法',
    'external_yaw_authoritative': '外部航向为权威输入', 'known_yaw_deg': '已知航向 / °',
    'selected_mask': '所选约束', 'required_mask': '必需约束', 'kind': '类型', 'body_axis': '机体轴',
    'weight': '权重', 'declination_deg': '磁偏角 / °', 'nav_azimuth_deg': '导航方位角 / °',
    'generation': '代次', 'mode': '任务校准模式', 'ready': '记录的就绪状态',
    'accel_bias_mps2': '加速度偏置 / m/s²', 'accel_scale': '加速度比例',
    'gyro_bias_radps': '角速度偏置 / rad/s', 'gyro_scale': '角速度比例',
    'instance': '实例', 'physical': '物理端点', 'path': '对象路径', 'sha256': 'SHA-256',
    'effective_mode':'实际校正来源','active_installation':'活动安装校准',
    'R_GA':'A → G 坐标变换','R_AM':'M → A 安装旋转',
    'saved_generation':'持久化代次','record_crc32':'记录 CRC32',
    'raw_archive_sha256':'原始归档 SHA-256','stable_dependency_sha256':'稳定依赖 SHA-256',
    'hardware_verified':'硬件验证','recorded_source_frame_qualified':'记录中声明的来源坐标系资格',
    'base_instance': '快照起始实例', 'profile_id': '配置编号',
    'imu_source_instance': 'IMU 来源实例', 'gnss_source_instance': 'GNSS 来源实例',
    'calibration_generation': 'IMU 校准代次', 'imu_correction_hash': 'IMU 校正摘要',
    'mag_calibration_generation': '磁力计校准代次', 'mag_calibration_set_hash': '磁校准集摘要',
    'descriptor': '描述符编号', 'device_class': '设备类别', 'driver': '驱动编号',
    'flags': '标志位', 'capabilities': '能力位', 'rate': '采样率',
    'driver_hash': '驱动摘要', 'model_hash': '型号摘要', 'algorithm_class': '算法类别',
    'name_hash': '名称摘要', 'key_hash': '参数键摘要', 'value': '值', 'axes': '各轴校正',
    'mag_generation': '磁校准代次', 'mag_hash': '磁校准摘要',
    'mag_set_hash': '磁校准集摘要', 'mag_instances': '磁力计实例',
}


class MissionSnapshotDialog(QDialog):
    def __init__(self, snapshot, translator, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translator.Text_Get('mission_snapshot.open'))
        self.resize(900, 620)
        self._zh = translator.Text_Get('mission_snapshot.open').startswith('记录')
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        self.tabs.tabBar().setStyleSheet("QTabBar::tab { min-width: 0px; padding: 6px 9px; }")
        layout.addWidget(self.tabs, 1)
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        state = snapshot.get('status', 'unavailable')
        self.status.setText(translator.Text_Get('mission_snapshot.' + ('verified' if state == 'verified' else 'unavailable'))
            + ('\n' + str(snapshot.get('reason', state)) if state != 'verified' else ''))
        if state == 'verified':
            for key, label in [('header', '任务'), ('radio', '无线'), ('alignment', '对准'),
                    ('devices', '设备'), ('algorithms', '算法'), ('parameters', '参数'),
                    ('calibration', '校准'), ('sources', '来源与身份')]:
                title = label if self._zh else key.replace('_', ' ').title()
                if key == 'parameters':
                    self._Parameters_Add(title, snapshot.get(key, ()), snapshot.get('parameter_dictionary', {}))
                else:
                    self._Section_Add(title, snapshot.get(key, {}))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(translator.Text_Get('action.close'))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _Parameters_Add(self, title, rows, dictionary):
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(['参数', '记录值', '单位', '记录键 / 类型'] if self._zh else
                                        ['Parameter', 'Recorded value', 'Unit', 'Recorded key / type'])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index, row in enumerate(rows):
            declaration = dictionary.get(str(row['key_hash']), {})
            fields = (declaration.get('name', '—'), str(row['value']), declaration.get('unit') or '—',
                      f"0x{row['key_hash']:08X} / {row['kind']}")
            for column, text in enumerate(fields):
                item = QTableWidgetItem(text)
                item.setToolTip((declaration.get('component', '') + '/' + text) if declaration and column == 0 else text)
                table.setItem(index, column, item)
        for column in (1, 2, 3):
            table.resizeColumnToContents(column)
        self.tabs.addTab(table, title)

    def _Section_Add(self, label, value):
        rows = []
        def visit(item, path='', depth=0):
            if len(rows) >= 256 or depth > 6:
                return
            if isinstance(item, dict):
                for key, child in item.items():
                    if key == 'value_bits':
                        continue
                    if key == 'module' and child == 'e32_400m20s':
                        child = 'E32-400M20S'
                    field = _LABELS.get(key, key.replace('_', ' ')) if self._zh else key.replace('_', ' ')
                    visit(child, (path + ' / ' if path else '') + field, depth + 1)
            elif isinstance(item, (list, tuple)):
                for index, child in enumerate(item[:128]):
                    visit(child, f'{path} [{index + 1}]', depth + 1)
            else:
                text = ('是' if item else '否') if self._zh and isinstance(item, bool) else str(item)
                rows.append((path, text if item is not None else '—'))
        visit(value)
        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(['记录字段', '记录值'] if self._zh else ['Recorded field', 'Recorded value'])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        for row, values in enumerate(rows):
            for column, text in enumerate(values):
                cell = QTableWidgetItem(text); cell.setToolTip(text); table.setItem(row, column, cell)
        self.tabs.addTab(table, label)
