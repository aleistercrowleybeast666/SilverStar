from pathlib import Path
from types import SimpleNamespace
import hashlib
import pytest
from silverstar_fccg.generator.native_usb_config import NativeUsbConfig_FilesRender
from silverstar_fccg.hardware.native_classic_cdc import NativeClassicCdc_Inspect
from test_native_classic_cdc import native
from test_native_derivatives import _Replay


def test_explicit_usb_options_preserve_original_and_patch_replay(tmp_path):
    root,args=native.__wrapped__(SimpleNamespace(param='f407-usb'),tmp_path)
    proof,_inventory,files=NativeClassicCdc_Inspect(root,**args)
    before={path:hashlib.sha256(value).hexdigest() for path,value in files.items()}
    rendered,include,manifest=NativeUsbConfig_FilesRender(files,proof['cdc']['owners'])
    original_path=manifest['original'].removeprefix('HardwareGenerated/NativeClassicCdc/')
    original=files[original_path]
    assert include=='HardwareGenerated/ReviewedNativeConfig/USB_DEVICE/Target'
    assert manifest['explicit_options']=={'USBD_CLASS_BOS_ENABLED':0,'USBD_USER_REGISTER_CALLBACK':0}
    _Replay(tmp_path,manifest['original'],original,rendered[manifest['derived']],rendered[manifest['patch']])
    assert before=={path:hashlib.sha256(value).hexdigest() for path,value in files.items()}
    changed={**files,original_path:original+b'\n#define USBD_USER_REGISTER_CALLBACK 1U\n'}
    with pytest.raises(ValueError):NativeUsbConfig_FilesRender(changed,proof['cdc']['owners'])
