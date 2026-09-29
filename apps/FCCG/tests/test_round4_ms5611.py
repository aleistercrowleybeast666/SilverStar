from __future__ import annotations

from pathlib import Path

from test_joint_sensor_library import _Command_Run, _Compiler_Get

from silverstar_fccg.generator.render import (
    _DeviceInstancesSource_Render,
    _ResourceHeader_Render,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.plugins.manifest import (
    PluginManifest_Load,
    PluginManifest_VariantResolve,
)
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.resources import ResourceAssignments_Resolve

from test_internal_platform_refactor import _CustomModel_Create


BUILTIN = Path(__file__).resolve().parents[1] / "plugins" / "builtin"
MS5611 = BUILTIN / "silverstar_device_barometer_ms5611" / "plugin.json"
PAYLOAD = MS5611.parent / "payload"


def test_ms5611_core_and_both_bus_adapters_host(tmp_path: Path) -> None:
    (tmp_path / "system_version.h").write_text(
        '#define SILVERSTAR_PRODUCT_STRING "SilverStar 0.1.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "project_resources.h").write_text(
        """#ifndef __PROJECT_RESOURCES_H
#define __PROJECT_RESOURCES_H
#include "platform_i2c.h"
#include "platform_spi.h"
#include "platform_gpio.h"
#include "platform_time.h"
#include "system_device_types.h"
#define PROJECT_MS5611_I2C_INSTANCE_COUNT 1U
#define PROJECT_MS5611_SPI_INSTANCE_COUNT 1U
typedef struct { PlatformI2cId i2c; PlatformTimeId time; } ProjectMs5611I2cResources;
typedef struct { PlatformSpiId spi; PlatformGpioId cs; PlatformTimeId time; } ProjectMs5611SpiResources;
SystemDeviceResult ProjectMs5611I2cResources_Get(uint8_t, ProjectMs5611I2cResources *);
SystemDeviceResult ProjectMs5611SpiResources_Get(uint8_t, ProjectMs5611SpiResources *);
#endif
""",
        encoding="utf-8",
    )
    core = BUILTIN / "silverstar_core_0_1_0" / "payload"
    includes = [
        tmp_path,
        PAYLOAD / "Devices/Barometer/MS5611/Inc",
        core / "Interfaces/Inc",
        core / "Common/Inc",
        BUILTIN / "silverstar_platform_api/payload/Platform/Inc",
    ]
    flags = [
        _Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-Wconversion", "-Wsign-conversion", "-Wshadow", "-Wvla",
    ]
    flags += ["-I" + str(path) for path in includes]
    source = PAYLOAD / "Devices/Barometer/MS5611/Src"
    for name, sources in (
        ("core", [source / "ms5611_core.c", PAYLOAD / "Tests/Host/test_ms5611_core.c"]),
        ("adapter", [source / "ms5611_core.c", source / "ms5611_adapter.c",
                     PAYLOAD / "Tests/Host/test_ms5611_adapter.c"]),
    ):
        binary = tmp_path / f"ms5611_{name}.exe"
        _Command_Run(flags + [str(path) for path in sources] + ["-lm", "-o", str(binary)],
                     tmp_path, f"compile_{name}")
        _Command_Run([str(binary)], tmp_path, f"run_{name}")
    _Command_Run(flags + ["-c", str(source / "ms5611_instance.c"),
                          "-o", str(tmp_path / "ms5611_instance.o")],
                 tmp_path, "compile_instance")


def test_ms5611_one_physical_plugin_two_bus_variants(builtin_catalog) -> None:
    manifest = PluginManifest_Load(MS5611)
    assert manifest.physical_device is not None
    assert manifest.physical_device.model == "MS5611"
    assert set(manifest.device_variants) == {"i2c", "spi"}
    for variant_id, kind in (("i2c", "i2c"), ("spi", "spi")):
        resolved = PluginManifest_VariantResolve(manifest, variant_id)
        assert resolved.resource_requirements[0].kind == kind
        assert resolved.metadata["device_descriptors"][0]["physical_device_id"] == (
            "PROJECT_PHYSICAL_DEVICE_ID_MS5611"
        )
        assert sum(source.endswith("ms5611_core.c") for source in resolved.build.sources) == 1
    assert builtin_catalog.Component_Get(manifest.component_id).version == "0.1.0"


def test_ms5611_i2c_generated_resource_and_dispatch(builtin_catalog) -> None:
    model = _CustomModel_Create(
        builtin_catalog,
        [DeviceInstance("baro0", "silverstar.device.barometer.ms5611", "i2c", "osr4096_20_hz")],
    )
    model.resource_assignments = {"baro0:data": "I2C1", "baro0:time": "SYSTEM_TIME"}
    resolution = ResourceAssignments_Resolve(model, builtin_catalog)
    assert resolution.valid, resolution
    header = _ResourceHeader_Render(model, builtin_catalog)
    source = _DeviceInstancesSource_Render(model, builtin_catalog.ProjectView_Get(model))
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "ProjectMs5611I2cResources_Get" in header
    assert "Ms5611I2cBarometerInstance_Process(0U)" in source
    assert sum(path.endswith("ms5611_core.c") for path in graph.sources) == 1


def test_ms5611_spi_generated_resource_and_dispatch(builtin_catalog) -> None:
    model = _CustomModel_Create(
        builtin_catalog,
        [DeviceInstance("baro0", "silverstar.device.barometer.ms5611", "spi", "osr4096_20_hz")],
    )
    source = _DeviceInstancesSource_Render(model, builtin_catalog.ProjectView_Get(model))
    graph = SourceGraph_Resolve(model, builtin_catalog)
    manifest = builtin_catalog.ProjectView_Get(model).InstanceIdComponent_Get("baro0")
    assert manifest.instance_resource_binding is not None
    assert manifest.instance_resource_binding.accessor == "ProjectMs5611SpiResources_Get"
    assert {field.member for field in manifest.instance_resource_binding.fields} == {
        "spi", "cs", "time"
    }
    assert "Ms5611SpiBarometerInstance_Process(0U)" in source
    assert sum(path.endswith("ms5611_core.c") for path in graph.sources) == 1


def test_ms5611_mixed_variants_keep_distinct_contexts_and_one_core(
    builtin_catalog,
) -> None:
    model = _CustomModel_Create(
        builtin_catalog,
        [
            DeviceInstance("baro_i2c", "silverstar.device.barometer.ms5611", "i2c", "osr4096_20_hz"),
            DeviceInstance("baro_spi", "silverstar.device.barometer.ms5611", "spi", "osr4096_20_hz"),
        ],
    )
    source = _DeviceInstancesSource_Render(model, builtin_catalog.ProjectView_Get(model))
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "case 0U: return Ms5611I2cBarometerInstance_Process(0U);" in source
    assert "case 1U: return Ms5611SpiBarometerInstance_Process(0U);" in source
    assert sum(path.endswith("ms5611_core.c") for path in graph.sources) == 1
