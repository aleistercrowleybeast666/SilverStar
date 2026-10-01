"""Actual ARM links with synthetic capacities/objects; no board evidence."""
from dataclasses import replace
import importlib.util
import json
import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest

from silverstar_fccg.build.runner import BuildAction, BuildRunner
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.artifact_memory import ArtifactMemorySummary_Encode
from silverstar_fccg.ui.pages.build import BuildPage
from silverstar_fccg.core.i18n import Translator


PLUGINS = Path(__file__).resolve().parents[1] / "plugins/builtin"
TOOL = PLUGINS / "silverstar_core_0_1_0/payload/Tools/auto_memory_layout.py"
MCU = PLUGINS / "silverstar_mcu_stm32f407vet6/payload"
API = PLUGINS / "silverstar_platform_api/payload/Platform/Inc"
spec = importlib.util.spec_from_file_location("auto_memory_layout", TOOL)
auto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto)


def test_old_configuration_defaults_to_legacy_and_auto_round_trip():
    model = ReferenceProject_Create("Layout")
    old = model.Dictionary_Get()
    del old["build"]["memory_layout"]
    assert ProjectModel_Parse(old).build.memory_layout == "legacy"
    model.build = replace(model.build, memory_layout="auto")
    assert ProjectModel_Parse(model.Dictionary_Get()).build.memory_layout == "auto"
    old["build"]["memory_layout"] = "dma"
    with pytest.raises(ValueError, match="memory_layout"):
        ProjectModel_Parse(old)


def test_gui_selection_is_explicit_and_runner_carries_it(qapp, tmp_path):
    page = BuildPage(Translator("en_US"))
    assert page.memory_layout_combo.currentData() == "legacy"
    selected = []
    page.memoryLayoutChanged.connect(selected.append)
    page.MemoryLayout_Set("auto")
    assert selected == []
    page.memory_layout_combo.setCurrentIndex(page.memory_layout_combo.findData("legacy"))
    assert selected == ["legacy"]
    model = ReferenceProject_Create("Layout")
    runner = BuildRunner(WorkspacePolicy(tmp_path))
    assert not any(item.startswith("MEMORY_LAYOUT=") for item in runner.Command_Get(model, BuildAction.BUILD))
    model.build = replace(model.build, memory_layout="auto")
    assert "MEMORY_LAYOUT=auto" in runner.Command_Get(model, BuildAction.BUILD)


