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
BMP390 = BUILTIN / "silverstar_device_barometer_bmp390" / "plugin.json"
PAYLOAD = BMP390.parent / "payload"


def test_bmp390_core_and_both_bus_adapters_host(
    tmp_path: Path,
) -> None:
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
#define PROJECT_BMP390_I2C_INSTANCE_COUNT 1U
#define PROJECT_BMP390_SPI_INSTANCE_COUNT 1U
typedef struct { PlatformI2cId i2c; PlatformTimeId time; } ProjectBmp390I2cResources;
typedef struct { PlatformSpiId spi; PlatformGpioId cs; PlatformTimeId time; } ProjectBmp390SpiResources;
SystemDeviceResult ProjectBmp390I2cResources_Get(uint8_t, ProjectBmp390I2cResources *);
SystemDeviceResult ProjectBmp390SpiResources_Get(uint8_t, ProjectBmp390SpiResources *);
#endif
""",
        encoding="utf-8",
    )
    core = BUILTIN / "silverstar_core_0_1_0" / "payload"
    includes = [
        tmp_path,
        PAYLOAD / "Devices/Barometer/BMP390/Inc",
        core / "Interfaces/Inc",
        core / "Common/Inc",
        BUILTIN / "silverstar_platform_api/payload/Platform/Inc",
    ]
    flags = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-Wconversion", "-Wsign-conversion", "-Wshadow", "-Wvla"]
    flags += ["-I" + str(path) for path in includes]
    source = PAYLOAD / "Devices/Barometer/BMP390/Src"
    for name, sources in (
        ("core", [source / "bmp390_core.c", PAYLOAD / "Tests/Host/test_bmp390_core.c"]),
        ("adapter", [source / "bmp390_core.c", source / "bmp390_adapter.c",
                     PAYLOAD / "Tests/Host/test_bmp390_adapter.c"]),
    ):
        binary = tmp_path / f"bmp390_{name}.exe"
        _Command_Run(flags + [str(path) for path in sources] + ["-lm", "-o", str(binary)],
                     tmp_path, f"compile_{name}")
        _Command_Run([str(binary)], tmp_path, f"run_{name}")
    _Command_Run(flags + ["-c", str(source / "bmp390_instance.c"),
                          "-o", str(tmp_path / "bmp390_instance.o")],
                 tmp_path, "compile_instance")


def test_bmp390_one_physical_plugin_two_bus_variants(builtin_catalog) -> None:
    manifest = PluginManifest_Load(BMP390)
    assert manifest.physical_device is not None
    assert manifest.physical_device.model == "BMP390"
    assert set(manifest.device_variants) == {"i2c", "spi"}
    for variant_id, kind in (("i2c", "i2c"), ("spi", "spi")):
        resolved = PluginManifest_VariantResolve(manifest, variant_id)
        assert resolved.resource_requirements[0].kind == kind
        assert resolved.metadata["device_descriptors"][0]["physical_device_id"] == (
            "PROJECT_PHYSICAL_DEVICE_ID_BMP390"
        )
        assert sum(source.endswith("bmp390_core.c") for source in resolved.build.sources) == 1
    assert builtin_catalog.Component_Get(manifest.component_id).version == "0.1.0"


def test_bmp390_i2c_generated_resource_and_dispatch(builtin_catalog) -> None:
    model = _CustomModel_Create(
        builtin_catalog,
        [DeviceInstance("baro0", "silverstar.device.barometer.bmp390", "i2c", "forced_20_hz")],
    )
    model.resource_assignments = {"baro0:data": "I2C1", "baro0:time": "SYSTEM_TIME"}
    resolution = ResourceAssignments_Resolve(model, builtin_catalog)
    assert resolution.valid, resolution
    header = _ResourceHeader_Render(model, builtin_catalog)
    source = _DeviceInstancesSource_Render(
        model, builtin_catalog.ProjectView_Get(model)
    )
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "ProjectBmp390I2cResources_Get" in header
    assert "Bmp390I2cBarometerInstance_Process(0U)" in source
    assert sum(path.endswith("bmp390_core.c") for path in graph.sources) == 1


def test_bmp390_spi_generated_resource_and_dispatch(builtin_catalog) -> None:
    model = _CustomModel_Create(
        builtin_catalog,
        [DeviceInstance("baro0", "silverstar.device.barometer.bmp390", "spi", "forced_20_hz")],
    )
    source = _DeviceInstancesSource_Render(
        model, builtin_catalog.ProjectView_Get(model)
    )
    graph = SourceGraph_Resolve(model, builtin_catalog)
    manifest = builtin_catalog.ProjectView_Get(model).InstanceIdComponent_Get("baro0")
    assert manifest.instance_resource_binding is not None
    assert manifest.instance_resource_binding.accessor == "ProjectBmp390SpiResources_Get"
    assert {field.member for field in manifest.instance_resource_binding.fields} == {
        "spi", "cs", "time"
    }
    assert "Bmp390SpiBarometerInstance_Process(0U)" in source
    assert sum(path.endswith("bmp390_core.c") for path in graph.sources) == 1


def test_bmp390_mixed_variants_keep_distinct_contexts_and_one_core(
    builtin_catalog,
) -> None:
    model = _CustomModel_Create(
        builtin_catalog,
        [
            DeviceInstance("baro_i2c", "silverstar.device.barometer.bmp390", "i2c", "forced_20_hz"),
            DeviceInstance("baro_spi", "silverstar.device.barometer.bmp390", "spi", "forced_20_hz"),
        ],
    )
    source = _DeviceInstancesSource_Render(
        model, builtin_catalog.ProjectView_Get(model)
    )
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "case 0U: return Bmp390I2cBarometerInstance_Process(0U);" in source
    assert "case 1U: return Bmp390SpiBarometerInstance_Process(0U);" in source
    assert sum(path.endswith("bmp390_core.c") for path in graph.sources) == 1
