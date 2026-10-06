"""Synthetic F1 FatFs pointer/binding negatives; no SD hardware execution."""
import re
from pathlib import Path

import pytest
from test_stack_budget import stacks, _ElfFixture_Create


def _SdFixture(root, monkeypatch, mutation=None):
    root = _ElfFixture_Create(root, monkeypatch)
    original_read = stacks.Command_Read
    family = Path(__file__).resolve().parents[1] / "plugins/builtin/silverstar_mcu_family_stm32f1_flight/payload"
    paths = ["Platform/STM32F1Flight/Src/sd_diskio_stm32f1flight.c",
             "Middlewares/Third_Party/FatFs/src/diskio.c",
             "Middlewares/Third_Party/FatFs/src/ff_gen_drv.c"]
    fatfs = "HardwareGenerated/STM32CubeMX/FATFS/App/fatfs.c"
    for path in paths:
        text = (family / path).read_text(encoding="utf8")
        if mutation == "registry" and path.endswith("ff_gen_drv.c"):
            text = text.replace("disk.drv[disk.nbr] = drv;", "disk.drv[disk.nbr] = replacement;")
        if mutation == "table" and path.endswith("sd_diskio_stm32f1flight.c"):
            text = re.sub(r"(?<=\n    )SD_write(?=,)", "UnreviewedWrite", text)
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf8")
    target = root / fatfs
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("void MX_FATFS_Init(void) { retSD = FATFS_LinkDriver(&SD_Driver, SDPath); }", encoding="utf8")
    if mutation == "alias":
        (root / "test.c").write_text("void mutate(void) { void *p = &SD_Driver; corrupt(p); }", encoding="utf8")
    else:
        (root / "test.c").write_text("", encoding="utf8")
    (root / "Generated/project_sources.mk").write_text(
        "C_SOURCES += \\\n  test.c \\\n  " + " \\\n  ".join(paths + [fatfs]) + "\n\n", encoding="utf8")
    build = root / "build/FCCG/SilverStar_F407/Release"
    for path in paths + [fatfs]:
        su = build / Path(path).with_suffix(".su")
        su.parent.mkdir(parents=True, exist_ok=True)
        su.write_text("", encoding="utf8")
    edges = {"MX_FATFS_Init": ["FATFS_LinkDriver"], "FATFS_LinkDriver": [],
             "disk_write": [], "SD_write": ["SdDiskIo_SectorWrite"], "SdDiskIo_SectorWrite": ["BSP_SD_WriteBlocks_DMA"],
             "BSP_SD_WriteBlocks_DMA": [], "SD_initialize": [], "SD_status": [], "SD_read": [], "SD_ioctl": []}
    if mutation == "caller":
        edges["OtherRegistration"] = ["FATFS_LinkDriver"]
    extra = ""
    for name, callees in edges.items():
        extra += "08000000 <" + name + ">:\n"
        for callee in callees:
            extra += " 8000000: f000 f000 bl 8000000 <" + callee + ">\n"
        if name == "disk_write":
            extra += " 8000004: 4798 blx r3\n"
        extra += " 8000008: 4770 bx lr\n"
    with (build / "test.su").open("a", encoding="utf8") as stream:
        stream.write("".join("fixture.c:1:1:" + name + "\t32\tstatic\n" for name in edges))
    addresses = {name: 0x08001000 + i * 16 for i,name in enumerate(stacks.DISK_CALLBACKS.values())}
    raw = b"".join((address | 1).to_bytes(4,"little") for address in addresses.values())
    if mutation == "pointers":
        raw = b"\0" * 20
    def read(command, cwd):
        if "objdump" in command[0] and "-s" in command:
            return "file format elf32-littlearm\n 20000000 " + " ".join(raw[i:i+4].hex() for i in range(0,16,4)) + "\n 20000010 " + raw[16:].hex() + "\n"
        text = original_read(command, cwd)
        if "objdump" in command[0]:
            return text.replace("08000000 <AppTask_Logger>:\n", "08000000 <AppTask_Logger>:\n 8000000: f000 f000 bl 8000000 <disk_write>\n") + extra
        if "nm" in command[0]:
            return text + "20000000 00000014 D SD_Driver\n" + "".join(f"{addr:08x} 00000020 t {name}\n" for name,addr in addresses.items())
        return text
    monkeypatch.setattr(stacks,"Command_Read",read)
    return root


def test_sd_provider_counts_actual_dma_subtree(tmp_path, monkeypatch):
    report = stacks.StackReport_Build(_SdFixture(tmp_path,monkeypatch),"Release","fixture-")
    assert report["passes"]
    logger = next(row for row in report["tasks"] if row["task"] == "Logger")
    assert logger["call_chain_bytes"] == 64 + 4 * 32
    assert logger["chain"][-1]["function"] == "BSP_SD_WriteBlocks_DMA"


@pytest.mark.parametrize("mutation,message", [
    ("registry", "Changed reviewed F1 FatFs binding source"),
    ("table", "Unreviewed selected SD_Driver callback table"),
    ("alias", "Unreviewed F1 SD_Driver source reference"),
    ("caller", "Unreviewed SD_Driver registration caller"),
    ("pointers", "Linked F1 SD callback pointers differ"),
])
def test_sd_binding_fails_closed(tmp_path, monkeypatch, mutation, message):
    with pytest.raises(ValueError,match=message):
        stacks.StackReport_Build(_SdFixture(tmp_path,monkeypatch,mutation),"Release","fixture-")
