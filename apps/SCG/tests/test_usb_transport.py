"""Generic CDC capability/ownership tests; no attached USB device is accessed."""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess

import pytest

from silverstar_fccg.app.usb_transport import (
    UsbTransport_Plan, UsbTransport_Export, UsbTransportPlanResult,
)
from silverstar_fccg.generator.usb_cdc_transport import UsbCdcTransport_Render
from silverstar_fccg.hardware.cubemx import CubeMxImportError

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "plugins/builtin/silverstar_core_0_1_0/payload/Common/Inc"


def _Compile_Run(tmp_path, harness, *, indexed=False):
    for path, body in UsbCdcTransport_Render(indexed=indexed).items():
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
    (tmp_path / "harness.c").write_text(harness, encoding="utf-8")
    command = ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wvla",
        "-fanalyzer", "-I" + str(tmp_path / "Inc"), "-I" + str(COMMON),
        str(tmp_path / "harness.c"), "-o", str(tmp_path / "host.exe")]
    result = subprocess.run(command, capture_output=True, text=True)
    (tmp_path / "compile.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(tmp_path / "host.exe")], capture_output=True, text=True)
    (tmp_path / "run.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr


def test_bounded_stream_sessions_and_fault_retirement(tmp_path):
    _Compile_Run(tmp_path, r'''
#include <assert.h>
#include <string.h>
#include <setjmp.h>
#include "Src/usb_cdc_transport.c"
static uint32_t mask;
static uint32_t arms;
static uint32_t submits;
static uint8_t *owned;
static UsbCdcResult state = USB_CDC_OK;
static UsbCdcResult submit = USB_CDC_OK;
static UsbCdcResult rearm = USB_CDC_OK;
static jmp_buf trap;
uint32_t UsbCdcPort_Lock(void) { uint32_t prior = mask; mask = 1U; return prior; }
void UsbCdcPort_Unlock(uint32_t token) { mask = token; }
UsbCdcResult UsbCdcPort_TxState(void) { return state; }
UsbCdcResult UsbCdcPort_Submit(uint8_t *data, uint16_t length)
{ assert(mask == 1U); assert(length > 0U); owned = data; submits++; return submit; }
UsbCdcResult UsbCdcPort_Rearm(void) { assert(mask == 1U); arms++; return rearm; }
void SilverStarAssert_Check(uint8_t ok, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{ (void)module; (void)file; (void)line; (void)reason; if (!ok) { longjmp(trap, 1); } }
int main(void)
{
    uint8_t data[USB_CDC_RX_CAPACITY];
    uint8_t out[USB_CDC_RX_CAPACITY];
    uint32_t session;
    uint16_t length;
    uint32_t old;
    uint32_t index;
    memset(data, 0x39, sizeof(data));
    assert(UsbCdc_Write(data, 1U, 1U) == USB_CDC_OFFLINE);
    assert(UsbCdc_Configure() == USB_CDC_OK);
    assert(UsbCdc_Configure() == USB_CDC_BUSY);
    assert(UsbCdc_Quiesced() == USB_CDC_BUSY);
    assert(UsbCdc_Service() == USB_CDC_OK && arms == 0U);
    old = UsbCdc_SessionGet();
    for (index = 0U; index < 8U; index++)
    {
        assert(UsbCdc_Receive(data, 64U) == USB_CDC_OK);
        assert(UsbCdc_Service() == USB_CDC_OK);
    }
    assert(arms == 7U);
    assert(UsbCdc_Receive(data, 1U) == USB_CDC_BUSY);
    assert(UsbCdc_Read(out, 63U, &length, &session) == USB_CDC_OK && length == 63U);
    assert(UsbCdc_Service() == USB_CDC_OK && arms == 7U);
    assert(UsbCdc_Read(out, 1U, &length, &session) == USB_CDC_OK && length == 1U);
    assert(UsbCdc_Service() == USB_CDC_OK && arms == 8U);
    assert(UsbCdc_Receive(data, 64U) == USB_CDC_OK);
    assert(UsbCdc_Read(out, sizeof(out), &length, &session) == USB_CDC_OK);
    assert(length == sizeof(out) && session == old && memcmp(out, data, sizeof(out)) == 0);
    assert(UsbCdc_Write(data, 64U, session) == USB_CDC_OK);
    state = USB_CDC_BUSY;
    assert(UsbCdc_Service() == USB_CDC_BUSY && submits == 0U);
    state = USB_CDC_OK;
    assert(UsbCdc_Service() == USB_CDC_OK && submits == 1U);
    data[0] = 0x72;
    assert(owned[0] == 0x39);
    state = USB_CDC_BUSY; /* Data IN and the trailing ZLP still own the buffer. */
    assert(UsbCdc_Service() == USB_CDC_BUSY);
    assert(UsbCdc_Write(data, 1U, session) == USB_CDC_BUSY);
    UsbCdc_LinkDown();
    assert(UsbCdc_Configure() == USB_CDC_BUSY && owned[0] == 0x39);
    assert(UsbCdc_Write(data, 1U, old) == USB_CDC_OFFLINE);
    assert(UsbCdc_Quiesced() == USB_CDC_OK);
    assert(UsbCdc_Configure() == USB_CDC_OK);
    assert(UsbCdc_Write(data, 1U, old) == USB_CDC_OFFLINE);
    assert(UsbCdc_Read(out, sizeof(out), &length, &session) == USB_CDC_OK && length == 0U);
    assert(UsbCdc_Write(data, 1U, session) == USB_CDC_OK);
    state = USB_CDC_OK;
    submit = USB_CDC_FAULT;
    assert(UsbCdc_Service() == USB_CDC_FAULT);
    assert(UsbCdc_Configure() == USB_CDC_BUSY && owned[0] == 0x72);
    assert(UsbCdc_Quiesced() == USB_CDC_OK);
    assert(UsbCdc_Configure() == USB_CDC_OK);
    assert(UsbCdc_Receive(data, 64U) == USB_CDC_OK);
    rearm = USB_CDC_FAULT;
    assert(UsbCdc_Service() == USB_CDC_FAULT);
    assert(UsbCdc_Read(out, sizeof(out), &length, &session) == USB_CDC_OFFLINE && length == 0U);
    assert(UsbCdc_Receive(NULL, 1U) == USB_CDC_INVALID);
    assert(UsbCdc_Write(data, USB_CDC_TX_CAPACITY + 1U, session) == USB_CDC_INVALID);
    s_session = UINT32_MAX;
    UsbCdc_LinkDown();
    assert(UsbCdc_Quiesced() == USB_CDC_OK);
    assert(UsbCdc_Configure() == USB_CDC_FAULT);
    /* Test-only terminal trap interception; no target recovery mechanism. */
    if (setjmp(trap) == 0)
    {
        s_count = USB_CDC_RX_CAPACITY + 1U;
        (void)UsbCdc_Service();
        assert(0);
    }
    return 0;
}
''')


def _PortHeaders_Write(tmp_path):
    (tmp_path / "Inc").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Inc/main.h").write_text('''#include <stdint.h>
static uint32_t __get_PRIMASK(void) { return 0U; }
static void __disable_irq(void) {}
static void __set_PRIMASK(uint32_t value) { (void)value; }
static void __DMB(void) {}
''')
    (tmp_path / "Inc/usb_device.h").write_text('''#include <stdint.h>
#define USBD_STATE_CONFIGURED 3U
#define USBD_OK 0U
#define USBD_BUSY 1U
#define CDC_DATA_FS_MAX_PACKET_SIZE 64U
typedef struct { uint32_t TxState; } USBD_CDC_HandleTypeDef;
typedef struct { uint8_t dev_state; uint8_t classId; void *pClassData; void *pClassDataCmsit[1]; } USBD_HandleTypeDef;
''')
    (tmp_path / "Inc/usbd_cdc_if.h").write_text('''uint8_t CDC_Transmit_FS(uint8_t *, uint16_t);
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *);
''')


@pytest.mark.parametrize("indexed", [False, True])
def test_classic_port_precheck_busy_and_ambiguous_postcall_failures(tmp_path, indexed):
    _PortHeaders_Write(tmp_path)
    _Compile_Run(tmp_path, r'''
#include <assert.h>
#include "Src/usb_cdc_port.c"
USBD_HandleTypeDef hUsbDeviceFS;
static unsigned calls;
static uint8_t result;
uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{ (void)data; (void)length; calls++; return result; }
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *device)
{ (void)device; calls++; return result; }
int main(void)
{
    USBD_CDC_HandleTypeDef cdc = {1U};
    uint8_t byte = 1U;
    hUsbDeviceFS.dev_state = USBD_STATE_CONFIGURED;
    hUsbDeviceFS.pClassData = &cdc;
    hUsbDeviceFS.pClassDataCmsit[0] = &cdc;
    assert(UsbCdcPort_Submit(&byte, 1U) == USB_CDC_BUSY && calls == 0U);
    cdc.TxState = 0U;
    result = USBD_BUSY;
    assert(UsbCdcPort_Submit(&byte, 1U) == USB_CDC_FAULT && calls == 1U);
    assert(UsbCdcPort_Rearm() == USB_CDC_FAULT && calls == 2U);
    result = USBD_OK;
    assert(UsbCdcPort_Submit(&byte, 1U) == USB_CDC_OK);
    assert(UsbCdcPort_Rearm() == USB_CDC_OK);
    hUsbDeviceFS.dev_state = 0U;
    assert(UsbCdcPort_Submit(&byte, 1U) == USB_CDC_OFFLINE);
    return 0;
}
''', indexed=indexed)


@pytest.fixture
def native_project(tmp_path):
    root = tmp_path / "native"
    root.mkdir()
    content = {
        "test.ioc": "Mcu.CPN=STM32_UNKNOWN_EXPERIMENTAL\nUSB_DEVICE.CLASS_NAME_FS=Cdc\n",
        "main.c": "void SystemClock_Config(void) {} void IRQ(void) { HAL_PCD_IRQHandler(); } int main(void) { MX_USB_DEVICE_Init(); }",
        "main.h": "", "usbd_cdc.c": "void USBD_CDC_Init(void) {} void USBD_CDC_DeInit(void) {} void USBD_CDC_DataIn(void) {} void USBD_CDC_DataOut(void) {}",
        "usbd_cdc.h": "TxState",
        "usbd_core.c": "void USBD_Init(void) {} void USBD_SetClassConfig(void) {} void USBD_ClrClassConfig(void) {}",
        "usbd_core.h": "", "usbd_def.h": "pClassData", "usbd_cdc_if.h": "",
        "usbd_cdc_if.c": "void CDC_Init_FS(void) {} void CDC_DeInit_FS(void) {} void CDC_Transmit_FS(void) {} void CDC_Receive_FS(void) { USBD_CDC_ReceivePacket(); }",
        "usb_device.c": "void MX_USB_DEVICE_Init(void) { USBD_RegisterClass(&hUsbDeviceFS, &USBD_CDC); }",
        "usb_device.h": "", "usbd_conf.c": "void USBD_LL_Transmit(void) {} void USBD_LL_PrepareReceive(void) {} void USBD_LL_CloseEP(void) {} void USBD_static_malloc(void) { pcd.speed = PCD_SPEED_FULL; }",
        "usbd_conf.h": "#define USBD_malloc USBD_static_malloc\n",
        "usbd_ctlreq.c": "/* fixture */", "usbd_ctlreq.h": "",
        "usbd_ioreq.c": "/* fixture */", "usbd_ioreq.h": "",
        "usbd_desc.c": "/* fixture */", "usbd_desc.h": "",
        "startup.s": "Reset_Handler:", "memory.ld": "MEMORY {}", "LICENSE.md": "test fixture",
    }
    content["Makefile"] = ("C_SOURCES = " + " ".join(p for p in content if p.endswith(".c")) +
        "\nASM_SOURCES = startup.s\nC_INCLUDES = -IInc\nC_DEFS = -DUSE_HAL_DRIVER\nLDSCRIPT = memory.ld\nCPU = -mcpu=cortex-m3\n")
    (root / "Inc").mkdir()
    (root / "Inc/fixture.h").write_text("/* fixture include directory */")
    for name, text in content.items():
        (root / name).write_text(text)
    return root


def test_capability_is_not_a_family_admission_and_export_preserves_source(native_project, tmp_path):
    before = {p.relative_to(native_project).as_posix(): p.read_bytes() for p in native_project.rglob("*") if p.is_file()}
    plan = UsbTransport_Export(native_project, tmp_path / "kit")
    assert plan.result == UsbTransportPlanResult.Experimental
    assert plan.part == "STM32_UNKNOWN_EXPERIMENTAL"
    assert any("NOT PROVEN" in review for review in plan.review)
    assert plan.licenses == ("LICENSE.md",)
    assert (tmp_path / "kit/Common/Inc/silverstar_assert.h").read_bytes() == (COMMON / "silverstar_assert.h").read_bytes()
    assert before == {p.relative_to(native_project).as_posix(): p.read_bytes() for p in native_project.rglob("*") if p.is_file()}
    assert UsbTransport_Plan(native_project) == plan
    with pytest.raises(CubeMxImportError, match="already exist"):
        UsbTransport_Export(native_project, tmp_path / "kit")
    with pytest.raises(CubeMxImportError, match="disjoint"):
        UsbTransport_Export(native_project, native_project / "kit")


def test_changed_input_is_refused_before_publication(native_project, tmp_path, monkeypatch):
    import silverstar_fccg.app.usb_transport as backend
    original = backend.UsbTransport_Plan
    calls = 0
    def changed(path):
        nonlocal calls
        calls += 1
        if calls == 2:
            source = native_project / "main.c"
            source.write_text(source.read_text() + "\n/* changed input */\n")
        return original(path)
    monkeypatch.setattr(backend, "UsbTransport_Plan", changed)
    with pytest.raises(CubeMxImportError, match="changed during export"):
        UsbTransport_Export(native_project, tmp_path / "kit")
    assert not (tmp_path / "kit").exists()
    assert "changed input" in (native_project / "main.c").read_text()


def test_concurrently_created_output_is_not_replaced(native_project, tmp_path, monkeypatch):
    import silverstar_fccg.app.usb_transport as backend
    original = backend._AssertionFiles_Read
    calls = 0
    destination = tmp_path / "kit"
    def reserve():
        nonlocal calls
        calls += 1
        if calls == 2:
            destination.mkdir()
        return original()
    monkeypatch.setattr(backend, "_AssertionFiles_Read", reserve)
    with pytest.raises(FileExistsError):
        UsbTransport_Export(native_project, destination)
    assert destination.is_dir()
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("assertion_owner", ["BUNDLED", "EXISTING"])
def test_exported_cmake_builds_with_exactly_one_assertion_owner(native_project, tmp_path, assertion_owner):
    kit = tmp_path / "kit"
    UsbTransport_Export(native_project, kit)
    _PortHeaders_Write(tmp_path)
    (tmp_path / "main.c").write_text('''#include <assert.h>
