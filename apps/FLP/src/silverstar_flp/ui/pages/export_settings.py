from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from silverstar_flp.core.i18n import Translator
from silverstar_flp.export.service import (
    ExportLanguage,
    ExportManifest,
    ExportOptions,
    ExportTheme,
)
from silverstar_flp.ui.touch_scroll import TouchScroll_Enable
from silverstar_flp.ui.widgets import StandardComboBox


class ImportDialog(QDialog):
    importRequested = Signal(object, object)
    folderSearchRequested = Signal(object)

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setModal(True)
        self.resize(720, 390)
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        self.source_group = QGroupBox()
        form = QFormLayout(self.source_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.source_type_label = QLabel()
        self.source_type_combo = StandardComboBox()
        self.source_type_combo.currentIndexChanged.connect(self._SourceType_Changed)
        form.addRow(self.source_type_label, self.source_type_combo)

        self.source_file_label = QLabel()
        log_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self._Import_Request)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._Log_Browse)
        log_row.addWidget(self.path_edit, 1)
        log_row.addWidget(self.browse_button)
        form.addRow(self.source_file_label, log_row)

        self.decoder_file_label = QLabel()
        decoder_row = QHBoxLayout()
        self.decoder_path_edit = QLineEdit()
        self.decoder_path_edit.returnPressed.connect(self._Import_Request)
        self.decoder_browse_button = QPushButton()
        self.decoder_browse_button.clicked.connect(self._Decoder_Browse)
        decoder_row.addWidget(self.decoder_path_edit, 1)
        decoder_row.addWidget(self.decoder_browse_button)
        form.addRow(self.decoder_file_label, decoder_row)

        self.folder_label = QLabel()
        folder_row = QHBoxLayout()
        self.folder_path_edit = QLineEdit()
        self.folder_browse_button = QPushButton()
        self.folder_browse_button.clicked.connect(self._Folder_Browse)
        self.folder_search_button = QPushButton()
        self.folder_search_button.clicked.connect(self._FolderSearch_Request)
        folder_row.addWidget(self.folder_path_edit, 1)
        folder_row.addWidget(self.folder_browse_button)
        folder_row.addWidget(self.folder_search_button)
        form.addRow(self.folder_label, folder_row)

        self.candidate_label = QLabel()
        self.candidate_combo = StandardComboBox()
        form.addRow(self.candidate_label, self.candidate_combo)
        layout.addWidget(self.source_group)

        self.note_label = QLabel()
        self.note_label.setObjectName("muted")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)
        self.result_label = QLabel()
        self.result_label.setObjectName("warningLabel")
        self.result_label.setWordWrap(True)
        self.result_label.hide()
        layout.addWidget(self.result_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self.reject)
        self.import_button = QPushButton()
        self.import_button.setObjectName("primaryButton")
        self.import_button.clicked.connect(self._Import_Request)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.import_button)
        layout.addLayout(button_row)
        self.Language_Apply(translator)

    def _SourceType_Changed(self) -> None:
        manual = str(self.source_type_combo.currentData() or "manual") == "manual"
        for widget in (
            self.path_edit,
            self.browse_button,
            self.decoder_path_edit,
            self.decoder_browse_button,
        ):
            widget.setEnabled(manual)
        for widget in (
            self.folder_path_edit,
            self.folder_browse_button,
            self.folder_search_button,
            self.candidate_combo,
        ):
            widget.setEnabled(not manual)

    def _Log_Browse(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.Text_Get("dialog.import.title"),
            str(Path.home()),
            "SilverStar flight logs (*.BIN *.bin *.SSLOG *.sslog);;All files (*)",
        )
        if selected:
            self.path_edit.setText(selected)

    def _Decoder_Browse(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.Text_Get("dialog.import.title"),
            str(Path.home()),
            "SilverStar decoder packages (*.ssdecoder);;All files (*)",
        )
        if selected:
            self.decoder_path_edit.setText(selected)

    def _Folder_Browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self._translator.Text_Get("import.folder_search"),
            self.folder_path_edit.text().strip() or str(Path.home()),
        )
        if selected:
            self.folder_path_edit.setText(selected)

    def Folder_Set(self, path: Path) -> None:
        self.folder_path_edit.setText(str(path))
        self.candidate_combo.clear()
        self.source_type_combo.setCurrentIndex(self.source_type_combo.findData("folder_search"))

    def _FolderSearch_Request(self) -> None:
        folder_text = self.folder_path_edit.text().strip()
        if not folder_text:
            self.result_label.setText(self._translator.Text_Get("import.folder_required"))
            self.result_label.show()
            return
        self.result_label.hide()
        self.folderSearchRequested.emit(Path(folder_text))

    def PairDiscovery_Set(self, discovery: object) -> None:
        self.candidate_combo.clear()
        pairs = tuple(getattr(discovery, "pairs", ()))
        for pair in pairs:
            label = (
                f"{pair.log_path.name}  +  {pair.decoder_package_path.name}  "
                f"[{pair.project_name} / {pair.firmware_version}]"
            )
            self.candidate_combo.addItem(label, pair)
        diagnostics = tuple(getattr(discovery, "diagnostics", ()))
        if len(pairs) == 1:
            self.candidate_combo.setCurrentIndex(0)
            self.result_label.setText(self._translator.Text_Get("import.exact_pair_found"))
        elif pairs:
            self.result_label.setText(self._translator.Text_Get("import.select_exact_pair"))
        else:
            detail = "\n".join(diagnostics)
            self.result_label.setText(
                self._translator.Text_Get("import.exact_pair_missing")
                + (f"\n{detail}" if detail else "")
            )
        self.result_label.show()

    def Paths_Set(
        self,
        *,
        log_path: Path | None = None,
        decoder_path: Path | None = None,
    ) -> None:
        if log_path is not None:
            self.path_edit.setText(str(log_path))
            self.folder_path_edit.setText(str(Path(log_path).parent))
        if decoder_path is not None:
            self.decoder_path_edit.setText(str(decoder_path))
        if log_path is not None and decoder_path is not None:
            index = self.source_type_combo.findData("manual")
            self.source_type_combo.setCurrentIndex(max(index, 0))

    def _Import_Request(self) -> None:
        source_type = str(self.source_type_combo.currentData() or "manual")
        if source_type == "folder_search":
            pair = self.candidate_combo.currentData()
            if pair is None:
                self._FolderSearch_Request()
                return
            self.result_label.hide()
            self.importRequested.emit(pair.log_path, pair.decoder_package_path)
            self.accept()
            return
        path_text = self.path_edit.text().strip()
        decoder_text = self.decoder_path_edit.text().strip()
        if not path_text or not decoder_text:
            self.result_label.setText(self._translator.Text_Get("import.path_required"))
            self.result_label.show()
            return
        self.result_label.hide()
        self.importRequested.emit(Path(path_text), Path(decoder_text))
        self.accept()

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        selected_type = self.source_type_combo.currentData() or "folder_search"
        self.source_type_combo.blockSignals(True)
        self.source_type_combo.clear()
        self.source_type_combo.addItem(translator.Text_Get("import.manual_pair"), "manual")
        self.source_type_combo.addItem(
            translator.Text_Get("import.folder_search"),
            "folder_search",
        )
        index = self.source_type_combo.findData(selected_type)
        self.source_type_combo.setCurrentIndex(max(index, 0))
        self.source_type_combo.blockSignals(False)

        self.setWindowTitle(translator.Text_Get("dialog.import.title"))
        self.source_group.setTitle(translator.Text_Get("dialog.import.source"))
        self.source_type_label.setText(translator.Text_Get("label.import_type"))
        self.source_file_label.setText(translator.Text_Get("label.log_file"))
        self.decoder_file_label.setText(translator.Text_Get("label.decoder_package"))
        self.folder_label.setText(translator.Text_Get("label.task_folder"))
        self.candidate_label.setText(translator.Text_Get("label.exact_pair"))
        self.browse_button.setText(translator.Text_Get("action.browse"))
        self.decoder_browse_button.setText(translator.Text_Get("action.browse"))
        self.folder_browse_button.setText(translator.Text_Get("action.browse"))
        self.folder_search_button.setText(translator.Text_Get("action.search"))
        self.cancel_button.setText(translator.Text_Get("action.dialog_cancel"))
        self.import_button.setText(translator.Text_Get("action.open_exact_pair"))
        self.note_label.setText(translator.Text_Get("import.read_only_note"))
        self.path_edit.setPlaceholderText(translator.Text_Get("import.flight_log_placeholder"))
        self.decoder_path_edit.setPlaceholderText(translator.Text_Get("import.decoder_placeholder"))
        self.folder_path_edit.setPlaceholderText(translator.Text_Get("import.folder_placeholder"))
        self._SourceType_Changed()


