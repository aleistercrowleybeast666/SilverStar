"""Real frozen CubeMX input admission tests; no board/native recipe execution.

SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT must contain reviewed cube-f103-usb and
cube-f407-usb. Missing configured inputs fail; absent configuration skips.
"""
from pathlib import Path
from dataclasses import replace
import hashlib
import os
import re
import shutil
import pytest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImportError
from silverstar_fccg.hardware.native_classic_cdc import NativeDeviceFacts, NativeMemoryRegion, NativeClassicCdc_Inspect


@pytest.fixture(params=["f103-usb", "f407-usb"])
def native(request, tmp_path):
    origin=os.environ.get("SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT", "")
    if not origin: pytest.skip("real complete native CDC inputs not configured")
    source=Path(origin)/("cube-"+request.param)
    if not source.is_dir(): pytest.fail("configured real input missing: "+str(source))
    scg=Path(__file__).resolve().parents[1]
    if request.param=="f103-usb":
        component="silverstar_mcu_stm32f103c8t6"; nss="SPI_RADIO_NSS"
        values=("STM32F103C8T6","cortex-m3","STM32F103xB","startup_stm32f103xb.s",
                (NativeMemoryRegion("FLASH",0x08000000,65536),NativeMemoryRegion("RAM",0x20000000,20480)))
    else:
        component="silverstar_mcu_stm32f407vet6"; nss="RADIO_NSS"
        values=("STM32F407VET6","cortex-m4","STM32F407xx","startup_stm32f407xx.s",
                (NativeMemoryRegion("FLASH",0x08000000,524288),NativeMemoryRegion("RAM",0x20000000,131072),NativeMemoryRegion("CCMRAM",0x10000000,65536)))
    evidence=scg/"plugins/builtin"/component/"plugin.json"
    package,family,header=("STM32Cube_FW_F1_V1.8.7","STM32F1xx","stm32f103xb.h") if request.param=="f103-usb" else ("STM32Cube_FW_F4_V1.28.3","STM32F4xx","stm32f407xx.h")
    irq_evidence=Path(os.environ.get("SILVERSTAR_VENDOR_IRQ_REPOSITORY", "D:/Tools/Embedded/STM32/Repository"))/package/"Drivers/CMSIS/Device/ST"/family/"Include"/header
    if not irq_evidence.is_file():pytest.fail("independent installed vendor IRQ header missing: "+str(irq_evidence))
    irq_text=re.sub(r'/\*.*?\*/|//[^\r\n]*','',irq_evidence.read_text(encoding="utf-8-sig"),flags=re.S)
    irq_numbers=tuple((n,int(v)) for n,v in re.findall(r"(?m)^\s*(\w+_IRQn)\s*=\s*(-?\d+)\s*(?=,|\})",irq_text))
    if request.param=="f407-usb":
        assert dict(irq_numbers)['FPU_IRQn']==81  # Final enumerator has no comma.
    facts=NativeDeviceFacts(*values,str(evidence),hashlib.sha256(evidence.read_bytes()).hexdigest(),
                            fpu="fpv4-sp-d16" if request.param=="f407-usb" else "",
                            irq_numbers=irq_numbers,irq_header_sha256=hashlib.sha256(irq_evidence.read_bytes()).hexdigest(),
                            irq_evidence_source=str(irq_evidence))
    root=tmp_path/"native"; shutil.copytree(source,root)
    return root,dict(device_facts=facts,spi_resource="SPI1",gpio_resources=(nss,"RADIO_RST","RADIO_BUSY","RADIO_DIO1"))


