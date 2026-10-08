"""Finalized publication ends; real active/grace/close errors remain visible."""
import os
from pathlib import Path
import pytest
from logger_health_boundary_support import boundary_run, CASES
from silverstar_fccg.app.service import FccgService


def test_estimator_health_logger_boundary(tmp_path, workspace_root):
    if os.name != 'nt' or not Path('D:/msys64/ucrt64/bin/gcc.exe').is_file():
        pytest.skip('Configured Windows Host GCC unavailable')
    selected=os.environ.get('SCG_LOGGER_HEALTH_PROJECT')
    if selected:
        project=Path(selected)
    else:
        service=FccgService(workspace_root)
        model=service.ReferenceProject_Create('LoggerHealthBoundary')
        project=tmp_path/'project'
        service.Project_Save(model,project,confirm_dangerous=True)
    evidence=boundary_run(project,tmp_path/'boundary',Path(__file__).parent/'fixtures/logger_health_boundary.c')
    assert evidence['compile_exit']==0,(tmp_path/'boundary/compile.log').read_text()
    assert len(evidence['cases'])==len(CASES)
    assert not [case for case in evidence['cases'] if case['exit']!=0],evidence['cases']
