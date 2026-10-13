"""Record the old stream's partial-packet capacity boundary against new needs.

This is a feature-gap reproduction, not a claim the old documented drop policy
violated its own contract. The original owner is loaded from the frozen commit.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess

REPO = Path(__file__).resolve().parents[4]
SCG = REPO / "apps/SCG"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    commit = subprocess.check_output(["git", "rev-parse", "c31c13c"], cwd=REPO, text=True).strip()
    name = "apps/SCG/src/silverstar_fccg/generator/ground_pc_usb_cdc.py"
    original = subprocess.check_output(["git", "show", commit + ":" + name], cwd=REPO)
    owner = output / "baseline_owner.py"
    owner.write_bytes(original)
    spec = importlib.util.spec_from_file_location("baseline_usb_owner", owner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (output / "pc_byte_stream.c").write_text(module.PcUsbCdc_Render(), encoding="utf8")
    payload = SCG / "plugins/builtin/silverstar_core_ground_0_1_0/payload"
    for src, dest in (("usb_main.h", "main.h"), ("usb_device.h", "usb_device.h"),
                      ("usb_cdc_if.h", "usbd_cdc_if.h")):
        (output / dest).write_bytes((payload / "Tests/Host" / src).read_bytes())
    (output / "usbd_conf.h").write_text("/* Host substitute; no hardware. */\n")
    (output / "harness.c").write_text('''#include <stdio.h>
#include <assert.h>
#include "pc_byte_stream.c"
uint32_t usb_test_mask;
USBD_HandleTypeDef hUsbDeviceFS;
uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{ (void)data; (void)length; return USBD_OK; }
void SilverStarAssert_Check(uint8_t ok, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{ (void)module; (void)file; (void)line; (void)reason; assert(ok); }
int main(void)
{
    uint8_t data[512] = {0};
    uint16_t actual;
    unsigned index;
    assert(PcByteStream_Init() == PC_BYTE_STREAM_INIT_OK);
    for (index = 0U; index < 8U; index++) { PcByteStream_OnUsbReceive(data, 64U); }
    actual = PcByteStream_Read(data, sizeof(data));
    printf("requested=512, actual=%u, dropped=%lu\\n", (unsigned)actual,
        (unsigned long)PcByteStream_OverflowCount_Get());
    return actual == 512U ? 0 : 1;
}
''', encoding="utf8")
    compile_command = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(output),
        "-I" + str(payload / "Ground/Core/Inc"), "-I" + str(payload / "Ground/Protocol/Inc"),
        "-I" + str(SCG / "plugins/builtin/silverstar_core_0_1_0/payload/Common/Inc"),
        "harness.c", "-o", "baseline.exe"]
    commands = []
    for label, command, expected in (("compile", compile_command, 0),
                                      ("required-capacity", [str(output / "baseline.exe")], 1)):
        result = subprocess.run(command, cwd=output, capture_output=True, text=True, encoding="utf8")
        (output / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf8")
        commands.append({"command": command, "exit": result.returncode, "expected_exit": expected})
        assert result.returncode == expected, result.stderr
    manifest = {"baseline_commit": commit, "owner": name, "owner_sha256": hashlib.sha256(original).hexdigest(),
        "commands": commands, "scope": __doc__,
        "files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf8")
    print((output / "required-capacity.log").read_text())


if __name__ == "__main__":
    main()
