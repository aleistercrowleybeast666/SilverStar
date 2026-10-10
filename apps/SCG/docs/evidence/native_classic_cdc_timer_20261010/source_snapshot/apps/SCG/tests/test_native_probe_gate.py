"""A CPP receipt may not silently select the old USB or another clock header."""
from pathlib import Path
import importlib.util
import pytest
from silverstar_fccg.hardware import native_machine_contract


@pytest.mark.parametrize('mutation',['none','old-config','analyzer-old-config','missing-clock','no-config'])
def test_probe_requires_actual_selected_headers(tmp_path,monkeypatch,mutation):
    tools=Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools'
    monkeypatch.syspath_prepend(str(tools))
    monkeypatch.setitem(__import__('sys').modules,'native_machine_contract',native_machine_contract)
    spec=importlib.util.spec_from_file_location('native_probe_gate_test',tools/'check_native_probe.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    clock='Drivers/CMSIS/Device/ST/STM32F4xx/Include/stm32f407xx.h'
    config='HardwareGenerated/ReviewedNativeConfig/USB_DEVICE/Target/usbd_conf.h'
    graph={'sources':['Generated/Src/native_clock_port.c','Generated/Src/native_abi_probe.c']}
    contract={'clock':{'clock_header':clock},'usb_config':{'derived':config}}
    for build in ('build','build/analysis'):
        for source in graph['sources']:
            dependencies=[source]
            if source.endswith('/native_clock_port.c') and mutation!='missing-clock':
                dependencies.append('HardwareGenerated/NativeClassicCdc/'+clock)
            if source.endswith('/native_abi_probe.c') and mutation!='no-config':
                old=mutation=='old-config' or (mutation=='analyzer-old-config' and build.endswith('/analysis'))
                dependencies.append('HardwareGenerated/NativeClassicCdc/USB_DEVICE/Target/usbd_conf.h' if old else config)
            obj=build+'/'+str(Path(source).with_suffix('.o')).replace('\\','/')
            dep=tmp_path/Path(obj).with_suffix('.d');dep.parent.mkdir(parents=True,exist_ok=True)
            dep.write_text(obj+': '+' '.join(dependencies)+'\n')
    if mutation=='none':
        gate.ConfigurationDependencies_Validate(tmp_path,graph,contract)
    else:
        with pytest.raises(ValueError):gate.ConfigurationDependencies_Validate(tmp_path,graph,contract)
