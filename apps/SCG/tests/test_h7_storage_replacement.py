"""Preserved input identity and real owning H7 HAL boundary behavior."""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from silverstar_fccg.generator.h7_storage import (
    OWNER, PREFIX, REQUIRED, REPLACEMENTS, H7StorageInputs_Validate, H7StorageSources_Replace,
)


def Context_Create():
    files = {path: (path + "\n").encode() for path in REQUIRED}
    contract = {"schema_id": "silverstar.h7-storage-replacement/1", "replacements": dict(REPLACEMENTS),
                "required_input_sha256": {p: hashlib.sha256(v).hexdigest() for p, v in files.items()}}
    owner = SimpleNamespace(metadata={"h7_storage_replacement": contract},
        build=SimpleNamespace(sources=tuple(REPLACEMENTS.values())),
        payload_root=Path(__file__).resolve().parents[1] /
            "plugins/builtin/silverstar_device_storage_sdmmc_fatfs_h7/payload")
    catalog = SimpleNamespace(Component_Get=lambda _: owner)
    model = SimpleNamespace(mcu="silverstar.mcu.stm32h743zit6", ComponentIds_Get=lambda: [OWNER],
        hardware=SimpleNamespace(mode="custom", hal_cmsis_source_policy="plugin_payload_authoritative"))
    return model, catalog, files


def test_h7_exact_sources_replaced_and_imported_bytes_preserved(tmp_path):
    model, catalog, files = Context_Create()
    before = deepcopy(files)
    receipt = H7StorageInputs_Validate(model, catalog, files, tmp_path)
    sources = ["unrelated.c", *REPLACEMENTS, *REPLACEMENTS.values()]
    excluded = []
    H7StorageSources_Replace(model, catalog, sources, excluded)
    assert sources == ["unrelated.c", *REPLACEMENTS.values()]
    assert excluded == list(REPLACEMENTS)
    assert receipt["verified_inputs"] and files == before
    assert not any(tmp_path.iterdir())


@pytest.mark.parametrize("path", sorted(REQUIRED))
def test_h7_refuses_each_modified_or_missing_required_input(tmp_path, path):
    model, catalog, files = Context_Create()
    files[path] += b"modified"
    with pytest.raises(ValueError, match="unreviewed or modified"):
        H7StorageInputs_Validate(model, catalog, files, tmp_path)
    del files[path]
    with pytest.raises(ValueError, match="unreviewed or modified"):
        H7StorageInputs_Validate(model, catalog, files, tmp_path)


def test_h7_checks_existing_user_copy_and_cache_admission(tmp_path):
    model, catalog, files = Context_Create()
    path = tmp_path / next(iter(REQUIRED))
    path.parent.mkdir(parents=True)
    path.write_bytes(b"user edit")
    with pytest.raises(ValueError, match="unreviewed or modified"):
        H7StorageInputs_Validate(model, catalog, files, tmp_path)
    assert path.read_bytes() == b"user edit"
    path.unlink()
    files[PREFIX + "Core/Src/main.c"] = b"void f(void){SCB_EnableDCache();}"
    with pytest.raises(ValueError, match="DCache disabled"):
        H7StorageInputs_Validate(model, catalog, files, tmp_path)


def test_h7_preserves_and_refuses_edited_owning_glue(tmp_path):
    model, catalog, files = Context_Create()
    path = tmp_path / "FATFS/Target/sd_diskio.c"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"user-modified driver")
    with pytest.raises(ValueError, match="owning source is modified"):
        H7StorageInputs_Validate(model, catalog, files, tmp_path)
    assert path.read_bytes() == b"user-modified driver"


def test_h7_refuses_local_header_shadowing_imported_identity(tmp_path):
    model, catalog, files = Context_Create()
    path = tmp_path / "FATFS/Target/sd_diskio.h"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"user-local header")
    with pytest.raises(ValueError, match="shadow headers"):
        H7StorageInputs_Validate(model, catalog, files, tmp_path)
    assert path.read_bytes() == b"user-local header"


@pytest.mark.parametrize("mutation", ("missing", "duplicate", "missing_owner"))
def test_h7_source_graph_never_keeps_ambiguous_glue(mutation):
    model, catalog, _ = Context_Create()
    sources = [*REPLACEMENTS, *REPLACEMENTS.values()]
    if mutation == "missing": sources.pop(0)
    elif mutation == "duplicate": sources.append(sources[0])
    else: sources.pop()
    before = list(sources)
    with pytest.raises(ValueError, match="exactly one"):
        H7StorageSources_Replace(model, catalog, sources, [])
    assert sources == before


def test_non_h7_source_graph_is_untouched():
    model = SimpleNamespace(ComponentIds_Get=lambda: [])
    sources = ["FATFS/Target/sd_diskio.c", "board.c"]
    excluded = ["irrelevant.c"]
    H7StorageSources_Replace(model, None, sources, excluded)
    assert sources == ["FATFS/Target/sd_diskio.c", "board.c"]
    assert excluded == ["irrelevant.c"]


def test_real_h7_bsp_normal_and_fault_boundaries(tmp_path):
    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests/fixtures/h7_storage"
    source = root / "plugins/builtin/silverstar_device_storage_sdmmc_fatfs_h7/payload/FATFS/Target/bsp_driver_sd.c"
    compiler = shutil.which("gcc")
    assert compiler, "Host GCC required"
    binary = tmp_path / "h7-bsp.exe"
    result = subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-fanalyzer",
        "-I"+str(fixture), str(source), str(fixture/"test_bsp.c"), "-o", str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def DiskioFixture_Compile(destination, source):
    root = Path(__file__).resolve().parents[1]
    port = root / "plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/storage_integrity"
    fixture = root / "tests/fixtures/h7_diskio"
    platform = root / "plugins/builtin/silverstar_platform_api/payload/Platform/Inc"
    compiler = shutil.which("gcc")
    assert compiler, "Host GCC required"
    binary = destination / "h7-diskio.exe"
    result = subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-fanalyzer",
        "-I"+str(fixture), "-I"+str(port), "-I"+str(platform), str(source),
        str(fixture/"test_diskio_faults.c"), "-o", str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return binary


def test_real_h7_diskio_rejects_late_ready_error_and_initialization_failure(tmp_path):
    source = Path(__file__).resolve().parents[1] / (
        "plugins/builtin/silverstar_device_storage_sdmmc_fatfs_h7/payload/FATFS/Target/sd_diskio.c")
    binary = DiskioFixture_Compile(tmp_path, source)
    for mode in (0, 1, 2, 3, 4):
        result = subprocess.run([str(binary), str(mode)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
