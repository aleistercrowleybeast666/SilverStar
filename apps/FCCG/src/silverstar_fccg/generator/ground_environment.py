"""Ground IDE metadata derived from the existing Make source graph."""
from __future__ import annotations

from dataclasses import replace

import yaml

from silverstar_fccg.generator.render import (
    _Eide_Render, _VsCodeExtensions_Render, _VsCodeSettings_Render,
)


def GroundEnvironmentFiles_Render(model, catalog, graph, sources, includes, defines):
    environment = catalog.Component_Get("silverstar.environment.vscode_eide_gcc")
    # Explicit virtual files prevent EIDE directory discovery from adding vendor
    # sources that the existing Ground Make graph does not compile.
    ide_graph = replace(
        graph, sources=sources, include_dirs=includes, defines=defines,
        virtual_sources=sources, exclude_sources=(),
    )
    document = yaml.safe_load(_Eide_Render(model, ide_graph, environment))
    document["srcDirs"] = []
    document["name"] = model.identity.name + "_Ground"
    document["deviceName"] = model.hardware.mcu or catalog.Component_Get(model.mcu).metadata.get("mcu_model")
    profile = catalog.Component_Get(model.mcu).platform.build_target_profile
    document["outDir"] = "build/FCCG/" + profile + "/EIDE"
    cpu = next((flag.split("=", 1)[1] for flag in graph.mcu_flags if flag.startswith("-mcpu=")), None)
    if cpu is None or not cpu.startswith("cortex-m"):
        raise ValueError("Ground EIDE requires an explicit Cortex-M CPU from its MCU graph")
    fpu = next((flag.split("=", 1)[1] for flag in graph.mcu_flags if flag.startswith("-mfpu=")), None)
    float_abi = next((flag.split("=", 1)[1] for flag in graph.mcu_flags if flag.startswith("-mfloat-abi=")), None)
    family = str(catalog.Component_Get(model.mcu).metadata.get("platform_family_id", ""))
    openocd = {"silverstar.mcu_family.stm32f1": "stm32f1x",
               "silverstar.mcu_family.stm32f4": "stm32f4x",
               "silverstar.mcu_family.stm32h7": "stm32h7x"}.get(family)
    first_party = ("Common/", "Devices/", "Generated/", "Ground/", "Platform/")
    strict = "-Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wundef -Wformat=2 -Wdouble-promotion -Wcast-align -Wcast-qual -Wstrict-prototypes -Wmissing-prototypes -Wswitch-enum -Wvla"
    vendor = "-Wall -Werror=implicit-function-declaration -Werror=incompatible-pointer-types -Werror=return-type"
    source_options = {source: strict if source.startswith(first_party) else vendor for source in sources}
    for target in document["targets"].values():
        target["cppPreprocessAttrs"]["defineList"] = list(defines)
        configuration = target["toolchainConfigMap"]["GCC"]
        configuration["cpuType"] = "Cortex-M" + cpu.removeprefix("cortex-m")
        configuration["floatingPointHardware"] = "none" if fpu is None else "single" if "sp" in fpu else "double"
        configuration["scatterFilePath"] = graph.linker_script
        options = configuration["options"]
        options["global"]["misc-control"] = " ".join(graph.mcu_flags)
        options["global"]["toolPrefix"] = model.build.toolchain_prefix or graph.toolchain_prefix
        # EIDE's FPU ABI selector accepts hard/softfp only. No-FPU CPUs do not
        # use it; the exact MCU graph flags above still explicitly select soft.
        if fpu is None:
            options["global"].pop("$float-abi-type", None)
        else:
            options["global"]["$float-abi-type"] = float_abi
        options["global"]["output-debug-info"] = "disable"
        options["global"]["not-use-syscalls"] = False
        options["c/cpp-compiler"]["optimization"] = "level-size"
        options["c/cpp-compiler"]["C_FLAGS"] = "-fstack-usage -Wvla -Werror=vla"
        options["linker"]["LIB_FLAGS"] = "-lc -lm -lnosys"
        options["linker"]["$outputTaskExcludes"] = []
        if openocd is not None:
            target["uploadConfigMap"]["OpenOCD"]["target"] = openocd
        else:
            # Do not advertise the Flight template's stm32f4x for another MCU.
            target["uploadConfigMap"].pop("OpenOCD", None)
            target["uploader"] = "STLink"
    file_options = {"version": "2.1", "options": {
        name: {"files": source_options, "virtualPathFiles": {}} for name in ("Release", "Debug")}}
    return {
        ".eide/eide.yml": ("# Ground IDE metadata; existing Make source graph is authoritative.\n" + yaml.safe_dump(document,sort_keys=False,allow_unicode=True)).encode("utf8"),
        ".eide/files.options.yml": yaml.safe_dump(file_options,sort_keys=False).encode("utf8"),
        ".vscode/settings.json": _VsCodeSettings_Render(environment).encode("utf8"),
        ".vscode/extensions.json": _VsCodeExtensions_Render(environment).encode("utf8"),
    }
