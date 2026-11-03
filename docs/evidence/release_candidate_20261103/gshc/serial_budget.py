"""Host byte and timing observations for three independent serial workflows."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT/'apps/GSHC'), str(ROOT/'apps/GSHC/tests'), str(ROOT/'apps/SCG/src')]
from config import DEFAULT_BAUDRATE, PROTOCOL_INPUT_QUEUE_MAX_CHUNKS
from protocol.receive_pipeline import ReceivePipeline
from transport.serial_backend import SerialConfig
from services.magnetometer_maintenance import MagMaintenanceDecoder, MAG_MAINTENANCE_MAX_LINE_BYTES
from services.file_service_client import FileServiceClient
from services.file_service_block import BLOCK_SIZE, WIRE_LIMIT
from services.maintenance_serial_profile import MaintenanceSerial_Timeout
from test_receive_pipeline import air_rx_gsp
from test_tm_receive_order import data
from test_ss_tm import cap
from test_file_service_block import BlockTransport


class CountedBlocks(BlockTransport):
    """An in-memory firmware peer. Client parsing, CRC, publication and readback are real."""
    def __init__(self, payload):
        super().__init__(payload)
        self.wire_bytes = 0

    def exchange(self, command, timeout, cancel):
        reply = super().exchange(command, timeout, cancel)
        self.wire_bytes += len(command.encode('ascii')) + len(reply.encode('ascii')) + 4
        return reply

    def block_poll(self, rid, timeout, cancel):
        frame = super().block_poll(rid, timeout, cancel)
        self.wire_bytes += len(f'LOGFILE POLL {rid}\r\n'.encode()) + len(frame) + 2
        return frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('new_output', type=Path)
    destination = parser.parse_args().new_output
    destination.mkdir(parents=True, exist_ok=False)
    config = SerialConfig('SIMULATED', DEFAULT_BAUDRATE)
    pipeline = ReceivePipeline()
    frames = [air_rx_gsp(data(i+1, stamp=(i+1)*200)) for i in range(1024)]
    wire = air_rx_gsp(cap(0)) + b''.join(frames)
    started = time.perf_counter()
    decoded = []
    for off in range(0, len(wire), config.read_chunk_size):
        decoded.extend(pipeline.feed(wire[off:off+config.read_chunk_size]))
    seconds = time.perf_counter() - started
    assert len(decoded) == 1025 and all(row.telemetry_result.value == 'accepted' for row in decoded)
    telemetry = dict(frames=len(frames), wire_frame_bytes=len(frames[0]), example_rate_hz=5,
                     stream_bytes_per_second=5*len(frames[0]), host_parse_seconds=seconds,
                     baud_8n1=config.baudrate, read_chunk=config.read_chunk_size,
                     read_timeout_s=config.timeout_s, input_queue_chunks=PROTOCOL_INPUT_QUEUE_MAX_CHUNKS)
    rows = [('EVENT MAG SAMPLE instance=3 physical_device_id=42 seq=%d sample_us=%d '
             'x_uT=-123.4567 y_uT=45.6789 z_uT=50.1234\r\n' % (i, 2000000+i*50000)).encode()
            for i in range(1200)]
    raw = b''.join(rows)
    reader = MagMaintenanceDecoder()
    started = time.perf_counter()
    samples = []
    for off in range(0, len(raw), 73):
        samples.extend(reader.feed(raw[off:off+73]))
    assert len(samples) == len(rows) and reader.discarded_lines == 0
    mag = dict(samples=len(samples), sample_hz=20, actual_bytes=len(raw),
               max_line_including_crlf=max(map(len,rows)), line_capacity=MAG_MAINTENANCE_MAX_LINE_BYTES,
               stream_bytes_per_second=len(raw)/60, host_parse_seconds=time.perf_counter()-started)
    payload = bytes(range(256))*4096 + b'last'
    peer = CountedBlocks(payload)
    started = time.perf_counter()
    saved = FileServiceClient(peer).download(1,destination)
    seconds = time.perf_counter()-started
    assert saved.read_bytes() == payload and len(peer.completions) == (len(payload)+BLOCK_SIZE-1)//BLOCK_SIZE
    transfer = dict(payload_bytes=len(payload), block_payload=BLOCK_SIZE, maximum_delimited_frame=WIRE_LIMIT,
                    verified_blocks=len(peer.completions), whole_sha256=hashlib.sha256(payload).hexdigest(),
                    counted_wire_bytes=peer.wire_bytes, ideal_sequential_wire_seconds_8n1=peer.wire_bytes*10/config.baudrate,
                    configured_timeout_s=MaintenanceSerial_Timeout(config.baudrate,2),
                    host_mock_download_seconds=seconds)
    report = {'scope':'Synthetic Host streams and file-service peer. No COM port opened. Wire time excludes scheduling and device/storage latency.',
              'telemetry':telemetry,'maintenance_mag':mag,'log_export':transfer}
    (destination/'serial-budget.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
