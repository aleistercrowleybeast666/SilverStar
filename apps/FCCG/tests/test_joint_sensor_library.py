from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from silverstar_fccg.plugins.manifest import PluginManifest_Load, PluginManifest_VariantResolve

ROOT = Path(__file__).resolve().parents[1]
BUILTIN = ROOT / "plugins" / "builtin"
FIXTURES = ROOT / "tests" / "fixtures" / "sensors"
IMU_MODELS = (
    "MPU6000", "MPU6050", "MPU6500", "MPU9250", "LSM6DSV32X", "LSM6DSV320X",
    "ICM42605", "ICM42688P",
)
SPECIAL_IMU_MODELS = ("BMI088", "BMI323", "ICM45686")
SPI_IMU_MODELS = tuple(name + "_SPI" for name in IMU_MODELS + SPECIAL_IMU_MODELS if name != "MPU6050")
GNSS_MODELS = ("neo_m8n", "max_m10s", "neo_f10n")
SYNC_IMU_MODELS = ("BMI088_SYNC400", "BMI088_SYNC400_SPI")


def _ImuVariant_Get(name: str):
    normalized = name.lower()
    interface = "spi" if normalized.endswith("_spi") else "i2c"
    chip = normalized.removesuffix("_spi").removesuffix("_sync400")
    folder = "silverstar_device_imu_" + chip
    manifest = PluginManifest_Load(BUILTIN / folder / "plugin.json")
    if not manifest.device_variants:
        return folder, manifest, "", ""
    selected = next(
        variant_id for variant_id, variant in manifest.device_variants.items()
        if variant["interface"] == interface
        and ("sync400" in normalized) == ("sync400" in variant_id)
    )
    variant = manifest.device_variants[selected]
    return (
        folder, PluginManifest_VariantResolve(manifest, selected),
        variant["interface"], variant["profile"],
    )


def test_joint_bmi088_sync_actual_c_mock(tmp_path: Path) -> None:
    common = BUILTIN / "silverstar_sensor_register_bus/payload/Devices/SensorBus"
    core = BUILTIN / "silverstar_core_0_1_0/payload"
    includes = [common / "Inc", core / "Interfaces/Inc", core / "System/Inc",
                BUILTIN / "silverstar_mcu_stm32f407vet6/payload/Platform/Inc"]
    sources = [common / "Src" / name for name in ("sensor_register_bus.c", "sensor_imu.c",
               "sensor_imu_adapter.c", "sensor_imu_spi_adapter.c", "sensor_bmi088_sync.c")]
    binary = tmp_path / "bmi088_sync.exe"
    command = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic"]
    command += ["-I" + str(path) for path in includes] + [str(path) for path in sources]
    command += [str(FIXTURES / "test_bmi088_sync.c"), "-o", str(binary)]
    _Command_Run(command, tmp_path, "compile_sync")
    output = _Command_Run([str(binary)], tmp_path, "run_sync")
    assert output.count("official image/reset/readback/pairing/order/gap/reentry/cross-epoch/stall/errors PASS") == 2


