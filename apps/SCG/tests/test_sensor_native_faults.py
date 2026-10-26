"""Actual native C fault paths with a test-only assertion trap."""
from pathlib import Path
import shutil
import subprocess


def test_pressure_mag_corrupt_state_traps_before_io_and_bus_fault_never_publishes(tmp_path):
    app = Path(__file__).resolve().parents[1]
    builtin = app / 'plugins/builtin'
    bmp = builtin / 'silverstar_device_barometer_bmp390/payload/Devices/Barometer/BMP390'
    mmc = builtin / 'silverstar_device_magnetometer_mmc5983ma/payload/Devices/Magnetometer/MMC5983MA'
    common = builtin / 'silverstar_core_0_1_0/payload/Common/Inc'
    compiler = shutil.which('gcc')
    assert compiler
    output = tmp_path / 'native_faults.exe'
    command = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wconversion',
               '-Wsign-conversion', '-Wshadow', '-Wmissing-prototypes', '-fanalyzer',
               '-I'+str(bmp/'Inc'), '-I'+str(mmc/'Inc'), '-I'+str(common),
               str(bmp/'Src/bmp390_core.c'), str(mmc/'Src/mmc5983ma_core.c'),
               str(app/'tests/fixtures/sensors/test_pressure_mag_faults.c'), '-lm', '-o', str(output)]
    compiled = subprocess.run(command, text=True, capture_output=True, timeout=60)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    checked = subprocess.run([str(output)], text=True, capture_output=True, timeout=10)
    assert checked.returncode == 0, checked.stdout + checked.stderr
