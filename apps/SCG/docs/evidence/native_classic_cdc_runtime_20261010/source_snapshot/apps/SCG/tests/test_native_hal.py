"""Actual recognized HAL function bodies, host MMIO mocks and fault injection.

These exercises preserve native input bytes and do not establish MCU timing,
arbitrary caller buffer safety, or all other vendor HAL entry points.
"""
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess

import pytest

from silverstar_fccg.generator.native_hal import (
    NativeHalDerivatives_Render, NativeC_FunctionSpanGet,
)


@pytest.fixture(params=["f103", "f407"])
def hal_sources(request):
    base = os.environ.get("SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT")
    if not base:
        pytest.skip("real complete native CDC inputs not configured")
    root = Path(base) / ("cube-" + request.param + "-usb")
    if not root.is_dir():
        pytest.fail("configured native project missing: " + str(root))
    paths = [p.relative_to(root).as_posix() for p in root.glob("Drivers/*_HAL_Driver/Src/*_hal_spi.c")]
    paths += [p.relative_to(root).as_posix() for p in root.glob("Drivers/*_HAL_Driver/Src/*_hal_uart.c")]
    return {p: (root / p).read_bytes() for p in paths}


def _Function_Get(text, name):
    start, _opening, end = NativeC_FunctionSpanGet(text, name)
    return text[start:end]


