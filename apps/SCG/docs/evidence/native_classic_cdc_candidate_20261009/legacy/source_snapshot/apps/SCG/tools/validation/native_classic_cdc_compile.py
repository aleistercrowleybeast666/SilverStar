"""Compile an admitted native project in a NEW isolated output, never its Makefile.

This is source/ABI/closure validation, not a Ground runtime adapter or hardware
acceptance. The descriptor is supplied by the trusted operator, outside input.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys

SCG=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SCG/"src"))
from silverstar_fccg.hardware.native_classic_cdc import NativeDeviceFacts, NativeMemoryRegion, NativeClassicCdc_Inspect, NATIVE_PREFIX


def NativeCompile_Run(args):
    root=args.input.resolve(); output=args.output.absolute()
    if output.exists() or output.resolve()!=output or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("new disjoint validation output required")
    if args.device_facts.resolve().is_relative_to(root):
        raise ValueError("trusted independent device descriptor must be outside the imported project")
    facts_json=json.loads(args.device_facts.read_text(encoding="utf-8"))
    facts=NativeDeviceFacts(**{**facts_json,"regions":tuple(NativeMemoryRegion(**r) for r in facts_json["regions"])})
    proof,inventory,files=NativeClassicCdc_Inspect(root,device_facts=facts,spi_resource=args.spi,gpio_resources=tuple(args.gpio))
    output.mkdir(parents=True)
    original_hashes={p:hashlib.sha256(b).hexdigest() for p,b in files.items()}
    for p,b in files.items():
        dest=output/NATIVE_PREFIX/p; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(b)
    tools=SCG/"plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools"
    spec=importlib.util.spec_from_file_location("native_dependency_contract",tools/"ground_artifact_contract.py")
    dependencies=importlib.util.module_from_spec(spec); spec.loader.exec_module(dependencies)
    graph={**proof["build"],"sources":[NATIVE_PREFIX+p for p in proof["build"]["sources"]],
           "asm_sources":[NATIVE_PREFIX+p for p in proof["build"]["asm_sources"]],
           "include_dirs":[NATIVE_PREFIX+p for p in proof["build"]["include_dirs"]],
           "required_irq_handlers":proof["required_irq_handlers"],"linker_script":NATIVE_PREFIX+proof["build"]["linker_script"]}
    compiler=args.toolchain_prefix+"gcc"
    environment=os.environ.copy()
    for name in ("CPATH","C_INCLUDE_PATH","CPLUS_INCLUDE_PATH","OBJC_INCLUDE_PATH","DEPENDENCIES_OUTPUT","SUNPRO_DEPENDENCIES","GCC_EXEC_PREFIX","COMPILER_PATH"):
        environment.pop(name,None)
    commands=[]
    log=output/"commands.log"

    def run(command):
        result=subprocess.run(command,cwd=output,env=environment,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        with log.open("a",encoding="utf-8") as stream:
            stream.write(json.dumps(command)+"\n"+result.stdout+"\nEXIT "+str(result.returncode)+"\n")
        commands.append({"command":command,"exit":result.returncode})
        if result.returncode: raise ValueError("native validation command failed; see "+str(log))
        return result.stdout

    flags=[*graph["mcu_flags"],*["-I"+p for p in graph["include_dirs"]],*["-D"+d for d in graph["defines"]]]
    # Declarations must agree with actual headers, and the compiler must select
    # the expected Cortex/32-bit pointer ABI. This test source is never executed.
    core={"cortex-m0":0,"cortex-m0plus":0,"cortex-m3":3,"cortex-m4":4}[facts.core]
    tx_qualifier="const " if proof["spi_abi"]["tx_buffer_const"] else ""
    fpu_probe='_Static_assert(__FPU_PRESENT == 1U, "independent FPU facts must match native CMSIS");' if facts.fpu else ''
    probe=output/"Generated/Src/native_abi_probe.c"; probe.parent.mkdir(parents=True)
    probe.write_text(f'''#include "main.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"
#include <stdint.h>
_Static_assert(__CORTEX_M == {core}U, "native CMSIS Cortex must match independent device facts");
{fpu_probe}
_Static_assert(sizeof(void *) == 4U, "selected native ABI must use 32-bit pointers");
_Static_assert(sizeof(((USBD_CDC_HandleTypeDef *)0)->TxState) == sizeof(uint32_t), "selected CDC adapter requires 32-bit TxState");
HAL_StatusTypeDef HAL_SPI_Transmit(SPI_HandleTypeDef *, {tx_qualifier}uint8_t *, uint16_t, uint32_t);
HAL_StatusTypeDef HAL_SPI_TransmitReceive(SPI_HandleTypeDef *, {tx_qualifier}uint8_t *, uint8_t *, uint16_t, uint32_t);
void HAL_GPIO_WritePin(GPIO_TypeDef *, uint16_t, GPIO_PinState);
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *, uint16_t);
uint32_t HAL_GetTick(void);
uint8_t CDC_Transmit_FS(uint8_t *, uint16_t);
''',encoding="utf-8")
    graph["sources"].append("Generated/Src/native_abi_probe.c")
    objects=[]
    started=datetime.now(timezone.utc).isoformat()
    try:
        version=run([compiler,"--version"]).splitlines()[0]
        for build_dir,analyzer in [("build",False),("build/analysis",True)]:
            objects=[]
            for source in graph["sources"]:
                obj=output/build_dir/Path(source).with_suffix(".o"); obj.parent.mkdir(parents=True,exist_ok=True)
                rel=obj.relative_to(output).as_posix(); asm=obj.with_suffix(".s").relative_to(output).as_posix()
                common=[compiler,*flags,"-std=c11","-Os","-ffunction-sections","-fdata-sections","-fstack-usage", "-Wall","-Werror=implicit-function-declaration","-Werror=incompatible-pointer-types","-Werror=return-type"]
                if analyzer: common.append("-fanalyzer")
                if source.startswith("Generated/"):common += ["-Wextra","-Wpedantic","-Werror"]
                run([*common,"-MD","-MP","-MF",rel.removesuffix(".o")+".d","-MT",rel,"-S",source,"-o",asm])
                dependencies.AssemblerSource_Prepare(output,graph,source,build_dir)
                run([compiler,*graph["mcu_flags"],"-x","assembler","-Wa,--MD,"+rel.removesuffix(".o")+".gas.d","-c",asm,"-o",rel])
                dependencies.DependencyClosure_Validate(output,graph,compiler,build_dir=build_dir,source=source)
                objects.append(rel)
            for source in graph["asm_sources"]:
                obj=output/build_dir/Path(source).with_suffix(".o");obj.parent.mkdir(parents=True,exist_ok=True)
                rel=obj.relative_to(output).as_posix()
                run([compiler,*flags,"-save-temps=obj","-MD","-MP","-MF",rel.removesuffix(".o")+".d","-MT",rel,"-Wa,--MD,"+rel.removesuffix(".o")+".gas.d","-x","assembler-with-cpp","-c",source,"-o",rel])
                dependencies.DependencyClosure_Validate(output,graph,compiler,build_dir=build_dir,source=source)
                objects.append(rel)
            elf=build_dir+"/native.elf"
            run([compiler,*objects,*graph["mcu_flags"],"-Wl,--gc-sections,-Map="+build_dir+"/native.map","-T"+graph["linker_script"],"-specs=nano.specs","-lc","-lm","-lnosys","-o",elf])
            symbols=run([args.toolchain_prefix+"nm","-n",elf])
            vector=build_dir+"/vectors.bin"
            run([args.toolchain_prefix+"objcopy","--dump-section",".isr_vector="+vector,elf])
            vector_bytes=(output/vector).read_bytes()
            dependencies.InterruptVectors_Validate(output,graph,symbols,vector_bytes)
            if len(vector_bytes)<8:
                raise ValueError("native vector has no initial MSP/reset entries")
            initial_sp,reset=struct.unpack_from("<II",vector_bytes)
            # ST GNU startup declares its real Reset_Handler body weak. Keep
            # that native policy; external IRQs still require strong owners.
            reset_owners=re.findall(r"(?m)^([0-9a-fA-F]+)\s+[TW]\s+Reset_Handler$",symbols)
            defaults=re.findall(r"(?m)^([0-9a-fA-F]+)\s+[TW]\s+Default_Handler$",symbols)
            startup_object=Path(graph["asm_sources"][0]).with_suffix('.o').as_posix()
            reset_map=re.search(r"\.text\.Reset_Handler\s+0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+"+
                re.escape(build_dir+'/'+startup_object)+r"\s",(output/build_dir/'native.map').read_text(encoding='utf-8'))
            if (initial_sp & 7 or not any(r.name!='FLASH' and r.origin<initial_sp<=r.origin+r.length for r in facts.regions)
                    or len(reset_owners)!=1 or reset != (int(reset_owners[0],16)|1)
                    or any(reset==(int(d,16)|1) for d in defaults) or not reset_map):
                raise ValueError("native initial MSP/reset vector contradicts memory/real startup owner contract")
            header=(output/elf).read_bytes()[:52]
            if header[:7]!=b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H",header,18)[0]!=40:
                raise ValueError("native artifact is not little-endian ELF32 ARM")
            eflags=struct.unpack_from("<I",header,36)[0]
            if ("-mfloat-abi=hard" in graph["mcu_flags"]) != bool(eflags & 0x400):
                raise ValueError("native artifact floating ABI contradicts device/build contract")
            sections=run([args.toolchain_prefix+"objdump","-h",elf]); allocated=0
            for match in re.finditer(r"^\s*\d+\s+(\S+)\s+([\da-fA-F]+)\s+([\da-fA-F]+)\s+([\da-fA-F]+).*\n\s*([^\n]+)",sections,re.M):
                name,size,vma,lma,section_flags=match.groups()
                if "ALLOC" not in section_flags or int(size,16)==0:continue
                allocated+=1
                for address in [int(vma,16)]+([int(lma,16)] if "LOAD" in section_flags else []):
                    if not any(r.origin<=address and address+int(size,16)<=r.origin+r.length for r in facts.regions):
                        raise ValueError("native allocated section escapes independent physical regions: "+name)
            if not allocated:raise ValueError("native artifact has no parsed allocated sections")
        # Identity, physical bounds and read-only input preservation remain
        # separately recorded from unproved USB/radio/task runtime behavior.
        for p,b in files.items():
            if (root/p).read_bytes()!=b or (output/NATIVE_PREFIX/p).read_bytes()!=b:raise ValueError("native inputs changed during validation")
        status="NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED"
    except Exception as error:
        status="FAILED"; failure=str(error)
        raise
    finally:
        receipt={"status":status,"started_utc":started,"finished_utc":datetime.now(timezone.utc).isoformat(),
          "source_commit":subprocess.check_output(["git","-C",str(SCG),"rev-parse","HEAD"],text=True).strip(),
          "auditable_dirty_diff":subprocess.check_output(["git","-C",str(SCG),"diff","--binary"],text=True),
          "new_module_sha256":hashlib.sha256((SCG/"src/silverstar_fccg/hardware/native_classic_cdc.py").read_bytes()).hexdigest(),
          "validation_script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "validation_script_source":Path(__file__).read_text(encoding="utf-8"),
          "import_module_source":(SCG/"src/silverstar_fccg/hardware/native_classic_cdc.py").read_text(encoding="utf-8"),
          "toolchain_version":locals().get("version"),
          "facts":facts_json,"contract":proof,"commands":commands,"graph":graph,"input_sha256":original_hashes,
          "output_artifact_sha256":{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob("*") if p.is_file() and p.suffix in {".elf",".map",".o",".su",".d",".s",".bin"}},
          "failure":locals().get("failure"),"limits":"NOT PROVEN: Ground runtime adapter, critical contracts, async lifecycle/rearm/EP0, physical memory authority beyond caller review, tick liveness, radio us timing, stack/WCET/hardware. No board access. This is not generated Ground firmware."}
        (output/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(status,output,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--device-facts",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--spi",required=True)
    parser.add_argument("--gpio",nargs="+",required=True)
    parser.add_argument("--toolchain-prefix",default="arm-none-eabi-")
    NativeCompile_Run(parser.parse_args())