#include "usb_cdc_transport.h"
#include "usb_device.h"
static USBD_CDC_HandleTypeDef cdc;
USBD_HandleTypeDef hUsbDeviceFS;
uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{ assert(data != 0 && length == 1U); return USBD_OK; }
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *device)
{ assert(device == &hUsbDeviceFS); return USBD_OK; }
int main(void)
{
    uint8_t byte = 7U;
    hUsbDeviceFS.dev_state = USBD_STATE_CONFIGURED;
    hUsbDeviceFS.pClassData = &cdc;
    assert(UsbCdc_Configure() == USB_CDC_OK);
    assert(UsbCdc_Write(&byte, 1U, UsbCdc_SessionGet()) == USB_CDC_OK);
    assert(UsbCdc_Service() == USB_CDC_OK);
    assert(UsbCdc_Service() == USB_CDC_OK);
    assert(UsbCdc_Write(&byte, 1U, UsbCdc_SessionGet()) == USB_CDC_OK);
    UsbCdc_LinkDown();
    assert(UsbCdc_Quiesced() == USB_CDC_OK);
    return 0;
}
''')
    existing = ('target_sources(kit_smoke PRIVATE "' +
                (COMMON.parent / "Src/silverstar_assert.c").as_posix() + '")\n') if assertion_owner == "EXISTING" else ""
    (tmp_path / "CMakeLists.txt").write_text('''cmake_minimum_required(VERSION 3.17)
