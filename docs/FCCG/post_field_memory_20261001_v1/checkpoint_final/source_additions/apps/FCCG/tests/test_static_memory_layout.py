"""Experimental placement must be explicit, isolated, and fail closed."""
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess

import pytest

from silverstar_fccg.generator.render import _Makefile_Render
from silverstar_fccg.project.reference import ReferenceProject_Create


@pytest.fixture
def make_project(tmp_path):
    make = shutil.which("mingw32-make") or shutil.which("make")
    if make is None:
        pytest.skip("GNU Make unavailable")

    def create(*, target="SilverStar_F407", eskf=True):
        model = ReferenceProject_Create("MemoryLayout")
        model.build = replace(model.build, target_profile=target)
        (tmp_path / "Makefile").write_text(_Makefile_Render(model), encoding="utf-8")
        directory = tmp_path / "Targets" / target
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "target.mk").write_text("", encoding="utf-8")
        (tmp_path / "Generated").mkdir(exist_ok=True)
        source = "Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c" if eskf else "APP/Src/estimator_task.c"
        (tmp_path / "Generated/project_sources.mk").write_text(f"C_SOURCES += {source}\n", encoding="utf-8")

        def run(*args):
            return subprocess.run([make, "-np", "list-build-config", *args], cwd=tmp_path,
                                  capture_output=True, text=True, timeout=15)
        return run
    return create


@pytest.mark.parametrize("value", ["bad", "legacy eskf_window_sram", ""])
def test_invalid_layout_is_rejected(make_project, value):
    result = make_project()(f"MEMORY_LAYOUT={value}")
    assert result.returncode != 0
    assert "Unsupported MEMORY_LAYOUT" in result.stderr


@pytest.mark.parametrize("target,eskf", [("SilverStar_F103", True), ("SilverStar_F407", False)])
def test_unsupported_layout_is_rejected(make_project, target, eskf):
    result = make_project(target=target, eskf=eskf)("MEMORY_LAYOUT=eskf_window_sram")
    assert result.returncode != 0
    assert "requires SilverStar_F407 and the ESKF15 backend" in result.stderr


@pytest.mark.parametrize("analyze", [False, True])
def test_layout_outputs_are_isolated_and_default_is_legacy(make_project, analyze):
    run = make_project()
    args = ["ANALYZE=1"] if analyze else []
    prefix = "build/FCCG/SilverStar_F407/" + ("StaticAnalysis/" if analyze else "") + "Release"
    legacy = run(*args)
    experimental = run(*args, "MEMORY_LAYOUT=eskf_window_sram")
    assert legacy.returncode == experimental.returncode == 0
    assert f"BUILD_ROOT := {prefix}\n" in legacy.stdout
    assert f"BUILD_ROOT := {prefix}/eskf_window_sram\n" in experimental.stdout
    assert "C_DEFS := SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM=1" in experimental.stdout
    assert "SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM=1" not in legacy.stdout


def test_legacy_artifact_recipe_retains_old_script_interface(make_project):
    run = make_project()
    for layout in ("legacy", "eskf_window_sram"):
        result = run("-o", "all", "artifact-check", f"MEMORY_LAYOUT={layout}")
        assert result.returncode == 0, result.stderr
        recipe = next(line for line in result.stdout.splitlines() if line.startswith("powershell -NoProfile"))
        assert ("-MemoryLayout" in recipe) == (layout != "legacy")


@pytest.mark.parametrize("layout,section", [(0, ".ccmram_bss"), (1, ".bss.silverstar_eskf_window")])
def test_arm_window_section_and_alignment(tmp_path, layout, section):
    compiler, objdump = shutil.which("arm-none-eabi-gcc"), shutil.which("arm-none-eabi-objdump")
    if compiler is None or objdump is None:
        pytest.skip("ARM toolchain unavailable")
    plugins = Path(__file__).resolve().parents[1] / "plugins/builtin"
    target = plugins / "silverstar_mcu_stm32f407vet6/payload/Targets/SilverStar_F407/Inc/platform_memory_target.h"
    api = plugins / "silverstar_platform_api/payload/Platform/Inc"
    eskf = plugins / "silverstar_algorithm_common/payload/Algorithm/Common/Inc"
    source = tmp_path / "window.c"
    source.write_text('#include "platform_memory.h"\n#include "navigation_quality.h"\n'
                      'static PLATFORM_ESKF_WINDOW_BSS NavigationWindowContext s_eskf_window;\n'
                      'void *Window_Get(void);\nvoid *Window_Get(void) { return &s_eskf_window; }\n', encoding="utf-8")
    output = tmp_path / "window.o"
    result = subprocess.run([compiler, "-mcpu=cortex-m4", "-mthumb", "-std=c11", "-Wall", "-Wextra", "-Werror",
                             "-include", str(target), f"-DSILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM={layout}",
                             "-I" + str(api), "-I" + str(eskf), "-c", str(source), "-o", str(output)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    sections = subprocess.check_output([objdump, "-h", str(output)], text=True)
    symbols = subprocess.check_output([objdump, "-t", str(output)], text=True)
    assert section in sections and "2**3" in sections
    assert f"{section}\t000000b8 s_eskf_window" in symbols


@pytest.mark.parametrize("layout,old_target", [(2, False), (1, True)])
def test_invalid_or_preserved_target_fails_closed(tmp_path, layout, old_target):
    compiler = shutil.which("arm-none-eabi-gcc")
    if compiler is None:
        pytest.skip("ARM toolchain unavailable")
    root = Path(__file__).resolve().parents[3]
    relative = "apps/FCCG/plugins/builtin/silverstar_mcu_stm32f407vet6/payload/Targets/SilverStar_F407/Inc/platform_memory_target.h"
    target = root / relative
    if old_target:
        target = tmp_path / "old_target.h"
        target.write_bytes(subprocess.check_output(["git", "show", f"d410f4a7254f0433e91a22adb237b2944939fd99:{relative}"], cwd=root))
    api = root / "apps/FCCG/plugins/builtin/silverstar_platform_api/payload/Platform/Inc"
    source = tmp_path / "invalid.c"
    source.write_text('#include "platform_memory.h"\n', encoding="utf-8")
    result = subprocess.run([compiler, "-mcpu=cortex-m4", "-mthumb", "-include", str(target),
                             f"-DSILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM={layout}", "-I" + str(api),
                             "-c", str(source), "-o", str(tmp_path / "invalid.o")],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert ("does not support" if old_target else "Invalid ESKF consistency window") in result.stderr
