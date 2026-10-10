"""Owned clock/critical templates for the experimental native Ground route.

The port samples native SysTick and HAL tick; it does not configure either and
does not use DWT. Generated runtime entry points remain behind the route gate.
"""
from __future__ import annotations

import re

from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet, NativeC_VisibleGet


def NativeClockSourceContract_Validate(files: dict[str, bytes], sources: list[str] | tuple[str, ...],
                                      *, hclk_hz: int) -> dict:
    iocs = [p for p in files if p.endswith(".ioc") and "/" not in p]
    fields = (dict(line.split("=", 1) for line in files[iocs[0]].decode(
              "utf-8-sig").splitlines() if "=" in line) if len(iocs) == 1 else {})
    if fields.get("NVIC.TimeBaseIP", "").startswith("TIM"):
        raise ValueError("Native timer timebase requires its own reviewed counter port; SysTick adapter is unsupported")
    def body(name: str) -> tuple[str, str]:
        owners = []
        for path in sources:
            text = files[path].decode("utf-8-sig")
            try:
                _start, opening, end = NativeC_FunctionSpanGet(text, name)
            except ValueError:
                continue
            owners.append((path, NativeC_VisibleGet(text)[opening + 1:end - 1]))
        if len(owners) != 1:
            raise ValueError("Native clock requires one actual owner: " + name)
        return owners[0]
    tick_path, tick = body("HAL_GetTick")
    increment_path, increment = body("HAL_IncTick")
    irq_path, irq = body("SysTick_Handler")
    if (re.sub(r"\s", "", tick) != "returnuwTick;" or
            re.sub(r"\s", "", increment) not in {"uwTick+=(uint32_t)uwTickFreq;", "uwTick+=uwTickFreq;"} or
            re.sub(r"\s", "", irq) != "HAL_IncTick();"):
        raise ValueError("Unreviewed native HAL tick read/increment/IRQ body")
    hal = NativeC_VisibleGet(files[tick_path].decode("utf-8-sig"))
    if tick_path != increment_path or not re.search(
            r"HAL_TickFreqTypeDef\s+uwTickFreq\s*=\s*HAL_TICK_FREQ_DEFAULT\s*;", hal):
        raise ValueError("Native HAL tick frequency owner differs from the reviewed default")
    if fields.get("RCC.HCLKFreq_Value") != str(hclk_hz):
        raise ValueError("Reviewed native HCLK differs from its clock inventory")
    return {"tick_owner": tick_path, "increment_owner": increment_path, "irq_owner": irq_path,
            "hclk_hz": hclk_hz, "runtime_policy": "Actual HAL/RCC/SysTick configuration and bounded progress probe required; no DWT"}


