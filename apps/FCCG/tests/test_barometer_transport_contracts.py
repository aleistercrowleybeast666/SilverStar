from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from test_joint_sensor_library import _Command_Run, _Compiler_Get

BUILTIN = Path(__file__).resolve().parents[1] / "plugins/builtin"


def _Function_Remove(text: str, name: str) -> str:
    start = re.search(r"^[^\n;]+\b" + name + r"\(", text, re.M).start()
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[:start] + text[end:]


def _Flags_Get(chip: str, tmp_path: Path) -> tuple[list[str], Path]:
    payload = BUILTIN / f"silverstar_device_barometer_{chip}" / "payload"
    includes = [tmp_path, payload / f"Devices/Barometer/{chip.upper()}/Inc",
                BUILTIN / "silverstar_core_0_1_0/payload/Interfaces/Inc",
                BUILTIN / "silverstar_core_0_1_0/payload/Common/Inc",
                BUILTIN / "silverstar_platform_api/payload/Platform/Inc"]
    (tmp_path / "system_version.h").write_text(
        '#define SILVERSTAR_PRODUCT_STRING "SilverStar 0.1.1"\n', encoding="utf-8")
    return ([_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-Wconversion", "-Wsign-conversion", "-Wshadow", "-Wvla", "-fanalyzer"]
            + ["-I" + str(path) for path in includes], payload)


@pytest.mark.parametrize("chip,prefix,address", [("bmp280", "Bmp280", "0x76U"),
                                                ("ms5611", "Ms5611", "0x77U")])
@pytest.mark.parametrize("transport", ["i2c", "spi"])
@pytest.mark.parametrize("optimization", ["-O0", "-O2"])
def test_single_transport_links_without_inactive_backend(
    tmp_path: Path, chip: str, prefix: str, address: str,
    transport: str, optimization: str,
) -> None:
    flags, payload = _Flags_Get(chip, tmp_path)
    fixture = (payload / f"Tests/Host/test_{chip}_adapter.c").read_text(encoding="utf-8")
    # Deliberately omit every inactive backend definition. Successful linking
    # proves no phantom hardware library is needed, even without optimization.
    inactive = (["PlatformGpio_Write", "PlatformSpi_Transfer"] if transport == "i2c"
                else ["PlatformI2c_MemoryRead", "PlatformI2c_MemoryWrite"] if chip == "bmp280"
                else ["PlatformI2c_Write", "PlatformI2c_MemoryRead"])
    for name in inactive:
        fixture = _Function_Remove(fixture, name)
    if transport == "i2c" and chip == "bmp280":
        fixture = fixture.replace("static uint8_t s_cs_high = 1U;\n", "")
    fixture = _Function_Remove(fixture, "main")
    active_init = (f"{prefix}Adapter_InitI2c(&adapter, PLATFORM_I2C_1, {address})"
                   if transport == "i2c" else
                   f"{prefix}Adapter_InitSpi(&adapter, PLATFORM_SPI_1, PLATFORM_GPIO_0)")
    inactive_init = (f"{prefix}Adapter_InitSpi(&adapter, PLATFORM_SPI_1, PLATFORM_GPIO_0)"
                     if transport == "i2c" else
                     f"{prefix}Adapter_InitI2c(&adapter, PLATFORM_I2C_1, {address})")
    inactive_interface = f"{prefix}Interface" + ("Spi" if transport == "i2c" else "I2c")
    write = "0xF4U, 0x55U" if chip == "bmp280" else "0x1EU"
    fixture += f"""
int main(void)
{{
    {prefix}Adapter adapter;
    uint8_t byte;
    uint32_t i2c_reads, spi_reads;
    Test{prefix}_Seed();
    assert({inactive_init} == SYSTEM_DEVICE_INVALID_ARGUMENT);
    assert({active_init} == SYSTEM_DEVICE_OK);
    Test{prefix}_Run(&adapter);
    assert({'s_i2c_reads > 0U && s_spi_reads == 0U' if transport == 'i2c' else 's_i2c_reads == 0U && s_spi_reads > 0U'});
    i2c_reads = s_i2c_reads; spi_reads = s_spi_reads;
    adapter.interface = {inactive_interface};
    assert({prefix}Bus_Read(&adapter, 0U, &byte, 1U) == {prefix}BusError);
    assert({prefix}Bus_Write(&adapter, {write}) == {prefix}BusError);
    adapter.interface = ({prefix}Interface)99;
    assert({prefix}Bus_Read(&adapter, 0U, &byte, 1U) == {prefix}BusError);
    assert({prefix}Bus_Write(&adapter, {write}) == {prefix}BusError);
    assert(s_i2c_reads == i2c_reads && s_spi_reads == spi_reads);
    return 0;
}}
"""
    test_source = tmp_path / "single_transport.c"
    test_source.write_text(fixture, encoding="utf-8")
    flags += [optimization, f"-DSYSTEM_BUILD_{chip.upper()}_I2C_ENABLED={int(transport == 'i2c')}U",
              f"-DSYSTEM_BUILD_{chip.upper()}_SPI_ENABLED={int(transport == 'spi')}U"]
    source = payload / f"Devices/Barometer/{chip.upper()}/Src"
    binary = tmp_path / "transport.exe"
    _Command_Run(flags + [str(source / f"{chip}_core.c"), str(source / f"{chip}_adapter.c"),
                          str(test_source), "-lm", "-o", str(binary)], tmp_path, "compile_transport")
    _Command_Run([str(binary)], tmp_path, "run_transport")


@pytest.mark.parametrize("chip,prefix", [("bmp280", "Bmp280"), ("ms5611", "Ms5611")])
def test_corrupt_stored_contract_stops_before_bus_access(
    tmp_path: Path, chip: str, prefix: str,
) -> None:
    if os.name == "nt":
        ctypes.windll.kernel32.SetErrorMode(3)
    flags, payload = _Flags_Get(chip, tmp_path)
    fixture = (payload / f"Tests/Host/test_{chip}_core.c").read_text(encoding="utf-8")
    fixture = '#include <stdio.h>\n' + fixture
    for function in (f"{prefix}Bus_Read", f"{prefix}Bus_Write"):
        start = fixture.index(function + "(")
        brace = fixture.index("{", start)
        fixture = fixture[:brace + 1] + '\n    (void)puts("BUS_ACCESS"); (void)fflush(stdout);' + fixture[brace + 1:]
    fixture = fixture.replace("int main(void)", "static int TestNormal(void)")
    fixture += f"""
int main(int argc, char **argv)
{{
    Test{prefix}Bus bus;
    {prefix}Context context;
    {prefix}Port port;
    if (argc == 1) {{ return TestNormal(); }}
    {'TestBmp280_BusSeed' if chip == 'bmp280' else 'TestMs5611_Seed'}(&bus); port.bus = &bus;
    {prefix}_Init(&context, &port);
    if (argv[1][0] == 's') {{ context.state = ({prefix}State)99; }}
    else if (argv[1][0] == 'b') {{ context.port.bus = NULL; }}
    {'else { context.state = Ms5611StateReadProm; context.prom_index = 8U; }' if chip == 'ms5611' else ''}
    (void)puts("BOUNDARY_BEGIN"); (void)fflush(stdout);
    (void){prefix}_Step(&context, 0U);
    (void)puts("FAULT_RETURNED");
    return 0;
}}
"""
    test_source = tmp_path / "corrupt.c"; test_source.write_text(fixture, encoding="utf-8")
    binary = tmp_path / "corrupt.exe"
    _Command_Run(flags + [str(payload / f"Devices/Barometer/{chip.upper()}/Src/{chip}_core.c"),
                          str(test_source), "-lm", "-o", str(binary)], tmp_path, "compile_corrupt")
    for fault in (["state", "bus", "index"] if chip == "ms5611" else ["state", "bus"]):
        command = [str(binary), fault]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        output = result.stdout + result.stderr
        (tmp_path / (fault + ".txt")).write_text(json.dumps(command) + "\n" + output
                                                  + f"\nexit_code={result.returncode}\n", encoding="utf-8")
        assert result.returncode != 0
        assert "BOUNDARY_BEGIN" in output
        assert "BUS_ACCESS" not in output and "FAULT_RETURNED" not in output
