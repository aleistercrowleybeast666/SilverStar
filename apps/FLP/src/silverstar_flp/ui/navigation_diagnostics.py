"""Read-only four-group and landing inspection. Missing evidence stays unknown."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.mission import MissionLandingTimestamp_Get
from silverstar_flp.ui.touch_scroll import TouchScroll_Enable


class DiagnosticTableModel(QAbstractTableModel):
    def __init__(self, columns, translator, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.translator = translator
        self.rows = []

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                self.translator.Text_Get("diagnostic." + self.columns[section])
                if orientation == Qt.Orientation.Horizontal
                else section + 1
            )
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            column = self.columns[index.column()]
            value = self.rows[index.row()].get(column)
            kind = getattr(self, 'kind', '')
            prefix = ('result' if column == 'result' else
                      'landing_reason' if column == 'reason' and kind == 'landing' else
                      'reanchor_reason' if column == 'reason' and kind == 'gnss' else
                      'transition' if column == 'transition' else None)
            if value is not None and prefix:
                return self.translator.Text_Get(f'diagnostic.{prefix}.{value}')
            if column == 'quality' and value is not None:
                if value == 0:
                    return self.translator.Text_Get('diagnostic.quality_ok')
                return ' / '.join(self.translator.Text_Get(f'diagnostic.quality_bit.{bit}')
                                  for bit in range(11) if int(value) & (1 << bit))
            if column == 'failure' and value is not None:
                return self.translator.Text_Get('diagnostic.failure.' + value)
            if column == 'source' and value in ('Recorded', 'Recomputed'):
                return self.translator.Text_Get('diagnostic.source.' + value)
            if column == 'group' and value in (
                'position_en', 'position_u', 'velocity_en', 'velocity_u',
            ):
                return self.translator.Text_Get('diagnostic.group.' + value)
            if isinstance(value, bool):
                return self.translator.Text_Get('diagnostic.yes' if value else 'diagnostic.no')
            if value is None:
                return '—'
            if isinstance(value, float):
                return f'{value:.6g}'
            return str(value)
        return None

    def Rows_Set(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()


class NavigationDiagnostics(QWidget):
    def __init__(self, kind, translator, parent=None):
        super().__init__(parent)
        self.kind, self.translator = kind, translator
        self._rows = []
        self._origin = 0
        self._interval = (0, float('inf'))
        self._source_note = ''
        self._empty_reason = ''
        self._gnss_detail_columns = (
            'source', 'failure', 'quality', 'innovation', 'variance',
            'outage', 'consistency', 'inflation', 'factor', 'reanchor', 'reason',
        )
        columns = {
            "gnss": (
                "time", "group", "valid", "result", "nis", "integrity_state",
                "integrity_reason", "source", "failure", "quality", "innovation",
                "variance", "outage", "consistency", "inflation", "factor",
                "reanchor", "reason",
            ),
            "landing": (
                "time",
                "transition",
                "reason",
                "elapsed",
                "coverage",
                "still",
                "bad",
                "slope",
                "span",
                "baro_coverage",
            ),
            "mechanization": (
                "time",
                "source_sequence",
                "recorded_sequence",
                "dt",
                "start_difference",
                "end_difference",
                "theta",
                "dv",
                "passed",
            ),
        }[kind]
        layout = QVBoxLayout(self)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        if kind == "gnss":
            self.count_note = QLabel()
            self.count_note.setWordWrap(True)
            layout.addWidget(self.count_note)
            button_row = QHBoxLayout()
            self.details_button = QPushButton(translator.Text_Get('diagnostic.details'))
            self.details_button.setCheckable(True)
            self.details_button.toggled.connect(self._Columns_Refresh)
            button_row.addWidget(self.details_button)
            self.full_range_button = QPushButton(translator.Text_Get('diagnostic.full_range'))
            self.full_range_button.clicked.connect(lambda: self.TimeRange_Set(0, float('inf')))
            button_row.addWidget(self.full_range_button)
            button_row.addStretch(1)
            layout.addLayout(button_row)
        if kind == "landing":
            self.summary_label = QLabel()
            self.summary_label.setWordWrap(True)
            layout.addWidget(self.summary_label)
        self.table = QTableView()
        self.model = DiagnosticTableModel(columns, translator, self.table)
        self.model.kind = kind
        self.table.setModel(self.model)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        TouchScroll_Enable(self.table)
        layout.addWidget(self.table)
        if kind == 'gnss':
            self._Columns_Refresh()

    def _Columns_Refresh(self):
        if self.kind != 'gnss':
            return
        detailed = self.details_button.isChecked()
        for index, column in enumerate(self.model.columns):
            self.table.setColumnHidden(
                index, column in self._gnss_detail_columns and not detailed,
            )

    def _GnssRecordedRows_Build(self, dataset):
        recovery = {
            (r.payload['replay_epoch'], r.payload['source_sequence'],
             r.payload['estimator_present_timestamp_us']): r.payload
            for r in dataset.Records_Get('GNSS_RECOVERY')
        }
        rows = []
        unmapped = 0
        for record in dataset.Records_Get('GNSS_MEASUREMENT'):
            p = record.payload
            if 'group_update_result' not in p:
                unmapped += 1
                continue
            evidence = recovery.get((
                p['replay_epoch'], p['sequence'],
                p['estimator_present_timestamp_us'],
            ), {})
            for group, name in enumerate(('position_en', 'position_u',
                                          'velocity_en', 'velocity_u')):
                axes = (0, 1) if group % 2 == 0 else (2,)
                innovation = p[
                    'position_innovation_m' if group < 2 else 'velocity_innovation_mps'
                ]
                variance = p[
                    'position_variance_m2' if group < 2 else 'velocity_variance_m2ps2'
                ]
                row = dict(
                    timestamp_us=p['estimator_present_timestamp_us'],
                    source='Recorded', group=name,
                    valid=bool(p['valid_group_mask'] & (1 << group)),
                    result=p['group_update_result'][group],
                    nis=p['group_nis'][group],
                    innovation=tuple(innovation[a] for a in axes),
                    variance=tuple(variance[a] for a in axes),
                    replay_epoch=p['replay_epoch'], source_sequence=p['sequence'],
                    operation_sequence=p.get('position_operation_sequence' if group < 2
                                             else 'velocity_operation_sequence'),
                )
                for column, field in (('quality', 'quality_reject_mask'),
                                      ('outage', 'outage'),
                                      ('consistency', 'consistency_count'),
                                      ('inflation', 'inflation_attempt_count'),
                                      ('factor', 'inflation_factor'),
                                      ('reanchor', 'reanchor_count'),
                                      ('reason', 'reanchor_reason')):
                    row[column] = evidence[field][group] if field in evidence else None
                rows.append(row)
        return rows, unmapped

    def Dataset_Set(self, dataset, resolver):
        self._dataset, self._resolver = dataset, resolver
        self._origin = dataset.start_timestamp_us or 0
        self._rows = []
        entry = resolver.store.SourceEntry_Get(resolver.store.ActiveSource_Get().source_id)
        if self.kind == 'gnss':
            recorded, unmapped = self._GnssRecordedRows_Build(dataset)
            is_kf6 = entry is not None and entry.algorithm_id is not None and (
                entry.algorithm_id.endswith('.kf6')
            )
            replay_rows = tuple(entry.diagnostics.get('gnss_group_updates', ())) if entry else ()
            if is_kf6 and replay_rows:
                self._rows = [dict(row, source=f'Replay #{entry.run_index} · KF6')
                              for row in replay_rows]
                source_template = self.translator.Text_Get('diagnostic.gnss_replay_source')
                self._source_note = source_template.format(
                    index=entry.run_index,
                )
            elif is_kf6:
                self._rows = []
                self._source_note = self.translator.Text_Get('diagnostic.gnss_replay_missing')
            else:
                self._rows = recorded
                self._source_note = self.translator.Text_Get('diagnostic.gnss_recorded_source')
                if entry is not None:
                    self._source_note += ' · ' + self.translator.Text_Get(
                        'diagnostic.gnss_fallback_recorded',
                    )
            self._empty_reason = (
                'diagnostic.gnss_mapping_failed' if unmapped and not recorded
                else 'diagnostic.gnss_no_record' if not recorded and not entry
                else 'diagnostic.gnss_replay_missing' if is_kf6 and not replay_rows
                else 'diagnostic.gnss_no_window'
            )
            for row in self._rows:
                quality = row.get('quality')
                row['failure'] = ('liveness' if quality is not None and int(quality) & 257 else
                                  'quality' if quality else
                                  'estimator' if row.get('valid') and row.get('result') == 2 else
                                  'none' if row.get('valid') else 'unknown')
                row['integrity_state'] = row.get('integrity_state')
                row['integrity_reason'] = row.get('integrity_reason')
            self.note.setText(self.translator.Text_Get('diagnostic.gnss_note') +
                              '\n' + self._source_note)
        elif self.kind == 'landing':
            records = tuple(dataset.Records_Get('LANDING_DIAGNOSTIC'))
            for record in records:
                p = record.payload
                self._rows.append(dict(
                    timestamp_us=int(p["evaluation_timestamp_us"]),
                    transition=p["transition"],
                    reason=p["reset_reason"],
                    elapsed=p["candidate_elapsed_us"] * 1e-6,
                    coverage=p["valid_coverage"],
                    still=p["still_ratio"],
                    bad=p["maximum_bad_duration_us"] * 1e-3,
                    slope=p["baro_slope_mps"],
                    span=p["baro_span_m"],
                    baro_coverage=p["baro_coverage"],
                ))
            if records:
                self.note.setText(self.translator.Text_Get('diagnostic.landing_note'))
            else:
                configs = dataset.Records_Get('MISSION_CONFIG')
                enabled = bool(configs and configs[0].payload.get('landing_enable')
                               and int(configs[0].payload.get('landing_mode', -1)) == 2)
                key = ('diagnostic.landing_no_records' if enabled or not configs else
                       'diagnostic.landing_strategy_disabled')
                self.note.setText(self.translator.Text_Get(key))
            confirmed = MissionLandingTimestamp_Get(dataset)
            completed = [record for record in records
                         if int(record.payload.get('transition', -1)) == 3
                         and int(record.payload.get('candidate_start_timestamp_us', 0)) > 0
                         and confirmed is not None
                         and int(record.payload['candidate_start_timestamp_us']) <= confirmed]
            if completed:
                final = max(completed, key=lambda record: (
                    int(record.payload.get('evaluation_timestamp_us', record.timestamp_us)),
                    record.record_sequence,
                ))
                candidate = int(final.payload['candidate_start_timestamp_us'])
                self.summary_label.setText(self.translator.Text_Get(
                    'diagnostic.landing_summary',
                ).format(
                    candidate=(candidate - self._origin) * 1e-6,
                    confirmed=(confirmed - self._origin) * 1e-6,
                    duration=(confirmed - candidate) * 1e-6,
                ))
                self.summary_label.show()
            else:
                self.summary_label.clear()
                self.summary_label.hide()
        elif entry:
            report = entry.diagnostics.get('mechanization_verification', {})
            self.note.setText(self.translator.Text_Get('diagnostic.mechanization_note') + '\n' +
                             str(report.get('first_divergence', '—')))
            for p in report.get('intervals', ()):
                self._rows.append(
                    dict(
                        timestamp_us=p["timestamp_us"],
                        source_sequence=p.get("source_sequence"),
                        recorded_sequence=p["sequence"],
                        dt=p.get("dt_difference_s"),
                        start_difference=p.get("start_timestamp_difference_us"),
                        end_difference=p.get("end_timestamp_difference_us"),
                        theta=p.get("delta_theta_difference"),
                        dv=p.get("delta_velocity_difference"),
                        passed=p["passed"],
                    )
                )
        else:
            self.note.setText(self.translator.Text_Get('diagnostic.mechanization_note'))
        self.TimeRange_Set(*self._interval)

    def TimeRange_Set(self, start, end):
        self._interval = start, end
        visible = [dict(row, time=(row['timestamp_us']-self._origin)*1e-6)
                   for row in self._rows
                   if self.kind == 'landing' or
                   start <= (row['timestamp_us']-self._origin)*1e-6 <= end]
        self.model.Rows_Set(visible)
        if self.kind == 'landing':
            self.table.setVisible(bool(visible))
        if self.kind == 'gnss':
            counts = self.translator.Text_Get('diagnostic.gnss_counts').format(
                total=len(self._rows), visible=len(visible),
            )
            if not visible:
                counts += ' · ' + self.translator.Text_Get(self._empty_reason)
            self.count_note.setText(counts)
