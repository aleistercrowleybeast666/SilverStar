"""Compile an admitted native project in a NEW isolated output, never its Makefile.

This validates source/ABI/closure and optionally a private generated Ground
runtime candidate, never hardware acceptance. The descriptor is supplied by
the trusted operator, outside input. Normal native generation remains blocked.
"""
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess

SCG=Path(__file__).resolve().parents[3]
from silverstar_fccg.hardware.native_classic_cdc import NativeDeviceFacts, NativeMemoryRegion, NativeClassicCdc_Inspect, NATIVE_PREFIX
from silverstar_fccg.hardware.native_machine_contract import NativeAssemblyDirectives_Validate, NativeArmAttributes_Validate, NativeIndependentVectors_Validate
from silverstar_fccg.generator.native_hal import NativeHalDerivatives_Render
from silverstar_fccg.generator.native_clock import NativeClock_FilesRender, NativeClockSourceContract_Validate
from silverstar_fccg.generator.native_ground import NativeGroundCandidate_Render
from silverstar_fccg.generator.native_clock_probe import NativeTimerProbe_FilesRender, NativeTimerProbe_MakeRender


def NativeCompile_Run(args, *, device_facts=None, runtime_catalog=None, prepared_candidate=None):
    timer_probe=getattr(args,'native_timer_probe',False)
    if timer_probe and (args.clock_hz is None or args.runtime_project is not None or args.reviewed_hal):
        raise ValueError('Private timer probe needs --clock-hz, includes HAL once, and is separate from Ground runtime')
    root=args.input.resolve(); output=args.output.absolute()
    if output.exists() or output.resolve()!=output or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("new disjoint validation output required")
    if device_facts is None:
        if args.device_facts.resolve().is_relative_to(root):
            raise ValueError("trusted independent device descriptor must be outside the imported project")
        facts_json=json.loads(args.device_facts.read_text(encoding="utf-8"))
        facts=NativeDeviceFacts(**{**facts_json,"regions":tuple(NativeMemoryRegion(**r) for r in facts_json["regions"]),
            "irq_numbers":tuple(tuple(item) for item in facts_json.get("irq_numbers",[]))})
    else:
        if not isinstance(device_facts, NativeDeviceFacts):
            raise ValueError("trusted independent NativeDeviceFacts required")
        facts=device_facts
        facts_json=json.loads(json.dumps(asdict(facts)))
    if prepared_candidate is None:
        proof,inventory,files=NativeClassicCdc_Inspect(root,device_facts=facts,spi_resource=args.spi,gpio_resources=tuple(args.gpio))
        native_prefix=NATIVE_PREFIX
    else:
        # Prepared input comes only from the backend after exact native/companion/model checks.
        proof,inventory,files,prepared_files,prepared_graph,prepared_records=prepared_candidate
        native_prefix='HardwareGenerated/STM32CubeMX/'
        facts.Facts_Validate()
    output.mkdir(parents=True)
    if getattr(args, 'backend_owner_token', None):
        (output/'backend-owner.json').write_text(json.dumps({'token':args.backend_owner_token}),encoding='utf-8')
    original_hashes={p:hashlib.sha256(b).hexdigest() for p,b in files.items()}
    for p,b in files.items():
        dest=output/native_prefix/p; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(b)
    snapshot_modules=[Path(__file__),SCG/"tools/validation/native_classic_cdc_compile.py",
        SCG/"src/silverstar_fccg/app/native_ground.py",SCG/"src/silverstar_fccg/app/service.py",
        SCG/"src/silverstar_fccg/project/model.py",SCG/"src/silverstar_fccg/hardware/native_classic_cdc.py",
        SCG/"src/silverstar_fccg/hardware/native_machine_contract.py",
        SCG/"src/silverstar_fccg/generator/native_hal.py",SCG/"src/silverstar_fccg/generator/native_clock.py"]
    if args.runtime_project is not None:
        snapshot_modules += [SCG/('src/silverstar_fccg/generator/'+name+'.py') for name in ('native_ground','native_platform','native_runtime','native_no_heap','native_pc','native_usb_data','native_radio','native_clock_tim','native_usb_config','native_usb_indexed','native_control','ground_usb_control')]
        snapshot_modules += list((SCG/'tests').glob('test_native*.py'))
        snapshot_modules += [SCG/('plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools/'+name+'.py') for name in ('check_ground','check_native_ground','check_native_probe')]
    if timer_probe:
        snapshot_modules += [SCG/('src/silverstar_fccg/generator/'+name+'.py') for name in ('native_clock_tim','native_clock_probe','native_usb_config','native_no_heap')]
        snapshot_modules += list((SCG/'tests').glob('test_native*.py'))
        snapshot_modules += [SCG/('plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools/'+name+'.py') for name in ('check_native_ground','check_native_probe')]
    if prepared_candidate is not None:
        snapshot_modules += [p for p in (SCG/'src/silverstar_fccg').rglob('*.py') if p.is_file()]
        snapshot_modules += list((SCG/'tests').glob('test_usb*.py'))
    snapshot_modules=list(dict.fromkeys(snapshot_modules))
    (output/"source-snapshot.json").write_text(json.dumps({
        "source_commit":subprocess.check_output(["git","-C",str(SCG),"rev-parse","HEAD"],text=True).strip(),
        "dirty_diff":subprocess.check_output(["git","-C",str(SCG),"diff","--binary"],text=True),
        "modules":{str(p.relative_to(SCG)):{"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
                  "source":p.read_text(encoding="utf-8")} for p in snapshot_modules},
        "input_sha256":original_hashes,"facts":facts_json},indent=2),encoding="utf-8")
    tools=SCG/"plugins/builtin/silverstar_core_ground_0_1_0/payload/Tools"
    spec=importlib.util.spec_from_file_location("native_dependency_contract",tools/"ground_artifact_contract.py")
    dependencies=importlib.util.module_from_spec(spec); spec.loader.exec_module(dependencies)
    graph={**proof["build"],"sources":[native_prefix+p for p in proof["build"]["sources"]],
           "asm_sources":[native_prefix+p for p in proof["build"]["asm_sources"]],
           "include_dirs":[native_prefix+p for p in proof["build"]["include_dirs"]],
           "required_irq_handlers":proof["required_irq_handlers"],"linker_script":native_prefix+proof["build"]["linker_script"]}
    experiments={}
    experimental_files={}
    if prepared_candidate is not None:
        from silverstar_fccg.project.model import ProjectModel_Load
        model=ProjectModel_Load(args.runtime_project)
        experimental_files,graph,records=prepared_files,prepared_graph,prepared_records
        experiments['c071_ground']=records
        experimental_files['candidate_config.ssproject']=args.runtime_project.read_bytes()
    elif timer_probe:
        experimental_files,graph,records=NativeTimerProbe_FilesRender(files,proof,hclk_hz=args.clock_hz,scg_root=SCG)
        experiments['native_timer_probe']=records
    elif args.runtime_project is not None:
        if args.clock_hz is None or args.reviewed_hal:
            raise ValueError('Private Ground candidate needs --clock-hz; HAL derivatives are included once')
        from silverstar_fccg.plugins.catalog import PluginCatalog
        from silverstar_fccg.project.model import ProjectModel_Load
        model=ProjectModel_Load(args.runtime_project)
        catalog=runtime_catalog
        if catalog is None:
            catalog=PluginCatalog(SCG/'plugins/builtin',SCG/'plugins/installed');catalog.Scan()
        experimental_files,graph,records=NativeGroundCandidate_Render(files,proof,inventory,model,catalog,hclk_hz=args.clock_hz)
        experiments['native_ground']=records
        experimental_files['candidate_config.ssproject']=args.runtime_project.read_bytes()
    elif args.reviewed_hal:
        derived,replacements,manifest=NativeHalDerivatives_Render(files,proof["build"]["sources"])
        experimental_files.update(derived)
        graph["sources"]=[replacements.get(p,p) for p in graph["sources"]]
        experiments["reviewed_hal"]=manifest
    if args.clock_hz is not None and args.runtime_project is None and not timer_probe:
        experiments["clock"]=NativeClockSourceContract_Validate(files,proof["build"]["sources"],hclk_hz=args.clock_hz)
        experimental_files.update(NativeClock_FilesRender(hclk_hz=args.clock_hz))
        api=SCG/"plugins/builtin/silverstar_platform_api/payload/Platform/Inc"
        for path in api.glob("*.h"):
            experimental_files["Platform/Inc/"+path.name]=path.read_bytes()
        core=SCG/"plugins/builtin/silverstar_core_0_1_0/payload"
        for path in ("Common/Inc/silverstar_assert.h","Common/Inc/silverstar_compiler.h","Common/Src/silverstar_assert.c"):
            experimental_files[path]=(core/path).read_bytes()
        from silverstar_fccg.generator.multi_target import _UserSection_Insert
        main=files[proof["cdc"]["owners"]["main.c"]].decode("utf-8-sig")
        main=_UserSection_Insert(main,"Includes",'#include "native_clock.h"\n#include "platform_time.h"',empty=True)
        main=_UserSection_Insert(main,"2","  if (PlatformTime_Init() != PLATFORM_OK) { Error_Handler(); }",empty=True)
        loop=re.findall(r"/\* USER CODE BEGIN 3 \*/(.*?)/\* USER CODE END 3 \*/",main,re.S)
        if len(loop)!=1 or loop[0].strip()!="}" or main.count("HAL_Init();")!=1:
            raise ValueError("Unreviewed native main clock probe hook")
        main=main.replace("HAL_Init();","if (HAL_Init() != HAL_OK) { Error_Handler(); }",1)
        main=main.replace("/* USER CODE BEGIN 3 */","/* USER CODE BEGIN 3 */\n    uint64_t now_us;\n    if (NativeClock_Read(&now_us) != NativeClockResult_Ok) { Error_Handler(); }",1)
        main_path="HardwareGenerated/ReviewedNativeEntry/Core/Src/main.c"
        experimental_files[main_path]=main.encode("utf-8")
        graph["sources"]=[main_path if p==NATIVE_PREFIX+proof["cdc"]["owners"]["main.c"] else p for p in graph["sources"]]
        graph["sources"].extend([p for p in experimental_files if p.startswith("Generated/") and p.endswith(".c")])
        graph["sources"].append("Common/Src/silverstar_assert.c")
        graph["include_dirs"].extend(["Generated/Inc","Platform/Inc","Common/Inc"])
    for path,content in experimental_files.items():
        dest=output/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
    compiler=args.toolchain_prefix+"gcc"
    environment=os.environ.copy()
    for name in ("CPATH","C_INCLUDE_PATH","CPLUS_INCLUDE_PATH","OBJC_INCLUDE_PATH","DEPENDENCIES_OUTPUT","SUNPRO_DEPENDENCIES","GCC_EXEC_PREFIX","COMPILER_PATH"):
        environment.pop(name,None)
    commands=[]
    warning_diagnostics=[]
    log=output/"commands.log"

    def run(command):
        result=subprocess.run(command,cwd=output,env=environment,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        with log.open("a",encoding="utf-8") as stream:
            stream.write(json.dumps(command)+"\n"+result.stdout+"\nEXIT "+str(result.returncode)+"\n")
        commands.append({"command":command,"exit":result.returncode})
        warning_diagnostics.extend(line for line in result.stdout.splitlines() if "warning:" in line)
        if result.returncode: raise ValueError("native validation command failed; see "+str(log))
        return result.stdout

    flags=[*graph["mcu_flags"],*["-I"+p for p in graph["include_dirs"]],*["-D"+d for d in graph["defines"]]]
    # Declarations must agree with actual headers, and the compiler must select
    # the expected Cortex/32-bit pointer ABI. This test source is never executed.
    core={"cortex-m0":0,"cortex-m0plus":0,"cortex-m3":3,"cortex-m4":4}[facts.core]
    tx_qualifier="const " if proof["spi_abi"]["tx_buffer_const"] else ""
    gpio_read_qualifier='const ' if proof.get('gpio_abi',{}).get('read_port_const',False) else ''
    fpu_probe='_Static_assert(__FPU_PRESENT == 1U, "independent FPU facts must match native CMSIS");' if facts.fpu else ''
    probe=output/"Generated/Src/native_abi_probe.c"; probe.parent.mkdir(parents=True,exist_ok=True)
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
GPIO_PinState HAL_GPIO_ReadPin({gpio_read_qualifier}GPIO_TypeDef *, uint16_t);
uint32_t HAL_GetTick(void);
uint8_t CDC_Transmit_FS(uint8_t *, uint16_t);
''',encoding="utf-8")
    graph["sources"].append("Generated/Src/native_abi_probe.c")
    if timer_probe:
        experimental_files['Generated/ground_source_graph.json']=json.dumps(graph,indent=2).encode('utf-8')
        experimental_files['Makefile']=NativeTimerProbe_MakeRender(graph,args.toolchain_prefix).encode()
        experimental_files['Generated/Src/native_abi_probe.c']=probe.read_bytes()
        records['compiled_owned_sha256']['Generated/Src/native_abi_probe.c']=hashlib.sha256(probe.read_bytes()).hexdigest()
        experimental_files['Generated/native_probe_contract.json']=json.dumps(records,indent=2).encode()
    if args.runtime_project is not None:
        # The validation ABI probe is part of the actual compiled graph. Keep
        # emitted Make and its machine-readable graph truthful about that scope.
        from types import SimpleNamespace
        from silverstar_fccg.generator.multi_target import _Makefile_Render
        experimental_files['Generated/ground_source_graph.json']=json.dumps(graph,indent=2).encode('utf-8')
        (output/'Generated/ground_source_graph.json').write_bytes(experimental_files['Generated/ground_source_graph.json'])
        candidate_make=_Makefile_Render(tuple(graph['sources']),tuple(graph['asm_sources']),tuple(graph['include_dirs']),
            tuple(graph['defines']),SimpleNamespace(**graph),model.ground_target.build.toolchain_prefix)
        candidate_make=candidate_make.replace('-Wl,--gc-sections,','-Wl,-u,_sbrk -Wl,--gc-sections,',1)
        checker='check_c071_candidate.py' if prepared_candidate is not None else 'check_native_ground.py'
        candidate_make=candidate_make.replace('$(PYTHON) Tools/check_ground.py architecture','$(PYTHON) Tools/'+checker)
        candidate_make=candidate_make.replace('$(PYTHON) Tools/check_ground.py host','$(PYTHON) Tools/'+checker+' host')
        candidate_make=candidate_make.replace('$(PYTHON) Tools/check_ground.py artifact','$(PYTHON) Tools/'+checker+' artifact')
        experimental_files['Makefile']=candidate_make.encode('utf-8')
        experimental_files['Generated/Src/native_abi_probe.c']=probe.read_bytes()
        records['compiled_owned_sha256']['Generated/Src/native_abi_probe.c']=hashlib.sha256(probe.read_bytes()).hexdigest()
        experimental_files['Generated/native_ground_contract.json']=json.dumps(records,indent=2).encode('utf-8')
        (output/'Generated/native_ground_contract.json').write_bytes(experimental_files['Generated/native_ground_contract.json'])
        (output/'Makefile').write_bytes(experimental_files['Makefile'])
    if timer_probe:
        for path,content in experimental_files.items():
            dest=output/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
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
                if source.startswith(("Generated/","Common/","Ground/","Devices/","Platform/")):common += ["-Wextra","-Wpedantic","-Werror",
                    "-Wconversion","-Wsign-conversion","-Wshadow","-Wundef","-Wformat=2",
                    "-Wdouble-promotion","-Wcast-align","-Wcast-qual","-Wstrict-prototypes","-Wmissing-prototypes","-Wswitch-enum","-Wvla"]
                run([*common,"-MD","-MP","-MF",rel.removesuffix(".o")+".d","-MT",rel,"-S",source,"-o",asm])
                dependencies.AssemblerSource_Prepare(output,graph,source,build_dir)
                NativeAssemblyDirectives_Validate((output/asm).read_text(encoding="utf-8"),core=facts.core,fpu=facts.fpu,
                    reviewed_assert_trap=(source=="Common/Src/silverstar_assert.c" and
                        (output/source).read_bytes()==(SCG/"plugins/builtin/silverstar_core_0_1_0/payload/Common/Src/silverstar_assert.c").read_bytes()))
                run([compiler,*graph["mcu_flags"],"-x","assembler","-Wa,--MD,"+rel.removesuffix(".o")+".gas.d","-c",asm,"-o",rel])
                NativeArmAttributes_Validate(run([args.toolchain_prefix+"readelf","-A",rel]),
                    core=facts.core,fpu=facts.fpu,hard_float="-mfloat-abi=hard" in graph["mcu_flags"])
                dependencies.DependencyClosure_Validate(output,graph,compiler,build_dir=build_dir,source=source)
                objects.append(rel)
            for source in graph["asm_sources"]:
                obj=output/build_dir/Path(source).with_suffix(".o");obj.parent.mkdir(parents=True,exist_ok=True)
                rel=obj.relative_to(output).as_posix()
                run([compiler,*flags,"-save-temps=obj","-MD","-MP","-MF",rel.removesuffix(".o")+".d","-MT",rel,"-Wa,--MD,"+rel.removesuffix(".o")+".gas.d","-x","assembler-with-cpp","-c",source,"-o",rel])
                NativeArmAttributes_Validate(run([args.toolchain_prefix+"readelf","-A",rel]),
                    core=facts.core,fpu=facts.fpu,hard_float="-mfloat-abi=hard" in graph["mcu_flags"],assembly=True)
                dependencies.DependencyClosure_Validate(output,graph,compiler,build_dir=build_dir,source=source)
                objects.append(rel)
            elf=build_dir+"/native.elf"
            run([compiler,*objects,*graph["mcu_flags"],*["-Wl,-u,"+symbol for symbol in graph.get('required_link_symbols',[])],"-Wl,--gc-sections,-Map="+build_dir+"/native.map","-T"+graph["linker_script"],"-specs=nano.specs","-lc","-lm","-lnosys","-o",elf])
            NativeArmAttributes_Validate(run([args.toolchain_prefix+"readelf","-A",elf]),
                core=facts.core,fpu=facts.fpu,hard_float="-mfloat-abi=hard" in graph["mcu_flags"])
            symbols=run([args.toolchain_prefix+"nm","-n",elf])
            vector=build_dir+"/vectors.bin"
            run([args.toolchain_prefix+"objcopy","--dump-section",".isr_vector="+vector,elf])
            vector_bytes=(output/vector).read_bytes()
            dependencies.InterruptVectors_Validate(output,graph,symbols,vector_bytes)
            NativeIndependentVectors_Validate(vector_bytes,symbols,proof["independent_irq_slots"])
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
            if (root/p).read_bytes()!=b or (output/native_prefix/p).read_bytes()!=b:raise ValueError("native inputs changed during validation")
        status="NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED"
        if warning_diagnostics:
            raise ValueError("Native warning diagnostics require independent review; strict no-warning acceptance FAILED")
    except Exception as error:
        status="FAILED"; failure=str(error)
        raise
    finally:
        receipt={"status":status,"started_utc":started,"finished_utc":datetime.now(timezone.utc).isoformat(),
          "validation_scope":"PRIVATE_NATIVE_TIM1_CLOCK_HAL_USB_CONFIG_PROBE" if timer_probe else
              ("PRIVATE_NATIVE_GROUND_RUNTIME_CANDIDATE" if args.runtime_project is not None else "PRIVATE_NATIVE_SOURCE_ABI_COMPILE_PROBE"),
          "runtime_model_sha256":hashlib.sha256(json.dumps(model.Dictionary_Get(),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode('utf-8')).hexdigest() if args.runtime_project is not None else None,
          "snapshot_root":str(root),
          "runtime_project":str(args.runtime_project.resolve()) if args.runtime_project is not None else None,
          "runtime_project_sha256":hashlib.sha256(args.runtime_project.read_bytes()).hexdigest() if args.runtime_project is not None and args.runtime_project.is_file() else None,
          "source_commit":subprocess.check_output(["git","-C",str(SCG),"rev-parse","HEAD"],text=True).strip(),
          "auditable_dirty_diff":subprocess.check_output(["git","-C",str(SCG),"diff","--binary"],text=True),
          "new_module_sha256":hashlib.sha256((SCG/"src/silverstar_fccg/hardware/native_classic_cdc.py").read_bytes()).hexdigest(),
          "validation_engine_path":str(Path(__file__).relative_to(SCG)),
          "validation_script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "validation_script_source":Path(__file__).read_text(encoding="utf-8"),
          "import_module_source":(SCG/"src/silverstar_fccg/hardware/native_classic_cdc.py").read_text(encoding="utf-8"),
          "machine_contract_source":(SCG/"src/silverstar_fccg/hardware/native_machine_contract.py").read_text(encoding="utf-8"),
          "machine_contract_sha256":hashlib.sha256((SCG/"src/silverstar_fccg/hardware/native_machine_contract.py").read_bytes()).hexdigest(),
          "experimental_modules":{p:{"sha256":hashlib.sha256((SCG/p).read_bytes()).hexdigest(),"source":(SCG/p).read_text(encoding="utf-8")}
              for p in ("src/silverstar_fccg/generator/native_hal.py","src/silverstar_fccg/generator/native_clock.py",
                        "src/silverstar_fccg/generator/native_platform.py","src/silverstar_fccg/generator/native_runtime.py",
                        "src/silverstar_fccg/generator/native_ground.py","src/silverstar_fccg/generator/native_no_heap.py",
                        "src/silverstar_fccg/generator/native_pc.py","src/silverstar_fccg/generator/native_usb_data.py",
                        "src/silverstar_fccg/generator/native_radio.py","src/silverstar_fccg/generator/native_clock_tim.py",
                        "src/silverstar_fccg/generator/native_clock_probe.py","src/silverstar_fccg/generator/native_usb_config.py",
                        "src/silverstar_fccg/generator/native_usb_indexed.py")},
          "experimental_files_sha256":{p:hashlib.sha256(b).hexdigest() for p,b in experimental_files.items()},
          "experiments":experiments,
          "toolchain_version":locals().get("version"),
          "warning_diagnostics":warning_diagnostics,
          "no_warning_gate":"FAIL" if warning_diagnostics else "NO_RECORDED_WARNING",
          "facts":facts_json,"contract":proof,"commands":commands,"graph":graph,"input_sha256":original_hashes,
          "output_artifact_sha256":{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob("*") if p.is_file() and p.suffix in {".elf",".map",".o",".su",".d",".s",".bin"}},
          "failure":locals().get("failure"),"limits":"PRIVATE CANDIDATE ONLY. NOT PROVEN: manual critical-contract acceptance, complete EP0/async lifecycle, physical memory authority beyond caller review, MCU tick/radio timing, whole-program stack/WCET and hardware. Source/ABI closure and private generated Ground compilation are recorded only for this snapshot. Normal native generation remains blocked; no board access."}
        (output/"receipt.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(status,output,flush=True)
    return receipt


