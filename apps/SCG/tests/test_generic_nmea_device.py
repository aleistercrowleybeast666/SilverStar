from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from silverstar_fccg.generator.render import GeneratedFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate


def test_generic_nmea_bounded_parser_host_vectors(
    workspace_root: Path, tmp_path: Path,
) -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC is not available")
    payload = (
        workspace_root / "plugins/builtin/silverstar_device_gnss_generic_nmea/payload"
    )
    core = workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload"
    nmea = payload / "Devices/GNSS/GENERIC_NMEA"
    executable = tmp_path / "generic_nmea_parser.exe"
    command = [
        compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        f"-I{nmea / 'Inc'}", f"-I{core / 'Interfaces/Inc'}",
        f"-I{core / 'Common/Inc'}",
        str(nmea / "Src/generic_nmea_parser.c"),
        str(payload / "Tests/Host/test_generic_nmea_parser.c"),
        "-lm", "-o", str(executable),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    subprocess.run([str(executable)], check=True, capture_output=True, text=True)


def test_generic_nmea_read_only_plugin_generates_one_bound_instance(
    builtin_catalog,
) -> None:
    model = ReferenceProject_Create("GenericNmea", catalog=builtin_catalog)
    model.device_instances = [
        DeviceInstance("gnss0", "silverstar.device.gnss.generic_nmea")
        if instance.instance_id == "gnss0" else instance
        for instance in model.device_instances
    ]
    model.resource_assignments.pop("gnss0:reset")
    model.resource_assignments.pop("gnss0:timepulse")
    validation = Project_Validate(model, builtin_catalog)
    assert validation.valid, validation.issues

    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert graph.sources.count(
        "Devices/GNSS/GENERIC_NMEA/Src/generic_nmea_parser.c"
    ) == 1
    assert graph.sources.count(
        "Devices/GNSS/GENERIC_NMEA/Src/generic_nmea_instance.c"
    ) == 1
    assert not any("NEO_M9N" in source for source in graph.sources)

    rendered = GeneratedFiles_Render(model, builtin_catalog, graph)
    resources = rendered["Generated/Inc/project_resources.h"].decode("utf-8")
    assert "PROJECT_GENERIC_NMEA_INSTANCE_COUNT" in resources
    assert "ProjectGenericNmeaResources_Get" in resources
    assert "PROJECT_NEO_M9N_INSTANCE_COUNT" not in resources
