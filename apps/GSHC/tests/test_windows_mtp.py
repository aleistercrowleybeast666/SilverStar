"""Synthetic files and injected Shell bridge; no phone or device access."""
import json
from pathlib import Path
import shutil
from threading import Event

import pytest

from services.device_export import DeviceExport
from services.windows_mtp import WindowsMtp, MtpReply, MtpOperationResult, MtpDestination_Validate

DESTINATION = '::{20D04FE0-3AEA-1069-A2D8-08002B30309D}\\\\?\\usb#SYNTHETIC#{6AC27878-A6FA-4155-BA85-F98F491D4F33}\\Storage'


def package(tmp_path):
    managed = tmp_path / 'managed'
    staging = tmp_path / 'staging'
    managed.mkdir()
    staging.mkdir()
    source = managed / 'fc_session_synthetic.jsonl'
    source.write_bytes(b'{"synthetic":true}\n')
    exporter = DeviceExport([source], staging, managed_root=managed, is_active=lambda _: False)
    return source, exporter.copy()


def test_mtp_roundtrip_verifies_each_file_and_keeps_source(tmp_path):
    source, output = package(tmp_path)
    requests = []
    def bridge(request, cancel):
        requests.append(request)
        assert request['operation'] == 'copy'
        for row in request['files']:
            shutil.copyfile(Path(request['package']) / row['name'], Path(request['readback']) / row['name'])
        return MtpReply(MtpOperationResult.Verified)
    reply = WindowsMtp(bridge).copy(output, DESTINATION, Event())
    assert reply.result is MtpOperationResult.Verified
    assert source.read_bytes() == b'{"synthetic":true}\n'
    assert len(requests) == 1 and len(requests[0]['files']) == 2
    assert not any('delete' in key or 'move' in key for key in requests[0])


def test_helper_claim_cannot_replace_local_readback_verification(tmp_path):
    source, output = package(tmp_path)
    reply = WindowsMtp(lambda *_: MtpReply(MtpOperationResult.Verified)).copy(output, DESTINATION, Event())
    assert reply.result is MtpOperationResult.Failed and 'readback' in reply.detail
    assert source.exists()
    receipt=json.loads((output/'mtp_result.json').read_text(encoding='utf-8'))
    assert receipt['result']=='failed' and receipt['helper_result']=='verified'


@pytest.mark.parametrize('destination', ['C:/phone', 'mtp://guess', '::{20D04FE0-3AEA-1069-A2D8-08002B30309D}\\archive.zip'])
def test_only_explicit_wpd_namespace_is_accepted(destination):
    with pytest.raises(ValueError):
        MtpDestination_Validate(destination)


def test_changed_staging_source_rejected_before_bridge(tmp_path):
    source, output = package(tmp_path)
    (output / source.name).write_bytes(b'changed')
    calls = []
    reply = WindowsMtp(lambda *a: calls.append(a)).copy(output, DESTINATION, Event())
    assert reply.result is MtpOperationResult.Failed and not calls and source.exists()


def test_manifest_traversal_rejected_before_bridge(tmp_path):
    source, output = package(tmp_path)
    path = output / 'manifest.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value['files'][0]['path'] = '../source.jsonl'
    path.write_text(json.dumps(value), encoding='utf-8')
    calls = []
    reply = WindowsMtp(lambda *a: calls.append(a)).copy(output, DESTINATION, Event())
    assert reply.result is MtpOperationResult.Failed and not calls and source.exists()


def test_cancel_and_uncertain_completion_never_claim_success(tmp_path):
    source, output = package(tmp_path)
    cancel = Event()
    cancel.set()
    reply = WindowsMtp(lambda *_: pytest.fail('cancelled work must not start')).copy(output, DESTINATION, cancel)
    assert reply.result is MtpOperationResult.Cancelled and source.exists()
    cancel.clear()
    reply = WindowsMtp(lambda *_: MtpReply(MtpOperationResult.Uncertain, 'submitted copy may continue')).copy(output, DESTINATION, cancel)
    assert reply.result is MtpOperationResult.Uncertain and source.exists()
    evidence=json.loads((output/'mtp_result.json').read_text(encoding='utf-8'))
    assert evidence['result']=='uncertain' and evidence['source_files_retained'] is True


def test_choose_cancel_and_wrong_namespace():
    assert WindowsMtp(lambda *_: MtpReply(MtpOperationResult.Cancelled)).choose('phone', Event()).result is MtpOperationResult.Cancelled
    assert WindowsMtp(lambda *_: MtpReply(MtpOperationResult.Selected, destination='C:/')).choose('phone', Event()).result is MtpOperationResult.Failed


def test_failure_preserves_structured_exception_chain(tmp_path):
    source, output = package(tmp_path)
    evidence={'stage':'validate_destination','resolution':[{'method':'namespace','result':'null'}],
              'exceptions':[{'type':'System.Exception','hresult':'0x80131500'},
                            {'type':'System.Runtime.InteropServices.COMException','hresult':'0x80004005'}]}
    reply=WindowsMtp(lambda *_:MtpReply(MtpOperationResult.Failed,'resolve failed',diagnostics=evidence)).copy(output,DESTINATION,Event())
    receipt=json.loads((output/'mtp_result.json').read_text(encoding='utf-8'))
    assert reply.diagnostics==evidence and receipt['diagnostics']==evidence
    assert receipt['result']=='failed' and source.exists()