def test_joint_sensor_real_generation_dual_i2c_binding(builtin_catalog, tmp_path: Path) -> None:
    from test_internal_platform_refactor import _CustomModel_Create

    from silverstar_fccg.generator.render import _ResourceHeader_Render
    from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
    from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
    from silverstar_fccg.project.model import DeviceInstance
    from silverstar_fccg.project.resources import ResourceAssignments_Resolve

    model = _CustomModel_Create(builtin_catalog, [DeviceInstance("imu0", "silverstar.device.imu.bmi088")])
    model.resource_assignments = {"imu0:data": "I2C1", "imu0:gyro": "I2C1", "imu0:time": "SYSTEM_TIME"}
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    resolution = ResourceAssignments_Resolve(model, builtin_catalog)
    assert resolution.valid, resolution
    header = _ResourceHeader_Render(model, builtin_catalog)
    assert "PlatformI2cId gyro_i2c;" in header
    assert "ProjectBmi088Resources_Get" in header
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "Devices/SensorBus/Src/sensor_imu.c" in graph.sources
    assert "Devices/IMU/BMI088/Src/bmi088_instance.c" in graph.sources
    (tmp_path / "project_resources.h").write_text(header, encoding="utf-8")
    source = tmp_path / "check.c"
    source.write_text('#include "project_resources.h"\nint main(void) { return sizeof(ProjectBmi088Resources) == 0; }\n', encoding="utf-8")
    includes = [tmp_path, BUILTIN / "silverstar_mcu_stm32f407vet6/payload/Platform/Inc", BUILTIN / "silverstar_mcu_stm32f407vet6/payload/Platform/STM32F4/Inc", BUILTIN / "silverstar_core_0_1_0/payload/Interfaces/Inc"]
    _Command_Run([_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-c", str(source), "-o", str(tmp_path / "check.o")] + ["-I"+str(path) for path in includes], tmp_path, "compile_resource")
    # The separate gyro address must participate in ordinary collision checking.
    model.device_instances.append(DeviceInstance("conflict", "silverstar.device.imu.mpu6050"))
    model.resource_assignments.update({"conflict:data": "I2C1", "conflict:time": "SYSTEM_TIME"})
    assert not ResourceAssignments_Resolve(model, builtin_catalog).valid


def test_joint_sensor_st240_jy_aux200_generated_profile_compiles(builtin_catalog, tmp_path: Path) -> None:
    from silverstar_fccg.generator.render import (
        _DeviceBuildCapabilitiesHeader_Render,
        _FlightConfigHeader_Render,
    )
    from silverstar_fccg.project.model import DeviceInstance
    from silverstar_fccg.project.reference import ReferenceProject_Create

    model = ReferenceProject_Create("MixedRateProfile", catalog=builtin_catalog)
    model.device_instances.insert(0, DeviceInstance("st0", "silverstar.device.imu.lsm6dsv32x"))
    model.capability_source_overrides.update({"imu.acceleration": "st0", "imu.angular_rate": "st0"})
    header = _FlightConfigHeader_Render(model, builtin_catalog)
    assert any(line.split() == ["#define", "SYSTEM_IMU_OUTPUT_RATE_HZ", "240U"] for line in header.splitlines())
    from silverstar_fccg.generator.render import AlgorithmParametersHeader_Render
    (tmp_path / "project_algorithm_parameters.h").write_text(AlgorithmParametersHeader_Render(model, builtin_catalog), encoding="utf-8")
    (tmp_path / "project_flight_config.h").write_text(header, encoding="utf-8")
    (tmp_path / "project_device_build_capabilities.h").write_text(_DeviceBuildCapabilitiesHeader_Render(model, builtin_catalog), encoding="utf-8")
    core = BUILTIN / "silverstar_core_0_1_0/payload"
    source = tmp_path / "rates.c"
    source.write_text('#include "project_flight_config.h"\n#include "system_user_config.h"\n_Static_assert(SYSTEM_IMU_OUTPUT_RATE_HZ == 240U, "ST ODR");\n_Static_assert(SYSTEM_MAGNETOMETER_OUTPUT_RATE_HZ == 200U, "JY auxiliary ODR");\nint main(void) { return 0; }\n', encoding="utf-8")
    includes = [tmp_path, core / "System/User", core / "System/Inc", core / "Interfaces/Inc"]
    for component in model.ComponentIds_Get():
        manifest = builtin_catalog.Component_Get(component)
        includes.extend(manifest.payload_root / relative for relative in manifest.build.include_dirs)
    command = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-c"] + ["-I"+str(path) for path in includes]
    _Command_Run(command + [str(source), "-o", str(tmp_path / "rates.o")], tmp_path, "compile_rates")
    _Command_Run(command + ["-include", str(tmp_path / "project_flight_config.h"), str(core / "System/Src/system_profile.c"), "-o", str(tmp_path / "profile.o")], tmp_path, "compile_profile")


def test_joint_sensor_qualification_uses_actual_primary(builtin_catalog) -> None:
    from silverstar_fccg.project.capabilities import CapabilityResolution_Resolve
    from silverstar_fccg.project.model import DeviceInstance
    from silverstar_fccg.project.reference import ReferenceProject_Create

    model = ReferenceProject_Create("QualifiedSource", catalog=builtin_catalog)
    model.device_instances.insert(0, DeviceInstance("st0", "silverstar.device.imu.lsm6dsv32x"))
    result = CapabilityResolution_Resolve(model, builtin_catalog)
    assert not result.source_conflicts
    jy = next(instance.instance_id for instance in model.device_instances if instance.plugin.endswith("jy901b"))
    model.capability_source_overrides["imu.acceleration"] = jy
    assert CapabilityResolution_Resolve(model, builtin_catalog).source_conflicts
    model.capability_source_overrides.clear()
    model.device_instances[0] = DeviceInstance("bmi0", "silverstar.device.imu.bmi088")
    assert CapabilityResolution_Resolve(model, builtin_catalog).source_conflicts
    # An unused qualification must not constrain a raw-only consumer.
    model.strategies = {}
    model.modes = {}
    result = CapabilityResolution_Resolve(model, builtin_catalog)
    assert not any("_qualified=" in value for value in result.source_conflicts)


def _Compiler_Get() -> str:
    compiler = shutil.which("gcc")
    assert compiler is not None, "Real Host GCC is required for sensor acceptance"
    return compiler


def _Command_Run(command: list[str], directory: Path, label: str) -> str:
    if "gcc" in Path(command[0]).name:
        common = BUILTIN / "silverstar_core_0_1_0/payload/Common"
        command = command + ["-I" + str(common / "Inc")]
        if "-c" in command:
            command += ["-Wconversion", "-Wsign-conversion", "-Wshadow", "-Wundef", "-Wformat=2", "-Wdouble-promotion", "-Wcast-align", "-Wcast-qual", "-Wstrict-prototypes", "-Wmissing-prototypes", "-Wswitch-enum", "-Wvla"]
        if "-c" not in command and not any("test_jy901b_quality.c" in arg for arg in command):
            command = command + [str(common / "Src/silverstar_assert.c")]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    output = result.stdout + result.stderr
    (directory / (label + ".txt")).write_text(
        json.dumps(command) + "\n" + output + f"\nexit_code={result.returncode}\n",
        encoding="utf-8",
    )
    assert result.returncode == 0, output
    return output


def test_joint_imu_actual_c_mock(tmp_path: Path) -> None:
    common = BUILTIN / "silverstar_sensor_register_bus/payload/Devices/SensorBus"
    command = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic"]
    command.extend(["-I" + str(common / "Inc"), str(common / "Src/sensor_register_bus.c"), str(common / "Src/sensor_imu.c"), str(common / "Src/sensor_high_g.c")])
    for model in IMU_MODELS:
        component = BUILTIN / ("silverstar_device_imu_" + model.lower()) / "payload/Devices/IMU" / model
        command.extend(["-I" + str(component / "Inc"), str(component / "Src" / (model.lower() + "_device.c"))])
    binary = tmp_path / "imu.exe"
    command.extend([str(FIXTURES / "test_sensor_imu.c"), "-o", str(binary)])
    _Command_Run(command, tmp_path, "compile")
    output = _Command_Run([str(binary)], tmp_path, "run")
    for model in IMU_MODELS:
        assert model + ": ID/reset/readback/SI/clip/epoch/idempotence/errors PASS" in output


def test_joint_ubx_actual_c_mock(tmp_path: Path) -> None:
    source = BUILTIN / "silverstar_ubx_protocol/payload/Devices/GNSS/UBX"
    binary = tmp_path / "ubx.exe"
    command = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-I" + str(source / "Inc"), str(source / "Src/ubx_receiver.c"), str(FIXTURES / "test_ubx_receiver.c"), "-o", str(binary)]
    _Command_Run(command, tmp_path, "compile")
    output = _Command_Run([str(binary)], tmp_path, "run")
    for model in ("NEO-M8N", "NEO-M9N", "MAX-M10S", "NEO-F10N"):
        assert model + ": factory baud/config/readback/SI/week/reboot zero-write PASS" in output


def test_joint_ubx_adapter_actual_transactions(tmp_path: Path) -> None:
    source = BUILTIN / "silverstar_ubx_protocol/payload/Devices/GNSS/UBX"
    core = BUILTIN / "silverstar_core_0_1_0/payload"
    includes = [source / "Inc", core / "Interfaces/Inc", core / "System/Inc",
                BUILTIN / "silverstar_mcu_stm32f407vet6/payload/Platform/Inc"]
    binary = tmp_path / "ubx_adapter.exe"
    command = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic"]
    command += ["-I" + str(path) for path in includes]
    command += [str(source / "Src/ubx_receiver.c"), str(source / "Src/ubx_system_adapter.c"),
                str(FIXTURES / "test_ubx_adapter.c"), "-o", str(binary)]
    _Command_Run(command, tmp_path, "compile")
    output = _Command_Run([str(binary)], tmp_path, "run")
    assert output.count("adapter fresh read/response evidence/zero-write mismatch/timeout/explicit persistence PASS") == 4


@pytest.mark.parametrize("name", ["silverstar_sensor_register_bus", "silverstar_ubx_protocol"] + list(IMU_MODELS + SPECIAL_IMU_MODELS + SPI_IMU_MODELS + SYNC_IMU_MODELS) + ["silverstar_device_gnss_" + name for name in GNSS_MODELS])
def test_joint_sensor_manifest_has_real_sources(name: str) -> None:
    manifest = (
        PluginManifest_Load(BUILTIN / name / "plugin.json")
        if name.startswith(("silverstar_sensor_", "silverstar_ubx_", "silverstar_device_gnss_"))
        else _ImuVariant_Get(name)[1]
    )
    assert manifest.build.sources
    for relative in manifest.build.sources:
        assert (manifest.payload_root / relative).is_file()
    if not manifest.metadata.get("internal"):
        assert manifest.metadata["initialization"]["hardware_status"] == "HARDWARE_UNVERIFIED"
        assert manifest.metadata["device_instance_bindings"]
        assert manifest.instance_resource_binding is not None


def test_joint_sensor_adapters_compile_with_real_interfaces(tmp_path: Path) -> None:
    folders = ["silverstar_sensor_register_bus", "silverstar_ubx_protocol"]
    imu_names = IMU_MODELS + SPECIAL_IMU_MODELS + SPI_IMU_MODELS + SYNC_IMU_MODELS
    folders += [_ImuVariant_Get(name)[0] for name in imu_names]
    folders += ["silverstar_device_gnss_" + name for name in GNSS_MODELS]
    includes = [tmp_path, BUILTIN / "silverstar_mcu_stm32f407vet6/payload/Platform/Inc"]
    includes += [BUILTIN / "silverstar_core_0_1_0/payload" / name / "Inc" for name in ("Interfaces", "System", "Common")]
    sources: list[Path] = []
    resource_lines = ['#ifndef __PROJECT_RESOURCES_H', '#define __PROJECT_RESOURCES_H', '#include "system_device_types.h"', '#include "platform_i2c.h"', '#include "platform_uart.h"', '#include "platform_time.h"', '#include "platform_spi.h"', '#include "platform_gpio.h"']
    for index, folder in enumerate(folders):
        manifest = (
            _ImuVariant_Get(imu_names[index - 2])[1]
            if 2 <= index < 2 + len(imu_names)
            else PluginManifest_Load(BUILTIN / folder / "plugin.json")
        )
        includes.extend(manifest.payload_root / name for name in manifest.build.include_dirs)
        sources.extend(manifest.payload_root / name for name in manifest.build.sources)
        binding = manifest.instance_resource_binding
        if binding is None:
            continue
        manifest_data = json.loads((BUILTIN / folder / "plugin.json").read_text(encoding="utf-8"))
        if 2 <= index < 2 + len(imu_names) and "device_variants" in manifest_data:
            _, _, interface, profile = _ImuVariant_Get(imu_names[index - 2])
            variant_id = next(
                key for key, value in manifest_data["device_variants"].items()
                if value["interface"] == interface and value["profile"] == profile
            )
            from silverstar_fccg.plugins.manifest import _VariantOverlay_Apply
            _VariantOverlay_Apply(manifest_data, manifest_data["device_variants"][variant_id]["overrides"])
        kinds = {item["name"]: item["kind"] for item in manifest_data["requires"]["resources"]}
        types = {"uart": "PlatformUartId", "i2c": "PlatformI2cId", "spi": "PlatformSpiId", "time": "PlatformTimeId", "gpio_output": "PlatformGpioId", "gpio_interrupt": "PlatformGpioId"}
        fields = " ".join(types[kinds[item["requirement"]]] + " " + item["member"] + ";" for item in manifest_data["metadata"]["instance_resource_binding"]["fields"])
        resource_lines += [f"#define {binding.count_symbol} 2U", f"typedef struct {{ {fields} }} {binding.struct_type};", f"SystemDeviceResult {binding.accessor}(uint8_t instance, {binding.struct_type} *resources);"]
    resource_lines.append("#endif")
    (tmp_path / "project_resources.h").write_text("\n".join(resource_lines) + "\n", encoding="utf-8")
    for index, source in enumerate(sources):
        command = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic"]
        command.extend("-I" + str(path) for path in includes)
        command += ["-c", str(source), "-o", str(tmp_path / f"sensor_{index}.o")]
        _Command_Run(command, tmp_path, f"adapter_{index}")


def test_joint_special_imu_actual_c_mock(tmp_path: Path) -> None:
    common = BUILTIN / "silverstar_sensor_register_bus/payload/Devices/SensorBus"
    command = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic"]
    command += ["-I" + str(common / "Inc"), str(common / "Src/sensor_register_bus.c"), str(common / "Src/sensor_imu.c"), str(common / "Src/sensor_bmi088_fifo.c")]
    for model in SPECIAL_IMU_MODELS:
        root = BUILTIN / ("silverstar_device_imu_" + model.lower().removesuffix("_spi")) / "payload/Devices/IMU" / model
        command += ["-I" + str(root / "Inc"), str(root / "Src" / (model.lower() + "_device.c"))]
    binary = tmp_path / "special.exe"
    command += [str(FIXTURES / "test_sensor_special.c"), "-o", str(binary)]
    _Command_Run(command, tmp_path, "special_compile")
    output = _Command_Run([str(binary)], tmp_path, "special_run")
    assert "special sensor failure injection PASS" in output


def test_jy901b_actual_quality_and_ram_contract(tmp_path: Path) -> None:
    root = BUILTIN / "silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B"
    core = BUILTIN / "silverstar_core_0_1_0/payload"
    includes = [root / "Inc", root / "Adapter/Inc", core / "Interfaces/Inc", core / "Common/Inc"]
    binary = tmp_path / "jy_quality.exe"
    command = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic"]
    command += ["-I" + str(path) for path in includes]
    command += [str(root / "Adapter/Src/jy901b_sample_quality.c"), str(FIXTURES / "test_jy901b_quality.c"), "-o", str(binary)]
    _Command_Run(command, tmp_path, "jy_compile")
    assert "80B-48B ABI PASS" in _Command_Run([str(binary)], tmp_path, "jy_run")


def test_joint_spi_actual_transport_and_drdy(tmp_path: Path) -> None:
    common = BUILTIN / "silverstar_sensor_register_bus/payload/Devices/SensorBus"
    core = BUILTIN / "silverstar_core_0_1_0/payload"
    includes = [common / "Inc", core / "Interfaces/Inc", BUILTIN / "silverstar_mcu_stm32f407vet6/payload/Platform/Inc"]
    sources = [common / "Src" / name for name in ("sensor_register_bus.c", "sensor_imu.c", "sensor_imu_adapter.c", "sensor_imu_spi_adapter.c")]
    for model in ("MPU6000_SPI", "BMI088_SPI", "BMI323_SPI"):
        root = BUILTIN / ("silverstar_device_imu_" + model.lower().removesuffix("_spi")) / "payload/Devices/IMU" / model
        includes.append(root / "Inc")
        sources.append(root / "Src" / (model.lower() + "_device.c"))
    binary = tmp_path / "spi.exe"
    command = [_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic"]
    command += ["-I" + str(path) for path in includes] + [str(path) for path in sources]
    command += [str(FIXTURES / "test_sensor_spi.c"), "-o", str(binary)]
    _Command_Run(command, tmp_path, "spi_compile")
    output = _Command_Run([str(binary)], tmp_path, "spi_run")
    assert output.count("SPI command/dummy/CS/DRDY/isolation/timeout-release PASS") == 3
