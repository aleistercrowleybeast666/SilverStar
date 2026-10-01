from pathlib import Path
import csv
import io
import json

import pytest
from PySide6.QtWidgets import QMessageBox, QFileDialog

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.build.runner import BuildAction, BuildResult
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.artifact_memory import ArtifactMemoryMarginLevel_Get
from silverstar_fccg.project.alignment import AlignmentConstraint
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.power10_report import (
    Power10Report_Create, Power10Report_Current_Is, Power10Report_Save,
    Power10Report_Csv, Power10TextPassed_Is,
)
from silverstar_fccg.project.release_policy import ReleaseCompatibilityIssues_Get
from silverstar_fccg.ui.main_window import MainWindow


OUTPUT = """POWER10_RULE5_FUNCTION|Flight|APP/sample.c|12|Review|11|0
POWER10_RULE5_FUNCTION|Flight|APP/sample.c|29|Boundary|5|1
POWER10_RULE5|Flight|files=1|functions=2|eligible_assertions=1|average=0.500000|informational
POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending
"""


@pytest.mark.parametrize("remaining,level", ((0,"error"),(9,"error"),(10,"warning"),(20,"warning"),(21,"success"),(100,"success")))
def test_memory_exact_boundaries(remaining, level):
    assert ArtifactMemoryMarginLevel_Get(remaining, 100) == level


@pytest.mark.parametrize("output,exit_code,passed", ((OUTPUT,0,True),(OUTPUT,1,False),
    (OUTPUT.replace("eligible_assertions=1", "eligible_assertions=0"),0,False),
    (OUTPUT + "POWER10_CONTRACT_REVIEW|FAIL|unhandled_fault\n",0,False),("",0,False)))
def test_exit_zero_does_not_override_hard_or_incomplete_reports(output, exit_code, passed):
    assert Power10TextPassed_Is(output, exit_code) is passed


def _ReportFixture_Create(tmp_path, model):
    root = tmp_path / "项目_α"
    (root / "APP").mkdir(parents=True)
    (root / "Tools").mkdir()
    (root / "APP/sample.c").write_text("boundary\n",encoding="utf-8")
    (root / "Tools/check_power_of_ten.ps1").write_text("checker\n",encoding="utf-8")
    (root / "Makefile").write_text("source graph\n",encoding="utf-8")
    (root / "SilverStar.ssproject").write_text(json.dumps(model.Dictionary_Get()),encoding="utf-8")
    return root, Power10Report_Create(root,model,OUTPUT,0)


def test_export_has_real_line_full_path_and_snapshot_then_rejects_stale(tmp_path, workspace_root):
    model = FccgService(workspace_root).ReferenceProject_Create("Review")
    root,report = _ReportFixture_Create(tmp_path,model)
    assert Power10Report_Current_Is(root,model,report)
    rows=list(csv.DictReader(io.StringIO(Power10Report_Csv(report))))
    assert rows[0]["function"] == "Review" and rows[0]["line"] == "12"
    assert rows[0]["full_path"] == str((root/"APP/sample.c").resolve())
    assert len(rows[0]["configuration_sha256"]) == 64
    assert "NOT_PROVEN" in rows[-1]["reason"]
    (root / "APP/sample.c").write_text("changed source\n",encoding="utf-8")
    assert not Power10Report_Current_Is(root,model,report)
    empty=dict(report,findings=[])
    assert "NOT_PROVEN" in Power10Report_Csv(empty)


def test_hard_failure_export_preserves_physical_line_and_function_scope(tmp_path, workspace_root):
    model = FccgService(workspace_root).ReferenceProject_Create("HardFailure")
    root, _ = _ReportFixture_Create(tmp_path, model)
    output = OUTPUT + ("POWER10_FUNCTION_SCOPE|Flight|APP/sample.c|12|27|Review\n"
                       "Power of Ten check FAILED:\n- goto violation:\n  APP/sample.c:15: goto unsafe;\n")
    report = Power10Report_Create(root, model, output, 1)
    rows = list(csv.DictReader(io.StringIO(Power10Report_Csv(report))))
    hard = next(row for row in rows if row['reason'].startswith('hard_failure;'))
    assert hard['function'] == 'Review' and hard['line'] == '15'
    assert hard['full_path'] == str((root/'APP/sample.c').resolve())
    assert 'goto' in hard['reason']


