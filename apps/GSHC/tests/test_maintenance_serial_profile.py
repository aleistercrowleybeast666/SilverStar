from types import SimpleNamespace

import pytest

from services.maintenance_serial_profile import MaintenanceSerial_Check, MaintenanceSerial_Timeout
from services.file_service_client import FileServiceClient, FileServiceError
from test_file_service_client import MockTransport


def expected(baud=230400):
    return dict(baudrate=baud, data_bits=8, parity='none', stop_bits=1, block_size=512,
                block_deadline_ms=30000, idle_timeout_ms=30000, minimum_wire_ms=(8210000+baud-1)//baud)


def caps(baud=230400):
    return dict(uart_baud=str(baud), uart_format='8N1', idle_timeout_ms='30000', max_block='512')


@pytest.mark.parametrize('baud', [1200, 230400, 460800, 921600, 1000000, 2000000])
def test_selected_expected_and_runtime_rates_agree(baud):
    MaintenanceSerial_Check(caps(baud), baud, expected(baud))
    timeout = MaintenanceSerial_Timeout(baud, 2)
    assert 2 <= timeout <= 30 and timeout >= 8210/baud + .25


@pytest.mark.parametrize('changes', [dict(uart_baud='921600'), dict(uart_format='7E1'),
    dict(idle_timeout_ms='100'), dict(uart_baud='nan'), dict(max_block='1024')])
def test_mismatch_does_not_become_an_accepted_capability(changes):
    value = caps()
    value.update(changes)
    with pytest.raises(ValueError):
        MaintenanceSerial_Check(value, 230400, expected())


def test_legacy_caps_require_no_new_uart_claim_unless_descriptor_expects_it():
    MaintenanceSerial_Check({}, 230400, None)
    with pytest.raises(ValueError, match='do not confirm'):
        MaintenanceSerial_Check({}, 230400, expected())
    with pytest.raises(ValueError, match='selected descriptor'):
        MaintenanceSerial_Check(caps(), 460800, expected())


def test_public_client_rejects_runtime_mismatch_before_any_file_request():
    class Wire(MockTransport):
        baudrate = 230400
        def exchange(self, command, timeout, cancel):
            result = super().exchange(command, timeout, cancel)
            if command == 'LOGFILE CAPS':
                result += ' uart_baud=460800 uart_format=8N1 idle_timeout_ms=30000'
            return result
    wire = Wire()
    client = FileServiceClient(wire)
    with pytest.raises(FileServiceError, match='differs'):
        client.negotiate()
    assert client.capabilities is None and wire.commands == ['LOGFILE CAPS']
