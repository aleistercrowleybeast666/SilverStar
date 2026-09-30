"""Passively capture bounded Ground UART/GSP diagnostics on a real board.

No bytes are transmitted. An explicit COM port is required; output stays in
the ignored Round 5 evidence workspace. This is observational evidence, not a
radio TX, command-path, or hardware-integration PASS by itself.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import serial

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GSHC_ROOT = REPOSITORY_ROOT / "apps" / "GSHC"
sys.path.insert(0, str(GSHC_ROOT))

def GroundCapture_ValidateOutputPath(output: Path) -> Path:
    target = output.resolve()
    evidence_root = (REPOSITORY_ROOT / ".work" / "round5").resolve()
    if not target.is_relative_to(evidence_root) or target == evidence_root:
        raise ValueError("Ground capture output must stay below .work/round5/")
    return target


def GroundCapture_Run(port: str, baudrate: int, duration_s: int) -> dict:
    from protocol.gsp_min import (
        GspAck,
        GspParser,
        GsStatus,
        GsToPcAirFrame,
        parse_gsp_frame,
    )

    if not port or baudrate <= 0 or not (1 <= duration_s <= 600):
        raise ValueError("Explicit port, positive baudrate and 1–600 seconds required")
    parser = GspParser()
    started_utc = datetime.now(UTC).isoformat()
    deadline = time.monotonic() + duration_s
    evidence: dict = {
        "port": port,
        "baudrate": baudrate,
        "duration_s": duration_s,
        "started_utc": started_utc,
        "received_bytes": 0,
        "status_count": 0,
        "status_first": None,
        "status_last": None,
        "ack_count": 0,
        "ack_last": None,
        "air_rx_count": 0,
        "air_rx_last": None,
        "unknown_or_malformed_frames": 0,
    }
    with serial.Serial(port=port, baudrate=baudrate, timeout=0.1) as connection:
        while time.monotonic() < deadline:
            data = connection.read(128)
            evidence["received_bytes"] += len(data)
            for frame in parser.feed(data):
                decoded = parse_gsp_frame(frame)
                if isinstance(decoded, GsStatus):
                    evidence["status_count"] += 1
                    if evidence["status_first"] is None:
                        evidence["status_first"] = asdict(decoded)
                    evidence["status_last"] = asdict(decoded)
                elif isinstance(decoded, GspAck):
                    evidence["ack_count"] += 1
                    evidence["ack_last"] = asdict(decoded)
                elif isinstance(decoded, GsToPcAirFrame):
                    evidence["air_rx_count"] += 1
                    evidence["air_rx_last"] = {
                        "length": len(decoded.air_frame),
                        "rssi_dbm": decoded.rssi_dbm,
                        "snr_db": decoded.snr_db,
                    }
                else:
                    evidence["unknown_or_malformed_frames"] += 1
    evidence["ended_utc"] = datetime.now(UTC).isoformat()
    evidence["parser"] = asdict(parser.diagnostics())
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Explicit Ground UART COM port")
    parser.add_argument("--baudrate", type=int, default=230400)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument(
        "--output", type=Path,
        default=REPOSITORY_ROOT / ".work/round5/ground-passive-capture.json",
    )
    args = parser.parse_args()
    output = GroundCapture_ValidateOutputPath(args.output)
    evidence = GroundCapture_Run(args.port, args.baudrate, args.seconds)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
