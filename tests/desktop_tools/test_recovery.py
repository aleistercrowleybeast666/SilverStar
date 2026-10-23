import ast
import math
from pathlib import Path
import pytest
from services.recovery_position import RecoveryPosition, RecoveryObserveResult, Recovery_Text, Recovery_Export


def observe(state, position=(3,4,8), *, session=1, stamp=1000, received=1_000_000_000):
    return state.Position_Observe(session,stamp,position,received,source="test AIR M0",sequence=7)


def test_last_real_sample_and_unknown_direction():
    state=RecoveryPosition()
    assert observe(state)==RecoveryObserveResult.Accepted
    view=state.Snapshot_Get(3_000_000_000,connected=True,current_session=1)
    assert (view['e_m'],view['n_m'],view['u_m'],view['horizontal_m'],view['age_s'])==(3,4,8,5,2)
    assert view['bearing_deg'] is None
    assert 'UNKNOWN' in Recovery_Text(view)


@pytest.mark.parametrize('position',[(math.nan,0,1),(1,math.inf,2),(0,1),None,(True,1,2)])
def test_invalid_does_not_erase_last_valid(position):
    state=RecoveryPosition();observe(state)
    old=state.sample
    assert observe(state,position)==RecoveryObserveResult.Invalid
    assert state.sample is old


@pytest.mark.parametrize('point,bearing',[((0,10,2),0),((10,0,2),90),((0,-10,2),180),((-10,0,2),270)])
def test_confirmed_north_clockwise_bearing(point,bearing):
    state=RecoveryPosition();observe(state,point);state.Frame_Confirm(True)
    assert state.Snapshot_Get(1_000_000_000)['bearing_deg']==bearing


def test_disconnect_retains_point_new_session_restarts_confirmation():
    state=RecoveryPosition();observe(state);state.Frame_Confirm(True)
    old=state.sample
    retained=state.Snapshot_Get(4_000_000_000,connected=False,current_session=2)
    assert state.sample is old and not retained['source_current'] and retained['age_s']==3
    assert observe(state,session=2,stamp=1,received=5_000_000_000)==RecoveryObserveResult.Accepted
    assert not state.Snapshot_Get(6_000_000_000)['frame_confirmed']
    assert observe(state,session=1,stamp=2000,received=7_000_000_000)==RecoveryObserveResult.Older


def test_out_of_order_and_clock_discontinuity():
    state=RecoveryPosition();observe(state)
    old=state.sample
    assert observe(state,stamp=999)==RecoveryObserveResult.Older
    assert state.sample is old
    assert state.Snapshot_Get(10)['age_s'] is None
    state.Frame_Confirm(True);observe(state,(0,0,-3))
    assert state.Snapshot_Get(1_000_000_000)['bearing_deg'] is None


def test_txt_matches_view_units_provenance_and_no_overwrite(tmp_path):
    state=RecoveryPosition();observe(state)
    snapshot=state.Snapshot_Get(4_000_000_000)
    path=tmp_path/'recovery.txt'
    text=Recovery_Export(path,snapshot,exported_at='2026-10-23T00:00:00Z')
    assert text==Recovery_Text(snapshot)+'\nExport UTC=2026-10-23T00:00:00Z\n'
    assert path.read_text(encoding='utf-8')==text
    assert all(value in text for value in ('E=3.000 m','horizontal=5.000 m','UNKNOWN','1000 ms','1000000000 ns','3.0 s','test AIR M0'))
    with pytest.raises(FileExistsError):Recovery_Export(path,snapshot)
    assert path.read_text(encoding='utf-8')==text


def test_source_wiring_preserves_third_page_and_restart_state():
    root=Path(__file__).parents[2]
    app=ast.parse((root/'apps/GSHC/app.py').read_text(encoding='utf-8'))
    controller=next(n for n in app.body if isinstance(n,ast.ClassDef) and n.name=='Controller')
    for name in ('_replace_state','FlightSession_Restart'):
        method=next(n for n in controller.body if isinstance(n,ast.FunctionDef) and n.name==name)
        calls=[n for n in ast.walk(method) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='FlightControllerState']
        assert any(k.arg=='recovery' for k in calls[0].keywords)
    ui=(root/'apps/GSHC/ui/main_window.py').read_text(encoding='utf-8')
    assert 'self.pages.addTab(self.post_process_page' in ui
    assert 'root.addWidget(self.recovery_panel)' in ui
    # Android remains a separate, unmerged candidate in this desktop-only task.
