"""A preview cannot overwrite a mission-range edit made after it was built."""
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.mission_functions import Functions_Derive
from silverstar_fccg.ui.main_window import MainWindow


def test_control_task_preview_rejects_changed_mission_ranges(qapp, workspace_root, tmp_path, monkeypatch):
    service = FccgService(workspace_root)
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=service)
    window._toolchain_checked = True
    window._model = service.ReferenceProject_Create('preview isolation')
    window._Project_Refresh()
    fixture = Path(__file__).parent/'fixtures/tuning_bundle_v1/kf6-pid.sstuning.json'
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *_args:
                        (str(fixture), 'TreeDiagram bundle (*.sstuning.json)'))
    errors = []
    window._Error_Show = lambda *args: errors.append(args)
    def preview(*_args, **kwargs):
        kwargs['check_box'].setChecked(True)
        # Model a pending editor completion during the modal event loop. This
        # is a real valid range, not a malformed fixture or artificial checksum.
        functions = Functions_Derive(window._model, service.catalog)
        telemetry = next(row for row in functions['functions'] if row['instance_id'] == 'telemetry')
        telemetry['start'] = {'kind':'stage_enter', 'stage_id':'ascent'}
        window._model.mission_functions = functions
        return QMessageBox.StandardButton.Apply
    window._MessageBox_Exec = preview
    try:
        window._ParameterProfile_Import('silverstar.algorithm.estimator.kf6')
        functions = window._model.mission_functions['functions']
        assert next(row for row in functions if row['instance_id']=='telemetry')['start'] == {
            'kind':'stage_enter', 'stage_id':'ascent'}
        assert not any(row['instance_id']=='controller' for row in functions)
        assert errors
    finally:
        window._MessageBox_Exec = lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard
        window.close()
