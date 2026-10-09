"""Profile admission and patch replay; no EP0 behavior/review is exercised."""
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
import difflib
import os
import shutil
import subprocess
import pytest
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.generator.native_usb_data import NativeUsbBulk_FilesRender, NativeUsbData_Derive, NativeUsbCore_Derive, NativeUsbLl_Derive
from silverstar_fccg.generator.native_radio import NativeRadioHal_Derive, NativeRadioDevice_Derive
from silverstar_fccg.generator.native_ground import NativeGroundCandidate_Render
from silverstar_fccg.hardware.native_classic_cdc import NativeClassicCdc_Inspect
from silverstar_fccg.plugins.catalog import PluginCatalog
from test_native_classic_cdc import native
from test_round2_targets import _GroundBoardProject_Get


@pytest.fixture
def ground_native(tmp_path):
    return native.__wrapped__(SimpleNamespace(param='f103-usb'), tmp_path)


def _Replay(tmp_path, path, original, derived, patch):
    git = shutil.which('git')
    if git is None: pytest.fail('Git required for exact patch replay')
    dest = tmp_path/path; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(original)
    run = subprocess.run([git,'-c','core.autocrlf=false','-c','core.eol=lf',
        'apply','--no-index','-p0','-'],input=patch,cwd=tmp_path,capture_output=True,timeout=30)
    assert run.returncode == 0, run.stdout.decode(errors='replace')+run.stderr.decode(errors='replace')
    assert dest.read_bytes() == derived


def test_native_usb_profiles_patch_replay_and_ep0_identity(ground_native, tmp_path):
    root,args = ground_native
    proof,_inventory,files = NativeClassicCdc_Inspect(root,**args)
    rendered,_replacements,manifest = NativeUsbBulk_FilesRender(files,proof['cdc']['owners'])
    for entry in manifest['entries']:
        original = files[entry['original'].removeprefix('HardwareGenerated/NativeClassicCdc/')]
        _Replay(tmp_path,entry['original'],original,rendered[entry['derived']],rendered[entry['patch']])
    original = files[proof['cdc']['owners']['usbd_cdc.c']].decode('utf-8-sig')
    derived = NativeUsbData_Derive(original.encode()).decode()
    for name in ('USBD_CDC_Setup','USBD_CDC_EP0_RxReady'):
        a,_o,b = NativeC_FunctionSpanGet(original,name)
        c,_o,d = NativeC_FunctionSpanGet(derived,name)
        assert original[a:b] == derived[c:d]


@pytest.mark.parametrize('kind',['class','core','ll','radio-hal','radio-device'])
def test_unknown_runtime_derivative_source_profile_rejected(kind):
    origin = os.environ.get('SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT')
    if not origin: pytest.skip('Native input fixture unavailable')
    scg = Path(__file__).resolve().parents[1]
    vendor = Path(origin)/'cube-f103-usb'
    radio = scg/'plugins/builtin/silverstar_device_telemetry_sx1281/payload'
    path,derive = {
        'class':(vendor/'Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c',NativeUsbData_Derive),
        'core':(vendor/'Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_core.c',NativeUsbCore_Derive),
        'll':(vendor/'USB_DEVICE/Target/usbd_conf.c',NativeUsbLl_Derive),
        'radio-hal':(radio/'Middlewares/Third_Party/SX1280lib/sx1280-hal.c',NativeRadioHal_Derive),
        'radio-device':(radio/'Devices/Telemetry/SX1281/Src/sx1281_device.c',NativeRadioDevice_Derive),
    }[kind]
    original = path.read_bytes()
    with pytest.raises(ValueError): derive(original+b'\n/* unreviewed */\n')


@pytest.mark.parametrize('kind',['hal','device'])
def test_radio_same_path_patch_reproduces_owned_derivative(tmp_path,kind):
    root = Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_device_telemetry_sx1281/payload'
    path,derive = ('Middlewares/Third_Party/SX1280lib/sx1280-hal.c',NativeRadioHal_Derive) if kind=='hal' else (
        'Devices/Telemetry/SX1281/Src/sx1281_device.c',NativeRadioDevice_Derive)
    original = (root/path).read_bytes(); derived = derive(original)
    patch = ''.join(difflib.unified_diff(original.decode().splitlines(keepends=True),
        derived.decode().splitlines(keepends=True),fromfile=path,tofile=path)).encode()
    _Replay(tmp_path,path,original,derived,patch)


@pytest.mark.parametrize('mutation',['normal','gpio-missing','gpio-after-owner','spi-after-owner','gpio-duplicate'])
def test_native_main_gpio_spi_order_is_required_before_runtime(ground_native,mutation):
    root,args = ground_native
    proof,inventory,files = NativeClassicCdc_Inspect(root,**args)
    path = proof['cdc']['owners']['main.c']
    if mutation == 'gpio-missing': files[path] = files[path].replace(b'  MX_GPIO_Init();',b'')
    elif mutation == 'gpio-after-owner':
        files[path] = files[path].replace(b'  MX_GPIO_Init();',b'').replace(
            b'/* USER CODE BEGIN 2 */',b'/* USER CODE BEGIN 2 */\n  MX_GPIO_Init();')
    elif mutation == 'spi-after-owner':
        files[path] = files[path].replace(b'  MX_SPI1_Init();',b'').replace(
            b'/* USER CODE BEGIN 2 */',b'/* USER CODE BEGIN 2 */\n  MX_SPI1_Init();')
    elif mutation == 'gpio-duplicate':
        files[path] = files[path].replace(b'  MX_GPIO_Init();',b'  MX_GPIO_Init();\n  MX_GPIO_Init();')
    scg = Path(__file__).resolve().parents[1]
    catalog = PluginCatalog(scg/'plugins/builtin',scg/'plugins/installed'); catalog.Scan()
    model = _GroundBoardProject_Get(catalog)
    model.ground_target = replace(model.ground_target,pc_interface='usb_cdc',activity_led_enabled=False,
        tx_led_resource='',rx_led_resource='')
    model.air_link = replace(model.air_link,radio_family='sx128x')
    if mutation == 'normal':
        rendered,_graph,_contract = NativeGroundCandidate_Render(files,proof,inventory,model,catalog,hclk_hz=72000000)
        assert b'NativePlatform_Quiesce();' in rendered['Generated/Src/native_runtime.c']
    else:
        with pytest.raises(ValueError,match='GPIO and SPI initialization'):
            NativeGroundCandidate_Render(files,proof,inventory,model,catalog,hclk_hz=72000000)
