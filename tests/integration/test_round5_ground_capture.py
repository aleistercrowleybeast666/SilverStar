from __future__ import annotations

import pytest

from tools import round5_ground_capture as capture


def test_ground_capture_passively_decodes_bounded_status_and_air(
    monkeypatch,
) -> None:
    from protocol.common import GspType
    from protocol.gsp_min import build_gsp_frame

    status = build_gsp_frame(int(GspType.GS_STATUS), bytes(12))
    ack = build_gsp_frame(int(GspType.ACK), bytes((3, 0, 0)))
    air = build_gsp_frame(int(GspType.AIR_RX), bytes((186, 20, 1, 0xA5)))
    chunks = iter((status, ack, air))
    ticks = iter((0.0, 0.1, 0.2, 0.3, 1.1))

    class FakeSerial:
        def __init__(self, *, port: str, baudrate: int, timeout: float) -> None:
            assert (port, baudrate, timeout) == ("COM-test", 230400, 0.1)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, size: int) -> bytes:
            assert size == 128
            return next(chunks)

    monkeypatch.setattr(capture.serial, "Serial", FakeSerial)
    monkeypatch.setattr(capture.time, "monotonic", lambda: next(ticks))
    result = capture.GroundCapture_Run("COM-test", 230400, 1)
    assert result["status_count"] == 1
    assert result["ack_count"] == 1
    assert result["air_rx_count"] == 1
    assert result["air_rx_last"] == {
        "length": 1, "rssi_dbm": -70, "snr_db": 5.0,
    }
    assert result["parser"]["crc_errors"] == 0


def test_ground_capture_output_is_limited_to_ignored_evidence() -> None:
    with pytest.raises(ValueError, match=r"\.work/round5"):
        capture.GroundCapture_ValidateOutputPath(
            capture.REPOSITORY_ROOT / "docs/capture.json"
        )
    allowed = capture.REPOSITORY_ROOT / ".work/round5/capture.json"
    assert capture.GroundCapture_ValidateOutputPath(allowed) == allowed.resolve()
