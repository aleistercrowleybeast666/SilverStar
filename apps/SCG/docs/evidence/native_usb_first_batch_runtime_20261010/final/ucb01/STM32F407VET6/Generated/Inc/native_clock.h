#ifndef __NATIVE_CLOCK_H
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

#define NATIVE_CLOCK_HCLK_HZ 168000000U
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