class ExportDialog(QDialog):
    exportRequested = Signal(object, object)
    manifestOpenRequested = Signal(object)

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._output_custom = False
        self._manifest_path: Path | None = None
        self._result_manifest: ExportManifest | None = None
        self.setModal(True)
        self.resize(680, 650)
        self.setMinimumSize(560, 500)

        layout = QVBoxLayout(self)
        self.destination_group = QGroupBox()
        form = QFormLayout(self.destination_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.folder_label = QLabel()
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(str(Path.cwd() / "exports"))
        self.folder_edit.textEdited.connect(self._Output_Customize)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._Folder_Browse)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.browse_button)
        form.addRow(self.folder_label, folder_row)

        self.export_language_label = QLabel()
        self.export_language_combo = StandardComboBox()
        form.addRow(self.export_language_label, self.export_language_combo)
        self.export_theme_label = QLabel()
        self.export_theme_combo = StandardComboBox()
        form.addRow(self.export_theme_label, self.export_theme_combo)
        self.export_source_label = QLabel()
        self.export_source_combo = StandardComboBox()
        self._source_options: tuple[tuple[str, str], ...] = ()
        form.addRow(self.export_source_label, self.export_source_combo)
        self.page_mode_label = QLabel()
        self.page_mode = StandardComboBox()
        for value in ("5", "10", "30", "60", "120", "Custom", "Current View", "Full"):
            self.page_mode.addItem(value, value)
        self.page_mode.setCurrentIndex(2)
        self.page_duration_label = QLabel()
        self.page_duration = QDoubleSpinBox()
        self.page_duration.setRange(.001, 8640000)
        self.page_duration.setDecimals(3)
        self.page_duration.setSuffix(" s")
        self.page_duration.setValue(30)
        self.page_duration.setVisible(False)
        self.page_duration_label.setVisible(False)
        self.page_mode.currentIndexChanged.connect(self._PageMode_Changed)
        form.addRow(self.page_mode_label, self.page_mode)
        form.addRow(self.page_duration_label, self.page_duration)
        self.gif_range_label = QLabel()
        self.gif_range = StandardComboBox()
        self.gif_range.addItem("Current View", "Current View")
        self.gif_range.addItem("Full", "Full")
        self.gif_range.currentIndexChanged.connect(self._GifMetadata_Refresh)
        form.addRow(self.gif_range_label, self.gif_range)
        self.gif_metadata = QLabel()
        self.gif_metadata.setWordWrap(True)
        form.addRow(self.gif_metadata)
        self._current_range = (0.0, 0.0)
        self._mission_duration = 0.0
        layout.addWidget(self.destination_group)

        self.items_group = QGroupBox()
        items_group_layout = QVBoxLayout(self.items_group)
        self.items_scroll = QScrollArea()
        TouchScroll_Enable(self.items_scroll)
        self.items_scroll.setWidgetResizable(True)
        self.items_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.items_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        items_widget = QWidget()
        self.items_layout = QVBoxLayout(items_widget)
        self.overview_check = QCheckBox()
        self.diagnostics_check = QCheckBox()
        self.events_check = QCheckBox()
        self.csv_check = QCheckBox()
        self.full_p_check = QCheckBox()
        self.plots_check = QCheckBox()
        self.trajectory_check = QCheckBox()
        self.gif_check = QCheckBox()
        self._checks = (
            self.overview_check,
            self.diagnostics_check,
            self.events_check,
            self.csv_check,
            self.full_p_check,
            self.plots_check,
            self.trajectory_check,
            self.gif_check,
        )
        for checkbox in self._checks:
            checkbox.setChecked(True)
            self.items_layout.addWidget(checkbox)
        self.items_layout.addStretch(1)
        self.items_scroll.setWidget(items_widget)
        items_group_layout.addWidget(self.items_scroll)
        layout.addWidget(self.items_group, 1)

        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        self.note_label.setObjectName("muted")
        layout.addWidget(self.note_label)
        self.result_label = QLabel("—")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        self.failure_details_edit = QPlainTextEdit()
        TouchScroll_Enable(self.failure_details_edit)
        self.failure_details_edit.setReadOnly(True)
        self.failure_details_edit.setMaximumHeight(170)
        self.failure_details_edit.setVisible(False)
        layout.addWidget(self.failure_details_edit)

        button_row = QHBoxLayout()
        self.failure_details_button = QPushButton()
        self.failure_details_button.clicked.connect(self._FailureDetails_Toggle)
        self.failure_details_button.setVisible(False)
        button_row.addWidget(self.failure_details_button)
        self.manifest_button = QPushButton()
        self.manifest_button.clicked.connect(self._ManifestOpen_Request)
        self.manifest_button.setVisible(False)
        button_row.addWidget(self.manifest_button)
        button_row.addStretch(1)
        self.close_button = QPushButton()
        self.close_button.clicked.connect(self.reject)
        self.export_button = QPushButton()
        self.export_button.setObjectName("primaryButton")
        self.export_button.clicked.connect(self._Export_Request)
        button_row.addWidget(self.close_button)
        button_row.addWidget(self.export_button)
        layout.addLayout(button_row)
        self.Language_Apply(translator)

    def Sources_Set(self, sources: tuple[tuple[str, str], ...]) -> None:
        self._source_options = sources
        self.export_source_combo.clear()
        self.export_source_combo.addItem(
            self._translator.Text_Get("export.source_follow_ui"), None
        )
        for source_id, label in sources:
            self.export_source_combo.addItem(label, source_id)

    def Range_Set(self, current, duration):
        self._current_range, self._mission_duration = current, duration
        self._GifMetadata_Refresh()

    def _GifMetadata_Refresh(self):
        from silverstar_flp.export.ranges import GifMetadata_Get

        interval = (
            (0.0, self._mission_duration)
            if self.gif_range.currentData() == "Full"
            else self._current_range
        )
        self.gif_metadata.setText(
            self._translator.Text_Get("export.gif_metadata", **GifMetadata_Get(*interval))
        )

    def _PageMode_Changed(self):
        custom = self.page_mode.currentData() == "Custom"
        self.page_duration.setVisible(custom)
        self.page_duration_label.setVisible(custom)

    def _Folder_Browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            self._translator.Text_Get("label.output_folder"),
            self.folder_edit.text(),
        )
        if selected:
            self._Output_Customize()
            self.folder_edit.setText(selected)

    def _Export_Request(self) -> None:
        folder_text = self.folder_edit.text().strip()
        if not folder_text:
            self.result_label.setText(self._translator.Text_Get("export.folder_required"))
            return
        source_id = self.export_source_combo.currentData()
        options = ExportOptions(
            source_mode="follow_ui" if source_id is None else "explicit",
            source_id=source_id,
            language=self.export_language_combo.currentData(),
            ui_language=self._translator.language,
            theme=self.export_theme_combo.currentData(),
            include_overview=self.overview_check.isChecked(),
            include_diagnostics=self.diagnostics_check.isChecked(),
            include_events=self.events_check.isChecked(),
            include_csv=self.csv_check.isChecked(),
            include_full_covariance_keyframes=self.full_p_check.isChecked(),
            include_plots=self.plots_check.isChecked(),
            include_trajectory_3d=self.trajectory_check.isChecked(),
            include_attitude_gif=self.gif_check.isChecked(),
            page_mode=self.page_mode.currentData(),
            page_duration=self.page_duration.value(),
            gif_range_mode=self.gif_range.currentData(),
        )
        self._ManifestPath_Set(None)
        self.export_button.setEnabled(False)
        self.result_label.setText(self._translator.Text_Get("export.running"))
        self.exportRequested.emit(Path(folder_text), options)

    def Result_Set(self, manifest: ExportManifest) -> None:
        self.export_button.setEnabled(True)
        self._result_manifest = manifest
        self._ManifestPath_Set(manifest.ManifestPath_Get())
        self._Result_Render()

    def Result_Error(self, message: str) -> None:
        self.export_button.setEnabled(True)
        self._result_manifest = None
        self._ManifestPath_Set(None)
        self._FailureDetails_Clear()
        self.result_label.setText(message)

    def Result_Clear(self) -> None:
        self._result_manifest = None
        self.result_label.setText("—")
        self._ManifestPath_Set(None)
        self._FailureDetails_Clear()

    def _Output_Customize(self) -> None:
        self._output_custom = True

    def OutputDirectory_Set(self, path: Path) -> None:
        if not self._output_custom:
            self.folder_edit.setText(str(Path(path)))

    def _ManifestPath_Set(self, path: Path | None) -> None:
        self._manifest_path = Path(path) if path is not None else None
        available = self._manifest_path is not None
        self.manifest_button.setEnabled(available)
        self.manifest_button.setVisible(available)

    def _ManifestOpen_Request(self) -> None:
        if self._manifest_path is not None:
            self.manifestOpenRequested.emit(self._manifest_path)

    def ManifestOpen_Error(self) -> None:
        self.result_label.setText(self._translator.Text_Get("export.manifest_open_failed"))

    def _Result_Render(self) -> None:
        manifest = self._result_manifest
        if manifest is None:
            return
        failure_count = len(manifest.failures)
        code = "export.complete_with_failures" if failure_count else "export.complete"
        lines = [
            self._translator.Text_Get(
                code,
                count=len(manifest.files),
                failures=failure_count,
            )
        ]
        if manifest.failures:
            lines.extend(
                (
                    "",
                    self._translator.Text_Get("export.failed_items"),
                    *(f"- {failure.localized_name}" for failure in manifest.failures),
                )
            )
        self.result_label.setText("\n".join(lines))
        details = []
        for failure in manifest.failures:
            details.extend(
                (
                    f"[{failure.item_id}] {failure.localized_name}",
                    (f"{self._translator.Text_Get('export.error_type')}: {failure.exception_type}"),
                    (
                        f"{self._translator.Text_Get('export.error_message')}: "
                        f"{failure.exception_message}"
                    ),
                    "",
                )
            )
        self.failure_details_edit.setPlainText("\n".join(details).rstrip())
        self.failure_details_button.setVisible(bool(manifest.failures))
        if not manifest.failures:
            self.failure_details_edit.setVisible(False)
        self._FailureDetailsButtonText_Update()

    def _FailureDetails_Clear(self) -> None:
        self.failure_details_edit.clear()
        self.failure_details_edit.setVisible(False)
        self.failure_details_button.setVisible(False)
        self._FailureDetailsButtonText_Update()

    def _FailureDetails_Toggle(self) -> None:
        self.failure_details_edit.setVisible(self.failure_details_edit.isHidden())
        self._FailureDetailsButtonText_Update()

    def _FailureDetailsButtonText_Update(self) -> None:
        code = (
            "action.hide_export_errors"
            if not self.failure_details_edit.isHidden()
            else "action.view_export_errors"
        )
        self.failure_details_button.setText(self._translator.Text_Get(code))

    def Task_Finish(self) -> None:
        self.export_button.setEnabled(True)

    def Theme_Set(self, theme: str) -> None:
        try:
            target = ExportTheme(theme)
        except ValueError:
            return
        index = self.export_theme_combo.findData(target.value)
        if index >= 0:
            self.export_theme_combo.setCurrentIndex(index)

    def Language_Apply(self, translator: Translator) -> None:
        self._translator = translator
        language = str(self.export_language_combo.currentData() or ExportLanguage.FOLLOW_UI.value)
        theme = str(self.export_theme_combo.currentData() or ExportTheme.FOLLOW_UI.value)

        self.export_language_combo.blockSignals(True)
        self.export_language_combo.clear()
        self.export_language_combo.addItem(
            translator.Text_Get("export.language_follow_ui"),
            ExportLanguage.FOLLOW_UI.value,
        )
        self.export_language_combo.addItem(
            translator.Text_Get("export.language_zh"), ExportLanguage.ZH.value
        )
        self.export_language_combo.addItem(
            translator.Text_Get("export.language_en"), ExportLanguage.EN.value
        )
        self.export_language_combo.setCurrentIndex(
            max(self.export_language_combo.findData(language), 0)
        )
        self.export_language_combo.blockSignals(False)

        self.export_theme_combo.blockSignals(True)
        self.export_theme_combo.clear()
        self.export_theme_combo.addItem(
            translator.Text_Get("export.language_follow_ui"),
            ExportTheme.FOLLOW_UI.value,
        )
        self.export_theme_combo.addItem(
            translator.Text_Get("theme.light"),
            ExportTheme.LIGHT.value,
        )
        self.export_theme_combo.addItem(
            translator.Text_Get("theme.dark"),
            ExportTheme.DARK.value,
        )
        self.export_theme_combo.setCurrentIndex(max(self.export_theme_combo.findData(theme), 0))
        self.export_theme_combo.blockSignals(False)

        self.setWindowTitle(translator.Text_Get("dialog.export.title"))
        self.gif_range_label.setText(translator.Text_Get("export.gif_range"))
        for key in ("Current View", "Full"):
            self.gif_range.setItemText(
                self.gif_range.findData(key), translator.Text_Get("export.range." + key)
            )
        self._GifMetadata_Refresh()
        self.page_mode_label.setText(translator.Text_Get("export.page_mode"))
        self.page_duration_label.setText(translator.Text_Get("range.duration"))
        for key in ("Custom", "Current View", "Full"):
            self.page_mode.setItemText(self.page_mode.findData(key),
                translator.Text_Get("export.range." + key))
        self.destination_group.setTitle(translator.Text_Get("dialog.export.destination"))
        self.folder_label.setText(translator.Text_Get("label.output_folder"))
        self.browse_button.setText(translator.Text_Get("action.browse"))
        self.export_language_label.setText(translator.Text_Get("label.export_language"))
        self.export_theme_label.setText(translator.Text_Get("label.export_theme"))
        self.export_source_label.setText(translator.Text_Get("export.source"))
        if self.export_source_combo.count():
            self.export_source_combo.setItemText(
                0, translator.Text_Get("export.source_follow_ui")
            )
        self.items_group.setTitle(translator.Text_Get("dialog.export.items"))
        labels = (
            "export.item.overview",
            "export.item.diagnostics",
            "export.item.events",
            "export.item.csv",
            "export.item.full_p_keyframes",
            "export.item.plots",
            "export.item.trajectory",
            "export.item.gif",
        )
        for checkbox, code in zip(self._checks, labels, strict=True):
            checkbox.setText(translator.Text_Get(code))
        self.note_label.setText(translator.Text_Get("export.note"))
        self.manifest_button.setText(translator.Text_Get("action.open_export_manifest"))
        self._FailureDetailsButtonText_Update()
        self.close_button.setText(translator.Text_Get("action.close"))
        self.export_button.setText(translator.Text_Get("action.export"))
        self._Result_Render()
