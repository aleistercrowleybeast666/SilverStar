"""V1 review counterexamples exercised against v2, without creating Qt widgets."""
import ast
from collections import deque
from enum import Enum
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import threading
import pytest
ROOT = Path(__file__).parents[2]
FLP = 'apps/FLP/src/silverstar_flp/ui/main_window.py'

def source_function(relative, name, cls=None, globals_=None):
    path = ROOT / relative
    tree = ast.parse(path.read_text(encoding='utf-8'))
    body = tree.body if cls is None else next((n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls))
    node = next((n for n in body if isinstance(n, ast.FunctionDef) and n.name == name))
    node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(globals_ or {})
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace[name]

@pytest.mark.parametrize('custom', [True, False])
def test_retirement_respects_unverified_export_and_save(custom):

    class Retirement(Enum):
        RETIRED = 'retired'
    worker = NS(context=NS(cancellation_event=NS(is_set=lambda: False)), Worker_Retire=lambda _: Retirement.RETIRED)
    action = lambda: NS(setEnabled=Mock(), setVisible=Mock())
    fake = NS(_worker_retiring=False, _active_worker=worker, _worker_finished_seen=True, _worker_publication_depth=0, _thread_pool=NS(waitForDone=lambda _: True), _worker_retire_timer=NS(stop=Mock()), _folder_search_worker=None, _dataset=NS(metadata={'custom_decoder_unverified': custom}), _channel_resolver=object(), _worker_connections=[], _source_restore_pending=None, taskSettled=NS(emit=Mock()), export_dialog=NS(Task_Finish=Mock()), replay_page=NS(Task_Finish=Mock()))
    for name in ('progress_bar', 'cancel_button', 'import_action', 'export_action', 'open_project_action', 'open_silverstar_project_action', 'save_project_action', 'save_project_as_action', 'new_project_action'):
        setattr(fake, name, action())
    source_function(FLP, '_Task_RetireTry', 'MainWindow', {'WorkerRetireResult': Retirement})(fake)
    for name in ('export_action', 'save_project_action', 'save_project_as_action'):
        assert getattr(fake, name).setEnabled.call_args.args == (not custom,)

@pytest.mark.parametrize('method,args', [('_ExportDialog_Show', ()), ('_Export_Start', (object(), object())), ('_Replay_Start', ('custom', object()))])
@pytest.mark.parametrize('custom', [True, False])
def test_exact_actions_guard_missing_resolver_or_custom_view(method, args, custom):
    fake = NS(_dataset=NS(metadata={'custom_decoder_unverified': custom}), _channel_resolver=None)
    source_function(FLP, method, 'MainWindow')(fake, *args)

@pytest.mark.parametrize('stage', ['prepare', 'insert'])
def test_custom_publication_failure_is_atomic(stage):
    old_dataset, old_project, old_store = (object(), object(), object())
    prepared = NS(Dataset_Set=Mock(side_effect=ValueError('reject') if stage == 'prepare' else None), deleteLater=Mock())
    fake = NS(_translator=object(), _dataset=old_dataset, _project=old_project, _replay_store=old_store, explorer_page=object(), custom_decoder_banner=NS(show=Mock()), pages=NS(indexOf=lambda _: 4, insertWidget=Mock(side_effect=ValueError('insert')), removeWidget=Mock()))
    with pytest.raises(ValueError):
        source_function(FLP, '_CustomView_Set', 'MainWindow', {'DataExplorerPage': lambda _: prepared, 'ProjectDocument': lambda: object(), 'ReplayResultStore': lambda: object()})(fake, NS(dataset=object()))
    assert fake._dataset is old_dataset and fake._project is old_project and (fake._replay_store is old_store)
    fake.custom_decoder_banner.show.assert_not_called()
    prepared.deleteLater.assert_called_once()

def test_custom_publication_commits_raw_view_and_label():
    prepared = NS(Dataset_Set=Mock(), deleteLater=Mock())
    old = NS(deleteLater=Mock())
    items = [NS(flags=lambda: 1, setFlags=Mock()) for _ in range(6)]
    fake = NS(_translator=object(), explorer_page=old, _page_widgets=(object(), object(), object(), object(), old, object()), custom_decoder_banner=NS(show=Mock()), time_range=NS(hide=Mock()), pages=NS(indexOf=lambda _: 4, insertWidget=Mock(), removeWidget=Mock(), setCurrentIndex=Mock()), navigation_list=NS(count=lambda: 6, item=lambda i: items[i], setCurrentRow=Mock()), _Project_SetDirty=Mock(), _ProjectHeader_Refresh=Mock(), status_label=NS(setText=Mock()))
    for name in ('save_project_action', 'save_project_as_action', 'export_action'):
        setattr(fake, name, NS(setEnabled=Mock()))
    data = NS(metadata={'custom_decoder_unverified': True})
    result = NS(dataset=data, source_package_path=Path('custom.ssdecoder'))
    assert source_function(FLP, '_CustomView_Set', 'MainWindow', {'DataExplorerPage': lambda _: prepared, 'ProjectDocument': lambda: object(), 'ReplayResultStore': lambda: object(), 'Qt': NS(ItemFlag=NS(ItemIsEnabled=1))})(fake, result)
    assert fake._dataset is data and fake._channel_resolver is None and (fake.explorer_page is prepared)
    prepared.Dataset_Set.assert_called_once_with(data)
    fake.custom_decoder_banner.show.assert_called_once()
    old.deleteLater.assert_called_once()
    assert 'custom.ssdecoder' in fake.status_label.setText.call_args.args[0]
    for i, item in enumerate(items):
        assert item.setFlags.call_args.args == (int(i == 4),)