project(UsbKitSmoke C)
add_executable(kit_smoke main.c)
target_include_directories(kit_smoke PRIVATE Inc)
target_compile_options(kit_smoke PRIVATE -Wall -Wextra -Werror -fanalyzer)
include(kit/usb_cdc_transport.cmake)
UsbCdc_Attach(kit_smoke ''' + assertion_owner + ")\n" + existing)
    for label, command in (
        ("configure", ["cmake", "-S", str(tmp_path), "-B", str(tmp_path / "build"), "-G", "Ninja",
            "-DCMAKE_C_COMPILER=" + shutil.which("gcc"), "-DCMAKE_MAKE_PROGRAM=" + shutil.which("ninja")]),
        ("build", ["cmake", "--build", str(tmp_path / "build"), "--verbose"]),
        ("run", [str(tmp_path / "build/kit_smoke.exe")]),
    ):
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf8")
        (tmp_path / (label + ".log")).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("file,change,reason", [
    ("usbd_cdc.c", None, "COMPLETE_NATIVE_CDC_REQUIRED"),
    ("test.ioc", "Mcu.IP0=USBX\n", "USBX_REQUIRES_SEPARATE_ADAPTER"),
    ("test.ioc", "Mcu.IP0=FREERTOS\n", "COMPOSITE_OR_RTOS_OWNER_UNSUPPORTED"),
    ("test.ioc", "Mcu.IP0=USB_OTG_HS\n", "HIGH_SPEED_OR_ALTERNATE_STACK_UNSUPPORTED"),
    ("usbd_conf.c", "pcd.Init.dma_enable = ENABLE;", "DMA_OR_DATA_CACHE_UNSUPPORTED"),
    ("main.c", "SCB_EnableDCache();", "DMA_OR_DATA_CACHE_UNSUPPORTED"),
    ("usb_device.c", "USBD_RegisterClass();", "SINGLE_CLASS_REQUIRED"),
    ("startup.s", None, "NATIVE_IRQ_AND_STARTUP_REQUIRED"),
    ("memory.ld", None, "NATIVE_LINKER_REQUIRED"),
])
def test_unsupported_capabilities_have_reasons(native_project, file, change, reason):
    path = native_project / file
    if change is None:
        path.unlink()
    else:
        path.write_text(path.read_text() + change)
    plan = UsbTransport_Plan(native_project)
    assert plan.result == UsbTransportPlanResult.Rejected
    assert reason in plan.reasons


@pytest.mark.parametrize("project", ["cube-f103-usb", "cube-f407-usb"])
def test_real_project_inspection_and_fingerprint(project, tmp_path):
    origin = os.environ.get("SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT")
    if not origin:
        pytest.skip("real generated CubeMX reference not configured")
    root = Path(origin) / project
    assert root.is_dir(), "configured native input missing"
    plan = UsbTransport_Export(root, tmp_path / "kit")
    assert plan.result == UsbTransportPlanResult.Experimental, plan.reasons
    assert plan.indexed == (project == "cube-f407-usb")
    assert all(hashlib.sha256((root / p).read_bytes()).hexdigest() == digest
               for p, digest in plan.files_sha256.items())
