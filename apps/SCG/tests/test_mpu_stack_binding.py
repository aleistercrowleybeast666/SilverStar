"""Binding negatives use injected ELF output; actual ARM reports are separate."""
import json
import re
from pathlib import Path

import pytest
from test_stack_budget import stacks, _ElfFixture_Create, _DependencyFixture_Write


def _MpuFixture(root, monkeypatch, mutation=None):
    root = _ElfFixture_Create(root, monkeypatch)
    original_read = stacks.Command_Read
    builtin = Path(__file__).resolve().parents[1] / "plugins/builtin"
    bus = builtin / "silverstar_sensor_register_bus/payload"
    mpu = builtin / "silverstar_device_imu_mpu6050/payload"
    paths = [
        "Devices/SensorBus/Src/sensor_imu.c",
        "Devices/SensorBus/Src/sensor_register_bus.c",
        "Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c",
        "Devices/IMU/MPU6050/Adapter/Src/mpu6050_instance.c",
        "Devices/IMU/MPU6050/Src/mpu6050_device.c",
    ]
    for path in paths + ["Devices/SensorBus/Inc/sensor_imu.h", "Devices/SensorBus/Inc/sensor_register_bus.h", "Devices/SensorBus/Adapter/Inc/sensor_imu_adapter.h"]:
        text = ((mpu if "/MPU6050/" in path else bus) / path).read_text(encoding="utf8")
        if mutation in ("runtime_bus", "runtime_profile") and path.endswith("mpu6050_instance.c"):
            write = "driver.bus.read = UnknownCallback" if mutation == "runtime_bus" else "driver.profile = other"
            text = text.replace("s_contexts[instance].owner_active = 1U;", "s_contexts[instance]." + write + "; s_contexts[instance].owner_active = 1U;")
        if mutation == "body" and path.endswith("sensor_register_bus.c"):
            text = text.replace("bus->read(", "replacement_read(")
        if mutation == "getter" and path.endswith("mpu6050_device.c"):
            text = text.replace("return &s_profile;", "return arbitrary_profile;")
        if mutation == "profile" and path.endswith("mpu6050_device.c"):
            text, count = re.subn(r"(static const SensorImuProfile s_profile\s*=\s*\{)",
                r"\1\n    .prepare = UnknownCallback,", text)
            assert count == 1
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf8")
    (root / "SilverStar.ssproject").write_text(json.dumps({
        "build": {"target_profile": "SilverStar_F407"},
        "components": {"devices": [{"plugin": "silverstar.device.imu.mpu6050"}]},
    }), encoding="utf8")
    (root / "Generated/project_sources.mk").write_text(
        "C_SOURCES += \\\n  test.c \\\n  " + " \\\n  ".join(paths) + "\n\n", encoding="utf8")
    build = root / "build/FCCG/SilverStar_F407/Release"
    for path in paths:
        su = build / Path(path).with_suffix(".su")
        su.parent.mkdir(parents=True, exist_ok=True)
        su.write_text("", encoding="utf8")
        _DependencyFixture_Write(su.with_suffix(".d"), path, monkeypatch)
    edges = {
        "SensorImu_Verify": ["SensorRegister_Read"],
        "SensorImu_ProcessConfigure": ["SensorRegister_Write"],
        "SensorImu_Read": ["SensorRegister_Read"],
        "SensorRegister_Read": [], "SensorRegister_Write": [],
        "SensorImuAdapter_ReadRegister": ["PlatformI2c_MemoryRead"],
        "SensorImuAdapter_WriteRegister": [],
        "PlatformI2c_MemoryRead": ["HAL_I2C_Mem_Read"],
        "HAL_I2C_Mem_Read": ["PlatformI2cDeadline_Expired"],
        "PlatformI2cDeadline_Expired": [],
        "Mpu6050_ProfileGet": [], "SensorImu_Init": [],
        "SensorImuAdapter_PrepareI2c": ["SensorImu_Init"],
        "Mpu6050ImuInstance_Init": ["SensorImuAdapter_PrepareI2c"],
    }
    if mutation == "caller":
        edges["UnreviewedInit"] = ["SensorImu_Init"]
    if mutation == "missing_target":
        del edges["SensorImuAdapter_ReadRegister"]
    if mutation == "recursion":
        edges["HAL_I2C_Mem_Read"] = ["SensorImu_Verify"]
    indirect = {"SensorImu_Verify", "SensorImu_ProcessConfigure", "SensorImu_Read",
                "SensorRegister_Read", "SensorRegister_Write"}
    extra = ""
    for name, callees in edges.items():
        extra += "08000000 <" + name + ">:\n"
        for callee in callees:
            extra += " 8000000: f000 f000 bl 8000000 <" + callee + ">\n"
        if name in indirect or (mutation == "unknown_hal" and name == "HAL_I2C_Mem_Read"):
            extra += " 8000004: 4798 blx r3\n"
        if mutation == "extra_call" and name == "SensorImu_Verify":
            extra += " 8000006: 4790 blx r2\n"
        if name == "Mpu6050_ProfileGet":
            extra += " 8000008: 08001000 .word 0x08001000\n"
        extra += " 800000c: 4770 bx lr\n"
    frames = {"SensorImu_Verify": 24, "SensorImuAdapter_ReadRegister": 112,
              "HAL_I2C_Mem_Read": 64, "PlatformI2cDeadline_Expired": 24}
    with (build / "test.su").open("a", encoding="utf8") as stream:
        for name in edges:
            stream.write("fixture.c:1:1:" + name + "\t" + str(frames.get(name,16)) + "\tstatic\n")
    def read(command, cwd):
        if "objdump" in command[0] and "-s" in command:
            pointer = "01000000" if mutation == "non_null" else "00000000"
            return ("file format elf32-littlearm\nContents of section .rodata:\n"
                " 8001000 00000000 00000000 00000000 00000000\n"
                " 8001010 " + pointer + " 00000000 00000000\n")
        text = original_read(command, cwd)
        if "objdump" in command[0]:
            return text.replace("08000000 <AppTask_Device>:\n",
                "08000000 <AppTask_Device>:\n 8000000: f000 f000 bl 8000000 <SensorImu_Verify>\n") + extra
        if "nm" in command[0]:
            return text + "08001000 00000060 " + ("d" if mutation == "writable" else "r") + " s_profile\n"
        return text
    monkeypatch.setattr(stacks, "Command_Read", read)
    return root


