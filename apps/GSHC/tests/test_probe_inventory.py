"""Host-only probe identity, lifecycle and bounded helper failures."""
from threading import Event
from unittest.mock import MagicMock, patch

import pytest
from transport import probe_inventory as inventory
from transport.probe_inventory import ProbeInventory, ProbeInventoryResult as Result, ProbeSelection


def nodes(serial='ABC', name='CMSIS-DAP v2'):
    root = 'USB\\VID_1234&PID_5678\\' + serial
    child = 'USB\\VID_1234&PID_5678&MI_00\\' + serial + '&0'
    return [dict(id=root, name='USB Composite Device', status='OK'),
            dict(id=child, name=name, parent=root, service='WINUSB', status='OK'),
            dict(id='HID\\VID_1234&PID_5678&MI_00\\'+serial, description='CMSIS-DAP',
                 parent=child, service='HidUsb', status='OK'),
            dict(id='USB\\VID_1234&PID_5678&MI_02\\'+serial, name='DAPLink COM9',
                 parent=root, **{'class': 'Ports'}, service='usbser', status='OK')]


def parsed(records):
    return inventory.ProbeInventory_Parse(dict(state='ready', nodes=records))


def test_composite_is_one_probe_and_uart_is_independent():
    result = parsed(nodes() + [dict(id='USB\\VID_1111&PID_2222\\UART', name='USB UART', **{'class':'Ports'})])
    assert result.result == Result.Ready and len(result.probes) == 1
    probe = result.probes[0]
    assert probe.serial == 'ABC' and probe.usb_id == '1234:5678'
    assert probe.identity == 'USB\\VID_1234&PID_5678\\ABC'
    assert probe.identity_kind == 'USB serial'
    assert len(probe.interfaces) == 2
    assert not any('COM9' in i or 'usbser' in i for i in probe.interfaces)


@pytest.mark.parametrize('name,family', [('ST-LINK/V2','ST-Link'), ('J-Link','J-Link'), ('DAPLink','CMSIS-DAP')])
def test_family_is_only_a_host_descriptor_candidate(name, family):
    result = parsed([dict(id='USB\\VID_1111&PID_2222\\S',name=name,status='Error')])
    assert result.probes[0].family == family
    assert result.probes[0].host_status == 'Error'


def test_location_identity_is_not_advertised_as_serial():
    assert parsed(nodes('5&LOCATION&0&1')).probes[0].identity_kind == 'USB instance/location'


def test_empty_and_vcp_only_do_not_imply_probe():
    assert parsed([]).result == Result.Empty
    assert parsed([nodes()[-1]]).result == Result.Empty


def test_incomplete_composite_parent_requires_retry():
    with pytest.raises(ValueError, match='Incomplete probe parent'):
        parsed([nodes()[1]])


@pytest.mark.parametrize('document', [None, {}, {'state':'ready','nodes':{}},
    {'state':'ready','nodes':[{}]}, {'state':'ready','nodes':[{'id':'X'}]*513},
    {'state':'ready','nodes':[{'id':'x'},{'id':'X'}]},
    {'state':'ready','nodes':[{'id':'X','name':'bad\ntext'}]},
    {'state':'ready','nodes':[{'id':'X','name':'x'*513}]}])
def test_invalid_inventory_rejected(document):
    with pytest.raises(ValueError):
        inventory.ProbeInventory_Parse(document)


def test_parent_cycle_and_probe_limit_fail_closed():
    with pytest.raises(ValueError, match='Cyclic'):
        parsed([dict(id='HID\\VID_1234&PID_5678\\X',name='CMSIS-DAP',parent='HID\\VID_1234&PID_5678\\X')])
    with pytest.raises(ValueError, match='32-probe'):
        parsed([dict(id=f'USB\\VID_1234&PID_5678\\{i}',name='CMSIS-DAP') for i in range(33)])


def test_selection_single_multi_reorder_unplug_replug_and_replacement():
    first, second = parsed(nodes('A')), parsed(nodes('B'))
    both = parsed(nodes('A')+nodes('B'))
    selection = ProbeSelection()
    selection.apply(both)
    assert selection.identity == ''  # Never pick arbitrarily from multiple probes.
    assert not selection.select('unknown')
    assert selection.select(first.probes[0].identity)
    selection.apply(parsed(list(reversed(nodes('A')+nodes('B')))))
    assert selection.identity == first.probes[0].identity
    assert selection.apply(second)  # Removed A must not silently select B.
    assert selection.identity == ''
    selection.apply(first)
    assert selection.identity == ''  # Replug needs explicit choice after loss.
    assert selection.select(first.probes[0].identity)
    assert selection.apply(ProbeInventory(Result.Failed))
    assert selection.identity == ''
    fresh = ProbeSelection()
    fresh.apply(parsed([]))
    fresh.apply(first)
    assert fresh.identity == first.probes[0].identity


def test_missing_dependency_and_precancel_never_spawn():
    with patch.object(inventory.shutil, 'which', return_value=None), patch.object(inventory.subprocess,'Popen') as spawn:
        assert inventory.ProbeInventory_Read(Event()).result == Result.MissingDependency
        cancelled = Event(); cancelled.set()
        assert inventory.ProbeInventory_Read(cancelled).result == Result.Cancelled
        spawn.assert_not_called()


@pytest.mark.parametrize('stdout,code,expected', [
    (b'{"state":"ready","nodes":[]}',0,Result.Empty),
    (b'{"state":"missing_dependency","detail":"missing CIM"}',0,Result.MissingDependency),
    (b'{"state":"failed","detail":"query failed"}',0,Result.Failed),
    (b'invalid',0,Result.Failed),(b'',1,Result.Failed),(b' '*1048577,0,Result.Failed)],
    ids=['empty','missing','failed','invalid_json','exit_error','oversized'])
def test_helper_outcomes_and_fixed_readonly_command(stdout, code, expected):
    process = MagicMock(returncode=code)
    process.communicate.return_value = stdout, b''
    process.poll.return_value = code
    with patch.object(inventory.sys,'platform','win32'), patch.object(inventory.shutil,'which',return_value='powershell.exe'), \
         patch.object(inventory.subprocess,'Popen',return_value=process) as spawn:
        assert inventory.ProbeInventory_Read(Event()).result == expected
    assert spawn.call_args.args[0][1:4] == ['-NoProfile','-NonInteractive','-ExecutionPolicy']
    assert 'GetDeviceProperties' in inventory._PNP_SCRIPT
    assert 'Present = TRUE' in inventory._PNP_SCRIPT
    assert all(word not in inventory._PNP_SCRIPT for word in ['-MethodName Reset','-MethodName Disable','-MethodName Enable'])
    process.kill.assert_not_called()


@pytest.mark.parametrize('cancelled', [False, True])
def test_timeout_or_cancel_only_terminates_owned_helper(cancelled):
    event = Event()
    process = MagicMock()
    process.poll.return_value = 0
    def spawn(*args, **kwargs):
        if cancelled: event.set()
        return process
    with patch.object(inventory.sys,'platform','win32'), patch.object(inventory.shutil,'which',return_value='powershell.exe'), \
         patch.object(inventory.subprocess,'Popen',side_effect=spawn):
        result = inventory.ProbeInventory_Read(event,timeout=0)
    assert result.result == (Result.Cancelled if cancelled else Result.Failed)
    process.kill.assert_called_once()
    process.communicate.assert_called_once()