def _Compile(tmp_path, text, name, *, analyzer=True):
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC unavailable")
    source = tmp_path / (name + ".c")
    source.write_text(text, encoding="utf-8")
    executable = source.with_suffix(".exe")
    command = [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wpedantic"]
    if analyzer:
        command.append("-fanalyzer")
    result = subprocess.run([*command, str(source), "-o", str(executable)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return executable


def test_derivative_profile_originals_and_reproducible_patch(hal_sources, tmp_path):
    from silverstar_fccg.hardware.native_classic_cdc import NATIVE_PREFIX
    originals = dict(hal_sources)
    rendered, replacements, manifest = NativeHalDerivatives_Render(hal_sources, list(hal_sources))
    assert hal_sources == originals and len(replacements) == 2
    assert all(old not in rendered and new in rendered for old, new in replacements.items())
    for entry in manifest["entries"]:
        original = originals[entry["original"].removeprefix(NATIVE_PREFIX)]
        assert hashlib.sha256(original).hexdigest() == entry["original_sha256"]
        assert hashlib.sha256(rendered[entry["derived"]]).hexdigest() == entry["derived_sha256"]
        # Native Windows Git works without the MSYS signal-pipe service.
        patch = shutil.which("git")
        if patch is None:
            pytest.fail("Git is needed for derivative patch reproducibility")
        source = tmp_path / entry["original"]
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(original)
        result = subprocess.run([patch, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
                                 "apply", "--no-index", "-p0", "-"],
                                input=rendered[entry["patch"]], cwd=tmp_path,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        assert result.returncode == 0, result.stdout.decode(errors="replace")
        assert source.read_bytes() == rendered[entry["derived"]]


def test_unknown_hal_source_bytes_rejected(hal_sources):
    for path in hal_sources:
        changed = {**hal_sources, path: hal_sources[path] + b"\n/* unreviewed */\n"}
        with pytest.raises(ValueError, match="Unreviewed native HAL source bytes"):
            NativeHalDerivatives_Render(changed, list(changed))


_UART_MOCK = '''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;
typedef struct { uint32_t DR; } UartRegisters;
typedef struct { uint32_t WordLength, Parity; } UartInit;
typedef struct {
    UartRegisters *Instance; UartInit Init;
    uint32_t gState, RxState, ErrorCode, ReceptionType, RxEventType;
    uint16_t TxXferSize, TxXferCount, RxXferSize, RxXferCount;
} UART_HandleTypeDef;
#define HAL_UART_STATE_READY 1U
#define HAL_UART_STATE_BUSY_TX 2U
#define HAL_UART_STATE_BUSY_RX 3U
#define HAL_UART_ERROR_NONE 0U
#define HAL_UART_RECEPTION_TOIDLE 1U
#define HAL_UART_RXEVENT_TC 1U
#define HAL_UART_RXEVENT_IDLE 2U
#define UART_WORDLENGTH_8B 8U
#define UART_WORDLENGTH_9B 9U
#define UART_PARITY_NONE 0U
#define UART_FLAG_TXE 1U
#define UART_FLAG_TC 2U
#define UART_FLAG_IDLE 3U
#define UART_FLAG_RXNE 4U
#define HAL_MAX_DELAY UINT32_MAX
#define RESET 0U
static uint32_t native_tick, rx_enabled=1U;
static HAL_StatusTypeDef wait_result=HAL_OK;
static uint32_t HAL_GetTick(void) { return native_tick++; }
static HAL_StatusTypeDef UART_WaitOnFlagUntilTimeout(UART_HandleTypeDef *h,
    uint32_t flag, uint32_t state, uint32_t tick, uint32_t timeout)
{ (void)h; (void)flag; (void)state; (void)tick; (void)timeout; return wait_result; }
#define __HAL_UART_GET_FLAG(h,f) ((void)(h), ((f)==UART_FLAG_RXNE ? rx_enabled : 0U))
#define __HAL_UART_CLEAR_IDLEFLAG(h) ((void)(h))
'''

_UART_MAIN = '''
static uint16_t buffer[65537];
int main(int argc, char **argv)
{
    UartRegisters registers={0U};
    UART_HandleTypeDef uart={.Instance=&registers,
        .Init={UART_WORDLENGTH_8B,UART_PARITY_NONE},
        .gState=HAL_UART_STATE_READY,.RxState=HAL_UART_STATE_READY};
    assert(argc==2);
    if (strcmp(argv[1],"fault-tx")==0 || strcmp(argv[1],"fault-rx")==0)
    {
        uint16_t received=0U;
        uart.Init.WordLength=UART_WORDLENGTH_9B;
        if (strcmp(argv[1],"fault-tx")==0)
        { assert(HAL_UART_Transmit(&uart,(uint8_t *)&buffer[1],1U,100U)==HAL_ERROR);
          assert(uart.gState==HAL_UART_STATE_READY && registers.DR==0U); }
        else
        { assert(HAL_UARTEx_ReceiveToIdle(&uart,(uint8_t *)&buffer[1],1U,&received,100U)==HAL_ERROR);
          assert(uart.RxState==HAL_UART_STATE_READY && received==0U); }
        return 0;
    }
    const uint16_t sizes[]={1U,3U,65535U};
    for (uint32_t mode=0U;mode<2U;mode++)
    {
        uart.Init.WordLength=mode==0U ? UART_WORDLENGTH_8B : UART_WORDLENGTH_9B;
        for (uint32_t item=0U;item<3U;item++)
        {
            uint16_t received=0U;
            uint16_t size=sizes[item];
            buffer[0]=0xCAFEU; buffer[65536]=0xBEEFU;
            for (uint32_t i=1U;i<65536U;i++) { buffer[i]=0x01A5U; }
            uint16_t expected=mode==0U ? ((uint8_t *)&buffer[1])[size-1U] : buffer[size];
            assert(HAL_UART_Transmit(&uart,(uint8_t *)&buffer[1],size,HAL_MAX_DELAY)==HAL_OK);
            assert(registers.DR==expected && uart.TxXferCount==0U && uart.gState==HAL_UART_STATE_READY);
            registers.DR=0x1A5U;
            assert(HAL_UARTEx_ReceiveToIdle(&uart,(uint8_t *)&buffer[1],size,&received,HAL_MAX_DELAY)==HAL_OK);
            assert(received==size && uart.RxXferCount==0U && uart.RxState==HAL_UART_STATE_READY);
            assert((mode==0U ? ((uint8_t *)&buffer[1])[size-1U] : buffer[size])==(mode==0U ? 0xA5U : 0x1A5U));
            assert(buffer[0]==0xCAFEU && buffer[65536]==0xBEEFU);
        }
    }
    uint16_t received=0xABCDU;
    assert(HAL_UART_Transmit(&uart,NULL,1U,1U)==HAL_ERROR);
    assert(HAL_UART_Transmit(&uart,(uint8_t *)buffer,0U,1U)==HAL_ERROR);
    assert(HAL_UARTEx_ReceiveToIdle(&uart,NULL,1U,&received,1U)==HAL_ERROR && received==0xABCDU);
    wait_result=HAL_TIMEOUT;
    assert(HAL_UART_Transmit(&uart,(uint8_t *)buffer,1U,1U)==HAL_TIMEOUT && uart.gState==HAL_UART_STATE_READY);
    rx_enabled=0U;
    assert(HAL_UARTEx_ReceiveToIdle(&uart,(uint8_t *)buffer,1U,&received,0U)==HAL_TIMEOUT);
    assert(received==0U && uart.RxState==HAL_UART_STATE_READY);
    return 0;
}
'''


def test_actual_uart_bodies_valid_buffers_and_internal_pointer_fault(hal_sources, tmp_path):
    rendered, _replacements, manifest = NativeHalDerivatives_Render(hal_sources, list(hal_sources))
    entry = next(item for item in manifest["entries"] if item["kind"] == "uart")
    original = next(content.decode("utf-8-sig") for path, content in hal_sources.items() if path.endswith("_hal_uart.c"))
    derived = rendered[entry["derived"]].decode("utf-8")
    names = ("HAL_UART_Transmit", "HAL_UARTEx_ReceiveToIdle")
    for label, source, analyzer in (("original", original, False), ("derived", derived, True)):
        bodies = "\n".join(_Function_Get(source, name) for name in names)
        executable = _Compile(tmp_path, _UART_MOCK + bodies + _UART_MAIN, label, analyzer=analyzer)
        run = subprocess.run([str(executable), "normal"], capture_output=True, text=True, timeout=15)
        assert run.returncode == 0, run.stdout + run.stderr
    # Test-only corruption of a local alternate pointer immediately before its
    # use, not evidence that a valid upstream caller causes the analyzer path.
    bodies = "\n".join(_Function_Get(derived, name) for name in names)
    bodies, count = re.subn(r"if\s*\(pdata8bits\s*==\s*NULL\)",
                           "pdata16bits = NULL;\n      if (pdata8bits == NULL)", bodies)
    assert count == 2
    executable = _Compile(tmp_path, _UART_MOCK + bodies + _UART_MAIN, "pointer_fault")
    for scenario in ("fault-tx", "fault-rx"):
        run = subprocess.run([str(executable), scenario], capture_output=True, text=True, timeout=15)
        assert run.returncode == 0, run.stdout + run.stderr


_SPI_MOCK = '''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;
typedef enum { RESET, SET } FlagStatus;
typedef uint32_t HAL_SPI_StateTypeDef;
typedef struct { uint32_t DR, CR1; } SpiRegisters;
typedef struct { uint32_t Direction, DataSize, Mode, CRCCalculation; } SpiInit;
typedef struct {
    SpiRegisters *Instance; SpiInit Init;
    uint32_t State, ErrorCode, Lock;
    const uint8_t *pTxBuffPtr; uint8_t *pRxBuffPtr;
    uint16_t TxXferSize, TxXferCount, RxXferSize, RxXferCount;
    void *TxISR, *RxISR;
} SPI_HandleTypeDef;
#define HAL_SPI_STATE_READY 1U
#define HAL_SPI_STATE_BUSY_TX 2U
#define HAL_SPI_STATE_BUSY_RX 3U
#define HAL_SPI_STATE_BUSY_TX_RX 4U
#define HAL_SPI_ERROR_NONE 0U
#define HAL_SPI_ERROR_FLAG 1U
#define SPI_MODE_MASTER 1U
#define SPI_MODE_SLAVE 2U
#define SPI_DIRECTION_2LINES 1U
#define SPI_DIRECTION_1LINE 2U
#define SPI_DIRECTION_2LINES_RXONLY 3U
#define SPI_DATASIZE_8BIT 8U
#define SPI_DATASIZE_16BIT 16U
#define SPI_CRCCALCULATION_DISABLE 0U
#define SPI_CRCCALCULATION_ENABLE 1U
#define SPI_CR1_SPE 1U
#define SPI_FLAG_TXE 1U
#define SPI_FLAG_RXNE 2U
#define SPI_FLAG_BSY 4U
#define SPI_IT_TXE 1U
#define SPI_IT_RXNE 2U
#define SPI_IT_ERR 4U
#define HAL_MAX_DELAY UINT32_MAX
#define USE_SPI_CRC 0U
#define SPI_BSY_FLAG_WORKAROUND_TIMEOUT 1000U
#define __IO volatile
#define IS_SPI_DIRECTION_2LINES_OR_1LINE(v) ((v)==SPI_DIRECTION_2LINES || (v)==SPI_DIRECTION_1LINE)
#define IS_SPI_DIRECTION_2LINES(v) ((v)==SPI_DIRECTION_2LINES)
#define assert_param(v) assert(v)
#define SET_BIT(r,v) ((r)|=(v))
#define __HAL_LOCK(h) do { if ((h)->Lock!=0U) { return HAL_BUSY; } (h)->Lock=1U; } while (0)
#define __HAL_UNLOCK(h) ((h)->Lock=0U)
#define __HAL_SPI_ENABLE(h) ((h)->Instance->CR1|=SPI_CR1_SPE)
#define __HAL_SPI_DISABLE(h) ((h)->Instance->CR1&=~SPI_CR1_SPE)
#define SPI_1LINE_TX(h) ((void)(h))
static uint32_t disabled_interrupts, crc_resets, flags_cleared;
#define __HAL_SPI_DISABLE_IT(h,v) ((void)(h), disabled_interrupts=(v))
#define SPI_RESET_CRC(h) ((void)(h), crc_resets++)
#define __HAL_SPI_CLEAR_OVRFLAG(h) ((void)(h), flags_cleared++)
static volatile uint32_t flags=SPI_FLAG_TXE|SPI_FLAG_RXNE;
#define __HAL_SPI_GET_FLAG(h,f) ((void)(h), flags & (f))
static uint32_t SystemCoreClock=72000000U;
static uint32_t HAL_GetTick(void) { return 1000U; }
'''

_SPI_MAIN = '''
int main(int argc, char **argv)
{
    uint8_t tx[262]={0xCAU,1U,2U,3U}, rx[262]={0xBEU};
    tx[261]=0xFEU; rx[261]=0xEFU;
    SpiRegisters registers={0U};
    SPI_HandleTypeDef spi={.Instance=&registers,
        .Init={SPI_DIRECTION_2LINES,SPI_DATASIZE_8BIT,SPI_MODE_MASTER,SPI_CRCCALCULATION_DISABLE},
        .State=HAL_SPI_STATE_READY};
    assert(argc==2);
    if (strcmp(argv[1],"normal")==0)
    {
        assert(HAL_SPI_Transmit(&spi,&tx[1],260U,100U)==HAL_OK);
        assert(spi.Lock==0U && spi.State==HAL_SPI_STATE_READY && spi.TxXferCount==0U);
        assert(HAL_SPI_TransmitReceive(&spi,&tx[1],&rx[1],260U,100U)==HAL_OK);
        assert(spi.RxXferCount==0U && spi.TxXferCount==0U && spi.Lock==0U);
        assert(tx[0]==0xCAU && tx[261]==0xFEU && rx[0]==0xBEU && rx[261]==0xEFU);
        assert(HAL_SPI_Transmit(&spi,NULL,1U,100U)==HAL_ERROR);
        assert(HAL_SPI_TransmitReceive(&spi,tx,NULL,1U,100U)==HAL_ERROR);
        spi.State=HAL_SPI_STATE_BUSY_TX;
        assert(HAL_SPI_Transmit(&spi,tx,1U,100U)==HAL_BUSY);
        return 0;
    }
    flags=0U;
    if (strcmp(argv[1],"tx-stopped")==0)
    { assert(HAL_SPI_Transmit(&spi,&tx[1],260U,100U)==HAL_TIMEOUT); }
    else if (strcmp(argv[1],"rx-stopped")==0)
    { assert(HAL_SPI_TransmitReceive(&spi,&tx[1],&rx[1],260U,100U)==HAL_TIMEOUT); }
    else
    {
        spi.State=HAL_SPI_STATE_BUSY_TX; spi.Lock=1U;
        spi.Init.Direction=SPI_DIRECTION_1LINE;
        spi.Init.CRCCalculation=SPI_CRCCALCULATION_ENABLE;
        registers.CR1=SPI_CR1_SPE;
        assert(SPI_WaitFlagStateUntilTimeout(&spi,SPI_FLAG_TXE,SET,HAL_MAX_DELAY,1000U)==HAL_TIMEOUT);
        assert(disabled_interrupts==(SPI_IT_TXE|SPI_IT_RXNE|SPI_IT_ERR));
        assert(registers.CR1==0U && crc_resets==1U);
    }
    assert(spi.Lock==0U && spi.State==HAL_SPI_STATE_READY);
    assert(tx[0]==0xCAU && tx[261]==0xFEU && rx[0]==0xBEU && rx[261]==0xEFU);
    return 0;
}
'''


def test_actual_spi_stopped_tick_pre_failure_and_bounded_derivative(hal_sources, tmp_path):
    rendered, _replacements, manifest = NativeHalDerivatives_Render(hal_sources, list(hal_sources))
    entry = next(item for item in manifest["entries"] if item["kind"] == "spi")
    original = next(content.decode("utf-8-sig") for path, content in hal_sources.items() if path.endswith("_hal_spi.c"))
    derived = rendered[entry["derived"]].decode("utf-8")
    names = ("SPI_WaitFlagStateUntilTimeout", "SPI_EndRxTxTransaction", "HAL_SPI_Transmit", "HAL_SPI_TransmitReceive")
    for label, source, analyzer in (("spi_original", original, False), ("spi_derived", derived, True)):
        bodies = "\n".join(_Function_Get(source, name) for name in names)
        executable = _Compile(tmp_path, _SPI_MOCK + bodies + _SPI_MAIN, label, analyzer=analyzer)
        run = subprocess.run([str(executable), "normal"], capture_output=True, text=True, timeout=10)
        assert run.returncode == 0, run.stdout + run.stderr
        for scenario in ("tx-stopped", "rx-stopped", "wait-stopped"):
            if label == "spi_original":
                # Only our isolated Host subprocess is terminated on timeout.
                with pytest.raises(subprocess.TimeoutExpired):
                    subprocess.run([str(executable), scenario], capture_output=True, text=True, timeout=1)
            else:
                run = subprocess.run([str(executable), scenario], capture_output=True, text=True, timeout=10)
                assert run.returncode == 0, run.stdout + run.stderr
