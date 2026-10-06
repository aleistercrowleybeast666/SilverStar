"""Small, reproducible independent checkpoint evidence. Does not qualify hardware."""
from pathlib import Path
import hashlib
import json
import os
import shlex
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
DAILY = Path("D:/python_software/SilverStar")
MAKE = "D:/msys64/ucrt64/bin/mingw32-make.exe"
ARM_DIR = "D:/Arm GNU Toolchain/14.3 rel1/bin"
ARM = ARM_DIR + "/arm-none-eabi-gcc.exe"


def Evidence_Run(directory, name, command, cwd=REPO, env=None, expected=0):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                            text=True, encoding="utf8", errors="replace", timeout=900)
    record = {"command": command, "cwd": str(cwd), "exit_code": result.returncode,
              "expected_exit_code": expected, "stdout": result.stdout, "stderr": result.stderr}
    (directory / (name + ".json")).write_text(json.dumps(record, indent=2), encoding="utf8")
    print(name, result.returncode, flush=True)
    return result


def LegacyProbe_Get(directory):
    probe = '''import json,hashlib
from dataclasses import replace
from pathlib import Path
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.generator.render import AirLinkHeader_Render
from silverstar_fccg.generator.ground_radio import GroundRadioConfig_Render,GroundRadioAirHeader_Render
root=Path.cwd()/"apps/SCG"
c=PluginCatalog(root/"plugins/builtin",root/"plugins/installed"); c.Scan()
m=ReferenceProject_Create("LegacyProbe",catalog=c)
h=AirLinkHeader_Render(m)
g=replace(m.ground_target,radio_plugin="silverstar.device.telemetry.sx1281",module_variant="e28_2g4m12sx")
out={"flight_header":h,"ground_header":GroundRadioAirHeader_Render(g,h),
"ground_config":GroundRadioConfig_Render(g),"air_link":m.Dictionary_Get()["air_link"]}
print(json.dumps(out,sort_keys=True))
'''
    results = []
    for label, repo in (("baseline", DAILY), ("candidate", REPO)):
        env = dict(os.environ, PYTHONPATH=str(repo / "apps/SCG/src"), PYTHONUTF8="1")
        result = Evidence_Run(directory, "sx_exact_" + label, [sys.executable, "-c", probe], repo, env)
        assert result.returncode == 0, result.stderr
        results.append(json.loads(result.stdout))
    assert results[0] == results[1], "Legacy SX configuration/header bytes changed"
    (directory / "sx_exact_comparison.json").write_text(json.dumps({"equal": True,
        "sha256": {key: hashlib.sha256(value.encode()).hexdigest() for key,value in results[0].items()
                   if isinstance(value,str)}, "scope": "Default SX1281 Flight/Ground headers, Ground config, old air_link serialization"}, indent=2), encoding="utf8")


def ArmSubset_Compile(directory, flight):
    dry = Evidence_Run(directory, "make_dry", [MAKE, "-B", "-n", "CONFIG=Release",
        "GCC_PATH=" + ARM_DIR, "all"], flight)
    assert dry.returncode == 0
    commands = [shlex.split(line) for line in dry.stdout.splitlines()
        if line.startswith('"D:/Arm GNU Toolchain/') and " -c " in line and "/NRF24L01P/" in line]
    commands = [command for command in commands if "/NRF24L01P/" in command[command.index("-o")-1]]
    assert len(commands) == 3
    for command in commands:
        source = command[command.index("-o") - 1]
        stem = Path(source).stem
        for mode in ("arm", "analyzer"):
            out = directory / (mode + "_" + stem + ".o")
            compiled = list(command)
            compiled[compiled.index("-o") + 1] = str(out)
            compiled = [('-MF' + str(out.with_suffix('.d'))) if item.startswith('-MF') else item for item in compiled]
            if mode == "analyzer": compiled.append("-fanalyzer")
            assert Evidence_Run(directory, mode + "_" + stem, compiled, flight).returncode == 0
    canary = directory / "analyzer_canary.c"
    canary.write_text('#include <stdlib.h>\nvoid Canary(void);\nvoid Canary(void) { void *p=malloc(8); free(p); free(p); }\n', encoding="utf8")
    result = Evidence_Run(directory, "analyzer_canary", [ARM, "-mcpu=cortex-m4", "-mthumb", "-O0",
        "-fanalyzer", "-Werror=analyzer-double-free", "-c", str(canary), "-o", str(directory / "canary.o")], expected=1)
    assert result.returncode != 0 and "double-free" in result.stderr
    size = ARM_DIR + "/arm-none-eabi-size.exe"
    objects = [str(path) for path in directory.glob("arm_*.o")]
    assert Evidence_Run(directory, "arm_static_sections", [size, *objects]).returncode == 0


def CrcCollision_Record(directory):
    # Generate a complete-datagram collision, then mix separately valid chunks.
    import binascii
    crc = lambda data: binascii.crc_hqx(data, 0xFFFF)
    old = bytearray(50)
    def changed(start, end):
        data = bytearray(old); data[start] = 1
        for patch in range(65536):
            data[end-2:end] = patch.to_bytes(2, "little")
            if crc(data) == crc(old): return data
        raise AssertionError("CRC linear patch not found")
    first = changed(0,22); second = changed(22,44)
    new = bytearray(a ^ b for a,b in zip(first,second))
    hybrid = old[:22] + new[22:]
    assert old != new != hybrid != old and crc(old) == crc(new) == crc(hybrid)
    (directory / "crc_collision.json").write_text(json.dumps({
        "old": old.hex(), "new": new.hex(), "mixed": hybrid.hex(), "crc16": crc(old),
        "same_identity": {"session":1,"sequence":1,"length":50},
        "consequence": "CRC16 cannot prove absence of identity-reuse mixed-datagram collisions. No cryptographic anti-replay claim; upper M0 command contracts unchanged and need review."}, indent=2), encoding="utf8")


if __name__ == "__main__":
    directory = Path(sys.argv[1]).resolve()
    assert not directory.exists(), "Use a fresh evidence directory"
    directory.mkdir(parents=True)
    for label, command in (("python_version", [sys.executable,"--version"]),
        ("arm_version",[ARM,"--version"]), ("host_gcc_version",["D:/msys64/ucrt64/bin/gcc.exe","--version"]),
        ("make_version",[MAKE,"--version"])):
        Evidence_Run(directory,label,command)
    paths = subprocess.check_output(["git", "-c", "safe.directory=" + str(REPO), "ls-files", "--modified", "--others", "--exclude-standard"], cwd=REPO, text=True).splitlines()
    hashes = {path: hashlib.sha256((REPO/path).read_bytes()).hexdigest() for path in paths if (REPO/path).is_file()}
    (directory/"source_hashes.json").write_text(json.dumps(hashes,indent=2),encoding="utf8")
    LegacyProbe_Get(directory)
    CrcCollision_Record(directory)
    ArmSubset_Compile(directory, Path(sys.argv[2]).resolve())
