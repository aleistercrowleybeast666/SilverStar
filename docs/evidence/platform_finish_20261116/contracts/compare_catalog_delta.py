"""Record C/D constant identity changes without masking any sealed input."""
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / ".work/platform-finish-20261116/contracts"
OBJDUMP = "D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-objdump.exe"


def main():
    module_path = WORK / "final-generated-d/f4/Flight_Controller/Tools/stack_arm.py"
    spec = importlib.util.spec_from_file_location("catalog_arm", module_path)
    arm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arm)
    result = {"scope": "Diagnostic comparison, not a case seal or acceptance gate.",
              "parser_sha256": hashlib.sha256(module_path.read_bytes()).hexdigest(),
              "configurations": {}}
    for configuration in ("Release", "Debug"):
        runs = []
        for label in ("c", "d"):
            project = WORK / ("final-generated-" + label) / "f4/Flight_Controller"
            elf = project / "build/FCCG/SilverStar_F407" / configuration / "SilverStar_0_1_3.elf"
            disassembly = subprocess.check_output([OBJDUMP, "-d", str(elf)], text=True)
            symbols = subprocess.check_output([OBJDUMP, "-t", str(elf)], text=True)
            functions = arm.Assembly_Parse(disassembly, symbols)
            source = (project / "Generated/Src/project_log_decoder_profile.c").read_text()
            block = re.search(r"s_generation_profile_hash\[[^]]+\]\s*=\s*\{([^}]+)\}", source)[1]
            constant = bytes(int(word, 16) for word in re.findall(r"0x([0-9A-F]{2})U", block))
            raw = elf.read_bytes()
            offsets = [match.start() for match in re.finditer(re.escape(constant), raw)]
            runs.append({"rows": {name: row["rows"] for name, row in functions.items()},
                         "raw": raw, "constant": constant.hex(), "constant_offsets": offsets,
                         "elf_sha256": hashlib.sha256(raw).hexdigest(),
                         "objdump_d_sha256": hashlib.sha256(disassembly.encode()).hexdigest(),
                         "objdump_t_sha256": hashlib.sha256(symbols.encode()).hexdigest()})
        first, second = runs
        changed = [name for name in first["rows"].keys() | second["rows"].keys()
                   if first["rows"].get(name) != second["rows"].get(name)]
        assert not changed
        assert len(first["raw"]) == len(second["raw"])
        offsets = [index for index, value in enumerate(first["raw"]) if value != second["raw"][index]]
        result["configurations"][configuration] = {
            "function_count": len(first["rows"]), "changed_instruction_rows": changed,
            "elf_changed_byte_offsets": offsets,
            "inputs": [{key: value for key, value in row.items() if key not in ("rows", "raw")}
                       for row in runs]}
    output = WORK / "c-d-linked-instruction-comparison.json"
    if output.exists():
        raise ValueError("Do not overwrite prior diagnostic evidence")
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print("C/D instruction rows unchanged; complete raw byte differences retained")


if __name__ == "__main__":
    main()
