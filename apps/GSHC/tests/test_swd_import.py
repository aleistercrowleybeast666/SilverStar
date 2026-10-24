"""Offline automatic target provenance; no probe enumeration or access."""
import json
from threading import Event

import pytest
from services.swd_import import Firmware_ImportAuto
from test_swd_firmware import arm_elf as diagnostic_elf_fixture
from test_swd_firmware import load
from transport.swd_firmware import DiagnosticResult as R

arm_elf=diagnostic_elf_fixture


def test_bare_elf_requires_descriptor_bound_provenance(arm_elf):
    reply=Firmware_ImportAuto([arm_elf])
    assert reply.result==R.Unsupported and reply.firmware is None
    firmware=load(arm_elf)
    reply=Firmware_ImportAuto([arm_elf],target_cache={firmware.sha256:firmware.target.name})
    assert reply.result==R.Ok and reply.firmware.sha256==firmware.sha256
    assert Firmware_ImportAuto([arm_elf],target_cache={'0'*64:firmware.target.name}).result==R.Unsupported


def test_adjacent_descriptor_binds_target_and_ambiguous_pair_is_rejected(arm_elf,tmp_path):
    elf=tmp_path/'fixture.elf'
    elf.write_bytes(arm_elf.read_bytes())
    descriptor=elf.with_suffix('.ssdiag')
    descriptor.write_text(json.dumps(load(arm_elf).descriptor),encoding='utf-8')
    reply=Firmware_ImportAuto([elf])
    assert reply.result==R.Ok and reply.firmware.provenance=='build_bound'
    second=elf.with_name(elf.name+'.ssdiag')
    second.write_bytes(descriptor.read_bytes())
    assert Firmware_ImportAuto([elf]).result==R.InvalidFile
    assert Firmware_ImportAuto([descriptor,elf]).result==R.Ok


@pytest.mark.parametrize('cache',[[],True,{'bad':'STM32F407VET6'},{'0'*64:True},{str(i).zfill(64):'STM32F407VET6' for i in range(9)}])
def test_invalid_target_cache_returns_a_bounded_error(arm_elf,cache):
    reply=Firmware_ImportAuto([arm_elf],target_cache=cache)
    assert reply.result==R.InvalidFile and reply.firmware is None


def test_cancel_precedes_any_file_access(tmp_path):
    cancel=Event();cancel.set()
    assert Firmware_ImportAuto([tmp_path/'absent.elf'],cancel=cancel).result==R.Cancelled


def test_changed_file_cannot_reuse_an_exact_hash_target(arm_elf,monkeypatch):
    from dataclasses import replace

    import services.swd_import as module
    from transport.swd_firmware import FirmwareReply
    firmware=load(arm_elf)
    monkeypatch.setattr(module,'Firmware_Import',lambda *args,**kwargs:
        FirmwareReply(R.Ok,firmware=replace(firmware,sha256='0'*64)))
    reply=Firmware_ImportAuto([arm_elf],target_cache={firmware.sha256:firmware.target.name})
    assert reply.result==R.InvalidFile and reply.firmware is None
