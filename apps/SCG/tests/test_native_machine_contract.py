"""CPU/IRQ mutations from the independent b0df77f review, not board tests."""
import pytest
import shutil
import subprocess
from test_native_classic_cdc import native
from silverstar_fccg.hardware.cubemx import CubeMxImportError
from silverstar_fccg.hardware.native_classic_cdc import NativeClassicCdc_Inspect
from silverstar_fccg.hardware.native_machine_contract import NativeArmAttributes_Validate, NativeIndependentVectors_Validate


def test_startup_cpu_override_rejected(native):
    root,args=native
    startup=root/args['device_facts'].startup
    cpu=args['device_facts'].core
    startup.write_text(startup.read_text(encoding='utf-8-sig').replace(
        '.cpu '+cpu, '.cpu cortex-m4' if cpu!='cortex-m4' else '.cpu cortex-m7'),encoding='utf-8')
    with pytest.raises(CubeMxImportError,match='CPU directive'):
        NativeClassicCdc_Inspect(root,**args)


def test_irq_vector_mutual_swap_rejected(native):
    root,args=native
    startup=root/args['device_facts'].startup
    a,b=('USB_LP_CAN1_RX0_IRQHandler','USB_HP_CAN1_TX_IRQHandler') if args['device_facts'].core=='cortex-m3' else ('OTG_FS_IRQHandler','USART1_IRQHandler')
    code=startup.read_text(encoding='utf-8-sig')
    startup.write_text(code.replace(a,'__SWAP__').replace(b,a).replace('__SWAP__',b),encoding='utf-8')
    with pytest.raises(CubeMxImportError,match='independent IRQn'):
        NativeClassicCdc_Inspect(root,**args)


def test_real_arm_cpu_override_object_rejected(tmp_path):
    compiler=shutil.which('arm-none-eabi-gcc'); readelf=shutil.which('arm-none-eabi-readelf')
    if not compiler or not readelf:pytest.skip('real ARM tools unavailable')
    source=tmp_path/'override.s';obj=tmp_path/'override.o'
    source.write_text('.syntax unified\n.cpu cortex-m4\n.thumb\n.text\n.global illegal\n.type illegal,%function\nillegal:\nqadd r0,r1,r2\nbx lr\n',encoding='utf-8')
    compiled=subprocess.run([compiler,'-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-c',str(source),'-o',str(obj)],capture_output=True,text=True,timeout=30)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    attributes=subprocess.run([readelf,'-A',str(obj)],capture_output=True,text=True,timeout=30)
    assert attributes.returncode==0 and 'v7E-M' in attributes.stdout
    with pytest.raises(ValueError,match='Actual ARM architecture'):
        NativeArmAttributes_Validate(attributes.stdout,core='cortex-m3',fpu='',hard_float=False,assembly=True)


def test_binary_vector_exchange_rejected_independently():
    import struct
    symbols='08000100 T USB_HP_CAN1_TX_IRQHandler\n08000200 T USB_LP_CAN1_RX0_IRQHandler\n'
    vector=bytearray(37*4)
    struct.pack_into('<I',vector,35*4,0x08000101)
    struct.pack_into('<I',vector,36*4,0x08000201)
    slots={'USB_HP_CAN1_TX_IRQHandler':19,'USB_LP_CAN1_RX0_IRQHandler':20}
    NativeIndependentVectors_Validate(vector,symbols,slots)
    vector[35*4:37*4]=vector[36*4:37*4]+vector[35*4:36*4]
    with pytest.raises(ValueError,match='independent IRQn binding'):
        NativeIndependentVectors_Validate(vector,symbols,slots)
