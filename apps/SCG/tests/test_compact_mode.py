from dataclasses import replace
import re

import pytest

from silverstar_fccg.generator.render import _DeviceInstancesHeader_Render, _Eide_Render
from silverstar_fccg.generator.source_graph import SourceGraphError, SourceGraph_Resolve
from silverstar_fccg.project.compact import CompactErrors_Get
from silverstar_fccg.project.model import DeviceInstance, ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate


def test_compact_setting_roundtrip_and_legacy_dictionary(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    legacy = model.Dictionary_Get()
    assert "compact_mode" not in legacy["build"]
    model.build = replace(model.build, compact_mode=True)
    saved = model.Dictionary_Get()
    assert ProjectModel_Parse(saved).build.compact_mode is True
    model.build = replace(model.build, compact_mode=False)
    assert model.Dictionary_Get() == legacy


@pytest.mark.parametrize("plugin", [
    "silverstar.device.imu.mpu6050",
    "silverstar.device.gnss.neo_m9n",
    "silverstar.device.telemetry.sx1281",
    "silverstar.device.barometer.bmp280",
])
def test_compact_rejects_duplicate_class_independent_of_brand(builtin_catalog, plugin):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.device_instances.append(DeviceInstance("extra0", plugin))
    assert CompactErrors_Get(model, builtin_catalog) == ()
    model.build = replace(model.build, compact_mode=True)
    assert CompactErrors_Get(model, builtin_catalog)
    assert "COMPACT_DEVICE_LIMIT" in {issue.code for issue in Project_Validate(model, builtin_catalog).issues}
    with pytest.raises(SourceGraphError, match="at most one"):
        SourceGraph_Resolve(model, builtin_catalog)


def test_compact_sizes_bounds_without_changing_normal_buffers(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    normal = SourceGraph_Resolve(model, builtin_catalog)
    assert "AIR_LINK_HAL_BUFFER_SIZE=260" not in normal.defines
    assert re.search(r"PROJECT_IMU_INSTANCE_COUNT_MAX\s+4U", _DeviceInstancesHeader_Render(model, builtin_catalog))
    model.build = replace(model.build, compact_mode=True)
    compact = SourceGraph_Resolve(model, builtin_catalog)
    assert "AIR_LINK_HAL_BUFFER_SIZE=260" in compact.defines
    assert re.search(r"PROJECT_IMU_INSTANCE_COUNT_MAX\s+1U", _DeviceInstancesHeader_Render(model, builtin_catalog))


def test_ret6_eide_uses_cm3_soft_float(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    graph = replace(SourceGraph_Resolve(model, builtin_catalog),
                    mcu_flags=("-mcpu=cortex-m3", "-mthumb", "-mfloat-abi=soft"))
    text = _Eide_Render(model, graph, builtin_catalog.Component_Get(model.development_environment))
    assert "cpuType: Cortex-M3" in text
    assert "floatingPointHardware: none" in text
    assert "$float-abi-type: soft" in text
