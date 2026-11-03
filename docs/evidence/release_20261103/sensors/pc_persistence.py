"""Cross the PC fit, firmware packet, durable slot and independent boot processes."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "apps/GSHC"))
from services.magnetometer_calibration import MagCalibration_Fit, MagCalibrationFitStatus
from services.magnetometer_maintenance import MagMaintenance_CalibrationPacketBuild


def main():
    exe, work, report = map(Path, sys.argv[1:4])
    work.mkdir(parents=True, exist_ok=False)
    index = np.arange(600)
    z = 1 - 2 * (index + 0.5) / 600
    angle = index * np.pi * (3 - np.sqrt(5))
    radius = np.sqrt(1 - z * z)
    sphere = 50 * np.column_stack((radius * np.cos(angle), radius * np.sin(angle), z))
    distortion = np.array([[1.16, 0.08, -0.02], [0.08, 0.85, 0.02], [-0.02, 0.02, 1.08]])
    pts = sphere @ distortion + (12, -8, 3)
    fit = MagCalibration_Fit(pts, 50)
    assert fit.status is MagCalibrationFitStatus.READY
    packet = MagMaintenance_CalibrationPacketBuild(0, 11, fit)
    crc = int.from_bytes(packet[-4:], "little")
    expected = np.asarray(fit.soft_iron) @ (np.array([13., -6., 6.]) - fit.hard_iron_uT)
    rows = []
    slots = work / "storage-port-slots.bin"
    for loaded, mode in enumerate(("tf_pc_save", "tf_pc_reboot")):
        cmd = [str(exe), mode, packet.hex() if not loaded else "-", str(slots)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr + result.stdout
        fields = result.stdout.strip().split()
        assert fields[0] == "readback"
        ids = tuple(map(int, fields[1:6]))
        assert ids == (11, 1, crc, 0x13572468, loaded)
        np.testing.assert_allclose(np.asarray(fields[6:], float), expected, atol=2e-5)
        rows.append(dict(command=cmd, exit_code=result.returncode, status=result.stdout.strip()))
    report.write_text(json.dumps(dict(rows=rows, packet_hex=packet.hex(),
        expected_vector=expected.tolist(), slots_sha256=hashlib.sha256(slots.read_bytes()).hexdigest(),
        host_exe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
        scope="Real PC solver/codec, C decode/apply, real A/B persistence service, fresh-process boot reload. Simulated slot hardware."),
        indent=2)+"\n", encoding="utf8")


if __name__ == "__main__":
    main()
