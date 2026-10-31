from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


# The six original scheduling expectations now use the active S generation and
# actual current service/driver. Legacy M0 codec byte tests remain in their
# explicit compatibility suite; normal firmware generation never enables M0.
from test_ss_tm_scheduler_host import tm_scheduler


@pytest.mark.parametrize("scenario", ["contended", "no_navigation", "unavailable",
    "no_imu", "recovery", "outside_mission"])
def test_generated_flight_scheduler(tm_scheduler, scenario):
    executable = tm_scheduler
    result = subprocess.run([str(executable), scenario], capture_output=True,
                            text=True, encoding="utf8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 failures" in result.stdout
    if scenario == "contended":
        # Use the actual generated C payload bytes in the unchanged GSHC parser.
        import struct
        import sys
        gshc = Path(__file__).resolve().parents[2] / "GSHC"
        sys.path.insert(0, str(gshc))
        try:
            from protocol.air import AirFlightStateMessage
            from protocol.ss_tm import TelemetryFrame_Parse
            frames = [bytes.fromhex(line.split()[1]) for line in result.stdout.splitlines()
                      if line.startswith("FLIGHT_HEX ")]
            assert frames
            for frame in frames:
                _, message, _ = TelemetryFrame_Parse(frame)
                assert isinstance(message, AirFlightStateMessage)
                assert len(frame) == 56
                assert struct.unpack_from("<ffffff", frame, 32) == pytest.approx(
                    [-0.0981511548, 0.0991782993, 0.0932015106,
                     -0.467806935, 0.483857244, 0.072262131])
        finally:
            sys.path.remove(str(gshc))
