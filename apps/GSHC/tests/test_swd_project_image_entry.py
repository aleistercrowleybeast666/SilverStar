"""Root v2 binding uses real synthetic ARM artifacts, without live hardware."""
import json
import shutil
import pytest
from test_swd_image_contract import image, TARGET
from silverstar_diagnostics.project_descriptor import (
    ProjectDescriptor_Create, ProjectDescriptor_Bind, ProjectDescriptor_Begin,
    ProjectBindingResult, ProjectDescriptor_Validate)
from silverstar_diagnostics.contract import DiagnosticError
from services.swd_import import Firmware_ImportAuto
from transport.swd_firmware import DiagnosticResult


def entry(image):
    path=image.parent/'Flight.ssdiag'
    path.write_text(json.dumps(ProjectDescriptor_Create('Synthetic',TARGET)))
    assert ProjectDescriptor_Bind(path,image,image_file=image.with_suffix('.hex').name)[0]==ProjectBindingResult.Ready
    return path


def test_root_v2_import_preserves_exact_image_and_metadata(image):
    path=entry(image)
    reply=Firmware_ImportAuto([path])
    assert reply.result==DiagnosticResult.Ok,reply.detail
    assert reply.firmware.descriptor['version']==2
    assert reply.firmware.image_identity['erased_gaps']
    assert reply.firmware.provenance=='build_bound'
    value=json.loads(path.read_text())
    assert value['schema']['version']==1 and value['schema']['binding'] is None
    assert ProjectDescriptor_Validate(value)==value


@pytest.mark.parametrize('kind',['elf','hex','missing_hex','target','image_path','hash'])
def test_root_v2_rejects_changed_or_unsafe_pair(image,kind):
    path=entry(image);value=json.loads(path.read_text())
    descriptor=value['builds']['.']['descriptor']
    if kind in ('elf','hex'):
        changed=image if kind=='elf' else image.with_suffix('.hex')
        data=bytearray(changed.read_bytes());data[-2]^=1;changed.write_bytes(data)
    elif kind=='missing_hex':image.with_suffix('.hex').rename(image.with_suffix('.saved_hex'))
    else:
        if kind=='target':descriptor['target']='STM32F103C8Tx'
        elif kind=='image_path':descriptor['image']['file']='../other.hex'
        else:descriptor['binding']['sha256']='0'*64
        path.write_text(json.dumps(value))
    result=Firmware_ImportAuto([path])
    assert result.result!=DiagnosticResult.Ok and result.firmware is None


def test_root_v2_failed_refresh_invalidates_previous_success(image):
    path=entry(image)
    ProjectDescriptor_Begin(path)
    assert Firmware_ImportAuto([path]).result!=DiagnosticResult.Ok
    image.with_suffix('.hex').write_text(':bad')
    assert ProjectDescriptor_Bind(path,image,image_file=image.with_suffix('.hex').name)[0]==ProjectBindingResult.Unavailable
    assert Firmware_ImportAuto([path]).firmware is None


def test_mixed_outputs_still_require_explicit_selection(image):
    path=entry(image)
    debug=image.parent/'Debug'/image.name;debug.parent.mkdir()
    shutil.copyfile(image,debug)
    assert ProjectDescriptor_Bind(path,debug)[0]==ProjectBindingResult.Ready
    assert 'Multiple' in Firmware_ImportAuto([path]).detail
    assert Firmware_ImportAuto([path,image]).firmware.descriptor['version']==2
    assert Firmware_ImportAuto([path,debug]).firmware.descriptor['version']==1