def test_import_preservation_and_reload(native,tmp_path,tmp_path_factory):
    from silverstar_fccg.plugins.catalog import PluginCatalog
    from silverstar_fccg.project.folder_contract import ProjectRoot_Save
    from silverstar_fccg.project.model import ProjectModel_Load
    from silverstar_fccg.generator.multi_target import GroundFiles_Render
    from test_round2_targets import _GroundBoardProject_Get
    root,args=native
    proof,inventory,files=NativeClassicCdc_Inspect(root,**args)
    assert proof["static_contract"]=="VALIDATED_TEXT_SCOPE"
    assert not proof["runtime_adapter_enabled"]
    assert proof["compiler_abi_closure"]==proof["tick_liveness"]=="NOT_PROVEN"
    service=FccgService(tmp_path_factory.mktemp("w"))
    first=service.NativeClassicCdcProject_Import(root,**args,risk_acknowledged=True)
    assert all((first.snapshot_root/p).read_bytes()==b==(root/p).read_bytes() for p,b in files.items())
    repeat=service.NativeClassicCdcProject_Import(root,**args,risk_acknowledged=True)
    assert repeat.hardware==first.hardware and repeat.snapshot_root==first.snapshot_root
    scg=Path(__file__).resolve().parents[1]
    catalog=PluginCatalog(scg/"plugins/builtin",scg/"plugins/installed"); catalog.Scan()
    model=_GroundBoardProject_Get(catalog)
    model.ground_target=replace(model.ground_target,board="",hardware=first.hardware)
    output=tmp_path/"project"; ProjectRoot_Save(model,output,create_new=True)
    loaded=ProjectModel_Load(output/"SilverStar.ssproject")
    assert loaded.ground_target.hardware==first.hardware
    loaded.ground_target.hardware.inventory["native_complete_classic_cdc"]["runtime_adapter_enabled"]=True
    before={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output.rglob("*") if p.is_file()}
    with pytest.raises(ValueError,match="runtime adapter.*NOT PROVEN"):
        GroundFiles_Render(loaded,catalog,WorkspacePolicy(tmp_path/"workspace"))
    assert before=={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in output.rglob("*") if p.is_file()}


@pytest.mark.parametrize("change",["missing-cdc","make-expression","CPU","ABI","memory","device-macro",
    "startup","USBX","class","RTOS","dynamic-allocation","unknown-hook","spi-owner","tick",
    "include-escape","linker-dependency","make-append","memory-expression",
    "spi-unknown-abi","spi-mixed-qualifier","reset-owner","facts-fpu"])
