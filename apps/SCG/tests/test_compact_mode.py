from dataclasses import replace
from pathlib import Path
import re

import pytest

from silverstar_fccg.generator.render import _DeviceInstancesHeader_Render, _Eide_Render
from silverstar_fccg.generator.source_graph import SourceGraphError, SourceGraph_Resolve
from silverstar_fccg.generator.compact_entry import CompactFlightMain_Integrate
from silverstar_fccg.generator.render import _FlightConfigHeader_Render
from silverstar_fccg.generator.render import GeneratedFiles_Render
from silverstar_fccg.hardware.inventory import CubeMxInventory_Parse
from silverstar_fccg.project.compact import CompactErrors_Get
from silverstar_fccg.project.model import DeviceInstance, ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Reconcile


def test_compact_setting_roundtrip_and_legacy_dictionary(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    legacy = model.Dictionary_Get()
    assert "compact_mode" not in legacy["build"]
    model.build = replace(model.build, feature_tier="compact")
    saved = model.Dictionary_Get()
    assert ProjectModel_Parse(saved).build.compact_mode is True
    model.build = replace(model.build, feature_tier="full")
    assert model.Dictionary_Get() == legacy


@pytest.mark.parametrize("compact", [False, True])
def test_generated_build_mode_contract_is_explicit_and_device_layer_only(builtin_catalog, compact):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    model.build = replace(model.build, feature_tier="compact" if compact else "full")
    AlgorithmParameters_Reconcile(model, builtin_catalog)
    files = GeneratedFiles_Render(model, builtin_catalog, SourceGraph_Resolve(model, builtin_catalog))
    assert "Generated/Inc/project_build_mode.h" not in files
    header = files["Generated/Inc/project_device_build_capabilities.h"].decode("utf-8")
    assert f"#define SILVERSTAR_BUILD_COMPACT_ENABLED {int(compact)}U" in header
    flag_lines = [line for line in header.splitlines() if "SILVERSTAR_BUILD_COMPACT_ENABLED" in line]
    assert flag_lines == [f"#define SILVERSTAR_BUILD_COMPACT_ENABLED {int(compact)}U"]
    assert "#include" not in header


@pytest.mark.parametrize("plugin", [
    "silverstar.device.imu.mpu6050",
    "silverstar.device.gnss.neo_m9n",
    "silverstar.device.telemetry.sx1281",
    "silverstar.device.barometer.bmp280",
])
def test_compact_rejects_duplicate_class_independent_of_brand(builtin_catalog, plugin):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    if plugin == "silverstar.device.barometer.bmp280":
        # The reference IMU embeds a barometer. One dedicated BMP correctly
        # takes priority; two dedicated devices still violate the tier limit.
        model.device_instances.append(DeviceInstance("dedicated0", plugin))
    model.device_instances.append(DeviceInstance("extra0", plugin))
    assert CompactErrors_Get(model, builtin_catalog) == ()
    model.build = replace(model.build, feature_tier="compact")
    assert CompactErrors_Get(model, builtin_catalog)
    assert "COMPACT_DEVICE_LIMIT" in {issue.code for issue in Project_Validate(model, builtin_catalog).issues}
    with pytest.raises(SourceGraphError, match="at most one"):
        SourceGraph_Resolve(model, builtin_catalog)


def test_compact_sizes_bounds_without_changing_normal_buffers(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    normal = SourceGraph_Resolve(model, builtin_catalog)
    assert "AIR_LINK_HAL_BUFFER_SIZE=260" not in normal.defines
    assert re.search(r"PROJECT_IMU_INSTANCE_COUNT_MAX\s+4U", _DeviceInstancesHeader_Render(model, builtin_catalog))
    model.build = replace(model.build, feature_tier="compact")
    compact = SourceGraph_Resolve(model, builtin_catalog)
    assert "AIR_LINK_HAL_BUFFER_SIZE=260" in compact.defines
    assert re.search(r"PROJECT_IMU_INSTANCE_COUNT_MAX\s+1U", _DeviceInstancesHeader_Render(model, builtin_catalog))


def test_ret6_eide_uses_cm3_soft_float(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    graph = replace(SourceGraph_Resolve(model, builtin_catalog),
                    mcu_flags=("-mcpu=cortex-m3", "-mthumb", "-mfloat-abi=soft"))
    text = _Eide_Render(model, graph, builtin_catalog.Component_Get(model.development_environment))
    assert "cpuType: Cortex-M3" in text
    assert "floatingPointHardware: none" in text
    assert "$float-abi-type: soft" in text


def test_compact_entry_rejects_user_application_code():
    clean = b"/* USER CODE BEGIN Includes */\n/* USER CODE END Includes */\n/* USER CODE BEGIN 2 */\n/* USER CODE END 2 */"
    result = CompactFlightMain_Integrate(clean)
    assert b"SystemStartup_Run()" in result and b"vTaskStartScheduler()" in result
    assert b"SystemStartup_Run()" not in clean
    with pytest.raises(ValueError, match="empty CubeMX"):
        CompactFlightMain_Integrate(result)
    with pytest.raises(ValueError, match="empty CubeMX"):
        CompactFlightMain_Integrate(clean.replace(b"BEGIN 2 */", b"BEGIN 2 */\nUserOwned_Init();"))


def test_compact_snapshot_capacity_keeps_disabled_stream_descriptors(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    normal = _FlightConfigHeader_Render(model, builtin_catalog)
    assert "PROJECT_SYSTEM_CONFIG_SNAPSHOT_SLOTS" not in normal
    model.build = replace(model.build, feature_tier="minimal")
    before = _FlightConfigHeader_Render(model, builtin_catalog)
    model.logging_streams = [replace(stream, enabled=False) for stream in model.logging_streams]
    after = _FlightConfigHeader_Render(model, builtin_catalog)
    slots = lambda text: int(re.search(r"#define PROJECT_SYSTEM_CONFIG_SNAPSHOT_SLOTS\s+(\d+)U", text)[1])
    depth = int(re.search(r"#define SYSTEM_LOG_RECORD_QUEUE_DEPTH\s+(\d+)U", before)[1])
    assert slots(before) == slots(after)
    # Owned snapshot traversal preserves every descriptor independently of the
    # ordinary queue. This Reference configuration exceeds its 24-slot queue.
    assert depth == 24 and slots(before) + 4 > depth
    from silverstar_fccg.generator.render import _MetadataSource_Render
    profile = _MetadataSource_Render(model, builtin_catalog)
    assert 'SSLOG_RECORD_COUNT + 4U + PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX) <= 65535U' in profile
    assert 'SYSTEM_LOG_RECORD_QUEUE_DEPTH' not in profile


def test_f1_shared_sdio_dma_requires_both_actual_handle_bindings():
    repository = Path(__file__).resolve().parents[3]
    ioc = (repository / "docs/FCCG/platform/evidence/SF6_RET6_phase1/SF6_RET6_Hardware.ioc").read_text()
    binding = """
    hdma_sdio.Instance = DMA2_Channel4;
    __HAL_LINKDMA(sdHandle, hdmarx, hdma_sdio);
    __HAL_LINKDMA(sdHandle, hdmatx, hdma_sdio);
    """
    parse = lambda text: CubeMxInventory_Parse(ioc, generated_files={"Core/Src/sdio.c": text})
    assert parse(binding).sdio_shared_dma_bound
    assert not parse("").sdio_shared_dma_bound
    assert not parse(binding.replace("hdmatx", "other_field")).sdio_shared_dma_bound
    assert not parse(binding.replace("hdmatx, hdma_sdio", "hdmatx, other_dma")).sdio_shared_dma_bound
    assert not parse(binding.replace("DMA2_Channel4", "DMA1_Channel4")).sdio_shared_dma_bound


def test_compact_no_gnss_cuts_origin_storage_and_sets_features_before_includes(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies["estimator"] = "silverstar.algorithm.estimator.sf6"
    normal = _FlightConfigHeader_Render(model, builtin_catalog)
    assert "SYSTEM_BUILD_GNSS_ORIGIN_STORAGE_SAMPLES" not in normal
    model.build = replace(model.build, feature_tier="minimal")
    with_gnss = _FlightConfigHeader_Render(model, builtin_catalog)
    assert re.search(r"SYSTEM_BUILD_GNSS_ORIGIN_AVAILABLE\s+1U", with_gnss)
    model.device_instances = [instance for instance in model.device_instances
                              if "gnss.position" not in builtin_catalog.InstanceComponent_Get(instance).provides]
    without = _FlightConfigHeader_Render(model, builtin_catalog)
    assert re.search(r"SYSTEM_BUILD_GNSS_ORIGIN_AVAILABLE\s+0U", without)
    assert re.search(r"SYSTEM_BUILD_GNSS_ORIGIN_STORAGE_SAMPLES\s+1U", without)
    assert without.index("#define SYSTEM_USER_POWER_ENABLE") < without.index('#include "project_algorithm_parameters.h"')
    model.protocols["maintenance"] = None
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert not any(source.startswith("Devices/GNSS/") for source in graph.sources)
