"""Exact reviewed H743 SDMMC glue replacement, without editing imported bytes."""
from __future__ import annotations
import hashlib
from pathlib import Path
import re

OWNER = "silverstar.device.storage.sdmmc_fatfs_h7"
PREFIX = "HardwareGenerated/STM32CubeMX/"
REPLACEMENTS = {PREFIX + "FATFS/Target/" + name: "FATFS/Target/" + name
                for name in ("sd_diskio.c", "bsp_driver_sd.c")}
REQUIRED = {PREFIX + name for name in (
    "FATFS/Target/sd_diskio.c", "FATFS/Target/bsp_driver_sd.c",
    "FATFS/Target/sd_diskio.h", "FATFS/Target/bsp_driver_sd.h", "FATFS/Target/ffconf.h",
    "FATFS/App/fatfs.c", "FATFS/App/fatfs.h", "Core/Src/sdmmc.c",
    "Core/Inc/sdmmc.h", "Core/Src/stm32h7xx_it.c")}


def H7StorageContract_Get(model, catalog):
    if OWNER not in model.ComponentIds_Get():
        return None
    if (model.mcu != "silverstar.mcu.stm32h743zit6" or model.hardware.mode != "custom"
            or model.hardware.hal_cmsis_source_policy != "plugin_payload_authoritative"):
        raise ValueError("H7 SDMMC replacement requires the exact imported H743 candidate")
    owner = catalog.Component_Get(OWNER)
    contract = owner.metadata.get("h7_storage_replacement")
    if (type(contract) is not dict or set(contract) != {"schema_id", "replacements", "required_input_sha256"}
            or contract["schema_id"] != "silverstar.h7-storage-replacement/1"
            or contract["replacements"] != REPLACEMENTS):
        raise ValueError("H7 storage replacement contract is missing or incompatible")
    hashes = contract["required_input_sha256"]
    if type(hashes) is not dict or set(hashes) != REQUIRED or any(
            type(value) is not str or not re.fullmatch("[0-9a-f]{64}", value) for value in hashes.values()):
        raise ValueError("H7 storage replacement requires the complete reviewed input identity")
    if any(path not in owner.build.sources for path in REPLACEMENTS.values()):
        raise ValueError("H7 storage replacement lacks its owning source")
    return contract


def H7StorageSources_Replace(model, catalog, sources: list[str], excluded: list[str]) -> None:
    contract = H7StorageContract_Get(model, catalog)
    if contract is None:
        return
    for original, replacement in REPLACEMENTS.items():
        if sources.count(original) != 1 or sources.count(replacement) != 1:
            raise ValueError("H7 storage replacement requires exactly one imported and owning source: " + original)
    for original in REPLACEMENTS:
        sources.remove(original)
        excluded.append(original)


def H7StorageInputs_Validate(model, catalog, hardware_files: dict[str, bytes], project_root: Path):
    contract = H7StorageContract_Get(model, catalog)
    if contract is None:
        return None
    actual = {}
    root = project_root.resolve()
    owner = catalog.Component_Get(OWNER)
    # The owning C files deliberately consume the retained/imported headers.
    # A user header beside a C file would win quoted-include lookup first.
    if any(path.is_file() for path in (root / "FATFS/Target").glob("*.h")):
        raise ValueError("H7 owning glue has unreviewed local shadow headers; preserve and review them")
    for relative in REPLACEMENTS.values():
        existing = root / relative
        if existing.is_symlink() or not existing.resolve().is_relative_to(root):
            raise ValueError("H7 owning source escapes the project: " + relative)
        if existing.is_file() and existing.read_bytes() != (owner.payload_root / relative).read_bytes():
            raise ValueError("H7 owning source is modified; preserve and review it before generation: " + relative)
    for relative, expected in contract["required_input_sha256"].items():
        existing = root / relative
        if existing.is_symlink() or not existing.resolve().is_relative_to(root):
            raise ValueError("H7 storage input must remain inside the project: " + relative)
        content = existing.read_bytes() if existing.is_file() else hardware_files.get(relative)
        if content is None or hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("H7 storage replacement input is unreviewed or modified: " + relative)
        actual[relative] = expected
    for relative, snapshot in hardware_files.items():
        if relative.startswith(PREFIX + "Core/") and relative.endswith((".c", ".h")):
            existing = root / relative
            content = existing.read_bytes() if existing.is_file() else snapshot
            code = re.sub(r"/\*.*?\*/|//[^\r\n]*", "", content.decode("utf-8"), flags=re.DOTALL)
            if re.search(r"\bSCB_EnableDCache\s*\(|\bSCB_CCR_DC_Msk\b", code):
                raise ValueError("H7 SDMMC candidate requires DCache disabled: " + relative)
    return {"schema_id": contract["schema_id"], "owner": OWNER,
            "source_policy": "imported bytes retained; exact two C units replaced in Make and IDE",
            "verified_inputs": actual, "replacements": REPLACEMENTS,
            "hardware_qualified": False}