def test_incompatible_inputs_rejected(native,change):
    root,args=native; make=root/"Makefile"; text=make.read_text(encoding="utf-8-sig")
    if change=="missing-cdc": (root/"USB_DEVICE/App/usbd_cdc_if.c").unlink()
    elif change=="make-expression": make.write_text(text.replace("Core/Src/main.c","$(shell whoami)",1),encoding="utf-8")
    elif change=="CPU": make.write_text(text.replace("-mcpu="+args["device_facts"].core,"-mcpu=cortex-m7"),encoding="utf-8")
    elif change=="ABI": make.write_text(text+"\nFLOAT-ABI = -mfloat-abi=hard\n",encoding="utf-8")
    elif change=="memory": args["device_facts"]=replace(args["device_facts"],regions=(NativeMemoryRegion("FLASH",0x08000000,999),))
    elif change=="device-macro": make.write_text(text.replace("-D"+args["device_facts"].device_macro,"-DSTM32UNKNOWN"),encoding="utf-8")
    elif change=="startup": args["device_facts"]=replace(args["device_facts"],startup="startup_stm32unknown.s")
    elif change in {"USBX","class","RTOS"}:
        ioc=next(root.glob("*.ioc")); data=ioc.read_text(encoding="utf-8-sig")
        if change=="USBX": data=data.replace("=USB_DEVICE","=USBX")
        elif change=="class": data=data.replace("=Cdc","=Hid")
        else: data+="\nMcu.IP99=FREERTOS\n"
        ioc.write_text(data,encoding="utf-8")
    elif change in {"dynamic-allocation","unknown-hook"}:
        path=root/("USB_DEVICE/Target/usbd_conf.c" if change=="dynamic-allocation" else "USB_DEVICE/App/usbd_cdc_if.c")
        data=path.read_text(encoding="utf-8-sig")
        path.write_text(data.replace("USBD_static_malloc","malloc") if change=="dynamic-allocation" else data.replace("USER CODE BEGIN 6","UNKNOWN HOOK"),encoding="utf-8")
    elif change=="spi-owner":
        path=root/"Core/Src/spi.c"; path.write_text(path.read_text(encoding="utf-8-sig").replace("SPI_MODE_MASTER","SPI_MODE_SLAVE"),encoding="utf-8")
    elif change=="tick":
        for path in (root/"Core/Src").glob("*.c"):
            data=path.read_text(encoding="utf-8-sig")
            if "HAL_IncTick" in data: path.write_text(data.replace("HAL_IncTick","Unknown_Tick"),encoding="utf-8")
    elif change=="include-escape": make.write_text(text.replace("-ICore/Inc","-I../escape"),encoding="utf-8")
    elif change=="make-append": make.write_text(text+"\nC_SOURCES += Core/Src/extra.c\n",encoding="utf-8")
    elif change=="memory-expression":
        script=next(root.glob("*.ld"))
        script.write_text(script.read_text(encoding="utf-8-sig").replace("MEMORY\n{", "MEMORY\n{\nEXTRA (xrw) : ORIGIN = (0x40000000), LENGTH = 1K"),encoding="utf-8")
    elif change in {"spi-unknown-abi","spi-mixed-qualifier"}:
        header=next((root/"Drivers").glob("*_HAL_Driver/Inc/*_hal_spi.h"))
        data=header.read_text(encoding="utf-8-sig")
        data=data.replace("const uint8_t *pData", "uint32_t *pData" if change=="spi-unknown-abi" else "uint8_t *pData",1)
        header.write_text(data,encoding="utf-8")
    elif change=="reset-owner":
        startup=root/args["device_facts"].startup
        startup.write_text(startup.read_text(encoding="utf-8-sig").replace("Reset_Handler:",
            ".thumb_set Reset_Handler, Default_Handler\nSyntheticReset:",1),encoding="utf-8")
    elif change=="facts-fpu":
        args["device_facts"]=replace(args["device_facts"],fpu="" if args["device_facts"].fpu else "fpv4-sp-d16")
    else:
        script=next(root.glob("*.ld")); script.write_text(script.read_text(encoding="utf-8-sig")+"\nINCLUDE other.ld\n",encoding="utf-8")
    reasons={"make-append":"literal C_SOURCES", "memory-expression":"Linker memory",
        "reset-owner":"reset entry body/owner", "facts-fpu":"FPU facts",
        "spi-unknown-abi":"blocking SPI ABI", "spi-mixed-qualifier":"SPI transmit buffer qualifiers",
        "missing-cdc":"Missing or escaping", "make-expression":"expression", "CPU":"Native CPU",
        "ABI":"ABI|FLOAT-ABI", "memory":"Linker memory", "device-macro":"effective definitions",
        "startup":"startup", "USBX":"Only complete", "class":"Only complete", "RTOS":"FreeRTOS",
        "dynamic-allocation":"Dynamic native USB", "unknown-hook":"lifecycle/receive hook",
        "spi-owner":"real type/init owner", "tick":"tick initialization", "include-escape":"Unsafe native build path",
        "linker-dependency":"linker file dependencies"}
    with pytest.raises(CubeMxImportError,match=reasons[change]): NativeClassicCdc_Inspect(root,**args)


@pytest.mark.parametrize("damage",["source","extra","contract"])
def test_snapshot_corruption_preserved_and_rejected(native,tmp_path_factory,damage):
    root,args=native; service=FccgService(tmp_path_factory.mktemp("w"))
    result=service.NativeClassicCdcProject_Import(root,**args,risk_acknowledged=True)
    path=result.snapshot_root/"Core/Src/main.c" if damage=="source" else (
        result.snapshot_root/"Extra.h" if damage=="extra" else result.snapshot_root.parent/"native-contract.json")
    path.write_bytes(b"user change\n")
    with pytest.raises(CubeMxImportError,match="Immutable native"):
        service.NativeClassicCdcProject_Import(root,**args,risk_acknowledged=True)
    assert path.read_bytes()==b"user change\n"


def test_long_snapshot_path_rejected_before_publication(native,tmp_path):
    if os.name != "nt": pytest.skip("Windows portable path limit")
    root,args=native
    workspace=tmp_path/("long_"+"x"*70)
    service=FccgService(workspace)
    with pytest.raises(CubeMxImportError,match="portable Windows limit"):
        service.NativeClassicCdcProject_Import(root,**args,risk_acknowledged=True)
    assert not service.hardware_importer.cache_root.exists()


def test_make_recipe_not_executed(native):
    root,args=native
    with (root/"Makefile").open("a") as stream: stream.write("\nall:\n\tSHOULD_NEVER_EXECUTE_NATIVE_RECIPE\n")
    NativeClassicCdc_Inspect(root,**args)
    assert not (root/"executed.txt").exists()