def NativeClock_FilesRender(*, hclk_hz: int) -> dict[str, bytes]:
    if type(hclk_hz) is not int or not 1_000_000 <= hclk_hz <= 200_000_000 or hclk_hz % 1_000_000:
        raise ValueError("Native SysTick clock needs an integral 1..200 MHz reviewed HCLK")
    header = '''#ifndef __NATIVE_CLOCK_H
#define __NATIVE_CLOCK_H
#include <stdint.h>
#include "platform_types.h"

typedef enum
{
    NativeClockResult_Ok = 0,
    NativeClockResult_NotInitialized,
    NativeClockResult_InvalidArgument,
    NativeClockResult_InvalidContext,
    NativeClockResult_InvalidConfiguration,
    NativeClockResult_UnstableSnapshot,
    NativeClockResult_Stopped,
    NativeClockResult_Discontinuous
} NativeClockResult;

typedef struct
{
    uint32_t tick_ms;
    uint32_t elapsed_cycles;
} NativeClockSnapshot;

#define NATIVE_CLOCK_HCLK_HZ @HCLK@U
#define NATIVE_CLOCK_CYCLES_PER_US (NATIVE_CLOCK_HCLK_HZ / 1000000U)
#define NATIVE_CLOCK_DELAY_LIMIT_US 100000U
#define NATIVE_CLOCK_POLL_LIMIT 2000000U

NativeClockResult NativeClockPort_SnapshotGet(NativeClockSnapshot *snapshot);
uint8_t NativeClock_ContextAllowedGet(void);
NativeClockResult NativeClock_Read(uint64_t *now_us);
NativeClockResult NativeClock_DelayUs(uint32_t delay_us);
NativeClockResult NativeClock_StatusGet(void);
void NativeClock_FaultRecord(NativeClockResult reason);
#endif /* __NATIVE_CLOCK_H */
'''.replace("@HCLK@", str(hclk_hz))
    critical = '''#include "platform_critical.h"
#include "main.h"
#include "silverstar_assert.h"

PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState saved = __get_PRIMASK();
    __disable_irq();
    __DMB();
    return saved;
}

void PlatformCritical_Exit(PlatformCriticalState saved)
{
    SILVERSTAR_ASSERT(saved <= 1U, SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    __DMB();
    __set_PRIMASK(saved);
}
'''
    port = '''#include "native_clock.h"
#include "platform_critical.h"
#include "main.h"

uint8_t NativeClock_ContextAllowedGet(void)
{
    return ((__get_IPSR() == 0U) && (__get_PRIMASK() == 0U)) ? 1U : 0U;
}
#include <stddef.h>

NativeClockResult NativeClockPort_SnapshotGet(NativeClockSnapshot *snapshot)
{
    uint32_t attempt;
    uint32_t control;
    uint32_t reload;
    if (snapshot == NULL) { return NativeClockResult_InvalidArgument; }
    if ((__get_IPSR() != 0U) || (__get_PRIMASK() != 0U))
    { return NativeClockResult_InvalidContext; }
    control = SysTick->CTRL;
    reload = SysTick->LOAD;
    if ((SystemCoreClock != NATIVE_CLOCK_HCLK_HZ) ||
        (HAL_RCC_GetHCLKFreq() != NATIVE_CLOCK_HCLK_HZ) ||
        (HAL_GetTickFreq() != HAL_TICK_FREQ_1KHZ) ||
        ((control & (SysTick_CTRL_ENABLE_Msk | SysTick_CTRL_TICKINT_Msk |
          SysTick_CTRL_CLKSOURCE_Msk)) != (SysTick_CTRL_ENABLE_Msk |
          SysTick_CTRL_TICKINT_Msk | SysTick_CTRL_CLKSOURCE_Msk)) ||
        (reload != (NATIVE_CLOCK_HCLK_HZ / 1000U - 1U)))
    { return NativeClockResult_InvalidConfiguration; }
    for (attempt = 0U; attempt < 3U; attempt++)
    {
        PlatformCriticalState saved = PlatformCritical_Enter();
        uint32_t pending_before = SCB->ICSR & SCB_ICSR_PENDSTSET_Msk;
        uint32_t tick = HAL_GetTick();
        uint32_t counter = SysTick->VAL;
        uint32_t pending_after = SCB->ICSR & SCB_ICSR_PENDSTSET_Msk;
        PlatformCritical_Exit(saved);
        /* VAL zero is the wrap/reload boundary; do not publish that sample.
         * The bounded critical section contains only the recognized HAL tick
         * read and register samples. Division happens after PRIMASK restore. */
        if ((pending_before == pending_after) && (counter != 0U) &&
            (counter <= reload))
        {
            snapshot->tick_ms = tick + ((pending_before != 0U) ? 1U : 0U);
            snapshot->elapsed_cycles = reload - counter;
            return NativeClockResult_Ok;
        }
    }
    return NativeClockResult_UnstableSnapshot;
}
'''
    clock = '''#include "native_clock.h"
#include "platform_time.h"
#include "silverstar_assert.h"
#include <stddef.h>

static NativeClockResult s_clock_result = NativeClockResult_NotInitialized;
static uint32_t s_last_tick;
static uint64_t s_total_ms;
static uint64_t s_last_us;

NativeClockResult NativeClock_StatusGet(void) { return s_clock_result; }

void NativeClock_FaultRecord(NativeClockResult reason)
{
    if ((reason != NativeClockResult_Ok) &&
        (s_clock_result == NativeClockResult_Ok)) { s_clock_result = reason; }
}

static NativeClockResult NativeClock_Update(const NativeClockSnapshot *sample)
{
    uint32_t delta = sample->tick_ms - s_last_tick;
    uint64_t next;
    SILVERSTAR_ASSERT(s_last_us / 1000ULL == s_total_ms,
        SILVERSTAR_ASSERT_MODULE_GENERATED, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_total_ms <= (UINT64_MAX / 1000ULL - 10000ULL),
        SILVERSTAR_ASSERT_MODULE_GENERATED, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if ((delta > 10000U) || (sample->elapsed_cycles >= NATIVE_CLOCK_HCLK_HZ / 1000U))
    { return NativeClockResult_Discontinuous; }
    next = (s_total_ms + delta) * 1000ULL +
        sample->elapsed_cycles / NATIVE_CLOCK_CYCLES_PER_US;
    if (next < s_last_us) { return NativeClockResult_Discontinuous; }
    s_total_ms += delta;
    s_last_tick = sample->tick_ms;
    s_last_us = next;
    return NativeClockResult_Ok;
}

NativeClockResult NativeClock_Read(uint64_t *now_us)
{
    NativeClockSnapshot sample;
    NativeClockResult result;
    if (now_us == NULL) { return NativeClockResult_InvalidArgument; }
    if (s_clock_result != NativeClockResult_Ok) { return s_clock_result; }
    result = NativeClockPort_SnapshotGet(&sample);
    if (result == NativeClockResult_Ok) { result = NativeClock_Update(&sample); }
    if (result != NativeClockResult_Ok)
    { NativeClock_FaultRecord(result); return result; }
    *now_us = s_last_us;
    return NativeClockResult_Ok;
}

NativeClockResult NativeClock_DelayUs(uint32_t delay_us)
{
    uint64_t start;
    uint64_t now;
    uint32_t poll;
    NativeClockResult result;
    if (delay_us > NATIVE_CLOCK_DELAY_LIMIT_US)
    { return NativeClockResult_InvalidArgument; }
    result = NativeClock_Read(&start);
    if (result != NativeClockResult_Ok) { return result; }
    for (poll = 0U; poll < NATIVE_CLOCK_POLL_LIMIT; poll++)
    {
        result = NativeClock_Read(&now);
        if (result != NativeClockResult_Ok) { return result; }
        if (now - start >= delay_us) { return NativeClockResult_Ok; }
    }
    NativeClock_FaultRecord(NativeClockResult_Stopped);
    return NativeClockResult_Stopped;
}

PlatformResult PlatformTime_Init(void)
{
    NativeClockSnapshot sample;
    NativeClockResult result;
    if (s_clock_result == NativeClockResult_Ok) { return PLATFORM_ALREADY_INITIALIZED; }
    if (s_clock_result != NativeClockResult_NotInitialized) { return PLATFORM_NOT_READY; }
    result = NativeClockPort_SnapshotGet(&sample);
    if (result != NativeClockResult_Ok) { s_clock_result = result; return PLATFORM_NOT_READY; }
    if (sample.elapsed_cycles >= NATIVE_CLOCK_HCLK_HZ / 1000U)
    { s_clock_result = NativeClockResult_InvalidConfiguration; return PLATFORM_NOT_READY; }
    s_last_tick = sample.tick_ms;
    s_total_ms = sample.tick_ms;
    s_last_us = s_total_ms * 1000ULL + sample.elapsed_cycles / NATIVE_CLOCK_CYCLES_PER_US;
    s_clock_result = NativeClockResult_Ok;
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok) { return PLATFORM_NOT_READY; }
    return PLATFORM_OK;
}

uint64_t PlatformTime_Us(void)
{
    uint64_t now = s_last_us;
    NativeClockResult result = NativeClock_Read(&now);
    if (result != NativeClockResult_Ok) { NativeClock_FaultRecord(result); }
    return now;
}

uint32_t PlatformTime_Ms(void) { return (uint32_t)(PlatformTime_Us() / 1000ULL); }

void PlatformTime_DelayMs(uint32_t delay_ms)
{
    NativeClockResult result;
    if (delay_ms > NATIVE_CLOCK_DELAY_LIMIT_US / 1000U)
    { NativeClock_FaultRecord(NativeClockResult_InvalidArgument); return; }
    result = NativeClock_DelayUs(delay_ms * 1000U);
    if (result != NativeClockResult_Ok) { NativeClock_FaultRecord(result); }
}
'''
    return {path: text.encode("utf-8") for path, text in {
        "Generated/Inc/native_clock.h": header,
        "Generated/Src/native_clock.c": clock,
        "Generated/Src/native_clock_port.c": port,
        "Generated/Src/native_critical.c": critical,
    }.items()}
