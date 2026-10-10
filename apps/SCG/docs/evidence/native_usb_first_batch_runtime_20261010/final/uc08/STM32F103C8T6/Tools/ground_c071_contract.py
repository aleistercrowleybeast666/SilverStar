"""Registered C071 mini contracts in the ordinary Ground gate chain."""

from pathlib import Path

import hashlib

import json

import re

import struct

import subprocess

import difflib

def C071_Active(graph):
    return 'STM32C071xx' in graph['defines'] or any(
        path.startswith('Platform/STM32C0/') for path in graph['sources'])

def _Profile_Get(root, graph, name, digest):
    path = root / 'Generated/C071' / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('C071 registration manifest changed: ' + name)
    return json.loads(path.read_text(encoding='utf8'))

def C071Architecture_Validate(root, graph):
    if (graph.get('registration_status') != 'registered' or
            graph.get('input_kind') != 'native_pcd_plus_pinned_classic_cdc' or
            graph.get('native_cdc') is not False or
            graph.get('native_project_complete') is not True or
            graph.get('complete_cube_import') is not False or
            graph.get('pc_interface') != 'usb_cdc' or
            graph['mcu_flags'] != ['-mcpu=cortex-m0plus', '-mthumb', '-mfloat-abi=soft']):
        raise ValueError('C071 registered native PCD/companion contract missing')
    provenance = graph['c071_companion']
    profile = _Profile_Get(root, graph, 'native-profile.json', provenance['native_profile_sha256'])
    companion = _Profile_Get(root, graph, 'companion-manifest.json', provenance['manifest_sha256'])
    native = 'HardwareGenerated/STM32CubeMX/'
    hashes = dict(profile['files_sha256'])
    hashes.update({'Makefile': profile['makefile_sha256'],
        'startup_stm32c071xx.s': profile['startup_sha256'],
        'STM32C071XX_FLASH.ld': profile['linker_sha256']})
    for prefix, expected in ((native, hashes), ('', companion['files_sha256'])):
        for relative, digest in expected.items():
            path = root / (prefix + relative)
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('C071 frozen source changed: ' + prefix + relative)
    sources = graph['sources']
    for patch in companion['vendor_patches']:
        original, derived = patch['original_path'], patch['derived_path']
        if original in sources or sources.count(derived) != 1:
            raise ValueError('C071 vendor patch source selection differs: ' + patch['id'])
        delta = ''.join(difflib.unified_diff(
            (root/original).read_text(encoding='utf8').splitlines(keepends=True),
            (root/derived).read_text(encoding='utf8').splitlines(keepends=True),
            fromfile=original, tofile=derived)).encode()
        if delta != (root/patch['patch_path']).read_bytes():
            raise ValueError('C071 vendor patch is not reproducible: ' + patch['id'])
    if graph['vendor_patch_sources'] != [patch['derived_path'] for patch in companion['vendor_patches']]:
        raise ValueError('C071 compiled vendor patch inventory changed')
    for name in ('main.c', 'stm32c0xx_hal_msp.c', 'usbd_conf.c', 'usbd_cdc_if.c'):
        expected = 'Platform/STM32C0/Src/' + name
        if [path for path in sources if Path(path).name == name] != [expected]:
            raise ValueError('C071 adapted source ownership collision: ' + name)
    if native + 'Core/Src/usb.c' not in sources:
        raise ValueError('C071 native usb.c PCD owner missing')
    pcd = [(path, (root/path).read_text(encoding='utf8')) for path in sources if path.endswith('.c')]
    for expression in (r'(?m)^PCD_HandleTypeDef hpcd_USB_DRD_FS;',
            r'(?m)^void HAL_PCD_MspInit\(', r'(?m)^void HAL_PCD_MspDeInit\('):
        owners = [path for path, text in pcd if re.search(expression, text)]
        if owners != [native + 'Core/Src/usb.c']:
            raise ValueError('C071 must have one native PCD/MSP owner: ' + expression)
    silicon = [path for path in sources if '/Drivers/' in path or '/system_stm32' in path]
    entries=graph.get('native_hal_derivatives',[])
    required=('stm32c0xx_hal_spi.c','stm32c0xx_hal_uart.c','stm32c0xx_hal_uart_ex.c')
    if [Path(e['derived']).name for e in entries]!=list(required):
        raise ValueError('C071 exact native HAL derivative inventory changed')
    for entry in entries:
        original,derived=entry['original'],entry['derived']
        if not original.startswith(native) or not derived.startswith('HardwareGenerated/ReviewedC071Hal/'):
            raise ValueError('C071 HAL source owner differs')
        if original in sources or sources.count(derived)!=1 or profile['files_sha256'][original.removeprefix(native)]!=entry['original_sha256']:
            raise ValueError('C071 HAL compiled owner/provenance differs')
        for kind in ('original','derived','patch'):
            if hashlib.sha256((root/entry[kind]).read_bytes()).hexdigest()!=entry[kind+'_sha256']:
                raise ValueError('C071 HAL derivative hash changed')
        delta=''.join(difflib.unified_diff((root/original).read_bytes().decode().splitlines(True),
            (root/derived).read_bytes().decode().splitlines(True),fromfile=original,tofile=derived)).encode()
        if delta!=(root/entry['patch']).read_bytes():raise ValueError('C071 HAL patch not reproducible')
    derived_paths={entry['derived'] for entry in entries}
    if any(not path.startswith(native) and path not in derived_paths for path in silicon):
        raise ValueError('C071 HAL/CMSIS/system tree mixed with companion')
    if (graph['asm_sources'] != [native + 'startup_stm32c071xx.s'] or
            graph['linker_script'] != native + 'STM32C071XX_FLASH.ld'):
        raise ValueError('C071 native startup/linker owner changed')
    conf = (root/'Platform/STM32C0/Src/usbd_conf.c').read_text(encoding='utf8')
    regions = re.findall(r'HAL_PCDEx_PMAConfig\(&hpcd_USB_DRD_FS,\s*(\w+),\s*PCD_SNG_BUF,\s*(0x\w+)\) != HAL_OK', conf)
    if regions != [('0x00','0x40'),('0x80','0x80'),('CDC_IN_EP','0xC0'),
                   ('CDC_OUT_EP','0x100'),('CDC_CMD_EP','0x140')]:
        raise ValueError('C071 checked aligned PMA layout changed')
    if conf.count('MX_USB_PCD_Init();') != 1 or 'HAL_PCD_Init(' in conf:
        raise ValueError('C071 companion must call native initializer exactly once')
    print('PASS registered C071 native PCD ownership, frozen companion and checked PMA layout')

