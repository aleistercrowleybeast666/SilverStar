"""Read-only product diagnosis; settings and descriptor copies stay private."""
from pathlib import Path
import hashlib, importlib.util, json, sys
import pytest

ROOT=Path(__file__).resolve().parents[2]
SELECTED=Path(sys.argv[1]).resolve()
LABEL=sys.argv[2]
OUT=Path(__file__).resolve().parent
sys.path.append(str(ROOT/'.venv/Lib/site-packages'))
sys.path[:0]=[str(SELECTED/'apps/SCG/src'),str(ROOT/'apps/FLP/src'),str(ROOT/'apps/FLP')]
def plugin(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'docs/evidence/nightly_software_20261008'/f'{name}.py')
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
normal=plugin('normal_test_paths')
private=plugin('closeout_test_paths')
records=[]
class Diagnosis:
    @pytest.fixture(autouse=True)
    def private_descriptor(self,request,tmp_path,monkeypatch):
        if request.node.name!='test_current_user_gui_open_recovers_ground_bindings_if_available':
            yield
            return
        original=Path('D:/stm32_project/SS_0_5_TEST_6/SilverStar.ssproject')
        if not original.is_file():
            yield
            return
        data=original.read_bytes()
        copy=tmp_path/'descriptor_copy/SilverStar.ssproject'
        copy.parent.mkdir()
        copy.write_bytes(data)
        records.append({'descriptorCopySha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
        original_constructor=request.module.Path
        monkeypatch.setattr(request.module,'Path',lambda value:copy if str(value)==str(original.as_posix()) else original_constructor(value))
        yield
        assert original.read_bytes()==data,'read-only source descriptor changed during isolated test'
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self,item):
        yield
        from PySide6.QtWidgets import QApplication
        from silverstar_fccg.ui.main_window import MainWindow
        from silverstar_fccg.project.air_link import GroundTargetIssues_Get
        for window in QApplication.instance().topLevelWidgets():
            if isinstance(window,MainWindow):
                records.append({'test':item.name,'enabled':window._model.ground_target.enabled,
                    'status':window.ground_target_page.status.text(),
                    'tooltip':window.ground_target_page.status.toolTip(),
                    'issueCodes':[i.code for i in GroundTargetIssues_Get(window._model,window._service.catalog)],
                    'generateEnabled':window.ground_target_page.generate_button.isEnabled(),
                    'privateProjectRoot':str(window._project_root)})
    def pytest_sessionfinish(self,session,exitstatus):
        (OUT/(LABEL+'-observations.json')).write_text(json.dumps({'exit':exitstatus,'selected':str(SELECTED),'records':records},indent=2),encoding='utf8')

names={
 'test_ground_board_recovery.py':['test_ground_selection_defaults_and_checkbox_visibility','test_current_user_gui_open_recovers_ground_bindings_if_available'],
 'test_ground_activity_configuration.py':['test_led_gui_keeps_defaults_until_explicit_binding','test_led_gui_restores_legacy_bindings_after_toggle','test_led_gui_rejects_ambiguous_board_declarations'],
 'test_ground_radio_editor.py':['test_legacy_single_ground_refresh_does_not_promote_or_rebind','test_ground_editor_order_initial_binding_and_reopen','test_ground_editor_caps_instances_at_four','test_ground_power_choices_only_allow_declared_values']}
cases=[str(SELECTED/'apps/SCG/tests'/file)+'::'+name for file,functions in names.items() for name in functions]
base=SELECTED/'apps/SCG/.work'/('gui_review_diag_'+LABEL)
raise SystemExit(pytest.main(['-p','no:cacheprovider',*cases,'-q','--tb=short','--basetemp='+str(base)],plugins=[normal,private,Diagnosis()]))
