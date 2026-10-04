"""JY901B installation setting is a saved, per-instance module command."""

import json
import shutil
import subprocess
import zipfile
from dataclasses import replace

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from test_jy901b_boot_probe_host import _CompilerCommand, _CompileAndRun
from test_scg_ui_metadata_hotfix import window


@pytest.mark.parametrize("orientation, command", [
    ("horizontal", ".installation_orientation = 0U"),
    ("vertical", ".installation_orientation = 1U"),
    ("preserve", ".installation_orientation = 2U"),
])
def test_orientation_survives_save_and_reaches_generated_driver(
    tmp_path, workspace_root, orientation, command,
):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("Jy901bOrientation")
    model.device_instances = [
        replace(instance, installation_orientation=orientation)
        if instance.plugin == "silverstar.device.imu.jy901b" else instance
        for instance in model.device_instances
    ]
    project = tmp_path / orientation
    service.Project_Save(model, project, confirm_dangerous=True)
    reopened = service.Project_Open(project)
    jy = next(item for item in reopened.device_instances
              if item.plugin == "silverstar.device.imu.jy901b")
    assert jy.installation_orientation == orientation
    resources = (project / "Generated/Src/project_resources.c").read_text(encoding="utf-8")
    assert command in resources
    driver = (project / "Devices/IMU/JY901B/Src/jy901b_device.c").read_text(encoding="utf-8")
    assert "IMU_REG_ORIENT" in driver
    assert "resources.installation_orientation" in driver
    assert "IMU_ORIENT_VERTICAL_VALUE" in driver
    decoder = project / "Jy901bOrientation.ssdecoder"
    with zipfile.ZipFile(decoder) as package:
        semantics = json.loads(package.read("project_semantics.json"))
    logged = next(item for item in semantics["devices"]
                  if item["plugin"] == "silverstar.device.imu.jy901b")
    assert logged["installation_orientation"] == orientation
    if orientation in ("horizontal", "preserve"):
        sources = (
            "Tests/Host/host_platform_mock.c",
            "Common/Src/common_ringbuf.c",
            "Common/Src/silverstar_assert.c",
            "Generated/Src/project_resources.c",
            "Devices/IMU/JY901B/Src/jy901b_device.c",
            "Devices/IMU/JY901B/Adapter/Src/jy901b_startup.c",
            "Devices/IMU/JY901B/Adapter/Src/jy901b_imu_adapter.c",
            "Devices/IMU/JY901B/Adapter/Src/jy901b_sample_quality.c",
            "System/Src/system_device_startup.c",
        )
        command = _CompilerCommand(project) + [
            "-DJY_BOOT_PROBE_ADAPTER_VERIFY=1", "-ffunction-sections",
            "-fdata-sections", "-Wl,--gc-sections",
            *(["-DJY_TEST_PRESERVE_ORIENT=1"] if orientation == "preserve" else []),
            *(str(project / source) for source in sources),
            str(workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/test_jy901b_startup.c"),
            "-lm",
        ]
        _CompileAndRun(command, project, tmp_path / "jy901b-horizontal.exe")


def test_legacy_jy901b_project_retains_previous_vertical_mode(workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("Jy901bLegacy")
    data = model.Dictionary_Get()
    for instance in data["components"]["devices"]:
        instance.pop("installation_orientation", None)
    restored = ProjectModel_Parse(json.loads(json.dumps(data)))
    jy = next(item for item in restored.device_instances
              if item.plugin == "silverstar.device.imu.jy901b")
    assert jy.installation_orientation == "preserve"
    assert next(item for item in model.device_instances
                if item.plugin == "silverstar.device.imu.jy901b").installation_orientation == "vertical"


def test_gui_orientation_selector_updates_and_reopens(window, qapp, tmp_path):
    window._model = window._service.ReferenceProject_Create("Jy901bGuiOrientation")
    window._model.device_instances = [
        replace(item, installation_orientation="preserve")
        if item.plugin == "silverstar.device.imu.jy901b" else item
        for item in window._model.device_instances
    ]
    window._Project_Refresh()
    combo = window.devices_page.orientation_combos["imu0"]
    assert combo.currentData() == "preserve"
    combo.setCurrentIndex(combo.findData("horizontal"))
    qapp.processEvents()
    assert window._model.DeviceInstance_Get("imu0").installation_orientation == "horizontal"
    ProjectRoot_Save(window._model, tmp_path / "gui")
    window._Project_Open(tmp_path / "gui")
    qapp.processEvents()
    assert window.devices_page.orientation_combos["imu0"].currentData() == "horizontal"


def test_multi_instance_horizontal_command_and_raw_sample_isolation(
    tmp_path, workspace_root,
):
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC unavailable")
    builtin = workspace_root / "plugins/builtin"
    core = builtin / "silverstar_core_0_1_0/payload"
    jy = builtin / "silverstar_device_imu_jy901b/payload"
    fixture = core / "Tests/Host/Fixtures/MultiInstance"
    service = FccgService(workspace_root)
    project = tmp_path / "Build"
    service.Project_Save(service.ReferenceProject_Create("Jy901bMulti"), project,
                         confirm_dangerous=True)
    command = [compiler, "-I", str(fixture / "Inc"),
               *_CompilerCommand(project)[1:],
               str(core / "Common/Src/silverstar_assert.c"),
               str(core / "Tests/Host/host_platform_mock.c"),
               str(fixture / "multi_instance_resources.c"),
               str(jy / "Devices/IMU/JY901B/Src/jy901b_device.c"),
               str(core / "Tests/Host/test_jy901b_multi_instance.c"),
               "-lm", "-o", str(tmp_path / "multi-instance.exe")]
    compiled = subprocess.run(command, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    executed = subprocess.run([tmp_path / "multi-instance.exe"], capture_output=True, text=True)
    assert executed.returncode == 0, executed.stdout + executed.stderr