def test_mpu_register_callbacks_include_platform_deadline_subtree(tmp_path, monkeypatch):
    report = stacks.StackReport_Build(_MpuFixture(tmp_path, monkeypatch), "Release", "fixture-")
    assert report["passes"]
    device = next(row for row in report["tasks"] if row["task"] == "Device")
    assert device["call_chain_bytes"] == 64 + 24 + 16 + 112 + 16 + 64 + 24
    assert device["chain"][-1]["function"] == "PlatformI2cDeadline_Expired"


@pytest.mark.parametrize("mutation,message", [
    ("body", "Changed reviewed callback binding body"),
    ("getter", "Changed immutable MPU profile getter"),
    ("profile", "Unreviewed MPU optional profile callbacks"),
    ("non_null", "Linked MPU optional callbacks are not NULL"),
    ("writable", "MPU profile is not one linked read-only object"),
    ("caller", "Unreviewed linked SensorImu initialization provenance"),
    ("extra_call", "Extra indirect MPU callback instruction"),
    ("missing_target", "Missing concrete MPU register callback"),
    ("unknown_hal", "Unresolved stack usage"),
    ("recursion", "Recursive stack path"),
])
def test_mpu_binding_fails_closed(tmp_path, monkeypatch, mutation, message):
    with pytest.raises(ValueError, match=message):
        stacks.StackReport_Build(_MpuFixture(tmp_path, monkeypatch, mutation), "Release", "fixture-")

@pytest.mark.parametrize("mutation", ["runtime_bus", "runtime_profile"])
def test_mpu_parent_counterexamples_rejected(tmp_path, monkeypatch, mutation):
    with pytest.raises(ValueError):
        stacks.StackReport_Build(_MpuFixture(tmp_path, monkeypatch, mutation), "Release", "fixture-")
