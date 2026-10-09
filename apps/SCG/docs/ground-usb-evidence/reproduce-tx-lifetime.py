import ast
import subprocess, sys
from pathlib import Path
from types import SimpleNamespace
import silverstar_fccg.generator.multi_target as current

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
repo = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else root.parent / "ground-usb-worktree"
base = "6fe76d87d05de6b7528e74d9c423df6d9217e47f"
old_text = subprocess.check_output(["git", "show", base + ":apps/SCG/src/silverstar_fccg/generator/multi_target.py"], cwd=repo, text=True)
node = next(node for node in ast.parse(old_text).body if isinstance(node, ast.FunctionDef) and node.name == "_PcAdapter_Render")
namespace = dict(current.__dict__)
exec(compile(ast.Module(body=[node], type_ignores=[]), "baseline_adapter", "exec"), namespace)
model = SimpleNamespace(ground_target=SimpleNamespace(pc_interface="usb_cdc"))
destination = root / "tx-lifetime"
destination.mkdir(exist_ok=True)
payload = repo / "apps/SCG/plugins/builtin/silverstar_core_ground_0_1_0/payload"
common = repo / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Common"
for source_name, name in (("usb_main.h", "main.h"), ("usb_device.h", "usb_device.h"), ("usb_cdc_if.h", "usbd_cdc_if.h")):
    (destination / name).write_bytes((payload / "Tests/Host" / source_name).read_bytes())
(destination / "usbd_conf.h").write_text("/* Host stub */\n", encoding="utf8")
(destination / "probe.c").write_text('''#include <stdint.h>
#include <assert.h>
#include "pc_byte_stream.h"
#include "usb_device.h"
#include "usbd_cdc_if.h"
uint32_t usb_test_mask;
static USBD_CDC_HandleTypeDef cdc;
USBD_HandleTypeDef hUsbDeviceFS = {USBD_STATE_CONFIGURED, &cdc};
static uint8_t *retained;
uint8_t CDC_Transmit_FS(uint8_t *buffer, uint16_t length) {
    assert(length == 3U); retained = buffer; cdc.TxState = 1U; return USBD_OK;
}
int main(void) {
    uint8_t caller[3] = {1U, 2U, 3U};
    assert(PcByteStream_Write(caller, 3U) == PC_BYTE_STREAM_WRITE_OK);
    caller[0] = 99U;
    /* The USB stack still owns an outstanding asynchronous transfer. */
    return retained[0] == 1U ? 0 : 23;
}
''', encoding="utf8")
for label, source in (("before", namespace["_PcAdapter_Render"](model)), ("after", current._PcAdapter_Render(model))):
    adapter = destination / (label + ".c")
    adapter.write_text(source, encoding="utf8")
    executable = destination / (label + ".exe")
    command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-I" + str(destination), "-I" + str(payload / "Ground/Core/Inc"), "-I" + str(payload / "Ground/Protocol/Inc"), "-I" + str(common / "Inc"), str(adapter), str(destination / "probe.c"), str(common / "Src/silverstar_assert.c"), "-o", str(executable)]
    print("COMMAND", command, flush=True)
    subprocess.run(command, check=True)
    result = subprocess.run([str(executable)])
    print(label, "exit", result.returncode, "expected", 23 if label == "before" else 0, flush=True)
    assert result.returncode == (23 if label == "before" else 0)
print("PASS: baseline caller-buffer corruption reproduced; owned TX buffer prevents it")
