from threading import Event
from types import SimpleNamespace

from PySide6.QtCore import QObject

from services.magnetometer_maintenance import MagMaintenanceDecoder
from services.maintenance_commands import ConsoleCommand_ResponsePrefix
from transport.file_service_backend import FileServiceSerialTransport
from transport.magnetometer_transport import MaintenanceMagTransport
from ui.file_transfer import MaintenanceOwner


SAMPLE = b"EVENT MAG SAMPLE instance=3 physical_device_id=42 seq=7 sample_us=123 x_uT=25.5 y_uT=-18.2 z_uT=42.0\r\n"


class ByteSerial:
    def __init__(self, **_):
        self.chunks = []
        self.commands = []
        self.closed = False

    def write(self, payload):
        command = payload.decode().strip()
        self.commands.append(command)
        # Wrong-instance output must not become this transaction's completion.
        self.chunks += [SAMPLE[:30], SAMPLE[30:], b"OK MAG 8 STREAM state=STARTED rate_hz=20\r\n",
                        b"OK MAG 3 STREAM state=STARTED rate_hz=20\r\n"]
        return len(payload)

    def read(self, _):
        return self.chunks.pop(0) if self.chunks else b""

    def close(self):
        self.closed = True


def test_mag_action_response_prefix_matches_protocol_without_losing_instance():
    assert ConsoleCommand_ResponsePrefix("MAG 3 STREAM START") == "MAG 3 STREAM"
    assert ConsoleCommand_ResponsePrefix("MAG 3 STREAM STOP") == "MAG 3 STREAM"
    assert ConsoleCommand_ResponsePrefix("MAG 3 CAL APPLY ABCD") == "MAG 3 CAL"
    assert ConsoleCommand_ResponsePrefix("MAG 3 CAL READ") == "MAG 3 CAL"
    assert ConsoleCommand_ResponsePrefix("MAG 3 INFO") == "MAG 3 INFO"
    assert ConsoleCommand_ResponsePrefix("IMU 0 CONFIG READ") == "IMU 0 CONFIG READ"


def test_shared_serial_observer_sees_fragmented_events_during_exchange_and_idle():
    serial = ByteSerial()
    transport = FileServiceSerialTransport("FAKE", 230400, serial_factory=lambda **_: serial)
    # This unit tests the established synchronized connection, not startup probing.
    transport._needs_sync = False
    decoder = MagMaintenanceDecoder()
    samples = []
    transport.receive_observer = lambda data: samples.extend(decoder.feed(data))
    reply = transport.exchange("MAG 3 STREAM START", .5, Event())
    assert reply == "OK MAG 3 STREAM state=STARTED rate_hz=20"
    assert len(samples) == 1 and samples[0].physical_device_id == 42
    serial.chunks += [SAMPLE[:31], SAMPLE[31:]]
    transport.check_alive()
    transport.check_alive()
    assert len(samples) == 2
    transport.close()
    assert serial.closed


def test_owner_bounds_sample_mailbox_and_rejects_file_jobs_while_stream_possible():
    owner = MaintenanceOwner("FAKE", 230400)
    owner.mag_subscribe(True)
    for index in range(600):
        owner._mag_capture(SAMPLE.replace(b"seq=7", f"seq={index}".encode()))
    samples, dropped = owner.mag_take()
    assert len(samples) == 256 and dropped == 344
    assert owner.mag_take()[0] == ()
    owner.mag_subscribe(False)
    owner._mag_capture(SAMPLE)
    assert owner.mag_take()[0] == ()
    owner.connected.set()
    owner.mag_stream_instance = 3
    assert not owner.submit(None, list_only=True)
    assert owner.submit_command("SYSTEM INFO")


def test_session_end_retains_lease_until_owner_job_handoff():
    class Manager(QObject):
        def __init__(self):
            super().__init__()
            self.owner = SimpleNamespace(connected=Event(), stop=Event(),
                mag_take=lambda: ((), 0), mag_subscribe=lambda _: None)
            self.owner.connected.set()
            self.job_busy = True
            self.worker = None
            self.releases = 0

        def mag_release(self):
            self.releases += 1

    manager = Manager()
    transport = MaintenanceMagTransport(manager)
    transport.owner = manager.owner
    transport.ending = True
    ended = []
    transport.ended.connect(lambda *args: ended.append(args))
    transport.pump()
    assert transport.session_active and not ended and manager.releases == 0
    manager.job_busy = False
    transport.pump()
    assert not transport.session_active and ended == [(True, "")] and manager.releases == 1
