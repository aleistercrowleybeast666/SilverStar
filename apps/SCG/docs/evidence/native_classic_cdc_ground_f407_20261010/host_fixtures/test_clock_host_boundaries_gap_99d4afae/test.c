#include "native_clock.h"
#include "platform_time.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>
static uint64_t clock_us = 10000ULL;
static uint32_t step = 1U;
static NativeClockResult port_result = NativeClockResult_Ok;
NativeClockResult NativeClockPort_SnapshotGet(NativeClockSnapshot *sample)
{
    if (port_result != NativeClockResult_Ok) { return port_result; }
    clock_us += step;
    sample->tick_ms = (uint32_t)(clock_us / 1000ULL);
    sample->elapsed_cycles = (uint32_t)(clock_us % 1000ULL) * 72U;
    return NativeClockResult_Ok;
}
int main(int argc, char **argv)
{
    uint64_t value = 0xDEADBEEFULL;
    assert(argc == 2);
    assert(NativeClock_Read(&value) == NativeClockResult_NotInitialized);
    assert(value == 0xDEADBEEFULL);
    assert(NativeClock_Read(NULL) == NativeClockResult_InvalidArgument);
    if (strcmp(argv[1],"wrap") == 0) { clock_us = (uint64_t)UINT32_MAX * 1000ULL + 997ULL; }
    assert(PlatformTime_Init() == PLATFORM_OK);
    assert(NativeClock_Read(&value) == NativeClockResult_Ok);
    if (strcmp(argv[1],"normal") == 0 || strcmp(argv[1],"wrap") == 0)
    {
        uint64_t before=value;
        assert(NativeClock_DelayUs(50U) == NativeClockResult_Ok);
        assert(NativeClock_Read(&value) == NativeClockResult_Ok && value-before>=50ULL);
        before=value; PlatformTime_DelayMs(20U);
        assert(NativeClock_Read(&value) == NativeClockResult_Ok && value-before>=20000ULL);
        assert(NativeClock_StatusGet() == NativeClockResult_Ok);
        if (strcmp(argv[1],"wrap") == 0) { assert(value>(uint64_t)UINT32_MAX*1000ULL); }
        assert(PlatformTime_Init() == PLATFORM_ALREADY_INITIALIZED);
        return 0;
    }
    if (strcmp(argv[1],"stopped") == 0)
    { step=0U; assert(NativeClock_DelayUs(2U) == NativeClockResult_Stopped); }
    else if (strcmp(argv[1],"backwards") == 0)
    { clock_us-=5ULL; assert(NativeClock_Read(&value) == NativeClockResult_Discontinuous); }
    else if (strcmp(argv[1],"gap") == 0)
    { clock_us+=10001000ULL; assert(NativeClock_Read(&value) == NativeClockResult_Discontinuous); }
    else
    { port_result=NativeClockResult_InvalidContext; assert(NativeClock_Read(&value)==port_result); }
    value=0xDEADBEEFULL;
    assert(NativeClock_Read(&value) != NativeClockResult_Ok && value==0xDEADBEEFULL);
    assert(PlatformTime_Init() == PLATFORM_NOT_READY);
    return 0;
}
