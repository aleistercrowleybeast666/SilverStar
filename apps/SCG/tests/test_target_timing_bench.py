from __future__ import annotations

import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.source_export import SourcePackage_Export
from silverstar_fccg.core.workspace import WorkspacePolicy

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "plugins/builtin/silverstar_core_0_1_0/payload"
BENCH_FILES = tuple("Tests/Target/" + name for name in (
    "timing_bench.c", "timing_bench.h", "timing_bench_f407.c", "timing_bench_f407.h",
    "timing_bench_example.c", "timing_bench_example.h", "TIMING_BENCH.md"))


@pytest.fixture(scope="module")
def timing_project(tmp_path_factory):
    project = tmp_path_factory.mktemp("target_timing")
    service = FccgService(ROOT)
    service.Project_Save(service.ReferenceProject_Create("TimingBench"), project, confirm_dangerous=True)
    return project


def _GraphValues_Get(project: Path, name: str) -> list[str]:
    text = (project / "Generated/project_sources.mk").read_text(encoding="utf-8")
    section = re.search(r"(?ms)^" + name + r" \+= \\\n(.*?)(?=\n\n|\Z)", text)
    assert section, name
    return [line.strip().rstrip("\\").strip() for line in section[1].splitlines() if line.strip()]


@pytest.mark.parametrize("optimization", ["-O2", "-Og"])
def test_real_timing_core_wrap_owner_rejection_and_saturation(tmp_path, optimization):
    compiler = shutil.which("gcc")
    assert compiler, "Host GCC is required for the real timing core test"
    executable = tmp_path / "timing.exe"
    command = [compiler, "-std=c11", optimization, "-Wall", "-Wextra", "-Werror", "-Wpedantic",
               "-Wconversion", "-Wsign-conversion", "-I" + str(CORE / "Tests/Target"),
               "-I" + str(CORE / "Tests/Host"), str(CORE / "Tests/Target/timing_bench.c"),
               str(CORE / "Tests/Host/test_timing_bench.c"), "-o", str(executable)]
    environment = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    compiled = subprocess.run(command, capture_output=True, text=True, env=environment)
    (tmp_path / "compile.log").write_text("COMMAND " + subprocess.list2cmdline(command) + "\n" +
                                          compiled.stdout + compiled.stderr, encoding="utf-8")
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    run = subprocess.run([str(executable)], capture_output=True, text=True, env=environment)
    (tmp_path / "host.log").write_text(run.stdout + run.stderr, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    counts = re.search(r"timing_bench: (\d+) checks, 0 failures", run.stdout)
    assert counts and int(counts[1]) > 2000


@pytest.mark.parametrize("optimization", ["-O2", "-Og"])
def test_real_f407_cmsis_adapter_and_application_example_compile(timing_project, tmp_path, optimization):
    compiler = shutil.which("arm-none-eabi-gcc")
    objdump = shutil.which("arm-none-eabi-objdump")
    assert compiler and objdump, "Real Cortex-M4 compiler and objdump are required"
    project = timing_project
    command = [compiler, "-std=c11", optimization, "-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16",
               "-mfloat-abi=hard", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-Wconversion",
               "-Wsign-conversion", "-Wshadow", "-Wundef", "-Wformat=2", "-Wdouble-promotion",
               "-Wcast-align", "-Wcast-qual", "-Wstrict-prototypes", "-Wmissing-prototypes",
               "-Wswitch-enum", "-Wvla", "-fstack-usage", "-I" + str(project / "Tests/Target")]
    command += ["-D" + value for value in _GraphValues_Get(project, "C_DEFS")]
    command += ["-I" + str(project / value) for value in _GraphValues_Get(project, "C_INCLUDES")]
    for value in _GraphValues_Get(project, "TARGET_FORCED_INCLUDES"):
        command += ["-include", str(project / value)]
    environment = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    for name in ("timing_bench", "timing_bench_f407", "timing_bench_example"):
        output = tmp_path / (name + ".o")
        run = subprocess.run(command + ["-c", str(project / "Tests/Target" / (name + ".c")),
                             "-o", str(output)], capture_output=True, text=True, env=environment)
        (tmp_path / (name + ".log")).write_text("COMMAND " + subprocess.list2cmdline(run.args) + "\n" +
                                               run.stdout + run.stderr, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        assert output.is_file() and output.with_suffix(".su").is_file()
    assembly = subprocess.run([objdump, "-dr", str(tmp_path / "timing_bench_f407.o")],
                              capture_output=True, text=True, check=True).stdout
    (tmp_path / "timing_bench_f407.disassembly.txt").write_text(assembly, encoding="utf-8")
    assert re.search(r"\bmsr\s+PRIMASK", assembly, re.IGNORECASE)
    assert re.search(r"\bcpsid\s+i", assembly, re.IGNORECASE)
    for symbol in ("TimingBench_ContextValidate", "SystemTaskStack_SnapshotGet", "LoggerBus_DiagnosticsGet",
                   "LoggerTask_DiagnosticsGet", "SystemTime_GetMonotonicUsFromIsr"):
        assert symbol in assembly


def test_bench_is_absent_from_default_graph_and_preserved_by_real_export(timing_project, tmp_path):
    source_graph = (timing_project / "Generated/project_sources.mk").read_text(encoding="utf-8")
    assert "Tests/Target/" not in source_graph and "timing_bench" not in source_graph
    fixture = tmp_path / "source"
    policy = WorkspacePolicy(ROOT)
    for relative in BENCH_FILES:
        assert (timing_project / relative).read_bytes() == (CORE / relative).read_bytes()
        package_path = Path("plugins/builtin/silverstar_core_0_1_0/payload") / relative
        policy.File_Copy(CORE / relative, fixture / package_path)
    destination = tmp_path / "source.zip"
    SourcePackage_Export(fixture, destination)
    with zipfile.ZipFile(destination) as archive:
        for relative in BENCH_FILES:
            name = "SilverStar_FCCG/plugins/builtin/silverstar_core_0_1_0/payload/" + relative
            assert archive.read(name) == (CORE / relative).read_bytes()


def test_timing_sources_survive_reference_reimport(monkeypatch):
    import tools.import_reference_components as importer

    monkeypatch.setattr(importer, "_ManifestValues_Get", lambda *_: [])
    components = {item["manifest"]["id"]: item for item in importer._Components_Get(
        Path("unused"), {"commit": "fixture", "snapshot_digest": "fixture"})}
    owned = components["silverstar.core.0_1_0"]["fccg_owned_files"]
    for relative in (*BENCH_FILES, "Tests/Host/test_timing_bench.c"):
        assert (ROOT / owned[relative]).read_bytes() == (CORE / relative).read_bytes()
