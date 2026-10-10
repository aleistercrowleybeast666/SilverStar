#include "native_clock.h"
#include "platform_critical.h"
#include "main.h"
#include <assert.h>
SysTickType tick_regs={7U,71999U,71000U};
ScbType scb_regs;
uint32_t SystemCoreClock=72000000U, hclk=72000000U, mask, exception, hal_tick=10U, changed, tick_frequency=1U;
uint32_t HAL_GetTick(void)
{
    if (changed != 0U) { scb_regs.ICSR ^= SCB_ICSR_PENDSTSET_Msk; }
    return hal_tick;
}
int main(void)
{
    NativeClockSnapshot sample={99U,99U};
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_Ok);
    assert(sample.tick_ms==10U && sample.elapsed_cycles==999U && mask==0U);
    scb_regs.ICSR=SCB_ICSR_PENDSTSET_Msk;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_Ok && sample.tick_ms==11U);
    hal_tick=UINT32_MAX;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_Ok && sample.tick_ms==0U);
    sample.tick_ms=99U; mask=1U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidContext && mask==1U && sample.tick_ms==99U);
    PlatformCriticalState saved=PlatformCritical_Enter();
    assert(saved==1U && mask==1U); PlatformCritical_Exit(saved); assert(mask==1U);
    mask=0U; saved=PlatformCritical_Enter(); assert(saved==0U && mask==1U);
    PlatformCritical_Exit(saved); assert(mask==0U);
    exception=15U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidContext && mask==0U);
    exception=0U; hclk=36000000U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);
    hclk=72000000U; tick_frequency=10U; sample.tick_ms=99U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration && sample.tick_ms==99U);
    tick_frequency=1U; tick_regs.VAL=0U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_UnstableSnapshot && mask==0U);
    tick_regs.VAL=71000U; changed=1U;
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_UnstableSnapshot && mask==0U);
    return 0;
}
