"""Main-owned Ground lifecycle; clock faults retire radio and PC publication."""


def NativeRuntime_FilesRender(*, transport_fault=False) -> dict[str, bytes]:
    header = '''#ifndef __NATIVE_RUNTIME_H
#define __NATIVE_RUNTIME_H
#include <stdint.h>
typedef enum {
    NativeRuntimeResult_Ok,
    NativeRuntimeResult_NotReady,
    NativeRuntimeResult_ClockFailure,
    NativeRuntimeResult_PlatformFailure,
    NativeRuntimeResult_RadioFailure,
    NativeRuntimeResult_PcFailure,
    NativeRuntimeResult_RetirementFailure
} NativeRuntimeResult;
NativeRuntimeResult NativeRuntime_Init(void);
NativeRuntimeResult NativeRuntime_Process(void);
uint8_t NativeRuntime_ReadyGet(void);
#endif /* __NATIVE_RUNTIME_H */
'''
    runtime = '''#include "native_runtime.h"
#include "native_platform.h"
#include "native_clock.h"
#include "ground_bridge.h"
#include "pc_byte_stream.h"
#include "platform_time.h"
#include "sx1281_device.h"
#include "native_usb_state.h"
#include "silverstar_assert.h"

typedef enum { NativeRuntimeState_Cold, NativeRuntimeState_Starting,
    NativeRuntimeState_Ready, NativeRuntimeState_Fault } NativeRuntimeState;
static volatile NativeRuntimeState s_state;
static uint8_t s_platform_started;
static NativeRuntimeResult s_fault = NativeRuntimeResult_NotReady;

uint8_t NativeRuntime_ReadyGet(void)
{
    SILVERSTAR_ASSERT((uint32_t)s_state <= (uint32_t)NativeRuntimeState_Fault,
        SILVERSTAR_ASSERT_MODULE_GENERATED, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    return ((s_state == NativeRuntimeState_Ready) &&
        (NativeClock_StatusGet() == NativeClockResult_Ok)) ? 1U : 0U;
}

static NativeRuntimeResult NativeRuntime_Abort(NativeRuntimeResult reason)
{
    s_state = NativeRuntimeState_Fault;
    PcByteStream_OnUsbReset();
    GroundBridge_PcReset();
    if (NativeUsb_Stop() != NativeUsbResult_Ok)
    { reason = NativeRuntimeResult_RetirementFailure; }
    if (s_platform_started != 0U)
    {
        /* Called only after the synchronous bridge/radio owner has returned.
         * Deactivate drops READY/queues and holds RESET without SPI or delays. */
        if (Lora_Deactivate(0U) != LoraDeactivateResult_Ok)
        { reason = NativeRuntimeResult_RetirementFailure; }
        s_platform_started = 0U;
    }
    /* Admission proves native GPIO initialization precedes this lifecycle.
     * Hold RESET even when clock/platform initialization never succeeded. */
    NativePlatform_Quiesce();
    s_fault = reason;
    return reason;
}

NativeRuntimeResult NativeRuntime_Init(void)
{
    GroundBridgeResult bridge;
    LoraChipStatus chip;
    if (s_state != NativeRuntimeState_Cold) { return NativeRuntimeResult_NotReady; }
    s_state = NativeRuntimeState_Starting;
    if (PlatformTime_Init() != PLATFORM_OK)
    { return NativeRuntime_Abort(NativeRuntimeResult_ClockFailure); }
    if (NativePlatform_Init() != PLATFORM_OK)
    { return NativeRuntime_Abort(NativeRuntimeResult_PlatformFailure); }
    s_platform_started = 1U;
    bridge = GroundBridge_Init();
    /* Initial STATUS remains queued while Starting; the PC adapter's ready
     * gate prevents transmission before this post-initialization probe. */
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok)
    { return NativeRuntime_Abort(NativeRuntimeResult_ClockFailure); }
    if ((bridge != GROUND_BRIDGE_OK) && (bridge != GROUND_BRIDGE_RADIO_ERROR) &&
        (bridge != GROUND_BRIDGE_PC_ERROR))
    { return NativeRuntime_Abort(NativeRuntimeResult_NotReady); }
    if (bridge != GROUND_BRIDGE_OK)
    { return NativeRuntime_Abort((bridge == GROUND_BRIDGE_RADIO_ERROR) ?
        NativeRuntimeResult_RadioFailure : NativeRuntimeResult_PcFailure); }
    /* Ground's void StartRx can invalidate the driver after Init reported OK.
     * Read its coherent cached postcondition before publishing readiness. */
    if ((Lora_ChipStatusGet(0U, &chip) != LORA_DIAG_RESULT_OK) || (chip.verified != 1U))
    { return NativeRuntime_Abort(NativeRuntimeResult_RadioFailure); }
    s_state = NativeRuntimeState_Ready;
    return NativeRuntimeResult_Ok;
}

NativeRuntimeResult NativeRuntime_Process(void)
{
    uint64_t now_us;
    GroundBridgeResult bridge;
    if (s_state == NativeRuntimeState_Fault) { return s_fault; }
    if (s_state != NativeRuntimeState_Ready) { return NativeRuntimeResult_NotReady; }
    if ((NativeClock_DelayUs(1U) != NativeClockResult_Ok) ||
        (NativeClock_Read(&now_us) != NativeClockResult_Ok))
    { return NativeRuntime_Abort(NativeRuntimeResult_ClockFailure); }
    bridge = GroundBridge_Process((uint32_t)(now_us / 1000ULL));
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok)
    { return NativeRuntime_Abort(NativeRuntimeResult_ClockFailure); }
    /* Radio timeouts and PC transport errors retain their ordinary diagnostic
     * paths. A clock failure instead permanently cancels runtime publication. */
    if (bridge == GROUND_BRIDGE_RADIO_ERROR) { return NativeRuntimeResult_RadioFailure; }
    if (bridge == GROUND_BRIDGE_PC_ERROR) { return NativeRuntimeResult_PcFailure; }
    if (bridge != GROUND_BRIDGE_OK)
    { return NativeRuntime_Abort(NativeRuntimeResult_NotReady); }
    return NativeRuntimeResult_Ok;
}
'''
    if transport_fault:
        header=header.replace('uint8_t NativeRuntime_ReadyGet(void);',
            'uint8_t NativeRuntime_ReadyGet(void);\nvoid NativeRuntime_TransportFaultRecord(void);')
        runtime=runtime.replace('static uint8_t s_platform_started;',
            'static uint8_t s_platform_started;\nstatic volatile uint8_t s_transport_fault;\n'
            '/* IRQ/main may latch a stored transport fault. Only the main owner\n'
            ' * retires USB/radio; the latch is never cleared after publication. */\n'
            'void NativeRuntime_TransportFaultRecord(void) { s_transport_fault = 1U; }')
        runtime=runtime.replace('(s_state == NativeRuntimeState_Ready) &&',
            '(s_state == NativeRuntimeState_Ready) && (s_transport_fault == 0U) &&')
        runtime=runtime.replace('    s_state = NativeRuntimeState_Starting;',
            '    if (s_transport_fault != 0U) { return NativeRuntime_Abort(NativeRuntimeResult_PcFailure); }\n'
            '    s_state = NativeRuntimeState_Starting;')
        runtime=runtime.replace('    if (s_state != NativeRuntimeState_Ready) { return NativeRuntimeResult_NotReady; }',
            '    if (s_state != NativeRuntimeState_Ready) { return NativeRuntimeResult_NotReady; }\n'
            '    if (s_transport_fault != 0U) { return NativeRuntime_Abort(NativeRuntimeResult_PcFailure); }')
        runtime=runtime.replace('    s_state = NativeRuntimeState_Ready;',
            '    if (s_transport_fault != 0U) { return NativeRuntime_Abort(NativeRuntimeResult_PcFailure); }\n'
            '    s_state = NativeRuntimeState_Ready;')
        runtime=runtime.replace('    /* Radio timeouts and PC transport errors',
            '    if (s_transport_fault != 0U) { return NativeRuntime_Abort(NativeRuntimeResult_PcFailure); }\n'
            '    /* Radio timeouts and PC transport errors')
    return {'Generated/Inc/native_runtime.h':header.encode('utf-8'),
            'Generated/Src/native_runtime.c':runtime.encode('utf-8')}