def C071EffectiveMacros_Validate(root, graph, compiler):
    flags = [*graph['mcu_flags'], *['-I'+path for path in graph['include_dirs']],
             *['-D'+value for value in graph['defines']]]
    for name in ('main.c','stm32c0xx_hal_rcc.c','usb.c','usbd_cdc.c'):
        source = next(path for path in graph['sources'] if Path(path).name == name)
        result = subprocess.run([compiler, '-E', '-dM', *flags, source], cwd=root,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode:
            raise ValueError('C071 actual preprocessing failed: ' + source)
        macros = result.stdout
        selected = re.findall(r'(?m)^#define (STM32[FC][0-9]{3}[A-Za-z0-9]+)\s+([^\r\n]*)$', macros)
        if selected != [('STM32C071xx','1')]:
            raise ValueError('C071 effective device macro changed')
        for macro in ('HSI_VALUE','HSI48_VALUE'):
            if not re.search(r'(?m)^#define '+macro+r'\s+\(?48000000[Uu][Ll]?\)?\s*$',macros):
                raise ValueError('C071 effective 48MHz clock changed: ' + macro)
        if name == 'usbd_cdc.c' and not all(re.search(r'(?m)^#define '+macro+r'\s+'+value+r'\s*$',macros)
                for macro,value in (('USBD_SELF_POWERED','0U'),('USBD_MAX_POWER','0x32U'))):
            raise ValueError('C071 effective bus-powered 100mA descriptor changed')
        print('PASS actual C071 device/48MHz preprocessing ' + source)