@pytest.fixture
def arm_fixture(tmp_path):
    cc, objdump = shutil.which("arm-none-eabi-gcc"), shutil.which("arm-none-eabi-objdump")
    if not cc or not objdump:
        pytest.skip("ARM toolchain unavailable")
    root = tmp_path / "fixture"
    root.mkdir()
    owner = root / "Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.o"
    owner.parent.mkdir(parents=True)
    source = owner.with_suffix(".c")
    source.write_text('''#include "platform_memory.h"
static PLATFORM_ESKF_WORK_BSS unsigned char s_work[24000];
static PLATFORM_ESKF_HISTORY_BSS unsigned char s_history[1024];
static PLATFORM_ESKF_WINDOW_BSS unsigned char s_eskf_window[184];
static PLATFORM_CPU_FAST_BSS unsigned char fixed_cpu[48000];
static PLATFORM_DMA_ACCESSIBLE unsigned char dma[80000];
static PLATFORM_CPU_FAST_DATA unsigned initialized = 0x12345678U;
void SystemInit(void); void __libc_init_array(void); int main(void);
void SystemInit(void) {} void __libc_init_array(void) {}
int main(void) { return s_work[0] + s_history[0] + s_eskf_window[0] +
    fixed_cpu[0] + dma[0] + (int)initialized; }
''', encoding="utf-8")
    base = [cc, "-mcpu=cortex-m4", "-mthumb", "-Wall", "-Wextra", "-Werror", "-std=c11", "-I" + str(API),
            "-include", str(MCU / "Targets/SilverStar_F407/Inc/platform_memory_target.h")]
    result = subprocess.run([*base, "-DSILVERSTAR_MEMORY_LAYOUT_AUTO=1", "-c", str(source), "-o", str(owner)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    (root / "SilverStar.ssproject").write_text(json.dumps({"component_provenance": {
        "silverstar.algorithm.estimator.eskf15": {"files": {
            "Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c": hashlib.sha256(source.read_bytes()).hexdigest()
        }}
    }}), encoding="utf-8")
    startup = root / "startup.o"
    subprocess.run([cc, "-mcpu=cortex-m4", "-mthumb", "-c", str(MCU / "startup_stm32f407xx.s"), "-o", str(startup)], check=True)
    script = root / "target.ld"
    script.write_bytes((MCU / "STM32F407XX_FLASH.ld").read_bytes())
    return root, cc, objdump, owner, startup, script, source, base


def link_fixture(fixture, *, name="auto", script=None):
    root, cc, objdump, owner, startup, default_script, _, _ = fixture
    output = root / name / "test.elf"
    args = type("Args", (), dict(linker=str(script or default_script), output=str(output), compiler=cc,
                               objdump=objdump, project=str(root), command=[str(owner), str(startup), "-mcpu=cortex-m4", "-mthumb", "-nostdlib",
                                                        "-Wl,-Map=" + str(output.with_suffix(".map"))]))()
    auto.Layout_Link(args)
    return output, json.loads((output.parent / "memory_layout/decision.json").read_text())


def test_actual_f407_links_overflow_relief_determinism_alignment_and_startup(arm_fixture, capsys):
    elf, report = link_fixture(arm_fixture)
    decision_output = capsys.readouterr().out
    artifact = "FLASH used=20 remaining=80 capacity=100\nmain SRAM used=70 remaining=30 capacity=100\nCCMRAM used=80 remaining=20 capacity=100\n"
    assert ArtifactMemorySummary_Encode(decision_output + artifact)
    assert any(item["exit_code"] != 0 for item in report["attempts"])  # pre-layout CCM overflow
    assert report["assignment"]["eskf_work"] == "RAM"
    assert len(report["attempts"]) == 8
    for group in report["groups"].values():
        assert group["address"] % 8 == 0
        assert group["zero_bounds"] in [["_sbss", "_ebss"], ["_sccmram_bss", "_eccmram_bss"]]
    _, second = link_fixture(arm_fixture)
    assert report["assignment"] == second["assignment"] and report["elf_sha256"] == second["elf_sha256"]
    objdump = arm_fixture[2]
    sections = auto.Tool_Run([objdump, "-h", str(elf)])
    assert ".ccmram_data" in sections and ".ccmram_bss" in sections
    initialized = auto.Tool_Run([objdump, "-s", "-j", ".ccmram_data", str(elf)])
    assert "78563412" in initialized  # actual linked load image preserves data
    startup = (MCU / "startup_stm32f407xx.s").read_text()
    for symbol in ("_siccmram_data", "_sccmram_data", "_eccmram_data", "_sccmram_bss", "_eccmram_bss", "_sbss", "_ebss"):
        assert "=" + symbol in startup
    # BSS has no load contents; target startup loops cover the actual bounds.
    dump = auto.Tool_Run([objdump, "-h", str(elf)])
    assert "CONTENTS" not in dump.split(".ccmram_bss", 1)[1].splitlines()[1]


def test_no_ccm_uses_real_sram_and_insufficient_capacity_really_fails(arm_fixture):
    root, _, _, _, _, script, _, _ = arm_fixture
    text = script.read_text(encoding="utf-8").replace("CCMRAM (xrw)      : ORIGIN = 0x10000000, LENGTH = 64K", "")
    # This is a synthetic no-CCM target, not an F412 board test. Preserve both
    # original copy/zero intervals while mapping their physical storage to RAM.
    text = text.replace("} >CCMRAM", "} >RAM").replace("LENGTH = 128K", "LENGTH = 256K")
    no_ccm = root / "no_ccm.ld"
    no_ccm.write_text(text, encoding="utf-8")
    _, report = link_fixture(arm_fixture, name="no_ccm", script=no_ccm)
    assert set(report["regions"]) == {"RAM"} and len(report["attempts"]) == 1
    assert set(report["assignment"].values()) == {"RAM"}
    no_ccm.write_text(text.replace("LENGTH = 256K", "LENGTH = 64K"), encoding="utf-8")
    with pytest.raises(ValueError, match="No candidate linked"):
        link_fixture(arm_fixture, name="too_small", script=no_ccm)
    assert not (root / "too_small/test.elf").exists()
    log = (root / "too_small/memory_layout/candidate_00.log").read_text()
    assert "overflowed" in log or "will not fit" in log


@pytest.mark.parametrize("change", ["dma", "initialized", "alignment", "wrong_owner"])
def test_unreviewed_dma_data_and_bad_alignment_are_rejected(arm_fixture, change):
    root, _, objdump, owner, _, _, source, base = arm_fixture
    text = source.read_text()
    if change == "dma":
        text = text.replace("s_work", "s_uart1_rx_dma")
    elif change == "initialized":
        text = text.replace("s_work[24000];", "s_work[24000] = {1};")
    elif change == "alignment":
        text = text.replace("PLATFORM_ESKF_WORK_BSS", '__attribute__((section(".bss.silverstar_auto_eskf_work"), aligned(1)))')
    source.write_text(text)
    compile_result = subprocess.run([*base, "-DSILVERSTAR_MEMORY_LAYOUT_AUTO=1", "-c", str(source), "-o", str(owner)], capture_output=True, text=True)
    if change == "initialized":
        assert compile_result.returncode != 0  # GNU assembler prohibits nonzero initialization in .bss
        return
    assert compile_result.returncode == 0, compile_result.stderr
    if change == "wrong_owner":
        wrong = root / "uart_dma.o"
        shutil.copy2(owner, wrong)
        owner = wrong
    with pytest.raises(ValueError, match="private BSS|wrong or duplicate"):
        auto.Groups_Inspect(objdump, [str(owner)])


def test_preserved_linker_missing_hooks_fails_closed(arm_fixture):
    text = arm_fixture[5].read_text(encoding="utf-8").replace("/* SILVERSTAR_AUTO_CCM_BSS */", "")
    with pytest.raises(ValueError, match="fresh project"):
        auto.Script_Render(text, {"eskf_work": "RAM"}, auto.Regions_Parse(text))


def test_preserved_user_source_cannot_inherit_cpu_only_proof(arm_fixture):
    arm_fixture[6].write_text(arm_fixture[6].read_text() + "\n/* user edit, requires CPU/DMA re-review */\n")
    with pytest.raises(ValueError, match="source proof"):
        link_fixture(arm_fixture, name="edited_source")


def test_f413_alias_cannot_be_counted_as_an_independent_ccm_bank():
    script = """MEMORY {
RAM (xrw) : ORIGIN = 0x20000000, LENGTH = 320K
CCMRAM (xrw) : ORIGIN = 0x10000000, LENGTH = 64K
FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 1024K
}"""
    with pytest.raises(ValueError, match="alias"):
        auto.Regions_Parse(script)
