"""Exercise publication guards with plain fakes; never instantiate Qt or a window."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock


def function_from_source(name):
    path=Path(__file__).parents[2]/'apps/FLP/src/silverstar_flp/ui/main_window.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MainWindow')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),method],type_ignores=[])
    ast.fix_missing_locations(module)
    namespace={'ReplayRequest':lambda **kwargs:kwargs}
    exec(compile(module,str(path),'exec'),namespace)
    return namespace[name]


def test_exact_publication_failure_keeps_unverified_banner_and_existing_view():
    plugin=NS(Parameters_Resolve=lambda *a:None,ProcessModelRevision_Resolve=lambda *a,**k:None,
              ParameterAudit_Get=lambda *a:{'config_source':'wrong provenance'})
    fake=NS(_registry=NS(Algorithm_Get=lambda _:plugin),_pending_new_project_path='pending',
            _Error_Show=Mock(),custom_decoder_banner=NS(hide=Mock()))
    configuration=dict(algorithm_id='test',mode='recorded',input_source='input',actual_values={},provenance='expected')
    project=NS(replay_configurations={'draft':configuration})
    result=NS(match_mode='exact_generation_profile',dataset=object())
    assert function_from_source('_LogOpenResult_Set')(fake,result,project) is False
    fake.custom_decoder_banner.hide.assert_not_called()
    fake._Error_Show.assert_called_once_with('project_parameter_provenance_invalid')


def test_custom_publication_routes_away_from_exact_project_binding():
    fake=NS(_CustomView_Set=Mock(return_value=True))
    result=NS(match_mode='user_custom_unverified')
    assert function_from_source('_LogOpenResult_Set')(fake,result,object()) is True
    fake._CustomView_Set.assert_called_once_with(result)


def test_changed_python_sources_parse_without_importing_apps():
    root=Path(__file__).parents[2]
    for relative in ('apps/GSHC/services/recovery_position.py','apps/GSHC/ui/recovery_panel.py',
                     'apps/FLP/src/silverstar_flp/ui/main_window.py',
                     'apps/FLP/src/silverstar_flp/ui/pages/export_settings.py',
                     'apps/SCG/src/silverstar_fccg/project/folder_contract.py'):
        ast.parse((root/relative).read_text(encoding='utf-8'),filename=relative)
