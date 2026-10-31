"""Record actual linked placement and local compiler frames without stack claims."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
PROJECT = ROOT / ".work/0.1.3-treediagram-20261101/h7-storage-v4/final/Flight_Controller"
BUILD = PROJECT / "build/FCCG/SilverStar_H743ZI/Release"
elf = BUILD / "SilverStar_0_1_3.elf"
nm_command = [shutil.which("arm-none-eabi-nm"), "-S", str(elf)]
nm = subprocess.run(nm_command,capture_output=True,text=True,check=True).stdout
scratch = [line for line in nm.splitlines() if line.endswith(" s_sd_scratch")]
assert len(scratch) == 1
address, length, _, _ = scratch[0].split()
assert int(length,16) == 512 and int(address,16) % 32 == 0
assert 0x24000000 <= int(address,16) < 0x24080000 - 511
disassemblies = {}
for name in ("BSP_SD_ReadBlocks_DMA", "BSP_SD_WriteBlocks_DMA", "HAL_SD_RxCpltCallback"):
    command = [shutil.which("arm-none-eabi-objdump"), "-d", "--disassemble="+name, str(elf)]
    result = subprocess.run(command,capture_output=True,text=True,check=True)
    assert "dmb" in result.stdout
    disassemblies[name] = {"command":command,"stdout":result.stdout}
frames = {name:(BUILD / "FATFS/Target" / name).read_text() for name in ("sd_diskio.su", "bsp_driver_sd.su")}
artifacts = [{"path":str(path.relative_to(ROOT)),"bytes":path.stat().st_size,
    "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
    for path in sorted(BUILD.iterdir()) if path.suffix in (".elf", ".bin", ".hex", ".map")]
record = {"artifacts":artifacts,"nm_command":nm_command,"scratch_symbol":scratch[0],
    "scratch_AXI_SRAM_32_aligned":True,"disassembly":disassemblies,"local_frames":frames,
    "scope":"Local emitted frames and symbol placement only; strict stack gate remains authoritative; no whole-task/MSP/ISR bound inferred."}
(EVIDENCE / "linked-placement-and-local-frames.json").write_text(json.dumps(record,indent=2)+"\n")
print(json.dumps({key:value for key,value in record.items() if key not in ("disassembly",)},indent=2))
