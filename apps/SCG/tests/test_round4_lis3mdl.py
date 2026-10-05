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
LIS3MDL = BUILTIN / "silverstar_device_magnetometer_lis3mdl" / "plugin.json"
PAYLOAD = LIS3MDL.parent / "payload"


def test_lis3mdl_core_and_both_bus_adapters_host(tmp_path: Path) -> None:
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
#define PROJECT_LIS3MDL_I2C_INSTANCE_COUNT 1U
#define PROJECT_LIS3MDL_SPI_INSTANCE_COUNT 1U
typedef struct { PlatformI2cId i2c; PlatformTimeId time; } ProjectLis3mdlI2cResources;
typedef struct { PlatformSpiId spi; PlatformGpioId cs; PlatformTimeId time; } ProjectLis3mdlSpiResources;
SystemDeviceResult ProjectLis3mdlI2cResources_Get(uint8_t, ProjectLis3mdlI2cResources *);
SystemDeviceResult ProjectLis3mdlSpiResources_Get(uint8_t, ProjectLis3mdlSpiResources *);
#endif
""",
        encoding="utf-8",
    )
    core = BUILTIN / "silverstar_core_0_1_0" / "payload"
    includes = [
        tmp_path,
        PAYLOAD / "Devices/Magnetometer/LIS3MDL/Inc",
        core / "Interfaces/Inc",
        core / "Common/Inc",
        BUILTIN / "silverstar_platform_api/payload/Platform/Inc",
    ]
    flags = [
        _Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-Wconversion", "-Wsign-conversion", "-Wshadow", "-Wvla",
    ]
    flags += ["-I" + str(path) for path in includes]
    source = PAYLOAD / "Devices/Magnetometer/LIS3MDL/Src"
    for name, sources in (
        ("core", [source / "lis3mdl_core.c", PAYLOAD / "Tests/Host/test_lis3mdl_core.c"]),
        ("adapter", [source / "lis3mdl_core.c", source / "lis3mdl_adapter.c",
                     PAYLOAD / "Tests/Host/test_lis3mdl_adapter.c"]),
    ):
        binary = tmp_path / f"lis3mdl_{name}.exe"
        _Command_Run(flags + [str(path) for path in sources] + ["-lm", "-o", str(binary)],
                     tmp_path, f"compile_{name}")
        _Command_Run([str(binary)], tmp_path, f"run_{name}")
    _Command_Run(flags + ["-c", str(source / "lis3mdl_instance.c"),
                          "-o", str(tmp_path / "lis3mdl_instance.o")],
                 tmp_path, "compile_instance")


def test_lis3mdl_one_physical_plugin_two_bus_variants(builtin_catalog) -> None:
    manifest = PluginManifest_Load(LIS3MDL)
    assert manifest.physical_device is not None
    assert manifest.physical_device.model == "LIS3MDL"
    assert set(manifest.device_variants) == {"i2c", "spi"}
    for variant_id, kind in (("i2c", "i2c"), ("spi", "spi")):
        resolved = PluginManifest_VariantResolve(manifest, variant_id)
        assert resolved.resource_requirements[0].kind == kind
        assert resolved.metadata["device_descriptors"][0]["physical_device_id"] == (
            "PROJECT_PHYSICAL_DEVICE_ID_LIS3MDL"
        )
        assert sum(source.endswith("lis3mdl_core.c") for source in resolved.build.sources) == 1
    assert builtin_catalog.Component_Get(manifest.component_id).version == "0.1.0"


def test_lis3mdl_i2c_generated_resource_and_dispatch(builtin_catalog) -> None:
    model = _CustomModel_Create(
        builtin_catalog,
        [DeviceInstance("mag0", "silverstar.device.magnetometer.lis3mdl", "i2c", "uhp_20_hz_4g")],
    )
    model.resource_assignments = {"mag0:data": "I2C1", "mag0:time": "SYSTEM_TIME"}
    resolution = ResourceAssignments_Resolve(model, builtin_catalog)
    assert resolution.valid, resolution
    header = _ResourceHeader_Render(model, builtin_catalog)
    source = _DeviceInstancesSource_Render(model, builtin_catalog.ProjectView_Get(model))
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "ProjectLis3mdlI2cResources_Get" in header
    assert "Lis3mdlI2cMagnetometerInstance_Process(0U)" in source
    assert sum(path.endswith("lis3mdl_core.c") for path in graph.sources) == 1


def test_lis3mdl_spi_generated_resource_and_dispatch(builtin_catalog) -> None:
    model = _CustomModel_Create(
        builtin_catalog,
        [DeviceInstance("mag0", "silverstar.device.magnetometer.lis3mdl", "spi", "uhp_20_hz_4g")],
    )
    source = _DeviceInstancesSource_Render(model, builtin_catalog.ProjectView_Get(model))
    graph = SourceGraph_Resolve(model, builtin_catalog)
    manifest = builtin_catalog.ProjectView_Get(model).InstanceIdComponent_Get("mag0")
    assert manifest.instance_resource_binding is not None
    assert manifest.instance_resource_binding.accessor == "ProjectLis3mdlSpiResources_Get"
    assert {field.member for field in manifest.instance_resource_binding.fields} == {
        "spi", "cs", "time"
    }
    assert "Lis3mdlSpiMagnetometerInstance_Process(0U)" in source
    assert sum(path.endswith("lis3mdl_core.c") for path in graph.sources) == 1