def test_gui_information_error_and_export_cancel_unicode_failure_stale(qapp,tmp_path,workspace_root,monkeypatch):
    window=MainWindow(SettingsStore(tmp_path/"export.ini"),service=FccgService(workspace_root))
    boxes=[]
    monkeypatch.setattr(window,"_MessageBox_Exec",lambda *args,**kwargs: boxes.append((args,kwargs)))
    window._Build_Complete(BuildResult(BuildAction.POWER10_CHECK,(),0,OUTPUT))
    assert boxes[-1][0][0] == QMessageBox.Icon.Information
    window._Build_Complete(BuildResult(BuildAction.POWER10_CHECK,(),0,OUTPUT.replace("eligible_assertions=1","eligible_assertions=0")))
    assert boxes[-1][0][0] == QMessageBox.Icon.Critical
    project=tmp_path/"export_project"
    target,report=_ReportFixture_Create(project,window._model)
    target.rename(project/"Flight_Controller")
    target=project/"Flight_Controller"
    report=Power10Report_Create(target,window._model,OUTPUT,0)
    Power10Report_Save(target,report)
    window._project_root=project
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args,**kwargs:("",""))
    before=len(boxes)
    window._Power10Report_Export()
    assert len(boxes)==before
    output=project/"审查 α.csv"
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args,**kwargs:(str(output),""))
    window._Power10Report_Export()
    assert output.read_text(encoding="utf-8-sig").startswith("target,function,full_path")
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args,**kwargs:(str(project),""))
    window._Power10Report_Export()
    assert boxes[-1][0][0] == QMessageBox.Icon.Critical
    (target/"APP/sample.c").write_text("new revision",encoding="utf-8")
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args,**kwargs: pytest.fail("stale report opened save dialog"))
    window._Power10Report_Export()
    assert boxes[-1][0][0] == QMessageBox.Icon.Critical
    window.close()


def test_legacy_magnetic_configuration_remains_intact_and_blocks_generation(workspace_root):
    service=FccgService(workspace_root)
    model=service.ReferenceProject_Create("Legacy")
    model.device_instances.append(DeviceInstance("mag0","silverstar.device.magnetometer.lis3mdl"))
    before=model.Dictionary_Get()
    assert ReleaseCompatibilityIssues_Get(model)
    assert model.Dictionary_Get()==before
    model.device_instances.pop()
    model.alignment=type(model.alignment)(constraints=(AlignmentConstraint("gravity"),AlignmentConstraint("magnetic_field")))
    assert ReleaseCompatibilityIssues_Get(model)


def test_fixed_pair_and_shared_hardware_layout_survive_rapid_switches(qapp,tmp_path,workspace_root):
    window=MainWindow(SettingsStore(tmp_path/"rapid.ini"),service=FccgService(workspace_root))
    window.show()
    editor=window.algorithm_parameters_page.alignment_editor
    for _ in range(30):
        editor.DraftStrategy_Set("silverstar.algorithm.alignment.external_attitude_source")
        editor.DraftStrategy_Set("silverstar.algorithm.alignment.vector_constraints")
        editor._Draft_Cancel()
        qapp.processEvents()
    assert len(editor._rows)==2 and all(not row["kind"].isEnabled() for row in editor._rows)
    assert "magnetometer0" not in window.devices_page.device_combos
    assert window.air_link_page.isAncestorOf(window.ground_target_page.pc_interface)
    assert window.pages.count()==7
    assert type(window.ground_target_page).__bases__[0] is type(window.board_hardware_page)
    assert set(window.ground_target_page.platform_values)==set(window.board_hardware_page.platform_values)
    window.close()
