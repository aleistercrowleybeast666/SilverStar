from pathlib import Path
import hashlib,os,json,subprocess,shutil
import pytest
from silverstar_fccg.generator.native_usb_indexed import NativeUsbIndexedData_Derive,NativeUsbIndexedCore_Derive,NativeUsbIndexedLl_Derive
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from test_native_usb_data import _ExerciseNativeBulk
from test_native_derivatives import _Replay


@pytest.mark.parametrize('scenario',['normal','open1','open2','open3','app-init','prepare-init',
    'tx-fail','tx-busy','rearm','receive','zlp','close','null-rx','null-out','oversize','bad-ep','bad-class','mirror'])
def test_actual_indexed_bulk_pipeline_and_faults(tmp_path,scenario):
    _ExerciseNativeBulk(tmp_path,scenario,indexed=True)


def test_indexed_profiles_preserve_ep0_and_replay_actual_derivatives(tmp_path):
    reference=os.environ.get('SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT')
    if not reference:pytest.skip('Native input unavailable')
    root=Path(reference)/'cube-f407-usb'
    for path,derive in [('Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c',NativeUsbIndexedData_Derive),
        ('Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_core.c',NativeUsbIndexedCore_Derive),
        ('USB_DEVICE/Target/usbd_conf.c',NativeUsbIndexedLl_Derive)]:
        import difflib
        original=(root/path).read_bytes();derived=derive(original)
        patch=''.join(difflib.unified_diff(original.decode().splitlines(keepends=True),derived.decode().splitlines(keepends=True),fromfile=path,tofile=path)).encode()
        _Replay(tmp_path,path,original,derived,patch)
        with pytest.raises(ValueError):derive(original+b'\n/* unreviewed */\n')
        if path.endswith('/usbd_cdc.c'):
            for name in ('USBD_CDC_Setup','USBD_CDC_EP0_RxReady'):
                bodies=[]
                for content in (original,derived):
                    text=content.decode();a,_o,b=NativeC_FunctionSpanGet(text,name);bodies.append(text[a:b])
                assert bodies[0]==bodies[1]
